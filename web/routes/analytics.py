"""
Admin Analytics API - Complete Overview of Active/Inactive Systems and Users
Provides comprehensive dashboard data for analysis
"""

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import func
import logging
import time
from flask import current_app

# Do not import `cache` from `web.app` at module import time (avoids circular import).
def _get_cache():
    """Lazily resolve the Flask-Caching extension for the current app (if available)."""
    try:
        app_cache = None
        if hasattr(current_app, 'extensions'):
            app_cache = current_app.extensions.get('cache')
        # Some setups attach the cache instance directly on the app
        if not app_cache and hasattr(current_app, 'cache'):
            app_cache = getattr(current_app, 'cache')
        return app_cache
    except Exception:
        return None

# Simple in-memory cache for analytics endpoints (per-process). Keyed by (tenant_id, endpoint, params)
_ANALYTICS_CACHE = {}
_DEFAULT_CACHE_TTL = int( (int(__import__('os').environ.get('ANALYTICS_CACHE_TTL_SECONDS', '60')) ))


def _cache_get(key):
    entry = _ANALYTICS_CACHE.get(key)
    if not entry:
        return None
    ts, ttl, value = entry
    if time.time() - ts > ttl:
        try:
            del _ANALYTICS_CACHE[key]
        except Exception:
            pass
        return None
    return value


def _cache_set(key, value, ttl=_DEFAULT_CACHE_TTL):
    _ANALYTICS_CACHE[key] = (time.time(), ttl, value)


logger = logging.getLogger("[ADMIN_ANALYTICS]")

analytics_bp = Blueprint('analytics', __name__, url_prefix='/api/v2/analytics')


