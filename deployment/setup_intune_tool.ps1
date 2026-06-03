# Requires admin privileges
<#
.SYNOPSIS
    Download Intune Win32 Content Prep Tool (IntuneWinAppUtil.exe) and configure ServerMonitor config.json
.DESCRIPTION
    Downloads the IntuneWinAppUtil.exe to a chosen folder and updates the project's config.json with the path.
.PARAMETER InstallPath
    Destination path for the IntuneWinAppUtil.exe (default: C:\Tools\IntuneWinAppUtil.exe)
.EXAMPLE
    .\setup_intune_tool.ps1 -InstallPath C:\Tools\IntuneWinAppUtil.exe
#>

param(
    [string]$InstallPath = "C:\\Tools\\IntuneWinAppUtil.exe",
    [string]$DownloadUrl = "https://github.com/Microsoft/Microsoft-Win32-Content-Prep-Tool/releases/latest/download/IntuneWinAppUtil.exe"
)

$ErrorActionPreference = 'Stop'

function Log { param($m) Write-Host "[INFO] $m" -ForegroundColor Cyan }

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "This script must be run as Administrator" -ForegroundColor Red
    exit 1
}

$dir = Split-Path -Path $InstallPath -Parent
if (-not (Test-Path $dir)) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    Log "Created directory: $dir"
}

$tempFile = [System.IO.Path]::GetTempFileName()

Log "Downloading IntuneWinAppUtil.exe from: $DownloadUrl"
try {
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $tempFile -UseBasicParsing -TimeoutSec 120
    Move-Item -Path $tempFile -Destination $InstallPath -Force
    Log "Downloaded to $InstallPath"
} catch {
    Write-Host "Failed to download IntuneWinAppUtil.exe: $_" -ForegroundColor Red
    if (Test-Path $tempFile) { Remove-Item $tempFile -Force }
    exit 1
}

# Update config.json in project root
$projectRoot = Split-Path -Parent $PSScriptRoot
$configFile = Join-Path $projectRoot "..\config.json" | Resolve-Path -ErrorAction SilentlyContinue
if (-not $configFile) {
    $configFile = Join-Path $projectRoot "..\config.json"
}

if (Test-Path $configFile) {
    try {
        $json = Get-Content $configFile -Raw | ConvertFrom-Json
        $json.intune_win_tool_path = $InstallPath
        $json | ConvertTo-Json -Depth 5 | Set-Content $configFile -Encoding UTF8
        Log "Updated config.json with intune_win_tool_path: $InstallPath"
    } catch {
        Write-Host "Failed to update config.json: $_" -ForegroundColor Yellow
    }
} else {
    Write-Host "Could not find config.json at expected location: $configFile" -ForegroundColor Yellow
}

Write-Host "
Setup complete. You may need to restart the ServerMonitor service or web server to pick up the new configuration." -ForegroundColor Green
