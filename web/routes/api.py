"""
api.py – Core API Blueprint
Provides screenshot serving (local fallback) and screenshot gallery endpoints.
"""

import os
import json
import mimetypes
import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from typing import Any, cast
from sqlalchemy.exc import OperationalError

from flask import Blueprint, send_file, jsonify, abort, request, make_response, url_for
from flask_login import login_required, current_user
from web.services.notification_service import create_notification

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)

LOCAL_TZ = ZoneInfo(os.getenv('APP_TIMEZONE', 'Asia/Kolkata'))


def _as_utc_naive(dt):
    if not dt:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(ZoneInfo('UTC')).replace(tzinfo=None)


def _as_local(dt):
    if not dt:
        return None
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo('UTC'))
        return dt.astimezone(LOCAL_TZ)
    except Exception as e:
        logger.warning(f"Timezone conversion failed for {dt}: {e}. Returning None.")
        return None


def _local_day_bounds_utc_naive(day):
    start_local = datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=LOCAL_TZ)
    end_local = datetime(day.year, day.month, day.day, 23, 59, 59, 999999, tzinfo=LOCAL_TZ)
    return _as_utc_naive(start_local), _as_utc_naive(end_local)


def _queue_remote_command(db, RemoteCommand, server_id, command, *, parameters=None, timeout_seconds=120, created_by=None):
    """Queue a command, storing long scripts in parameters for Postgres varchar safety."""
    cmd = RemoteCommand()
    cmd.server_id = server_id
    cmd.command = command if len(command) <= 250 else command[:250]
    if len(command) > 250:
        payload = {}
        if parameters:
            try:
                payload = json.loads(parameters) if isinstance(parameters, str) else dict(parameters)
            except Exception:
                payload = {'parameters': parameters}
        payload['script'] = command
        cmd.parameters = json.dumps(payload)
    elif parameters is not None:
        cmd.parameters = json.dumps(parameters) if isinstance(parameters, (dict, list)) else parameters
    else:
        cmd.parameters = None
    cmd.status = 'pending'
    cmd.timeout_seconds = timeout_seconds
    if created_by:
        cmd.created_by = created_by
    db.session.add(cmd)
    return cmd


def _retry_db_commit(db, attempts=3, delay=0.5):
    for attempt in range(attempts):
        try:
            db.session.commit()
            return True
        except OperationalError as exc:
            message = str(exc).lower()
            if 'database is locked' in message and attempt < attempts - 1:
                db.session.rollback()
                time.sleep(delay * (attempt + 1))
                continue
            db.session.rollback()
            raise
    return False


def _retry_db_flush(db, attempts=3, delay=0.25):
    for attempt in range(attempts):
        try:
            db.session.flush()
            return True
        except OperationalError as exc:
            message = str(exc).lower()
            if 'database is locked' in message and attempt < attempts - 1:
                db.session.rollback()
                time.sleep(delay * (attempt + 1))
                continue
            db.session.rollback()
            raise
    return False


def _resolve_screenshot_local_path(shot, update_db=False):
    """Resolve a screenshot local path from stored path or known screenshot folder."""
    if not shot:
        return None

    path = (shot.local_file_path or '').strip()
    if path:
        try:
            if os.path.isfile(path):
                return os.path.abspath(path)
        except Exception:
            pass

    try:
        from web.app import app as flask_app
        app_root = os.path.dirname(flask_app.root_path)
        base_dir = os.path.join(app_root, 'data', 'screenshots')

        if shot.filename:
            candidate = os.path.abspath(os.path.join(base_dir, shot.filename))
            if os.path.isfile(candidate):
                if update_db and candidate != path:
                    shot.local_file_path = candidate
                    try:
                        from web.models import db
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
                return candidate

        if path:
            candidate = os.path.abspath(os.path.join(base_dir, os.path.basename(path)))
            if os.path.isfile(candidate):
                if update_db and candidate != path:
                    shot.local_file_path = candidate
                    try:
                        from web.models import db
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
                return candidate
    except Exception:
        pass

    return None

#
# Legacy agent compatibility endpoints
# - PowerShell agent in `web/static/agent/ServerMonitorAgent.ps1` posts to:
#     POST /api/metrics
#     POST /api/command
#     POST /api/screenshot?api_key=...
#     POST /api/register_agent
#


@api_bp.route('/api/metrics', methods=['POST'])
def legacy_api_metrics():
    """Back-compat wrapper for older agents. Delegates to /api/v2/agent/metrics."""
    return agent_metrics()


@api_bp.route('/api/command', methods=['POST'])
def legacy_api_command_poll():
    """Back-compat wrapper: return pending remote commands for an agent api_key."""
    from web.models import Server, RemoteCommand

    data = request.get_json(silent=True) or {}
    api_key = (data.get('api_key') or data.get('agent_key') or '').strip()
    hostname = (data.get('hostname') or '').strip()

    server = None
    if api_key:
        server = Server.query.filter_by(api_key=api_key).first()
    if server is None and hostname:
        server = Server.query.filter_by(hostname=hostname).first()
    if server is None:
        return jsonify({'success': False, 'commands': []})

    pending = RemoteCommand.query.filter_by(server_id=server.id, status='pending')\
        .order_by(RemoteCommand.created_at.asc()).limit(10).all()

    cmds = []
    for c in pending:
        cmds.append({
            'id': c.id,
            'command': c.command,
            'params': c.parameters or '',
        })

    return jsonify({'success': True, 'commands': cmds})


@api_bp.route('/api/register_agent', methods=['POST'])
def legacy_api_register_agent():
    """Back-compat wrapper: minimal agent registration/heartbeat."""
    from web.models import db, Server, Tenant

    data = request.get_json(silent=True) or {}
    api_key = (data.get('agent_key') or data.get('api_key') or request.headers.get('X-Agent-Key') or '').strip()
    hostname = (data.get('hostname') or '').strip()
    ip = (data.get('ip') or '').strip()
    os_info = (data.get('os_info') or '').strip()
    serial_number = (data.get('serial_number') or '').strip()

    if not hostname:
        return jsonify({'success': False, 'error': 'hostname required'}), 400

    server = None
    if api_key and api_key != 'demo_mode_key':
        server = Server.query.filter_by(api_key=api_key).first()
    if server is None:
        server = Server.query.filter_by(hostname=hostname).first()

    if server is None:
        tenant = Tenant.query.first()
        if not tenant:
            return jsonify({'success': False, 'error': 'No tenant configured'}), 400
        server = Server()
        server.hostname = hostname
        server.name = hostname
        server.tenant_id = tenant.id
        server.api_key = api_key or ''
        server.source = 'agent'
        server.type = 'agent'
        db.session.add(server)

    server.hostname = hostname
    server.name = server.name or hostname
    if ip:
        server.ip = ip
    if os_info:
        server.os_info = os_info
    if serial_number:
        server.serial_number = serial_number
    server.last_seen = datetime.utcnow()
    server.status = 'online'
    server.agent_installed = True
    server.monitoring_active = True
    db.session.commit()

    return jsonify({'success': True, 'server_id': server.id})


