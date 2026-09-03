# 🏢 InfraMonitor - Organization-Wide Deployment Guide

## Overview

Deploy InfraMonitor across your organization domain to monitor all servers, execute remote commands, manage software, and track employee productivity.

---

## 📋 Pre-Deployment Checklist

- [ ] **Server Requirements**
  - [ ] Windows Server 2016+ or Windows 10/11 Pro for central server
  - [ ] PostgreSQL 12+ or SQL Server 2019+ for database
  - [ ] 50GB+ disk space for logs/metrics
  - [ ] Static IP address for monitoring server
  - [ ] HTTPS certificate (self-signed or CA-signed)

- [ ] **Network Requirements**
  - [ ] Port 5000 (HTTPS/HTTP) accessible from domain systems
  - [ ] Port 5001 (admin portal) - optional, internal only
  - [ ] Firewall rules configured
  - [ ] DNS record created (e.g., `InfraMonitor.yourdomain.com`)

- [ ] **Active Directory Setup**
  - [ ] Service account created (e.g., `svc_InfraMonitor@domain.com`)
  - [ ] OUs identified for agent deployment
  - [ ] Group Policy configured (optional, for auto-deployment)

---

## 🚀 Phase 1: Central Server Deployment

### Step 1: Deploy Central Monitoring Server

**Location:** Your central IT server (e.g., `monitor-01.yourdomain.com`)

```powershell
# On central server - Clone repository
git clone <your-repo-url> C:\InfraMonitor
cd C:\InfraMonitor

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
pip install psycopg2-binary  # For PostgreSQL
```

### Step 2: Configure PostgreSQL Database

```powershell
# On PostgreSQL Server (or use Azure Database for PostgreSQL)
# Create database and user

psql -U postgres
CREATE DATABASE InfraMonitor_org;
CREATE USER InfraMonitor_user WITH PASSWORD 'SecurePassword123!';
ALTER ROLE InfraMonitor_user SET client_encoding TO 'utf8';
ALTER ROLE InfraMonitor_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE InfraMonitor_user SET default_transaction_deferrable TO on;
ALTER ROLE InfraMonitor_user SET default_transaction_level TO 'read committed';
GRANT ALL PRIVILEGES ON DATABASE InfraMonitor_org TO InfraMonitor_user;
```

### Step 3: Configure Environment Variables

Create `.env` file in `C:\InfraMonitor`:

```ini
# Database
DATABASE_URL=postgresql://InfraMonitor_user:SecurePassword123!@db-server.yourdomain.com:5432/InfraMonitor_org

# Flask
FLASK_ENV=production
FLASK_SECRET_KEY=your-very-long-random-secret-key-here-min-32-chars
SECRET_KEY=your-very-long-random-secret-key-here-min-32-chars

# Server Configuration
SERVER_PORT=5000
SERVER_HOST=0.0.0.0
ENABLE_HTTPS=true
SSL_CERT=/path/to/cert.crt
SSL_KEY=/path/to/key.key

# Authentication
ALLOW_SIGNUP=false
DEFAULT_ADMIN_PASSWORD=GeneratedSecurePassword123!

# Email Notifications (Optional)
SMTP_SERVER=mail.yourdomain.com
SMTP_PORT=587
SMTP_USERNAME=InfraMonitor@yourdomain.com
SMTP_PASSWORD=email-password
SMTP_FROM=InfraMonitor <InfraMonitor@yourdomain.com>

# Agent Configuration
AGENT_API_TOKEN_TTL=86400  # 24 hours
MAX_AGENTS_PER_TENANT=unlimited
```

### Step 4: Initialize Database Schema

```powershell
cd C:\InfraMonitor
.\.venv\Scripts\Activate.ps1
python -m scripts.database.init_db_from_models
```

### Step 5: Create Admin Account

