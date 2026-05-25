# ============================================================================
# ServerMonitor Agent Launcher
# ============================================================================

Write-Host "ServerMonitor Agent v3.0 - Starting..." -ForegroundColor Cyan

# Get the script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "[1/2] Checking Python Virtual Environment..." -ForegroundColor Yellow

# Check if already activated
if ($env:VIRTUAL_ENV) {
    Write-Host "OK - Already in virtual environment: $env:VIRTUAL_ENV" -ForegroundColor Green
} else {
    Write-Host "Activating Python Virtual Environment..." -ForegroundColor Yellow
    & ".\.venv\Scripts\Activate.ps1"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to activate virtual environment" -ForegroundColor Red
        exit 1
    }
    Write-Host "OK - Virtual environment activated" -ForegroundColor Green
}

# Configuration - Agent connects to Flask Web Server on port 5000 (NOT PostgreSQL)
$ServerURL = "http://127.0.0.1:5000"   # Flask server is on port 5000
$AgentKey = "demo_mode_key"
$PollingInterval = 30

Write-Host ""
Write-Host "[2/2] Configuration Summary:" -ForegroundColor Yellow
Write-Host "  - Server URL: $ServerURL" -ForegroundColor Cyan
Write-Host "  - Agent Key: $AgentKey (demo mode)" -ForegroundColor Cyan
Write-Host "  - Poll Interval: $PollingInterval seconds" -ForegroundColor Cyan
Write-Host "  - Hostname: $env:COMPUTERNAME" -ForegroundColor Cyan
Write-Host ""
Write-Host "Starting Agent (Press Ctrl+C to stop)..." -ForegroundColor Yellow
Write-Host "Make sure Web Server is running on $ServerURL" -ForegroundColor Gray
Write-Host ""

# Set environment variables for the agent
$env:SERVER_URL = $ServerURL
$env:AGENT_KEY = $AgentKey
$env:AGENT_INTERVAL = $PollingInterval

# Start agent
python agent.py
