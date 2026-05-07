# Agent Management - Support Runbook

**For:** IT Support Engineers & System Administrators  
**Version:** 2.0  
**Last Updated:** April 20, 2026

---

## Table of Contents

1. [Quick Diagnosis](#quick-diagnosis)
2. [Common Issues](#common-issues)
3. [Advanced Troubleshooting](#advanced-troubleshooting)
4. [Log Analysis](#log-analysis)
5. [Command Reference](#command-reference)

---

## Quick Diagnosis

### Issue: Server showing "Offline" in dashboard

**Step 1: Verify Network Connectivity (30 seconds)**

```powershell
# From monitoring station or your workstation
$serverName = "SERVERNAME"

# Test ping
Test-Connection -ComputerName $serverName -Count 1
# Expected: Reply from X.X.X.X: bytes=32 ...
# If fails: Network connectivity issue - contact network team

# Test RDP port
$port = 3389
$sock = New-Object System.Net.Sockets.TcpClient
$sock.Connect($serverName, $port)
$sock.Close()
# If no error: RDP available
```

**Step 2: Check Agent Service Status (1 minute)**

```powershell
# RDP to server
mstsc /v:$serverName

# On server, check agent service
Get-Service *ServerMonitor* -ErrorAction SilentlyContinue |
  Select Name, Status, StartType

# Expected output:
# Name                      Status StartType
# ----                      ------ ---------
# ServerMonitorAgent         Running Automatic
```

**Step 3: Review Recent Logs (2 minutes)**

```powershell
# Check Event Viewer
Get-EventLog Application -Source ServerMonitorAgent -Newest 5 |
  Format-List TimeGenerated, eventid, Message
```

**Step 4: Try Agent Restart (1 minute)**

- Go to Dashboard → select offline server
- Click **"Trigger Agent Restart"** button
- Wait 60 seconds
- Check if agent comes online
- **Success?** Problem solved, document and close
- **Failure?** Continue to [Common Issues](#common-issues)

---

## Common Issues

### Issue #1: Agent Service Not Running

**Diagnosis:**

```powershell
Get-Service ServerMonitorAgent | Select Status
# Returns: "Stopped" instead of "Running"

# Check startup type
Get-Service ServerMonitorAgent | Select StartType
# Should be: "Automatic"
```

**Solution A: Manual Restart**

```powershell
# Start the service
Start-Service ServerMonitorAgent

# Verify
Get-Service ServerMonitorAgent | Select Status
# Should show: Running

# Check Event Viewer for startup errors
Get-EventLog Application -Source ServerMonitorAgent -Newest 1 |
  Select TimeGenerated, Message
```

**Solution B: Restart Dependencies First**

```powershell
# Agent depends on being able to:
# 1. Resolve DNS
Get-Service dnsclient | Select Status
# 2. Access network
Get-NetAdapter | Select Status

# If DNS/network unhealthy, fix those first
# Then restart agent
Start-Service ServerMonitorAgent
```

**Solution C: Reinstall Agent**

```powershell
# If start fails repeatedly:

# 1. Stop service
Stop-Service ServerMonitorAgent -Force

# 2. Uninstall
$agentPath = "C:\Program Files\ServerMonitorAgent"
if (Test-Path $agentPath) {
    Remove-Item $agentPath -Recurse -Force
}

# 3. Request IT to reinstall via MDM/SCCM

# 4. Verify installation
Get-Service ServerMonitorAgent -ErrorAction SilentlyContinue
```

**Expected Outcome:** Service shows "Running", agent goes online within 60 sec

---

### Issue #2: Agent Offline Despite Service Running

**Diagnosis:**

```powershell
# Service is running...
Get-Service ServerMonitorAgent | Select Status
# Returns: Running

# But agent still offline in dashboard after 3+ minutes
# Indicates: Network connectivity between agent and central service
```

**Check Network Connectivity:**

```powershell
$apiEndpoint = "https://monitoring.company.com/api/health"

# Test connectivity from agent server
$result = Invoke-WebRequest -Uri $apiEndpoint -UseBasicParsing
if ($result.StatusCode -eq 200) {
    Write-Host "✓ API reachable"
} else {
    Write-Host "✗ API unreachable - Status: $($result.StatusCode)"
}
```

**Possible Causes & Solutions:**

1. **Firewall blocking agent traffic**

   ```powershell
   # Check firewall rules
   Get-NetFirewallRule -DisplayName "*ServerMonitor*" |
     Select DisplayName, Enabled, Direction

   # If not enabled, enable them:
   Enable-NetFirewallRule -DisplayName "ServerMonitorAgent-Outbound"
   ```

2. **Proxy authentication required**

   ```powershell
   # Check if proxy is configured
   netsh winhttp show proxy

   # If proxy shown, verify agent has credentials:
   reg query "HKLM\Software\ServerMonitor" /v ProxyUsername
   ```

3. **DNS resolution failure**

   ```powershell
   # Verify DNS
   Resolve-DnsName monitoring.company.com
   # Should return IP address

   # Check agent DNS config
   Get-Content "C:\Program Files\ServerMonitorAgent\config.json" |
     findstr /i "dns"
   ```

4. **API endpoint down**
   ```powershell
   # Test from multiple servers
   $servers = "SERVER1", "SERVER2"
   foreach ($srv in $servers) {
       Invoke-Command -ComputerName $srv -ScriptBlock {
           Invoke-WebRequest -Uri "https://monitoring.company.com/api/health"
       }
   }
   # If all fail: Escalate to backend team
   ```

---

### Issue #3: "ERR_DUPLICATE_COMMAND" Error

**When User Sees:** "Command in progress. Existing restart attempt (ID: restart_12345) from 2 minutes ago"

**Diagnosis:**

```sql
-- Check command history
SELECT command_id, server_id, status, created_at
FROM remote_command
WHERE server_id = ?
  AND action = 'restart_agent'
  AND created_at > datetime('now', '-5 minutes')
ORDER BY created_at DESC;

-- Expected: One pending command
-- If multiple pending: Queue issue
```

**Solution:**

1. **If first restart is stuck:**

   ```sql
   -- Update stuck command to failed
   UPDATE remote_command
   SET status = 'failed', error = 'Timeout after 5 min'
   WHERE command_id = 'restart_12345';

   -- Now user can retry
   ```

2. **If agent already restarted:**
   - Command may have succeeded but status not updated
   - Agent should come online within 60 sec
   - If still offline, see [Issue #2](#issue-2-agent-offline-despite-service-running)

**Expected Outcome:** After 5 minutes or manual failure update, user can retry

---

### Issue #4: "ERR_QUEUE_FULL" Error

**When User Sees:** "Too many restart commands pending (10 already pending)"

**Diagnosis:**

```sql
-- Check queue depth
SELECT server_id, COUNT(*) as pending_count
FROM remote_command
WHERE status = 'pending'
GROUP BY server_id
ORDER BY pending_count DESC;

-- Critical if: pending_count > 10 for one server
```

**Immediate Actions:**

1. **Check if agent is hung:**

   ```powershell
   # RDP to server
   Get-Process -Name ServerMonitorAgent | Select Handles, WorkingSet
   # If memory > 500 MB: Process may be hung

   # Force restart
   Stop-Process -Name ServerMonitorAgent -Force
   Start-Service ServerMonitorAgent
   ```

2. **Clear stuck commands:**

   ```sql
   -- Mark old pending commands as failed
   UPDATE remote_command
   SET status = 'failed',
       error = 'Cleared - queue overflow'
   WHERE status = 'pending'
     AND created_at < datetime('now', '-10 minutes')
     AND action = 'restart_agent';

   -- Verify
   SELECT COUNT(*) FROM remote_command
     WHERE status = 'pending';
   -- Should now be < 10
   ```

3. **Monitor recovery:**
   - Check agent comes online
   - Commands should process
   - Queue depth should decrease

**Expected Outcome:** Queue clears within 2-3 minutes as commands execute

---

## Advanced Troubleshooting

### Scenario: Agent won't restart, firewall enabled, API reachable

**Complete diagnostic sequence:**

```powershell
$serverName = "PROBLEMATIC-SERVER"

# Run comprehensive checks
Write-Host "=== AGENT HEALTH CHECK ===" -ForegroundColor Green
Write-Host "1. Service Status:"
Get-Service ServerMonitorAgent | Select Name, Status, StartType

Write-Host "`n2. Process Memory:"
Get-Process ServerMonitorAgent -ErrorAction SilentlyContinue |
  Select Name, Handles, WorkingSet, @{n='Memory_MB';e={$_.WorkingSet/1MB}}

Write-Host "`n3. Recent Errors:"
Get-EventLog Application -Source ServerMonitorAgent -Newest 3 |
  Select TimeGenerated, EventID, Message

Write-Host "`n4. Agent Config:"
Get-Content "C:\Program Files\ServerMonitorAgent\config.json"

Write-Host "`n5. Network Connectivity:"
Test-Connection -ComputerName "monitoring.company.com" -Count 1

Write-Host "`n6. Certificate Validation:"
[System.Net.ServicePointManager]::ServerCertificateValidationCallback = {$true}
$api = Invoke-WebRequest -Uri "https://monitoring.company.com/api/health" -UseBasicParsing
$api.StatusCode
```

**If all checks pass but agent still offline:**

```powershell
# Enable verbose logging
reg add "HKLM\Software\ServerMonitor" /v LogLevel /d "DEBUG" /f

# Restart service and collect logs immediately
Stop-Service ServerMonitorAgent
[System.Threading.Thread]::Sleep(2000)
Start-Service ServerMonitorAgent

# Wait 30 seconds
[System.Threading.Thread]::Sleep(30000)

# Get recent logs
Get-ChildItem "C:\ProgramData\ServerMonitor\logs" -Filter "*.log" |
  Get-Content -Tail 50
```

**Contact escalation:** If logs show network timeouts, escalate to Network/firewall team

---

## Log Analysis

### Where Agent Logs Live

```powershell
# Local agent logs (on each server)
$agentLogPath = "C:\ProgramData\ServerMonitor\logs"
Get-ChildItem $agentLogPath

# Central monitoring logs (on central service)
$centralLogPath = "\\monitoring-server\logs\agents"
Get-ChildItem $centralLogPath | Where Name -like "*.log"
```

### Reading Agent Logs

```powershell
# Follow live logs
Get-Content "C:\ProgramData\ServerMonitor\logs\agent-latest.log" -Wait

# Search for specific errors
Select-String "ERROR|WARN" `
  "C:\ProgramData\ServerMonitor\logs\agent-latest.log" |
  Format-List LineNumber, Line
```

### Interpreting Common Log Entries

**✅ GOOD:**

```
2026-04-20 10:15:23 [INFO] Connected to central API
2026-04-20 10:15:24 [INFO] Metrics sent: CPU=45% RAM=62%
2026-04-20 10:15:30 [INFO] Command received: restart_agent
2026-04-20 10:15:31 [INFO] Restarting agent service...
```

**❌ BAD:**

```
2026-04-20 10:15:23 [ERROR] Connection timed out (5s)
2026-04-20 10:15:24 [ERROR] Certificate validation failed
2026-04-20 10:15:25 [WARN] Retrying connection (attempt 3/5)
2026-04-20 10:15:45 [ERROR] Max retries exceeded, going offline
```

---

## Command Reference

### PowerShell Commands

```powershell
# Service Management
Get-Service ServerMonitorAgent | Select Status, StartType
Start-Service ServerMonitorAgent
Stop-Service ServerMonitorAgent -Force
Restart-Service ServerMonitorAgent

# Event Log Analysis
Get-EventLog Application -Source ServerMonitorAgent -Newest 10
Get-EventLog Application -Source ServerMonitorAgent |
  Where EventID -eq 1000  # Error events

# Registry Check
reg query "HKLM\Software\ServerMonitor"
reg add "HKLM\Software\ServerMonitor" /v LogLevel /d "DEBUG" /f

# Network Diagnostics
Test-Connection -ComputerName "monitoring.company.com"
Test-NetConnection -ComputerName "monitoring.company.com" -Port 443
Resolve-DnsName "monitoring.company.com"
```

### SQL Queries

```sql
-- Check agent status
SELECT server_id, hostname, last_seen,
       CASE WHEN last_seen < datetime('now', '-1 minute')
         THEN 'OFFLINE' ELSE 'ONLINE' END as status
FROM server
ORDER BY last_seen DESC;

-- Check restart command history
SELECT command_id, server_id, status, created_at, error
FROM remote_command
WHERE action = 'restart_agent'
  AND created_at > datetime('now', '-24 hours')
ORDER BY created_at DESC;

-- Check restart failures
SELECT server_id, COUNT(*) as failure_count,
       MAX(created_at) as last_failure
FROM remote_command
WHERE action = 'restart_agent'
  AND status = 'failed'
  AND created_at > datetime('now', '-7 days')
GROUP BY server_id
HAVING failure_count > 3;
```

---

## Escalation Checklist

**Escalate to Backend Team when:**

- [ ] Multiple servers offline simultaneously
- [ ] All networks can reach API but agent won't connect
- [ ] API endpoint returning 500 errors
- [ ] Database showing duplicate commands
- [ ] Agent logs show certificate validation failures

**Escalate to Network Team when:**

- [ ] Firewall rule missing for agent ports
- [ ] Proxy authentication failing
- [ ] DNS resolution failing
- [ ] Tracert shows packet loss to API

**Escalate to IT Service Desk when:**

- [ ] Agent needs reinstallation
- [ ] Server out of support
- [ ] Hardware failure suspected
- [ ] User needs permissions changed

---

## Known Limitations & Workarounds

| Issue                        | Limitation                       | Workaround                               |
| ---------------------------- | -------------------------------- | ---------------------------------------- |
| Restart takes 60+ sec        | Agent may take time to reconnect | Check "Last Seen" field, not just on/off |
| Can't batch restart          | Only one server at a time        | Use PowerShell script to loop restarts   |
| No auto-restart              | Must be manual triggered         | Submitting feature request for Phase 2   |
| Restart within 5 min blocked | Duplicate prevention             | Document original request, wait time     |

---

## Troubleshooting Decision Tree

```
Server offline?
├─ Can ping?
│  ├─ YES → Service running?
│  │        ├─ YES → Network to API?
│  │        │        ├─ YES → Check logs (advanced troubleshooting)
│  │        │        └─ NO → Firewall/network team
│  │        └─ NO → Start service (Solution A)
│  └─ NO → Network connectivity issue
│           └─ Network team
└─ Service visible?
   ├─ YES → Reinstall (Solution C)
   └─ NO → Agent not installed (deploy via MDM)
```

---

## Feedback & Continuous Improvement

**Issues found in this runbook?**

- Email: itsupport@company.com
- Subject: "Agent Troubleshooting Runbook - [specific issue]"

**Suggest new diagnostic procedure?**

- Submit via internal wiki with details and results

---

## Version History

| Version | Date       | Changes                                     |
| ------- | ---------- | ------------------------------------------- |
| 2.0     | 2026-04-20 | Expanded with advanced diagnostic scenarios |
| 1.0     | 2026-04-18 | Initial release                             |