@analytics_bp.route('/overview', methods=['GET'])
@login_required
def get_overview():
    """Get complete system overview - active/inactive breakdown"""
    if not current_user.is_superadmin:
        return jsonify({'error': 'Admin only'}), 403
    
    try:
        from web.models import db, AzureDevice, AzureUser, Server

        # Try cached response first
        cache_key = f"overview:{current_user.tenant_id if not current_user.is_superadmin else 'global'}"
        # Prefer Flask-Caching (Redis) if configured
        cache = _get_cache()
        if cache:
            try:
                cached = cache.get(cache_key)
            except Exception:
                cached = None
            if cached:
                return jsonify(cached)
        else:
            cached = _cache_get(cache_key)
            if cached:
                return jsonify(cached)
        
        # Device summary
        total_devices = db.session.query(AzureDevice).filter_by(
            tenant_id=current_user.tenant_id if not current_user.is_superadmin else None
        ).count()
        
        active_devices = db.session.query(AzureDevice).filter(
            AzureDevice.is_active == 1,
            AzureDevice.device_status == 'active'
        )
        if not current_user.is_superadmin and current_user.tenant_id:
            active_devices = active_devices.filter(AzureDevice.tenant_id == current_user.tenant_id)
        active_devices = active_devices.count()
        
        inactive_devices = db.session.query(AzureDevice).filter(
            AzureDevice.is_active == 0,
            AzureDevice.device_status == 'inactive'
        )
        if not current_user.is_superadmin and current_user.tenant_id:
            inactive_devices = inactive_devices.filter(AzureDevice.tenant_id == current_user.tenant_id)
        inactive_devices = inactive_devices.count()
        
        retired_devices = db.session.query(AzureDevice).filter(
            AzureDevice.device_status == 'retired'
        )
        if not current_user.is_superadmin and current_user.tenant_id:
            retired_devices = retired_devices.filter(AzureDevice.tenant_id == current_user.tenant_id)
        retired_devices = retired_devices.count()
        
        # User summary
        total_users = db.session.query(AzureUser).count()
        if not current_user.is_superadmin and current_user.tenant_id:
            total_users = db.session.query(AzureUser).filter(
                AzureUser.tenant_id == current_user.tenant_id
            ).count()
        
        active_users = db.session.query(AzureUser).filter(
            AzureUser.is_active == 1,
            AzureUser.employment_status == 'active'
        )
        if not current_user.is_superadmin and current_user.tenant_id:
            active_users = active_users.filter(AzureUser.tenant_id == current_user.tenant_id)
        active_users = active_users.count()
        
        terminated_users = db.session.query(AzureUser).filter(
            AzureUser.employment_status == 'terminated'
        )
        if not current_user.is_superadmin and current_user.tenant_id:
            terminated_users = terminated_users.filter(AzureUser.tenant_id == current_user.tenant_id)
        terminated_users = terminated_users.count()
        
        onleave_users = db.session.query(AzureUser).filter(
            AzureUser.employment_status == 'onleave'
        )
        if not current_user.is_superadmin and current_user.tenant_id:
            onleave_users = onleave_users.filter(AzureUser.tenant_id == current_user.tenant_id)
        onleave_users = onleave_users.count()
        
        # Server summary
        total_servers = db.session.query(Server).count()
        if not current_user.is_superadmin and current_user.tenant_id:
            total_servers = db.session.query(Server).filter(
                Server.tenant_id == current_user.tenant_id
            ).count()
        
        # Server.is_online is a property; check last_seen instead (within 60 seconds)
        threshold = datetime.utcnow() - timedelta(seconds=60)
        online_servers = db.session.query(Server).filter(
            Server.last_seen >= threshold
        )
        if not current_user.is_superadmin and current_user.tenant_id:
            online_servers = online_servers.filter(Server.tenant_id == current_user.tenant_id)
        online_servers = online_servers.count()
        
        payload = {
            'success': True,
            'timestamp': datetime.utcnow().isoformat(),
            'devices': {
                'total': total_devices,
                'active': active_devices,
                'inactive': inactive_devices,
                'retired': retired_devices,
                'active_percentage': round((active_devices / total_devices * 100) if total_devices > 0 else 0, 2)
            },
            'users': {
                'total': total_users,
                'active': active_users,
                'terminated': terminated_users,
                'onleave': onleave_users,
                'active_percentage': round((active_users / total_users * 100) if total_users > 0 else 0, 2)
            },
            'servers': {
                'total': total_servers,
                'online': online_servers,
                'offline': total_servers - online_servers
            }
        }

        # set cache
        if cache:
            try:
                cache.set(cache_key, payload)
            except Exception:
                pass
        else:
            _cache_set(cache_key, payload)

        return jsonify(payload)
    
    except Exception as e:
        logger.error(f"Error getting overview: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@analytics_bp.route('/devices/activity-timeline', methods=['GET'])
@login_required
def get_devices_activity_timeline():
    """Get timeline of device activity over last 90 days"""
    if not current_user.is_superadmin:
        return jsonify({'error': 'Admin only'}), 403
    
    try:
        from web.models import db, AzureDevice
        
        # Get 9 intervals over 90 days
        intervals = []
        end_date = datetime.utcnow()
        
        for i in range(9, -1, -1):
            start = end_date - timedelta(days=(i+1)*10)
            end = end_date - timedelta(days=i*10)
            
            query = db.session.query(func.count(AzureDevice.id)).filter(
                AzureDevice.last_activity >= start,
                AzureDevice.last_activity < end
            )
            
            if not current_user.is_superadmin and current_user.tenant_id:
                query = query.filter(AzureDevice.tenant_id == current_user.tenant_id)
            
            count = query.scalar() or 0
            intervals.append({
                'period': f"{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}",
                'active_devices': count
            })
        
        return jsonify({
            'success': True,
            'timeline': intervals
        })
    
    except Exception as e:
        logger.error(f"Error getting activity timeline: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@analytics_bp.route('/employees/device-mapping', methods=['GET'])
@login_required
def get_employees_device_mapping():
    """Get mapping of employees to their assigned devices"""
    if not current_user.is_superadmin:
        return jsonify({'error': 'Admin only'}), 403
    
    try:
        from web.models import db, AzureUser, AzureDevice, AzureDeviceOwner
        
        # Pagination params
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)

        # Cache key
        cache_key = f"employees_device_mapping:{current_user.tenant_id if not current_user.is_superadmin else 'global'}:{page}:{per_page}"
        cache = _get_cache()
        if cache:
            try:
                cached = cache.get(cache_key)
            except Exception:
                cached = None
            if cached:
                return jsonify(cached)
        else:
            cached = _cache_get(cache_key)
            if cached:
                return jsonify(cached)

        # Get active employees and their devices
        query = db.session.query(
            AzureUser.id,
            AzureUser.email,
            AzureUser.display_name,
            AzureUser.department,
            func.count(AzureDevice.id).label('device_count')
        ).outerjoin(
            AzureDeviceOwner, AzureUser.id == AzureDeviceOwner.user_id
        ).outerjoin(
            AzureDevice, AzureDeviceOwner.device_id == AzureDevice.id
        ).filter(
            AzureUser.is_active == 1,
            AzureUser.employment_status == 'active'
        ).group_by(AzureUser.id)
        
        if not current_user.is_superadmin and current_user.tenant_id:
            query = query.filter(AzureUser.tenant_id == current_user.tenant_id)
        
        total = query.count()
        results = query.order_by(func.count(AzureDevice.id).desc()).offset((page-1)*per_page).limit(per_page).all()

        employees = []
        for row in results:
            employees.append({
                'id': row[0],
                'email': row[1],
                'name': row[2],
                'department': row[3],
                'device_count': row[4] or 0
            })

        payload = {
            'success': True,
            'page': page,
            'per_page': per_page,
            'total': total,
            'employees': employees
        }

        if cache:
            try:
                cache.set(cache_key, payload)
            except Exception:
                pass
        else:
            _cache_set(cache_key, payload)

        return jsonify(payload)
    
    except Exception as e:
        logger.error(f"Error getting employees device mapping: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@analytics_bp.route('/employees/<int:employee_id>/devices', methods=['GET'])
@login_required
def get_employee_devices(employee_id):
    """Get devices assigned to a specific employee"""
    if not current_user.is_superadmin:
        return jsonify({'error': 'Admin only'}), 403
    
    try:
        from web.models import db, AzureUser, AzureDevice, AzureDeviceOwner
        
        employee = db.session.get(AzureUser, employee_id)
        if not employee:
            return jsonify({'success': False, 'error': 'Employee not found'}), 404
        
        # Get devices for this employee
        devices = db.session.query(AzureDevice).join(
            AzureDeviceOwner, AzureDevice.id == AzureDeviceOwner.device_id
        ).filter(
            AzureDeviceOwner.user_id == employee_id
        ).all()
        
        return jsonify({
            'success': True,
            'employee': {
                'id': employee.id,
                'email': employee.email,
                'name': employee.display_name,
                'department': employee.department
            },
            'devices': [{
                'id': d.id,
                'name': d.display_name,
                'type': d.device_type,
                'os': d.os_platform,
                'status': d.device_status,
                'last_activity': d.last_activity.isoformat() if d.last_activity else None,
                'is_compliant': d.is_compliant
            } for d in devices]
        })
    
    except Exception as e:
        logger.error(f"Error getting employee devices: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@analytics_bp.route('/inactivity-report', methods=['GET'])
@login_required
def get_inactivity_report():
    """Get report of inactive devices and users"""
    if not current_user.is_superadmin:
        return jsonify({'error': 'Admin only'}), 403
    
    try:
        from web.models import db, AzureDevice, AzureUser
        
        days_threshold = request.args.get('days', 90, type=int)
        threshold_date = datetime.utcnow() - timedelta(days=days_threshold)
        
        # Inactive devices
        inactive_devices = db.session.query(AzureDevice).filter(
            AzureDevice.last_activity < threshold_date,
            AzureDevice.is_active == 1
        ).order_by(AzureDevice.last_activity.desc()).limit(100).all()
        
        # Inactive users
        inactive_users = db.session.query(AzureUser).filter(
            AzureUser.last_activity < threshold_date,
            AzureUser.is_active == 1
        ).order_by(AzureUser.last_activity.desc()).limit(100).all()
        
        return jsonify({
            'success': True,
            'threshold_days': days_threshold,
            'threshold_date': threshold_date.isoformat(),
            'devices': {
                'count': len(inactive_devices),
                'items': [{
                    'id': d.id,
                    'name': d.display_name,
                    'last_activity': d.last_activity.isoformat() if d.last_activity else None,
                    'days_inactive': (datetime.utcnow() - d.last_activity.replace(tzinfo=None)).days if d.last_activity else None
                } for d in inactive_devices]
            },
            'users': {
                'count': len(inactive_users),
                'items': [{
                    'id': u.id,
                    'email': u.email,
                    'name': u.display_name,
                    'last_activity': u.last_activity.isoformat() if u.last_activity else None,
                    'days_inactive': (datetime.utcnow() - u.last_activity.replace(tzinfo=None)).days if u.last_activity else None
                } for u in inactive_users]
            }
        })
    
    except Exception as e:
        logger.error(f"Error getting inactivity report: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
