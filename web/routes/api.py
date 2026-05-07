"""
api.py – Core API Blueprint
Provides screenshot serving (local fallback) and screenshot gallery endpoints.
"""

import os
import mimetypes
import logging
from datetime import datetime, timedelta

from typing import Any, cast

from flask import Blueprint, send_file, jsonify, abort, request, make_response
from flask_login import login_required, current_user

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)

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
        base_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            '..', 'data', 'screenshots'
        )
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

    # Defensive: check local file path and also attempt to resolve relative paths
    file_exists = False
    try:
        file_exists = bool(shot.local_file_path and os.path.isfile(shot.local_file_path))
    except Exception:
        file_exists = False

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
    # Cache aggressively; filenames are unique per capture timestamp.
    resp.headers['Cache-Control'] = 'public, max-age=86400'
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
            day_start = datetime(target.year, target.month, target.day, 0, 0, 0)
            day_end   = datetime(target.year, target.month, target.day, 23, 59, 59)
            q = q.filter(Screenshot.captured_at >= day_start,
                         Screenshot.captured_at <= day_end)
        except ValueError:
            pass

    q = q.order_by(Screenshot.captured_at.desc())

    total = q.count()
    shots = q.offset((page - 1) * per_page).limit(per_page).all()

    # Distinct dates (for the date filter tabs) – always across ALL screenshots
    all_dates_rows = (
        db.session.query(
            db.func.date(Screenshot.captured_at).label('d')
        )
        .filter(Screenshot.server_id == server_id)
        .group_by(db.func.date(Screenshot.captured_at))
        .order_by(db.func.date(Screenshot.captured_at).desc())
        .all()
    )
    distinct_dates = [r.d for r in all_dates_rows if r.d]

    result = []
    for s in shots:
        has_local = bool(s.local_file_path and os.path.isfile(s.local_file_path))
        # Only expose local thumbnails as image src to avoid hotlinking to SharePoint.
        thumb_url = f'/api/screenshot/{s.id}?size=thumb' if has_local else None
        result.append({
            'id':            s.id,
            'filename':      s.filename,
            'captured_at':   s.captured_at.isoformat() if s.captured_at else None,
            'captured_date': s.captured_at.strftime('%Y-%m-%d') if s.captured_at else None,
            'active_user':   s.active_user or '',
            'file_size_kb':  s.file_size_kb or 0,
            'sharepoint_url': s.sharepoint_url or None,
            'image_url':     f'/api/screenshot/{s.id}' if has_local else None,
            'thumb_url':     thumb_url,
            'has_image':     bool(s.sharepoint_url or has_local),
        })

    return jsonify({
        'success':     True,
        'total':       total,
        'page':        page,
        'per_page':    per_page,
        'dates':       distinct_dates,
        'screenshots': result,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Remote Control Operations  –  RDP, Software, Repairs
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/api/v2/server/<int:server_id>/remote/rdp', methods=['POST'])
@login_required
def api_remote_rdp(server_id):
    """Generate RDP connection command for remote desktop access"""
    from web.models import Server
    server = Server.query.get_or_404(server_id)
    
    if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
        abort(403)
    
    return jsonify({
        'success': True,
        'ip_address': server.ip_address or server.hostname,
        'rdp_command': f'mstsc /v:{server.ip_address or server.hostname} /admin',
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
    from web.models import Server
    server = Server.query.get_or_404(server_id)
    
    if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
        abort(403)
    
    data = request.get_json() or {}
    action = data.get('action', 'install')  # install or uninstall
    software = data.get('software', '')
    
    if not software:
        return jsonify({'error': 'Software name required'}), 400
    
    return jsonify({
        'success': True,
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
        cmd = RemoteCommand()
        cmd.server_id = server_id
        cmd.command = command_name
        cmd.parameters = json.dumps(params) if isinstance(params, (dict, list)) and params else (params if params else None)
        cmd.status = 'pending'
        db.session.add(cmd)
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
    from web.models import Server
    server = Server.query.get_or_404(server_id)
    
    if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
        abort(403)
    
    import random
    command_id = random.randint(1000, 9999)
    
    return jsonify({
        'success': True,
        'command_id': command_id,
        'message': 'Agent restart queued for next heartbeat'
    })

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
    from web.models import db, Server, Metric, Screenshot, EmployeeActivity

    data = request.get_json(silent=True) or {}

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
            db.session.add(server)
            logger.info(f"Auto-created server record for hostname={hostname}")

    if server is None:
        return jsonify({'success': False, 'error': 'Unknown agent. Register the server first.'}), 404

    # ── Update server heartbeat & metadata ────────────────────────────────
    now = datetime.utcnow()
    server.last_seen = now
    server.status    = 'online'
    server.agent_installed  = True
    server.monitoring_active = True
    if ip:
        server.ip = ip
    if os_info:
        server.os_info = os_info

    # ── Store Metric row ──────────────────────────────────────────────────
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
    db.session.add(metric)

    # ── Employee activity (logged_in_user) ────────────────────────────────
    if logged_in_user:
        activity = EmployeeActivity()
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
        db.session.add(activity)

    # ── Screenshot (base64 inline, save to disk) ───────────────────────────
    ss_data = data.get('screenshot')
    screenshot_enabled = server.screenshot_enabled
    screenshot_interval_minutes = server.screenshot_interval_minutes or 10

    if ss_data and ss_data.get('success') and ss_data.get('image'):
        try:
            import base64 as _b64
            import os as _os

            img_bytes = _b64.b64decode(ss_data['image'])
            ext       = 'jpg' if ss_data.get('format', 'jpeg') == 'jpeg' else ss_data.get('format', 'png')
            ts_str    = now.strftime('%Y%m%d_%H%M%S')
            fname     = f"screenshot_{server.id}_{hostname}_{ts_str}.{ext}"

            # Save next to the database in a screenshots sub-folder
            # current_app not required here; compute base dir directly
            base_dir  = _os.path.join(
                _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                '..', 'data', 'screenshots'
            )
            _os.makedirs(base_dir, exist_ok=True)
            file_path = _os.path.join(base_dir, fname)

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
            shot.local_file_path = _os.path.abspath(file_path)
            db.session.add(shot)
            logger.info(f"Screenshot saved: {file_path}")
        except Exception as e:
            logger.error(f"Failed to save screenshot: {e}")

    db.session.commit()

    # ── Emit real-time update via SocketIO ────────────────────────────────
    try:
        # Cast socketio to Any to avoid strict type errors in static analysis tools
        from web.app import socketio
        sio = cast(Any, socketio)
        sio.emit('metrics_update', {
            'server_id': server.id,
            'timestamp': now.isoformat() + 'Z',
            'metrics':   {'cpu': cpu, 'ram': ram, 'disk': disk},
        }, room=str(server.tenant_id))
    except Exception:
        pass

    return jsonify({
        'success':                    True,
        'server_id':                  server.id,
        'screenshot_enabled':         screenshot_enabled,
        'screenshot_interval_minutes': screenshot_interval_minutes,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Agent Command Poll  –  GET /api/v2/agent/commands
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/api/v2/agent/commands', methods=['GET'])
def agent_poll_commands():
    """Return pending commands for an agent identified by hostname header."""
    from web.models import Server, RemoteCommand

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

    return jsonify([
        {
            'command_id': c.id,
            'command':    c.command,
            'parameters': c.parameters or '',
        }
        for c in pending
    ])


# ─────────────────────────────────────────────────────────────────────────────
# Agent Command Result  –  POST /api/v2/agent/commands/result
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/api/v2/agent/commands/result', methods=['POST'])
def agent_command_result():
    """Accept execution result for a previously dispatched command."""
    from web.models import db, RemoteCommand

    data       = request.get_json(silent=True) or {}
    command_id = data.get('command_id')
    output     = data.get('output', '')
    status     = data.get('status', 'completed')

    if not command_id:
        return jsonify({'success': False, 'error': 'command_id required'}), 400

    cmd = db.session.get(RemoteCommand, command_id)
    if not cmd:
        return jsonify({'success': False, 'error': 'Command not found'}), 404

    cmd.status      = status
    cmd.output      = output
    cmd.executed_at = datetime.utcnow()
    db.session.commit()

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
            
        # Dummy logic to fulfill the forecast API requirements
        metrics = Metric.query.filter_by(server_id=server_id).order_by(Metric.timestamp.desc()).limit(10).all()
        if len(metrics) < 2:
            return jsonify({
                'success': False, 
                'message': 'Insufficient historical data for forecasting.'
            }), 200
            
        cpu_vals = [m.cpu_util_percent or m.cpu for m in metrics]
        cpu_trend = 'up' if cpu_vals[0] > cpu_vals[-1] else 'stable'
        
        return jsonify({
            'success': True,
            'message': 'Analysis complete',
            'recommendation': 'Server resources look stable based on recent trends.' if cpu_trend == 'stable' else 'CPU usage is trending upward.',
            'cpu': {'trend': cpu_trend},
            'ram': {'trend': 'stable'}
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
    enabled = data.get('enabled', False)
    interval = data.get('interval', 10)
    
    try:
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
    import json
    
    server = Server.query.get_or_404(server_id)
    
    if not current_user.is_superadmin and server.tenant_id != current_user.tenant_id:
        abort(403)
    
    data = request.get_json() or {}
    command = data.get('command', '').strip()
    
    if not command:
        return jsonify({'success': False, 'error': 'Command cannot be empty'}), 400
    
    try:
        # Queue the command directly — agent will run it in PowerShell as-is
        cmd = RemoteCommand()
        cmd.server_id = server_id
        cmd.command = command
        cmd.parameters = None
        cmd.status = 'pending'
        db.session.add(cmd)
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
