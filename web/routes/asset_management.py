"""
Asset Management and Remote System Control Routes
Employees, Devices, Login/Logout tracking, Software Deployment, and Remote Access
"""

import logging
from datetime import datetime
from flask import Blueprint, render_template, jsonify, request, redirect, url_for, abort, flash, make_response
from flask_login import login_required, current_user
from web.utils import require_tenant_access

import csv
import io

from web.active_agents_monitor import ActiveAgentsMonitor
from web.models import (
    db, Server, Metric, EmployeeAssetLog, DeviceActivity, EmployeeDeviceAssignment,
    SystemAlert, AuditLog, RemoteCommand, Tenant,
    AzureUser, AzureDevice, AzureDeviceOwner, Screenshot, Employee
)

logger = logging.getLogger("[ASSET_MGMT]")

asset_mgmt_bp = Blueprint('asset_mgmt', __name__)


def _seconds_to_hms(value):
    """Productivity columns currently store seconds despite legacy *_minutes names."""
    seconds = int(value or 0)
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def _compact_identity(value):
    return (value or '').lower().replace('.', '').replace('_', '').replace('-', '')


def _build_employee_device_maps(tenant_id, day_start, day_end):
    """Build caches to resolve employees to servers and Azure devices."""
    assignments = EmployeeDeviceAssignment.query.filter_by(tenant_id=tenant_id, is_active=True).all()
    servers = Server.query.filter_by(tenant_id=tenant_id).all()
    server_map = {s.id: s for s in servers}
    server_ids = [s.id for s in servers]

    azure_devices = AzureDevice.query.filter_by(tenant_id=tenant_id).all()
    azure_device_map = {d.id: d for d in azure_devices}

    azure_users = AzureUser.query.filter_by(tenant_id=tenant_id).all()
    azure_users_by_email = {u.email.lower(): u for u in azure_users if u.email}
    azure_users_by_employee_id = {u.employee_id.lower(): u for u in azure_users if u.employee_id}
    azure_users_by_mail_nickname = {u.mail_nickname.lower(): u for u in azure_users if u.mail_nickname}
    azure_users_by_sam = {u.sam_account_name.lower(): u for u in azure_users if u.sam_account_name}

    azure_owners = AzureDeviceOwner.query.filter_by(tenant_id=tenant_id).all()
    owners_by_user_id = {}
    for owner in azure_owners:
        owners_by_user_id.setdefault(owner.user_id, []).append(owner)

    latest_screenshot_by_server = {}
    if server_ids:
        screenshots = Screenshot.query.filter(Screenshot.server_id.in_(server_ids)).order_by(Screenshot.server_id.asc(), Screenshot.captured_at.desc()).all()
        for screenshot in screenshots:
            if screenshot.server_id not in latest_screenshot_by_server:
                latest_screenshot_by_server[screenshot.server_id] = screenshot.id

    assignment_by_emp = {a.employee_id: a for a in assignments}

    activity_rows = DeviceActivity.query.filter(
        DeviceActivity.server_id.in_(server_ids),
        DeviceActivity.login_time >= day_start,
        DeviceActivity.login_time <= day_end
    ).order_by(DeviceActivity.login_time.desc()).all() if server_ids else []

    latest_activity_by_user = {}
    for act in activity_rows:
        user_key = (act.session_user or '').strip().lower()
        if user_key and user_key not in latest_activity_by_user:
            latest_activity_by_user[user_key] = act

    asset_logs = EmployeeAssetLog.query.filter_by(tenant_id=tenant_id).order_by(EmployeeAssetLog.login_timestamp.desc()).all()
    latest_log_by_email = {}
    for log in asset_logs:
        if log.employee_email:
            key = log.employee_email.lower()
            if key not in latest_log_by_email:
                latest_log_by_email[key] = log

    return {
        'server_map': server_map,
        'azure_device_map': azure_device_map,
        'azure_users_by_email': azure_users_by_email,
        'azure_users_by_employee_id': azure_users_by_employee_id,
        'azure_users_by_mail_nickname': azure_users_by_mail_nickname,
        'azure_users_by_sam': azure_users_by_sam,
        'owners_by_user_id': owners_by_user_id,
        'assignment_by_emp': assignment_by_emp,
        'latest_activity_by_user': latest_activity_by_user,
        'latest_log_by_email': latest_log_by_email,
        'latest_screenshot_by_server': latest_screenshot_by_server,
    }


def _resolve_employee_device(tenant_id, emp, day_start, day_end, device_maps):
    """Try to resolve a device for an employee using assignment, Azure, activity, and asset logs."""
    server = None
    azure_device = None
    source = 'unassigned'

    assignment = device_maps['assignment_by_emp'].get(emp.id)
    if assignment:
        if assignment.server_id:
            server = device_maps['server_map'].get(assignment.server_id)
            source = 'assignment'
        elif assignment.azure_device_id:
            azure_device = device_maps['azure_device_map'].get(assignment.azure_device_id)
            source = 'assignment'

    if not server and not azure_device:
        local_username = (emp.local_username or '').strip().lower()
        username_candidates = [local_username]
        if emp.email:
            username_candidates.append(emp.email.split('@', 1)[0].lower())

        for username in username_candidates:
            if not username:
                continue
            activity = device_maps['latest_activity_by_user'].get(username)
            if activity:
                server = device_maps['server_map'].get(activity.server_id)
                source = 'device_activity'
                break

    if not server and not azure_device and emp.email:
        log = device_maps['latest_log_by_email'].get(emp.email.lower())
        if log:
            server = device_maps['server_map'].get(log.server_id)
            source = 'employee_asset_log'
            if not server:
                return {
                    'name': log.hostname,
                    'ip': log.ip_address or '',
                    'status': 'present',
                    'source': source,
                    'status_text': 'Present'
                }

    if not server and not azure_device:
        azure_user = None
        if emp.email:
            azure_user = device_maps['azure_users_by_email'].get(emp.email.lower())
        if not azure_user and emp.local_username:
            azure_user = device_maps['azure_users_by_employee_id'].get(emp.local_username.lower())
        if not azure_user and emp.local_username:
            azure_user = device_maps['azure_users_by_mail_nickname'].get(emp.local_username.lower())
        if not azure_user and emp.local_username:
            azure_user = device_maps['azure_users_by_sam'].get(emp.local_username.lower())

        if azure_user:
            owners = device_maps['owners_by_user_id'].get(azure_user.id, [])
            if owners:
                owner = owners[0]
                azure_device = device_maps['azure_device_map'].get(owner.device_id)
                source = 'azure_mapping'

    if server:
        return {
            'name': server.hostname,
            'ip': server.ip or '',
            'server_id': server.id,
            'status': 'present' if getattr(server, 'is_online', False) else 'absent',
            'source': source,
            'status_text': 'Present' if getattr(server, 'is_online', False) else 'Absent'
        }

    if azure_device:
        return {
            'name': azure_device.display_name,
            'ip': '',
            'status': 'present' if azure_device.is_active == 1 else 'absent',
            'source': source,
            'status_text': 'Present' if azure_device.is_active == 1 else 'Absent'
        }

    return {
        'name': '',
        'ip': '',
        'status': 'absent',
        'source': source,
        'status_text': 'Absent'
    }


def _find_employee_for_server(server, tenant_id):
    """Resolve the employee linked to a server via assignment or Azure device mapping."""
    if not server:
        return None

    assignment = EmployeeDeviceAssignment.query.filter_by(
        tenant_id=tenant_id,
        server_id=server.id,
        is_active=True
    ).first()
    if assignment and assignment.employee_id:
        return Employee.query.get(assignment.employee_id)

    azure_device = AzureDevice.query.filter_by(
        tenant_id=tenant_id,
        display_name=server.hostname
    ).first()
    if not azure_device:
        return None

    owner = AzureDeviceOwner.query.filter_by(
        tenant_id=tenant_id,
        device_id=azure_device.id
    ).first()
    if not owner:
        return None

    # owner.user_id stores the AzureUser DB primary key (integer). Use that to fetch the AzureUser.
    try:
        azure_user = AzureUser.query.filter_by(
            tenant_id=tenant_id,
            id=int(owner.user_id)
        ).first()
    except Exception:
        # In case owner.user_id is unexpectedly not an integer, avoid raising a server error and bail out.
        return None
    if not azure_user:
        return None

    if azure_user.email:
        emp = Employee.query.filter_by(tenant_id=tenant_id, email=azure_user.email).first()
        if emp:
            return emp

    if azure_user.employee_id:
        emp = Employee.query.filter_by(tenant_id=tenant_id, local_username=azure_user.employee_id).first()
        if emp:
            return emp

    if azure_user.sam_account_name:
        emp = Employee.query.filter_by(tenant_id=tenant_id, local_username=azure_user.sam_account_name).first()
        if emp:
            return emp

    return None


