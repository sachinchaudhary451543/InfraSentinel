# ============================================================================
# ServerMonitor PostgreSQL Database Initialization
# ============================================================================

Write-Host "ServerMonitor PostgreSQL Database Initialization" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""

# PostgreSQL Connection Details
$PGUser = "postgres"
$PGPassword = $env:PGPASSWORD
$PGHost = "127.0.0.1"
$PGPort = "3000"
$DBName = "servermonitor"

Write-Host "Creating database: $DBName" -ForegroundColor Yellow
Write-Host "PostgreSQL: $PGHost`:$PGPort" -ForegroundColor Gray
Write-Host ""

# Create database using psql
# Password is passed via PGPASSWORD environment variable
$env:PGPASSWORD = $PGPassword

try {
    # Check if database already exists
    Write-Host "[1/2] Checking if database exists..." -ForegroundColor Yellow
    $result = & psql -U $PGUser -h $PGHost -p $PGPort -l 2>$null | Select-String $DBName
    
    if ($result) {
        Write-Host "OK - Database '$DBName' already exists" -ForegroundColor Green
    }
    else {
        Write-Host "Database not found. Creating..." -ForegroundColor Yellow
        
        # Create the database
        & psql -U $PGUser -h $PGHost -p $PGPort -c "CREATE DATABASE $DBName;" 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "OK - Database '$DBName' created successfully" -ForegroundColor Green
        }
        else {
            Write-Host "ERROR: Failed to create database" -ForegroundColor Red
            exit 1
        }
    }
    
    Write-Host ""
    Write-Host "[2/2] Database initialization complete" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "  1. Run: .\START_SERVERMONITOR.ps1" -ForegroundColor White
    Write-Host "  2. Open: http://localhost:5000" -ForegroundColor White
    Write-Host ""
    
}
catch {
    Write-Host "ERROR: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Troubleshooting:" -ForegroundColor Yellow
    Write-Host "  1. Ensure PostgreSQL is running on $PGHost`:$PGPort" -ForegroundColor Gray
    Write-Host "  2. Verify PGUSER and PGPASSWORD environment variables (user: $PGUser)" -ForegroundColor Gray
    Write-Host "  3. Check that psql is in PATH" -ForegroundColor Gray
    exit 1
}
finally {
    # Clear the password from environment
    $env:PGPASSWORD = $null
}
