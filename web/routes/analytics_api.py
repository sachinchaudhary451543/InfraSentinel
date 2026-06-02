from flask import Blueprint, jsonify, request, render_template
import logging
from flask_login import login_required, current_user
from datetime import datetime, time

from web.models import db, ActivitySession, AppUsage, AttendanceRecord, Employee, EmployeeDeviceAssignment, EmployeeActivity, Server, Screenshot
from web.routes.api import _resolve_screenshot_local_path
from web.utils import require_role, get_allowed_employee_ids

analytics_api_bp = Blueprint('analytics_api', __name__)
logger = logging.getLogger(__name__)


@analytics_api_bp.route('/workforce')
@login_required
def workforce_dashboard():
    """Workforce Intelligence Dashboard page."""
    tenant_id = current_user.tenant_id

    import pytz
    ist = pytz.timezone('Asia/Kolkata')

    def _hms(seconds):
        seconds = int(seconds or 0)
        return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"

    def _last_seen_label(dt):
        if not dt:
            return None
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        return dt.astimezone(ist).strftime('%d %b %Y, %I:%M %p')

    def _screenshot_thumb(shot):
        if not shot:
            return None, False
        local_path = _resolve_screenshot_local_path(shot)
        if local_path or shot.sharepoint_url:
            return f"/api/screenshot/{shot.id}?size=thumb", True
        return None, False

    # Gather summary data for the template using India/local business day.
    today = datetime.now(ist).date()
    
    # Employee count
    employees = Employee.query.filter_by(tenant_id=tenant_id, is_active=True, employment_status='active').all()
    
    # Active assignments (correlated devices)
    assignments = EmployeeDeviceAssignment.query.filter_by(tenant_id=tenant_id, is_active=True).all()
    
    # Today's attendance
    attendance = AttendanceRecord.query.filter_by(tenant_id=tenant_id, date=today).all()
    
    # Today's sessions
    day_start = ist.localize(datetime.combine(today, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
    day_end = ist.localize(datetime.combine(today, time.max)).astimezone(pytz.UTC).replace(tzinfo=None)
    sessions = ActivitySession.query.filter(
        ActivitySession.tenant_id == tenant_id,
        ActivitySession.start_time >= day_start,
        ActivitySession.start_time <= day_end
    ).all()
    
    # Note: We use the integer '*_minutes' columns to store SECONDS for higher precision without schema changes.
    total_active = sum(s.active_minutes or 0 for s in sessions)
    total_idle = sum(s.idle_minutes or 0 for s in sessions)
    total_productive = sum(s.productive_minutes or 0 for s in sessions)
    
    # Format totals as HH:MM:SS (since they are stored as seconds)
    total_active_str = _hms(total_active)
    total_idle_str = _hms(total_idle)
    total_productive_str = _hms(total_productive)
    
    # Build employee detail rows for the table
    emp_rows = []
    for emp in employees:
        att = next((a for a in attendance if a.employee_id == emp.id), None)
        emp_sessions = [s for s in sessions if s.employee_id == emp.id]
        active_sec = sum(s.active_minutes or 0 for s in emp_sessions)
        idle_sec = sum(s.idle_minutes or 0 for s in emp_sessions)
        prod_sec = sum(s.productive_minutes or 0 for s in emp_sessions)
        assignment = next((a for a in assignments if a.employee_id == emp.id), None)
        device_name = ''
        device_ip = ''
        screenshot_enabled = False
        server_status = 'offline'
        last_seen = None
        screenshot_thumb = None
        screenshot_available = False
        screenshot_enabled = False
        server_status = 'offline'
        last_seen = None
        if assignment and assignment.server_id:
            srv = db.session.get(Server, assignment.server_id)
            if srv:
                device_name = srv.hostname or srv.name or ''
                device_ip = srv.ip or ''
                screenshot_enabled = bool(srv.screenshot_enabled)
                server_status = srv.status_label
                last_seen = srv.last_seen

                latest_ss = Screenshot.query.filter_by(server_id=srv.id).order_by(Screenshot.captured_at.desc()).first()
                screenshot_thumb, screenshot_available = _screenshot_thumb(latest_ss)

        first_act_str = '—'
        last_act_str = '—'
        if att:
            if att.first_activity:
                first_act_str = att.first_activity.replace(tzinfo=pytz.UTC).astimezone(ist).strftime('%I:%M %p')
            if att.last_activity:
                last_act_str = att.last_activity.replace(tzinfo=pytz.UTC).astimezone(ist).strftime('%I:%M %p')
        
        emp_rows.append({
            'id': emp.id,
            'name': emp.display_name or emp.name or emp.email or emp.local_username or 'Unknown',
            'email': emp.email or '',
            'department': emp.department or '',
            'device': device_name,
            'device_ip': device_ip,
            'server_id': assignment.server_id if assignment and assignment.server_id else None,
            'server_name': device_name,
            'screenshot_enabled': screenshot_enabled,
            'screenshot_available': screenshot_available,
            'screenshot_thumb': screenshot_thumb,
            'server_status': server_status,
            'server_last_seen': _last_seen_label(last_seen),
            'status': att.status if att else 'absent',
            'first_activity': first_act_str,
            'last_activity': last_act_str,
            'active_str': _hms(active_sec),
            'idle_str': _hms(idle_sec),
            'productive_str': _hms(prod_sec),
        })

    # Focus: only agent-installed systems and the employees linked to them
    # Servers with agent installed for this tenant
    servers = Server.query.filter_by(tenant_id=tenant_id, agent_installed=True).all()

    # Active assignments (correlated devices) - used to map servers -> employees
    # (we already fetched assignments earlier; reuse them)

    # Active assignments correlate servers to employees

    live_agents = []
    for srv in servers:
        # find linked employee for this server if any
        assignment = next((a for a in assignments if a.server_id == srv.id), None)
        emp = db.session.get(Employee, assignment.employee_id) if assignment and assignment.employee_id else None
        latest_ss = Screenshot.query.filter_by(server_id=srv.id).order_by(Screenshot.captured_at.desc()).first()
        screenshot_thumb, screenshot_available = _screenshot_thumb(latest_ss)
        latest_activity = EmployeeActivity.query.filter_by(server_id=srv.id).order_by(EmployeeActivity.timestamp.desc()).first()
        emp_sessions = [s for s in sessions if emp and s.employee_id == emp.id]
        active_sec = sum(s.active_minutes or 0 for s in emp_sessions)
        idle_sec = sum(s.idle_minutes or 0 for s in emp_sessions)
        prod_sec = sum(s.productive_minutes or 0 for s in emp_sessions)
        if not emp_sessions and latest_activity and latest_activity.timestamp >= day_start and latest_activity.timestamp <= day_end:
            idle_sec = int(latest_activity.idle_time or 0)

        live_agents.append({
            'id': emp.id if emp else None,
            'name': (
                emp.display_name if emp and getattr(emp, 'display_name', None)
                else latest_activity.user if latest_activity and latest_activity.user
                else (srv.hostname or srv.name or 'Unknown')
            ),
            'email': emp.email if emp else '',
            'department': emp.department if emp else '',
            'device': srv.hostname or srv.name or '',
            'device_ip': srv.ip or '',
            'server_id': srv.id,
            'server_name': srv.hostname or srv.name or '',
            'screenshot_enabled': bool(srv.screenshot_enabled),
            'screenshot_available': screenshot_available,
            'screenshot_thumb': screenshot_thumb,
            'server_status': srv.status_label,
            'server_last_seen': _last_seen_label(srv.last_seen),
            'active_str': _hms(active_sec),
            'idle_str': _hms(idle_sec),
            'productive_str': _hms(prod_sec),
            'current_app': latest_activity.app if latest_activity and latest_activity.app else '',
            'current_window': latest_activity.window_title if latest_activity and latest_activity.window_title else '',
        })

    # Debug: log counts to help diagnose missing live agent cards in UI
    try:
        logger.info(f"Workforce: tenant={tenant_id} employees={len(employees)} assignments={len(assignments)} emp_rows={len(emp_rows)} live_agents={len(live_agents)}")
        # log sample of first few linked agents
        sample = [r for r in emp_rows if r.get('server_id')][:10]
        if sample:
            logger.info(f"Workforce sample linked agents: {[(r['id'], r['server_id']) for r in sample]}")
    except Exception:
        pass

    # Top-level agent metrics
    total_agents = len(servers)
    active_agents = sum(1 for s in servers if getattr(s, 'status_label', '').upper() == 'ONLINE')
    idle_agents = sum(1 for s in servers if getattr(s, 'status_label', '').upper() == 'IDLE')
    offline_agents = total_agents - active_agents - idle_agents
    screenshot_enabled_count = sum(1 for s in servers if bool(s.screenshot_enabled))
    active_screens = sum(1 for a in live_agents if a.get('screenshot_available') and (a.get('server_status') or '').upper() == 'ONLINE')

    return render_template(
        'workforce_dashboard.html',
        employees=emp_rows,
        live_agents=live_agents,
        total_employees=len(employees),
        total_assignments=len(assignments),
        attendance_count=len(attendance),
        total_active_str=total_active_str,
        total_idle_str=total_idle_str,
        total_productive_str=total_productive_str,
        today=today.isoformat(),
        total_agents=total_agents,
        active_agents=active_agents,
        idle_agents=idle_agents,
        offline_agents=offline_agents,
        screenshot_enabled_count=screenshot_enabled_count,
        active_screens=active_screens,
    )

@analytics_api_bp.route('/api/v2/workforce/timeline', methods=['GET'])
@login_required
@require_role('super_admin', 'org_admin', 'manager')
def get_timeline():
    """
    Returns chronological timeline of ActivitySessions and AppUsage for specific employees.
    """
    tenant_id = current_user.tenant_id
    allowed_ids = get_allowed_employee_ids(current_user)
    
    # Query parameters
    employee_id = request.args.get('employee_id', type=int)
    date_str = request.args.get('date') # YYYY-MM-DD
    
    if not date_str:
        target_date = datetime.utcnow().date()
    else:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400
            
    # RBAC Enforcement
    if employee_id:
        if allowed_ids is not None and employee_id not in allowed_ids:
            return jsonify({'success': False, 'error': 'Unauthorized to view this employee'}), 403
        target_employees = [employee_id]
    else:
        if allowed_ids is None:
            # All employees in tenant
            target_employees = [e.id for e in Employee.query.filter_by(tenant_id=tenant_id, is_active=True, employment_status='active').all()]
        else:
            target_employees = allowed_ids
            
    if not target_employees:
        return jsonify({'success': True, 'timeline': []})
        
    start_time = datetime.combine(target_date, datetime.min.time())
    end_time = datetime.combine(target_date, datetime.max.time())
    
    sessions = ActivitySession.query.filter(
        ActivitySession.tenant_id == tenant_id,
        ActivitySession.employee_id.in_(target_employees),
        ActivitySession.start_time >= start_time,
        ActivitySession.start_time <= end_time
    ).all()
    
    timeline_data = []
    for session in sessions:
        # Get apps for this session
        apps = AppUsage.query.filter_by(session_id=session.id).all()
        
        timeline_data.append({
            'session_id': session.id,
            'employee_id': session.employee_id,
            'start_time': session.start_time.isoformat(),
            'end_time': session.end_time.isoformat() if session.end_time else None,
            'active_minutes': session.active_minutes,
            'idle_minutes': session.idle_minutes,
            'productive_minutes': session.productive_minutes,
            'apps': [{
                'app_name': app.app_name,
                'window_title': app.window_title,
                'start_time': app.start_time.isoformat(),
                'duration_seconds': app.duration_seconds,
                'classification': app.classification
            } for app in apps]
        })
        
    return jsonify({
        'success': True,
        'date': target_date.isoformat(),
        'timeline': timeline_data
    })


@analytics_api_bp.route('/api/v2/workforce/attendance', methods=['GET'])
@login_required
@require_role('super_admin', 'org_admin', 'manager')
def get_attendance():
    """
    Returns daily attendance records for the tenant, filtered by RBAC.
    """
    tenant_id = current_user.tenant_id
    allowed_ids = get_allowed_employee_ids(current_user)
    
    date_str = request.args.get('date') # YYYY-MM-DD
    
    if not date_str:
        target_date = datetime.utcnow().date()
    else:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400
            
    query = AttendanceRecord.query.filter_by(
        tenant_id=tenant_id,
        date=target_date
    )
    
    if allowed_ids is not None:
        query = query.filter(AttendanceRecord.employee_id.in_(allowed_ids))
        
    records = query.all()
    
    attendance_data = []
    for record in records:
        attendance_data.append({
            'employee_id': record.employee_id,
            'date': record.date.isoformat(),
            'first_activity': record.first_activity.isoformat() if record.first_activity else None,
            'last_activity': record.last_activity.isoformat() if record.last_activity else None,
            'total_active_minutes': record.total_active_minutes,
            'total_idle_minutes': record.total_idle_minutes,
            'status': record.status
        })
        
    return jsonify({
        'success': True,
        'date': target_date.isoformat(),
        'attendance': attendance_data
    })