def _build_productivity_rows(tenant_id, target_date):
    from web.models import ActivitySession, AttendanceRecord

    employees = Employee.query.filter_by(tenant_id=tenant_id, is_active=True).all()
    attendance = AttendanceRecord.query.filter_by(tenant_id=tenant_id, date=target_date).all()
    day_start = datetime.combine(target_date, datetime.min.time())
    day_end = datetime.combine(target_date, datetime.max.time())
    sessions = ActivitySession.query.filter(
        ActivitySession.tenant_id == tenant_id,
        ActivitySession.start_time >= day_start,
        ActivitySession.start_time <= day_end
    ).all()

    device_maps = _build_employee_device_maps(tenant_id, day_start, day_end)
    emp_rows = []

    for emp in employees:
        att = next((a for a in attendance if a.employee_id == emp.id), None)
        emp_sessions = [s for s in sessions if s.employee_id == emp.id]
        
        # Only skip employees when there is no session, no attendance, and no assigned or mapped device.
        device_info = _resolve_employee_device(tenant_id, emp, day_start, day_end, device_maps)
        if not emp_sessions and not att and not device_info.get('name'):
            continue
        
        active_sec = sum(s.active_minutes or 0 for s in emp_sessions)
        idle_sec = sum(s.idle_minutes or 0 for s in emp_sessions)
        prod_sec = sum(s.productive_minutes or 0 for s in emp_sessions)

        import pytz
        ist = pytz.timezone('Asia/Kolkata')
        first_act_str = '—'
        last_act_str = '—'
        if att:
            if att.first_activity:
                first_act_str = att.first_activity.replace(tzinfo=pytz.UTC).astimezone(ist).strftime('%I:%M %p')
            if att.last_activity:
                last_act_str = att.last_activity.replace(tzinfo=pytz.UTC).astimezone(ist).strftime('%I:%M %p')
        elif emp_sessions:
            first_session = min(emp_sessions, key=lambda s: s.start_time or datetime.max)
            last_session = max(emp_sessions, key=lambda s: s.end_time or (s.start_time or datetime.min))
            if first_session and first_session.start_time:
                first_act_str = first_session.start_time.strftime('%I:%M %p')
            if last_session and last_session.end_time:
                last_act_str = last_session.end_time.strftime('%I:%M %p')
            elif last_session and last_session.start_time:
                last_act_str = last_session.start_time.strftime('%I:%M %p')

        # FIX: Status should be based on actual activity, not just device_info
        row_status = 'absent'
        
        # If there are activity sessions, mark as present
        if emp_sessions:
            row_status = 'present'
        # Otherwise use attendance record status if available
        elif att and att.status:
            row_status = att.status
        # Finally check device status as fallback
        elif device_info.get('status') == 'present':
            row_status = 'present'

        emp_rows.append({
            'id': emp.id,
            'name': emp.display_name or emp.name or emp.email or emp.local_username or 'Unknown',
            'email': emp.email or '',
            'department': emp.department or '',
            'device': device_info.get('name', ''),
            'device_ip': device_info.get('ip', ''),
            'server_id': device_info.get('server_id'),
            'screenshot_id': device_maps['latest_screenshot_by_server'].get(device_info.get('server_id')),
            'status': row_status,
            'first_activity': first_act_str,
            'last_activity': last_act_str,
            'active_sec': active_sec,
            'active_str': _seconds_to_hms(active_sec),
            'idle_str': _seconds_to_hms(idle_sec),
            'productive_str': _seconds_to_hms(prod_sec),
            'source': device_info.get('source', 'unassigned')
        })

    emp_rows.sort(key=lambda x: x['active_sec'], reverse=True)
    return emp_rows


@asset_mgmt_bp.route('/assets/employees')
@login_required
def list_employees_assets():
    """Asset Management UI Shell (Data loaded via Infinite Scroll JSON API)"""
    try:
        tenant = Tenant.query.get(current_user.tenant_id)
        if not tenant:
            return render_template('asset_management.html', error='Tenant not configured')

        # Fast aggregate stats for quick loading
        total_manual = Employee.query.filter_by(tenant_id=current_user.tenant_id).count()
        total_azure = AzureUser.query.filter_by(tenant_id=current_user.tenant_id).count()
        total_employees = total_manual + total_azure
        
        total_assets = EmployeeAssetLog.query.filter_by(tenant_id=current_user.tenant_id).count()
        
        employees = Employee.query.filter_by(tenant_id=current_user.tenant_id).all()
        
        return render_template(
            'asset_management.html',
            total_employees=total_employees,
            total_assets=total_assets,
            employees=employees
        )
    except Exception as e:
        logger.error(f"Error loading asset UI: {e}")
        return render_template('asset_management.html', error=str(e), employees=[])

