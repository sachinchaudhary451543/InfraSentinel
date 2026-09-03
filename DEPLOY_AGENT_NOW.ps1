# ==============================================================================
# DEPLOY AGENT - Fast Deployment Script
# ==============================================================================
# Run this as Administrator to deploy the agent with all fixes

Write-Host "`n" + "="*70 -ForegroundColor Green
Write-Host "  SERVERMONITOR - AGENT DEPLOYMENT" -ForegroundColor Green
Write-Host "="*70 -ForegroundColor Green

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")
if (-not $isAdmin) {
    Write-Host "`n❌ ERROR: This script must run as Administrator!" -ForegroundColor Red
    Write-Host "   Right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
    exit 1
}

Write-Host "`n✅ Running as Administrator" -ForegroundColor Green

# Set environment variables
Write-Host "`n📝 Setting environment variables..." -ForegroundColor Cyan

# Get agent key from user or use default
$agentKey = $env:AGENT_KEY
if (-not $agentKey) {
    Write-Host "`n⚠️  AGENT_KEY not set. Set a unique key before deploying the agent." -ForegroundColor Yellow
    $env:AGENT_KEY = "demo_mode_key"
}
else {
    Write-Host "   AGENT_KEY: $agentKey" -ForegroundColor Green
}

# Get server URL or use localhost
$serverUrl = $env:SERVER_URL
if (-not $serverUrl) {
    Write-Host "   SERVER_URL not set. Using: http://localhost:3000" -ForegroundColor Yellow
    $env:SERVER_URL = "http://localhost:3000"
}
else {
    Write-Host "   SERVER_URL: $serverUrl" -ForegroundColor Green
}

# Enable screenshots
$env:ENABLE_SCREENSHOTS = "true"
$env:SCREENSHOT_INTERVAL = "300"

Write-Host "`n📊 Environment Configuration:" -ForegroundColor Cyan
Write-Host "   AGENT_KEY:          $env:AGENT_KEY" -ForegroundColor White
Write-Host "   SERVER_URL:         $env:SERVER_URL" -ForegroundColor White
Write-Host "   ENABLE_SCREENSHOTS: $env:ENABLE_SCREENSHOTS" -ForegroundColor White
Write-Host "   SCREENSHOT_INTERVAL: $env:SCREENSHOT_INTERVAL seconds" -ForegroundColor White

# Navigate to working directory
$workDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $workDir

Write-Host "`n📂 Working Directory: $workDir" -ForegroundColor Cyan

# Start the agent
Write-Host "`n🚀 Starting agent (agent_improved.py)..." -ForegroundColor Green
Write-Host "   Press Ctrl+C to stop" -ForegroundColor Yellow

Write-Host "`n" + "="*70 -ForegroundColor Green
Write-Host "  AGENT OUTPUT" -ForegroundColor Green
Write-Host "="*70 -ForegroundColor Green + "`n"

# Run the improved agent
python agent_improved.py

Write-Host "`n" + "="*70
Write-Host "Agent stopped." -ForegroundColor Yellow
Write-Host "="*70
