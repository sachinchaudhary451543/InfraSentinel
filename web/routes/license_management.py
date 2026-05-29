"""
License Management API
Complete license overview, breakdown, and assignment tracking
"""

from flask import Blueprint, request, jsonify, g
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy import func
import logging

logger = logging.getLogger("[LICENSE_MGMT]")

license_bp = Blueprint('licenses', __name__, url_prefix='/api/v2/licenses')


def is_azure_configured(tenant_id):
    from web.models import Tenant, db
    tenant = db.session.get(Tenant, tenant_id)
    if not tenant:
        return False
    cid = (getattr(tenant, 'azure_client_id', None) or '').strip()
    csecret = (getattr(tenant, 'azure_client_secret', None) or '').strip()
    tid = (getattr(tenant, 'azure_tenant_id', None) or '').strip()
    return bool(cid and csecret and tid)


def _populate_license_assignments_from_graph(tenant_id, license_obj):
    """Best-effort drawer fallback: fetch assignedLicenses once and cache matching users."""
    from web.models import Tenant, AzureLicenseAssignment, AzureUser, db
    from web.azure_licenses import acquire_token, list_users_with_assigned_licenses

    tenant = db.session.get(Tenant, tenant_id)
    if not tenant:
        return 0

    cid = (getattr(tenant, 'azure_client_id', None) or '').strip()
    csecret = (getattr(tenant, 'azure_client_secret', None) or '').strip()
    tid = (getattr(tenant, 'azure_tenant_id', None) or '').strip()
    if not (cid and csecret and tid):
        logger.warning("License drawer fallback skipped: missing Azure credentials for tenant %s", tenant_id)
        return 0

    token = acquire_token(cid, csecret, tid)
    target_sku = (license_obj.sku_id or '').lower()
    users = list_users_with_assigned_licenses(token)
    users_by_graph_id = {
        u.user_id: u for u in AzureUser.query.filter_by(tenant_id=tenant_id).all()
    }
    created = 0

    for user_data in users:
        assigned_skus = {
            str(item.get('skuId') or '').lower()
            for item in (user_data.get('assignedLicenses') or [])
            if item.get('skuId')
        }
        if target_sku not in assigned_skus:
            continue

        graph_user_id = user_data.get('id')
        if not graph_user_id:
            continue

        email = user_data.get('userPrincipalName') or user_data.get('mail') or 'unknown@unknown.com'
        azure_user = users_by_graph_id.get(graph_user_id)
        if not azure_user:
            azure_user = AzureUser(tenant_id=tenant_id, user_id=graph_user_id)
            db.session.add(azure_user)
            users_by_graph_id[graph_user_id] = azure_user

        azure_user.email = email
        azure_user.display_name = user_data.get('displayName') or azure_user.display_name
        azure_user.department = user_data.get('department')
        azure_user.job_title = user_data.get('jobTitle')
        azure_user.mail_nickname = user_data.get('mailNickname')
        azure_user.sam_account_name = user_data.get('onPremisesSamAccountName')
        azure_user.employee_id = azure_user.mail_nickname or email.split('@', 1)[0]
        db.session.flush()

        assignment = AzureLicenseAssignment.query.filter_by(
            tenant_id=tenant_id,
            user_id=azure_user.id,
            license_id=license_obj.id,
        ).first()
        if not assignment:
            assignment = AzureLicenseAssignment(
                tenant_id=tenant_id,
                user_id=azure_user.id,
                license_id=license_obj.id,
                assigned_at=datetime.utcnow(),
            )
            db.session.add(assignment)
            created += 1

    db.session.commit()
    return created


# ─────────────────────────────────────────────────────────────────────────────
# License Summary (lightweight endpoint for quick dashboard data)
# ─────────────────────────────────────────────────────────────────────────────

