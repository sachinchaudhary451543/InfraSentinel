#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Diagnose agent installation and Intune deployment issues on Windows systems.
    
.DESCRIPTION
    Collects Intune logs, Event Viewer entries, network connectivity, and agent status.
    Safe to run on any Windows 10/11 managed device. No modifications are made.
    
.EXAMPLE
    .\Diagnose-AgentInstall.ps1
    
.NOTES
    Author: ServerMonitor Deployment Team
    Requires: Administrator privileges
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"
$WarningPreference = "Continue"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Agent Installation Diagnostic Tool" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Colors
$Good = "Green"
$Bad = "Red"
$Warn = "Yellow"
$Info = "Cyan"

function Write-Status {
    param([string]$Test, [bool]$Status, [string]$Message)
    $icon = if ($Status) { "✓" } else { "✗" }
    $color = if ($Status) { $Good } else { $Bad }
    Write-Host "  [$icon] $Test : $Message" -ForegroundColor $color
}

# ========== 1. System Info ==========
Write-Host "`n[1] SYSTEM INFORMATION" -ForegroundColor $Info
$os = [System.Environment]::OSVersion.VersionString
if ([System.Environment]::Is64BitOperatingSystem) {
    $arch = "64-bit"
} else {
    $arch = "32-bit"
}
Write-Host "  OS: $os ($arch)"
Write-Host "  Computer: $env:COMPUTERNAME"
if ($env:USERDOMAIN) { $domainInfo = $env:USERDOMAIN } else { $domainInfo = 'Not domain-joined' }
Write-Host "  Domain: $domainInfo"
Write-Host "  User: $env:USERNAME"

# ========== 2. Intune Enrollment ==========
Write-Host "`n[2] INTUNE ENROLLMENT STATUS" -ForegroundColor $Info
$msilog = "C:\ProgramData\Microsoft\IntuneManagementExtension\Logs\IntuneManagementExtension.log"
$intuneKeyPath = "HKLM:\SOFTWARE\Microsoft\Enrollments"

if (Test-Path $intuneKeyPath) {
    $enrolled = $true
    Write-Host "  [✓] Device appears to be MDM-enrolled" -ForegroundColor $Good
} else {
    $enrolled = $false
    Write-Host "  [✗] No MDM enrollment found in registry" -ForegroundColor $Bad
}

# ========== 3. Intune Management Extension ==========
Write-Host "`n[3] INTUNE MANAGEMENT EXTENSION STATUS" -ForegroundColor $Info
if (Test-Path $msilog) {
    Write-Host "  [✓] IME log file exists: $msilog" -ForegroundColor $Good
    $lastMod = (Get-Item $msilog).LastWriteTime
    $age = (Get-Date) - $lastMod
    Write-Host "    Last modified: $lastMod ($($age.TotalHours) hours ago)"
    
    Write-Host "    Last 50 lines:" -ForegroundColor $Warn
    Get-Content $msilog -Tail 50 | ForEach-Object {
        Write-Host "    $_"
    }
} else {
    Write-Host "  [✗] IME log not found at: $msilog" -ForegroundColor $Bad
    Write-Host "    This may indicate IME is not installed or has not run yet." -ForegroundColor $Warn
}

# ========== 4. Event Viewer Logs ==========
Write-Host "`n[4] RECENT INSTALLER ERRORS (Event Viewer)" -ForegroundColor $Info
$appEvents = Get-WinEvent -LogName "Application" -FilterXPath "*[System[EventID=1000 or EventID=1001 or EventID=1002]] and System[TimeCreated[@SystemTime > '$(((Get-Date).AddHours(-24)).ToUniversalTime().ToString('o'))']" -ErrorAction SilentlyContinue | Select-Object -First 10
if ($appEvents) {
    Write-Host "  Found recent errors:" -ForegroundColor $Bad
    $appEvents | ForEach-Object {
        Write-Host "    $($_.TimeCreated): $($_.Message.Substring(0, [Math]::Min(100, $_.Message.Length)))"
    }
} else {
    Write-Host "  [✓] No recent application crashes found in Event Viewer" -ForegroundColor $Good
}

# ========== 5. Network Connectivity ==========
Write-Host "`n[5] NETWORK CONNECTIVITY TESTS" -ForegroundColor $Info

# Test Intune CDN connectivity
Write-Host "  Testing Intune blob storage connectivity..."
try {
    $testResult = Test-NetConnection -ComputerName "login.windows.net" -Port 443 -InformationLevel Quiet -ErrorAction Stop
    Write-Status "Intune Identity" $testResult "Connected to login.windows.net:443"
} catch {
    Write-Status "Intune Identity" $false "Failed to connect: $_"
}

