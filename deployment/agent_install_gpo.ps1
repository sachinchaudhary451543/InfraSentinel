# ServerMonitor Agent - GPO Deployment Script
# 
# Instructions:
# 1. Place agent.py and nssm.exe in a network share accessible by Domain Computers (e.g., \\Server\Deploy$)
# 2. Update the variables below to match your environment. Do NOT commit the API_KEY to public source control.
# 3. Create a Group Policy Object (GPO) and add this as a Startup Script (Computer Configuration -> Policies -> Windows Settings -> Scripts -> Startup).

$LogFile = "C:\Windows\Temp\ServerMonitor_Agent_Install.log"
function Write-Log {
    param([string]$Message)
    $TimeStamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$TimeStamp - $Message" | Out-File $LogFile -Append
}

Write-Log "Starting ServerMonitor Agent installation process."

# ====================================================================
# CONFIGURATION - UPDATE THESE FOR YOUR ENVIRONMENT
# ====================================================================
$DeployShare = "\\YOUR-SERVER\Deploy$\ServerMonitor"
$InstallDir = "C:\Program Files\ServerMonitorAgent"

# Ensure you use a secure mechanism for the API_KEY if possible, or leave blank to require manual portal generation
$ApiUrl = "http://monitor.yourcompany.com"
$ApiKey = "YOUR_TENANT_AGENT_KEY" 
# ====================================================================

# Check if already installed
if (Get-Service -Name "ServerMonitorAgent" -ErrorAction SilentlyContinue) {
    Write-Log "ServerMonitorAgent service is already installed. Exiting."
    exit 0
}

Write-Log "Creating installation directory: $InstallDir"
if (-Not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
}

# Copy files from deploy share
Write-Log "Copying agent files from $DeployShare"
try {
    Copy-Item -Path "$DeployShare\agent.py" -Destination "$InstallDir\agent.py" -Force
    Copy-Item -Path "$DeployShare\nssm.exe" -Destination "$InstallDir\nssm.exe" -Force
} catch {
    Write-Log "Failed to copy files: $_"
    exit 1
}

# Find Python installation
$PythonPath = ""
if (Test-Path "C:\Program Files\Python310\python.exe") { $PythonPath = "C:\Program Files\Python310\python.exe" }
elseif (Test-Path "C:\Program Files\Python311\python.exe") { $PythonPath = "C:\Program Files\Python311\python.exe" }
elseif (Test-Path "C:\Program Files\Python312\python.exe") { $PythonPath = "C:\Program Files\Python312\python.exe" }
else {
    $PythonPath = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
}

if (-Not $PythonPath) {
    Write-Log "Python not found! Cannot install agent service."
    exit 1
}

Write-Log "Found Python at: $PythonPath"

# Install NSSM Service
Write-Log "Installing NSSM Service"
$NssmPath = "$InstallDir\nssm.exe"
$AgentScript = "$InstallDir\agent.py"

& $NssmPath install ServerMonitorAgent "$PythonPath" "$AgentScript --url $ApiUrl --key $ApiKey"
& $NssmPath set ServerMonitorAgent AppDirectory "$InstallDir"
& $NssmPath set ServerMonitorAgent AppStdout "$InstallDir\agent.log"
& $NssmPath set ServerMonitorAgent AppStderr "$InstallDir\agent_error.log"
& $NssmPath set ServerMonitorAgent Start SERVICE_AUTO_START
& $NssmPath set ServerMonitorAgent Description "ServerMonitor Telemetry and Control Agent"

Write-Log "Starting Service"
Start-Service -Name "ServerMonitorAgent"

Write-Log "Installation completed successfully."