@license_bp.route('/summary')
@login_required
def summary():
    """Return license SKUs and per-user assignments for the current tenant."""
    from web.models import LicenseSku, LicenseAssignment

    tenant_id = getattr(g, 'request_tenant_id', None) or current_user.tenant_id
    if not is_azure_configured(tenant_id):
        return jsonify({'success': True, 'skus': [], 'assignments': [], 'not_configured': True})

    skus = LicenseSku.query.filter_by(tenant_id=tenant_id).all()
    assigns = LicenseAssignment.query.filter_by(tenant_id=tenant_id).all()

    skus_out = [
        {
            'sku_id': s.sku_id,
            'sku_part_number': s.sku_part_number,
            'prepaid_units': s.prepaid_units,
            'consumed_units': s.consumed_units,
            'metadata': s.meta_data,
            'fetched_at': s.fetched_at.isoformat() if s.fetched_at else None
        }
        for s in skus
    ]

    assigns_out = [
        {
            'user_id': a.user_id,
            'user_principal_name': a.user_principal_name,
            'sku_id': a.sku_id,
            'state': a.state,
            'last_seen': a.last_seen.isoformat() if a.last_seen else None,
            'metadata': a.meta_data,
        }
        for a in assigns
    ]

    return jsonify({'success': True, 'skus': skus_out, 'assignments': assigns_out})


# ─────────────────────────────────────────────────────────────────────────────
# License Overview (full dashboard data with AzureLicense model)
# ─────────────────────────────────────────────────────────────────────────────

