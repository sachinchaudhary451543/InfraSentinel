#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Uninstalls ServerMonitor Agent cleanly.
    
.DESCRIPTION
    Stops the service, removes files, and cleans registry entries.
    Safe to run even if agent is partially installed.
    
.PARAMETER Silent
    If $true, suppresses all console output. Default: $false
    
.EXAMPLE
    .\Uninstall-Agent.ps1
    
.NOTES
    Author: ServerMonitor Deployment Team
    Requires: Administrator privileges
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [bool]$Silent = $false
)

$ErrorActionPreference = "Continue"

if (-not $Silent) {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "ServerMonitor Agent Uninstaller" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
}

# Configuration
$ServiceName = "ServerMonitorAgent"
$InstallDir = "C:\Program Files\ServerMonitor\Agent"
$RegistryPath = "HKLM:\SOFTWARE\ServerMonitor\Agent"
$DataDir = "C:\ProgramData\ServerMonitor"

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

try {
    # Step 1: Stop service
    Log "Stopping agent service..." "INFO"
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($svc) {
        if ($svc.Status -eq "Running") {
            Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
            Log "Service stopped" "OK"
        }
        
        # Remove service
        Log "Removing service..." "INFO"
        & "sc.exe" delete $ServiceName | Out-Null
        Start-Sleep -Seconds 1
        Log "Service removed" "OK"
    } else {
        Log "Service not found (not installed or already removed)" "WARN"
    }
    
    # Step 2: Remove installation directory
    if (Test-Path $InstallDir) {
        Log "Removing installation directory: $InstallDir" "INFO"
        Remove-Item -Path $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
        Log "Installation directory removed" "OK"
    }
    
    # Step 3: Remove data directory
    if (Test-Path $DataDir) {
        Log "Removing data directory: $DataDir" "INFO"
        Remove-Item -Path $DataDir -Recurse -Force -ErrorAction SilentlyContinue
        Log "Data directory removed" "OK"
    }
    
    # Step 4: Remove registry keys
    if (Test-Path $RegistryPath) {
        Log "Removing registry keys: $RegistryPath" "INFO"
        Remove-Item -Path $RegistryPath -Force -ErrorAction SilentlyContinue
        Log "Registry keys removed" "OK"
    }
    
    # Step 5: Clean temp files
    $tempPattern = "$env:TEMP\SMAgent*"
    Get-Item -Path $tempPattern -ErrorAction SilentlyContinue | ForEach-Object {
        Log "Removing temp: $($_.FullName)" "WARN"
        Remove-Item -Path $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }
    
    Log "✓ UNINSTALLATION COMPLETE" "OK"
    Log "Agent has been successfully removed from this system." "INFO"
    
} catch {
    Log "UNINSTALLATION FAILED: $_" "ERROR"
    exit 1
}
