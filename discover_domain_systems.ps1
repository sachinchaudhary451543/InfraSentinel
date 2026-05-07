param(
    [string]$Domain = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().DomainName,
    [string]$OutputFile = "",
    [string]$FilterOS = ""
)

# Default output
if (-not $OutputFile) { 
    $OutputFile = Join-Path (Split-Path $PSScriptRoot) "data" "discovered_systems.json"
}

if (-not (Test-Path (Split-Path $OutputFile))) {
    New-Item -Path (Split-Path $OutputFile) -ItemType Directory -Force | Out-Null
}

Write-Host "[DISCOVERY] Scanning domain: $Domain"
Write-Host "[DISCOVERY] Output: $OutputFile"

$systems = @()

# --- Method 1: Active Directory Computers (preferred for domain systems) ---
try {
    Add-Type -AssemblyName System.DirectoryServices
    $searcher = New-Object DirectoryServices.DirectorySearcher
    $searcher.Filter = "(&(objectClass=computer)(operatingSystem=*))"
    $searcher.SizeLimit = 10000
    
    $results = $searcher.FindAll()
    Write-Host "[DISCOVERY] Found $($results.Count) computers in AD"
    
    foreach ($result in $results) {
        $props = $result.Properties
        $hostname = $props["name"][0]
        $os = $props["operatingSystem"][0]
        $ip = ""
        
        # Try to resolve IP
        try {
            $ip = [System.Net.Dns]::GetHostAddresses($hostname)[0].IPAddressToString
        }
        catch {
            $ip = "Unknown"
        }
        
        # Filter by OS if specified
        if ($FilterOS -and $os -notmatch $FilterOS) {
            continue
        }
        
        $systems += @{
            hostname      = $hostname
            ip            = $ip
            os            = $os
            domain        = $Domain
            source        = "ActiveDirectory"
            discovered_at = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
            status        = "pending"
        }
    }
    Write-Host "[DISCOVERY] AD scan completed: $($systems.Count) systems"
}
catch {
    Write-Warning "[DISCOVERY] AD scan failed: $_"
}

# --- Method 2: Network Ping Sweep (fallback for non-domain systems) ---
if ($systems.Count -eq 0) {
    Write-Host "[DISCOVERY] Attempting network ping sweep (fallback)..."
    
    $subnet = "192.168"  # Adjust based on your network
    $found = @()
    
    for ($i = 1; $i -le 254; $i++) {
        for ($j = 1; $j -le 254; $j++) {
            $ip = "$subnet.$i.$j"
            if (Test-Connection -ComputerName $ip -Count 1 -Quiet -TimeoutSeconds 1) {
                try {
                    $hostname = [System.Net.Dns]::GetHostByAddress($ip).HostName
                    $found += @{ hostname = $hostname; ip = $ip }
                }
                catch {
                    # IP responded but no hostname
                }
            }
        }
    }
    
    foreach ($item in $found) {
        $systems += @{
            hostname      = $item.hostname
            ip            = $item.ip
            os            = "Unknown"
            domain        = $Domain
            source        = "NetworkSweep"
            discovered_at = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
            status        = "pending"
        }
    }
}

# --- Output to JSON ---
$output = @{
    discovery_timestamp = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    domain              = $Domain
    total_systems       = $systems.Count
    systems             = $systems
}

$output | ConvertTo-Json -Depth 10 | Out-File -FilePath $OutputFile -Encoding utf8 -Force
Write-Host "[DISCOVERY] ✅ Discovery completed. Found $($systems.Count) systems."
Write-Host "[DISCOVERY] Output saved to: $OutputFile"
Write-Host "[DISCOVERY] Next: Import these systems into admin portal"