@license_bp.route('/overview', methods=['GET'])
@login_required
def get_license_overview():
    """Get complete license overview"""
    if not current_user.is_superadmin:
        return jsonify({'error': 'Admin only'}), 403
    
    try:
        from web.models import db, AzureLicense
        
        tenant_id = getattr(g, 'request_tenant_id', None) or current_user.tenant_id
        if not is_azure_configured(tenant_id):
            return jsonify({
                'success': True,
                'not_configured': True,
                'licenses': [],
                'summary': {
                    'total_licenses': 0,
                    'assigned_licenses': 0,
                    'available_licenses': 0,
                    'utilization_percentage': 0
                }
            })

        licenses = db.session.query(AzureLicense).filter_by(tenant_id=tenant_id).all()
        
        total_assigned = sum(l.assigned_licenses or 0 for l in licenses)
        total_available = sum(l.available_licenses or 0 for l in licenses)
        total_licenses = sum(l.total_licenses or 0 for l in licenses)
        
        return jsonify({
            'success': True,
            'timestamp': datetime.utcnow().isoformat(),
            'summary': {
                'total_licenses': total_licenses,
                'assigned_licenses': total_assigned,
                'available_licenses': total_available,
                'utilization_percentage': round((total_assigned / total_licenses * 100) if total_licenses > 0 else 0, 2)
            },
            'licenses': [{
                'id': l.id,
                'sku_id': l.sku_id,
                'sku_name': l.sku_name,
                'product_name': l.product_name,
                'total': l.total_licenses,
                'assigned': l.assigned_licenses,
                'available': l.available_licenses,
                'utilization': round((l.assigned_licenses / l.total_licenses * 100) if l.total_licenses > 0 else 0, 2),
                'last_synced': l.last_synced.isoformat() if l.last_synced else None
            } for l in licenses]
        })
    
    except Exception as e:
        logger.error(f"Error getting license overview: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@license_bp.route('/<int:license_id>/breakdown', methods=['GET'])
@login_required
def get_license_breakdown(license_id):
    """Get detailed breakdown of a specific license - users assigned to this SKU"""
    if not current_user.is_superadmin:
        return jsonify({'error': 'Admin only'}), 403
    
    try:
        from web.models import db, AzureLicense, AzureLicenseAssignment, AzureUser, LicenseAssignment, Employee
        
        tenant_id = getattr(g, 'request_tenant_id', None) or current_user.tenant_id
        if not is_azure_configured(tenant_id):
            return jsonify({'success': True, 'assigned_users': [], 'not_configured': True, 'assignment_count': 0})

        license_obj = db.session.get(AzureLicense, license_id)
        if not license_obj:
            return jsonify({'success': False, 'error': 'License not found'}), 404
        
        if license_obj.tenant_id != tenant_id:
            return jsonify({'success': False, 'error': 'License not found'}), 404
        
        # Primary source: AzureLicenseAssignment (populated by sync service)
        az_assignments = db.session.query(
            AzureLicenseAssignment, AzureUser
        ).join(
            AzureUser, AzureLicenseAssignment.user_id == AzureUser.id
        ).filter(
            AzureLicenseAssignment.license_id == license_obj.id,
            AzureLicenseAssignment.tenant_id == tenant_id
        ).all()
        
        assigned_users = []
        seen_emails = set()
        
        for assignment, user in az_assignments:
            email = (user.email or '').strip()
            if email.lower() in seen_emails:
                continue
            seen_emails.add(email.lower())

            employee = None
            if email:
                employee = Employee.query.filter_by(tenant_id=tenant_id, email=email).first()
            display_name = user.display_name or (employee.name if employee else None) or email.split('@')[0].replace('.', ' ').title()
            
            assigned_users.append({
                'user_id': user.id,
                'display_name': display_name,
                'email': email,
                'name': display_name,
                'department': user.department or (employee.department if employee else None),
                'job_title': user.job_title or (employee.job_title if employee else None),
                'assigned_at': assignment.assigned_at.isoformat() if assignment.assigned_at else (assignment.created_at.isoformat() if getattr(assignment, 'created_at', None) else None),
                'state': 'active'
            })

        # Fallback: also check legacy LicenseAssignment table if no data above
        if not assigned_users:
            legacy_assignments = LicenseAssignment.query.filter_by(
                tenant_id=tenant_id,
                sku_id=(license_obj.sku_id or '').lower()
            ).all()
            
            emails = [a.user_principal_name for a in legacy_assignments if a.user_principal_name]
            user_map = {}
            if emails:
                azure_users = AzureUser.query.filter(AzureUser.email.in_(emails)).all()
                user_map = {u.email.lower(): u for u in azure_users}
            
            for a in legacy_assignments:
                email = (a.user_principal_name or '').strip()
                azure_u = user_map.get(email.lower())
                employee = Employee.query.filter_by(tenant_id=tenant_id, email=email).first() if email else None
                name = azure_u.display_name if azure_u else (employee.name if employee else email.split('@')[0].replace('.', ' ').title())
                dept = azure_u.department if azure_u else (employee.department if employee else None)
                job_title = azure_u.job_title if azure_u else (employee.job_title if employee else None)
                
                assigned_users.append({
                    'user_id': a.user_id,
                    'display_name': name,
                    'email': email,
                    'name': name,
                    'department': dept,
                    'job_title': job_title,
                    'assigned_at': a.assigned_at.isoformat() if a.assigned_at else (a.last_seen.isoformat() if a.last_seen else None),
                    'state': a.state or 'active'
                })
        
        # Sort by name
        assigned_users.sort(key=lambda x: (x.get('name') or '').lower())
        
        return jsonify({
            'success': True,
            'license': {
                'id': license_obj.id,
                'sku_id': license_obj.sku_id,
                'sku_name': license_obj.sku_name,
                'product_name': license_obj.product_name,
                'total': license_obj.total_licenses,
                'assigned': license_obj.assigned_licenses,
                'available': license_obj.available_licenses
            },
            'assigned_users': assigned_users,
            'assignment_count': len(assigned_users)
        })
    
    except Exception as e:
        logger.error(f"Error getting license breakdown: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@license_bp.route('/user/<int:user_id>/assignments', methods=['GET'])
@login_required
def get_user_licenses(user_id):
    """Get all licenses assigned to a user"""
    if not current_user.is_superadmin:
        return jsonify({'error': 'Admin only'}), 403
    
    try:
        from web.models import db, AzureUser, AzureLicenseAssignment, AzureLicense
        
        tenant_id = getattr(g, 'request_tenant_id', None) or current_user.tenant_id
        if not is_azure_configured(tenant_id):
            return jsonify({'success': True, 'licenses': [], 'license_count': 0, 'not_configured': True})

        user = db.session.get(AzureUser, user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        assignments = db.session.query(
            AzureLicense.sku_name,
            AzureLicense.product_name,
            AzureLicenseAssignment.assigned_at,
            AzureLicenseAssignment.disabled_plans_json
        ).join(
            AzureLicense, AzureLicenseAssignment.license_id == AzureLicense.id
        ).filter(
            AzureLicenseAssignment.user_id == user_id
        ).all()
        
        licenses = []
        for row in assignments:
            licenses.append({
                'sku_name': row[0],
                'product_name': row[1],
                'assigned_at': row[2].isoformat() if row[2] else None,
                'disabled_plans': row[3] or '[]'
            })
        
        return jsonify({
            'success': True,
            'user': {
                'id': user.id,
                'email': user.email,
                'name': user.display_name,
                'department': user.department
            },
            'licenses': licenses,
            'license_count': len(licenses)
        })
    
    except Exception as e:
        logger.error(f"Error getting user licenses: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@license_bp.route('/report/utilization', methods=['GET'])
@login_required
def get_utilization_report():
    """Get license utilization report"""
    if not current_user.is_superadmin:
        return jsonify({'error': 'Admin only'}), 403
    
    try:
        from web.models import db, AzureLicense
        
        tenant_id = getattr(g, 'request_tenant_id', None) or current_user.tenant_id
        if not is_azure_configured(tenant_id):
            return jsonify({
                'success': True,
                'not_configured': True,
                'summary': {
                    'high_utilization': 0,
                    'medium_utilization': 0,
                    'low_utilization': 0
                },
                'high_utilization_licenses': [],
                'medium_utilization_licenses': [],
                'low_utilization_licenses': []
            })

        licenses = db.session.query(AzureLicense).filter_by(tenant_id=tenant_id).all()
        
        # Group by utilization buckets
        high_util = []    # 80-100%
        medium_util = []  # 50-79%
        low_util = []     # 0-49%
        
        for license in licenses:
            util = (license.assigned_licenses / license.total_licenses * 100) if license.total_licenses > 0 else 0
            
            license_info = {
                'id': license.id,
                'product_name': license.product_name,
                'total': license.total_licenses,
                'assigned': license.assigned_licenses,
                'available': license.available_licenses,
                'utilization': round(util, 2)
            }
            
            if util >= 80:
                high_util.append(license_info)
            elif util >= 50:
                medium_util.append(license_info)
            else:
                low_util.append(license_info)
        
        return jsonify({
            'success': True,
            'timestamp': datetime.utcnow().isoformat(),
            'summary': {
                'high_utilization': len(high_util),
                'medium_utilization': len(medium_util),
                'low_utilization': len(low_util)
            },
            'high_utilization_licenses': high_util,
            'medium_utilization_licenses': medium_util,
            'low_utilization_licenses': low_util
        })
    
    except Exception as e:
        logger.error(f"Error getting utilization report: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@license_bp.route('/sync-status', methods=['GET'])
@login_required
def get_sync_status():
    """Get last sync time for licenses"""
    if not current_user.is_superadmin:
        return jsonify({'error': 'Admin only'}), 403
    
    try:
        from web.models import db, AzureLicense
        
        tenant_id = getattr(g, 'request_tenant_id', None) or current_user.tenant_id
        if not is_azure_configured(tenant_id):
            return jsonify({
                'success': True,
                'not_configured': True,
                'last_synced': None,
                'message': 'Azure credentials are not configured.'
            })

        latest_sync = db.session.query(AzureLicense).filter_by(tenant_id=tenant_id).order_by(
            AzureLicense.last_synced.desc()
        ).first()
        
        if latest_sync:
            return jsonify({
                'success': True,
                'last_synced': latest_sync.last_synced.isoformat(),
                'last_synced_ago': str(datetime.utcnow() - latest_sync.last_synced)
            })
        else:
            return jsonify({
                'success': True,
                'last_synced': None,
                'message': 'No license sync data available'
            })
    
    except Exception as e:
        logger.error(f"Error getting sync status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@license_bp.route('/sync', methods=['POST'])
@login_required
def trigger_license_sync():
    """Trigger an immediate license sync (admin only). Runs synchronously and returns results."""
    if not current_user.is_superadmin:
        return jsonify({'error': 'Admin only'}), 403

    try:
        from web.tasks.sync_licenses import run_license_sync

        tenant_id = current_user.tenant_id
        if not is_azure_configured(tenant_id):
            return jsonify({
                'success': False,
                'error': 'Azure credentials are not configured. Please go to Tenant Settings to configure them.'
            }), 400

        logger.info(f"Manual license sync triggered by {current_user.username} for tenant {tenant_id}")

        result = run_license_sync(tenant_id=tenant_id)
        logger.info(f"License sync completed: {result}")

        return jsonify({
            'success': True,
            'message': 'License sync completed successfully',
            'result': result
        })

    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"License sync failed: {error_detail}")
        return jsonify({
            'success': False,
            'error': str(e),
            'detail': error_detail
        }), 500