@asset_mgmt_bp.route('/api/v2/assets/live_activity')
@login_required
def get_live_activity():
    """Returns a JSON list of recent device activities for the tenant."""
    try:
        tenant_id = current_user.tenant_id
        
        # Get servers for this tenant
        servers = Server.query.filter_by(tenant_id=tenant_id).all()
        server_ids = [s.id for s in servers]
        server_map = {s.id: s.hostname for s in servers}
        
        if not server_ids:
            return jsonify({'success': True, 'data': []})
            
        activities = DeviceActivity.query.filter(
            DeviceActivity.server_id.in_(server_ids)
        ).order_by(DeviceActivity.reported_at.desc()).limit(100).all()
        
        data = []
        for a in activities:
            data.append({
                'id': a.id,
                'hostname': server_map.get(a.server_id, 'Unknown'),
                'session_user': a.session_user,
                'login_time': a.login_time.isoformat() + ('Z' if a.login_time.tzinfo is None else '') if a.login_time else None,
                'logout_time': a.logout_time.isoformat() + ('Z' if a.logout_time.tzinfo is None else '') if a.logout_time else None,
                'idle_minutes': a.idle_minutes,
                'active_minutes': a.active_minutes,
                'session_type': a.session_type,
                'reported_at': a.reported_at.isoformat() + ('Z' if a.reported_at.tzinfo is None else '') if a.reported_at else None
            })
            
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        logger.error(f"Error fetching live activity: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500



@asset_mgmt_bp.route('/api/v2/assets/employees_scroll')
@login_required
def get_employees_scroll():
    """Returns a JSON page of employees and their assets with infinite scroll."""
    try:
        q = request.args.get('q', '').strip().lower()
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        statusFilter = request.args.get('status', '').strip().lower()
        sourceFilter = request.args.get('source', '').strip().lower()
        
        tenant_id = current_user.tenant_id
        
        # 1. Gather users from Manual Employee table (Priority)
        manual_employees = Employee.query.filter_by(tenant_id=tenant_id)
        if q:
            manual_employees = manual_employees.filter(db.or_(
                Employee.name.ilike(f'%{q}%'),
                Employee.email.ilike(f'%{q}%'),
                Employee.local_username.ilike(f'%{q}%')
            ))
        manual_list = manual_employees.all()

        employee_dict = {}
        for me in manual_list:
            email = me.email.lower()
            employee_dict[email] = {
                'id': me.id,
                'email': me.email,
                'name': me.name,
                'title': me.designation or 'N/A',
                'department': me.department or 'N/A',
                'user_id': None,
                'local_username': me.local_username,
                'source': 'Manual',
                'assets': []
            }

        # 2. Gather users from AzureUser (Fallback)
        query = AzureUser.query.filter_by(tenant_id=tenant_id)
        if q:
            query = query.filter(db.or_(
                AzureUser.display_name.ilike(f'%{q}%'),
                AzureUser.email.ilike(f'%{q}%')
            ))
            
        azure_users = query.all()
        manual_by_azure_id = {
            (getattr(me, 'azure_user_id', None) or '').lower(): (me.email or '').lower()
            for me in manual_list
            if getattr(me, 'azure_user_id', None) and me.email
        }
        manual_by_local = {
            _compact_identity(getattr(me, 'local_username', None)): (me.email or '').lower()
            for me in manual_list
            if getattr(me, 'local_username', None) and me.email
        }
        for au in azure_users:
            email = (au.email or '').lower()
            local_keys = {
                _compact_identity(au.employee_id),
                _compact_identity(au.mail_nickname),
                _compact_identity(email.split('@', 1)[0] if email else ''),
            }
            merge_email = (
                email if email in employee_dict else
                manual_by_azure_id.get((au.user_id or '').lower()) or
                next((manual_by_local[k] for k in local_keys if k in manual_by_local), None)
            )

            if email and not merge_email:
                merge_email = email

            if merge_email and merge_email not in employee_dict:
                employee_dict[merge_email] = {
                    'email': au.email,
                    'name': au.display_name or 'Unknown',
                    'title': au.job_title or 'N/A',
                    'department': au.department or 'N/A',
                    'user_id': au.user_id,
                    'azure_db_id': au.id,
                    'source': 'Azure',
                    'assets': []
                }
            elif merge_email:
                employee_dict[merge_email]['user_id'] = au.user_id
                employee_dict[merge_email]['azure_db_id'] = au.id
                employee_dict[merge_email]['email'] = au.email or employee_dict[merge_email].get('email')
                employee_dict[merge_email]['name'] = au.display_name or employee_dict[merge_email].get('name') or 'Unknown'
                employee_dict[merge_email]['title'] = au.job_title or employee_dict[merge_email].get('title') or 'N/A'
                employee_dict[merge_email]['department'] = au.department or employee_dict[merge_email].get('department') or 'N/A'
                
        # 2. Fetch latest asset log per (employee_email, hostname) in one grouped query
        log_query = db.session.query(
            EmployeeAssetLog.employee_email.label('employee_email'),
            EmployeeAssetLog.hostname.label('hostname'),
            db.func.max(EmployeeAssetLog.id).label('latest_id')
        ).filter(EmployeeAssetLog.tenant_id == tenant_id)
        if q:
            log_query = log_query.filter(db.or_(
                EmployeeAssetLog.employee_email.ilike(f'%{q}%'),
                EmployeeAssetLog.hostname.ilike(f'%{q}%')
            ))
        log_rows = log_query.group_by(
            EmployeeAssetLog.employee_email,
            EmployeeAssetLog.hostname
        ).all()

        latest_log_ids = [r.latest_id for r in log_rows if r.latest_id]
        asset_logs = EmployeeAssetLog.query.filter(
            EmployeeAssetLog.id.in_(latest_log_ids)
        ).all() if latest_log_ids else []

        # 2a. Bulk fetch servers + latest metric per server
        server_ids = list({log.server_id for log in asset_logs if log.server_id})
        servers = Server.query.filter(Server.id.in_(server_ids)).all() if server_ids else []
        server_map = {s.id: s for s in servers}

        latest_metric_rows = db.session.query(
            Metric.server_id,
            db.func.max(Metric.timestamp).label('max_ts')
        ).filter(
            Metric.server_id.in_(server_ids)
        ).group_by(Metric.server_id).all() if server_ids else []

        metric_lookup = {}
        if latest_metric_rows:
            max_ts_by_server = {r.server_id: r.max_ts for r in latest_metric_rows if r.max_ts is not None}
            ts_values = list({ts for ts in max_ts_by_server.values() if ts is not None})
            latest_metrics = Metric.query.filter(
                Metric.server_id.in_(list(max_ts_by_server.keys())),
                Metric.timestamp.in_(ts_values)
            ).all()
            for m in latest_metrics:
                if max_ts_by_server.get(m.server_id) == m.timestamp:
                    metric_lookup[m.server_id] = (m.cpu_util_percent or 0)
        
        for log in asset_logs:
            emp_email = log.employee_email.lower()
            if emp_email not in employee_dict:
                # User not in Azure, create skeleton
                if q and q not in emp_email and q not in log.hostname.lower():
                    continue
                employee_dict[emp_email] = {
                    'email': log.employee_email,
                    'name': log.employee_email.split('@')[0],
                    'title': 'N/A',
                    'department': 'N/A',
                    'user_id': None,
                    'assets': []
                }
                
            server = server_map.get(log.server_id)
            cpu_pct = metric_lookup.get(log.server_id, 0)
            is_online = server.is_online if server else False
                    
            asset_entry = {
                'id': f"log_{log.id}",
                'hostname': log.hostname,
                'ip_address': log.ip_address or '—',
                'os_info': log.os_info or 'Unknown',
                'device_type': log.device_type or 'Unknown',
                'cpu_percent': cpu_pct,
                'is_online': is_online,
                'source': 'Agent',
                'assigned_date': log.login_timestamp.isoformat() if log.login_timestamp else None
            }
            # Prevent duplicates
            if not any(a['hostname'] == log.hostname for a in employee_dict[emp_email]['assets']):
                employee_dict[emp_email]['assets'].append(asset_entry)
                
        # 3. Gather AzureDeviceOwner/AzureDevice mapping in bulk
        # azure_db_id holds the AzureUser DB PK (int). AzureUser.user_id holds the Azure AD object id (string).
        # AzureDeviceOwner.user_id is an INTEGER FK to AzureUser.id — do NOT pass Azure AD UUID strings into it.
        db_user_ids = [e['azure_db_id'] for e in employee_dict.values() if e.get('azure_db_id')]
        # Collect any Azure AD object ids (strings) we have, and resolve them to DB ids before querying
        azure_ad_ids = [e['user_id'] for e in employee_dict.values() if e.get('user_id')]

        resolved_ids = []
        if azure_ad_ids:
            # Find corresponding AzureUser DB ids for these Azure AD object ids
            matches = AzureUser.query.filter(
                AzureUser.tenant_id == tenant_id,
                AzureUser.user_id.in_(azure_ad_ids)
            ).with_entities(AzureUser.id).all()
            resolved_ids = [m.id for m in matches]

        # Combine DB ids from both sources (deduplicated)
        owner_user_ids = list({int(x) for x in (db_user_ids or []) + (resolved_ids or [])})

        owners = AzureDeviceOwner.query.filter(
            AzureDeviceOwner.tenant_id == tenant_id,
            AzureDeviceOwner.user_id.in_(owner_user_ids)
        ).all() if owner_user_ids else []

        # Build owner lookup with linked_at dates
        owners_by_user = {}
        owner_linked_at = {}  # (user_id, device_id) -> linked_at date
        device_ids = set()
        graph_device_ids = set()
        for o in owners:
            owners_by_user.setdefault(o.user_id, []).append(o.device_id)
            if o.device_id:
                if isinstance(o.device_id, int) or str(o.device_id).isdigit():
                    device_ids.add(int(o.device_id))
                else:
                    graph_device_ids.add(o.device_id)
            owner_linked_at[(o.user_id, o.device_id)] = o.linked_at

        devices = AzureDevice.query.filter(
            AzureDevice.tenant_id == tenant_id,
            db.or_(
                AzureDevice.id.in_(list(device_ids)),
                AzureDevice.device_id.in_(list(graph_device_ids))
            )
        ).all() if (device_ids or graph_device_ids) else []
        device_map = {d.id: d for d in devices}
        device_map.update({d.device_id: d for d in devices})

        for emp_email, emp_data in employee_dict.items():
            owner_keys = [v for v in (emp_data.get('azure_db_id'), emp_data.get('user_id')) if v]
            if not owner_keys:
                continue
            for owner_key in owner_keys:
              for device_id in owners_by_user.get(owner_key, []):
                dev = device_map.get(device_id)
                if dev:
                    # check dupes by name
                    if not any(a['hostname'].lower() == dev.display_name.lower() for a in emp_data['assets']):
                        linked = owner_linked_at.get((owner_key, device_id))
                        emp_data['assets'].append({
                            'id': f"azure_{dev.id}",
                            'hostname': dev.display_name,
                            'ip_address': '—',
                            'os_info': dev.os_platform or 'Unknown',
                            'device_type': dev.device_type or 'Unknown',
                            'cpu_percent': 0,
                            'source': 'Intune/Entra',
                            'assigned_date': linked.isoformat() if linked else None
                        })

        # Apply final status filter & sort
        final_list = list(employee_dict.values())
        
        # Apply source filter first (filters individual assets)
        if sourceFilter == 'agent':
            for e in final_list:
                e['assets'] = [a for a in e['assets'] if a['source'] == 'Agent']
        elif sourceFilter == 'azure':
            for e in final_list:
                e['assets'] = [a for a in e['assets'] if a['source'] == 'Intune/Entra']

        # Sort by having assets first, then by name
        def sort_key(emp):
            has_assets = len(emp['assets']) > 0
            return (0 if has_assets else 1, emp['name'].lower())
            
        final_list.sort(key=sort_key)
        
        if statusFilter == 'active':
            final_list = [e for e in final_list if len(e['assets']) > 0]
        elif statusFilter == 'healthy':
            final_list = [e for e in final_list if len(e['assets']) > 0 and all(a['cpu_percent'] < 80 for a in e['assets'])]
        elif statusFilter == 'warning':
            final_list = [e for e in final_list if any(80 <= a['cpu_percent'] < 95 for a in e['assets'])]
        elif statusFilter == 'critical':
            final_list = [e for e in final_list if any(a['cpu_percent'] >= 95 for a in e['assets'])]
            
        # If source filter is applied, remove employees with no assets matching the filter to clean up the view
        if sourceFilter in ('agent', 'azure'):
            final_list = [e for e in final_list if len(e['assets']) > 0]
            
        # Perform memory slicing for pagination
        total = len(final_list)
        paged = final_list[offset:offset+limit]
        
        return jsonify({
            'success': True,
            'total': total,
            'offset': offset,
            'limit': limit,
            'data': paged
        })
    except Exception as e:
        logger.error(f"Error in employees_scroll: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@asset_mgmt_bp.route('/assets/employee/<email>')
@login_required
def employee_asset_detail(email):
    """Show detailed information about an employee and their combined assets"""
    try:
        tenant_id = current_user.tenant_id
        
        # 1. Fetch User Info
        # Try Manual Employee first
        manual_emp = Employee.query.filter(
            Employee.tenant_id == tenant_id,
            Employee.email.ilike(email)
        ).first()

        azure_user = None
        if not manual_emp:
            azure_user = AzureUser.query.filter(
                AzureUser.tenant_id == tenant_id,
                AzureUser.email.ilike(email)
            ).first()

        user_info = {
            'name': manual_emp.name if manual_emp else (azure_user.display_name if azure_user else email.split('@')[0]),
            'email': email,
            'title': manual_emp.designation if manual_emp else (azure_user.job_title if azure_user else 'N/A'),
            'department': manual_emp.department if manual_emp else (azure_user.department if azure_user else 'N/A'),
            'is_manual': manual_emp is not None
        }

        asset_details = []
        seen_hostnames = set()

        # 2. Get Agent Managed Devices (EmployeeAssetLog) — deduplicated per hostname/server
        from collections import defaultdict
        server_logs = defaultdict(list)
        asset_logs = EmployeeAssetLog.query.filter(
            EmployeeAssetLog.employee_email.ilike(email),
            EmployeeAssetLog.tenant_id == tenant_id
        ).order_by(EmployeeAssetLog.login_timestamp.desc()).all()

        for log in asset_logs:
            key = log.server_id or log.hostname.lower()
            server_logs[key].append(log)

        # Pre-fetch servers and related metrics/alerts to fix N+1 issue
        server_ids = [s for s in server_logs.keys() if isinstance(s, int)]
        servers_map = {}
        metrics_map = {}
        activities_map = {}
        alerts_map = {}

        if server_ids:
            servers = Server.query.filter(Server.id.in_(server_ids)).all()
            servers_map = {s.id: s for s in servers}

            # Fetch latest metric for each server
            latest_metric_rows = db.session.query(
                Metric.server_id,
                db.func.max(Metric.timestamp).label('max_ts')
            ).filter(Metric.server_id.in_(server_ids)).group_by(Metric.server_id).all()
            if latest_metric_rows:
                ts_dict = {r.server_id: r.max_ts for r in latest_metric_rows}
                metrics = Metric.query.filter(
                    Metric.server_id.in_(list(ts_dict.keys())),
                    Metric.timestamp.in_(list(ts_dict.values()))
                ).all()
                for m in metrics:
                    if ts_dict.get(m.server_id) == m.timestamp:
                        metrics_map[m.server_id] = m

            # Fetch active alerts for all servers
            all_alerts = SystemAlert.query.filter(
                SystemAlert.server_id.in_(server_ids), 
                SystemAlert.is_active == True
            ).all()
            for a in all_alerts:
                alerts_map.setdefault(a.server_id, []).append(a)

            # Fetch LATEST recent activities for all servers (within last 7 days, ordered newest first)
            from datetime import datetime, timedelta
            seven_days_ago = datetime.utcnow() - timedelta(days=7)
            all_activities = DeviceActivity.query.filter(
                DeviceActivity.server_id.in_(server_ids),
                DeviceActivity.login_time >= seven_days_ago
            ).order_by(DeviceActivity.login_time.desc()).limit(300).all()
            for a in all_activities:
                if len(activities_map.setdefault(a.server_id, [])) < 20:
                    activities_map[a.server_id].append(a)

        for key, logs in server_logs.items():
            latest_log = logs[0]
            earliest_log = logs[-1]
            hostname_lower = latest_log.hostname.lower()
            if hostname_lower in seen_hostnames:
                continue
            seen_hostnames.add(hostname_lower)

            server = servers_map.get(latest_log.server_id) if latest_log.server_id else None
            if server:
                activities = activities_map.get(server.id, [])
                latest_metric = metrics_map.get(server.id)
                alerts = alerts_map.get(server.id, [])
                
                first_ts = earliest_log.login_timestamp
                last_ts = server.last_seen if server and server.last_seen else latest_log.login_timestamp
                
                asset_details.append({
                    'source': 'Agent',
                    'log_id': f"log_{latest_log.id}",
                    'hostname': latest_log.hostname,
                    'ip_address': server.ip or latest_log.ip_address or 'N/A',
                    'os_info': server.os_info or latest_log.os_info or 'Unknown',
                    'domain': latest_log.domain or 'N/A',
                    'device_type': latest_log.device_type or 'Unknown',
                    'first_login': first_ts.isoformat() + 'Z' if first_ts and getattr(first_ts, 'tzinfo', None) is None else (first_ts.isoformat() if first_ts else 'Unknown'),
                    'last_active': last_ts.isoformat() + 'Z' if last_ts and getattr(last_ts, 'tzinfo', None) is None else (last_ts.isoformat() if last_ts else 'Unknown'),
                    'server_id': server.id,
                    'server_status': 'Online' if server.is_online else 'Offline',
                    'is_online': server.is_online,
                    'cpu_percent': latest_metric.cpu_util_percent or 0 if latest_metric else 0,
                    'memory_percent': latest_metric.ram_util_percent or 0 if latest_metric else 0,
                    'disk_percent': latest_metric.ssd_util_percent or 0 if latest_metric else 0,
                    'virtual_cores': latest_metric.virtual_cores or 0 if latest_metric else 0,
                    'memory_gb': latest_metric.total_ram_gb or 0 if latest_metric else 0,
                    'disk_gb': latest_metric.total_ssd_gb or 0 if latest_metric else 0,
                    'activities': [
                        {
                            'user': a.session_user,
                            'login': a.login_time.isoformat() + 'Z' if a.login_time and getattr(a.login_time, 'tzinfo', None) is None else (a.login_time.isoformat() if a.login_time else None),
                            'logout': a.logout_time.isoformat() + 'Z' if a.logout_time and getattr(a.logout_time, 'tzinfo', None) is None else (a.logout_time.isoformat() if a.logout_time else None),
                            'session_type': a.session_type,
                            'idle_minutes': a.idle_minutes,
                            'active_minutes': a.active_minutes
                        } for a in activities
                    ],
                    'alerts_count': len(alerts),
                    'alerts': [
                        {
                            'id': a.id,
                            'type': a.alert_type,
                            'message': a.message,
                            'severity': a.severity,
                            'created': a.created_at.isoformat() + 'Z' if getattr(a.created_at, 'tzinfo', None) is None else a.created_at.isoformat(),
                            'is_active': a.is_active
                        } for a in alerts[:5]
                    ],
                    'screenshots': Screenshot.query.filter_by(server_id=server.id).order_by(Screenshot.captured_at.desc()).limit(4).all()
                })

        # 3. Get Azure Managed Devices (Intune)
        if azure_user and azure_user.id:
            # AzureDeviceOwner.user_id is an INTEGER FK to AzureUser.id — only compare integer IDs.
            owners = AzureDeviceOwner.query.filter(
                AzureDeviceOwner.tenant_id == tenant_id,
                AzureDeviceOwner.user_id == azure_user.id
            ).all()
            for o in owners:
                dev = db.session.get(AzureDevice, int(o.device_id)) if str(o.device_id).isdigit() else None
                if not dev:
                    dev = AzureDevice.query.filter_by(tenant_id=tenant_id, device_id=o.device_id).first()
                if dev and dev.display_name.lower() not in seen_hostnames:
                    seen_hostnames.add(dev.display_name.lower())
                    asset_details.append({
                        'source': 'Intune/Entra',
                        'log_id': f"dev_{dev.id}",
                        'hostname': dev.display_name,
                        'ip_address': 'N/A',
                        'os_info': dev.os_platform or 'Unknown',
                        'domain': 'Azure AD Joined',
                        'device_type': dev.device_type or 'Unknown',
                        'first_login': dev.created_at.isoformat() + 'Z' if dev.created_at and getattr(dev.created_at, 'tzinfo', None) is None else (dev.created_at.isoformat() if dev.created_at else 'Unknown'),
                        'last_active': dev.created_at.isoformat() + 'Z' if dev.created_at and getattr(dev.created_at, 'tzinfo', None) is None else (dev.created_at.isoformat() if dev.created_at else 'Unknown'),
                        'server_id': None,
                        'server_status': 'Intune Managed',
                        'cpu_percent': 0,
                        'memory_percent': 0,
                        'disk_percent': 0,
                        'virtual_cores': 0,
                        'memory_gb': 0,
                        'disk_gb': 0,
                        'activities': [],
                        'alerts_count': 0,
                        'alerts': []
                    })

        if not asset_details and not azure_user:
            return redirect(url_for('asset_mgmt.list_employees_assets'))

        return render_template(
            'employee_asset_detail.html',
            email=email,
            user_info=user_info,
            assets=asset_details,
            total_assets=len(asset_details)
        )
    
    except Exception as e:
        logger.error(f"Error loading employee asset detail: {e}")
        return redirect(url_for('asset_mgmt.list_employees_assets'))


@asset_mgmt_bp.route('/assets/reports')
@login_required
def reports():
    """Admin reports UI — allows downloading various CSV reports (productivity, device activity, audit logs)."""
    # Only show to superadmins/tenant admins
    if not current_user.is_superadmin:
        return render_template('reports.html', error='Only super admins can access reports', users=[], default_start=None, default_end=None)

    # Gather available users from EmployeeActivity for filter dropdown
    try:
        from web.models import EmployeeActivity, db, Server
        # Restrict to tenant servers
        server_q = Server.query.filter_by(tenant_id=current_user.tenant_id).with_entities(Server.id).all()
        server_ids = [r.id for r in server_q]
        users = []
        if server_ids:
            rows = db.session.query(EmployeeActivity.user).filter(EmployeeActivity.server_id.in_(server_ids)).distinct().all()
            users = sorted([r[0] for r in rows if r[0]])
    except Exception:
        users = []

    # Defaults for date range (today)
    from datetime import date, timedelta
    default_end = date.today().isoformat()
    default_start = (date.today() - timedelta(days=7)).isoformat()

    return render_template('reports.html', users=users, default_start=default_start, default_end=default_end)


@asset_mgmt_bp.route('/assets/remote-control/<int:server_id>')
@login_required
def remote_control_server(server_id):
    """Remote management interface for a server"""
    try:
        server = Server.query.get_or_404(server_id)
        
        # Check authorization - return HTML redirect for browsers (so anchors show a user-friendly message)
        if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
            # API clients expect JSON, but browser navigation expects an HTML response.
            if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
                return jsonify({'error': 'Unauthorized'}), 403
            flash('You are not authorized to view that system.', 'danger')
            return redirect(url_for('asset_mgmt.system_controls'))
        
        # Get tenant for SharePoint status
        tenant = Tenant.query.get(server.tenant_id)
        sharepoint_configured = (tenant and tenant.sharepoint_connected and tenant.sharepoint_site_url)
        
        # Get server status and metrics based on persistent status
        is_online = (server.status == 'online')
        
        latest_metric = Metric.query.filter_by(server_id=server_id)\
            .order_by(Metric.timestamp.desc()).first()
        
        # Get pending commands
        pending_commands = RemoteCommand.query.filter_by(
            server_id=server_id, status='pending'
        ).all()
        
        # Get recent commands
        recent_commands = RemoteCommand.query.filter_by(
            server_id=server_id
        ).order_by(RemoteCommand.created_at.desc()).limit(20).all()

        # Get recent screenshots
        from web.models import Screenshot
        recent_screenshots = Screenshot.query.filter_by(
            server_id=server_id
        ).order_by(Screenshot.captured_at.desc()).limit(12).all()
        
        return render_template(
            'remote_control_v2.html',
            server=server,
            is_online=is_online,
            sharepoint_configured=sharepoint_configured,
            cpu_percent=latest_metric.cpu_util_percent if latest_metric else 0,
            memory_percent=latest_metric.ram_util_percent if latest_metric else 0,
            disk_percent=latest_metric.ssd_util_percent if latest_metric else 0,
            pending_count=len(pending_commands),
            recent_commands=recent_commands,
            screenshots=recent_screenshots
        )
    
    except Exception as e:
        logger.error(f"Error loading remote control: {e}")
        return redirect(url_for('asset_mgmt.system_controls'))


@asset_mgmt_bp.route('/assets/system-controls')
@login_required
def system_controls():
    """System controls landing page (per-tenant list of servers)."""
    try:
        from web.models import EmployeeDeviceAssignment, Employee
        q = Server.query
        tenant_id = current_user.tenant_id if not current_user.is_superadmin else None
        
        if tenant_id:
            q = q.filter_by(tenant_id=tenant_id)
            
        servers = q.order_by(Server.hostname.asc()).all()
        
        # Attach assignment data for the UI
        assignments = []
        employees = []
        if tenant_id:
            assignments = EmployeeDeviceAssignment.query.filter_by(tenant_id=tenant_id, is_active=True).all()
            employees = Employee.query.filter_by(tenant_id=tenant_id).all()
        else:
            assignments = EmployeeDeviceAssignment.query.filter_by(is_active=True).all()
            employees = Employee.query.all()
            
        emp_map = {e.id: e.name or e.email for e in employees}
        assignment_map = {a.server_id: emp_map.get(a.employee_id) for a in assignments}
        
        for s in servers:
            s.assigned_employee_name = assignment_map.get(s.id)
            
        return render_template('system_controls.html', servers=servers)
    except Exception as e:
        logger.error(f"Error loading system controls: {e}")
        return render_template('system_controls.html', servers=[], error=str(e))


@asset_mgmt_bp.route('/assets/productivity')
@login_required
def productivity_overview():
    """HR View: Employee Productivity List."""
    try:
        tenant_id = current_user.tenant_id
        
        # Get target date from query args or default to today
        date_str = (request.args.get('date') or '').strip()
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.utcnow().date()
        except ValueError:
            target_date = datetime.utcnow().date()
            
        emp_rows = _build_productivity_rows(tenant_id, target_date)
        
        return render_template(
            'productivity_overview.html',
            employees=emp_rows,
            selected_date=target_date.strftime('%Y-%m-%d'),
            page_title='Employee Productivity',
            page_description='Employee productivity and linked agent system screenshots for the selected date.',
            workforce_mode=False
        )
    except Exception as e:
        logger.error(f"Error loading productivity view: {e}")
        return render_template('productivity_overview.html', employees=[], selected_date='', error=str(e))


@asset_mgmt_bp.route('/assets/productivity/report')
@login_required
def productivity_export():
    """Export filtered productivity rows as CSV."""
    try:
        tenant_id = current_user.tenant_id
        date_str = (request.args.get('date') or '').strip()
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.utcnow().date()
        except ValueError:
            target_date = datetime.utcnow().date()

        emp_rows = _build_productivity_rows(tenant_id, target_date)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'Employee Name', 'Email', 'Department', 'Device', 'Device IP',
            'Status', 'First Activity', 'Last Activity', 'Active Time', 'Idle Time',
            'Productive Time', 'Device Source'
        ])
        for row in emp_rows:
            writer.writerow([
                row['name'], row['email'], row['department'], row['device'], row['device_ip'],
                row['status'], row['first_activity'], row['last_activity'], row['active_str'],
                row['idle_str'], row['productive_str'], row['source']
            ])

        response = make_response(output.getvalue())
        response.headers['Content-Disposition'] = f'attachment; filename=productivity_{target_date.strftime("%Y%m%d")}.csv'
        response.mimetype = 'text/csv'
        return response
    except Exception as e:
        logger.error(f"Error exporting productivity CSV: {e}")
        return redirect(url_for('asset_mgmt.productivity_overview'))


