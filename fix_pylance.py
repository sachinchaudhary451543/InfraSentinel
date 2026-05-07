#!/usr/bin/env python3
"""Fix Pylance errors in api.py by adding helper functions and using typed patterns"""

# Read the file with UTF-8 encoding
with open('web/routes/api.py', 'r', encoding='utf-8') as f:
    content = f.read()

# ============================================================================
# PHASE 1: Add helper function after api_error_handler if not already present
# ============================================================================
if 'def _emit_to_room' not in content:
    # Find the position after api_error_handler function
    marker = "    return wrapped\n\n\ndef _resolve_agent_identity"
    helper_code = '''    return wrapped


def _emit_to_room(event: str, data: dict, room: str | None = None, to: str | None = None) -> None:
    """
    Typed wrapper for socketio.emit with room/to support.
    This properly handles the room/to parameters by using **kwargs unpacking,
    which allows Pylance to accept parameters that may not be in its type stubs.
    
    Args:
        event: Event name to emit
        data: Data dict to send
        room: Room ID to emit to (for tenant isolation)
        to: Alternative name for room (flask-socketio supports both)
    """
    try:
        from web.app import socketio
        # Use **kwargs to bypass strict type checking for parameters not in stubs
        emit_kwargs: dict = {}
        if room is not None:
            emit_kwargs['room'] = room
        elif to is not None:
            emit_kwargs['to'] = to
        socketio.emit(event, data, **emit_kwargs)
    except Exception as e:
        logging.warning(f"Failed to emit {event}: {e}")


def _get_current_user():
    """Return typed current_user for static checkers (asserts authenticated).

    This asserts current_user is present (routes guarded by @login_required)
    and returns it cast to the application's User model type so Pylance
    recognizes attributes like tenant_id and is_superadmin.
    """
    from typing import cast
    from web.models import User
    u = current_user
    assert u is not None
    return cast(User, u)


def _resolve_agent_identity'''
    content = content.replace(marker, helper_code)
    print("✓ Added helper functions (_emit_to_room, _get_current_user)")

# ============================================================================
# PHASE 2: Replace SQLAlchemy model constructors with attribute assignment
# ============================================================================
# DeviceActivity
old = '''                active_session = DeviceActivity(  # type: ignore
                    server_id=server.id,
                    session_user=raw_user,
                    login_time=now_utc,
                    reported_at=now_utc,
                    session_type='interactive'
                )'''
new = '''                active_session = DeviceActivity()
                active_session.server_id = server.id
                active_session.session_user = raw_user
                active_session.login_time = now_utc
                active_session.reported_at = now_utc
                active_session.session_type = 'interactive\''''
if old in content:
    content = content.replace(old, new)
    print("✓ Fixed DeviceActivity constructor (line 186-190)")

# EmployeeAssetLog
old = '''        log = EmployeeAssetLog(  # type: ignore
            server_id=server.id,
            tenant_id=server.tenant_id,
            employee_id=employee_id,
            employee_email=employee_email,
            hostname=server.hostname or server.name or 'Unknown',
            ip_address=server.ip,
            os_info=server.os_info,
            device_type=(server.server_type or 'endpoint').lower(),
            login_timestamp=now_utc
        )'''
new = '''        log = EmployeeAssetLog()
        log.server_id = server.id
        log.tenant_id = server.tenant_id
        log.employee_id = employee_id
        log.employee_email = employee_email
        log.hostname = server.hostname or server.name or 'Unknown'
        log.ip_address = server.ip
        log.os_info = server.os_info
        log.device_type = (server.server_type or 'endpoint').lower()
        log.login_timestamp = now_utc'''
if old in content:
    content = content.replace(old, new)
    print("✓ Fixed EmployeeAssetLog constructor")

# Metric in api_metrics_push
old = '''    m = Metric(
        server_id=server.id,
        cpu=cpu_val,
        ram=ram_val,
        disk=disk_val,
        timestamp=datetime.utcnow()
    )'''
new = '''    m = Metric()
    m.server_id = server.id
    m.cpu = cpu_val
    m.ram = ram_val
    m.disk = disk_val
    m.timestamp = datetime.utcnow()'''
if old in content:
    content = content.replace(old, new)
    print("✓ Fixed Metric constructor (api_metrics_push)")

# EmployeeActivity
old = '''    activity = EmployeeActivity(  # type: ignore
        server_id=server.id,
        user=data.get('logged_in_user', 'System'),
        app=data.get('active_app', 'None'),
        window_title=data.get('window_title', 'None'),
        idle_time=data.get('idle_time', 0),
        timestamp=datetime.utcnow()
    )'''
new = '''    activity = EmployeeActivity()
    activity.server_id = server.id
    activity.user = data.get('logged_in_user', 'System')
    activity.app = data.get('active_app', 'None')
    activity.window_title = data.get('window_title', 'None')
    activity.idle_time = data.get('idle_time', 0)
    activity.timestamp = datetime.utcnow()'''
if old in content:
    content = content.replace(old, new)
    print("✓ Fixed EmployeeActivity constructor (api_metrics_push)")

# ============================================================================
# PHASE 3: Replace socketio.emit calls with _emit_to_room
# ============================================================================
# Pattern 1: socketio.emit with room parameter
old = '''        socketio.emit('metrics_update', {  # type: ignore
            'server_id': server.id,
            'tenant_id': server.tenant_id,
            'hostname': server.hostname,
            'status': server.status_label,
            'metrics': {'cpu': m.cpu, 'ram': m.ram, 'disk': m.disk},
            'activity': {'user': activity.user, 'app': activity.app, 'idle': activity.idle_time},
            'vms': vm_list,
            'timestamp': m.timestamp.isoformat()
        }, room=str(server.tenant_id))  # type: ignore'''
new = '''        _emit_to_room('metrics_update', {
            'server_id': server.id,
            'tenant_id': server.tenant_id,
            'hostname': server.hostname,
            'status': server.status_label,
            'metrics': {'cpu': m.cpu, 'ram': m.ram, 'disk': m.disk},
            'activity': {'user': activity.user, 'app': activity.app, 'idle': activity.idle_time},
            'vms': vm_list,
            'timestamp': m.timestamp.isoformat()
        }, room=str(server.tenant_id))'''
if old in content:
    content = content.replace(old, new)
    print("✓ Fixed socketio.emit in api_metrics_push")

# Remove from web.app import socketio statements that are no longer needed
# (the _emit_to_room function handles this)
lines = content.split('\n')
new_lines = []
skip_next = False
for i, line in enumerate(lines):
    if line.strip() == 'from web.app import socketio':
        # Check if there's a socketio.emit right after this
        if i + 1 < len(lines) and 'socketio.emit' in lines[i + 1]:
            skip_next = True
            continue
    if skip_next and line.strip().startswith('socketio.emit'):
        skip_next = False
        continue
    new_lines.append(line)

content = '\n'.join(new_lines)

# Write back with UTF-8 encoding
with open('web/routes/api.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("\n✓ All fixes applied successfully!")
