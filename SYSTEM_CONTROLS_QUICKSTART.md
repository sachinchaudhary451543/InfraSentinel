# Quick Start Guide - System Controls & Agent Deployment

## 🎯 What You Can Do Now

### 1. Execute Remote Commands with Real-Time Output

**Navigate to:**

- Click on any server → System Controls → Terminal section

**How to use:**

```
1. Enter command: Get-ComputerInfo
2. Click "Run" button
3. Watch output appear in real-time (updates every 500ms)
4. See exit code when command completes
5. Check error output if command fails
```

**Example Commands:**

- `whoami` - See current user
- `Get-ComputerInfo` - Computer details
- `Get-Process | Where-Object {$_.CPU -gt 10}` - High CPU processes
- `Restart-Computer -Force` - Restart system (use with caution!)

---

### 2. Install or Uninstall Software

**Navigate to:**

- System Controls → Remote Actions → Software section

**How to use:**

```
1. Enter software name: Chrome
2. Select action: Install or Uninstall
3. Click "Queue"
4. Software will be installed via Chocolatey on the agent
5. Check System Controls History to see results
```

**Supported Packages:**

- Any package in Chocolatey repository
- Examples: Chrome, Firefox, 7zip, VLC, Notepad++, PowerShell-Core

---

### 3. View Command Execution History

**Navigate to:**

- System Controls → View full history at bottom of page

**Shows:**

- All past commands executed on this server
- Command status (pending, running, completed, failed)
- Exit code and execution time
- Who queued the command

---

### 4. Deploy Agent to Discovered Systems

**Navigate to:**

- Agent Portal (top menu) → Domain Discovery tab

**How to use:**

```
1. See list of all discovered systems (from AD or network scan)
2. Find unimported system (status: "Pending")
3. Click "Push Agent" button
4. Confirm deployment in dialog
5. Agent deploys automatically
6. System imported and ready for monitoring
```

**What Happens:**

- PowerShell Remoting connects to target system
- Agent installer downloads and runs
- System appears in "Imported" state
- Productivity tracking starts automatically

---

## 📊 Real-Time Output Example

```
Command: Get-ComputerInfo

Status: pending → running → completed

Output:
PS C:\> Get-ComputerInfo

Name             : WORKSTATION-01
ComputerName     : WORKSTATION-01
DNSHostName      : WORKSTATION-01.domain.com
IPv4Address      : 192.168.1.100
OS               : Windows 10 Pro
Build            : 19045

Exit Code: 0 ✓
```

---

## 🔒 Security & Permissions

**Who can use these features?**

- Only **Superadmin** users can:
  - Execute remote commands
  - Manage software installation
  - Deploy agents to new systems

- **Regular users** can:
  - View command history
  - See discovered systems (read-only)

**All operations are logged:**

- Command executed by whom
- When it was executed
- What the command was
- Results and exit codes

---

## ⚙️ System Requirements

**Agent Service:**

- Must be running on the target server
- Must have connectivity back to the portal
- Must have PowerShell 5.0+ installed (Windows)

**Portal Server:**

- Flask app running (web/app.py)
- Database accessible (SQLite or PostgreSQL)
- API endpoints registered and available

---

## 🐛 Troubleshooting

### Command shows "pending" but never executes?

**Solutions:**

1. Check if agent service is running on target server
2. Check network connectivity to target server
3. Check firewall rules allow agent communication
4. Check agent has permission to execute commands

### Output appears blank or partial?

**Solutions:**

1. Wait a few seconds (command might still be running)
2. Check command syntax (use PowerShell help: `Get-Help Get-Process`)
3. Look at error output section for error details
4. Try simpler command first: `whoami`

### Software install fails?

**Solutions:**

1. Verify Chocolatey is installed on target system
2. Check package name is correct (search on chocolatey.org)
3. Verify agent has admin rights
4. Check software isn't already installed

### Agent deployment shows "Queued" but system doesn't import?

**Solutions:**

1. Check if agent service is running on target
2. Verify PowerShell Remoting is enabled (Windows)
3. Check network connectivity
4. Check target system OS matches deployment method (psremoting for Windows, SSH for Linux)
5. Try manual deployment: Run deployment script on target system

---

## 📈 Monitoring Productivity After Agent Deployment

**After agent is deployed to a system:**

1. Wait ~5 minutes for first data collection
2. Navigate to: System Controls → Productivity tab
3. See real-time productivity metrics:
   - Active time vs Idle time
   - Active applications
   - Window titles and usage
   - Screenshots (if enabled)

4. View trends:
   - Daily productivity chart
   - App usage breakdown
   - Time tracking by task

---

## 🚀 Common Workflows

### Workflow 1: Quick System Diagnostics

```
1. Go to System Controls
2. Run: Get-SystemInfo
3. See full system configuration
4. Check: CPU, RAM, Disk usage
5. Done - no need for RDP!
```

### Workflow 2: Deploy Agent to New System

```
1. Admin runs domain discovery scan
2. Go to Agent Portal → Domain Discovery
3. See discovered system: "MARKETING-PC-02"
4. Click "Push Agent"
5. Wait ~2 minutes
6. Agent now monitoring system
7. Employee productivity tracked automatically
```

### Workflow 3: Install Security Update

```
1. Go to System Controls → Software
2. Enter: SecurityPatch-KB5034129
3. Select: Install
4. Queue command
5. Agent silently installs on background
6. System reboots when ready
7. Check history to confirm success
```

### Workflow 4: Troubleshoot Slow System

```
1. Go to System Controls → Terminal
2. Run: Get-Process | Sort-Object CPU -Descending | Select -First 10
3. See top 10 CPU hogs
4. If found bad process: Get-Process badapp | Stop-Process -Force
5. Monitor in next hour to see improvement
```

---

## 📝 Advanced Commands

### Windows PowerShell

```powershell
# Check disk space
Get-Volume

# See network connections
netstat -an

# Check installed updates
Get-Hotfix | Sort-Object InstalledOn -Descending

# Clear temp files
Remove-Item C:\Windows\Temp\* -Force -Recurse

# Check running services
Get-Service | Where-Object {$_.Status -eq 'Running'}

# See scheduled tasks
Get-ScheduledTask | Where-Object {$_.TaskPath -notlike "\Microsoft*"}
```

### PowerShell (Cross-Platform)

```powershell
# Check system uptime
uptime

# See network info
ipconfig /all

# Monitor performance
Get-Counter -Counter "\Processor(_Total)\% Processor Time"

# List installed software
Get-CimInstance Win32_Product | Select-Object Name, Version
```

---

## 🔧 Configuration Options

### Command Timeout

Default: 120 seconds
Can be changed when queuing command via API

### Polling Interval

Default: 500ms (0.5 seconds)
Set in JavaScript: `setInterval(..., 500)`

### Software Source

Default: Chocolatey
Can be extended to support: Winget, MSI, Installers

---

## 📞 Support

For issues with:

- **Command execution**: Check agent service + network connectivity
- **Agent deployment**: Check target OS + PowerShell Remoting
- **Software install**: Check Chocolatey + package name
- **Output display**: Check browser console for JavaScript errors

See detailed troubleshooting in: `SYSTEM_CONTROL_IMPLEMENTATION.md`

---

**Status:** ✅ All features ready for production use!
