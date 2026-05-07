"""
Enhanced API endpoints for:
1. Accurate productivity tracking with app usage
2. Real-time domain discovery polling
3. Domain system management (add/remove/manage discovered systems)
"""

import logging
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from sqlalchemy import func, desc, case

from web.models import (
    db, Server, EmployeeActivity, Metric, Screenshot, 
    Tenant, DeviceActivity, SystemDiscovery
)

logger = logging.getLogger("[API_IMPROVEMENTS]")
api_imp_bp = Blueprint('api_improvements', __name__)


@api_imp_bp.route('/api/v2/productivity/accurate/<int:server_id>', methods=['GET'])
@login_required
def get_accurate_productivity(server_id):
    """
    Get accurate productivity metrics using DeviceActivity data (actual active/idle times)
    instead of EmployeeActivity sample counts.
    
    Returns:
    - Productivity percentage based on actual active time vs total time
    - Top applications/windows used
    - Breakdown by user
    - Time period: Last 24 hours by default, or specify ?days=N
    """
    try:
        server = Server.query.get_or_404(server_id)
        if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
            return jsonify({'error': 'Unauthorized'}), 403

        # Get time period from query params
        days = request.args.get('days', 1, type=int)
        cutoff_time = datetime.utcnow() - timedelta(days=days)

        # 1. Get productivity from DeviceActivity (actual login/logout times with active/idle minutes)
        activities = DeviceActivity.query.filter(
            DeviceActivity.server_id == server_id,
            DeviceActivity.reported_at >= cutoff_time
        ).all()

        total_active_minutes = 0
        total_idle_minutes = 0
        user_breakdown = {}
        session_details = []

        for activity in activities:
            active = activity.active_minutes or 0
            idle = activity.idle_minutes or 0
            total_active_minutes += active
            total_idle_minutes += idle

            user = activity.session_user or 'Unknown'
            if user not in user_breakdown:
                user_breakdown[user] = {'active': 0, 'idle': 0, 'sessions': 0}
            
            user_breakdown[user]['active'] += active
            user_breakdown[user]['idle'] += idle
            user_breakdown[user]['sessions'] += 1

            session_details.append({
                'user': user,
                'login': activity.login_time.isoformat() if activity.login_time else None,
                'logout': activity.logout_time.isoformat() if activity.logout_time else None,
                'active_minutes': active,
                'idle_minutes': idle,
                'session_type': activity.session_type,
                'productivity_percent': int((active / (active + idle) * 100)) if (active + idle) > 0 else 0
            })

        # Calculate overall productivity
        total_time = total_active_minutes + total_idle_minutes
        overall_productivity = int((total_active_minutes / total_time * 100)) if total_time > 0 else 0

        # 2. Get top applications from EmployeeActivity (if available)
        app_usage = db.session.query(
            EmployeeActivity.app,
            EmployeeActivity.window_title,
            func.count(EmployeeActivity.id).label('sample_count')
        ).filter(
            EmployeeActivity.server_id == server_id,
            EmployeeActivity.timestamp >= cutoff_time
        ).group_by(
            EmployeeActivity.app,
            EmployeeActivity.window_title
        ).order_by(desc('sample_count')).limit(10).all()

        top_apps = [
            {
                'app': app or 'Unknown',
                'window_title': window or '—',
                'sample_count': int(count),
                'estimated_minutes': int(count * 10 / 60)  # Assume 10s samples
            }
            for app, window, count in app_usage
        ]

        return jsonify({
            'success': True,
            'server_id': server_id,
            'period_days': days,
            'cutoff_time': cutoff_time.isoformat(),
            'productivity': {
                'overall_percent': overall_productivity,
                'total_active_minutes': total_active_minutes,
                'total_idle_minutes': total_idle_minutes,
                'total_session_minutes': total_time,
                'user_breakdown': {
                    user: {
                        'active_minutes': data['active'],
                        'idle_minutes': data['idle'],
                        'sessions': data['sessions'],
                        'productivity_percent': int((data['active'] / (data['active'] + data['idle']) * 100)) if (data['active'] + data['idle']) > 0 else 0
                    }
                    for user, data in user_breakdown.items()
                }
            },
            'top_applications': top_apps,
            'session_details': session_details,
        })
    except Exception as e:
        logger.error(f"Error fetching accurate productivity: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_imp_bp.route('/api/v2/employee-activity/log', methods=['POST'])
@login_required
def log_employee_activity():
    """
    Log employee activity with app/window tracking for accurate productivity measurement.
    
    Expected JSON payload:
    {
        "server_id": 1,
        "user": "domain\\\\username",
        "app": "chrome.exe",
        "window_title": "Gmail - Compose",
        "idle_time": 120
    }
    """
    try:
        data = request.get_json(silent=True) or {}
        server_id = data.get('server_id')
        user = data.get('user') or 'Unknown'
        app = data.get('app')
        window_title = data.get('window_title')
        idle_time = data.get('idle_time', 0)

        if not server_id:
            return jsonify({'success': False, 'error': 'server_id required'}), 400

        server = Server.query.get(server_id)
        if not server:
            return jsonify({'success': False, 'error': 'Server not found'}), 404

        # Log activity
        activity = EmployeeActivity()
        activity.server_id = server_id
        activity.user = user
        activity.app = app
        activity.window_title = window_title
        activity.idle_time = idle_time
        activity.timestamp = datetime.utcnow()

        db.session.add(activity)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Activity logged for {user} on {server.hostname}',
            'activity_id': activity.id
        })
    except Exception as e:
        logger.error(f"Error logging employee activity: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@api_imp_bp.route('/api/v2/domain-discovery/poll', methods=['GET'])
@login_required
def poll_domain_discovery():
    """
    Real-time polling endpoint for domain discovery status.
    Returns discovered systems and their current status.
    
    Query params:
    - status: 'pending', 'imported', 'failed' (filter by status)
    - limit: number of results (default 50)
    """
    try:
        if not current_user.is_superadmin:
            return jsonify({'error': 'Only superadmins can access domain discovery'}), 403

        status_filter = request.args.get('status', '').strip().lower()
        limit = request.args.get('limit', 50, type=int)

        query = SystemDiscovery.query.filter_by(
            tenant_id=current_user.tenant_id
        )

        if status_filter in ['pending', 'imported', 'failed']:
            query = query.filter_by(status=status_filter)

        discoveries = query.order_by(
            SystemDiscovery.discovered_at.desc()
        ).limit(limit).all()

        # Check if any discovered systems are already imported
        discovered_hosts = {d.hostname.lower(): d for d in discoveries}
        imported_servers = Server.query.filter(
            Server.hostname.ilike('%' + '%'.lower() + '%')  # Check for partial matches
        ).all()

        data = []
        for disc in discoveries:
            # Check if this system has been imported
            is_imported = any(s.hostname.lower() == disc.hostname.lower() for s in imported_servers)
            
            data.append({
                'id': disc.id,
                'hostname': disc.hostname,
                'ip': disc.ip,
                'os_info': disc.os_info,
                'source': disc.source,
                'status': disc.status,
                'is_imported': is_imported,
                'discovered_at': disc.discovered_at.isoformat() if disc.discovered_at else None,
                'updated_at': disc.updated_at.isoformat() if disc.updated_at else None,
            })

        # Status summary
        all_discoveries = SystemDiscovery.query.filter_by(
            tenant_id=current_user.tenant_id
        ).all()
        
        summary = {
            'pending': sum(1 for d in all_discoveries if d.status == 'pending'),
            'imported': sum(1 for d in all_discoveries if d.status == 'imported'),
            'failed': sum(1 for d in all_discoveries if d.status == 'failed'),
            'total': len(all_discoveries)
        }

        return jsonify({
            'success': True,
            'discoveries': data,
            'summary': summary,
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"Error polling domain discovery: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_imp_bp.route('/api/v2/domain-discovery/<int:discovery_id>/import', methods=['POST'])
@login_required
def import_discovered_system(discovery_id):
    """
    Import a discovered system into the Server inventory.
    
    Returns the newly created Server record.
    """
    try:
        if not current_user.is_superadmin:
            return jsonify({'error': 'Only superadmins can import systems'}), 403

        discovery = SystemDiscovery.query.get_or_404(discovery_id)
        
        if discovery.tenant_id != current_user.tenant_id:
            return jsonify({'error': 'Unauthorized'}), 403

        # Check if already imported
        existing = Server.query.filter_by(hostname=discovery.hostname).first()
        if existing:
            return jsonify({
                'success': False,
                'error': f'System {discovery.hostname} already imported as Server ID {existing.id}'
            }), 400

        # Create new Server record
        server = Server()
        server.tenant_id = discovery.tenant_id
        server.hostname = discovery.hostname
        server.ip = discovery.ip
        server.os_info = discovery.os_info
        server.status = 'offline'
        server.is_online = False
        server.api_key = db.func.uuid()  # Generate new API key

        db.session.add(server)
        db.session.flush()

        # Update discovery status
        discovery.status = 'imported'
        discovery.updated_at = datetime.utcnow()

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'System {discovery.hostname} imported successfully',
            'server_id': server.id,
            'server': {
                'id': server.id,
                'hostname': server.hostname,
                'ip': server.ip,
                'os_info': server.os_info,
                'status': server.status
            }
        })
    except Exception as e:
        logger.error(f"Error importing discovered system: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@api_imp_bp.route('/api/v2/domain-discovery/<int:discovery_id>', methods=['DELETE'])
@login_required
def delete_discovered_system(discovery_id):
    """
    Delete/discard a discovered system record.
    """
    try:
        if not current_user.is_superadmin:
            return jsonify({'error': 'Only superadmins can manage domain discoveries'}), 403

        discovery = SystemDiscovery.query.get_or_404(discovery_id)
        
        if discovery.tenant_id != current_user.tenant_id:
            return jsonify({'error': 'Unauthorized'}), 403

        hostname = discovery.hostname
        db.session.delete(discovery)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Discovered system {hostname} deleted'
        })
    except Exception as e:
        logger.error(f"Error deleting discovered system: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@api_imp_bp.route('/api/v2/domain-discovery/<int:discovery_id>', methods=['PATCH'])
@login_required
def update_discovered_system(discovery_id):
    """
    Update discovered system status or notes.
    
    Expected JSON:
    {
        "status": "pending|imported|failed",
        "notes": "Optional notes"
    }
    """
    try:
        if not current_user.is_superadmin:
            return jsonify({'error': 'Only superadmins can manage domain discoveries'}), 403

        discovery = SystemDiscovery.query.get_or_404(discovery_id)
        
        if discovery.tenant_id != current_user.tenant_id:
            return jsonify({'error': 'Unauthorized'}), 403

        data = request.get_json(silent=True) or {}
        
        if 'status' in data:
            status = data['status'].lower()
            if status in ['pending', 'imported', 'failed']:
                discovery.status = status
        
        if 'notes' in data:
            discovery.notes = data.get('notes')

        discovery.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Discovered system {discovery.hostname} updated',
            'discovery': {
                'id': discovery.id,
                'hostname': discovery.hostname,
                'status': discovery.status,
                'updated_at': discovery.updated_at.isoformat()
            }
        })
    except Exception as e:
        logger.error(f"Error updating discovered system: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@api_imp_bp.route('/api/v2/domain-discovery/bulk-import', methods=['POST'])
@login_required
def bulk_import_discovered_systems():
    """
    Bulk import multiple discovered systems.
    
    Expected JSON:
    {
        "discovery_ids": [1, 2, 3, ...]
    }
    """
    try:
        if not current_user.is_superadmin:
            return jsonify({'error': 'Only superadmins can import systems'}), 403

        data = request.get_json(silent=True) or {}
        discovery_ids = data.get('discovery_ids', [])

        if not discovery_ids:
            return jsonify({'success': False, 'error': 'No discovery IDs provided'}), 400

        discoveries = SystemDiscovery.query.filter(
            SystemDiscovery.id.in_(discovery_ids),
            SystemDiscovery.tenant_id == current_user.tenant_id
        ).all()

        imported_count = 0
        skipped_count = 0
        errors = []

        for discovery in discoveries:
            # Check if already imported
            existing = Server.query.filter_by(hostname=discovery.hostname).first()
            if existing:
                skipped_count += 1
                errors.append(f"{discovery.hostname}: Already imported")
                continue

            try:
                server = Server()
                server.tenant_id = discovery.tenant_id
                server.hostname = discovery.hostname
                server.ip = discovery.ip
                server.os_info = discovery.os_info
                server.status = 'offline'
                server.is_online = False

                db.session.add(server)
                db.session.flush()

                discovery.status = 'imported'
                discovery.updated_at = datetime.utcnow()

                imported_count += 1
            except Exception as e:
                errors.append(f"{discovery.hostname}: {str(e)}")
                skipped_count += 1

        db.session.commit()

        return jsonify({
            'success': True,
            'imported_count': imported_count,
            'skipped_count': skipped_count,
            'errors': errors,
            'message': f'Imported {imported_count} systems, skipped {skipped_count}'
        })
    except Exception as e:
        logger.error(f"Error bulk importing systems: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