@asset_mgmt_bp.route('/assets/productivity/screenshots')
@login_required
def productivity_screenshots():
    """Tenant-level system screenshot gallery for productivity monitoring."""
    try:
        tenant_id = current_user.tenant_id
        date_str = (request.args.get('date') or '').strip()
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.utcnow().date()
        except ValueError:
            target_date = datetime.utcnow().date()

        day_start = datetime.combine(target_date, datetime.min.time())
        day_end = datetime.combine(target_date, datetime.max.time())

        screenshots = Screenshot.query.filter(
            Screenshot.tenant_id == tenant_id,
            Screenshot.captured_at >= day_start,
            Screenshot.captured_at <= day_end
        ).order_by(Screenshot.captured_at.desc()).all()

        active_agents = ActiveAgentsMonitor.get_active_agents_for_tenant(tenant_id)
        return render_template(
            'productivity_screenshots.html',
            screenshots=screenshots,
            active_agents=active_agents,
            selected_date=target_date.strftime('%Y-%m-%d'),
            page_title='System Images',
            page_description='Review system screenshots captured by active agents across managed devices.',
            screenshot_mode=True,
            workforce_mode=False
        )
    except Exception as e:
        logger.error(f"Error loading productivity screenshots: {e}")
        return render_template(
            'productivity_screenshots.html',
            screenshots=[],
            active_systems=[],
            selected_date='',
            page_title='System Images',
            page_description='Unable to load system screenshots at this time.',
            screenshot_mode=True,
            workforce_mode=False,
            error=str(e)
        )