@api_bp.route('/api/screenshot', methods=['POST'])
def legacy_api_screenshot_upload():
    """Back-compat screenshot upload (multipart) used by older PowerShell agent."""
    from web.models import db, Server, Screenshot

    api_key = (request.args.get('api_key') or request.headers.get('X-Agent-Key') or '').strip()
    if not api_key:
        return jsonify({'success': False, 'error': 'api_key required'}), 400

    server = Server.query.filter_by(api_key=api_key).first()
    if not server:
        return jsonify({'success': False, 'error': 'Unknown agent key'}), 404

    f = request.files.get('file')
    if not f:
        return jsonify({'success': False, 'error': 'file required'}), 400

    now = datetime.utcnow()
    hostname = server.hostname or server.name or 'server'
    ts_str = now.strftime('%Y%m%d_%H%M%S')
    fname = f"screenshot_{server.id}_{hostname}_{ts_str}.jpg"

    try:
        # Use Flask app root (ServerMonitor) as base and join data/screenshots
        from web.app import app as flask_app
        app_root = os.path.dirname(flask_app.root_path)  # web -> ServerMonitor
        base_dir = os.path.join(app_root, 'data', 'screenshots')
        os.makedirs(base_dir, exist_ok=True)
        file_path = os.path.abspath(os.path.join(base_dir, fname))
        f.save(file_path)

        shot = Screenshot()
        shot.server_id = server.id
        shot.tenant_id = server.tenant_id
        shot.filename = fname
        shot.hostname = hostname
        shot.captured_at = now
        shot.uploaded_at = now
        shot.uploaded = False
        try:
            shot.file_size_kb = int(os.path.getsize(file_path) // 1024)
        except Exception:
            shot.file_size_kb = 0
        shot.active_user = ''
        shot.os_info = server.os_info or ''
        shot.ip_address = server.ip or ''
        shot.local_file_path = file_path
        db.session.add(shot)
        db.session.commit()
        return jsonify({'success': True, 'screenshot_id': shot.id})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Legacy screenshot upload failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# Screenshot file serving  (local_file_path fallback when SharePoint is absent)
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/api/screenshot/<int:screenshot_id>')
@login_required
def api_screenshot_view(screenshot_id):
    """
    Serve a locally stored screenshot image.
    Falls back to a 404 when the file doesn't exist on disk.
    """
    from web.models import Screenshot

    shot = Screenshot.query.get_or_404(screenshot_id)

    # Tenant isolation
    if not current_user.is_superadmin and shot.tenant_id != current_user.tenant_id:
        abort(403)

    # Defensive: check local file path and also attempt to resolve the screenshot folder if the stored path is stale.
    serve_path = _resolve_screenshot_local_path(shot, update_db=True)
    if serve_path:
        shot.local_file_path = serve_path
    file_exists = bool(serve_path)

    if not file_exists:
        logger.warning(f"Screenshot missing on disk: id={screenshot_id}, path={shot.local_file_path}")
        # If there's an external URL, redirect to it; otherwise return 204 (no content) to avoid breaking img tags
        if shot.sharepoint_url:
            from flask import redirect
            return redirect(shot.sharepoint_url)
        # Return a transparent 1x1 PNG when file missing to avoid broken images in the dashboard
        try:
            from io import BytesIO
            import base64
            # 1x1 transparent PNG
            transparent_png = base64.b64decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8Xw8AAuMB9U6qfzkAAAAASUVORK5CYII='
            )
            buf = BytesIO(transparent_png)
            resp = make_response(send_file(buf, mimetype='image/png', as_attachment=False, download_name='empty.png'))
            resp.headers['Cache-Control'] = 'public, max-age=60'
            return resp
        except Exception:
            abort(404)

    size = (request.args.get('size') or '').strip().lower()

    # Optional cached thumbnail for faster gallery loads.
    # Uses Pillow if installed; otherwise falls back to the original file.
    serve_path = shot.local_file_path
    serve_mime = None
    if size in ('thumb', 'sm', 'small'):
        try:
            from PIL import Image  # type: ignore

            thumb_dir = os.path.join(os.path.dirname(shot.local_file_path), "_thumbs")
            os.makedirs(thumb_dir, exist_ok=True)
            thumb_name = f"{os.path.basename(shot.local_file_path)}.thumb.jpg"
            thumb_path = os.path.join(thumb_dir, thumb_name)

            if (not os.path.isfile(thumb_path)) or (os.path.getmtime(thumb_path) < os.path.getmtime(shot.local_file_path)):
                with Image.open(shot.local_file_path) as im:
                    im = im.convert("RGB")
                    im.thumbnail((640, 640))
                    im.save(thumb_path, format="JPEG", quality=70, optimize=True)

            serve_path = thumb_path
            serve_mime = "image/jpeg"
        except Exception:
            serve_path = shot.local_file_path

    mime_type, _ = mimetypes.guess_type(serve_path)
    mime_type = serve_mime or mime_type or 'image/png'

    resp = make_response(send_file(
        serve_path,
        mimetype=mime_type,
        as_attachment=False,
        download_name=shot.filename or os.path.basename(serve_path),
    ))
    # Cache by URL token; the client receives a unique timestamp query parameter per screenshot.
    resp.headers['Cache-Control'] = 'public, max-age=86400, immutable'
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# Screenshot Gallery API  – date-filtered, paginated
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/api/v2/server/<int:server_id>/screenshots')
@login_required
def api_server_screenshots(server_id):
    """
    Return screenshots for a server, optionally filtered by date.

    Query params:
      date_str  – YYYY-MM-DD  (optional; omit for all)
      page      – 1-based page number  (default 1)
      per_page  – items per page       (default 24)

    Response JSON:
    {
      "success": true,
      "total": 42,
      "dates": ["2026-04-29", "2026-04-28", ...],   # all distinct capture dates
      "screenshots": [
        {
          "id": 1,
          "filename": "screenshot_xxx.png",
          "captured_at": "2026-04-29T10:30:00",
          "captured_date": "2026-04-29",
          "active_user": "sachin",
          "file_size_kb": 256,
          "image_url": "/api/screenshot/1",           # local path OR
          "sharepoint_url": "https://...",             # SharePoint URL (may be null)
          "has_image": true
        }, ...
      ]
    }
    """
    from web.models import Screenshot, Server, db

    # Auth
    server = Server.query.get_or_404(server_id)
    if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
        abort(403)

    date_str  = request.args.get('date_str', '').strip()
    page      = max(1, int(request.args.get('page', 1)))
    per_page  = min(48, max(6, int(request.args.get('per_page', 24))))

    # Build base query
    q = Screenshot.query.filter_by(server_id=server_id)

    if date_str:
        try:
            target = datetime.strptime(date_str, '%Y-%m-%d').date()
            day_start, day_end = _local_day_bounds_utc_naive(target)
            q = q.filter(Screenshot.captured_at >= day_start,
                         Screenshot.captured_at <= day_end)
        except ValueError:
            pass

    q = q.order_by(Screenshot.captured_at.desc())

    total = q.count()
    shots = q.offset((page - 1) * per_page).limit(per_page).all()

    # Distinct dates (for the date filter tabs) – always across ALL screenshots
    all_capture_rows = (
        db.session.query(Screenshot.captured_at)
        .filter(Screenshot.server_id == server_id)
        .order_by(Screenshot.captured_at.desc())
        .all()
    )
    distinct_dates = []
    seen_dates = set()
    for row in all_capture_rows:
        try:
            local_dt = _as_local(row.captured_at)
            if not local_dt:
                continue
            local_date = local_dt.date().isoformat()
            if local_date not in seen_dates:
                distinct_dates.append(local_date)
                seen_dates.add(local_date)
        except Exception as e:
            logger.warning(f"Failed to process screenshot date {row.captured_at}: {e}")
            continue

    result = []
    for s in shots:
        local_path = _resolve_screenshot_local_path(s, update_db=True)
        has_local = bool(local_path)
        ts = int((s.uploaded_at or s.captured_at or datetime.utcnow()).timestamp())
        image_url = url_for('api.api_screenshot_view', screenshot_id=s.id, t=ts) if (has_local or bool(s.sharepoint_url)) else None
        thumb_url = url_for('api.api_screenshot_view', screenshot_id=s.id, size='thumb', t=ts) if image_url else None

        captured_local = _as_local(s.captured_at)
        uploaded_local = _as_local(s.uploaded_at)

        result.append({
            'id':            s.id,
            'filename':      s.filename,
            'captured_at':   s.captured_at.isoformat() if s.captured_at else None,
            'captured_at_local': captured_local.isoformat() if captured_local else None,
            'uploaded_at_local': uploaded_local.isoformat() if uploaded_local else None,
            'captured_date': captured_local.date().isoformat() if captured_local else None,
            'timezone':      str(LOCAL_TZ),
            'active_user':   s.active_user or '',
            'file_size_kb':  s.file_size_kb or 0,
            'sharepoint_url': s.sharepoint_url or None,
            'image_url':     url_for('api.api_screenshot_view', screenshot_id=s.id, t=ts) if (has_local or bool(s.sharepoint_url)) else None,
            'thumb_url':     url_for('api.api_screenshot_view', screenshot_id=s.id, size='thumb', t=ts) if (has_local or bool(s.sharepoint_url)) else None,
            'has_image':     bool(image_url),
        })

    resp = jsonify({
        'success':     True,
        'total':       total,
        'page':        page,
        'per_page':    per_page,
        'dates':       distinct_dates,
        'screenshots': result,
    })
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# Remote Control Operations  –  RDP, Software, Repairs
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/api/v2/server/<int:server_id>/remote/rdp', methods=['POST'])
@login_required
def api_remote_rdp(server_id):
    """Generate RDP connection command for remote desktop access"""
    from web.models import AuditLog, Server, db
    server = Server.query.get_or_404(server_id)
    
    if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
        abort(403)

    audit = AuditLog()
    audit.tenant_id = server.tenant_id
    audit.user = current_user.username
    audit.action = 'REMOTE_ACCESS:RDP'
    audit.resource = f'Server:{server.hostname}'
    audit.details = 'RDP access initiated'
    audit.timestamp = datetime.utcnow()
    audit.status = 'accessed'
    db.session.add(audit)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'hostname': server.hostname,
        'ip_address': server.ip or server.hostname,
        'rdp_command': f'mstsc /v:{server.ip or server.hostname} /admin',
        'message': 'RDP connection initiated'
    })


