# PowerShell installer for Server Agent
# Usage: Run as Administrator

$AgentExe = "server_agent.exe"
$InstallDir = "C:\Program Files\ServerAgent"
$TaskName = "ServerAgentMonitor"

# Create install directory if it doesn't exist
if (!(Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir | Out-Null
}

# Copy the agent executable
Copy-Item -Path $AgentExe -Destination $InstallDir -Force

# Register scheduled task to run at startup
$Action = New-ScheduledTaskAction -Execute "$InstallDir\$AgentExe"
$Trigger = New-ScheduledTaskTrigger -AtStartup
$Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# Remove existing task if present
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal

Write-Host "Server Agent installed and set to auto-start on boot."
