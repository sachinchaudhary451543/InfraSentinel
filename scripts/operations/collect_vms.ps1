param(
    [string]$Servers = "",
    [string]$OutputDir = ""
)

# default OutputDir
if (-not $OutputDir) { $OutputDir = Join-Path $PSScriptRoot "data" }
if (-not (Test-Path $OutputDir)) { New-Item -Path $OutputDir -ItemType Directory -Force | Out-Null }
$csvPath = Join-Path $OutputDir "VMInfo.csv"

# parse servers into array
$ServersArr = @()
if ($Servers -and ($Servers -is [string])) {
    $ServersArr = $Servers -split '[,;]' | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
}
elseif ($Servers -is [array]) {
    $ServersArr = $Servers
}
if (-not $ServersArr) { $ServersArr = @("localhost") }

# load saved credential if present
$credPath = Join-Path $PSScriptRoot "storedCred.xml"
$cred = $null
if (Test-Path $credPath) {
    try { $cred = Import-Clixml -Path $credPath } catch { $cred = $null }
}

# scriptblock to get VM info
$scriptBlock = {
    $hostname = $env:COMPUTERNAME
    $hostip = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias "Ethernet*" -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike '169.*' } | Select-Object -First 1 -ExpandProperty IPAddress)
    if (-not $hostip) { $hostip = "" }
    $hostos = try { (Get-CimInstance Win32_OperatingSystem).Caption } catch { "Windows" }

    $vmRows = @()
    if (Get-Command Get-VM -ErrorAction SilentlyContinue) {
        try {
            $vms = Get-VM
            foreach ($vm in $vms) {
                $row = [PSCustomObject]@{
                    Hostname = $hostname
                    VMName = $vm.Name
                    State = $vm.State.ToString()
                    CPUUsage = $vm.CPUUsage
                    MemoryAssigned = $vm.MemoryAssigned
                    Uptime = $vm.Uptime.ToString()
                    Path = $vm.Path
                    HostIP = $hostip
                    HostOS = $hostos
                }
                $vmRows += $row
            }
        } catch {}
    }

    # Fallback/Empty handle inside block
    if ($vmRows.Count -eq 0) {
        $vmRows += [PSCustomObject]@{
            Hostname = $hostname
            VMName = ''
            State = ''
            CPUUsage = ''
            MemoryAssigned = ''
            Uptime = ''
            Path = ''
            HostIP = $hostip
            HostOS = $hostos
        }
    }
    return $vmRows
}

$allResults = @()

foreach ($srv in $ServersArr) {
    try {
        if ($srv -eq "localhost" -or $srv -eq $env:COMPUTERNAME) {
            $allResults += &$scriptBlock
        }
        else {
            if ($cred) {
                $allResults += Invoke-Command -ComputerName $srv -Credential $cred -ScriptBlock $scriptBlock -ErrorAction Stop
            } else {
                $allResults += Invoke-Command -ComputerName $srv -ScriptBlock $scriptBlock -ErrorAction Stop
            }
        }
    }
    catch {
        Write-Warning "Failed to collect VMs from $srv: $($_.Exception.Message)"
        # Add entry with error if needed, or skip
    }
}

# Export results
if ($allResults.Count -gt 0) {
    # Ensure properties are flat and clean from Invoke-Command metadata
    $cleanResults = $allResults | Select-Object Hostname, VMName, State, CPUUsage, MemoryAssigned, Uptime, Path, HostIP, HostOS
    $cleanResults | Export-Csv -Path $csvPath -NoTypeInformation -Force -Encoding UTF8
    Write-Host "VM info exported to $csvPath ($( ($cleanResults | Where-Object { $_.VMName -ne '' }).Count ) VMs found)"
} else {
    Write-Host "No data collected."
}