@api_bp.route('/api/v2/server/<int:server_id>/enable-monitoring', methods=['POST'])
@login_required
def api_enable_monitoring(server_id):
    """
    Dashboard helper: return an install script and download URL for the agent.
    """
    from web.models import db, Server
    server = db.session.get(Server, server_id)
    if not server or (not current_user.is_superadmin and server.tenant_id != current_user.tenant_id):
        abort(403)

    # One-click: download the pre-configured bot bundle and run it as admin.
    download_url = f"/agent/download-bot/{server.id}"
    host = request.host_url.rstrip('/')

    install_script = "\n".join([
        f"# ServerMonitor Agent installer for {server.hostname}",
        f"$Url = \"{host}{download_url}\"",
        "$Out = Join-Path $env:TEMP \"ServerMonitorAgent.zip\"",
        "Write-Host \"Downloading agent bundle...\" -ForegroundColor Cyan",
        "Invoke-WebRequest -Uri $Url -OutFile $Out -TimeoutSec 60",
        "$Dir = Join-Path $env:TEMP \"ServerMonitorAgent\"",
        "if(Test-Path $Dir){ Remove-Item $Dir -Recurse -Force }",
        "Expand-Archive -Path $Out -DestinationPath $Dir -Force",
        "Write-Host \"Launching installer (RunMeAsAdmin.bat)...\" -ForegroundColor Cyan",
        "Start-Process -FilePath (Join-Path $Dir \"RunMeAsAdmin.bat\") -Verb RunAs",
    ])

    return jsonify({
        'success': True,
        'download_url': download_url,
        'install_script': install_script,
        'server_id': server.id,
    })


@api_bp.route('/api/v2/server/<int:server_id>/remote/software', methods=['POST'])
@login_required
def api_remote_software(server_id):
    """Deploy or remove software on remote server"""
    from web.models import AuditLog, db, RemoteCommand, Server

    server = Server.query.get_or_404(server_id)
    if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
        abort(403)

    data = request.get_json() or {}
    action = (data.get('action', 'install') or '').strip().lower()
    software = (data.get('software') or '').strip()

    if not software:
        return jsonify({'error': 'Software name required'}), 400

    if action == 'uninstall':
        software_literal = "'" + software.replace("'", "''") + "'"
        powershell_cmd = f'''
$target = {software_literal}
$paths = @(
  'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',
  'HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*'
)
$app = Get-ItemProperty $paths -ErrorAction SilentlyContinue |
  Where-Object {{ $_.DisplayName -eq $target }} |
  Select-Object -First 1
if (-not $app) {{
  Write-Error "Installed software not found: $target"
  exit 1
}}
$cmd = $app.QuietUninstallString
if (-not $cmd) {{ $cmd = $app.UninstallString }}
if (-not $cmd) {{
  Write-Error "No uninstall command found for: $target"
  exit 1
}}
Write-Host "Running uninstall for $target"
Start-Process -FilePath "cmd.exe" -ArgumentList "/c $cmd" -Wait -NoNewWindow
'''.strip()
    else:
        powershell_cmd = f'choco install {software} -y --allow-empty-checksums'

    remote_cmd = _queue_remote_command(db, RemoteCommand, server_id, powershell_cmd, parameters={
        'action': action,
        'software': software,
        'requested_by': current_user.username
    }, created_by=current_user.username)

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
        'action': action,
        'software': software,
        'message': f'Deployment queued: {action} {software}'
    })


@api_bp.route('/api/v2/server/<int:server_id>/remote/repair', methods=['POST'])
@login_required
def api_remote_repair(server_id):
    """Execute system repair and diagnostics by queuing commands"""
    from web.models import db, Server, RemoteCommand
    import json
    
    server = Server.query.get_or_404(server_id)
    
    if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
        abort(403)
    
    data = request.get_json() or {}
    repair_type = data.get('repair_type', 'sfc')
    
    repair_commands = {
        'sfc': ('Repair-WindowsImage -Online -RestoreHealth', ''),
        'disk_check': ('chkdsk C: /f', ''),
        'windows_update': ('Install-Module PSWindowsUpdate -Force -SkipPublisherCheck; Get-WindowsUpdate -Install -AcceptAll', '')
    }
    
    command_name, params = repair_commands.get(repair_type, ('Get-Volume', {}))
    
    try:
        # Build RemoteCommand via attribute assignment to satisfy static analysis
        cmd = _queue_remote_command(db, RemoteCommand, server_id, command_name, parameters=params or None,
                                    timeout_seconds=600, created_by=current_user.username)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'command_id': cmd.id,
            'repair_type': repair_type,
            'command': command_name,
            'message': f'Repair task queued: {command_name}'
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to queue repair: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/api/v2/server/<int:server_id>/agent/restart', methods=['POST'])
@login_required
def api_agent_restart(server_id):
    """Queue agent restart on target system"""
    from web.models import db, RemoteCommand, Server
    server = Server.query.get_or_404(server_id)
    
    if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
        abort(403)
    
    script = r'''
$svc = Get-Service -Name "ServerMonitorAgent" -ErrorAction SilentlyContinue
if ($svc) {
    Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 2; Restart-Service -Name ServerMonitorAgent -Force"'
    Write-Host "ServerMonitorAgent service restart scheduled"
} else {
    Write-Host "ServerMonitorAgent service not found; exiting current agent process"
    Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 2; Get-Process agent -ErrorAction SilentlyContinue | Stop-Process -Force"'
}
'''.strip()

    try:
        cmd = _queue_remote_command(db, RemoteCommand, server_id, script, timeout_seconds=60,
                                    created_by=current_user.username)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to queue agent restart: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
    return jsonify({
        'success': True,
        'command_id': cmd.id,
        'message': 'Agent restart queued for next heartbeat'
    })


# Software Management  –  GET /api/v2/server/<id>/software-list
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/api/v2/server/<int:server_id>/software-list')
@login_required
def get_server_software_list(server_id):
    """Get list of installed software on a server from the latest metrics"""
    from web.models import Server, Metric
    import json
    
    server = Server.query.get_or_404(server_id)
    if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
        abort(403)
    
    software_list = []
    metrics = Metric.query.filter_by(server_id=server_id)\
        .order_by(Metric.timestamp.desc()).limit(50).all()

    for metric in metrics:
        if not metric.details:
            continue
        try:
            details = json.loads(metric.details) if isinstance(metric.details, str) else metric.details
            candidate = details.get('installed_software', [])
            if candidate:
                software_list = candidate
                break
        except Exception:
            continue
    
    return jsonify({
        'success': True,
        'software_list': software_list,
        'count': len(software_list),
        'message': f'Found {len(software_list)} installed packages'
    })