```powershell
python -c "
from web.app import app, db
from web.models import User, Tenant

with app.app_context():
    tenant = Tenant.query.filter_by(name='Default').first()
    if not tenant:
        tenant = Tenant(name='Default', is_active=True)
        db.session.add(tenant)
        db.session.commit()

    admin = User(
        username='admin',
        email='admin@yourdomain.com',
        tenant_id=tenant.id,
        is_superadmin=True,
        is_active=True
    )
    admin.set_password('YourSecureAdminPassword123!')
    db.session.add(admin)
    db.session.commit()
    print('✅ Admin user created')
"
```

### Step 6: Install as Windows Service (Optional but Recommended)

```powershell
# Install NSSM (Non-Sucking Service Manager)
choco install nssm -y

# Register Flask app as service
nssm install InfraMonitor "python" "C:\InfraMonitor\web\app.py"
nssm set InfraMonitor AppDirectory "C:\InfraMonitor"
nssm set InfraMonitor AppEnvironmentExtra DATABASE_URL=postgresql://...
nssm set InfraMonitor Start SERVICE_AUTO_START
nssm set InfraMonitor AppRotateFiles 1
nssm set InfraMonitor AppRotateOnline 1

# Start service
Start-Service InfraMonitor
```

### Step 7: Configure HTTPS (Production)

```powershell
# Using Let's Encrypt (recommended for public servers)
# Install Certbot: https://certbot.eff.org

certbot certonly --standalone -d InfraMonitor.yourdomain.com

# Update .env:
# SSL_CERT=C:\Certbot\live\InfraMonitor.yourdomain.com\fullchain.pem
# SSL_KEY=C:\Certbot\live\InfraMonitor.yourdomain.com\privkey.pem
```

### Step 8: Test Central Server

```powershell
# Restart service
Restart-Service InfraMonitor

# Test connectivity
curl -k https://InfraMonitor.yourdomain.com:5000/
# Should return login page
```

---

## 👥 Phase 2: Generate Agent API Keys

### For Each Tenant/Department

1. **Login to AdminPortal:** `https://InfraMonitor.yourdomain.com:5001`
2. **Navigate:** Settings → API Keys
3. **Generate Key:**
   - Name: "Department-A-Production"
   - Permissions: agent:metrics, agent:commands, server:register
   - Expiry: 90 days (auto-renew)
4. **Copy Key** (looks like: `sk_prod_1a2b3c4d5e6f7g8h9i0j...`)
5. **Share securely** to deployment team (store in secure vault)

---

## 🖥️ Phase 3: Agent Deployment Strategies

### Strategy A: Group Policy (Recommended for Large Organizations)

**Requirements:**

- Domain-joined Windows computers
- Group Policy editing access
- PowerShell execution enabled

**Steps:**

1. **Create GPO:**

   ```powershell
   New-GPO -Name "InfraMonitor-Agent-Deployment" | Edit-GPO
   ```

2. **Configure Startup Script:**
   - Navigate: Computer Configuration → Windows Settings → Scripts → Startup
   - Add script: `Deploy-Agent.ps1` (see below)

3. **Create Deployment Script** (`C:\InfraMonitor\Deploy-Agent.ps1`):

```powershell
param(
    [string]$ServerUrl = "https://InfraMonitor.yourdomain.com",
    [string]$AgentKey = $env:SERVER_MONITOR_KEY,
    [string]$TenantId = "prod-tenant-1"
)

Write-Host "🤖 InfraMonitor Agent Deployment Starting..."

# Check if agent already installed
if (Test-Path "C:\Program Files\InfraMonitor\Agent\agent.py") {
    Write-Host "✅ Agent already installed"
    exit 0
}

# Create directory
$AgentDir = "C:\Program Files\InfraMonitor\Agent"
New-Item -ItemType Directory -Path $AgentDir -Force | Out-Null

# Download agent package
$DownloadUrl = "$ServerUrl/api/v2/agent/download"
$DownloadPath = "$env:TEMP\InfraMonitor-agent.zip"
Invoke-WebRequest -Uri $DownloadUrl -OutFile $DownloadPath -UseBasicParsing

# Extract
Expand-Archive -Path $DownloadPath -DestinationPath $AgentDir -Force

# Configure agent
$ConfigFile = "$AgentDir\agent_config.json"
$Config = @{
    SERVER_URL = $ServerUrl
    AGENT_KEY = $AgentKey
    TENANT_ID = $TenantId
    INTERVAL = 30
} | ConvertTo-Json

Set-Content -Path $ConfigFile -Value $Config

# Install as Windows Service using NSSM
choco install nssm -y --force

nssm install InfraMonitorAgent "python" "$AgentDir\agent.py"
nssm set InfraMonitorAgent AppDirectory $AgentDir
nssm set InfraMonitorAgent Start SERVICE_AUTO_START

# Start service
Start-Service InfraMonitorAgent

Write-Host "✅ InfraMonitor Agent installed and started"
Write-Host "📊 Check portal at: $ServerUrl"
```

