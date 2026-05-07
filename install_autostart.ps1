# Auto-register ServerMonitor as a Windows Scheduled Task
# Usage: Run as admin after setup

$pythonExe = "{0}\python.exe" -f (Get-Location)
$scriptPath = "{0}\main.py" -f (Get-Location)
$taskName = "ServerMonitor_AutoStart"

# Remove existing task if present
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# Register new task to run at startup
Register-ScheduledTask -TaskName $taskName -Trigger (New-ScheduledTaskTrigger -AtStartup) `
    -Action (New-ScheduledTaskAction -Execute $pythonExe -Argument $scriptPath) `
    -RunLevel Highest -Description "Auto-start ServerMonitor metrics collection and upload" -Force

Write-Host "Scheduled Task '$taskName' created to auto-start ServerMonitor on boot."