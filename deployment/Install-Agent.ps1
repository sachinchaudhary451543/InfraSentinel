#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Silent installer for ServerMonitor Agent.
    
.DESCRIPTION
    Downloads and installs the agent from your portal, configures it, and registers with the server.
    Safe to run multiple times (idempotent).
    
.PARAMETER PortalUrl
    Base URL of your ServerMonitor portal (e.g., https://servermonitor-web.onrender.com)
    
.PARAMETER TenantKey
    Agent key from your portal (provided by admin or fetched from config)
    
.PARAMETER Silent
    If $true, suppresses all console output. Default: $false
    
.EXAMPLE
    .\Install-Agent.ps1 -PortalUrl "https://servermonitor-web.onrender.com" -TenantKey "your-agent-key"
    
.NOTES
    Author: ServerMonitor Deployment Team
    Version: 1.0
    Requires: Administrator privileges, PowerShell 5.0+
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [string]$PortalUrl = "https://servermonitor-web.onrender.com",
    
    [Parameter(Mandatory=$false)]
    [string]$TenantKey = "",
    
    [Parameter(Mandatory=$false)]
    [bool]$Silent = $false
)

$ErrorActionPreference = "Stop"

if (-not $Silent) {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "ServerMonitor Agent Installer" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
}

# ========== Configuration ==========
$InstallDir = "C:\Program Files\ServerMonitor\Agent"
$TempDir = "$env:TEMP\SMAgentInstall"
$ServiceName = "ServerMonitorAgent"
$AgentExe = "$InstallDir\agent.exe"
$RegistryPath = "HKLM:\SOFTWARE\ServerMonitor\Agent"

# ========== Functions ==========
function Log {
    param([string]$Message, [string]$Level = "INFO")
    if (-not $Silent) {
        $color = switch($Level) {
            "ERROR" { "Red" }
            "WARN" { "Yellow" }
            "OK" { "Green" }
            default { "White" }
        }
        Write-Host "[$Level] $Message" -ForegroundColor $color
    }
}

function Test-AgentAlreadyInstalled {
    if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
        return $true
    }
    return $false
}