4. **Link GPO to OU:**
   ```powershell
   New-GPLink -Name "InfraMonitor-Agent-Deployment" -Target "OU=Servers,DC=yourdomain,DC=com" -Enforced Yes
   ```

---

### Strategy B: Manual Deployment Script (for specific servers)

```powershell
# On each target server:
$ServerUrl = "https://InfraMonitor.yourdomain.com"
$AgentKey = "sk_prod_1a2b3c4d5e6f7g8h9i0j..."

Invoke-Expression (Invoke-WebRequest -Uri "$ServerUrl/api/v2/agent/install-script" -UseBasicParsing).Content |
    Invoke-Expression @{SERVER_URL=$ServerUrl; AGENT_KEY=$AgentKey}
```

---

### Strategy C: Remote Deployment via Ansible/WinRM

```yaml
---
- name: Deploy InfraMonitor Agent
  hosts: all
  vars:
    server_url: "https://InfraMonitor.yourdomain.com"
    agent_key: "{{ vault_agent_key }}"

  tasks:
    - name: Create agent directory
      win_file:
        path: 'C:\Program Files\InfraMonitor\Agent'
        state: directory

    - name: Download agent package
      win_get_url:
        url: "{{ server_url }}/api/v2/agent/download"
        dest: '%TEMP%\InfraMonitor-agent.zip'

    - name: Extract agent
      win_unzip:
        src: '%TEMP%\InfraMonitor-agent.zip'
        dest: 'C:\Program Files\InfraMonitor\Agent'

    - name: Configure agent
      win_template:
        src: agent_config.json.j2
        dest: 'C:\Program Files\InfraMonitor\Agent\agent_config.json'

    - name: Install Windows Service
      win_shell: |
        nssm install InfraMonitorAgent python C:\Program Files\InfraMonitor\Agent\agent.py
        nssm start InfraMonitorAgent
```

---

## 📊 Phase 4: Post-Deployment Validation

### Check Agent Connectivity

```powershell
# On InfraMonitor Portal
# Navigate: Dashboard → Servers
# Filter by Status = "Agent Installed"

# Should see all deployed agents with:
# ✅ Last Heartbeat: <1 minute ago
# ✅ CPU/RAM/Disk metrics updating
# ✅ Active application detection (if user logged in)
```

### Test Remote Command Execution

```powershell
# Via Portal: System Controls → Terminal
# Command: Get-ComputerInfo
# Expected: Full system info returned within 10 seconds
```

### Test Software Detection

```powershell
# Via Portal: System Controls → Software
# Should see list of 30+ installed applications
# Try: "Uninstall Chrome" → Queue → Verify execution
```

---

## 🔒 Security Configuration

### 1. Network Security

```powershell
# Firewall Rules (on monitoring server)
New-NetFirewallRule -DisplayName "InfraMonitor Inbound" `
    -Direction Inbound -LocalPort 5000 -Protocol TCP `
    -Action Allow -RemoteAddress 10.0.0.0/8

# Restrict to internal network only
New-NetFirewallRule -DisplayName "InfraMonitor Admin" `
    -Direction Inbound -LocalPort 5001 -Protocol TCP `
    -Action Allow -RemoteAddress 192.168.1.0/24
```

### 2. Database Security