# Software Upload & Install  –  POST /api/v2/server/<id>/software-upload
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/api/v2/server/<int:server_id>/software-upload', methods=['POST'])
@login_required
def upload_software_package(server_id):
    """Upload and queue installation of a software package or executable"""
    from web.models import db, Server, RemoteCommand, AuditLog
    import os
    
    server = Server.query.get_or_404(server_id)
    if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
        abort(403)
    
    # Check for file in request
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['file']
    filename = file.filename or ''
    if not filename:
        return jsonify({'success': False, 'error': 'No file selected'}), 400
    
    # Validate file extension
    allowed_extensions = {'exe', 'msi', 'zip', 'ps1'}
    if '.' not in filename or filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
        return jsonify({
            'success': False,
            'error': f'Only {", ".join(allowed_extensions)} files allowed'
        }), 400
    
    try:
        # Create uploads directory if it doesn't exist
        upload_dir = os.path.join(os.path.dirname(__file__), '../../uploads')
        os.makedirs(upload_dir, exist_ok=True)
        
        # Save file with unique name
        from werkzeug.utils import secure_filename
        safe_filename = secure_filename(filename) or 'upload'
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        saved_filename = f"{timestamp}_{safe_filename}"
        file_path = os.path.join(upload_dir, saved_filename)
        
        file.save(file_path)
        file_size = os.path.getsize(file_path)
        file_url = f"{request.host_url.rstrip('/')}/api/v2/server/{server_id}/software-download/{saved_filename}"
        
        # Build PowerShell command to download and execute
        powershell_cmd = f'''
$ProgressPreference = 'SilentlyContinue'
$url = '{file_url}'
$outPath = "$env:TEMP\\{saved_filename}"
Invoke-WebRequest -Uri $url -OutFile $outPath -ErrorAction Stop

if ($outPath -match '\\.exe$') {{
    & $outPath /S /D=C:\\Program Files\\{os.path.splitext(filename)[0]}
}} elseif ($outPath -match '\\.msi$') {{
    msiexec /i $outPath /quiet /norestart
}} elseif ($outPath -match '\\.ps1$') {{
    & $outPath
}} elseif ($outPath -match '\\.zip$') {{
    Expand-Archive -Path $outPath -DestinationPath "$env:TEMP\\{os.path.splitext(filename)[0]}"
}}

Remove-Item $outPath -Force
Write-Host "Installation completed"
'''.strip()
        
        # Queue the command
        cmd = _queue_remote_command(db, RemoteCommand, server_id, powershell_cmd, parameters={
            'file': saved_filename,
            'size': file_size,
            'uploaded_by': current_user.username
        }, timeout_seconds=600, created_by=current_user.username)
        
        # Audit log
        audit = AuditLog()
        audit.tenant_id = current_user.tenant_id
        audit.user = current_user.username
        audit.action = 'DEPLOY_SOFTWARE:upload'
        audit.resource = f'Server:{server.hostname}'
        audit.details = f'Uploaded {filename} ({file_size} bytes)'
        audit.timestamp = datetime.utcnow()
        audit.status = 'pending'
        db.session.add(audit)
        db.session.commit()
        
        logger.info(f"Software package uploaded: {filename} ({file_size} bytes) for server {server_id}")
        
        return jsonify({
            'success': True,
            'command_id': cmd.id,
            'filename': filename,
            'size': file_size,
            'message': f'Installation queued for {filename}'
        }), 201
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to upload software: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# Software Download  –  GET /api/v2/server/<id>/software-download/<filename>
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/api/v2/server/<int:server_id>/software-download/<filename>')
def download_software_package(server_id, filename):
    """Download a previously uploaded software package (for agent to download)"""
    from web.models import Server
    import os
    
    _server = Server.query.get_or_404(server_id)  # Verify server exists for auth check
    
    try:
        upload_dir = os.path.join(os.path.dirname(__file__), '../../uploads')
        file_path = os.path.join(upload_dir, filename)
        
        # Security: Ensure file is within upload directory
        if not os.path.abspath(file_path).startswith(os.path.abspath(upload_dir)):
            abort(403)
        
        if not os.path.exists(file_path):
            abort(404)
        
        return send_file(file_path, as_attachment=True)
    
    except Exception as e:
        logger.error(f"Failed to download software: {e}")
        abort(500)