@asset_mgmt_bp.route('/assets/productivity/<int:employee_id>')
@login_required
def employee_productivity_detail(employee_id):
    """HR View: Deep dive into a specific employee's productivity."""
    from web.models import ActivitySession, AttendanceRecord, AppUsage
    try:
        tenant_id = current_user.tenant_id
        
        # Verify employee ownership
        emp = Employee.query.get_or_404(employee_id)
        if emp.tenant_id != tenant_id:
            abort(403)
            
        date_str = (request.args.get('date') or '').strip()
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.utcnow().date()
        except ValueError:
            target_date = datetime.utcnow().date()
            
        attendance = AttendanceRecord.query.filter_by(employee_id=emp.id, date=target_date).first()
        
        import pytz
        ist = pytz.timezone('Asia/Kolkata')
        attendance_first_activity_display = None
        attendance_last_activity_display = None
        attendance_status = 'not_available'
        if attendance:
            attendance_status = 'recorded'
            if attendance.first_activity:
                attendance_first_activity_display = attendance.first_activity.replace(tzinfo=pytz.UTC).astimezone(ist)
            if attendance.last_activity:
                attendance_last_activity_display = attendance.last_activity.replace(tzinfo=pytz.UTC).astimezone(ist)
        
        day_start = datetime.combine(target_date, datetime.min.time())
        day_end = datetime.combine(target_date, datetime.max.time())
        sessions = ActivitySession.query.filter(
            ActivitySession.employee_id == emp.id,
            ActivitySession.start_time >= day_start,
            ActivitySession.start_time <= day_end
        ).order_by(ActivitySession.start_time.asc()).all()
        
        # Aggregate totals (now stored as seconds due to ProductivityEngine precision change)
        active_sec = sum(s.active_minutes or 0 for s in sessions)
        idle_sec = sum(s.idle_minutes or 0 for s in sessions)
        prod_sec = sum(s.productive_minutes or 0 for s in sessions)
        
        active_str = _seconds_to_hms(active_sec)
        idle_str = _seconds_to_hms(idle_sec)
        prod_str = _seconds_to_hms(prod_sec)
        
        # Add formatted strings to the object dynamically (assuming seconds)
        for s in sessions:
            if s.start_time:
                s.start_time_display = s.start_time.replace(tzinfo=pytz.UTC).astimezone(ist)
            if s.end_time:
                s.end_time_display = s.end_time.replace(tzinfo=pytz.UTC).astimezone(ist)
            
            s_active_sec = s.active_minutes or 0
            s_idle_sec = s.idle_minutes or 0
            s.active_str = _seconds_to_hms(s_active_sec)
            s.idle_str = _seconds_to_hms(s_idle_sec)

        if not attendance and sessions:
            attendance_status = 'sessions'
            first_session = min((s for s in sessions if s.start_time), key=lambda x: x.start_time, default=None)
            last_session = max((s for s in sessions if s.end_time or s.start_time), key=lambda x: x.end_time or x.start_time, default=None)
            if first_session and first_session.start_time:
                attendance_first_activity_display = first_session.start_time.replace(tzinfo=pytz.UTC).astimezone(ist)
            if last_session:
                if last_session.end_time:
                    attendance_last_activity_display = last_session.end_time.replace(tzinfo=pytz.UTC).astimezone(ist)
                elif last_session.start_time:
                    attendance_last_activity_display = last_session.start_time.replace(tzinfo=pytz.UTC).astimezone(ist)
        
        # Get App Usage for the day
        app_usages = []
        if sessions:
            session_ids = [s.id for s in sessions]
            app_usages = AppUsage.query.filter(AppUsage.session_id.in_(session_ids)).all()
            
        # Aggregate apps
        app_stats = {}
        for app in app_usages:
            name = app.app_name or 'Unknown'
            if name not in app_stats:
                app_stats[name] = {'duration': 0, 'classification': app.classification}
            app_stats[name]['duration'] += (app.duration_seconds or 0)
            
        # Convert app_stats to list and sort
        total_app_seconds = sum(data['duration'] for data in app_stats.values())
        duration_scale = (active_sec / total_app_seconds) if active_sec > 0 and total_app_seconds > active_sec else 1
        top_apps = []
        for name, data in app_stats.items():
            duration_seconds = int((data['duration'] or 0) * duration_scale)
            duration_min = round(duration_seconds / 60)
            top_apps.append({
                'name': name,
                'duration_min': duration_min,
                'duration_str': _seconds_to_hms(duration_seconds),
                'classification': data['classification']
            })
        top_apps.sort(key=lambda x: x['duration_min'], reverse=True)
        
        active_min = active_sec // 60
        idle_min = idle_sec // 60
        prod_min = prod_sec // 60
        
        return render_template(
            'employee_productivity.html',
            employee=emp,
            attendance=attendance,
            attendance_status=attendance_status,
            sessions=sessions,
            top_apps=top_apps,
            active_min=active_min,
            idle_min=idle_min,
            prod_min=prod_min,
            active_str=active_str,
            idle_str=idle_str,
            prod_str=prod_str,
            attendance_first_activity_display=attendance_first_activity_display,
            attendance_last_activity_display=attendance_last_activity_display,
            selected_date=target_date.strftime('%Y-%m-%d'),
            today=target_date.strftime('%b %d, %Y')
        )
    except Exception as e:
        logger.error(f"Error loading employee productivity detail: {e}")
        flash(f"Error loading details: {str(e)}", "error")
        return redirect(url_for('asset_mgmt.productivity_overview'))


