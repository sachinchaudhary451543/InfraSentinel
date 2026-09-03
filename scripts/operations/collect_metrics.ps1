param(
    [string]$Servers = "",
    [string]$DriveLetters = "",
    [string]$OutputDir = ""
)

# default OutputDir
if (-not $OutputDir) { $OutputDir = Join-Path $PSScriptRoot "data" }
if (-not (Test-Path $OutputDir)) { New-Item -Path $OutputDir -ItemType Directory -Force | Out-Null }
$csvTempPath = Join-Path $OutputDir "ServerMetrics_All.csv"
$logPath = Join-Path $OutputDir "collect_metrics.log"
function Log($m) { "$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss')) - $m" | Out-File -FilePath $logPath -Append -Encoding utf8 }

# parse servers into array
$ServersArr = @()
if ($Servers -and ($Servers -is [string])) {
    $ServersArr = $Servers -split '[,;]' | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
}
elseif ($Servers -is [array]) {
    $ServersArr = $Servers
}
if (-not $ServersArr) { $ServersArr = @("localhost") }

# parse drive letters into array (normalized)
$DriveLettersArr = @()
if ($DriveLetters -and ($DriveLetters -is [string])) {
    $DriveLettersArr = $DriveLetters -split '[,;]' | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
}
elseif ($DriveLetters -is [array]) {
    $DriveLettersArr = $DriveLetters
}
# normalize to form like "C:"
$DriveLettersArr = $DriveLettersArr | ForEach-Object {
    $d = $_.ToString().Trim()
    if ($d -match '^[A-Za-z]$') { "${d}:" }             # use ${} to avoid parser error
    elseif ($d -match '^[A-Za-z]:$') { $d }
    else { $d }
}
if (-not $DriveLettersArr) { $DriveLettersArr = @() }

# load saved credential if present
$credPath = Join-Path $PSScriptRoot "storedCred.xml"
$cred = $null
if (Test-Path $credPath) {
    try { $cred = Import-Clixml -Path $credPath } catch { $cred = $null }
}

