import logging
import secrets
from datetime import datetime, timezone
from flask import Blueprint, render_template, jsonify, request, url_for, current_app, send_file
from flask_login import login_required, current_user
import io
import zipfile
from web.models import db, Server, Tenant, AzureUser, AzureDeviceOwner, EmployeeAssetLog

logger = logging.getLogger("[AGENT_PORTAL]")

agent_portal_bp = Blueprint('agent_mgmt', __name__)

@agent_portal_bp.route('/agent-portal')
@login_required
def agent_portal():
    """Agent Management Portal Shell"""
    tenant = None
    if current_user.tenant_id:
        tenant = db.session.get(Tenant, current_user.tenant_id)
    if tenant is None and current_user.is_superadmin:
        tenant = Tenant.query.order_by(Tenant.id.asc()).first()
    return render_template('agent_portal.html', tenant=tenant)

@agent_portal_bp.route('/api/systems/list')
@login_required
def list_systems():
    """Return all registered servers for current tenant (used by Agent Portal UI)."""
    try:
        query = Server.query
        if not current_user.is_superadmin:
            query = query.filter_by(tenant_id=current_user.tenant_id)
        else:
            # Superadmin: show all, but prefer current tenant first
            pass

        servers = query.order_by(Server.id.desc()).all()
        server_ids = [s.id for s in servers]
        
        # Build owner mappings
        owner_by_device_id = {}
        owner_by_server_id = {}
        
        if current_user.tenant_id:
            azure_users = db.session.query(AzureUser).filter_by(tenant_id=current_user.tenant_id).all()
            user_by_uuid = {u.user_id: u for u in azure_users}
            
            azure_owners = db.session.query(AzureDeviceOwner).filter_by(tenant_id=current_user.tenant_id).all()
            for o in azure_owners:
                u = user_by_uuid.get(o.user_id)
                if u:
                    owner_by_device_id[o.device_id] = u.display_name or u.email
            
            if server_ids:
                asset_logs = db.session.query(EmployeeAssetLog).filter(
                    EmployeeAssetLog.tenant_id == current_user.tenant_id,
                    EmployeeAssetLog.server_id.in_(server_ids)
                ).order_by(EmployeeAssetLog.login_timestamp.desc()).all()
                
                seen_servers = set()
                for log in asset_logs:
                    if log.server_id not in seen_servers:
                        owner_by_server_id[log.server_id] = log.employee_email or log.employee_id
                        seen_servers.add(log.server_id)

        result = []
        for s in servers:
            diff = None
            if s.last_seen:
                diff = (datetime.now(timezone.utc).replace(tzinfo=None) - s.last_seen).total_seconds()
            status = 'online' if diff is not None and diff < 90 else ('offline' if s.last_seen else 'registered')
            
            # Resolve assigned user
            assigned_user = owner_by_server_id.get(s.id)
            if not assigned_user and s.azure_device_id:
                assigned_user = owner_by_device_id.get(s.azure_device_id)
                

            result.append({
                'id': s.id,
                'hostname': s.hostname or s.name or f'Server-{s.id}',
                'ip': s.ip or '',
                'status': status,
                'agent_installed': bool(s.agent_installed),
                'api_key': (s.api_key or '')[:16] + '...' if s.api_key else '',
                'last_seen': s.last_seen.isoformat() if s.last_seen else None,
                'serial_number': s.serial_number or '',
                'employee_name': assigned_user or 'Unassigned'
            })
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error listing systems: {e}")
        return jsonify([])

