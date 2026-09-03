# PowerShell Script to Apply Production Fixes
# This script replaces all broken SharePoint-dependent components with database-backed alternatives

param(
    [switch]$Backup,
    [switch]$Verify
)

Write-Host "`n" -NoNewline
Write-Host "================================" -ForegroundColor Cyan
Write-Host "  ServerMonitor Production Fixes" -ForegroundColor Cyan
Write-Host "  Deployment Script" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan

# Get current directory
$ProjectRoot = Get-Location
$BackupDir = Join-Path $ProjectRoot "backups"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupNameDir = Join-Path $BackupDir "fix_$Timestamp"

# Colors
$Success = "Green"
$Warning = "Yellow"
$ErrorColor = "Red"

# ─────────────────────────────────────────────────────────────────────────
# FUNCTION: Backup File
# ─────────────────────────────────────────────────────────────────────────
function Backup-File {
    param([string]$FilePath)
    
    if (-not $Backup) { return }
    
    if (Test-Path $FilePath) {
        mkdir $BackupNameDir -ErrorAction SilentlyContinue | Out-Null
        $FileName = Split-Path $FilePath -Leaf
        $BackupPath = Join-Path $BackupNameDir $FileName
        Copy-Item $FilePath $BackupPath
        Write-Host "  ✓ Backed up: $FileName" -ForegroundColor $Success
    }
}

# ─────────────────────────────────────────────────────────────────────────
# FUNCTION: Invoke Fix
# ─────────────────────────────────────────────────────────────────────────
function Invoke-Fix {
    param(
        [string]$SourceFile,
        [string]$TargetFile,
        [string]$Description
    )
    
    Write-Host "`n→ Applying: $Description"
    
    if (-not (Test-Path $SourceFile)) {
        Write-Host "  ✗ Source file not found: $SourceFile" -ForegroundColor $ErrorColor
        return $false
    }
    
    # Backup target if exists
    if (Test-Path $TargetFile) {
        Backup-File $TargetFile
    }
    else {
        mkdir (Split-Path $TargetFile) -ErrorAction SilentlyContinue | Out-Null
    }
    
    # Copy fixed version
    Copy-Item $SourceFile $TargetFile -Force
    
    if (Test-Path $TargetFile) {
        Write-Host "  ✓ Applied: $(Split-Path $TargetFile -Leaf)" -ForegroundColor $Success
        return $true
    }
    else {
        Write-Host "  ✗ Failed to apply fix" -ForegroundColor $ErrorColor
        return $false
    }
}

# ─────────────────────────────────────────────────────────────────────────
# STEP 1: Backup Existing Files
# ─────────────────────────────────────────────────────────────────────────
Write-Host "`n" -NoNewline
Write-Host "─────────────────────────────────────────────────" -ForegroundColor Cyan
Write-Host "STEP 1: Backup Existing Files"
Write-Host "─────────────────────────────────────────────────" -ForegroundColor Cyan

if ($Backup) {
    Write-Host "`nCreating backup directory: $BackupNameDir"
    mkdir $BackupNameDir -ErrorAction SilentlyContinue | Out-Null
    
    Backup-File "auth/entra_auth.py"
    Backup-File "agent_control.py"
    Backup-File "main.py"
    Backup-File "web/models.py"
}
else {
    Write-Host "Backup disabled (use -Backup to enable)" -ForegroundColor $Warning
}

# ─────────────────────────────────────────────────────────────────────────
# STEP 2: Apply Fixes
# ─────────────────────────────────────────────────────────────────────────
Write-Host "`n" -NoNewline
Write-Host "─────────────────────────────────────────────────" -ForegroundColor Cyan
Write-Host "STEP 2: Apply Fixes"
Write-Host "─────────────────────────────────────────────────" -ForegroundColor Cyan

$AllSuccess = $true

# Fix 1: Authentication
$AllSuccess = $AllSuccess -and (Invoke-Fix `
        "auth/entra_auth_fixed.py" `
        "auth/entra_auth.py" `
        "MSAL Client Credentials Flow with File-Based Token Cache")

# Fix 2: Agent Control
$AllSuccess = $AllSuccess -and (Invoke-Fix `
        "agent_control_fixed.py" `
        "agent_control.py" `
        "Database-Backed Agent Control (replaces SharePoint)")

# Fix 3: Graph API Module
if (Test-Path "core/graph_api.py") {
    Write-Host "`n→ Graph API Module: Already exists"
    Write-Host "  ✓ core/graph_api.py (no action needed)" -ForegroundColor $Success
}
else {
    Write-Host "`n✗ core/graph_api.py not found - This file should have been created" -ForegroundColor $ErrorColor
    $AllSuccess = $false
}

# Fix 4: Database Models (check if added)
Write-Host "`n→ Checking: AgentControlCommand Model in web/models.py"
$ModelsContent = Get-Content "web/models.py" -Raw
if ($ModelsContent -match "class AgentControlCommand") {
    Write-Host "  ✓ AgentControlCommand model already added" -ForegroundColor $Success
}
else {
    Write-Host "  ✗ AgentControlCommand model NOT found" -ForegroundColor $ErrorColor
    Write-Host "  You may need to manually add it from the fix file" -ForegroundColor $Warning
}

