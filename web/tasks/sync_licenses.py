"""Background sync tasks for license data.

This module exposes `run_license_sync(tenant_id=None)` which can be invoked by a
scheduler, worker, or manually via an admin endpoint.

PERFORMANCE NOTE: We only fetch subscribedSkus (1 API call) for the dashboard.
Per-user license details are fetched separately on-demand, NOT during bulk sync,
because iterating every user is extremely slow for large tenants.
"""
from typing import Optional
import os
import logging
from datetime import datetime

from web.azure_licenses import acquire_token, list_subscribed_skus, list_users_with_assigned_licenses
from web.models import (
    db,
    LicenseSku,
    AzureLicense,
    AzureLicenseAssignment,
    AzureUser,
    LicenseHistory,
    SyncJob,
    AuditLog,
    Tenant,
)

LOG = logging.getLogger(__name__)
_SYNC_RUNNING = False


# Well-known Microsoft SKU → friendly product name mapping
SKU_FRIENDLY_NAMES = {
    'O365_BUSINESS_ESSENTIALS': 'Microsoft 365 Business Basic',
    'O365_BUSINESS_PREMIUM': 'Microsoft 365 Business Standard',
    'SPB': 'Microsoft 365 Business Premium',
    'SMB_BUSINESS': 'Microsoft 365 Apps for Business',
    'SMB_BUSINESS_PREMIUM': 'Microsoft 365 Business Premium',
    'ENTERPRISEPACK': 'Office 365 E3',
    'ENTERPRISEPREMIUM': 'Office 365 E5',
    'DESKLESSPACK': 'Office 365 F3',
    'STANDARDPACK': 'Office 365 E1',
    'EXCHANGESTANDARD': 'Exchange Online Plan 1',
    'EXCHANGEENTERPRISE': 'Exchange Online Plan 2',
    'EMS': 'Enterprise Mobility + Security E3',
    'EMSPREMIUM': 'Enterprise Mobility + Security E5',
    'POWER_BI_STANDARD': 'Power BI (free)',
    'POWER_BI_PRO': 'Power BI Pro',
    'PROJECTPREMIUM': 'Project Plan 5',
    'VISIOCLIENT': 'Visio Plan 2',
    'FLOW_FREE': 'Power Automate Free',
    'TEAMS_EXPLORATORY': 'Microsoft Teams Exploratory',
    'AAD_PREMIUM': 'Azure AD Premium P1',
    'AAD_PREMIUM_P2': 'Azure AD Premium P2',
    'STREAM': 'Microsoft Stream',
    'POWERAPPS_VIRAL': 'Power Apps Trial',
    'WIN10_PRO_ENT_SUB': 'Windows 10/11 Enterprise E3',
    'WINDOWS_STORE': 'Windows Store for Business',
    'ATP_ENTERPRISE': 'Microsoft Defender for Office 365 P1',
    'THREAT_INTELLIGENCE': 'Microsoft Defender for Office 365 P2',
    'IDENTITY_THREAT_PROTECTION': 'Microsoft 365 E5 Security',
    'INFORMATION_PROTECTION_COMPLIANCE': 'Microsoft 365 E5 Compliance',
    'M365_F1': 'Microsoft 365 F1',
    'SPE_E3': 'Microsoft 365 E3',
    'SPE_E5': 'Microsoft 365 E5',
    'SPE_F1': 'Microsoft 365 F3',
    'RIGHTSMANAGEMENT': 'Azure Information Protection Plan 1',
    'MCOSTANDARD': 'Skype for Business Online (Plan 2)',
    'MCOPSTN1': 'Microsoft 365 Domestic Calling Plan',
    'PHONESYSTEM_VIRTUALUSER': 'Phone System - Virtual User',
    'MICROSOFT_BUSINESS_CENTER': 'Microsoft Business Center',
    'EXCHANGEDESKLESS': 'Exchange Online Kiosk',
    'MCOMEETADV': 'Microsoft 365 Audio Conferencing',
    'PROJECTESSENTIALS': 'Project Plan 1',
    'DYN365_ENTERPRISE_PLAN1': 'Dynamics 365 Plan',
    'INTUNE_A': 'Microsoft Intune Plan 1',
    'WINDOWS_STORE': 'Windows Store for Business',
}


