# Quick Reference: Agent Deployment & Portal Fixes

All files are in: `c:\ServerMonitor\deployment\`

---

## 📋 Files Created

### 1. **Install-Agent.ps1** — Silent Agent Installer
- **Purpose:** Deploy agent to a single machine or via Group Policy
- **Usage:**
  ```powershell
  # Test install
  .\Install-Agent.ps1 -PortalUrl "https://your-portal" -TenantKey "your-key"
  
  # Silent (for scripting)
  .\Install-Agent.ps1 -PortalUrl "https://your-portal" -TenantKey "your-key" -Silent $true
  ```
- **Features:**
  - Checks prerequisites
  - Downloads & installs agent
  - Configures as Windows service
  - Sets detection registry keys
  - Starts service
  - Verifies installation

### 2. **Uninstall-Agent.ps1** — Clean Removal
- **Purpose:** Removes agent completely for testing/redeployment
- **Usage:**
  ```powershell
  .\Uninstall-Agent.ps1
  ```
- **Cleans:**
  - Stops & removes service
  - Deletes installation directory
  - Cleans registry keys
  - Removes temp files

### 3. **Diagnose-AgentInstall.ps1** — Troubleshooting Tool
- **Purpose:** Diagnose why agent failed to install on employee devices
- **Usage (on failing device):**
  ```powershell
  .\Diagnose-AgentInstall.ps1
  ```
- **Checks:**
  - Windows version & prerequisites
  - Intune enrollment status
  - Intune logs (last 50 lines)
  - Event Viewer for crashes
  - Network connectivity
  - Service status
  - Registry keys
- **Output:** %TEMP%\AgentDiagnostics_*.txt

### 4. **DEPLOYMENT_GUIDE.md** — Step-by-Step Instructions
- **Sections:**
  1. Prerequisites (Intune license, device requirements)
  2. Prepare installer (test, MSI wrapper, or PowerShell script)
  3. Create Intune Win32 app (upload, configure detection)
  4. Deploy to devices (broad or staged rollout)
  5. Monitor rollout (Intune status page)
  6. Troubleshoot failures (common errors & fixes)
  7. Manual deployment (for testing)
- **Best for:** First-time deployers, pilots, troubleshooting

### 5. **nginx.conf.template** — Reverse Proxy Config
- **Purpose:** Proper routing for Socket.IO WebSocket connections
- **Key sections:**
  - HTTP → HTTPS redirect
  - SSL certificate configuration
  - `/socket.io` endpoint (WebSocket upgrade headers, long timeouts)
  - `/t/<tenant>/socket.io` for multi-tenant
  - `/api` for backend APIs
  - `/static/vendor/` for Socket.IO fallback file
- **Critical settings:**
  - `proxy_buffering off` (for WebSocket)
  - `Upgrade` and `Connection` headers
  - 86400s timeouts for persistent connections
- **Usage:** Copy and customize with your domain/cert paths, then reload NGINX

---

## 🚀 Quick Start: Deploy to Pilot Group

### Step 1: Prepare Installer (5 min)
```powershell
# If you have an MSI, test it:
msiexec /i AgentInstaller.msi /qn /norestart
echo %ERRORLEVEL%  # Should be 0

# Otherwise, use Install-Agent.ps1 and wrap it:
# Download: https://github.com/Microsoft/Microsoft-Win32-Content-Prep-Tool/releases
.\IntuneWinAppUtil.exe -c C:\pkg\agent -s Install-Agent.ps1 -o C:\pkg\output
```

### Step 2: Create Intune App (10 min)
1. Open **Microsoft Endpoint Manager** → **Apps** → **Windows** → **Add**
2. Upload `.intunewin` file
3. **Install command:** `msiexec /i AgentInstaller.msi /qn /norestart`
4. **Detection rule:** Registry → HKLM\SOFTWARE\ServerMonitor\Agent → Installed = 1
5. Click **Create**

### Step 3: Assign to Pilot (2 min)
1. Go to **Assignments** → **Add groups**
2. **Type:** Required
3. **Group:** 5–10 test devices
4. **Save**

### Step 4: Monitor (Wait 24–48 hours)
1. Check **Monitor** → **Device install status**
2. Look for "Succeeded" on all pilot devices
3. Check device in portal (should appear in agent list)

### Step 5: Scale Up (if successful)
1. Create new assignments for 25%, 50%, 100%
2. Space them 24–48 hours apart
3. Watch for failures on each phase

---

## 🔧 Fix Checklist: Socket.IO & Portal Data

### Socket.IO 400 Errors Fixed ✓
- ✅ Multi-CDN loader in `web/templates/base.html`
- ✅ Local fallback at `/static/vendor/socket.io.min.js`
- ✅ NGINX config for WebSocket routing
- ✅ Tenant-aware socket namespace

### Stale Portal Data Fixed ✓
- ✅ Screenshot URLs include `?t=<timestamp>` cache-buster
- ✅ Gallery JSON response includes `Cache-Control: no-store`
- ✅ Portal pages marked no-cache (base.html, asset_management.py)
- ✅ NGINX doesn't cache dynamic endpoints

### Agent Deployment Fixed ✓
- ✅ Intune detection rules documented
- ✅ Silent installer scripts provided
- ✅ Diagnostic tools for troubleshooting
- ✅ Common error codes & solutions documented

---

## ⚠️ Common Failures & Quick Fixes

| Error | Solution |
|-------|----------|
| **Socket.IO 400 error** | ✓ Already fixed; ensure base.html uses CDN loader |
| **Stale screenshots** | ✓ Already fixed; gallery URLs include ?t=timestamp |
| **Agent install "Failed"** | Run Diagnose-AgentInstall.ps1; check detection rule in Intune |
| **Agent running, not in portal** | Check network connectivity; verify config.json on agent machine |
| **WebSocket timeout** | Check NGINX config; ensure proxy_read_timeout ≥ 86400s |
| **MSI install fails** | Test MSI directly: `msiexec /i AgentInstaller.msi /l*v c:\temp\install.log` |

---

## 📞 Deployment Support Info

### Collect This for Troubleshooting
1. Device name/hostname
2. Output of Diagnose-AgentInstall.ps1
3. Intune failure details (from Monitor tab)
4. IntuneManagementExtension.log (last 100 lines)
5. Agent config: `C:\Program Files\ServerMonitor\Agent\config.json`
6. Agent log (if exists): `C:\Program Files\ServerMonitor\Agent\logs\agent.log`

### Manual Test on Device
```powershell
# 1. Check prerequisites
[System.Environment]::OSVersion.VersionString  # Windows 10 Build 19041+