# Test portal connectivity (example: adjust to your domain)
Write-Host "  Testing ServerMonitor portal connectivity..."
$portalHost = "servermonitor-web.onrender.com"  # Update to your actual domain
try {
    $testResult = Test-NetConnection -ComputerName $portalHost -Port 443 -InformationLevel Quiet -ErrorAction Stop
    Write-Status "Portal" $testResult "Connected to $portalHost:443"
} catch {
    Write-Status "Portal" $false "Failed to connect to $portalHost`: $_"
}

# ========== 6. Agent Service Status ==========
Write-Host "`n[6] AGENT SERVICE STATUS" -ForegroundColor $Info
$agentService = Get-Service -Name "ServerMonitorAgent" -ErrorAction SilentlyContinue
if ($agentService) {
    $running = $agentService.Status -eq "Running"
    Write-Status "Agent Service" $running "Status: $($agentService.Status)"
    Write-Host "    Startup type: $($agentService.StartType)"
    Write-Host "    Display name: $($agentService.DisplayName)"
} else {
    Write-Status "Agent Service" $false "Service 'ServerMonitorAgent' not found (not installed yet)"
}

# ========== 7. Agent Installation Paths ==========
Write-Host "`n[7] AGENT INSTALLATION PATHS" -ForegroundColor $Info
$agentPath = "C:\Program Files\ServerMonitor\Agent"
if (Test-Path $agentPath) {
    Write-Status "Agent Folder" $true "Found at $agentPath"
    Get-ChildItem $agentPath -Recurse | Select-Object -First 10 | ForEach-Object {
        Write-Host "    - $($_.Name)"
    }
} else {
    Write-Status "Agent Folder" $false "Not found at $agentPath"
}

# ========== 8. Agent Registration Key ==========
Write-Host "`n[8] AGENT REGISTRATION STATUS" -ForegroundColor $Info
$regPath = "HKLM:\SOFTWARE\ServerMonitor\Agent"
if (Test-Path $regPath) {
    Write-Status "Registry Key" $true "Found at $regPath"
    $props = Get-ItemProperty $regPath
    $props | Get-Member -MemberType NoteProperty | ForEach-Object {
        if ($_.Name -ne "PSPath" -and $_.Name -ne "PSParentPath" -and $_.Name -ne "PSChildName" -and $_.Name -ne "PSDrive" -and $_.Name -ne "PSProvider") {
            Write-Host "    $($_.Name): $($props.($_.Name))"
        }
    }
} else {
    Write-Status "Registry Key" $false "Not found at $regPath (agent may not be registered)"
}

# ========== 9. Summary & Recommendations ==========
Write-Host "`n[9] SUMMARY & NEXT STEPS" -ForegroundColor $Info

$recommendations = @()
if (-not $enrolled) { $recommendations += "• Device is not MDM-enrolled in Intune. Enroll device first." }
if (-not $agentService) { $recommendations += "• Agent service not installed. Run installer script or wait for Intune deployment." }
if ($agentService -and $agentService.Status -ne "Running") { $recommendations += "• Agent service is not running. Check permissions and service dependencies." }

if ($recommendations.Count -eq 0) {
    Write-Host "  [✓] System appears ready. Agent is installed and running." -ForegroundColor $Good
    Write-Host "  Next: Check portal to confirm device is visible and sending data." -ForegroundColor $Info
} else {
    Write-Host "  Issues detected:" -ForegroundColor $Bad
    $recommendations | ForEach-Object { Write-Host "    $_" }
}

# ========== 10. Export Summary ==========
Write-Host "`n[10] EXPORTING DIAGNOSTICS" -ForegroundColor $Info
$exportPath = "$env:TEMP\AgentDiagnostics_$(Get-Date -Format 'yyyyMMdd_HHmmss').txt"
Write-Host "  Diagnostics summary exported to: $exportPath" -ForegroundColor $Info

# Capture full output to file
$diagnosticText = @"
=== AGENT INSTALLATION DIAGNOSTICS ===
Date: $(Get-Date)
Computer: $env:COMPUTERNAME
User: $env:USERNAME

OS: $os ($arch)
Intune Enrollment: $(if ($enrolled) { 'Yes' } else { 'No' })
Agent Installed: $(if ($agentService) { 'Yes' } else { 'No' })
Agent Running: $(if ($agentService -and $agentService.Status -eq 'Running') { 'Yes' } else { 'No' })

=== RECOMMENDATIONS ===
$(($recommendations | Out-String).Trim())

=== INTUNE MANAGEMENT EXTENSION LOG (Last 100 lines) ===
$(if (Test-Path $msilog) { Get-Content $msilog -Tail 100 | Out-String } else { 'Log file not found' })
"@

$diagnosticText | Out-File $exportPath -Encoding UTF8
Write-Host "  Run: Invoke-Item '$exportPath' to open the report." -ForegroundColor $Info

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Diagnostics Complete" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
