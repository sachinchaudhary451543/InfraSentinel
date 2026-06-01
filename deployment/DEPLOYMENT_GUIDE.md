# ServerMonitor Agent — Bulk Deployment Guide

## Overview

This guide walks you through deploying the ServerMonitor Agent to all employee systems via Intune (Microsoft Endpoint Manager) or manual scripts.

**Quick Facts:**
- Deployment method: Windows app (Win32) via Intune or PowerShell script
- Installation time: ~2–5 minutes per device
- Requires: Azure AD enrollment or Intune enrollment
- Detection: Agent registers with portal automatically after install

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Prepare Installer](#prepare-installer)
3. [Create Intune Win32 App](#create-intune-win32-app)
4. [Deploy to Devices](#deploy-to-devices)
5. [Monitor Rollout](#monitor-rollout)
6. [Troubleshoot Failures](#troubleshoot-failures)
7. [Quick Manual Deploy](#quick-manual-deploy)

---

## Prerequisites

### For Intune Deployment
- [ ] Admin access to Microsoft Endpoint Manager (MEM) admin center
- [ ] Devices are Azure AD joined or hybrid
- [ ] Microsoft Intune licenses assigned to devices
- [ ] Windows 10/11 (Build 19041+)

### For Manual Deployment
- [ ] Admin access to each machine
- [ ] PowerShell 5.0+
- [ ] Network connectivity to portal

### General
- [ ] Agent installer file or ZIP package ready
- [ ] Portal URL (e.g., https://servermonitor-web.onrender.com)
- [ ] Agent key/tenant ID from portal admin

---

## Prepare Installer

### Option A: Use Existing Installer
If you have an **MSI or EXE** installer:
1. Test it on a test machine with silent flags:
   ```powershell
   msiexec /i AgentInstaller.msi /qn /norestart
   # OR
   AgentSetup.exe /S /v"/qn"
   ```
2. Verify it creates:
   - Service `ServerMonitorAgent` (or your service name)
   - Registry key `HKLM:\SOFTWARE\ServerMonitor\Agent\Installed = 1`
   - Agent files in `C:\Program Files\ServerMonitor\Agent\`
3. Note the exact silent install and uninstall commands.

### Option B: Create MSI Wrapper (Advanced)
If you only have a PowerShell script:
1. Use tools like **Advanced Installer** or **WiX** to wrap your script into an MSI.
2. The MSI must:
   - Run the script as SYSTEM
   - Create the registry key `HKLM:\SOFTWARE\ServerMonitor\Agent\Installed = 1` on success
   - Return exit code 0 for success

### Option C: Use Provided PowerShell Installer
Edit `deployment/Install-Agent.ps1`:
```powershell
# Update these values:
$PortalUrl = "https://your-portal-url.com"
$TenantKey = "your-agent-key-from-portal"
```

Then package into an MSI:
1. Download **Microsoft Intune Win32 Content Prep Tool** (IntuneWinAppUtil.exe)
2. Create a folder with the PowerShell script:
   ```
   C:\pkg\agent\
   ├── Install-Agent.ps1
   └── README.txt
   ```
3. Package it:
   ```powershell
   .\IntuneWinAppUtil.exe -c C:\pkg\agent -s Install-Agent.ps1 -o C:\pkg\output
   ```
   This produces `Install-Agent.intunewin` ready for Intune.

---

## Create Intune Win32 App

### Step 1: Get IntuneWinAppUtil Tool
1. Download from Microsoft:
   https://github.com/Microsoft/Microsoft-Win32-Content-Prep-Tool/releases
2. Extract and note the path (e.g., `C:\Tools\IntuneWinAppUtil.exe`)

### Step 2: Prepare Installer Package
Create a folder with your installer:
```
C:\pkg\agent\
├── AgentInstaller.msi
├── config.json  (optional)
└── README.txt
```

### Step 3: Create .intunewin Package
```powershell
cd C:\Tools
.\IntuneWinAppUtil.exe -c C:\pkg\agent -s AgentInstaller.msi -o C:\pkg\output
```

Output: `C:\pkg\output\AgentInstaller.intunewin` (~5–50 MB depending on files)

### Step 4: Upload to Intune
1. Go to **Microsoft Endpoint Manager admin center** → **Apps** → **Windows** → **Add**
2. **App type:** "Windows app (Win32)" → **Select**
3. Upload the `.intunewin` file
4. Fill in metadata:
   - **Name:** ServerMonitor Agent
   - **Publisher:** Your Company
   - **Description:** "Monitoring agent for device management and screenshots"
   - **Icon:** (optional)

### Step 5: Configure Installation Settings
1. **Program section:**
   - **Install command:**
     ```
     msiexec /i AgentInstaller.msi /qn /norestart
     ```
   - **Uninstall command:**
     ```
     msiexec /x {PRODUCT-GUID} /qn
     ```
     (Replace `{PRODUCT-GUID}` with your MSI's product code)
   - **Install behavior:** "System" (installs as SYSTEM account)
   - **Device restart behavior:** "No specific action"

2. **Requirements section:**
   - **OS Architecture:** "64-bit" (or both if needed)
   - **Minimum OS:** "Windows 10 (Build 19041)" or higher

### Step 6: Configure Detection Rules
This is **critical** — Intune marks the app installed only if this passes.

**Recommended: Registry-based detection**
1. Click **Add** under Detection rules
2. **Rule type:** "Registry"
3. Configure:
   - **Hive:** "HKEY_LOCAL_MACHINE"
   - **Key path:** "SOFTWARE\ServerMonitor\Agent"
   - **Value name:** "Installed"
   - **Detection method:** "Value exists" or "Equals"
   - **Expected value:** (if using Equals) "1"
4. Click **OK**

Alternative: **File-based detection**
1. **Rule type:** "File"
2. **Path:** "C:\Program Files\ServerMonitor\Agent\agent.exe"
3. **File or folder:** "File"
4. **Detection method:** "File exists"

### Step 7: Configure Return Codes
1. Go to **Return codes** section
2. Map exit codes:
   - **0** → Success
   - **3010** → Success (Restart required) — if your installer returns this
   - **Any other** → Failure (default behavior)

### Step 8: Review & Create
1. Review all settings
2. Click **Create**

---

## Deploy to Devices

### Option 1: Assign to All Devices (Broad Rollout)
1. In the newly created app, go to **Assignments**
2. Click **Add groups**
3. **Assignment type:** "Required"
4. **Add group:** Select "All Devices" (or create a dynamic group)
5. **Availability:** "Devices without user"
6. Click **Save**
7. **Schedule:** Deployment starts immediately or set a future date

### Option 2: Staged Rollout (Recommended)
1. **Phase 1 (Pilot):** Assign to a test group (5–10 devices) as "Required"
2. Monitor for 24–48 hours
3. **Phase 2:** If successful, assign to 25% of devices
4. **Phase 3:** Assign to 50%
5. **Phase 4:** Assign to 100%

### Create a Dynamic Device Group (Optional)
For automated phased rollout:
1. Go to **Microsoft Entra** (Azure AD) → **Groups** → **New group**
2. **Group type:** "Dynamic Device"
3. **Membership rule:** Example:
   ```
   (device.deviceOwnershipType -eq "Company") and (device.operatingSystem -startsWith "Windows")
   ```
4. Click **Create** and wait 5–10 minutes for group to populate

---

## Monitor Rollout

### From Intune Portal
1. Go to the app → **Monitor** → **Device install status**
2. View:
   - **Succeeded:** Installation successful
   - **Failed:** Installation did not complete
   - **Pending:** Waiting to be processed by device
   - **Not Applicable:** Device doesn't meet requirements

### Check Per-Device Details
1. Click on a failed device name → **View failure details**
2. Look for:
   - Content download errors (network/proxy issue)
   - Installer errors (check return codes)
   - Detection rule failures (registry key not found)

### View Device Logs
On each device, check:
```powershell
# Intune Management Extension log
Get-Content 'C:\ProgramData\Microsoft\IntuneManagementExtension\Logs\IntuneManagementExtension.log' -Tail 100

# Or run diagnostic script
cd C:\
powershell -ExecutionPolicy Bypass -File "\\SERVER\share\Diagnose-AgentInstall.ps1"
```

---

## Troubleshoot Failures

### Problem: "Failed" Status in Intune

**Step 1: Check Device Logs**
Run on the failing device (as Administrator):
```powershell
# Option A: Use provided diagnostic script
C:\Temp\Diagnose-AgentInstall.ps1

# Option B: Manual logs
tail -f 'C:\ProgramData\Microsoft\IntuneManagementExtension\Logs\IntuneManagementExtension.log'
Get-WinEvent -LogName "Application" -MaxEvents 50 | Select-Object TimeCreated, Message
```

**Step 2: Common Errors**
| Error | Cause | Fix |
|-------|-------|-----|
| 0x80070005 | Access denied | Ensure app installs as SYSTEM; check file permissions |
| 0x80070002 | File not found | Content download failed; check network/proxy |
| 0x80070003 | Path not found | Invalid install path; check command syntax |
| Registry key not found | Detection rule failed | Verify installer creates correct registry key |
| Service not running | Service failed to start | Check service log; verify dependencies |

**Step 3: Manual Test**
Reproduce the install on the failing device:
```powershell
# Download the MSI from Intune content host (from Intune logs)
$url = "https://...blob.core.windows.net/...AgentInstaller.intunewin"
# Or use the IntuneWinAppUtil to extract .intunewin:
# The .intunewin is a ZIP; rename to .zip and extract to see MSI

# Test silent install
msiexec /i AgentInstaller.msi /qn /l*v C:\temp\install.log /norestart

# Check exit code
echo $LASTEXITCODE

# Check registry
Get-ItemProperty -Path 'HKLM:\SOFTWARE\ServerMonitor\Agent' -ErrorAction SilentlyContinue

# Check service
Get-Service -Name ServerMonitorAgent
```

### Problem: "Agent Installed But Not Visible in Portal"

Check on the device:
1. **Agent is running?**
   ```powershell
   Get-Service -Name ServerMonitorAgent | Select Status
   ```
2. **Agent can reach portal?**
   ```powershell
   Test-NetConnection -ComputerName servermonitor-web.onrender.com -Port 443
   ```
3. **Agent config correct?**
   ```powershell
   Get-Content "C:\Program Files\ServerMonitor\Agent\config.json" | ConvertFrom-Json
   ```
4. **Check agent logs:**
   ```powershell
   Get-Content "C:\Program Files\ServerMonitor\Agent\logs\agent.log" -Tail 50
   ```

**If network is blocked:** Ensure antivirus/firewall allows outbound to portal domain.

---

## Quick Manual Deploy

### For Testing on One Machine
1. Save `Install-Agent.ps1` locally
2. Run as Administrator:
   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   C:\path\to\Install-Agent.ps1 -PortalUrl "https://your-portal" -TenantKey "your-key"
   ```
3. Check result:
   ```powershell
   Get-Service -Name ServerMonitorAgent
   Get-ItemProperty -Path "HKLM:\SOFTWARE\ServerMonitor\Agent"
   ```

### For Network Deployment (Group Policy or Script)
1. Place scripts on a network share (e.g., `\\fileserver\Deploy\`)
2. Create a Group Policy or scheduled task to run:
   ```batch
   powershell -ExecutionPolicy Bypass -File "\\fileserver\Deploy\Install-Agent.ps1"
   ```
3. Deploy to OUs and monitor logs

---

## Deployment Checklist

- [ ] Installer tested and working (silent install passes)
- [ ] .intunewin package created and verified
- [ ] Win32 app uploaded to Intune
- [ ] Installation command configured correctly
- [ ] Uninstall command configured correctly
- [ ] Detection rule verified (matches actual installation)
- [ ] Return codes mapped appropriately
- [ ] Pilot group (5–10 devices) assigned as Required
- [ ] Pilot devices verified successful install in 24 hours
- [ ] Portal shows pilot devices registered
- [ ] Rollout to next phase (25%, 50%, 100%)
- [ ] Overall deployment monitored for 1 week
- [ ] Troubleshooting documented for support team

---

## Support & Logs

### Device-Side Diagnostic
**Run on any employee device:**
```powershell
powershell -ExecutionPolicy Bypass -File "C:\Temp\Diagnose-AgentInstall.ps1"
```
Generates a summary with recommendations.

### Server-Side Diagnostics
Check portal:
1. Admin → Registered Agents
2. Filter by status (Online, Offline, Pending registration)
3. Check heartbeat age and last activity

---

## Contact & Escalation

For deployment issues, collect:
- Device hostname
- Output of `Diagnose-AgentInstall.ps1`
- Intune app failure details
- IntuneManagementExtension.log (last 100 lines)
- Agent config and logs from `C:\Program Files\ServerMonitor\Agent\`

Then escalate to: your-admin@company.com

---

**Document Version:** 1.0  
**Last Updated:** 2026-06-01  
**Next Review:** 2026-07-01