@asset_mgmt_bp.route('/assets/remote-control/<int:server_id>/screenshots')
@login_required
def remote_control_screenshots(server_id):
    """Live screenshots page for a server."""
    try:
        server = Server.query.get_or_404(server_id)
        if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
            abort(403)

        tenant = Tenant.query.get(server.tenant_id)
        sharepoint_configured = (tenant and tenant.sharepoint_connected and tenant.sharepoint_site_url)

        return render_template(
            'remote_screenshots.html',
            server=server,
            sharepoint_configured=sharepoint_configured,
            screenshot_enabled=bool(server.screenshot_enabled),
            screenshot_interval=int(server.screenshot_interval_minutes or 10),
        )
    except Exception as e:
        logger.error(f"Error loading screenshots page: {e}")
        return redirect(url_for('asset_mgmt.remote_control_server', server_id=server_id))


@asset_mgmt_bp.route('/assets/remote-control/<int:server_id>/logs')
@login_required
def remote_control_logs(server_id):
    """Audit + remote command history for a server."""
    try:
        server = Server.query.get_or_404(server_id)
        if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
            abort(403)

        page = request.args.get('page', 1, type=int)
        per_page = 60

        # AuditLog does not store server_id; it stores a resource key like "Server:<hostname>"
        resource_key = f"Server:{server.hostname}"
        audit_query = AuditLog.query.filter(
            AuditLog.tenant_id == server.tenant_id,
            AuditLog.resource == resource_key
        ).order_by(AuditLog.timestamp.desc())
        paginated = audit_query.paginate(page=page, per_page=per_page)

        commands = RemoteCommand.query.filter_by(server_id=server_id).order_by(RemoteCommand.created_at.desc()).limit(50).all()

        return render_template(
            'remote_logs.html',
            server=server,
            logs=paginated.items,
            pagination=paginated,
            commands=commands,
        )
    except Exception as e:
        logger.error(f"Error loading remote logs: {e}")
        return redirect(url_for('asset_mgmt.remote_control_server', server_id=server_id))