# ─────────────────────────────────────────────────────────────────────────────
# Agent Metrics Intake  –  POST /api/v2/agent/metrics
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/api/v2/agent/metrics', methods=['POST'])
def agent_metrics():
    """
    Receive metrics from an agent.

    Agent identifies itself with the `api_key` field (matches Server.api_key).
    If no server matches that key we fall back to hostname-based lookup for the
    demo_mode_key case so local testing still works.

    Expected JSON body (all optional except api_key):
    {
      "api_key":       "...",
      "hostname":      "BFS-sachin",
      "ip":            "192.168.x.x",
      "os_info":       "Windows 10",
      "logged_in_user": "sachin",
      "metrics": {
        "cpu_percent":    45.2,
        "ram_percent":    62.1,
        "total_ram_gb":   16,
        "used_ram_gb":    10,
        "disk_percent":   55,
        "total_disk_gb":  512,
        "used_disk_gb":   280,
        // extended fields from the improved agent:
        "cpu_util_percent": ...,
        "ram_util_percent": ...,
        "disk_util_percent": ...,
        ...
      },
      "screenshot": {          // optional
        "success": true,
        "image":   "<base64>",
        "format":  "jpeg"
      }
    }
    """
    from web.models import db, Server, Metric, Screenshot, EmployeeActivity, EmployeeDeviceAssignment
    import traceback

    logger.info("📥 Metrics endpoint called")
    
    try:
        data = request.get_json(silent=True) or {}
        logger.info(f"Received payload keys: {list(data.keys())}")
        
        api_key  = data.get('api_key') or data.get('agent_key', '')
        hostname = (data.get('hostname') or '').strip()
        ip       = data.get('ip', '')
        os_info  = data.get('os_info', '')
        logged_in_user = data.get('logged_in_user', '')
        idle_time_seconds = float(data.get('idle_time_seconds', data.get('idle_time', 0)) or 0)
        activity_payload = data.get('activity') or {}
        active_app = (activity_payload.get('app') or data.get('active_app') or '').strip()
        window_title = (activity_payload.get('window_title') or data.get('window_title') or '').strip()
        browser_url = (activity_payload.get('browser_url') or activity_payload.get('url') or data.get('browser_url') or '').strip()

        logger.info(f"Parsed: user={logged_in_user}, app={active_app}, idle={idle_time_seconds}")
        
        # ── Resolve the Server record ──────────────────────────────────────────
        server = None

        # 1) Match by api_key first (production path)
        if api_key and api_key != 'demo_mode_key':
            server = Server.query.filter_by(api_key=api_key).first()

        # 2) Fallback: match by hostname within any tenant (dev/demo path)
        if server is None and hostname:
            server = Server.query.filter_by(hostname=hostname).first()

        # 3) Auto-create server for demo_mode_key so local dev works out of the box
        if server is None and hostname:
            from web.models import Tenant
            import secrets as _secrets
            tenant = Tenant.query.first()
            if tenant:
                server = Server()
                server.hostname   = hostname
                server.name       = hostname
                server.tenant_id  = tenant.id
                server.api_key    = api_key if (api_key and api_key != 'demo_mode_key') else _secrets.token_hex(32)
                server.source     = 'agent'
                server.type       = 'agent'
                server.agent_installed = True
                # Ensure screenshots and remote-control defaults are enabled for newly auto-created servers
                try:
                    server.screenshot_enabled = True
                    server.screenshot_interval_minutes = 10
                except Exception:
                    pass
                db.session.add(server)
                logger.info(f"Auto-created server record for hostname={hostname}")

        if server is None:
            logger.warning(f"Server not found for hostname={hostname}, api_key={api_key}")
            return jsonify({'success': False, 'error': 'Unknown agent. Register the server first.'}), 404

        # ── Check Tenant Subscription Status ──────────────────────────────
        # Verify Tenant subscription status safely
        tenant_status = 'active'
        if getattr(server, 'tenant', None):
            tenant_status = server.tenant.status or 'active'  # type: ignore
            
        if tenant_status != 'active':
            return jsonify({'success': False, 'error': f'Tenant subscription is {tenant_status}. Telemetry rejected.'}), 403

        # ── Update server heartbeat & metadata ────────────────────────────
        now = datetime.utcnow()
        prev_status = getattr(server, 'status', None)
        server.last_seen = now
        server.status    = 'online'
        server.agent_installed  = True
        server.monitoring_active = True
        if ip:
            server.ip = ip
        if os_info:
            server.os_info = os_info

        try:
            _retry_db_flush(db)
        except OperationalError as exc:
            logger.error(f"Agent metrics failed due to locked database during flush: {exc}")
            return jsonify({'success': False, 'error': 'Database is busy. Try again shortly.'}), 503
        
        # ── Identity Correlation Engine ───────────────────────────────────
        if logged_in_user:
            try:
                existing_assignment = EmployeeDeviceAssignment.query.filter_by(
                    tenant_id=server.tenant_id,
                    server_id=server.id,
                    is_active=True
                ).first()
                if not existing_assignment:
                    from core.identity_correlation import IdentityCorrelationService
                    serial_number = data.get('serial_number') or ''
                    IdentityCorrelationService.correlate_agent_payload(
                        tenant_id=server.tenant_id,
                        server_id=server.id,
                        hostname=hostname,
                        serial_number=serial_number,
                        logged_in_user=logged_in_user
                    )
            except Exception as e:
                logger.error(f"Identity correlation failed: {str(e)}")

        # ── Store Metric row ──────────────────────────────────────────────
        metrics_raw = data.get('metrics') or {}

        cpu  = float(metrics_raw.get('cpu_percent')    or metrics_raw.get('cpu_util_percent')  or metrics_raw.get('cpu')  or 0)
        ram  = float(metrics_raw.get('ram_percent')    or metrics_raw.get('ram_util_percent')  or metrics_raw.get('ram')  or 0)
        disk = float(metrics_raw.get('disk_percent')   or metrics_raw.get('disk_util_percent') or metrics_raw.get('disk') or 0)

        metric = Metric()
        metric.server_id         = server.id
        metric.timestamp         = now
        metric.cpu               = cpu
        metric.ram               = ram
        metric.disk              = disk
        metric.cpu_util_percent  = cpu
        metric.ram_util_percent  = ram
        metric.ssd_util_percent  = disk
        metric.total_ram_gb      = float(metrics_raw.get('total_ram_gb', 0) or 0)
        metric.used_ram_gb       = float(metrics_raw.get('used_ram_gb',  0) or 0)
        metric.available_ram_gb  = float(metrics_raw.get('ram_available_gb', 0) or 0)
        metric.total_ssd_gb      = float(metrics_raw.get('total_disk_gb', 0) or 0)
        metric.used_ssd_gb       = float(metrics_raw.get('used_disk_gb',  0) or 0)
        
        # Store activity and other details as JSON
        details_obj = {
            'active_app': active_app,
            'window_title': window_title,
            'browser_url': browser_url,
            'idle_time_seconds': int(max(0, idle_time_seconds)),
            'logged_in_user': logged_in_user,
        }
        # Include installed_software if provided
        if 'installed_software' in (data.get('details') or {}):
            details_obj['installed_software'] = data['details']['installed_software']
        
        metric.details = json.dumps(details_obj)
        db.session.add(metric)
        logger.info("Metric row created, added to session")

        # ── Employee activity (logged_in_user) ────────────────────────────────
        if logged_in_user:
            activity = EmployeeActivity()
            activity.tenant_id = server.tenant_id
            activity.server_id = server.id
            activity.user      = logged_in_user
            activity.timestamp = now
            activity.idle_time = int(max(0, idle_time_seconds))
            activity.app = active_app or None
            if browser_url and window_title:
                activity.window_title = f"{window_title} | {browser_url}"
            elif browser_url:
                activity.window_title = browser_url
            else:
                activity.window_title = window_title or None
            
            # Try to link to employee if identity correlation has been done
            try:
                assignment = EmployeeDeviceAssignment.query.filter_by(
                    tenant_id=server.tenant_id,
                    server_id=server.id,
                    is_active=True
                ).first()
                if assignment and assignment.employee_id:
                    activity.employee_id = assignment.employee_id
                    logger.debug(f"Activity linked to employee {assignment.employee_id}")
            except Exception as e:
                logger.debug(f"Could not link activity to employee: {e}")
            
            db.session.add(activity)
            logger.info(f"Employee activity added: user={logged_in_user}, tenant_id={server.tenant_id}")

            # Commit activity before calling ProductivityEngine to avoid database locks
            try:
                _retry_db_commit(db)
                logger.info("Activity committed")
            except Exception as commit_err:
                logger.warning(f"Failed to commit employee activity: {commit_err}")

            # ── Phase 6: Detailed Productivity Engine (Relational Models) ────────
            try:
                from core.productivity_engine import ProductivityEngine
                ProductivityEngine.process_agent_activity(
                    tenant_id=server.tenant_id,
                    server_id=server.id,
                    logged_in_user=logged_in_user,
                    active_app=active_app,
                    window_title=window_title,
                    browser_url=browser_url,
                    idle_time_seconds=int(max(0, idle_time_seconds)),
                    timestamp=now
                )
                logger.info("ProductivityEngine processed successfully")
            except Exception as e:
                logger.error(f"Failed to process detailed productivity metrics: {str(e)}")
                logger.error(traceback.format_exc())

        # ── Screenshot (base64 inline, save to disk) ───────────────────────────
        ss_data = data.get('screenshot')
        screenshot_enabled = server.screenshot_enabled
        screenshot_interval_minutes = server.screenshot_interval_minutes or 10

        ss_image_b64 = None
        if ss_data and ss_data.get('success') and ss_data.get('image'):
            logger.info(f"[DEBUG] Processing screenshot from server {server.id} ({hostname}): success={ss_data.get('success')}, image_len={len(ss_data.get('image', ''))}")
            try:
                import base64 as _b64
                import os as _os

                ss_image_b64 = ss_data.get('image')
                img_bytes = _b64.b64decode(ss_image_b64, validate=True)
                if len(img_bytes) < 100:
                    # Log more context for tiny/invalid payloads to help troubleshooting
                    logger.warning(f"Tiny/invalid screenshot payload from server {server.id} ({hostname}) - decoded size={len(img_bytes)} bytes")
                    raise ValueError("Screenshot payload decoded to an empty or invalid image")
                ext       = 'jpg' if ss_data.get('format', 'jpeg') == 'jpeg' else ss_data.get('format', 'png')
                ts_str    = now.strftime('%Y%m%d_%H%M%S')
                fname     = f"screenshot_{server.id}_{hostname}_{ts_str}.{ext}"

                # Save next to the database in a screenshots sub-folder
                # Use Flask app root (ServerMonitor) as base and join data/screenshots
                from web.app import app as flask_app
                app_root = _os.path.dirname(flask_app.root_path)  # web -> ServerMonitor
                base_dir = _os.path.join(app_root, 'data', 'screenshots')
                _os.makedirs(base_dir, exist_ok=True)
                file_path = _os.path.join(base_dir, fname)
                file_path = _os.path.abspath(file_path)  # Normalize the path

                with open(file_path, 'wb') as f:
                    f.write(img_bytes)

                shot = Screenshot()
                shot.server_id      = server.id
                shot.tenant_id      = server.tenant_id
                shot.filename       = fname
                shot.hostname       = hostname
                shot.captured_at    = now
                shot.uploaded_at    = now
                shot.uploaded       = False
                shot.file_size_kb   = len(img_bytes) // 1024
                shot.active_user    = logged_in_user or ''
                shot.os_info        = os_info
                shot.ip_address     = ip
                shot.local_file_path = file_path
                db.session.add(shot)
                logger.info(f"Screenshot saved: {file_path}")
            except Exception as e:
                logger.error(f"Failed to save screenshot: {e}")

        # Emit screenshot frame over SocketIO for live preview (non-persistent stream)
        if ss_image_b64:
            try:
                from web.app import socketio as socketio_instance
                sio = cast(Any, socketio_instance)

                def _emit_screenshot_frame(b64data, shot_obj_id=None):
                    try:
                        payload = {
                            'server_id': server.id,
                            'timestamp': now.isoformat() + 'Z',
                            'image_b64': b64data,
                            'screenshot_id': shot_obj_id
                        }
                        logger.info(f"[DEBUG] Emitting screenshot_frame to room={server.tenant_id} for server_id={server.id}, b64_size={len(b64data)} bytes")
                        sio.emit('screenshot_frame', payload, room=str(server.tenant_id))
                        logger.info(f"[DEBUG] Screenshot_frame emitted successfully for server {server.id}")
                    except Exception as e:
                        logger.error(f"SocketIO screenshot emit failed for server {server.id}: {e}", exc_info=True)

                logger.info(f"[DEBUG] Starting screenshot emit background task for server {server.id} to tenant {server.tenant_id}")
                try:
                    socketio_instance.start_background_task(_emit_screenshot_frame, ss_image_b64, None)
                except Exception as e:
                    logger.error(f"Failed to start screenshot_frame background task for server {server.id}: {e}", exc_info=True)
            except Exception as e:
                logger.warning(f"SocketIO is unavailable for screenshot emit: {e}")

        logger.info("About to commit final transaction")
        try:
            _retry_db_commit(db)
            logger.info("Final commit successful")
        except OperationalError as exc:
            logger.error(f"Agent metrics failed due to locked database during commit: {exc}")
            return jsonify({'success': False, 'error': 'Database is busy. Try again shortly.'}), 503

        # Extract values before background thread to avoid SQLAlchemy session issues
        server_id = server.id
        tenant_id = server.tenant_id
        try:
            # Notify UI if server just transitioned to online
            if prev_status != 'online':
                try:
                    create_notification(tenant_id, 'alert', f"System online: {server.hostname}",
                                        f"Agent reported for system {server.hostname} (ID {server.id})", {'server_id': server.id})
                except Exception:
                    pass
        except Exception:
            pass
        
        # ── Emit real-time update via Socket.IO in a background task ──────────────
        def _emit_metrics_update():
            try:
                from web.app import socketio as socketio_instance
                cast(Any, socketio_instance).emit('metrics_update', {
                    'server_id': server_id,
                    'timestamp': now.isoformat() + 'Z',
                    'metrics':   {'cpu': cpu, 'ram': ram, 'disk': disk},
                }, room=str(tenant_id))
            except Exception as e:
                logger.error(f"SocketIO emit failed: {e}")

        try:
            from web.app import socketio as socketio_instance
            socketio_instance.start_background_task(_emit_metrics_update)
        except Exception as e:
            logger.warning(f"SocketIO background task skipped: {e}")

        logger.info("Metrics endpoint returning success")
        return jsonify({
            'success':                    True,
            'server_id':                  server_id,
            'screenshot_enabled':         screenshot_enabled,
            'screenshot_interval_minutes': screenshot_interval_minutes,
        })

    except Exception as e:
        error_msg = str(e)
        error_trace = traceback.format_exc()
        logger.error(f"❌ Metrics endpoint error: {error_msg}")
        logger.error(error_trace)
        return jsonify({
            'success': False, 
            'error': error_msg,
            'type': type(e).__name__,
            'traceback': error_trace
        }), 500


