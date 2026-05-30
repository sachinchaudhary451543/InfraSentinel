# ============================================================================
# ServerMonitor - Web Server Launcher
# ============================================================================

Write-Host "ServerMonitor v3.0 - Web Server Starting..." -ForegroundColor Cyan

# Get the script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "[1/2] Checking Python Virtual Environment..." -ForegroundColor Yellow

# Check if already activated
if ($env:VIRTUAL_ENV) {
    Write-Host "OK - Already in virtual environment: $env:VIRTUAL_ENV" -ForegroundColor Green
}
else {
    Write-Host "Activating Python Virtual Environment..." -ForegroundColor Yellow
    & ".\.venv\Scripts\Activate.ps1"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to activate virtual environment" -ForegroundColor Red
        exit 1
    }
    Write-Host "OK - Virtual environment activated" -ForegroundColor Green
}

# Configuration
$ServerPort = 5000
$ServerURL = "http://127.0.0.1:$ServerPort"

Write-Host ""
Write-Host "[2/2] Configuration Summary:" -ForegroundColor Yellow
Write-Host "  - Flask Web Server: $ServerURL" -ForegroundColor Cyan
Write-Host "  - PostgreSQL Database: 127.0.0.1:3000" -ForegroundColor Cyan
Write-Host "  - Navigate to: http://localhost:$ServerPort" -ForegroundColor Magenta
Write-Host ""
Write-Host "Starting Server (Press Ctrl+C to stop)..." -ForegroundColor Yellow
Write-Host ""

# Set environment variables for the server
$env:FLASK_ENV = "development"
$env:FLASK_DEBUG = "0"
# PostgreSQL is configured on port 3000 with correct credentials
# Note: @ in password is URL-encoded as %40
$env:DATABASE_URL = "postgresql://postgres:Airport%402026@127.0.0.1:3000/servermonitor"

# Start Flask server on port 5000
python -c "from web.app import app; app.run(host='127.0.0.1', port=5000, debug=False)"