@asset_mgmt_bp.route('/assets/remote-control/<int:server_id>/productivity')
@login_required
def remote_control_productivity(server_id):
    """Productivity page for a server (activity stream + summary)."""
    try:
        from web.models import EmployeeActivity
        from sqlalchemy import func

        server = Server.query.get_or_404(server_id)
        if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
            abort(403)

        employee = _find_employee_for_server(server, server.tenant_id)
        date_str = (request.args.get('date') or '').strip()
        if employee:
            if date_str:
                return redirect(url_for('asset_mgmt.employee_productivity_detail', employee_id=employee.id, date=date_str))
            return redirect(url_for('asset_mgmt.employee_productivity_detail', employee_id=employee.id))

        user_filter = (request.args.get('user') or '').strip()
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.utcnow().date()
        except ValueError:
            target_date = datetime.utcnow().date()

        day_start = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0)
        day_end = datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59)

        base = db.session.query(EmployeeActivity).filter(
            EmployeeActivity.server_id == server_id,
            EmployeeActivity.timestamp >= day_start,
            EmployeeActivity.timestamp <= day_end
        )
        if user_filter:
            base = base.filter(EmployeeActivity.user == user_filter)

        total_count = base.with_entities(func.count(EmployeeActivity.id)).scalar() or 0
        active_count = base.with_entities(func.sum(db.case((EmployeeActivity.idle_time < 60, 1), else_=0))).scalar() or 0

        active_time = int(active_count) * 10
        total_time = int(total_count) * 10
        percent = int((active_time / total_time * 100)) if total_time > 0 else 0

        activities = base.order_by(EmployeeActivity.timestamp.desc()).limit(1000).all()

        users = sorted([
            u[0] for u in db.session.query(EmployeeActivity.user)
            .filter(EmployeeActivity.server_id == server_id, EmployeeActivity.timestamp >= day_start, EmployeeActivity.timestamp <= day_end)
            .distinct().all()
            if u and u[0]
        ])

        return render_template(
            'remote_productivity.html',
            server=server,
            percent=percent,
            active_time_str=f"{active_time // 3600}h {(active_time % 3600) // 60}m",
            total_samples=int(total_count),
            activities=activities,
            users=users,
            selected_date=target_date.strftime('%Y-%m-%d'),
            selected_user=user_filter,
        )
    except Exception as e:
        logger.error(f"Error loading productivity page: {e}")
        return redirect(url_for('asset_mgmt.remote_control_server', server_id=server_id))