def _get_friendly_name(sku_part_number: str) -> str:
    """Map a SKU part number to a human-friendly product name."""
    return SKU_FRIENDLY_NAMES.get(sku_part_number, sku_part_number or 'Unknown')


def _safe_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def repair_azure_device_owner_keys(tenant_id: Optional[int] = None):
    """Convert legacy Graph UUID owner rows to current AzureUser/AzureDevice DB PK rows."""
    from web.models import AzureDeviceOwner, AzureDevice, AzureUser

    query = AzureDeviceOwner.query
    if tenant_id:
        query = query.filter_by(tenant_id=tenant_id)

    converted = 0
    for owner in query.all():
        changed = False

        if not str(owner.user_id).isdigit():
            user = AzureUser.query.filter_by(tenant_id=owner.tenant_id, user_id=owner.user_id).first()
            if user:
                owner.user_id = user.id
                changed = True

        if not str(owner.device_id).isdigit():
            device = AzureDevice.query.filter_by(tenant_id=owner.tenant_id, device_id=owner.device_id).first()
            if device:
                owner.device_id = device.id
                changed = True

        if changed:
            converted += 1

    if converted:
        db.session.commit()
    return converted


def _create_audit(user: Optional[str], tenant_id: Optional[int], action: str, resource: str, details: str, status: str = 'success'):
    try:
        a = AuditLog(user=user or 'system', tenant_id=tenant_id, action=action, resource=resource, details=details, status=status, timestamp=datetime.utcnow())
        db.session.add(a)
        db.session.commit()
    except Exception as e:
        LOG.warning('Failed to create audit log: %s', e)
        db.session.rollback()


def _resolve_credentials(tenant):
    """Resolve Azure credentials: prefer tenant record, fall back to .env."""
    cid = getattr(tenant, 'azure_client_id', None) or os.environ.get('SERVERMONITOR_CLIENT_ID', '')
    csecret = getattr(tenant, 'azure_client_secret', None) or os.environ.get('SERVERMONITOR_CLIENT_SECRET', '')
    toid = getattr(tenant, 'azure_tenant_id', None) or os.environ.get('AZURE_TENANT_ID', '')
    return (cid or '').strip(), (csecret or '').strip(), (toid or '').strip()


