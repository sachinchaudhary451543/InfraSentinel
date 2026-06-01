#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Automated Fix Deployment: Screenshots & Remote Controls
    
.DESCRIPTION
    Deploys all fixes for screenshot and remote control issues:
    1. Applies database fixes
    2. Restarts web server
    3. Restarts all agents
    4. Verifies system
    
.PARAMETER SkipDatabaseFix
    Skip the database fix step (if already applied)
    
.PARAMETER SkipWebRestart
    Skip restarting the web server
    
.PARAMETER SkipAgentRestart  
    Skip restarting agents
    
.PARAMETER RunDiagnostics
    Run diagnostic tests after deployment
    
.EXAMPLE
    .\Deploy-ScreenshotFix.ps1
    .\Deploy-ScreenshotFix.ps1 -RunDiagnostics
    .\Deploy-ScreenshotFix.ps1 -SkipWebRestart -RunDiagnostics

.NOTES
    Author: ServerMonitor Team
    Version: 1.0
    Requires: Administrator privileges, PowerShell 5.0+
#>

[CmdletBinding()]
param(
    [switch]$SkipDatabaseFix,
    [switch]$SkipWebRestart,
    [switch]$SkipAgentRestart,
    [switch]$RunDiagnostics
)

$ErrorActionPreference = "Stop"
$WarningPreference = "Continue"

function Write-Status {
    param([string]$Message, [ValidateSet('INFO', 'SUCCESS', 'ERROR', 'WARNING')]$Level = 'INFO')
    $color = @{
        'INFO'    = 'Cyan'
        'SUCCESS' = 'Green'
        'ERROR'   = 'Red'
        'WARNING' = 'Yellow'
    }[$Level]
    Write-Host "[$Level] $Message" -ForegroundColor $color
}

function Test-PathExists {
    param([string]$Path)
    if (Test-Path $Path) {
        return $true
    }
    Write-Status "Path not found: $Path" 'WARNING'
    return $false
}

# ═════════════════════════════════════════════════════════════════════════════
# MAIN DEPLOYMENT
# ═════════════════════════════════════════════════════════════════════════════

Write-Host "╔══════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   ServerMonitor Screenshot & Controls FIX DEPLOYMENT            ║" -ForegroundColor Cyan
Write-Host "║   Automated Fix Application (v1.0)                             ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan

$deploymentStart = Get-Date

# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Verify Environment
# ─────────────────────────────────────────────────────────────────────────────
Write-Status "Step 1: Verifying environment..." 'INFO'

$ServerMonitorPath = "C:\ServerMonitor"
if (-not (Test-PathExists $ServerMonitorPath)) {
    Write-Status "ServerMonitor not found at $ServerMonitorPath" 'ERROR'
    exit 1
}
Write-Status "✓ ServerMonitor found at $ServerMonitorPath" 'SUCCESS'

$pythonPath = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonPath) {
    Write-Status "Python not found. Please install Python 3.8+" 'ERROR'
    exit 1
}
Write-Status "✓ Python found: $($pythonPath.Source)" 'SUCCESS'

# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Database Fix
# ─────────────────────────────────────────────────────────────────────────────
if (-not $SkipDatabaseFix) {
    Write-Status "Step 2: Applying database fixes..." 'INFO'
    
    $fixScript = Join-Path $ServerMonitorPath "fix_screenshots_and_controls.py"
    if (-not (Test-PathExists $fixScript)) {
        Write-Status "Fix script not found: $fixScript" 'ERROR'
        exit 1
    }
    
    try {
        Write-Status "  Running fix_screenshots_and_controls.py..." 'INFO'
        Push-Location $ServerMonitorPath
        & python fix_screenshots_and_controls.py
        Pop-Location
        Write-Status "✓ Database fixes applied" 'SUCCESS'
    } catch {
        Write-Status "Failed to apply database fixes: $_" 'ERROR'
        exit 1
    }
} else {
    Write-Status "Step 2: Skipping database fix (as requested)" 'WARNING'
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Restart Web Server
# ─────────────────────────────────────────────────────────────────────────────
if (-not $SkipWebRestart) {
    Write-Status "Step 3: Restarting web server..." 'INFO'
    
    try {
        Write-Status "  Stopping portal..." 'INFO'
        Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match 'run_portal|main\.py' } | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 3
        
        Write-Status "  Starting portal..." 'INFO'
        $portalScript = Join-Path $ServerMonitorPath "run_portal.py"
        if (Test-PathExists $portalScript) {
            Start-Process -FilePath python -ArgumentList $portalScript -WorkingDirectory $ServerMonitorPath -NoNewWindow
            Start-Sleep -Seconds 5
            Write-Status "✓ Web server restarted" 'SUCCESS'
        } else {
            Write-Status "Portal script not found: $portalScript" 'WARNING'
        }
    } catch {
        Write-Status "Warning: Could not restart web server: $_" 'WARNING'
    }
} else {
    Write-Status "Step 3: Skipping web server restart (as requested)" 'WARNING'
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Restart Agents
# ─────────────────────────────────────────────────────────────────────────────
if (-not $SkipAgentRestart) {
    Write-Status "Step 4: Restarting agents..." 'INFO'
    
    # Try to restart Windows service
    $serviceName = "ServerMonitorAgent"
    $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    
    if ($service) {
        try {
            Write-Status "  Stopping service: $serviceName" 'INFO'
            Stop-Service -Name $serviceName -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
            
            Write-Status "  Starting service: $serviceName" 'INFO'
            Start-Service -Name $serviceName -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
            
            $status = (Get-Service -Name $serviceName).Status
            Write-Status "✓ Service restarted (Status: $status)" 'SUCCESS'
        } catch {
            Write-Status "Could not restart service: $_" 'WARNING'
        }
    } else {
        Write-Status "Service $serviceName not found" 'WARNING'
        Write-Status "Note: Please restart agent manually on each computer" 'INFO'
    }
} else {
    Write-Status "Step 4: Skipping agent restart (as requested)" 'WARNING'
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 5: Diagnostics (Optional)
# ─────────────────────────────────────────────────────────────────────────────
if ($RunDiagnostics) {
    Write-Status "Step 5: Running diagnostics..." 'INFO'
    Start-Sleep -Seconds 5  # Wait for services to stabilize
    
    $diagnosticScript = Join-Path $ServerMonitorPath "diagnostic_test.py"
    if (Test-PathExists $diagnosticScript) {
        try {
            Write-Status "  Running diagnostic_test.py..." 'INFO'
            Push-Location $ServerMonitorPath
            & python diagnostic_test.py
            Pop-Location
            Write-Status "✓ Diagnostics completed" 'SUCCESS'
        } catch {
            Write-Status "Diagnostics failed: $_" 'WARNING'
        }
    } else {
        Write-Status "Diagnostic script not found" 'WARNING'
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# Completion
# ─────────────────────────────────────────────────────────────────────────────
$deploymentEnd = Get-Date
$duration = ($deploymentEnd - $deploymentStart).TotalSeconds

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║   ✅ DEPLOYMENT COMPLETE                                        ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════════════════════════╝" -ForegroundColor Green

Write-Host ""
Write-Status "Deployment Summary:" 'INFO'
Write-Status "  Duration: $([math]::Round($duration, 1)) seconds" 'INFO'
Write-Status "  Database Fix: $(if ($SkipDatabaseFix) { 'SKIPPED' } else { 'APPLIED' })" 'INFO'
Write-Status "  Web Server: $(if ($SkipWebRestart) { 'SKIPPED' } else { 'RESTARTED' })" 'INFO'
Write-Status "  Agents: $(if ($SkipAgentRestart) { 'SKIPPED' } else { 'RESTARTED' })" 'INFO'

Write-Host ""
Write-Status "Next Steps:" 'INFO'
Write-Host "  1. Wait 30-60 seconds for agents to connect"
Write-Host "  2. Check portal: http://localhost:5000"
Write-Host "  3. Agents should appear as 'Online'"
Write-Host "  4. Screenshots should appear within 10-15 minutes"
Write-Host "  5. Test remote commands from admin panel"
Write-Host ""
Write-Status "Troubleshooting:" 'INFO'
Write-Host "  • Check agent logs: C:\Program Files\ServerMonitor\Agent\agent.log"
Write-Host "  • Run: python diagnostic_test.py"
Write-Host "  • Database check: SELECT COUNT(*) FROM screenshot;"
Write-Host "  • File check: dir C:\ServerMonitor\data\screenshots\"
Write-Host ""
