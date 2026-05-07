"""
Asset Management and Remote System Control Routes
Employees, Devices, Login/Logout tracking, Software Deployment, and Remote Access
"""

import logging
from datetime import datetime
from flask import Blueprint, render_template, jsonify, request, redirect, url_for, abort
from flask_login import login_required, current_user

from web.models import (
    db, Server, Metric, EmployeeAssetLog, DeviceActivity, 
    SystemAlert, AuditLog, RemoteCommand, Tenant,
    AzureUser, AzureDevice, AzureDeviceOwner, Screenshot, Employee
)

logger = logging.getLogger("[ASSET_MGMT]")

asset_mgmt_bp = Blueprint('asset_mgmt', __name__)


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
        
        return render_template(
            'asset_management.html',
            total_employees=total_employees,
            total_assets=total_assets
        )
    except Exception as e:
        logger.error(f"Error loading asset UI: {e}")
        return render_template('asset_management.html', error=str(e))

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
        for au in azure_users:
            email = (au.email or '').lower()
            if email and email not in employee_dict:
                employee_dict[email] = {
                    'email': au.email,
                    'name': au.display_name or 'Unknown',
                    'title': au.job_title or 'N/A',
                    'department': au.department or 'N/A',
                    'user_id': au.user_id,
                    'source': 'Azure',
                    'assets': []
                }
                
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
                'source': 'Agent'
            }
            # Prevent duplicates
            if not any(a['hostname'] == log.hostname for a in employee_dict[emp_email]['assets']):
                employee_dict[emp_email]['assets'].append(asset_entry)
                
        # 3. Gather AzureDeviceOwner/AzureDevice mapping in bulk
        user_ids = [e['user_id'] for e in employee_dict.values() if e.get('user_id')]
        owners = AzureDeviceOwner.query.filter(
            AzureDeviceOwner.tenant_id == tenant_id,
            AzureDeviceOwner.user_id.in_(user_ids)
        ).all() if user_ids else []

        owners_by_user = {}
        device_ids = set()
        for o in owners:
            owners_by_user.setdefault(o.user_id, []).append(o.device_id)
            if o.device_id:
                device_ids.add(o.device_id)

        devices = AzureDevice.query.filter(
            AzureDevice.tenant_id == tenant_id,
            AzureDevice.device_id.in_(list(device_ids))
        ).all() if device_ids else []
        device_map = {d.device_id: d for d in devices}

        for emp_email, emp_data in employee_dict.items():
            uid = emp_data['user_id']
            if not uid:
                continue
            for device_id in owners_by_user.get(uid, []):
                dev = device_map.get(device_id)
                if dev:
                    # check dupes by name
                    if not any(a['hostname'].lower() == dev.display_name.lower() for a in emp_data['assets']):
                        emp_data['assets'].append({
                            'id': f"azure_{dev.id}",
                            'hostname': dev.display_name,
                            'ip_address': '—',
                            'os_info': dev.os_platform or 'Unknown',
                            'device_type': dev.device_type or 'Unknown',
                            'cpu_percent': 0,
                            'source': 'Intune/Entra'
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
        if azure_user and azure_user.user_id:
            owners = AzureDeviceOwner.query.filter_by(tenant_id=tenant_id, user_id=azure_user.user_id).all()
            for o in owners:
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


@asset_mgmt_bp.route('/assets/remote-control/<int:server_id>')
@login_required
def remote_control_server(server_id):
    """Remote management interface for a server"""
    try:
        server = Server.query.get_or_404(server_id)
        
        # Check authorization
        if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
            return jsonify({'error': 'Unauthorized'}), 403
        
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
        return redirect(url_for('asset_mgmt.list_employees_assets'))


@asset_mgmt_bp.route('/assets/system-controls')
@login_required
def system_controls():
    """System controls landing page (per-tenant list of servers)."""
    try:
        q = Server.query
        if not current_user.is_superadmin:
            q = q.filter_by(tenant_id=current_user.tenant_id)
        servers = q.order_by(Server.hostname.asc()).all()
        return render_template('system_controls.html', servers=servers)
    except Exception as e:
        logger.error(f"Error loading system controls: {e}")
        return render_template('system_controls.html', servers=[], error=str(e))


@asset_mgmt_bp.route('/assets/productivity')
@login_required
def productivity_overview():
    """Productivity landing page (per-tenant list of servers)."""
    try:
        from web.models import EmployeeActivity
        from sqlalchemy import func

        q = Server.query
        if not current_user.is_superadmin:
            q = q.filter_by(tenant_id=current_user.tenant_id)
        servers = q.order_by(Server.hostname.asc()).all()
        server_ids = [s.id for s in servers]

        date_str = (request.args.get('date') or '').strip()
        user_filter = (request.args.get('user') or '').strip()
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.utcnow().date()
        except ValueError:
            target_date = datetime.utcnow().date()

        day_start = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0)
        day_end = datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59)

        stats = {}
        if server_ids:
            activity_filter = [
                EmployeeActivity.server_id.in_(server_ids),
                EmployeeActivity.timestamp >= day_start,
                EmployeeActivity.timestamp <= day_end
            ]
            if user_filter:
                activity_filter.append(EmployeeActivity.user == user_filter)

            rows = (
                db.session.query(
                    EmployeeActivity.server_id,
                    func.count(EmployeeActivity.id).label('total_count'),
                    func.sum(db.case((EmployeeActivity.idle_time < 60, 1), else_=0)).label('active_count')
                )
                .filter(*activity_filter)
                .group_by(EmployeeActivity.server_id)
                .all()
            )
            for r in rows:
                active_count = int(r.active_count or 0)
                total_count = int(r.total_count or 0)
                active_time = active_count * 10
                total_time = total_count * 10
                percent = int((active_time / total_time * 100)) if total_time > 0 else 0
                stats[int(r.server_id)] = {
                    'percent': percent,
                    'active_time_str': f"{active_time // 3600}h {(active_time % 3600) // 60}m",
                    'total_samples': total_count,
                }

        # User dropdown: include everyone we've ever seen in activity, plus manually-maintained employee usernames.
        users_set = set()
        try:
            uq = db.session.query(EmployeeActivity.user).filter(EmployeeActivity.server_id.in_(server_ids)).distinct()
            for u in uq.all():
                if u and u[0]:
                    users_set.add(u[0])
        except Exception:
            pass
        try:
            emp_q = Employee.query
            if not current_user.is_superadmin:
                emp_q = emp_q.filter_by(tenant_id=current_user.tenant_id)
            for e in emp_q.all():
                if getattr(e, 'local_username', None):
                    users_set.add(e.local_username)
        except Exception:
            pass
        users = sorted(users_set)

        return render_template(
            'productivity_overview.html',
            servers=servers,
            stats=stats,
            users=users,
            selected_date=target_date.strftime('%Y-%m-%d'),
            selected_user=user_filter,
        )
    except Exception as e:
        logger.error(f"Error loading productivity overview: {e}")
        return render_template('productivity_overview.html', servers=[], stats={}, users=[], selected_date='', selected_user='', error=str(e))


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

        date_str = (request.args.get('date') or '').strip()
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