# scriptblock executed remotely (or locally)
$scriptBlock = {
    param($driveLettersStr)
    try {
        # Parse drive letters string into array inside remote session (if provided)
        $driveLetters = @()
        if ($driveLettersStr -and ($driveLettersStr -is [string])) {
            $driveLetters = $driveLettersStr -split '[,;]' | ForEach-Object {
                $v = $_.Trim()
                if ($v -match '^[A-Za-z]$') { "${v}:" } elseif ($v -match '^[A-Za-z]:$') { $v } else { $v }
            } | Where-Object { $_ -ne "" }
        }
        elseif ($driveLettersStr -is [array]) {
            $driveLetters = $driveLettersStr
        }

        # RAM
        $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
        $totalRAMGB = if ($os.TotalVisibleMemorySize) { [math]::Round($os.TotalVisibleMemorySize / 1MB, 2) } else { 0.00 }
        $freeRAMGB = if ($os.FreePhysicalMemory) { [math]::Round($os.FreePhysicalMemory / 1MB, 2) } else { 0.00 }
        $usedRAMGB = [math]::Round($totalRAMGB - $freeRAMGB, 2)
        $ramUtilPct = if ($totalRAMGB -gt 0) { [math]::Round(($usedRAMGB / $totalRAMGB) * 100, 2) } else { 0.00 }

        # Drives: only fixed drives
        $allFixed = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" -ErrorAction Stop
        # if no specific drives requested, use all fixed
        if (-not $driveLetters -or $driveLetters.Count -eq 0) {
            $selected = $allFixed
        }
        else {
            # match case-insensitively
            $lettersUp = $driveLetters | ForEach-Object { $_.ToUpper() }
            $selected = $allFixed | Where-Object { $lettersUp -contains ($_.DeviceID.ToUpper()) }
            if (-not $selected -or $selected.Count -eq 0) {
                # fallback to all fixed if none matched
                $selected = $allFixed
            }
        }

        [int64]$sizeSumBytes = 0
        [int64]$freeSumBytes = 0
        $driveDetails = @()
        foreach ($d in $selected) {
            if ($null -eq $d.Size) { continue }
            $sizeSumBytes += [int64]$d.Size
            $freeSumBytes += [int64]$d.FreeSpace
            $driveDetails += [PSCustomObject]@{
                Drive    = $d.DeviceID
                Total_GB = [math]::Round($d.Size / 1GB, 2)
                Free_GB  = [math]::Round($d.FreeSpace / 1GB, 2)
                Used_GB  = [math]::Round((($d.Size - $d.FreeSpace) / 1GB), 2)
                Util_Pct = if ($d.Size -gt 0) { [math]::Round((1 - ($d.FreeSpace / $d.Size)) * 100, 2) } else { 0 }
            }
        }

        $totalSSDGB = if ($sizeSumBytes -gt 0) { [math]::Round($sizeSumBytes / 1GB, 2) } else { 0.00 }
        $freeSSDGB = if ($freeSumBytes -gt 0) { [math]::Round($freeSumBytes / 1GB, 2) } else { 0.00 }
        $usedSSDGB = [math]::Round($totalSSDGB - $freeSSDGB, 2)
        $totalSSDTB = [math]::Round($totalSSDGB / 1024, 2)
        $freeSSDTB = [math]::Round($freeSSDGB / 1024, 2)
        $usedSSDTB = [math]::Round($usedSSDGB / 1024, 2)
        $ssdUtilPct = if ($totalSSDGB -gt 0) { [math]::Round(($usedSSDGB / $totalSSDGB) * 100, 2) } else { 0.00 }

        # CPU
        $cpuInfo = Get-CimInstance Win32_Processor -ErrorAction Stop
        $virtualCores = ($cpuInfo | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum
        try {
            $cpuAvg = (Get-CimInstance Win32_Processor -ErrorAction Stop | Measure-Object -Property LoadPercentage -Average).Average
            $cpuUtilPct = if ($null -ne $cpuAvg) { [math]::Round($cpuAvg, 2) } else { 0.00 }
        }
        catch {
            $cpuUtilPct = 0.00
        }

        $checked = if ($selected) { ($selected | ForEach-Object { $_.DeviceID }) } else { @() }
        $checkedStr = if ($checked.Count -gt 0) { [string]::Join(";", $checked) } else { "" }
        $detailsJson = if ($driveDetails.Count -gt 0) { $driveDetails | ConvertTo-Json -Compress } else { "[]" }

        # Hyper-V Detection
        $hypervEnabled = 0
        if (Get-Service -Name "vmms" -ErrorAction SilentlyContinue) {
            $hypervEnabled = 1
        }
        elseif (Get-WindowsFeature -Name Hyper-V -ErrorAction SilentlyContinue | Where-Object { $_.InstallState -eq 'Installed' }) {
            $hypervEnabled = 1
        }

        # return stable property names expected by Python
        [PSCustomObject]@{
            Timestamp           = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
            Hostname            = $env:COMPUTERNAME
            VirtualCores        = $virtualCores
            CPU_Util_Percent    = $cpuUtilPct
            TotalRAM_GB         = $totalRAMGB
            AvailableRAM_GB     = $freeRAMGB
            UsedRAM_GB          = $usedRAMGB
            RAMUtil_Percent     = $ramUtilPct
            TotalSSD_GB         = $totalSSDGB
            AvailableSSD_GB     = $freeSSDGB
            UsedSSD_GB          = $usedSSDGB
            TotalSSD_TB         = $totalSSDTB
            AvailableSSD_TB     = $freeSSDTB
            UsedSSD_TB          = $usedSSDTB
            SSDUtil_Percent     = $ssdUtilPct
            IsHyperV_Enabled    = $hypervEnabled
            DriveLettersChecked = $checkedStr
            Drives_Details      = $detailsJson
            Error               = $null
        }
    }
    catch {
        $err = $_.Exception.Message
        Write-Error "Error collecting metrics: $err"
        [PSCustomObject]@{
            Timestamp           = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
            Hostname            = $env:COMPUTERNAME
            VirtualCores        = $null
            CPU_Util_Percent    = $null
            TotalRAM_GB         = $null
            AvailableRAM_GB     = $null
            UsedRAM_GB          = $null
            RAMUtil_Percent     = $null
            TotalSSD_GB         = $null
            AvailableSSD_GB     = $null
            UsedSSD_GB          = $null
            TotalSSD_TB         = $null
            AvailableSSD_TB     = $null
            UsedSSD_TB          = $null
            SSDUtil_Percent     = $null
            IsHyperV_Enabled    = 0
            DriveLettersChecked = ($driveLetters -join ';')
            Drives_Details      = "[]"
            Error               = $err
        }
    }
}

# collect results
$results = @()
foreach ($s in $ServersArr) {
    Log "Collecting from $s (drives: $($DriveLettersArr -join ','))"
    try {
        if ($s -eq "localhost" -or $s -eq "." -or $s -eq "127.0.0.1" -or $s.ToLower() -eq $env:COMPUTERNAME.ToLower()) {
            $r = & $scriptBlock ($DriveLetters -as [string])
        }
        elseif ($cred) {
            $r = Invoke-Command -ComputerName $s -Credential $cred -ScriptBlock $scriptBlock -ArgumentList ($DriveLetters -as [string])
        }
        else {
            $r = Invoke-Command -ComputerName $s -ScriptBlock $scriptBlock -ArgumentList ($DriveLetters -as [string])
        }
        if ($r) { $results += $r }
    }
    catch {
        $em = $_.Exception.Message
        Log "Failed to collect from $s : $em"
        $results += [PSCustomObject]@{
            Timestamp           = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
            Hostname            = $s
            DriveLettersChecked = ($DriveLettersArr -join ';')
            Error               = $em
        }
    }
}

if ($results.Count -gt 0) {
    # ensure consistent columns order
    $results = $results | Select-Object Timestamp, Hostname, VirtualCores, CPU_Util_Percent, TotalRAM_GB, AvailableRAM_GB, UsedRAM_GB, RAMUtil_Percent, TotalSSD_GB, AvailableSSD_GB, UsedSSD_GB, TotalSSD_TB, AvailableSSD_TB, UsedSSD_TB, SSDUtil_Percent, IsHyperV_Enabled, DriveLettersChecked, Drives_Details, Error
    $results | Export-Csv -Path $csvTempPath -NoTypeInformation -Encoding UTF8 -Force
    Log "Results saved to $csvTempPath"
}
else {
    Log "No results collected"
}
# also print a table locally for debugging
$results | Format-Table -AutoSize