@asset_mgmt_bp.route('/assets/api/v2/asset/<int:server_id>/status')
@login_required
def asset_status(server_id):
    """Return JSON status/metrics for a server used by the employee detail UI."""
    try:
        server = Server.query.get_or_404(server_id)

        # Authorization: tenant-scoped or superadmin
        if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403

        latest_metric = Metric.query.filter_by(server_id=server_id).order_by(Metric.timestamp.desc()).first()

        # Build metrics payload with keys expected by the frontend
        if latest_metric:
            metrics = {
                'cpu_percent': float(latest_metric.cpu_util_percent or 0),
                'ram_percent': float(latest_metric.ram_util_percent or 0),
                'disk_percent': float(latest_metric.ssd_util_percent or 0),
                'ram_gb': float(latest_metric.used_ram_gb or 0),
                'ram_total': float(latest_metric.total_ram_gb or 0),
                'disk_gb': float(latest_metric.used_ssd_gb or 0),
                'disk_total': float(latest_metric.total_ssd_gb or 0),
                'virtual_cores': int(latest_metric.virtual_cores or 0)
            }
        else:
            metrics = {
                'cpu_percent': 0,
                'ram_percent': 0,
                'disk_percent': 0,
                'ram_gb': 0,
                'ram_total': 0,
                'disk_gb': 0,
                'disk_total': 0,
                'virtual_cores': 0
            }

        # Activity and alerts
        activities = DeviceActivity.query.filter_by(server_id=server_id).order_by(DeviceActivity.reported_at.desc()).limit(5).all()
        activity_summary = [
            {
                'user': a.session_user,
                'login': a.login_time.isoformat() if a.login_time else None,
                'logout': a.logout_time.isoformat() if a.logout_time else None,
                'idle_minutes': a.idle_minutes,
                'active_minutes': a.active_minutes,
                'session_type': a.session_type
            }
            for a in activities
        ]

        active_alerts = SystemAlert.query.filter_by(server_id=server_id, is_active=True).all()

        return jsonify({
            'success': True,
            'metrics': metrics,
            'activity': activity_summary,
            'alerts': {
                'active_count': len(active_alerts),
            }
        })

    except Exception as e:
        logger.error(f"Error fetching asset status for {server_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@asset_mgmt_bp.route('/assets/api/v2/alert/<int:alert_id>/resolve', methods=['POST'])
@login_required
def resolve_incident(alert_id):
    """Resolve/close an active incident/alert"""
    try:
        alert = SystemAlert.query.get_or_404(alert_id)
        
        # Check authorization
        if not current_user.is_superadmin and alert.server.tenant_id != current_user.tenant_id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        # Mark alert as inactive/resolved
        alert.is_active = False
        alert.resolved_at = datetime.utcnow()
        db.session.commit()
        
        # Audit log
        audit = AuditLog(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            user=current_user.username,
            action='resolve_incident',
            resource=f'SystemAlert:{alert_id}',
            details=f'Resolved incident: {alert.alert_type} - {alert.message}'
        )
        db.session.add(audit)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Incident resolved'}), 200
    
    except Exception as e:
        logger.error(f"Error resolving incident: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@asset_mgmt_bp.route('/assets/api/v2/asset/<int:server_id>/delete', methods=['POST'])
@login_required
def delete_server(server_id):
    """Delete a server and all its associated data"""
    try:
        server = Server.query.get_or_404(server_id)
        
        # Check authorization
        if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
            
        # Delete related records
        from web.models import Screenshot
        Screenshot.query.filter_by(server_id=server_id).delete()
        Metric.query.filter_by(server_id=server_id).delete()
        DeviceActivity.query.filter_by(server_id=server_id).delete()
        SystemAlert.query.filter_by(server_id=server_id).delete()
        RemoteCommand.query.filter_by(server_id=server_id).delete()
        EmployeeAssetLog.query.filter_by(server_id=server_id).delete()
        
        db.session.delete(server)
        db.session.commit()
        
        logger.info(f"Server {server_id} ({server.hostname}) deleted by {current_user.username}")
        
        return jsonify({'success': True, 'message': 'Device deleted successfully'})
        
    except Exception as e:
        logger.error(f"Error deleting server {server_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@asset_mgmt_bp.route('/assets/audit-logs')
@login_required
def view_audit_logs():
    """View audit trail for all remote operations"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 50
        
        # Get audit logs for this tenant
        audit_query = AuditLog.query.filter_by(
            tenant_id=current_user.tenant_id
        ).order_by(AuditLog.timestamp.desc())
        
        # Filter by action if provided
        action_filter = request.args.get('action', '')
        if action_filter:
            audit_query = audit_query.filter(AuditLog.action.contains(action_filter))
        
        paginated = audit_query.paginate(page=page, per_page=per_page)
        
        return render_template(
            'audit_logs.html',
            logs=paginated.items,
            pagination=paginated,
            total_logs=paginated.total
        )
    
    except Exception as e:
        logger.error(f"Error loading audit logs: {e}")
        # Return with empty pagination object to prevent template errors
        class EmptyPagination:
            total = 0
            pages = 0
            items = []
        
        return render_template(
            'audit_logs.html',
            logs=[],
            pagination=EmptyPagination(),
            error=str(e)
        )


@asset_mgmt_bp.route('/server/<int:server_id>/audit-gallery')
@login_required
def server_audit_gallery(server_id):
    """Server-specific audit log + screenshot gallery view"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 50

        server = Server.query.get_or_404(server_id)
        if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
            abort(403)

        # Audit logs for this server
        resource_key = f"Server:{server.hostname}"
        audit_query = AuditLog.query.filter(
            AuditLog.tenant_id == server.tenant_id,
            AuditLog.resource == resource_key
        ).order_by(AuditLog.timestamp.desc())
        paginated = audit_query.paginate(page=page, per_page=per_page)

        # Recent screenshots for this server (latest 200)
        screenshots = Screenshot.query.filter_by(server_id=server_id).order_by(Screenshot.captured_at.desc()).limit(200).all()

        return render_template('server_audit_gallery.html', server=server, logs=paginated.items, pagination=paginated, screenshots=screenshots)

    except Exception as e:
        logger.error(f"Error loading server audit/gallery for {server_id}: {e}")
        return render_template('server_audit_gallery.html', server=None, logs=[], pagination=None, screenshots=[], error=str(e))
@asset_mgmt_bp.route('/employees/add', methods=['POST'])
@login_required
def add_employee():
    """Manually add an employee for monitoring (IT-generated email)"""
    try:
        data = request.form
        name = data.get('name')
        email = data.get('email')
        local_username = data.get('local_username')
        department = data.get('department')
        designation = data.get('designation')
        manager_id_raw = data.get('manager_id')
        manager_id = int(manager_id_raw) if manager_id_raw and manager_id_raw.isdigit() else None
        
        if not name or not email:
            return jsonify({'success': False, 'error': 'Name and Email are required'}), 400
            
        emp = Employee(
            tenant_id=current_user.tenant_id,
            name=name,
            email=email,
            local_username=local_username,
            department=department,
            designation=designation,
            manager_id=manager_id
        )
        db.session.add(emp)
        db.session.commit()
        return redirect(url_for('asset_mgmt.list_employees_assets'))
    except Exception as e:
        logger.error(f"Error adding employee: {e}")
        return redirect(url_for('asset_mgmt.list_employees_assets'))

@asset_mgmt_bp.route('/employees/delete/<int:employee_id>', methods=['POST'])
@login_required
def delete_employee(employee_id):
    """Remove a manually added employee"""
    try:
        emp = Employee.query.get_or_404(employee_id)
        if emp.tenant_id != current_user.tenant_id:
            return "Unauthorized", 403
            
        db.session.delete(emp)
        db.session.commit()
        return redirect(url_for('asset_mgmt.list_employees_assets'))
    except Exception as e:
        logger.error(f"Error deleting employee: {e}")
        return redirect(url_for('asset_mgmt.list_employees_assets'))

@asset_mgmt_bp.route('/sync_sharepoint', methods=['POST'])
@login_required
def manual_sharepoint_sync():
    """Manually trigger data sync to SharePoint for the requested tenant"""
    try:
        from web.models import Tenant
        from web.services.sharepoint_sync import force_sync_tenant
        
        data = request.get_json() or {}
        req_tenant_id = data.get('tenant_id')
        
        if current_user.is_superadmin and req_tenant_id:
            tenant = db.session.get(Tenant, req_tenant_id)
        else:
            tenant = db.session.get(Tenant, current_user.tenant_id)
            
        if not tenant:
            return jsonify({'success': False, 'error': 'Tenant not found.'})
            
        if not tenant.sharepoint_connected:
            return jsonify({'success': False, 'error': 'SharePoint not connected for this organization'})
            
        if not tenant.sharepoint_site_url:
            return jsonify({'success': False, 'error': 'Please save your SharePoint Site URL configuration first before syncing.'})
            
        # Use the unified force_sync_tenant method to properly calculate windows and update timestamps
        result = force_sync_tenant(tenant.id)
        
        if result.get('success'):
            bd = result.get('breakdown', {})
            return jsonify({
                'success': True,
                'metrics': bd.get('metrics', 0),
                'vms': bd.get('vms', 0),
                'logs': bd.get('logs', 0),
                'employees': bd.get('employees', 0),
                'activity': bd.get('activity', 0),
                'screenshots': bd.get('screenshots', 0),
                'error': result.get('error')
            })
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Unknown error during sync.')})
            
    except Exception as e:
        logger.error(f"Manual SharePoint sync failed: {e}")
        return jsonify({'success': False, 'error': str(e)})


@asset_mgmt_bp.route('/api/notifications', methods=['GET'])
@login_required
def get_notifications():
    """Fetch recent sync notifications for the current tenant"""
    try:
        from web.models import SyncNotification
        
        notifications = SyncNotification.query.filter_by(
            tenant_id=current_user.tenant_id
        ).order_by(SyncNotification.created_at.desc()).limit(20).all()
        
        unread_count = SyncNotification.query.filter_by(
            tenant_id=current_user.tenant_id,
            is_read=False
        ).count()
        
        items = []
        for n in notifications:
            items.append({
                'id': n.id,
                'category': n.category,
                'title': n.title,
                'message': n.message,
                'is_read': n.is_read,
                'created_at': n.created_at.strftime('%Y-%m-%d %H:%M:%S UTC') if n.created_at else None,
                'time_ago': _time_ago(n.created_at) if n.created_at else ''
            })
        
        return jsonify({'success': True, 'notifications': items, 'unread_count': unread_count})
    except Exception as e:
        logger.error(f"Failed to fetch notifications: {e}")
        return jsonify({'success': True, 'notifications': [], 'unread_count': 0})


@asset_mgmt_bp.route('/api/notifications/mark_read', methods=['POST'])
@login_required
def mark_notifications_read():
    """Mark all notifications as read for the current tenant"""
    try:
        from web.models import SyncNotification
        
        SyncNotification.query.filter_by(
            tenant_id=current_user.tenant_id,
            is_read=False
        ).update({'is_read': True})
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Failed to mark notifications: {e}")
        return jsonify({'success': False})


def _time_ago(dt):
    """Convert datetime to human-readable 'time ago' string"""
    if not dt:
        return ''
    now = datetime.utcnow()
    diff = now - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return 'just now'
    elif seconds < 3600:
        mins = seconds // 60
        return f'{mins}m ago'
    elif seconds < 86400:
        hours = seconds // 3600
        return f'{hours}h ago'
    else:
        days = seconds // 86400
        return f'{days}d ago'

@asset_mgmt_bp.route('/api/tenant/manual-azure-sync', methods=['POST'])
@login_required
@require_tenant_access
def manual_azure_sync():
    """Manually trigger Azure AD synchronization for the current tenant."""
    try:
        from web.models import Tenant
        from auth.msal_auth import get_azure_client
        from web.azure_sync_service import AzureSyncService
        from core.identity_correlation import IdentityCorrelationService
        
        tenant_id = current_user.tenant_id
        tenant = db.session.get(Tenant, tenant_id)
        if not tenant:
            return jsonify({'success': False, 'error': 'Tenant not found.'}), 404
            
        if not tenant.azure_client_id or not tenant.azure_client_secret or not tenant.azure_tenant_id:
            return jsonify({'success': False, 'error': 'Please configure and save your Azure App credentials first.'}), 400
            
        client = get_azure_client(
            client_id=tenant.azure_client_id,
            client_secret=tenant.azure_client_secret,
            tenant_id=tenant.azure_tenant_id
        )
        
        # Trigger full comprehensive sync
        res = AzureSyncService.get_full_sync(db, tenant, client)
        
        if 'error' in res:
            return jsonify({'success': False, 'error': res['error']}), 500
            
        # Resolve device ownership using identity correlation engine
        IdentityCorrelationService.resolve_device_ownership(tenant.id)
        
        # Extract count details
        devices_count = res.get('devices', {}).get('synced', 0) + res.get('devices', {}).get('updated', 0)
        users_count = res.get('users', {}).get('synced', 0) + res.get('users', {}).get('updated', 0)
        licenses_count = res.get('licenses', {}).get('assignments', 0)
        
        return jsonify({
            'success': True,
            'users': users_count,
            'devices': devices_count,
            'licenses': licenses_count
        })
        
    except Exception as e:
        logger.error(f"Manual Azure Sync failed: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
