"""
Enhanced Command Execution & System Control API
- Improved command execution with real terminal output capture
- Installed software list retrieval
- Domain system agent push capabilities
- Remote command result polling
"""

import logging
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from sqlalchemy import desc

from web.models import (
    db, Server, RemoteCommand, Tenant, SystemDiscovery, 
    AuditLog, AzureUser, AzureDevice, AzureDeviceOwner
)

logger = logging.getLogger("[SYSTEM_CONTROL]")
sys_control_bp = Blueprint('sys_control', __name__)


@sys_control_bp.route('/api/v2/commands', methods=['POST'])
@login_required
def execute_command():
    """
    Queue a remote command for execution on target server.
    
    Expected JSON:
    {
        "server_id": 1,
        "command": "Get-Process notepad",
        "timeout": 120  # seconds (optional, default 120)
    }
    
    Returns:
    {
        "success": true,
        "command_id": 123,
        "status": "pending",
        "message": "Command queued for execution"
    }
    """
    try:
        data = request.get_json(silent=True) or {}
        server_id = data.get('server_id')
        command = (data.get('command') or '').strip()
        timeout = int(data.get('timeout', 120))

        if not server_id or not command:
            return jsonify({'success': False, 'error': 'server_id and command required'}), 400

        server = Server.query.get(server_id)
        if not server or (not current_user.is_superadmin and server.tenant_id != current_user.tenant_id):
            return jsonify({'success': False, 'error': 'Unauthorized or server not found'}), 403

        # Create remote command record
        cmd = RemoteCommand()
        cmd.server_id = server_id
        cmd.command = command
        cmd.status = 'pending'
        cmd.created_at = datetime.utcnow()
        cmd.timeout_seconds = timeout
        cmd.created_by = current_user.username

        db.session.add(cmd)
        db.session.commit()

        # Log the command for audit
        try:
            audit = AuditLog()
            audit.tenant_id = server.tenant_id
            audit.user_id = current_user.id
            audit.action = 'execute_command'
            audit.resource = f"Server:{server.hostname}"
            audit.details = f"Command: {command[:200]}"
            audit.timestamp = datetime.utcnow()
            db.session.add(audit)
            db.session.commit()
        except Exception as e:
            logger.warning(f"Failed to log audit: {e}")

        return jsonify({
            'success': True,
            'command_id': cmd.id,
            'server_id': server_id,
            'status': 'pending',
            'message': f'Command queued: {command[:50]}...'
        })
    except Exception as e:
        logger.error(f"Error queuing command: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@sys_control_bp.route('/api/v2/commands/<int:command_id>', methods=['GET'])
@login_required
def get_command_status(command_id):
    """
    Get command execution status and output.
    
    Returns:
    {
        "success": true,
        "command_id": 123,
        "status": "completed|failed|pending|running",
        "output": "command output here",
        "error_output": "stderr if any",
        "executed_at": "2026-05-04T10:30:00",
        "completed_at": "2026-05-04T10:30:05",
        "exit_code": 0
    }
    """
    try:
        cmd = RemoteCommand.query.get(command_id)
        if not cmd or (not current_user.is_superadmin and 
                      cmd.server.tenant_id != current_user.tenant_id):
            return jsonify({'success': False, 'error': 'Command not found or unauthorized'}), 404

        return jsonify({
            'success': True,
            'command_id': cmd.id,
            'server_id': cmd.server_id,
            'command': cmd.command,
            'status': cmd.status,
            'output': cmd.output or '',
            'error_output': cmd.error_output or '',
            'executed_at': cmd.executed_at.isoformat() if cmd.executed_at else None,
            'completed_at': cmd.completed_at.isoformat() if cmd.completed_at else None,
            'exit_code': cmd.exit_code,
            'created_at': cmd.created_at.isoformat() if cmd.created_at else None
        })
    except Exception as e:
        logger.error(f"Error fetching command status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@sys_control_bp.route('/api/v2/server/<int:server_id>/software/list', methods=['GET'])
@login_required
def get_installed_software(server_id):
    """
    Get list of installed software on target server.
    
    Query params:
    - filter: optional search filter (case-insensitive)
    - limit: number of results (default 100)
    
    Returns cached list from last agent report or queries for fresh list.
    """
    try:
        server = Server.query.get(server_id)
        if not server or (not current_user.is_superadmin and server.tenant_id != current_user.tenant_id):
            return jsonify({'success': False, 'error': 'Unauthorized or server not found'}), 403

        search_filter = (request.args.get('filter') or '').strip().lower()
        limit = int(request.args.get('limit', 100))

        # Check if we have cached software list
        software_cache = getattr(server, 'software_cache', None)
        
        if software_cache:
            try:
                import json
                software_list = json.loads(software_cache) if isinstance(software_cache, str) else software_cache
            except Exception:
                software_list = []
        else:
            # Queue a command to get software list
            # This will be executed by the agent next heartbeat
            cmd = RemoteCommand()
            cmd.server_id = server_id
            cmd.command = "Get-WmiObject -Class Win32_Product | Select-Object Name,Version,Vendor | ConvertTo-Json"
            cmd.status = 'pending'
            cmd.created_at = datetime.utcnow()
            db.session.add(cmd)
            db.session.commit()
            
            software_list = []

        # Filter results
        if search_filter:
            software_list = [s for s in software_list 
                           if search_filter in s.get('name', '').lower() 
                           or search_filter in s.get('vendor', '').lower()]

        # Limit results
        software_list = software_list[:limit]

        return jsonify({
            'success': True,
            'server_id': server_id,
            'software_list': software_list,
            'total': len(software_list),
            'is_cached': bool(software_cache),
            'message': f'Found {len(software_list)} software packages'
        })
    except Exception as e:
        logger.error(f"Error fetching software list: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@sys_control_bp.route('/api/v2/server/<int:server_id>/software/install', methods=['POST'])
@login_required
def install_software(server_id):
    """
    Queue software installation on remote server.
    
    Expected JSON:
    {
        "software": "Chrome",  # or full package name
        "version": "latest"    # optional
    }
    """
    try:
        server = Server.query.get(server_id)
        if not server or (not current_user.is_superadmin and server.tenant_id != current_user.tenant_id):
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403

        data = request.get_json(silent=True) or {}
        software = (data.get('software') or '').strip()
        version = (data.get('version') or 'latest').strip()

        if not software:
            return jsonify({'success': False, 'error': 'Software name required'}), 400

        # Queue installation command
        install_cmd = f"choco install {software} -y"
        if version and version != 'latest':
            install_cmd += f" --version {version}"

        cmd = RemoteCommand()
        cmd.server_id = server_id
        cmd.command = install_cmd
        cmd.status = 'pending'
        cmd.created_at = datetime.utcnow()
        cmd.created_by = current_user.username

        db.session.add(cmd)
        db.session.commit()

        return jsonify({
            'success': True,
            'command_id': cmd.id,
            'server_id': server_id,
            'action': 'install',
            'software': software,
            'message': f'Installation queued: {software} ({version})'
        })
    except Exception as e:
        logger.error(f"Error queuing installation: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@sys_control_bp.route('/api/v2/server/<int:server_id>/software/uninstall', methods=['POST'])
@login_required
def uninstall_software(server_id):
    """
    Queue software uninstallation on remote server.
    
    Expected JSON:
    {
        "software": "Chrome"  # exact program name or package name
    }
    """
    try:
        server = Server.query.get(server_id)
        if not server or (not current_user.is_superadmin and server.tenant_id != current_user.tenant_id):
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403

        data = request.get_json(silent=True) or {}
        software = (data.get('software') or '').strip()

        if not software:
            return jsonify({'success': False, 'error': 'Software name required'}), 400

        # Queue uninstallation command
        uninstall_cmd = f"choco uninstall {software} -y --force"

        cmd = RemoteCommand()
        cmd.server_id = server_id
        cmd.command = uninstall_cmd
        cmd.status = 'pending'
        cmd.created_at = datetime.utcnow()
        cmd.created_by = current_user.username

        db.session.add(cmd)
        db.session.commit()

        return jsonify({
            'success': True,
            'command_id': cmd.id,
            'server_id': server_id,
            'action': 'uninstall',
            'software': software,
            'message': f'Uninstallation queued: {software}'
        })
    except Exception as e:
        logger.error(f"Error queuing uninstallation: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@sys_control_bp.route('/api/v2/domain-discovery/systems', methods=['GET'])
@login_required
def get_discovered_systems_for_agent():
    """
    Get all discovered systems that haven't been imported yet.
    Suitable for agent push/deployment from agent portal.
    
    Query params:
    - status: 'pending' (not yet imported/managed), 'all'
    - source: filter by discovery source
    """
    try:
        if not current_user.is_superadmin:
            return jsonify({'success': False, 'error': 'Only superadmins can access'}), 403

        status_filter = request.args.get('status', 'pending').lower()
        source_filter = request.args.get('source', '').strip()

        query = SystemDiscovery.query.filter_by(
            tenant_id=current_user.tenant_id
        )

        if status_filter == 'pending':
            query = query.filter_by(status='pending')

        if source_filter:
            query = query.filter_by(source=source_filter)

        systems = query.order_by(SystemDiscovery.discovered_at.desc()).all()

        # Check which systems are already imported to servers
        imported_hostnames = {s.hostname.lower() for s in Server.query.filter_by(
            tenant_id=current_user.tenant_id
        ).all()}
        
        # Build owner mapping by hostname
        owner_by_hostname = {}
        if current_user.tenant_id:
            azure_users = db.session.query(AzureUser).filter_by(tenant_id=current_user.tenant_id).all()
            user_by_uuid = {u.user_id: u for u in azure_users}
            
            azure_owners = db.session.query(AzureDeviceOwner).filter_by(tenant_id=current_user.tenant_id).all()
            owner_by_device_id = {}
            for o in azure_owners:
                u = user_by_uuid.get(o.user_id)
                if u:
                    owner_by_device_id[o.device_id] = u.display_name or u.email
                    
            azure_devices = db.session.query(AzureDevice).filter_by(tenant_id=current_user.tenant_id).all()
            for dev in azure_devices:
                if dev.device_id in owner_by_device_id and dev.display_name:
                    owner_by_hostname[dev.display_name.lower()] = owner_by_device_id[dev.device_id]

        data = []
        for sys in systems:
            is_imported = sys.hostname.lower() in imported_hostnames
            assigned_user = owner_by_hostname.get(sys.hostname.lower())
            
            data.append({
                'discovery_id': sys.id,
                'hostname': sys.hostname,
                'ip_address': sys.ip,
                'os_info': sys.os_info,
                'source': sys.source,
                'status': sys.status,
                'discovered_at': sys.discovered_at.isoformat() if sys.discovered_at else None,
                'is_imported': is_imported,
                'is_manageable': not is_imported,  # Can push agent to unimported systems
                'employee_name': assigned_user or 'Unassigned'
            })

        return jsonify({
            'success': True,
            'discovered_systems': data,
            'total': len(data),
            'unmanaged_count': sum(1 for d in data if not d['is_imported'])
        })
    except Exception as e:
        logger.error(f"Error fetching discovered systems: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@sys_control_bp.route('/api/v2/domain-discovery/<int:discovery_id>/push-agent', methods=['POST'])
@login_required
def push_agent_to_discovered_system(discovery_id):
    """
    Push/deploy agent to a discovered system and import it.
    
    Expected JSON:
    {
        "agent_type": "psremoting|wmi|ssh",  # deployment method
        "credentials": {  # optional, uses domain creds if not provided
            "username": "domain\\username",
            "password": "password"
        }
    }
    """
    try:
        if not current_user.is_superadmin:
            return jsonify({'success': False, 'error': 'Only superadmins can deploy agents'}), 403

        discovery = SystemDiscovery.query.get(discovery_id)
        if not discovery or discovery.tenant_id != current_user.tenant_id:
            return jsonify({'success': False, 'error': 'System not found'}), 404

        # Check if already imported
        existing_server = Server.query.filter_by(hostname=discovery.hostname).first()
        if existing_server:
            server = existing_server
            discovery.status = 'imported'
            discovery.imported_at = datetime.utcnow()
            db.session.commit()
        else:
            # Create new server if not exists (although normally imported first)
            pass

        data = request.get_json(silent=True) or {}
        agent_type = data.get('agent_type', 'psremoting').lower()
        credentials = data.get('credentials', {})

        # Queue agent deployment command
        if agent_type == 'psremoting':
            deploy_cmd = (
                f"$ProgressPreference='SilentlyContinue'; "
                f"Invoke-Command -ComputerName {discovery.hostname} -ScriptBlock {{"
                f"  iex (New-Object Net.WebClient).DownloadString('http://{{PORTAL_URL}}/agent/download/script')"
                f"}}"
            )
        elif agent_type == 'wmi':
            deploy_cmd = f"wmic /node:\"{discovery.hostname}\" process call create \"powershell -Command iex (New-Object Net.WebClient).DownloadString('http://{{PORTAL_URL}}/agent/download/script')\""
        elif agent_type == 'ssh':
            deploy_cmd = f"ssh admin@{discovery.ip} 'curl http://{{PORTAL_URL}}/agent/download/script | bash'"
        else:
            return jsonify({'success': False, 'error': 'Invalid agent_type'}), 400

        # Create remote command for deployment
        cmd = RemoteCommand()
        cmd.command = deploy_cmd
        cmd.status = 'pending'
        cmd.created_at = datetime.utcnow()
        cmd.created_by = current_user.username

        # Create server record (will be activated when agent connects)
        server = Server()
        server.tenant_id = discovery.tenant_id
        server.hostname = discovery.hostname
        server.ip = discovery.ip
        server.os_info = discovery.os_info
        server.status = 'pending'
        server.is_online = False
        server.agent_installed = False
        server.monitoring_active = False
        server.source = 'domain_discovery'

        db.session.add(server)
        db.session.flush()

        cmd.server_id = server.id
        db.session.add(cmd)

        # Update discovery status
        discovery.status = 'import_queued'
        discovery.updated_at = datetime.utcnow()

        db.session.commit()

        return jsonify({
            'success': True,
            'server_id': server.id,
            'command_id': cmd.id,
            'hostname': discovery.hostname,
            'agent_type': agent_type,
            'message': f'Agent deployment queued for {discovery.hostname}'
        })
    except Exception as e:
        logger.error(f"Error pushing agent: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@sys_control_bp.route('/api/v2/server/<int:server_id>/commands/history', methods=['GET'])
@login_required
def get_command_history(server_id):
    """
    Get command execution history for a server.
    
    Query params:
    - limit: number of recent commands (default 20)
    - status: filter by status (pending, running, completed, failed)
    """
    try:
        server = Server.query.get(server_id)
        if not server or (not current_user.is_superadmin and server.tenant_id != current_user.tenant_id):
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403

        limit = int(request.args.get('limit', 20))
        status_filter = request.args.get('status', '').strip().lower()

        query = RemoteCommand.query.filter_by(server_id=server_id)

        if status_filter:
            query = query.filter_by(status=status_filter)

        commands = query.order_by(desc(RemoteCommand.created_at)).limit(limit).all()

        result = []
        for cmd in commands:
            result.append({
                'command_id': cmd.id,
                'command': cmd.command[:100],  # truncate for display
                'status': cmd.status,
                'created_at': cmd.created_at.isoformat() if cmd.created_at else None,
                'executed_at': cmd.executed_at.isoformat() if cmd.executed_at else None,
                'completed_at': cmd.completed_at.isoformat() if cmd.completed_at else None,
                'exit_code': cmd.exit_code,
                'created_by': getattr(cmd, 'created_by', 'System')
            })

        return jsonify({
            'success': True,
            'server_id': server_id,
            'commands': result,
            'total': len(result)
        })
    except Exception as e:
        logger.error(f"Error fetching command history: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
