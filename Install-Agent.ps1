# ServerMonitor Agent Installer with Service Auto-Start
# =====================================================
# One-command installation of the monitoring agent with auto-start on Windows
#
# Usage:
#   .\Install-Agent.ps1 -AgentKey "YOUR_KEY" -ServerUrl "https://portal:8080" -AutoStart
#
# This script:
#   1. Creates agent configuration
#   2. Registers as Windows Service for auto-start
#   3. Starts monitoring immediately
#   4. Persists across system restarts

param(
    [Parameter(Mandatory = $true)]
    [string]$AgentKey,
    
    [Parameter(Mandatory = $true)]
    [string]$ServerUrl,
    
    [int]$IntervalSeconds = 30,
    
    [switch]$AutoStart = $false,
    
    [string]$InstallPath = "C:\Program Files\ServerMonitor\Agent"
)

$ErrorActionPreference = "Stop"
$WarningPreference = "SilentlyContinue"

function Write-Status {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $prefix = switch ($Level) {
        "SUCCESS" { "✓" }
        "ERROR" { "✗" }
        "WARNING" { "⚠" }
        default { "•" }
    }
    Write-Host "[$timestamp] $prefix $Message" -ForegroundColor $(
        switch ($Level) {
            "SUCCESS" { "Green" }
            "ERROR" { "Red" }
            "WARNING" { "Yellow" }
            default { "Cyan" }
        }
    )
}

function Test-AdminPrivileges {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Install-AgentService {
    # Check for admin privileges
    if (-not (Test-AdminPrivileges)) {
        Write-Status "Administrator privileges required. Please run PowerShell as Administrator." "ERROR"
        exit 1
    }
    
    Write-Status "ServerMonitor Agent Installer"
    Write-Status "========================================"
    
    # Create installation directory
    if (-not (Test-Path $InstallPath)) {
        Write-Status "Creating installation directory: $InstallPath"
        New-Item -ItemType Directory -Path $InstallPath -Force | Out-Null
    }
    
    # Create configuration file
    $configPath = Join-Path $InstallPath "agent_config.json"
    $config = @{
        AGENT_KEY    = $AgentKey
        SERVER_URL   = $ServerUrl
        INTERVAL     = $IntervalSeconds
        SERVICE_MODE = $true
        INSTALLED_AT = (Get-Date -Format "o")
        HOSTNAME     = $env:COMPUTERNAME
    }
    
    $config | ConvertTo-Json | Out-File -FilePath $configPath -Encoding UTF8
    Write-Status "Configuration saved: $configPath"
    
    # Create service startup script
    $servicePath = Join-Path $InstallPath "agent_service.bat"
    $agentPyPath = Join-Path $PSScriptRoot "agent.py"
    
    $batchContent = @"
@echo off
REM ServerMonitor Agent Service Launcher
REM This batch file is called by Windows Service Control Manager
cd /d "$InstallPath"
python "$agentPyPath" >> "$InstallPath\service.log" 2>&1
"@
    
    $batchContent | Out-File -FilePath $servicePath -Encoding ASCII -Force
    Write-Status "Service launcher created: $servicePath"
    
    # Install Windows Service
    Write-Status "Installing Windows Service..."
    $serviceName = "ServerMonitorAgent"
    $displayName = "ServerMonitor Agent - $env:COMPUTERNAME"
    
    # Check if service already exists
    $existingService = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($existingService) {
        Write-Status "Service already exists. Removing old service..."
        Stop-Service -Name $serviceName -ErrorAction SilentlyContinue -Force
        Start-Sleep -Seconds 2
        sc.exe delete $serviceName | Out-Null
        Start-Sleep -Seconds 1
    }
    
    # Create new service
    $pythonExe = (Get-Command python).Source
    $serviceCmd = "sc.exe create $serviceName binPath= `"$pythonExe `"$agentPyPath`"`" DisplayName= `"$displayName`" start= auto"
    
    Invoke-Expression $serviceCmd | Out-Null
    
    if ($?) {
        Write-Status "Windows Service installed successfully" "SUCCESS"
        Write-Status "Service Name: $serviceName"
        Write-Status "Service Type: Automatic (Auto-start on boot)"
    }
    else {
        Write-Status "Failed to install Windows Service" "ERROR"
        exit 1
    }
    
    # Set service description
    sc.exe description $serviceName "Monitors system health and sends metrics to ServerMonitor portal" | Out-Null
    
    # Start service if AutoStart is enabled
    if ($AutoStart) {
        Write-Status "Starting service..."
        Start-Service -Name $serviceName -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        
        $svc = Get-Service -Name $serviceName
        if ($svc.Status -eq "Running") {
            Write-Status "Service is running" "SUCCESS"
        }
        else {
            Write-Status "Service failed to start. Check logs." "WARNING"
        }
    }
    
    # Display summary
    Write-Status ""
    Write-Status "Installation Summary"
    Write-Status "========================================"
    Write-Status "Installation Path: $InstallPath"
    Write-Status "Agent Key: $($AgentKey.Substring(0, 10))..."
    Write-Status "Server URL: $ServerUrl"
    Write-Status "Check Interval: ${IntervalSeconds}s"
    Write-Status "Service Name: $serviceName"
    Write-Status "Auto-start Enabled: $AutoStart"
    Write-Status ""
    Write-Status "Next Steps:"
    Write-Status "1. Start service: net start $serviceName"
    Write-Status "2. Stop service: net stop $serviceName"
    Write-Status "3. View logs: $InstallPath\service.log"
    Write-Status "4. Status: Get-Service $serviceName"
}

# Run installation
try {
    Install-AgentService
    Write-Status "Installation completed successfully" "SUCCESS"
}
catch {
    Write-Status "Installation failed: $_" "ERROR"
    exit 1
}