```sql
-- PostgreSQL: Create minimal privilege user for agent
CREATE USER agent_readonly WITH PASSWORD 'ReadOnlyPassword123!';
GRANT CONNECT ON DATABASE InfraMonitor_org TO agent_readonly;
GRANT USAGE ON SCHEMA public TO agent_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO agent_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO agent_readonly;
```

### 3. API Token Rotation

```powershell
# Schedule monthly rotation
$TaskAction = New-ScheduledTaskAction -Execute "python" `
    -Argument "C:\InfraMonitor\rotate_api_tokens.py"
$TaskTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday `
    -At 02:00AM
Register-ScheduledTask -Action $TaskAction -Trigger $TaskTrigger `
    -TaskName "InfraMonitor-Token-Rotation" -RunLevel Highest
```

---

## 📈 Monitoring & Maintenance

### Dashboard Setup

1. **Create Dashboards:** Portal → Dashboards → New
2. **Add Widgets:**
   - Server Status Grid
   - CPU/Memory Utilization
   - Productivity Timeline
   - Command Execution History
   - Alert Status

### Alerts Configuration

```powershell
# CPU > 80% for 5 minutes
New-Alert -Name "High CPU" -Condition "cpu_percent > 80" `
    -Duration "5m" -Action "SendEmail"

# Agent offline > 30 minutes
New-Alert -Name "Agent Offline" -Condition "heartbeat_age > 30m" `
    -Duration "5m" -Action "SendAlert"

# Suspicious activity detected
New-Alert -Name "Suspicious Command" -Condition "command_type == 'delete_system'" `
    -Duration "0m" -Action "BlockExecution,NotifyAdmin"
```

### Backup Strategy

```powershell
# Daily database backups
$BackupPath = "\\backup-server\InfraMonitor-backups"
$BackupFile = "$BackupPath\InfraMonitor_$(Get-Date -Format 'yyyyMMdd_HHmmss').sql"

pg_dump -U InfraMonitor_user InfraMonitor_org |
    gzip > $BackupFile

# Retain 30 days
Get-ChildItem $BackupPath -Filter "InfraMonitor_*.sql.gz" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
    Remove-Item
```

---

## 🐛 Troubleshooting

### Agent Won't Connect

```powershell
# Check configuration
Get-Content "C:\Program Files\InfraMonitor\Agent\agent_config.json"

# Verify network connectivity
Test-NetConnection -ComputerName InfraMonitor.yourdomain.com -Port 5000

# Check service status
Get-Service InfraMonitorAgent | Select-Object Name, Status, StartType

# View logs
Get-Content "C:\Program Files\InfraMonitor\Agent\agent.log" -Tail 50
```

### High Memory Usage

```powershell
# Check metric retention
# Portal Settings → Data Retention → Adjust from 90 days to 30 days

# Archive old metrics
python archiveMetrics.py --days 90
```

### Slow Dashboard

```powershell
# Verify database indexes
EXPLAIN ANALYZE SELECT * FROM metric WHERE timestamp > NOW() - INTERVAL '7 days';

# Increase connection pool
# Update DATABASE_URL pool configuration
DATABASE_URL=postgresql://user:pass@host/db?connect_timeout=10&pool_size=20
```

---

## 📞 Support & Escalation

| Issue              | Contact             | Priority |
| ------------------ | ------------------- | -------- |
| Agent deployment   | IT Operations       | P2       |
| Portal access      | Help Desk           | P3       |
| Performance issues | Infrastructure Team | P1       |
| Security concerns  | IT Security         | P0       |
| Billing/Licensing  | Finance             | P3       |

---

## 🎯 Success Criteria

- ✅ 100% of servers showing as "Connected" in Portal
- ✅ Metrics updating every 5 minutes (< 2 minute latency)
- ✅ Remote commands executing within 10 seconds
- ✅ Software detection working on 95%+ of servers
- ✅ Productivity tracking showing active users
- ✅ No agent-related support tickets in first 48 hours

---

**Next Steps:**

1. Provision central server infrastructure
2. Configure PostgreSQL database
3. Create first API key for pilot deployment
4. Deploy to 5-10 pilot systems
5. Validate and scale to full organization