# ─────────────────────────────────────────────────────────────────────────────
# Agent Command Poll  –  GET /api/v2/agent/commands
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/api/v2/agent/commands', methods=['GET'])
def agent_poll_commands():
    """Return pending commands for an agent identified by hostname header."""
    from web.models import db, Server, RemoteCommand

    hostname = request.headers.get('X-Hostname', '').strip()
    api_key  = request.headers.get('X-Agent-Key', '').strip()

    server = None
    if api_key and api_key != 'demo_mode_key':
        server = Server.query.filter_by(api_key=api_key).first()
    if server is None and hostname:
        server = Server.query.filter_by(hostname=hostname).first()

    if server is None:
        return jsonify([])

    pending = RemoteCommand.query.filter_by(
        server_id=server.id, status='pending'
    ).order_by(RemoteCommand.created_at.asc()).limit(5).all()

    if pending:
        for c in pending:
            c.status = 'sent'
        db.session.commit()

        try:
            from web.app import socketio
            for c in pending:
                cast(Any, socketio).emit('command_started', {
                    'command_id': c.id,
                    'server_id': server.id,
                    'command': c.command[:100],
                    'status': 'sent'
                }, broadcast=True)
        except Exception as e:
            logger.warning(f"WebSocket command_started skipped: {e}")

    return jsonify([
        {
            'command_id': c.id,
            'command':    c.command,
            'parameters': c.parameters or '',
            'timeout_seconds': c.timeout_seconds or 120,
        }
        for c in pending
    ])


# ─────────────────────────────────────────────────────────────────────────────
# Agent Command Result  –  POST /api/v2/agent/commands/result
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/api/v2/agent/commands/result', methods=['POST'])
def agent_command_result():
    """Accept execution result for a previously dispatched command and broadcast via WebSocket."""
    from web.models import db, RemoteCommand

    data       = request.get_json(silent=True) or {}
    command_id = data.get('command_id')
    output     = data.get('output', '')
    error_output = data.get('error_output', '')
    exit_code  = data.get('exit_code')
    status     = data.get('status', 'completed')

    if not command_id:
        return jsonify({'success': False, 'error': 'command_id required'}), 400

    cmd = db.session.get(RemoteCommand, command_id)
    if not cmd:
        return jsonify({'success': False, 'error': 'Command not found'}), 404

    cmd.status      = status
    cmd.output      = output
    cmd.error_output = error_output
    if exit_code is not None:
        try:
            cmd.exit_code = int(exit_code)
        except (TypeError, ValueError):
            cmd.exit_code = None
    cmd.executed_at = datetime.utcnow()
    cmd.completed_at = datetime.utcnow()
    db.session.commit()

    event_status = 'success' if status == 'completed' else status

    # BROADCAST via WebSocket to portal UI
    try:
        from web.app import socketio
        cast(Any, socketio).emit('command_result', {
            'command_id': cmd.id,
            'server_id': cmd.server_id,
            'command': cmd.command[:100],
            'status': event_status,
            'output': output,
            'error_output': error_output,
            'executed_at': cmd.executed_at.isoformat() if cmd.executed_at else None,
            'exit_code': cmd.exit_code
        }, broadcast=True)
        logger.info(f"✅ WebSocket: command {command_id} → {status}")
    except Exception as e:
        logger.warning(f"WebSocket broadcast skipped: {e}")

    return jsonify({'success': True})


# ─────────────────────────────────────────────────────────────────────────────
# Metrics History  –  GET /api/v2/metrics/history
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/api/v2/metrics/history', methods=['GET'])
@login_required
def api_metrics_history():
    from web.models import db, Metric, Server
    
    server_id = request.args.get('server_id', type=int)
    time_range = request.args.get('range', '24h')
    limit = request.args.get('limit', 240, type=int)
    
    if not server_id:
        return jsonify({'error': 'server_id required'}), 400
        
    server = db.session.get(Server, server_id)
    if not server or (not current_user.is_superadmin and server.tenant_id != current_user.tenant_id):
        return jsonify({'error': 'Unauthorized'}), 403
        
    now = datetime.utcnow()
    if time_range == '1h':
        start_time = now - timedelta(hours=1)
    elif time_range == '6h':
        start_time = now - timedelta(hours=6)
    elif time_range == '7d':
        start_time = now - timedelta(days=7)
    else:  # 24h default
        start_time = now - timedelta(hours=24)
        
    metrics = Metric.query.filter(
        Metric.server_id == server_id,
        Metric.timestamp >= start_time
    ).order_by(Metric.timestamp.desc()).limit(limit).all()
    
    # Reverse so they are chronological
    metrics = list(reversed(metrics))
    
    result = []
    for m in metrics:
        result.append({
            'timestamp': m.timestamp.isoformat() + 'Z',
            'cpu_util_percent': m.cpu_util_percent or m.cpu,
            'ram_util_percent': m.ram_util_percent or m.ram,
            'disk_util_percent': getattr(m, 'ssd_util_percent', None) or getattr(m, 'disk', 0)
        })
        
    return jsonify(result)