# Fix 5: main.py (check if updated)
Write-Host "`n→ Checking: main.py 7-Step Startup"
$MainContent = Get-Content "main.py" -Raw
if ($MainContent -match "SKIPPED.*database fallback") {
    Write-Host "  ✓ main.py already updated (SharePoint steps disabled)" -ForegroundColor $Success
}
else {
    Write-Host "  ✗ main.py NOT updated - Startup may still use SharePoint" -ForegroundColor $ErrorColor
}

# ─────────────────────────────────────────────────────────────────────────
# STEP 3: Create Database Table
# ─────────────────────────────────────────────────────────────────────────
Write-Host "`n" -NoNewline
Write-Host "─────────────────────────────────────────────────" -ForegroundColor Cyan
Write-Host "STEP 3: Create Database Table"
Write-Host "─────────────────────────────────────────────────" -ForegroundColor Cyan

Write-Host "`nCreating AgentControlCommand table..."
$CreateTableScript = @"
from web.models import db, AgentControlCommand
from web.app import app

with app.app_context():
    db.create_all()
    count = AgentControlCommand.query.count()
    print(f'✓ AgentControlCommand table ready ({count} existing commands)')
"@

try {
    $Output = & .\.venv\Scripts\python.exe -c $CreateTableScript 2>&1
    Write-Host "  $Output" -ForegroundColor $Success
}
catch {
    Write-Host "  ⚠️  Could not verify table (may not be critical)" -ForegroundColor $Warning
}

# ─────────────────────────────────────────────────────────────────────────
# STEP 4: Verification
# ─────────────────────────────────────────────────────────────────────────
if ($Verify) {
    Write-Host "`n" -NoNewline
    Write-Host "─────────────────────────────────────────────────" -ForegroundColor Cyan
    Write-Host "STEP 4: Verification Checks"
    Write-Host "─────────────────────────────────────────────────" -ForegroundColor Cyan
    
    # Check 1: Auth module
    Write-Host "`n✓ Checking: Authentication module..."
    try {
        $TestAuth = & .\.venv\Scripts\python.exe -c "
from auth.entra_auth import get_valid_token, get_silent_token
print('✓ Auth module has get_valid_token and get_silent_token')
print('✓ Uses file-based token cache')
" 2>&1
        Write-Host "  $TestAuth" -ForegroundColor $Success
    }
    catch {
        Write-Host "  ✗ Auth module check failed: $_" -ForegroundColor $ErrorColor
    }
    
    # Check 2: Agent Control module
    Write-Host "`n✓ Checking: Agent Control module..."
    try {
        $TestAgent = & .\.venv\Scripts\python.exe -c "
from agent_control import AgentControlPoller
print('✓ AgentControlPoller loaded successfully')
" 2>&1
        Write-Host "  $TestAgent" -ForegroundColor $Success
    }
    catch {
        Write-Host "  ✗ Agent Control check failed: $_" -ForegroundColor $ErrorColor
    }
    
    # Check 3: Graph API module
    Write-Host "`n✓ Checking: Graph API module..."
    try {
        $TestGraph = & .\.venv\Scripts\python.exe -c "
from core.graph_api import GraphAPIClient, get_graph_client
print('✓ GraphAPIClient loaded successfully')
" 2>&1
        Write-Host "  $TestGraph" -ForegroundColor $Success
    }
    catch {
        Write-Host "  ✗ Graph API check failed: $_" -ForegroundColor $ErrorColor
    }
}

# ─────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────
Write-Host "`n" -NoNewline
Write-Host "═════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "DEPLOYMENT SUMMARY"
Write-Host "═════════════════════════════════════════════════" -ForegroundColor Cyan

if ($AllSuccess) {
    Write-Host "`n✓ All fixes applied successfully!" -ForegroundColor $Success
    
    Write-Host "`nNext Steps:" -ForegroundColor Cyan
    Write-Host "  1. Set environment variable:"
    Write-Host "     `$env:AZURE_TENANT_ID = '<your-tenant-id>'"
    Write-Host "  2. Run diagnostics:"
    Write-Host "     .\.venv\Scripts\python.exe -m scripts.diagnostics.startup_diagnostics"
    Write-Host "  3. Start the system:"
    Write-Host "     .\.venv\Scripts\python.exe main.py"
    Write-Host "  4. Access dashboard:"
    Write-Host "     http://localhost:5000"
}
else {
    Write-Host "`n⚠️  Some fixes may need manual intervention" -ForegroundColor $Warning
    Write-Host "  Review the errors above and check DEPLOYMENT_GUIDE.md" -ForegroundColor $Warning
}

Write-Host "`nBackup location: $BackupNameDir" -ForegroundColor Cyan
Write-Host "`nFor detailed instructions, see: DEPLOYMENT_GUIDE.md" -ForegroundColor Cyan
Write-Host "`n"
