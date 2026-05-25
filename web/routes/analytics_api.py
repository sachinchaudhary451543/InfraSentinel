from flask import Blueprint, jsonify, request, g, render_template
from flask_login import login_required, current_user
from datetime import datetime, timedelta

from web.models import db, ActivitySession, AppUsage, AttendanceRecord, Employee, EmployeeDeviceAssignment, Server, AzureDevice
from web.utils import require_role, get_allowed_employee_ids

analytics_api_bp = Blueprint('analytics_api', __name__)


@analytics_api_bp.route('/workforce')
@login_required
def workforce_dashboard():
    """Workforce Intelligence Dashboard page."""
    tenant_id = current_user.tenant_id
    
    # Gather summary data for the template
    today = datetime.utcnow().date()
    
    # Employee count
    employees = Employee.query.filter_by(tenant_id=tenant_id, is_active=True).all()
    
    # Active assignments (correlated devices)
    assignments = EmployeeDeviceAssignment.query.filter_by(tenant_id=tenant_id, is_active=True).all()
    
    # Today's attendance
    attendance = AttendanceRecord.query.filter_by(tenant_id=tenant_id, date=today).all()
    
    # Today's sessions
    day_start = datetime.combine(today, datetime.min.time())
    day_end = datetime.combine(today, datetime.max.time())
    sessions = ActivitySession.query.filter(
        ActivitySession.tenant_id == tenant_id,
        ActivitySession.start_time >= day_start,
        ActivitySession.start_time <= day_end
    ).all()
    
    total_active = sum(s.active_minutes or 0 for s in sessions)
    total_idle = sum(s.idle_minutes or 0 for s in sessions)
    total_productive = sum(s.productive_minutes or 0 for s in sessions)
    
    # Format totals as HH:MM:SS
    total_active_str = f"{total_active // 3600:02d}:{(total_active % 3600) // 60:02d}:{total_active % 60:02d}"
    total_idle_str = f"{total_idle // 3600:02d}:{(total_idle % 3600) // 60:02d}:{total_idle % 60:02d}"
    total_productive_str = f"{total_productive // 3600:02d}:{(total_productive % 3600) // 60:02d}:{total_productive % 60:02d}"
    
    import pytz
    ist = pytz.timezone('Asia/Kolkata')
    
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
        if assignment and assignment.server_id:
            srv = db.session.get(Server, assignment.server_id)
            device_name = srv.hostname if srv else ''
            device_ip = srv.ip if srv else ''
        
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
            'status': att.status if att else 'absent',
            'first_activity': first_act_str,
            'last_activity': last_act_str,
            'active_str': f"{active_sec // 3600:02d}:{(active_sec % 3600) // 60:02d}:{active_sec % 60:02d}",
            'idle_str': f"{idle_sec // 3600:02d}:{(idle_sec % 3600) // 60:02d}:{idle_sec % 60:02d}",
            'productive_str': f"{prod_sec // 3600:02d}:{(prod_sec % 3600) // 60:02d}:{prod_sec % 60:02d}",
        })
    
    return render_template(
        'workforce_dashboard.html',
        employees=emp_rows,
        total_employees=len(employees),
        total_assignments=len(assignments),
        attendance_count=len(attendance),
        total_active_str=total_active_str,
        total_idle_str=total_idle_str,
        total_productive_str=total_productive_str,
        today=today.isoformat()
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
            target_employees = [e.id for e in Employee.query.filter_by(tenant_id=tenant_id).all()]
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
    ).order_by(ActivitySession.start_time.asc()).all()
    
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