# ─────────────────────────────────────────────────────────────────────────────
# Employee Productivity Report – GET /api/v2/employee/productivity
# Supports JSON and CSV output. Filters: user (OS username), start (YYYY-MM-DD), end (YYYY-MM-DD)
# Returns daily aggregates: date, user, records, avg_idle_seconds, top_app
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/api/v2/employee/productivity', methods=['GET'])
@login_required
def api_employee_productivity():
    from web.models import EmployeeActivity, Server
    import csv
    import io

    user = (request.args.get('user') or '').strip()
    start_str = (request.args.get('start') or '').strip()
    end_str = (request.args.get('end') or '').strip()
    out_fmt = (request.args.get('format') or 'json').lower()

    q = EmployeeActivity.query

    # Restrict by tenant for non-superadmins by joining Server
    if not current_user.is_superadmin:
        q = q.join(Server, EmployeeActivity.server_id == Server.id).filter(Server.tenant_id == current_user.tenant_id)

    if user:
        q = q.filter(EmployeeActivity.user == user)

    try:
        if start_str:
            start_dt = datetime.fromisoformat(start_str + 'T00:00:00')
            q = q.filter(EmployeeActivity.timestamp >= start_dt)
        if end_str:
            end_dt = datetime.fromisoformat(end_str + 'T23:59:59')
            q = q.filter(EmployeeActivity.timestamp <= end_dt)
    except Exception:
        return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400

    rows = q.order_by(EmployeeActivity.timestamp.asc()).all()

    # Aggregate per-day + per-user
    agg = {}
    for r in rows:
        day = r.timestamp.date().isoformat()
        key = (day, r.user or '')
        if key not in agg:
            agg[key] = {'date': day, 'user': r.user or '', 'records': 0, 'active_records': 0, 'idle_sum': 0.0, 'apps': {}}
        rec = agg[key]
        rec['records'] += 1
        rec['idle_sum'] += float(r.idle_time or 0)
        if float(r.idle_time or 0) < 60:
            rec['active_records'] += 1
        app = (r.app or 'Unknown')[:200]
        rec['apps'][app] = rec['apps'].get(app, 0) + 1

    result = []
    for (day, user), v in sorted(agg.items(), key=lambda x: (x[0][0], x[0][1])):
        top_app = ''
        if v['apps']:
            top_app = max(v['apps'].items(), key=lambda kv: kv[1])[0]
        avg_idle = (v['idle_sum'] / v['records']) if v['records'] else 0
        result.append({
            'date': v['date'],
            'user': v['user'],
            'records': v['records'],
            'active_records': v['active_records'],
            'avg_idle_seconds': round(avg_idle, 1),
            'top_app': top_app,
            'apps_breakdown': v['apps']
        })

    if out_fmt == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['date', 'user', 'records', 'active_records', 'avg_idle_seconds', 'top_app'])
        for r in result:
            writer.writerow([r['date'], r['user'], r['records'], r['active_records'], r['avg_idle_seconds'], r['top_app']])
        resp = make_response(output.getvalue())
        resp.headers['Content-Type'] = 'text/csv'
        resp.headers['Content-Disposition'] = 'attachment; filename="employee_productivity.csv"'
        return resp

    return jsonify({'success': True, 'rows': result})