@agent_portal_bp.route('/api/v2/agent/register-system', methods=['POST'])
@login_required
def register_system():
    """Register a system and generate a bot installer"""
    try:
        data = request.get_json()
        hostname = data.get('hostname')
        ip_address = data.get('ip_address')
        serial_number = data.get('serial_number')
        address = data.get('address')
        
        if not hostname:
            return jsonify({'success': False, 'error': 'Hostname is required'}), 400
            
        # Check if server already exists for this tenant
        server = Server.query.filter_by(hostname=hostname, tenant_id=current_user.tenant_id).first()
        if not server:
            server = Server()
            server.hostname = hostname
            server.name = hostname
            server.tenant_id = current_user.tenant_id
            server.api_key = secrets.token_hex(32)
            db.session.add(server)
        
        server.ip = ip_address
        server.serial_number = serial_number
        server.address = address
        server.monitoring_active = True
        server.last_seen = datetime.now(timezone.utc).replace(tzinfo=None)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'server_id': server.id,
            'message': f'System {hostname} registered successfully.'
        })
    except Exception as e:
        logger.error(f"Error registering system: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@agent_portal_bp.route('/agent/download-bot/<int:server_id>')
@login_required
def download_bot(server_id):
    """Generate and download a pre-configured PowerShell bot installer"""
    server = db.session.get(Server, server_id)
    if not server or (not current_user.is_superadmin and server.tenant_id != current_user.tenant_id):
        return "Unauthorized or Server Not Found", 403

    server_url = request.host_url.rstrip('/')
    bslash = "\\"
    
    # Pre-configured PowerShell script
    install_script = f"""# ServerMonitor Pre-configured Bot Installer
# Targeted Host: {server.hostname}
# Registration ID: {server.id}

$ApiKey = "{server.api_key}"
$ServerId = {server.id}
$ApiUrl = "{server_url}/api/metrics"
$RegisterUrl = "{server_url}/api/register_agent"
$SerialNumber = "{server.serial_number or ''}"
$IntervalSeconds = 15

Write-Host "Initializing ServerMonitor Bot for {server.hostname}..." -ForegroundColor Cyan

# Step 0: Immediate registration heartbeat so portal detects this agent right away
Write-Host "Registering agent with server..." -ForegroundColor Yellow
try {{
    $regBody = @{{
        agent_key = $ApiKey
        hostname  = $env:COMPUTERNAME
        ip        = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {{ $_.InterfaceAlias -notlike "*Loopback*" -and $_.PrefixOrigin -ne "WellKnown" }} | Select-Object -First 1).IPAddress
        os_info   = (Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue).Caption
        serial_number = if($SerialNumber){{$SerialNumber}}else{{(Get-CimInstance Win32_Bios -ErrorAction SilentlyContinue).SerialNumber}}
    }} | ConvertTo-Json -Depth 5
    $regResp = Invoke-RestMethod -Uri $RegisterUrl -Method Post -Body $regBody -Headers @{{
        "Content-Type" = "application/json"
        "X-Agent-Key"  = $ApiKey
    }} -TimeoutSec 10
    if ($regResp.success) {{
        Write-Host "  Agent registered! Server ID: $($regResp.server_id)" -ForegroundColor Green
        $ServerId = $regResp.server_id
    }} else {{
        Write-Host "  Registration response: $($regResp | ConvertTo-Json -Compress)" -ForegroundColor Yellow
    }}
}} catch {{
    Write-Host "  Registration failed (will retry via agent loop): $_" -ForegroundColor Yellow
}}

$AgentDir = "$env:ProgramData{bslash}ServerMonitorAgent"
if (-not (Test-Path $AgentDir)) {{
    New-Item -Path $AgentDir -ItemType Directory -Force | Out-Null
}}

# Save config for the agent script
@{{
    ApiKey       = $ApiKey
    ServerUrl    = "{server_url}"
}} | ConvertTo-Json | Set-Content "$AgentDir{bslash}config.json" -Encoding UTF8
Write-Host "Config saved to $AgentDir{bslash}config.json" -ForegroundColor Green

# Download production agent script
$AgentSource = "{server_url}/static/agent/ServerMonitorAgent.ps1"
Write-Host "Downloading agent payload from $AgentSource..."
Invoke-WebRequest -Uri $AgentSource -OutFile "$AgentDir{bslash}ServerMonitorAgent.ps1" -TimeoutSec 30

# Create scheduled task - run at logon of current user so Win32 idle/screenshot APIs work
Write-Host "Registering persistent monitoring service..."
$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Action   = New-ScheduledTaskAction -Execute "powershell.exe" `
               -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -NonInteractive -File `"$AgentDir{bslash}ServerMonitorAgent.ps1`" -ApiKey `"$ApiKey`" -ServerUrl `"{server_url}`""
$Trigger  = New-ScheduledTaskTrigger -AtLogOn -User $CurrentUser
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit 0
$Principal = New-ScheduledTaskPrincipal -UserId $CurrentUser -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName "ServerMonitorBot" -Action $Action -Trigger $Trigger `
    -Settings $Settings -Principal $Principal -Force

# Start immediately in current session
Write-Host "Starting agent in current session..."
Start-Process powershell.exe -ArgumentList "-ExecutionPolicy Bypass -WindowStyle Hidden -NonInteractive -File `"$AgentDir{bslash}ServerMonitorAgent.ps1`" -ApiKey `"$ApiKey`" -ServerUrl `"{server_url}`"" -WindowStyle Hidden
Write-Host ""
Write-Host "Bot successfully deployed and tracking started!" -ForegroundColor Green
Write-Host "Your agent should appear in the portal within 30 seconds." -ForegroundColor Cyan
"""

    # Batch wrapper for "one-click" admin execution
    bat_content = f"""@echo off
title ServerMonitor Bot Deployment
echo ---------------------------------------------------
echo   Deploying ServerMonitor Bot on %COMPUTERNAME%
echo ---------------------------------------------------
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \""%~dp0deploy.ps1\""' -Verb RunAs"
echo.
echo Please approve the UAC prompt to complete setup.
echo.
pause
"""

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("deploy.ps1", install_script.encode('utf-8'))
        zf.writestr("OneClickInstall.bat", bat_content.encode('utf-8'))
    
    mem.seek(0)
    return send_file(
        mem,
        as_attachment=True,
        download_name=f"MonitorBot-{server.hostname}.zip",
        mimetype='application/zip'
    )


# ─────────────────────────────────────────────────────────────────────────────
# NEW: Python Agent Download & Installation
# ─────────────────────────────────────────────────────────────────────────────

@agent_portal_bp.route('/agent/download-python-agent/<int:server_id>')
@login_required
def download_python_agent(server_id):
    """Download pre-configured Python agent (agent_improved.py)"""
    server = db.session.get(Server, server_id)
    if not server or (not current_user.is_superadmin and server.tenant_id != current_user.tenant_id):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    server_url = request.host_url.rstrip('/')
    
    # Generate a config-embedded Python agent
    agent_code = f'''#!/usr/bin/env python3
"""
ServerMonitor Agent (Pre-configured)
Hostname: {server.hostname}
API Key: {server.api_key[:8]}...
Generated: {datetime.now(timezone.utc).isoformat()}
"""

import os
import sys
import json
import logging
import socket
import subprocess
import base64
import io
from datetime import datetime, timezone
from pathlib import Path

import psutil
import requests

try:
    from PIL import ImageGrab
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION (Pre-configured for deployment)
# ─────────────────────────────────────────────────────────────────────────────

API_KEY = "{server.api_key}"
SERVER_URL = "{server_url}"
AGENT_INTERVAL = int(os.environ.get('AGENT_INTERVAL', 30))
ENABLE_SCREENSHOTS = os.environ.get('ENABLE_SCREENSHOTS', 'true').lower() == 'true'
SCREENSHOT_INTERVAL = int(os.environ.get('SCREENSHOT_INTERVAL', 300))
LOG_FILE = Path(os.path.expanduser('~')) / 'ServerMonitor' / 'agent_improved.log'

# Setup logging
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def get_system_metrics():
    """Collect comprehensive system metrics"""
    try:
        # CPU metrics
        cpu_logical = psutil.cpu_count(logical=True)
        cpu_physical = psutil.cpu_count(logical=False)
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # RAM metrics
        ram = psutil.virtual_memory()
        ram_total_gb = ram.total / (1024**3)
        ram_used_gb = ram.used / (1024**3)
        ram_available_gb = ram.available / (1024**3)
        ram_percent = ram.percent
        
        # Disk metrics
        disk = psutil.disk_usage('/')
        disk_total_gb = disk.total / (1024**3)
        disk_used_gb = disk.used / (1024**3)
        disk_free_gb = disk.free / (1024**3)
        disk_percent = disk.percent
        
        # Network
        try:
            hostname_ip = socket.gethostbyname(socket.gethostname())
        except:
            hostname_ip = "127.0.0.1"
        
        # Logged-in user
        import getpass
        logged_in_user = getpass.getuser()
        
        # Timestamps
        utc_timestamp = datetime.now(timezone.utc).isoformat() + 'Z'
        local_timestamp = datetime.now(timezone.utc).isoformat()
        
        return {{
            'cpu_logical_cores': cpu_logical,
            'cpu_physical_cores': cpu_physical,
            'cpu_util_percent': cpu_percent,
            'ram_total_gb': round(ram_total_gb, 2),
            'ram_used_gb': round(ram_used_gb, 2),
            'ram_available_gb': round(ram_available_gb, 2),
            'ram_util_percent': ram_percent,
            'disk_total_gb': round(disk_total_gb, 2),
            'disk_used_gb': round(disk_used_gb, 2),
            'disk_free_gb': round(disk_free_gb, 2),
            'disk_util_percent': disk_percent,
            'network_ip': hostname_ip,
            'logged_in_user': logged_in_user,
            'timestamp': utc_timestamp,
            'local_timestamp': local_timestamp
        }}
    except Exception as e:
        logger.error(f"Error collecting metrics: {{e}}")
        return None

def capture_screenshot():
    """Capture system screenshot"""
    try:
        if not PILLOW_AVAILABLE:
            return {{'success': False, 'reason': 'PIL not available'}}
        
        img = ImageGrab.grab()
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG', quality=70)
        img_byte_arr.seek(0)
        
        return {{
            'success': True,
            'image': base64.b64encode(img_byte_arr.getvalue()).decode('utf-8'),
            'format': 'jpeg',
            'size': len(img_byte_arr.getvalue()),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }}
    except Exception as e:
        logger.error(f"Error capturing screenshot: {{e}}")
        return {{'success': False, 'reason': str(e)}}

def send_metrics(metrics, screenshot=None):
    """Send metrics to server"""
    try:
        payload = {{
            'api_key': API_KEY,
            'hostname': socket.gethostname(),
            'ip': metrics.get('network_ip'),
            'os_info': f"{{sys.platform}} {{sys.version.split()[0]}}",
            'logged_in_user': metrics.get('logged_in_user'),
            'metrics': metrics
        }}
        
        if screenshot and screenshot.get('success'):
            payload['screenshot'] = screenshot
        
        headers = {{
            'X-Agent-Key': API_KEY,
            'X-Hostname': socket.gethostname(),
            'Content-Type': 'application/json'
        }}
        
        response = requests.post(
            f"{{SERVER_URL}}/api/v2/agent/metrics",
            json=payload,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            logger.info(f"✅ Metrics sent | CPU: {{metrics['cpu_util_percent']}}% | RAM: {{metrics['ram_util_percent']}}% | Disk: {{metrics['disk_util_percent']}}%")
            return True
        else:
            logger.error(f"❌ Server error: {{response.status_code}} {{response.text}}")
            return False
    except Exception as e:
        logger.error(f"Error sending metrics: {{e}}")
        return False

def main():
    """Main agent loop"""
    logger.info(f"🚀 ServerMonitor Agent started for {{socket.gethostname()}}")
    logger.info(f"   API Key: {server.api_key[:8]}...")
    logger.info(f"   Server: {{SERVER_URL}}")
    logger.info(f"   Interval: {{AGENT_INTERVAL}}s, Screenshots: {{ENABLE_SCREENSHOTS}}")
    
    # Validate connectivity on startup
    try:
        response = requests.get(f"{{SERVER_URL}}/health", timeout=5)
        logger.info(f"✅ Server connectivity verified")
    except Exception as e:
        logger.error(f"❌ Cannot connect to server: {{e}}")
        logger.error("   Retrying in 30 seconds...")
        
    screenshot_counter = 0
    
    while True:
        try:
            # Collect metrics
            metrics = get_system_metrics()
            if not metrics:
                logger.warning("Failed to collect metrics, retrying...")
                continue
            
            # Capture screenshot if interval reached
            screenshot = None
            if ENABLE_SCREENSHOTS and screenshot_counter >= SCREENSHOT_INTERVAL // AGENT_INTERVAL:
                screenshot = capture_screenshot()
                screenshot_counter = 0
            else:
                screenshot_counter += 1
            
            # Send to server
            send_metrics(metrics, screenshot)
            
        except KeyboardInterrupt:
            logger.info("🛑 Agent stopped by user")
            break
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {{e}}")
        
        import time
        time.sleep(AGENT_INTERVAL)

if __name__ == '__main__':
    main()
'''
    
    # Send as downloadable file
    return send_file(
        io.BytesIO(agent_code.encode('utf-8')),
        as_attachment=True,
        download_name=f"agent_improved_{server.hostname}.py",
        mimetype='text/plain'
    )


@agent_portal_bp.route('/agent/download-deployment-script/<int:server_id>')
@login_required
def download_deployment_script(server_id):
    """Download PowerShell deployment script with pre-configured API key"""
    server = db.session.get(Server, server_id)
    if not server or (not current_user.is_superadmin and server.tenant_id != current_user.tenant_id):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    server_url = request.host_url.rstrip('/')
    
    # Pre-configured deployment script
    deploy_script = f'''# ServerMonitor Agent Deployment Script (Pre-configured)
# System: {server.hostname}
# Generated: {datetime.now(timezone.utc).isoformat()}

Write-Host "`n" + "="*70 -ForegroundColor Green
Write-Host "  SERVERMONITOR - PYTHON AGENT DEPLOYMENT" -ForegroundColor Green
Write-Host "="*70 -ForegroundColor Green

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")
if (-not $isAdmin) {{
    Write-Host "`n❌ ERROR: This script must run as Administrator!" -ForegroundColor Red
    Write-Host "   Right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
    exit 1
}}

Write-Host "`n✅ Running as Administrator" -ForegroundColor Green

# Set environment variables
Write-Host "`n📝 Setting environment variables..." -ForegroundColor Cyan

$env:AGENT_KEY = "{server.api_key}"
$env:SERVER_URL = "{server_url}"
$env:ENABLE_SCREENSHOTS = "true"
$env:SCREENSHOT_INTERVAL = "300"
$env:AGENT_INTERVAL = "30"

Write-Host "`n📊 Environment Configuration:" -ForegroundColor Cyan
Write-Host "   AGENT_KEY:           {server.api_key[:16]}..." -ForegroundColor White
Write-Host "   SERVER_URL:          {{$env:SERVER_URL}}" -ForegroundColor White
Write-Host "   ENABLE_SCREENSHOTS:  {{$env:ENABLE_SCREENSHOTS}}" -ForegroundColor White
Write-Host "   SCREENSHOT_INTERVAL: {{$env:SCREENSHOT_INTERVAL}} seconds" -ForegroundColor White
Write-Host "   AGENT_INTERVAL:      {{$env:AGENT_INTERVAL}} seconds" -ForegroundColor White

# Verify Python is installed
Write-Host "`n🔍 Checking Python installation..." -ForegroundColor Cyan
$pythonCheck = python --version 2>&1
if ($LASTEXITCODE -ne 0) {{
    Write-Host "❌ Python is not installed or not in PATH" -ForegroundColor Red
    Write-Host "   Please install Python 3.8+ from python.org" -ForegroundColor Yellow
    exit 1
}}
Write-Host "✅ Python found: $pythonCheck" -ForegroundColor Green

# Install dependencies
Write-Host "`n📦 Installing required packages..." -ForegroundColor Cyan
python -m pip install psutil requests Pillow -q
if ($LASTEXITCODE -ne 0) {{
    Write-Host "⚠️  Warning: Some packages may not have installed correctly" -ForegroundColor Yellow
}} else {{
    Write-Host "✅ Packages installed successfully" -ForegroundColor Green
}}

# Create agent installation directory
$AgentDir = "$env:USERPROFILE\\.ServerMonitor"
if (-not (Test-Path $AgentDir)) {{
    New-Item -Path $AgentDir -ItemType Directory -Force | Out-Null
    Write-Host "`n📁 Created directory: $AgentDir" -ForegroundColor Green
}}

Write-Host "`n🚀 Starting agent (agent_improved.py)..." -ForegroundColor Green
Write-Host "   Press Ctrl+C to stop" -ForegroundColor Yellow

Write-Host "`n" + "="*70 -ForegroundColor Green
Write-Host "  AGENT OUTPUT" -ForegroundColor Green
Write-Host "="*70 -ForegroundColor Green + "`n"

# Run the agent
python agent_improved_{server.hostname}.py

Write-Host "`n" + "="*70
Write-Host "Agent stopped." -ForegroundColor Yellow
Write-Host "="*70
'''
    
    return send_file(
        io.BytesIO(deploy_script.encode('utf-8')),
        as_attachment=True,
        download_name=f"DEPLOY_{server.hostname}.ps1",
        mimetype='text/plain'
    )


@agent_portal_bp.route('/agent/quick-setup/<int:server_id>')
@login_required
def get_quick_setup(server_id):
    """Get quick setup instructions"""
    server = db.session.get(Server, server_id)
    if not server or (not current_user.is_superadmin and server.tenant_id != current_user.tenant_id):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    server_url = request.host_url.rstrip('/')
    
    setup_guide = f"""
╔════════════════════════════════════════════════════════════════════════════╗
║                 SERVERMONITOR AGENT QUICK SETUP GUIDE                      ║
╚════════════════════════════════════════════════════════════════════════════╝

System: {server.hostname}
API Key: {server.api_key}
Server URL: {server_url}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST

════════════════════════════════════════════════════════════════════════════

📥 STEP 1: Download Files
  
  1a. Download from Agent Portal:
      • agent_improved_{server.hostname}.py (Python agent)
      • DEPLOY_{server.hostname}.ps1 (Deployment script)
  
  1b. OR download both files from your browser:
      {server_url}/agent/download-python-agent/{server_id}
      {server_url}/agent/download-deployment-script/{server_id}

════════════════════════════════════════════════════════════════════════════

⚙️  STEP 2: Prepare Windows System
  
  2a. Right-click PowerShell → "Run as Administrator"
  
  2b. Navigate to where you saved the files:
      cd "C:\\Users\\YourName\\Downloads"
  
  2c. Run the deployment script:
      .\\DEPLOY_{server.hostname}.ps1
  
  Note: Script will automatically:
    ✓ Install Python dependencies (psutil, requests, Pillow)
    ✓ Set environment variables (API_KEY, SERVER_URL)
    ✓ Start the Python agent

════════════════════════════════════════════════════════════════════════════

🚀 STEP 3: Manual Run (if needed)
  
  If deployment script doesn't work, run manually:
  
  PowerShell as Administrator:
    $env:AGENT_KEY = "{server.api_key}"
    $env:SERVER_URL = "{server_url}"
    $env:ENABLE_SCREENSHOTS = "true"
    python agent_improved_{server.hostname}.py

════════════════════════════════════════════════════════════════════════════

✅ STEP 4: Verify on Dashboard
  
  • Open browser: {server_url}
  • Look for "{server.hostname}" in registered systems
  • Check metrics are being updated every 30 seconds
  • Screenshots should appear within 5 minutes

════════════════════════════════════════════════════════════════════════════

🎯 WHAT YOU'LL GET:
  
  ✓ Real-time CPU, RAM, Disk monitoring
  ✓ Network information and login tracking
  ✓ Screenshots every 5 minutes
  ✓ Automatic performance metrics
  ✓ IST timezone (Indian Standard Time)
  ✓ 30-second update intervals

════════════════════════════════════════════════════════════════════════════

⚠️  TROUBLESHOOTING:
  
  No metrics appearing?
    • Verify agent is running (check for ✅ Metrics sent messages)
    • Check {server_url} is reachable
    • Ensure PowerShell is running as Administrator
  
  Python not found?
    • Install from: https://www.python.org/
    • Add to PATH during installation
    • Restart PowerShell after installing
  
  Screenshots not working?
    • Wait 5+ minutes (default interval)
    • Check Pillow library installed: pip list | findstr Pillow
    • Try manual command: python -c "from PIL import ImageGrab; ImageGrab.grab()"

════════════════════════════════════════════════════════════════════════════

📊 API CONFIGURATION:
  
  API Key:      {server.api_key}
  Server URL:   {server_url}
  Endpoint:     {server_url}/api/v2/agent/metrics
  Method:       POST
  Interval:     30 seconds (configurable)
  Screenshots:  Enabled (every 5 minutes)

════════════════════════════════════════════════════════════════════════════

For more help, visit: {server_url}/agent-portal
Generated: {datetime.now().isoformat()}
"""
    
    return jsonify({
        'success': True,
        'hostname': server.hostname,
        'api_key': server.api_key,
        'server_url': server_url,
        'setup_guide': setup_guide,
        'download_urls': {
            'agent': f"{server_url}/agent/download-python-agent/{server_id}",
            'deployment': f"{server_url}/agent/download-deployment-script/{server_id}"
        }
    })
