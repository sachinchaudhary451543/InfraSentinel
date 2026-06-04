"""
Azure Sync Service - Dynamic Detection System
Automatically syncs and detects active/inactive users, devices, and licenses from Azure
"""

import logging
from datetime import datetime, timedelta
from sqlalchemy import func, and_

logger = logging.getLogger("[AZURE_SYNC]")


class AzureSyncService:
    """Service to sync Azure data and detect activity dynamically"""
    
    @staticmethod
    def sync_azure_devices(db, tenant, azure_client):
        """Sync device data from Azure and detect active/inactive"""
        try:
            from web.models import AzureDevice
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            from core.identity_correlation import normalize_hostname
            
            # Fetch devices from Azure Graph API
            devices = azure_client.get_devices()
            
            synced_count = 0
            updated_count = 0

            # Build rows for upsert
            rows = []
            for device_data in devices:
                device_id = device_data.get('id')
                if not device_id:
                    continue

                last_signin = device_data.get('lastSignInDateTime')
                last_activity = None
                is_active = None
                device_status = None
                if last_signin:
                    last_activity = datetime.fromisoformat(last_signin.replace('Z', '+00:00'))
                    days_since_activity = (datetime.utcnow() - last_activity.replace(tzinfo=None)).days
                    if days_since_activity > 90:
                        is_active = 0
                        device_status = 'inactive'
                    else:
                        is_active = 1
                        device_status = 'active'

                row = {
                    'tenant_id': tenant.id,
                    'device_id': device_id,
                    'display_name': device_data.get('displayName', 'Unknown'),
                    'normalized_hostname': normalize_hostname(device_data.get('displayName', 'Unknown')),
                    'device_type': device_data.get('deviceType', 'Unknown'),
                    'os_platform': device_data.get('operatingSystem', 'Unknown'),
                    'os_version': device_data.get('operatingSystemVersion', 'Unknown'),
                    'is_compliant': bool(device_data.get('isCompliant', False)),
                    'is_managed_by_intune': device_data.get('managedBy') == 'Intune',
                    'last_activity': last_activity,
                    'last_synced': datetime.utcnow(),
                    'is_active': is_active,
                    'device_status': device_status,
                }
                rows.append(row)

            # If using Postgres, use INSERT ... ON CONFLICT to upsert efficiently
            dialect_name = getattr(db.session.bind.dialect, 'name', None)
            if dialect_name == 'postgresql' and rows:
                try:
                    table = AzureDevice.__table__
                    insert_stmt = pg_insert(table).values(rows)
                    update_cols = {c.name: insert_stmt.excluded[c.name] for c in table.c if c.name not in ('id', 'created_at')}
                    upsert = insert_stmt.on_conflict_do_update(index_elements=['tenant_id', 'device_id'], set_=update_cols)
                    db.session.execute(upsert)
                    db.session.commit()

                    # estimate counts (best-effort)
                    synced_count = len([r for r in rows if r.get('last_synced')])
                    updated_count = 0
                    logger.info(f"Upserted {len(rows)} devices for tenant {tenant.name} (postgres path)")
                    return {'synced': synced_count, 'updated': updated_count}
                except Exception as e:
                    logger.warning(f"Postgres upsert failed, falling back to ORM path: {e}")
                    db.session.rollback()

            # Non-Postgres fallback: fetch existing and update
            existing = {d.device_id: d for d in AzureDevice.query.filter_by(tenant_id=tenant.id).all()}
            new_devices = []
            for r in rows:
                device = existing.get(r['device_id'])
                if not device:
                    device = AzureDevice()
                    device.tenant_id = r['tenant_id']
                    device.device_id = r['device_id']
                    new_devices.append(device)
                    synced_count += 1
                else:
                    updated_count += 1
                # apply fields
                device.display_name = r['display_name']
                device.normalized_hostname = r['normalized_hostname']
                device.device_type = r['device_type']
                device.os_platform = r['os_platform']
                device.os_version = r['os_version']
                device.is_compliant = r['is_compliant']
                device.is_managed_by_intune = r['is_managed_by_intune']
                device.last_activity = r['last_activity']
                device.last_synced = r['last_synced']
                device.is_active = r['is_active']
                device.device_status = r['device_status']

            if new_devices:
                try:
                    db.session.bulk_save_objects(new_devices)
                except Exception:
                    for nd in new_devices:
                        db.session.add(nd)

            db.session.commit()
            logger.info(f"Synced {synced_count} new devices, updated {updated_count} devices for tenant {tenant.name}")
            return {'synced': synced_count, 'updated': updated_count}
        
        except Exception as e:
            logger.error(f"Error syncing devices: {e}")
            db.session.rollback()
            return {'error': str(e)}
    
    @staticmethod
    def sync_azure_users(db, tenant, azure_client):
        """Sync user data from Azure and detect active/inactive"""
        try:
            from web.models import AzureUser
            
            # Fetch users from Azure Graph API
            users = azure_client.get_users()
            
            synced_count = 0
            updated_count = 0
            
            synced_count = 0
            updated_count = 0

            # Prefetch existing users for this tenant
            existing = {u.user_id: u for u in AzureUser.query.filter_by(tenant_id=tenant.id).all()}
            new_users = []

            for user_data in users:
                user_id = user_data.get('id')
                if not user_id:
                    continue

                user = existing.get(user_id)
                if not user:
                    user = AzureUser()
                    user.tenant_id = tenant.id
                    user.user_id = user_id
                    synced_count += 1
                    new_users.append(user)
                else:
                    updated_count += 1

                # Update user properties
                user.email = user_data.get('userPrincipalName', 'unknown@unknown.com')
                user.display_name = user_data.get('displayName', 'Unknown')
                user.job_title = user_data.get('jobTitle')
                user.department = user_data.get('department')
                user.mail_nickname = user_data.get('mailNickname')
                user.sam_account_name = user_data.get('onPremisesSamAccountName')

                # Extract employee ID from Azure AD employeeId attribute (camelCase from Graph API)
                email_parts = user.email.split('@')
                user.employee_id = user_data.get('employeeId') or user_data.get('employee_id') or user_data.get('mailNickname') or email_parts[0]

                # Detect activity from Azure (lastActivityDateTime via Intune)
                last_activity = user_data.get('lastActivityDateTime')
                if last_activity:
                    user.last_activity = datetime.fromisoformat(last_activity.replace('Z', '+00:00'))

                    # Auto-detect inactive (120 days threshold)
                    days_since_activity = (datetime.utcnow() - user.last_activity.replace(tzinfo=None)).days

                    if days_since_activity > 120:
                        user.is_active = 0
                        user.employment_status = 'inactive'
                    else:
                        user.is_active = 1
                        user.employment_status = 'active'

                # Check if account is disabled
                if user_data.get('accountEnabled') == False:
                    user.is_active = 0
                    user.employment_status = 'terminated'
                    user.left_date = datetime.utcnow()

                user.last_synced = datetime.utcnow()

            # Bulk save new users
            if new_users:
                try:
                    db.session.bulk_save_objects(new_users)
                except Exception:
                    for nu in new_users:
                        db.session.add(nu)

            db.session.commit()
            logger.info(f"Synced {synced_count} new users, updated {updated_count} users for tenant {tenant.name}")
            return {'synced': synced_count, 'updated': updated_count}

        except Exception as e:
            logger.error(f"Error syncing users: {e}")
            db.session.rollback()
            return {'error': str(e)}
    
    @staticmethod
    def sync_azure_licenses(db, tenant, azure_client):
        """Sync license data from Azure"""
        try:
            from web.models import AzureLicense, AzureLicenseAssignment
            
            # Fetch all subscribed SKUs from Azure
            licenses = azure_client.get_subscribed_skus()
            
            synced_count = 0
            
            for license_data in licenses:
                sku_id = str(license_data.get('skuId') or '').lower()
                if not sku_id:
                    continue
                
                # Check if license exists
                license_obj = AzureLicense.query.filter(
                    AzureLicense.tenant_id == tenant.id,
                    db.func.lower(AzureLicense.sku_id) == sku_id
                ).first()
                
                if not license_obj:
                    license_obj = AzureLicense()
                    license_obj.tenant_id = tenant.id
                    synced_count += 1
                license_obj.sku_id = sku_id
                
                # Update license properties
                license_obj.sku_name = license_data.get('skuPartNumber', 'Unknown')
                license_obj.product_name = license_data.get('productName', 'Unknown')
                
                # Parse service plans
                service_plans = license_data.get('servicePlans', [])
                license_obj.service_plans_json = str(service_plans)
                
                # License counts
                prep = license_data.get('prepaidUnits', {})
                enabled = prep.get('enabled', 0) if isinstance(prep, dict) else 0
                consumed = license_data.get('consumedUnits', license_data.get('assignedUnits', 0))
                total = int(enabled or 0)
                consumed = int(consumed or 0)
                license_obj.total_licenses = total
                license_obj.assigned_licenses = consumed
                license_obj.available_licenses = max(total - consumed, 0)
                
                license_obj.last_synced = datetime.utcnow()
                db.session.add(license_obj)
            
            db.session.commit()
            logger.info(f"Synced {synced_count} licenses for tenant {tenant.name}")
            
            # Now sync license assignments
            return AzureSyncService.sync_license_assignments(db, tenant, azure_client)
        
        except Exception as e:
            logger.error(f"Error syncing licenses: {e}")
            db.session.rollback()
            return {'error': str(e)}
    
    @staticmethod
    def sync_license_assignments(db, tenant, azure_client):
        """Sync individual license assignments to users"""
        try:
            from web.models import AzureLicense, AzureLicenseAssignment, AzureUser
            
            assignment_count = 0
            
            # Get all users with licenses
            users_with_licenses = azure_client.get_users_with_licenses()
            
            for user_data in users_with_licenses:
                user_id = user_data.get('id')
                user_email = user_data.get('userPrincipalName')
                
                # Find the user in our database
                user = AzureUser.query.filter_by(
                    tenant_id=tenant.id,
                    user_id=user_id
                ).first()
                
                if not user:
                    continue
                
                # Get assigned licenses for this user from Graph
                assigned_skus = user_data.get('assignedLicenses', [])
                current_sku_ids = {str(sku_data.get('skuId')).lower() for sku_data in assigned_skus if sku_data.get('skuId')}
                
                # Get previous assignments
                previous_assignments = AzureLicenseAssignment.query.filter_by(
                    user_id=user.id,
                    tenant_id=tenant.id
                ).all()
                
                previous_sku_db_map = {a.license_id: a for a in previous_assignments}
                
                # We need to map license_id to sku_id
                from web.models import AzureLicense, LicenseHistory
                previous_skus = {}
                for a in previous_assignments:
                    lic = AzureLicense.query.get(a.license_id)
                    if lic:
                        previous_skus[(lic.sku_id or '').lower()] = a
                
                # Detect REMOVALS (was in DB, not in new payload)
                for old_sku_id, old_assign in previous_skus.items():
                    if str(old_sku_id).lower() not in current_sku_ids:
                        # Log removal
                        hist = LicenseHistory(
                            tenant_id=tenant.id,
                            user_id=user_id,
                            user_principal_name=user_email,
                            sku_id=old_sku_id,
                            event_type='REMOVED',
                            event_date=datetime.utcnow()
                        )
                        db.session.add(hist)
                        db.session.delete(old_assign)
                
                # Create new assignments
                for sku_data in assigned_skus:
                    sku_id = str(sku_data.get('skuId') or '').lower()
                    if not sku_id:
                        continue
                    
                    if sku_id in {str(k).lower() for k in previous_skus.keys()}:
                        continue # Already assigned, skip
                        
                    # Find the license in our database
                    license_obj = AzureLicense.query.filter(
                        AzureLicense.tenant_id == tenant.id,
                        db.func.lower(AzureLicense.sku_id) == sku_id
                    ).first()
                    
                    if not license_obj:
                        continue
                    
                    assignment = AzureLicenseAssignment()
                    assignment.tenant_id = tenant.id
                    assignment.user_id = user.id
                    assignment.license_id = license_obj.id
                    assignment.assigned_at = datetime.utcnow()
                    
                    # Get disabled plans
                    disabled_plans = sku_data.get('disabledPlans', [])
                    assignment.disabled_plans_json = str(disabled_plans)
                    
                    db.session.add(assignment)
                    
                    # Log Assignment
                    hist = LicenseHistory(
                        tenant_id=tenant.id,
                        user_id=user_id,
                        user_principal_name=user_email,
                        sku_id=sku_id,
                        event_type='ASSIGNED',
                        event_date=datetime.utcnow()
                    )
                    db.session.add(hist)
                    
                    assignment_count += 1
            
            # Create snapshot
            from web.models import TenantLicenseSummary, AzureLicense
            for lic in AzureLicense.query.filter_by(tenant_id=tenant.id).all():
                summary = TenantLicenseSummary.query.filter_by(
                    tenant_id=tenant.id,
                    sku_id=lic.sku_id,
                    snapshot_date=datetime.utcnow().date()
                ).first()
                if not summary:
                    summary = TenantLicenseSummary(
                        tenant_id=tenant.id,
                        sku_id=lic.sku_id,
                        sku_part_number=lic.sku_name,
                        snapshot_date=datetime.utcnow().date()
                    )
                    db.session.add(summary)
                summary.total_units = lic.total_licenses
                summary.consumed_units = lic.assigned_licenses
                
            db.session.commit()
            logger.info(f"Synced {assignment_count} license assignments for tenant {tenant.name}")
            return {'assignments': assignment_count}
        
        except Exception as e:
            logger.error(f"Error syncing license assignments: {e}")
            db.session.rollback()
            return {'error': str(e)}
    
    @staticmethod
    def sync_device_user_mapping(db, tenant, azure_client):
        """Map devices to their owners/assigned users"""
        try:
            from web.models import AzureDevice, AzureUser, AzureDeviceOwner
            
            mapping_count = 0
            
            devices = AzureDevice.query.filter_by(tenant_id=tenant.id).all()
            users_by_graph_id = {
                user.user_id: user
                for user in AzureUser.query.filter_by(tenant_id=tenant.id).all()
            }
            
            for device in devices:
                if hasattr(azure_client, 'get_device_owners'):
                    owners = azure_client.get_device_owners(device.device_id)
                else:
                    graph_devices = azure_client.get_devices()
                    match = next((d for d in graph_devices if d.get('id') == device.device_id), {})
                    owners = match.get('owners', [])
                
                # Clear old mappings
                AzureDeviceOwner.query.filter_by(tenant_id=tenant.id, device_id=device.id).delete()
                
                # Create new mappings
                for owner_data in owners:
                    owner_user_id = owner_data.get('id')
                    
                    # Find user in database
                    user = users_by_graph_id.get(owner_user_id)
                    
                    if not user:
                        continue
                    
                    mapping = AzureDeviceOwner()
                    mapping.tenant_id = tenant.id
                    mapping.device_id = device.id
                    mapping.user_id = user.id
                    mapping.owner_type = "registeredOwner"
                    mapping.linked_at = datetime.utcnow()
                    
                    db.session.add(mapping)
                    mapping_count += 1
            
            db.session.commit()
            logger.info(f"Synced {mapping_count} device-user mappings for tenant {tenant.name}")
            return {'mappings': mapping_count}
        
        except Exception as e:
            logger.error(f"Error syncing device-user mappings: {e}")
            db.session.rollback()
            return {'error': str(e)}
    
    @staticmethod
    def get_full_sync(db, tenant, azure_client):
        """Perform complete sync of all Azure data"""
        try:
            logger.info(f"Starting full Azure sync for tenant {tenant.name}...")
            
            result = {
                'tenant': tenant.name,
                'timestamp': datetime.utcnow().isoformat(),
                'devices': AzureSyncService.sync_azure_devices(db, tenant, azure_client),
                'users': AzureSyncService.sync_azure_users(db, tenant, azure_client),
                'licenses': AzureSyncService.sync_azure_licenses(db, tenant, azure_client),
                'device_mappings': AzureSyncService.sync_device_user_mapping(db, tenant, azure_client),
            }
            
            logger.info(f"Full Azure sync completed for tenant {tenant.name}")
            return result
        
        except Exception as e:
            logger.error(f"Error in full sync: {e}")
            return {'error': str(e)}
