"""
API Routes for Data Status Management
Allows marking devices/users as active/inactive/terminated
"""

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime
import logging

from web.models import db, AzureDevice, AzureUser, Employee, Server
from web.active_data_filter import ActiveDataFilter

logger = logging.getLogger("[STATUS_MGMT]")

status_mgmt_bp = Blueprint('status_mgmt', __name__, url_prefix='/api/v2/status')


@status_mgmt_bp.route('/azure/device/<device_id>/retire', methods=['POST'])
@login_required
def retire_azure_device(device_id):
    """Mark Azure device as retired"""
    try:
        device = db.session.get(AzureDevice, device_id)
        if not device or (not current_user.is_superadmin and device.tenant_id != current_user.tenant_id):
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        device.is_active = 0
        device.device_status = 'retired'
        device.disabled_at = datetime.utcnow()
        db.session.commit()
        
        logger.info(f"User {current_user.username} retired device {device.display_name}")
        
        return jsonify({
            'success': True,
            'message': f"Device '{device.display_name}' marked as retired"
        })
    except Exception as e:
        logger.error(f"Error retiring device: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@status_mgmt_bp.route('/azure/device/<device_id>/mark-inactive', methods=['POST'])
@login_required
def mark_device_inactive(device_id):
    """Manually mark device as inactive"""
    try:
        device = db.session.get(AzureDevice, device_id)
        if not device or (not current_user.is_superadmin and device.tenant_id != current_user.tenant_id):
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        device.is_active = 0
        device.device_status = 'inactive'
        device.disabled_at = datetime.utcnow()
        db.session.commit()
        
        logger.info(f"User {current_user.username} marked device {device.display_name} as inactive")
        
        return jsonify({
            'success': True,
            'message': f"Device '{device.display_name}' marked as inactive"
        })
    except Exception as e:
        logger.error(f"Error marking device inactive: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@status_mgmt_bp.route('/azure/device/<device_id>/reactivate', methods=['POST'])
@login_required
def reactivate_device(device_id):
    """Reactivate a device"""
    try:
        device = db.session.get(AzureDevice, device_id)
        if not device or (not current_user.is_superadmin and device.tenant_id != current_user.tenant_id):
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        device.is_active = 1
        device.device_status = 'active'
        device.disabled_at = None
        db.session.commit()
        
        logger.info(f"User {current_user.username} reactivated device {device.display_name}")
        
        return jsonify({
            'success': True,
            'message': f"Device '{device.display_name}' reactivated"
        })
    except Exception as e:
        logger.error(f"Error reactivating device: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@status_mgmt_bp.route('/azure/user/<user_id>/mark-terminated', methods=['POST'])
@login_required
def mark_user_terminated(user_id):
    """Mark user employment as terminated"""
    try:
        data = request.json or {}
        left_date = data.get('left_date')
        if left_date:
            left_date = datetime.fromisoformat(left_date)
        else:
            left_date = datetime.utcnow()
        
        user = db.session.get(AzureUser, user_id)
        if not user or (not current_user.is_superadmin and user.tenant_id != current_user.tenant_id):
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        user.is_active = 0
        user.employment_status = 'terminated'
        user.left_date = left_date
        db.session.commit()
        
        logger.info(f"User {current_user.username} marked {user.email} as terminated (left: {left_date})")
        
        return jsonify({
            'success': True,
            'message': f"User '{user.email}' marked as terminated",
            'left_date': left_date.isoformat()
        })
    except Exception as e:
        logger.error(f"Error marking user terminated: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@status_mgmt_bp.route('/azure/user/<user_id>/mark-onleave', methods=['POST'])
@login_required
def mark_user_onleave(user_id):
    """Mark user as on leave (temporarily inactive)"""
    try:
        user = db.session.get(AzureUser, user_id)
        if not user or (not current_user.is_superadmin and user.tenant_id != current_user.tenant_id):
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        user.employment_status = 'onleave'
        db.session.commit()
        
        logger.info(f"User {current_user.username} marked {user.email} as on leave")
        
        return jsonify({
            'success': True,
            'message': f"User '{user.email}' marked as on leave"
        })
    except Exception as e:
        logger.error(f"Error marking user on leave: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@status_mgmt_bp.route('/azure/user/<user_id>/reactivate', methods=['POST'])
@login_required
def reactivate_user(user_id):
    """Reactivate a user"""
    try:
        user = db.session.get(AzureUser, user_id)
        if not user or (not current_user.is_superadmin and user.tenant_id != current_user.tenant_id):
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        user.is_active = 1
        user.employment_status = 'active'
        user.left_date = None
        db.session.commit()
        
        logger.info(f"User {current_user.username} reactivated {user.email}")
        
        return jsonify({
            'success': True,
            'message': f"User '{user.email}' reactivated"
        })
    except Exception as e:
        logger.error(f"Error reactivating user: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@status_mgmt_bp.route('/devices/inactive-summary', methods=['GET'])
@login_required
def get_inactive_devices_summary():
    """Get summary of inactive devices"""
    try:
        if current_user.is_superadmin:
            inactive_devices = db.session.query(AzureDevice).filter(
                AzureDevice.is_active == 0,
                AzureDevice.device_status.in_(['inactive', 'retired'])
            ).all()
        else:
            inactive_devices = db.session.query(AzureDevice).filter(
                AzureDevice.tenant_id == current_user.tenant_id,
                AzureDevice.is_active == 0,
                AzureDevice.device_status.in_(['inactive', 'retired'])
            ).all()
        
        inactive_count = len(inactive_devices)
        active_count = ActiveDataFilter.get_device_summary(db, current_user.tenant_id)
        
        return jsonify({
            'success': True,
            'inactive_count': inactive_count,
            'active_summary': active_count,
            'devices': [{
                'id': d.id,
                'name': d.display_name,
                'status': d.device_status,
                'last_activity': d.last_activity.isoformat() if d.last_activity else None,
                'disabled_at': d.disabled_at.isoformat() if d.disabled_at else None
            } for d in inactive_devices[:50]]  # Show first 50
        })
    except Exception as e:
        logger.error(f"Error fetching inactive devices: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@status_mgmt_bp.route('/users/inactive-summary', methods=['GET'])
@login_required
def get_inactive_users_summary():
    """Get summary of terminated/inactive users"""
    try:
        if current_user.is_superadmin:
            inactive_users = db.session.query(AzureUser).filter(
                AzureUser.employment_status.in_(['terminated', 'inactive', 'onleave'])
            ).all()
        else:
            inactive_users = db.session.query(AzureUser).filter(
                AzureUser.tenant_id == current_user.tenant_id,
                AzureUser.employment_status.in_(['terminated', 'inactive', 'onleave'])
            ).all()
        
        user_summary = ActiveDataFilter.get_user_summary(db, current_user.tenant_id)
        
        return jsonify({
            'success': True,
            'summary': user_summary,
            'users': [{
                'id': u.id,
                'email': u.email,
                'name': u.display_name,
                'status': u.employment_status,
                'left_date': u.left_date.isoformat() if u.left_date else None,
                'last_activity': u.last_activity.isoformat() if u.last_activity else None
            } for u in inactive_users[:50]]  # Show first 50
        })
    except Exception as e:
        logger.error(f"Error fetching inactive users: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@status_mgmt_bp.route('/auto-mark-inactive', methods=['POST'])
@login_required
def auto_mark_inactive():
    """Automatically mark devices/users as inactive based on inactivity threshold"""
    if not current_user.is_superadmin:
        return jsonify({'success': False, 'error': 'Admin only'}), 403
    
    try:
        device_count = ActiveDataFilter.mark_inactive_azure_devices(db)
        user_count = ActiveDataFilter.mark_inactive_azure_users(db)
        
        return jsonify({
            'success': True,
            'devices_marked_inactive': device_count,
            'users_marked_inactive': user_count,
            'message': f"Marked {device_count} devices and {user_count} users as inactive"
        })
    except Exception as e:
        logger.error(f"Error in auto-mark-inactive: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