# ─────────────────────────────────────────────────────────────────────────────
# Latest Server Metrics  –  GET /api/v2/server/<id>/metrics/latest
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/api/v2/server/<int:server_id>/metrics/latest', methods=['GET'])
@login_required
def api_server_metrics_latest(server_id):
    """Return the latest metrics for a specific server (for live dashboard polling)."""
    from web.models import db, Metric, Server
    
    server = db.session.get(Server, server_id)
    if not server or (not current_user.is_superadmin and server.tenant_id != current_user.tenant_id):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        # Get the most recent metric
        metric = Metric.query.filter_by(server_id=server_id).order_by(
            Metric.timestamp.desc()
        ).first()
        
        if not metric:
            return jsonify({
                'success': True,
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'cpu': 0,
                'ram': 0,
                'disk': 0,
                'no_data': True
            })
        
        return jsonify({
            'success': True,
            'timestamp': metric.timestamp.isoformat() + 'Z',
            'cpu': round(float(metric.cpu_util_percent or metric.cpu or 0), 1),
            'ram': round(float(metric.ram_util_percent or metric.ram or 0), 1),
            'disk': round(float(getattr(metric, 'ssd_util_percent', None) or getattr(metric, 'disk', 0)), 1)
        })
    except Exception as e:
        logger.error(f"Failed to fetch latest metrics for server {server_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# AI Forecast Dummy  –  GET /api/v2/server/<id>/forecast
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/api/v2/server/<int:server_id>/forecast', methods=['GET'])
@login_required
def api_server_forecast(server_id):
    from web.models import db, Metric, Server
    
    try:
        server = db.session.get(Server, server_id)
        if not server or (not current_user.is_superadmin and server.tenant_id != current_user.tenant_id):
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
            
        # Advanced forecasting using linear regression
        metrics = Metric.query.filter_by(server_id=server_id).order_by(Metric.timestamp.desc()).limit(60).all()
        if len(metrics) < 10:
            return jsonify({
                'success': False, 
                'message': 'Insufficient historical data for forecasting. Currently learning patterns...'
            }), 200
            
        cpu_vals = [m.cpu_util_percent or getattr(m, 'cpu', 0) or 0 for m in metrics]
        ram_vals = [m.ram_util_percent or getattr(m, 'ram', 0) or 0 for m in metrics]
        
        # Reverse to chronologically ascending for trend calculation
        cpu_vals.reverse()
        ram_vals.reverse()

        def calculate_trend(values):
            n = len(values)
            if n < 2: return 0
            sum_x = sum(range(n))
            sum_y = sum(values)
            sum_x2 = sum(i*i for i in range(n))
            sum_xy = sum(i*values[i] for i in range(n))
            
            denominator = (n * sum_x2 - sum_x**2)
            if denominator == 0: return 0
            return (n * sum_xy - sum_x * sum_y) / denominator
            
        cpu_slope = calculate_trend(cpu_vals)
        ram_slope = calculate_trend(ram_vals)
        
        # Determine trend categories
        def get_trend_category(slope, current_val):
            if slope > 0.5: return 'Critical Spike' if current_val > 80 else 'Sharply Up'
            elif slope > 0.1: return 'Upward'
            elif slope < -0.5: return 'Dropping'
            elif slope < -0.1: return 'Downward'
            else: return 'Stable'
            
        cpu_trend = get_trend_category(cpu_slope, cpu_vals[-1])
        ram_trend = get_trend_category(ram_slope, ram_vals[-1])
        
        # Construct recommendations based on trends
        recommendations = []
        if cpu_slope > 0.2 and cpu_vals[-1] > 80:
            recommendations.append("CPU usage is high and rising; consider load balancing or scaling up.")
        elif cpu_slope > 0.5:
            recommendations.append("CPU usage is spiking rapidly. Investigate background processes.")
            
        if ram_slope > 0.2 and ram_vals[-1] > 80:
            recommendations.append("Memory is near capacity and trending upwards. Potential memory leak or high load.")
            
        if not recommendations:
            if cpu_trend == 'Stable' and ram_trend == 'Stable':
                recommendations.append("System resources are stable. No action required.")
            else:
                recommendations.append("Trends detected, but within safe operational thresholds.")
                
        recommendation_text = " ".join(recommendations)
        
        return jsonify({
            'success': True,
            'message': 'AI Predictive Analysis complete',
            'recommendation': recommendation_text,
            'cpu': {'trend': cpu_trend, 'slope': round(cpu_slope, 4)},
            'ram': {'trend': ram_trend, 'slope': round(ram_slope, 4)}
        }), 200
    except Exception as e:
        logger.error(f"Error in forecast endpoint for server {server_id}: {e}")
        return jsonify({
            'success': False,
            'message': 'Forecast service unavailable'
        }), 500


# ─────────────────────────────────────────────────────────────────────────────
# Server Alerts API  –  GET /api/v2/server/<id>/alerts
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/api/v2/server/<int:server_id>/alerts', methods=['GET'])
@login_required
def api_server_alerts(server_id):
    """Return active alert count for a specific server."""
    from web.models import db, Server, SystemAlert
    
    server = db.session.get(Server, server_id)
    if not server or (not current_user.is_superadmin and server.tenant_id != current_user.tenant_id):
        return jsonify({'error': 'Unauthorized'}), 403
        
    try:
        active_alerts_count = db.session.query(SystemAlert).filter_by(
            server_id=server_id,
            is_active=True
        ).count()
        
        return jsonify({
            'success': True,
            'alert_count': active_alerts_count
        })
    except Exception as e:
        logger.error(f"Failed to fetch alerts for server {server_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# Screenshot Configuration  –  POST /api/v2/server/<id>/screenshots/config
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/api/v2/server/<int:server_id>/screenshots/config', methods=['POST'])
@login_required
def api_screenshot_config(server_id):
    """Update screenshot configuration for a server"""
    from web.models import db, Server
    
    server = Server.query.get_or_404(server_id)
    
    if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
        abort(403)
    
    data = request.get_json() or {}
    enabled_raw = data.get('enabled', data.get('screenshot_enabled', False))
    if isinstance(enabled_raw, str):
        enabled = enabled_raw.strip().lower() in ('1', 'true', 'yes', 'on')
    else:
        enabled = bool(enabled_raw)
    interval = data.get('interval', data.get('screenshot_interval_minutes', 10))
    
    try:
        try:
            interval = int(interval)
        except (TypeError, ValueError):
            interval = 10

        # Validate interval
        if interval < 5:
            interval = 5
        if interval > 1440:
            interval = 1440  # Max 24 hours
        
        server.screenshot_enabled = enabled
        server.screenshot_interval_minutes = interval
        db.session.commit()
        
        return jsonify({
            'success': True,
            'enabled': enabled,
            'interval': interval,
            'message': 'Screenshot configuration updated'
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update screenshot config: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# Terminal Command Execution  –  POST /api/v2/server/<id>/terminal/command
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/api/v2/server/<int:server_id>/terminal/command', methods=['POST'])
@login_required
def api_terminal_command(server_id):
    """Queue a terminal command to be executed by the agent"""
    from web.models import db, Server, RemoteCommand
    
    server = Server.query.get_or_404(server_id)
    
    if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
        abort(403)
    
    data = request.get_json() or {}
    command = data.get('command', '').strip()
    
    if not command:
        return jsonify({'success': False, 'error': 'Command cannot be empty'}), 400
    
    try:
        # Queue the command directly — agent will run it in PowerShell as-is
        cmd = _queue_remote_command(db, RemoteCommand, server_id, command, timeout_seconds=120,
                                    created_by=current_user.username)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'command_id': cmd.id,
            'command': command,
            'message': 'Command queued for execution'
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to queue terminal command: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# Get Command Status  –  GET /api/v2/commands/<id>
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/api/v2/commands/<int:command_id>')
@login_required
def api_get_command_status(command_id):
    """Get the status and output of a queued command"""
    from web.models import RemoteCommand
    
    cmd = RemoteCommand.query.get_or_404(command_id)
    
    # Authorization check
    if not current_user.is_superadmin and cmd.server.tenant_id != current_user.tenant_id:
        abort(403)
    
    return jsonify({
        'success': True,
        'id': cmd.id,
        'status': cmd.status,
        'command': cmd.command,
        'output': cmd.output or '',
        'error_output': cmd.error_output or '',
        'exit_code': cmd.exit_code,
        'created_at': cmd.created_at.isoformat() if cmd.created_at else None,
        'executed_at': cmd.executed_at.isoformat() if cmd.executed_at else None,
        'completed_at': cmd.completed_at.isoformat() if cmd.completed_at else None
    })


# Queue Terminal Command  –  POST /api/v2/commands
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/api/v2/commands', methods=['POST'])
@login_required
def api_queue_terminal_command():
    """Queue a terminal command for execution on a server"""
    from web.models import db, Server, RemoteCommand
    
    data = request.get_json() or {}
    server_id = data.get('server_id')
    command = data.get('command', '').strip()
    timeout = data.get('timeout', 120)
    
    if not server_id or not command:
        return jsonify({
            'success': False,
            'error': 'Missing server_id or command'
        }), 400
    
    # Get server and check authorization
    server = Server.query.get_or_404(server_id)
    if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
        abort(403)
    
    try:
        # Create and queue the command
        cmd = _queue_remote_command(db, RemoteCommand, server_id, command, timeout_seconds=timeout,
                                    created_by=current_user.username)
        db.session.commit()
        
        logger.info(f"Queued terminal command {cmd.id} on server {server_id}: {command[:100]}")
        
        return jsonify({
            'success': True,
            'command_id': cmd.id,
            'command': command,
            'message': 'Command queued successfully'
        }), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to queue command: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# Historical metrics endpoint for charting
@api_bp.route('/api/v2/server/<int:server_id>/metrics/history')
@login_required
def api_server_metrics_history(server_id):
    """Return recent metric points for a server (used by dashboard charts)."""
    try:
        from web.models import Metric, Server

        server = Server.query.get_or_404(server_id)
        if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
            abort(403)

        # Query the latest N metrics for this server
        limit = int(request.args.get('limit', 120))
        metrics = Metric.query.filter_by(server_id=server_id).order_by(Metric.timestamp.desc()).limit(limit).all()

        # Reverse to chronological order
        metrics = list(reversed(metrics))

        data = {
            'success': True,
            'server_id': server_id,
            'points': [
                {
                    'timestamp': m.timestamp.isoformat(),
                    'cpu': m.cpu,
                    'ram': m.ram,
                    'disk': m.disk
                } for m in metrics
            ]
        }
        return jsonify(data), 200
    except Exception as e:
        logger.error(f"Failed to fetch metrics history: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ─────────────────────────────────────────────────────────────────────────────
# Azure AD Inventory Sync  –  POST /api/v2/inventory/sync
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/api/v2/inventory/sync', methods=['POST'])
@login_required
def api_inventory_sync():
    """Manually trigger Azure AD device inventory sync for the current tenant"""
    from web.models import Tenant, AzureDevice, db
    from core import azure_graph
    
    tenant = db.session.get(Tenant, current_user.tenant_id)
    if not tenant or not tenant.azure_client_id:
        return jsonify({'success': False, 'error': 'Azure credentials not configured'})
        
    try:
        devices = azure_graph.get_devices(tenant)
        synced = 0
        for item in (devices or []):
            did = item.get('id')
            name = item.get('displayName')
            if not did or not name:
                continue
            ad = AzureDevice.query.filter_by(device_id=did, tenant_id=tenant.id).first()
            if not ad:
                ad = AzureDevice()
                ad.tenant_id = tenant.id
                ad.device_id = did
                db.session.add(ad)
            
            ad.display_name = name
            ad.os_platform = item.get('operatingSystem', '')
            ad.os_version = item.get('operatingSystemVersion', '')
            synced += 1
        db.session.commit()
        logger.info(f'[Azure Inventory Sync] {tenant.name}: {synced} devices synced manually')
        return jsonify({'success': True, 'synced': synced})
    except Exception as e:
        db.session.rollback()
        logger.error(f'[Azure Inventory Sync] Failed manual sync for {tenant.name}: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/api/v2/inventory/sync/debug', methods=['GET'])
@login_required
def api_inventory_sync_debug():
    """Diagnostic endpoint to help debug Azure inventory sync failures.

    Returns token acquisition status and a small sample from Microsoft Graph for the current tenant.
    Admin-only: only users belonging to the tenant may call this while signed in.
    """
    from web.models import Tenant, db
    try:
        tenant = db.session.get(Tenant, current_user.tenant_id)
        if not tenant:
            return jsonify({'success': False, 'error': 'Tenant not found for current user'}), 404

        # Try to acquire a token using the tenant app credentials
        try:
            from core import azure_graph
            token = azure_graph._get_token_for_tenant(tenant)
        except Exception as e:
            token = None
            token_err = str(e)
        else:
            token_err = None

        # Try to call Graph /devices endpoint (will return empty list on failure)
        try:
            from core import azure_graph
            devices = azure_graph.get_devices(tenant)
        except Exception as e:
            devices = []
            devices_err = str(e)
        else:
            devices_err = None

        data = {
            'tenant': tenant.name,
            'azure_configured': bool(tenant.azure_client_id and tenant.azure_client_secret and tenant.azure_tenant_id),
            'token_acquired': bool(token),
            'token_error': token_err,
            'devices_count': len(devices) if isinstance(devices, (list, tuple)) else 0,
            'devices_sample': devices[:5] if isinstance(devices, list) else [],
            'devices_error': devices_err,
        }

        return jsonify({'success': True, 'diagnostic': data})

    except Exception as e:
        logger.error(f'[Azure Inventory Sync Debug] Unexpected error: {e}', exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