def run_license_sync(tenant_id: Optional[int] = None):
    """Run license sync for a single tenant (or all tenants when tenant_id is None).

    This is a FAST sync that only fetches subscribedSkus (1 API call per tenant).
    It populates both LicenseSku (legacy) and AzureLicense (dashboard) models.
    """
    global _SYNC_RUNNING
    if _SYNC_RUNNING:
        LOG.warning('License sync skipped because another license sync is already running')
        return {'skipped': True, 'reason': 'license sync already running'}

    _SYNC_RUNNING = True
    job = SyncJob(tenant_id=tenant_id, job_type='license_sync', status='started', started_at=datetime.utcnow())
    db.session.add(job)
    db.session.commit()
    LOG.info('License sync job %s started (tenant_id=%s)', job.id, tenant_id)

    try:
        if tenant_id:
            tenants = [db.session.get(Tenant, tenant_id)]
        else:
            tenants = Tenant.query.all()

        result = {'tenants': []}
        for t in tenants:
            if not t:
                continue

            cid, csecret, toid = _resolve_credentials(t)

            if not (cid and csecret and toid):
                LOG.warning('Tenant %s (id=%s) missing Azure credentials; skipping', t.name, t.id)
                result['tenants'].append({'tenant_id': t.id, 'skipped': True, 'reason': 'Missing Azure credentials'})
                continue

            LOG.info('Syncing licenses for tenant "%s" (id=%s)...', t.name, t.id)

            # Step 1: Acquire token (app-only client credentials)
            token = acquire_token(cid, csecret, toid)
            LOG.info('Token acquired for tenant "%s"', t.name)

            # Step 2: Fetch SKUs (single fast API call)
            skus = list_subscribed_skus(token)
            LOG.info('Fetched %d SKUs from Azure for tenant "%s"', len(skus), t.name)

            # Step 3: Persist to LicenseSku (legacy model) — only active SKUs
            active_skus = []
            for s in skus:
                # Skip disabled/suspended/expired SKUs
                cap_status = (s.get('capabilityStatus') or '').lower()
                if cap_status and cap_status not in ('enabled', 'warning'):
                    LOG.debug('Skipping SKU %s (capabilityStatus=%s)', s.get('skuPartNumber'), cap_status)
                    continue
                # Skip SKUs with 0 total licenses (free trials that expired)
                prep = s.get('prepaidUnits', {})
                total = prep.get('enabled', 0) if isinstance(prep, dict) else 0
                if total == 0 and s.get('consumedUnits', 0) == 0:
                    LOG.debug('Skipping SKU %s (0 total, 0 consumed)', s.get('skuPartNumber'))
                    continue
                active_skus.append(s)

            LOG.info('Filtered %d → %d active SKUs for tenant "%s"', len(skus), len(active_skus), t.name)

            for s in active_skus:
                sku_id = str(s.get('skuId') or '').lower()
                if not sku_id:
                    continue
                sku = LicenseSku.query.filter(
                    LicenseSku.tenant_id == t.id,
                    db.func.lower(LicenseSku.sku_id) == sku_id,
                ).first()
                if not sku:
                    sku = LicenseSku(tenant_id=t.id, sku_id=sku_id)
                sku.sku_id = sku_id
                sku.sku_part_number = s.get('skuPartNumber')
                prep = s.get('prepaidUnits', {})
                sku.prepaid_units = _safe_int(prep.get('enabled', 0) if isinstance(prep, dict) else 0)
                sku.consumed_units = _safe_int(s.get('consumedUnits', 0))
                sku.meta_data = s
                sku.fetched_at = datetime.utcnow()
                db.session.add(sku)

            # Step 4: Persist to AzureLicense (dashboard model) — only active SKUs
            for s in active_skus:
                sku_id = str(s.get('skuId') or '').lower()
                if not sku_id:
                    continue
                sku_part = s.get('skuPartNumber', '')
                prep = s.get('prepaidUnits', {})
                enabled = prep.get('enabled', 0) if isinstance(prep, dict) else 0
                total = _safe_int(enabled)
                consumed = _safe_int(s.get('consumedUnits', 0))
                available = max(total - consumed, 0)

                az_lic = AzureLicense.query.filter(
                    AzureLicense.tenant_id == t.id,
                    db.func.lower(AzureLicense.sku_id) == sku_id,
                ).first()
                if not az_lic:
                    az_lic = AzureLicense()
                    az_lic.tenant_id = t.id
                az_lic.sku_id = sku_id

                az_lic.sku_name = sku_part
                az_lic.product_name = _get_friendly_name(sku_part)
                az_lic.total_licenses = total
                az_lic.assigned_licenses = consumed
                az_lic.available_licenses = available
                az_lic.service_plans_json = str(s.get('servicePlans', []))
                az_lic.last_synced = datetime.utcnow()
                db.session.add(az_lic)

            # Remove stale AzureLicense rows for SKUs no longer active
            active_sku_ids = {str(s.get('skuId') or '').lower() for s in active_skus if s.get('skuId')}
            stale_licenses = AzureLicense.query.filter(
                AzureLicense.tenant_id == t.id,
                ~AzureLicense.sku_id.in_(active_sku_ids)
            ).all()
            for stale in stale_licenses:
                LOG.info('Removing stale license SKU %s (%s) for tenant "%s"', stale.sku_name, stale.sku_id, t.name)
                AzureLicenseAssignment.query.filter_by(tenant_id=t.id, license_id=stale.id).delete()
                db.session.delete(stale)

            db.session.commit()

            users = list_users_with_assigned_licenses(token)
            LOG.info('Fetched %d users with assignedLicenses for tenant "%s"', len(users), t.name)
            licenses_by_sku = {
                lic.sku_id.lower(): lic
                for lic in AzureLicense.query.filter_by(tenant_id=t.id).all()
                if lic.sku_id
            }
            users_by_graph_id = {
                user.user_id: user
                for user in AzureUser.query.filter_by(tenant_id=t.id).all()
            }
            existing_assignments = {
                (assignment.user_id, assignment.license_id): assignment
                for assignment in AzureLicenseAssignment.query.filter_by(tenant_id=t.id).all()
            }
            seen_assignment_keys = set()
            assignment_upserts = 0

            for user_data in users:
                graph_user_id = user_data.get('id')
                if not graph_user_id:
                    continue

                upn = user_data.get('userPrincipalName') or user_data.get('mail') or 'unknown@unknown.com'
                azure_user = users_by_graph_id.get(graph_user_id)
                if not azure_user:
                    azure_user = AzureUser(tenant_id=t.id, user_id=graph_user_id)
                    db.session.add(azure_user)
                    users_by_graph_id[graph_user_id] = azure_user

                azure_user.email = upn
                azure_user.display_name = user_data.get('displayName') or azure_user.display_name
                azure_user.department = user_data.get('department')
                azure_user.job_title = user_data.get('jobTitle')
                azure_user.mail_nickname = user_data.get('mailNickname')
                azure_user.sam_account_name = user_data.get('onPremisesSamAccountName')
                azure_user.employee_id = user_data.get('employeeId') or user_data.get('employee_id') or azure_user.mail_nickname or upn.split('@', 1)[0]
                azure_user.last_synced = datetime.utcnow()
                db.session.flush()

                for assigned in user_data.get('assignedLicenses', []) or []:
                    sku_id = str(assigned.get('skuId') or '').lower()
                    if not sku_id:
                        continue

                    license_obj = licenses_by_sku.get(sku_id)
                    if not license_obj:
                        LOG.warning('Assignment skipped: SKU %s not found for tenant "%s"', sku_id, t.name)
                        continue

                    key = (azure_user.id, license_obj.id)
                    seen_assignment_keys.add(key)
                    assignment = existing_assignments.get(key)
                    if not assignment:
                        assignment = AzureLicenseAssignment(
                            tenant_id=t.id,
                            user_id=azure_user.id,
                            license_id=license_obj.id,
                            assigned_at=datetime.utcnow(),
                        )
                        db.session.add(assignment)
                        existing_assignments[key] = assignment
                        db.session.add(LicenseHistory(
                            tenant_id=t.id,
                            user_id=graph_user_id,
                            user_principal_name=upn,
                            sku_id=sku_id,
                            event_type='ASSIGNED',
                            event_date=datetime.utcnow(),
                        ))
                        assignment_upserts += 1

                    assignment.disabled_plans_json = str(assigned.get('disabledPlans', []))

            for key, assignment in list(existing_assignments.items()):
                if key in seen_assignment_keys:
                    continue

                user = db.session.get(AzureUser, assignment.user_id)
                lic = db.session.get(AzureLicense, assignment.license_id)
                if user and lic:
                    db.session.add(LicenseHistory(
                        tenant_id=t.id,
                        user_id=user.user_id,
                        user_principal_name=user.email,
                        sku_id=(lic.sku_id or '').lower(),
                        event_type='REMOVED',
                        event_date=datetime.utcnow(),
                    ))
                db.session.delete(assignment)

            db.session.commit()
            LOG.info('Synced %d new license assignments for tenant "%s"', assignment_upserts, t.name)

            tenant_result = {'tenant_id': t.id, 'tenant_name': t.name, 'skus_synced': len(skus)}
            result['tenants'].append(tenant_result)
            LOG.info('License sync completed for tenant "%s": %d SKUs synced', t.name, len(skus))

            _create_audit(user=None, tenant_id=t.id, action='LICENSE_SYNC',
                          resource=f'tenant:{t.id}', details=f"Synced {len(skus)} license SKUs from Azure")

        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.session.commit()
        LOG.info('License sync job %s completed successfully', job.id)
        return result

    except Exception as e:
        LOG.exception('License sync job failed')
        job.status = 'failed'
        job.log = str(e)
        job.completed_at = datetime.utcnow()
        db.session.commit()
        _create_audit(user=None, tenant_id=tenant_id, action='LICENSE_SYNC_FAILED',
                      resource=f'tenant:{tenant_id}', details=str(e), status='failed')
        raise
    finally:
        _SYNC_RUNNING = False