@asset_mgmt_bp.route('/api/v2/server/<int:server_id>/remote/software', methods=['POST'])
@login_required
def deploy_software(server_id):
    """Deploy or uninstall software on a server"""
    try:
        server = Server.query.get_or_404(server_id)
        
        # Authorization check
        if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        data = request.get_json()
        action = data.get('action')  # install or uninstall
        software = data.get('software')  # software name
        
        if not action or not software:
            return jsonify({'error': 'Missing action or software name'}), 400
        
        # Create command for agent
        remote_cmd = RemoteCommand()
        remote_cmd.server_id = server_id
        remote_cmd.command = f"{action.upper()} {software}"
        remote_cmd.parameters = f'{{"action": "{action}", "software": "{software}", "requested_by": "{current_user.username}"}}'
        remote_cmd.status = 'pending'
        db.session.add(remote_cmd)
        
        # Log audit trail
        audit = AuditLog()
        audit.tenant_id = current_user.tenant_id
        audit.user = current_user.username
        audit.action = f'DEPLOY_SOFTWARE:{action}'
        audit.resource = f'Server:{server.hostname}'
        audit.details = f'{action} {software}'
        audit.timestamp = datetime.utcnow()
        audit.status = 'pending'
        db.session.add(audit)
        db.session.commit()
        
        logger.info(f"Software deployment queued: {action} {software} on {server.hostname}")
        
        return jsonify({
            'success': True,
            'command_id': remote_cmd.id,
            'message': f'Software {action} queued for {server.hostname}'
        })
    
    except Exception as e:
        logger.error(f"Error deploying software: {e}")
        return jsonify({'error': str(e)}), 500


@asset_mgmt_bp.route('/api/v2/server/<int:server_id>/remote/rdp', methods=['POST'])
@login_required
def get_rdp_access(server_id):
    """Generate RDP connection details for remote access"""
    try:
        server = Server.query.get_or_404(server_id)
        
        # Authorization check
        if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Log audit trail for RDP access
        audit = AuditLog()
        audit.tenant_id = current_user.tenant_id
        audit.user = current_user.username
        audit.action = 'REMOTE_ACCESS:RDP'
        audit.resource = f'Server:{server.hostname}'
        audit.details = f'RDP access initiated'
        audit.timestamp = datetime.utcnow()
        audit.status = 'accessed'
        db.session.add(audit)
        db.session.commit()
        
        logger.info(f"RDP access initiated for {server.hostname} by {current_user.username}")
        
        return jsonify({
            'success': True,
            'hostname': server.hostname,
            'ip_address': server.ip,
            'rdp_command': f'mstsc /v:{server.ip}',
            'timestamp': datetime.utcnow().isoformat(),
            'accessed_by': current_user.username
        })
    
    except Exception as e:
        logger.error(f"Error generating RDP access: {e}")
        return jsonify({'error': str(e)}), 500



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
        
        if not name or not email:
            return jsonify({'success': False, 'error': 'Name and Email are required'}), 400
            
        emp = Employee(
            tenant_id=current_user.tenant_id,
            name=name,
            email=email,
            local_username=local_username,
            department=department,
            designation=designation
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