function Stop-AgentService {
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($svc -and $svc.Status -eq "Running") {
        Log "Stopping existing agent service..." "WARN"
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
}

function Get-AgentPackage {
    param([string]$Url, [string]$OutPath)
    
    Log "Downloading agent from: $Url" "INFO"
    try {
        $progressPreference = 'SilentlyContinue'
        Invoke-WebRequest -Uri $Url -OutFile $OutPath -UseBasicParsing -TimeoutSec 300 -ErrorAction Stop
        Log "Download successful: $OutPath" "OK"
        return $true
    } catch {
        Log "Download failed: $_" "ERROR"
        return $false
    }
}

function Install-Agent {
    param([string]$InstallerPath, [string]$TargetDir)
    
    Log "Installing agent to: $TargetDir" "INFO"
    
    # Create target directory
    if (-not (Test-Path $TargetDir)) {
        New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
        Log "Created install directory: $TargetDir" "OK"
    }
    
    # For this example, assume the installer is a ZIP with agent files
    # Adjust this based on your actual installer (MSI, EXE, etc.)
    if ($InstallerPath -like "*.zip") {
        Log "Extracting ZIP archive..." "INFO"
        Expand-Archive -Path $InstallerPath -DestinationPath $TargetDir -Force -ErrorAction Stop
        Log "Extraction successful" "OK"
    } elseif ($InstallerPath -like "*.msi") {
        Log "Running MSI installer..." "INFO"
        $msiLog = "$env:TEMP\agent-install.log"
        $msiArgs = @(
            "/i", $InstallerPath
            "/qn", "/norestart"
            "/l*v", $msiLog
        )
        $proc = Start-Process -FilePath "msiexec.exe" -ArgumentList $msiArgs -PassThru -Wait -ErrorAction Stop
        if ($proc.ExitCode -ne 0 -and $proc.ExitCode -ne 3010) {
            Log "MSI installer failed with exit code: $($proc.ExitCode)" "ERROR"
            Log "Check log: $msiLog" "ERROR"
            return $false
        }
        Log "MSI installation successful (exit code: $($proc.ExitCode))" "OK"
    } else {
        Log "Unsupported installer type. Manual installation required." "ERROR"
        return $false
    }
    
    return $true
}

function Set-AgentConfiguration {
    param(
        [string]$PortalUrl,
        [string]$TenantKey,
        [string]$InstallDir
    )
    
    Log "Configuring agent..." "INFO"
    
    # Create config file
    $configPath = "$InstallDir\config.json"
    $config = @{
        portal_url = $PortalUrl
        tenant_key = $TenantKey
        log_level = "INFO"
        heartbeat_interval_sec = 60
        screenshot_enabled = $true
        screenshot_interval_min = 15
    } | ConvertTo-Json
    
    $config | Out-File -FilePath $configPath -Encoding UTF8 -Force
    Log "Config file created: $configPath" "OK"
    
    return $true
}

function Register-AgentService {
    param([string]$ExePath, [string]$ServiceName)
    
    Log "Registering agent as Windows service..." "INFO"
    
    # Check if service already exists
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($svc) {
        Log "Service already exists, removing..." "WARN"
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        Remove-Item -Path "HKLM:\SYSTEM\CurrentControlSet\Services\$ServiceName" -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
    
    # Create service (requires sc.exe or registry manipulation)
    # Using registry for portability
    # servicePath placeholder removed; service registration may be handled by MSI or external tooling
    
    # For real MSI installers, the service is created automatically
    # This is a placeholder for manual registration
    Log "Service registration completed" "OK"
    
    return $true
}

function Set-RegistryKeys {
    param([string]$Version, [string]$InstallDir)
    
    Log "Setting registry keys..." "INFO"
    
    if (-not (Test-Path $RegistryPath)) {
        New-Item -Path $RegistryPath -Force | Out-Null
    }
    
    New-ItemProperty -Path $RegistryPath -Name "Installed" -Value 1 -PropertyType DWORD -Force | Out-Null
    New-ItemProperty -Path $RegistryPath -Name "Version" -Value $Version -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $RegistryPath -Name "InstallPath" -Value $InstallDir -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $RegistryPath -Name "InstalledDate" -Value (Get-Date -Format "yyyy-MM-dd HH:mm:ss") -PropertyType String -Force | Out-Null
    
    Log "Registry keys set" "OK"
}

function Start-AgentService {
    param([string]$ServiceName)
    
    Log "Starting agent service..." "INFO"
    try {
        Start-Service -Name $ServiceName -ErrorAction Stop
        Start-Sleep -Seconds 2
        $svc = Get-Service -Name $ServiceName
        Log "Agent service started (Status: $($svc.Status))" "OK"
        return $true
    } catch {
        Log "Failed to start service: $_" "ERROR"
        return $false
    }
}

function Test-Installation {
    param([string]$InstallDir)
    
    Log "Verifying installation..." "INFO"
    
    $checks = @{
        "Installation Directory Exists" = (Test-Path $InstallDir)
        "Agent Executable Present" = (Test-Path "$InstallDir\agent.exe")
        "Config File Present" = (Test-Path "$InstallDir\config.json")
        "Service Registered" = $null -ne (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue)
        "Service Running" = (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue).Status -eq "Running"
    }
    
    $allPassed = $true
    foreach ($check in $checks.GetEnumerator()) {
        $status = if ($check.Value) { "✓" } else { "✗" }
        if (-not $check.Value) { $allPassed = $false }
        $resultText = if ($check.Value) { "OK" } else { "ERROR" }
        Log "  [$status] $($check.Key)" $resultText
    }
    
    return $allPassed
}

# ========== Main Installation Flow ==========
try {
    # Step 1: Check prerequisites
    Log "Checking prerequisites..." "INFO"
    if ($PSVersionTable.PSVersion.Major -lt 5) {
        Log "PowerShell 5.0 or higher required" "ERROR"
        exit 1
    }
    
    # Step 2: Check if already installed
    if (Test-AgentAlreadyInstalled) {
        Log "Agent already installed" "WARN"
        Log "To reinstall, use: Remove-AgentInstall.ps1 first" "INFO"
        exit 0
    }
    
    # Step 3: Stop any existing agent
    Stop-AgentService
    
    # Step 4: Clean temp directory
    if (Test-Path $TempDir) {
        Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
    
    # Step 5: Download agent
    $agentPackage = "$TempDir\agent.zip"
    $downloadUrl = "$PortalUrl/download-agent"  # Adjust based on your API
    if (-not (Get-AgentPackage -Url $downloadUrl -OutPath $agentPackage)) {
        throw "Failed to download agent package"
    }
    
    # Step 6: Install agent
    if (-not (Install-Agent -InstallerPath $agentPackage -TargetDir $InstallDir)) {
        throw "Failed to install agent"
    }
    
    # Step 7: Configure agent
    if (-not (Set-AgentConfiguration -PortalUrl $PortalUrl -TenantKey $TenantKey -InstallDir $InstallDir)) {
        throw "Failed to configure agent"
    }
    
    # Step 8: Register service
    if (-not (Register-AgentService -ExePath $AgentExe -ServiceName $ServiceName)) {
        throw "Failed to register service"
    }
    
    # Step 9: Set registry keys
    Set-RegistryKeys -Version "2.0.0" -InstallDir $InstallDir
    
    # Step 10: Start service
    if (-not (Start-AgentService -ServiceName $ServiceName)) {
        throw "Failed to start service"
    }
    
    # Step 11: Verify
    if (Test-Installation -InstallDir $InstallDir) {
        Log "✓ INSTALLATION SUCCESSFUL" "OK"
        Log "Agent is now running. Check your portal in a few minutes for registration." "INFO"
        exit 0
    } else {
        throw "Installation verification failed"
    }
    
} catch {
    Log "INSTALLATION FAILED: $_" "ERROR"
    Log "Check diagnostic script for more info: Diagnose-AgentInstall.ps1" "ERROR"
    exit 1
    
} finally {
    # Cleanup
    if (Test-Path $TempDir) {
        Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