# 2. Try manual install
msiexec /i C:\path\to\AgentInstaller.msi /qn /norestart /l*v C:\temp\install.log

# 3. Check if installed
Get-ItemProperty -Path 'HKLM:\SOFTWARE\ServerMonitor\Agent'

# 4. Check service
Get-Service -Name ServerMonitorAgent

# 5. Check connectivity
Test-NetConnection -ComputerName servermonitor-web.onrender.com -Port 443
```

---

## 🎯 Multi-Tenant Socket.IO (If Applicable)

If your portal uses tenant prefixes (e.g., `/t/company1/`):

1. **Frontend automatically handles it:**
   - `base.html` detects tenant from URL path
   - Sets `window.socketIoBasePath = "/t/company1/socket.io"`
   - Client connects to tenant-specific namespace

2. **NGINX routes it:**
   - Incoming: `wss://portal/t/company1/socket.io`
   - Proxies to: `http://localhost:5000/t/company1/socket.io`
   - Backend handles namespace isolation

3. **No agent code changes needed** — agent connects normally

---

## 📊 Monitoring Commands

### Check Agent Deployments in Intune
```powershell
# If you have Microsoft.Graph module installed:
Connect-MgGraph -Scopes "DeviceManagementApps.Read.All"
Get-MgDeviceAppManagement | Select DisplayName, Status
```

### Check Portal for Registered Agents
Visit: `https://your-portal/admin/agents`
- Shows: Device name, IP, last heartbeat, agent version
- Filters: Status (Online/Offline), department, OS

### Monitor Agent Service on Device
```powershell
# Watch service status
Get-Service ServerMonitorAgent | Select Status, StartType

# Watch recent logs
Get-WinEvent -LogName Application -MaxEvents 20 | Where {$_.Source -like "*Monitor*"}

# Watch network connections
Get-NetTCPConnection | Where {$_.State -eq "Established"} | Select LocalPort, OwningProcess
```

---

## 🔄 Deployment Workflow (Recommended)

```
Week 1:
  Mon: Pilot group (5 devices) assigned as Required
  Tue: Check Intune status → verify all succeeded
  Wed: Check portal → all 5 devices registered & online
  
Week 2:
  Mon: Phase 2 (25% of org) assigned
  Tue–Thu: Monitor logs & support tickets
  
Week 3:
  Mon: Phase 3 (50% of org) assigned
  Tue–Thu: Monitor
  
Week 4:
  Mon: Phase 4 (100% of org) assigned
  Tue–Fri: Monitor & support tail-off
  
Week 5+:
  Ongoing: Monitor for failures, service as needed
```

---

## 📝 Deployment Checklist

**Pre-Deployment:**
- [ ] Installer tested on non-production machine
- [ ] `.intunewin` package created
- [ ] Intune app created & configured
- [ ] Detection rule tested
- [ ] Pilot group created (5–10 devices)

**Deployment:**
- [ ] Pilot assigned as "Required"
- [ ] Waited 24 hours
- [ ] All pilot devices show "Succeeded"
- [ ] Portal shows 5+ devices registered & online
- [ ] No critical errors in support tickets

**Rollout:**
- [ ] Phase 1 (25%) assigned
- [ ] Monitored for 24–48 hours
- [ ] Phase 2 (50%) assigned
- [ ] Monitored for 24–48 hours
- [ ] Phase 3 (100%) assigned
- [ ] Ongoing monitoring & support

---

**Last Updated:** 2026-06-01  
**Deployment Scripts Version:** 1.0  
**Portal Fixes Status:** ✅ Complete
