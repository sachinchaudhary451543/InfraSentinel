# ServerMonitorAgent.ps1 - Production Multi-Tenant Push Agent v3.0
# ================================================================
# Collects CPU, RAM, Disk, Hyper-V VM metrics and pushes to the
# ServerMonitor API every 15 seconds. Includes retry logic and
# local buffering for network resilience.
#
# Usage:
#   .\ServerMonitorAgent.ps1 -AgentKey "YOUR_KEY" -ApiUrl "https://server:3000/api/metrics"
#   .\ServerMonitorAgent.ps1 -AgentKey "YOUR_KEY" -ApiUrl "..." -MonitoringMode light
#
param(
    [Parameter(Mandatory=$true)]
    [string]$ApiKey,

    [Parameter(Mandatory=$true)]
    [int]$ServerId,

    [Parameter(Mandatory=$true)]
    [string]$ApiUrl,

    [int]$IntervalSeconds = 15,

    [ValidateSet("full", "light")]
    [string]$MonitoringMode = "full",

    [bool]$ScreenshotEnabled = $false,

    [int]$ScreenshotIntervalMinutes = 10,

    [string]$SerialNumber = "",

    [int]$MaxBufferSize = 200,
    [int]$MaxRetries = 3
)

$AgentVersion = "3.0.0"
$ErrorActionPreference = "SilentlyContinue"
$AgentDir = $PSScriptRoot
$BufferDir = Join-Path $AgentDir "data"
$BufferFile = Join-Path $BufferDir "buffer.json"
$LogFile = Join-Path $BufferDir "agent.log"

# Ensure data directory exists
if (-not (Test-Path $BufferDir)) {
    New-Item -Path $BufferDir -ItemType Directory -Force | Out-Null
}

# Preference: Replace 'localhost' with '127.0.0.1' to avoid IPv6/IPv4 priority lag
if ($ApiUrl -match "://localhost") {
    $ApiUrl = $ApiUrl -replace "://localhost", "://127.0.0.1"
}

function Write-AgentLog($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - $msg"
    Write-Host $line
    try {
        $line | Out-File -FilePath $LogFile -Append -Encoding utf8
    } catch {}
}

# ─────────────────────────────────────────────────
# METRIC COLLECTORS
# ─────────────────────────────────────────────────

function Get-SystemMetrics {
    try {
        # CPU
        $cpuInfo = Get-CimInstance Win32_Processor -ErrorAction Stop
        $virtualCores = ($cpuInfo | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum
        $cpuAvg = ($cpuInfo | Measure-Object -Property LoadPercentage -Average).Average
        $cpuPct = if ($null -ne $cpuAvg) { [math]::Round($cpuAvg, 2) } else { 0.0 }

        # RAM
        $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
        $totalRAMGB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
        $freeRAMGB = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
        $usedRAMGB = [math]::Round($totalRAMGB - $freeRAMGB, 2)
        $ramPct = if ($totalRAMGB -gt 0) { [math]::Round(($usedRAMGB / $totalRAMGB) * 100, 2) } else { 0.0 }

        # Disk - All fixed drives
        $allFixed = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" -ErrorAction Stop
        [int64]$totalDiskBytes = 0
        [int64]$freeDiskBytes = 0
        $drives = @()

        foreach ($d in $allFixed) {
            if ($null -eq $d.Size) { continue }
            $totalDiskBytes += [int64]$d.Size
            $freeDiskBytes += [int64]$d.FreeSpace
            $drives += @{
                letter   = $d.DeviceID
                total_gb = [math]::Round($d.Size / 1GB, 2)
                free_gb  = [math]::Round($d.FreeSpace / 1GB, 2)
                used_pct = if ($d.Size -gt 0) { [math]::Round((1 - ($d.FreeSpace / $d.Size)) * 100, 2) } else { 0 }
            }
        }

        $totalDiskGB = [math]::Round($totalDiskBytes / 1GB, 2)
        $freeDiskGB = [math]::Round($freeDiskBytes / 1GB, 2)
        $usedDiskGB = [math]::Round($totalDiskGB - $freeDiskGB, 2)
        $diskPct = if ($totalDiskGB -gt 0) { [math]::Round(($usedDiskGB / $totalDiskGB) * 100, 2) } else { 0.0 }

        return @{
            cpu             = $cpuPct
            ram             = $ramPct
            disk            = $diskPct
            virtual_cores   = $virtualCores
            total_ram_gb    = $totalRAMGB
            available_ram_gb = $freeRAMGB
            used_ram_gb     = $usedRAMGB
            total_disk_gb   = $totalDiskGB
            available_disk_gb = $freeDiskGB
            used_disk_gb    = $usedDiskGB
            drives          = $drives
        }
    } catch {
        Write-AgentLog "ERROR collecting metrics: $_"
        return @{ cpu = 0; ram = 0; disk = 0; virtual_cores = 0 }
    }
}

function Get-HyperVMs {
    if ($MonitoringMode -eq "light") { return @() }

    try {
        # Force-load Hyper-V module (required when running as Scheduled Task)
        Import-Module Hyper-V -ErrorAction SilentlyContinue

        if (-not (Get-Command Get-VM -ErrorAction SilentlyContinue)) {
            Write-AgentLog "Hyper-V module not available on this system"
            return @()
        }

        $vms = Get-VM -ErrorAction Stop
        $vmList = @()
        foreach ($v in $vms) {
            $vmList += @{
                name   = $v.Name
                state  = $v.State.ToString()
                cpu    = $v.CPUUsage
                ram_mb = [math]::Round($v.MemoryAssigned / 1MB, 0)
            }
        }
        Write-AgentLog "Detected $($vmList.Count) Hyper-V VMs"
        return $vmList
    } catch {
        Write-AgentLog "Hyper-V not available or error: $_"
        return @()
    }
}

function Get-SystemInfo {
    $hostname = $env:COMPUTERNAME
    try {
        $ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notlike "*Loopback*" -and $_.PrefixOrigin -ne "WellKnown" } | Select-Object -First 1).IPAddress
    } catch {
        try { $ip = [System.Net.Dns]::GetHostAddresses($hostname) | Where-Object { $_.AddressFamily -eq 'InterNetwork' } | Select-Object -First 1 -ExpandProperty IPAddressToString } catch { $ip = "Unknown" }
    }

    $osCaption = (Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue).Caption
    $osVersion = [System.Environment]::OSVersion.Version.ToString()

    $biosSerial = ""
    try {
        $biosSerial = (Get-CimInstance Win32_Bios -ErrorAction SilentlyContinue).SerialNumber
    } catch {}

    return @{
        hostname      = $hostname
        ip            = $ip
        os_info       = "$osCaption $osVersion"
        serial_number = if($SerialNumber){$SerialNumber}else{$biosSerial}
    }
}

# ─────────────────────────────────────────────────
# NETWORK / PUSH LOGIC
# ─────────────────────────────────────────────────

function Push-Payload($payload, [int]$retries = $MaxRetries) {
    $jsonBody = $payload | ConvertTo-Json -Depth 10 -Compress
    $headers = @{
        "Content-Type"    = "application/json"
        "X-Agent-Version" = $AgentVersion
    }

    for ($attempt = 1; $attempt -le $retries; $attempt++) {
        try {
            $response = Invoke-RestMethod -Uri $ApiUrl -Method Post -Body $jsonBody -Headers $headers -TimeoutSec 10
            return $response
        } catch {
            $waitSec = [math]::Pow(2, $attempt)
            if ($attempt -lt $retries) {
                Write-AgentLog "Push failed (attempt $attempt/$retries). Retrying in ${waitSec}s..."
                Start-Sleep -Seconds $waitSec
            } else {
                Write-AgentLog "Push failed after $retries attempts: $_"
                return $null
            }
        }
    }
    return $null
}

function Push-BatchBuffer {
    if (-not (Test-Path $BufferFile)) { return }

    try {
        $bufferContent = Get-Content $BufferFile -Raw | ConvertFrom-Json
        if (-not $bufferContent -or $bufferContent.Count -eq 0) {
            Remove-Item $BufferFile -Force
            return
        }

        Write-AgentLog "Flushing buffer ($($bufferContent.Count) entries)..."

        # Use batch endpoint
        $batchUrl = $ApiUrl -replace '/metrics$', '/metrics/batch'
        $batchPayload = @{
            api_key   = $ApiKey
            server_id = $ServerId
            payloads  = @($bufferContent)
        }

        $jsonBody = $batchPayload | ConvertTo-Json -Depth 10 -Compress
        $headers = @{ "Content-Type" = "application/json"; "X-Agent-Version" = $AgentVersion }

        $response = Invoke-RestMethod -Uri $batchUrl -Method Post -Body $jsonBody -Headers $headers -TimeoutSec 30

        if ($response.success) {
            Write-AgentLog "Buffer flushed: $($response.processed) entries processed"
            Remove-Item $BufferFile -Force

            # Process any commands returned during recovery flush
            if ($null -ne $response.screenshot_enabled) {
                $ScreenshotEnabled = [bool]$response.screenshot_enabled
                Write-AgentLog "CONFIG: Screenshots updated to $ScreenshotEnabled via batch"
            }
            if ($null -ne $response.screenshot_interval_minutes -and $response.screenshot_interval_minutes -gt 0) {
                $ScreenshotIntervalMinutes = [int]$response.screenshot_interval_minutes
                $screenshotIntervalSec = $ScreenshotIntervalMinutes * 60
            }
            if ($response.commands -and $response.commands.Count -gt 0) {
                Write-AgentLog "Received $($response.commands.Count) command(s) in batch response"
                Execute-PendingCommands $response.commands
            }
        }
    } catch {
        Write-AgentLog "Buffer flush failed: $_"
    }
}

function Save-ToBuffer($payload) {
    try {
        $buffer = @()
        if (Test-Path $BufferFile) {
            $existing = Get-Content $BufferFile -Raw | ConvertFrom-Json
            if ($existing) { $buffer = @($existing) }
        }

        # Strip api_key and server_id from buffered entries
        $entry = $payload.Clone()
        $entry.Remove('api_key')
        $entry.Remove('server_id')
        $buffer += $entry

        # Cap buffer size
        if ($buffer.Count -gt $MaxBufferSize) {
            $buffer = $buffer[-$MaxBufferSize..-1]
        }

        $buffer | ConvertTo-Json -Depth 10 | Set-Content $BufferFile -Encoding UTF8
        Write-AgentLog "Buffered locally ($($buffer.Count) total entries)"
    } catch {
        Write-AgentLog "Buffer save error: $_"
    }
}

function Execute-PendingCommands($commands) {
    foreach ($cmd in $commands) {
        Write-AgentLog "Executing command $($cmd.command_id): $($cmd.command)"
        try {
            $job = Start-Job -ScriptBlock { param($c) Invoke-Expression $c 2>&1 | Out-String } -ArgumentList $cmd.command
            Wait-Job $job -Timeout 60 | Out-Null
            
            if ($job.State -ne 'Completed') {
                Stop-Job $job
                $output = "ERROR: Command timed out after 60 seconds. Background processes may still be running."
                $status = "failed"
            } else {
                $output = Receive-Job $job
                $status = "completed"
            }
            Remove-Job $job -Force
        } catch {
            $output = $_.Exception.Message
            $status = "failed"
        }

        # Report result back
        $resultUrl = $ApiUrl -replace '/metrics$', '/v2/agent/commands/result'
        try {
            $resultPayload = @{
                command_id = $cmd.command_id
                output     = $output.Substring(0, [math]::Min($output.Length, 4000))
                status     = $status
            } | ConvertTo-Json -Depth 5

            Invoke-RestMethod -Uri $resultUrl -Method Post -Body $resultPayload -Headers @{
                "Content-Type" = "application/json"
                "X-Agent-Key"  = $ApiKey
            } -TimeoutSec 10 | Out-Null
            Write-AgentLog "Reported result for command $($cmd.command_id) (Status: $status)"
        } catch {
            Write-AgentLog "Failed to report command result: $_"
        }
    }
}

# ─────────────────────────────────────────────────
# SCREENSHOT CAPTURE
# ─────────────────────────────────────────────────

function Test-InteractiveSession {
    """Check if an interactive user session is active (non-headless)"""
    try {
        $sessions = query user 2>&1
        if ($LASTEXITCODE -ne 0) { return $false }
        # Look for Active sessions
        $activeSessions = $sessions | Where-Object { $_ -match 'Active' }
        return ($null -ne $activeSessions -and @($activeSessions).Count -gt 0)
    } catch {
        # Fallback: check if explorer.exe is running (indicates desktop session)
        $explorer = Get-Process -Name explorer -ErrorAction SilentlyContinue
        return ($null -ne $explorer)
    }
}

function Capture-Screenshot {
    """Capture the desktop screenshot and return the file path, or $null if skipped"""
    if (-not (Test-InteractiveSession)) {
        Write-AgentLog "SCREENSHOT: No interactive session detected, skipping capture"
        return $null
    }

    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        Add-Type -AssemblyName System.Drawing -ErrorAction Stop

        $screenshotDir = Join-Path $AgentDir "screenshots"
        if (-not (Test-Path $screenshotDir)) {
            New-Item -Path $screenshotDir -ItemType Directory -Force | Out-Null
        }

        # Capture all screens
        $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
        $bitmap = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
        $graphics.Dispose()

        # Check if the image is all black (headless/locked screen)
        $samplePixels = @()
        $step = [math]::Max(1, [int]($bounds.Width / 10))
        for ($x = 0; $x -lt $bounds.Width; $x += $step) {
            $pixel = $bitmap.GetPixel($x, [int]($bounds.Height / 2))
            $samplePixels += ($pixel.R + $pixel.G + $pixel.B)
        }
        $avgBrightness = ($samplePixels | Measure-Object -Average).Average

        if ($avgBrightness -lt 5) {
            Write-AgentLog "SCREENSHOT: Screen appears too dark or blank (Brightness: $($avgBrightness|Out-String).Trim()), skipping to avoid black image"
            $bitmap.Dispose()
            return $null
        }

        # Save as compressed JPEG
        $timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
        $filename = "$($env:COMPUTERNAME)_${timestamp}.jpg"
        $filepath = Join-Path $screenshotDir $filename

        $jpegCodec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object { $_.MimeType -eq 'image/jpeg' }
        $encoderParams = New-Object System.Drawing.Imaging.EncoderParameters(1)
        $encoderParams.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter([System.Drawing.Imaging.Encoder]::Quality, 60)
        $bitmap.Save($filepath, $jpegCodec, $encoderParams)
        $bitmap.Dispose()

        $fileSizeKB = [math]::Round((Get-Item $filepath).Length / 1024, 1)
        Write-AgentLog "SCREENSHOT: Captured $filename (${fileSizeKB}KB)"
        return $filepath
    } catch {
        Write-AgentLog "SCREENSHOT: Capture failed: $_"
        return $null
    }
}

function Upload-Screenshot($filepath) {
    """Upload screenshot to the server API for SharePoint forwarding"""
    try {
        $uploadUrl = $ApiUrl -replace '/metrics$', '/screenshots/upload'

        # Get active user for metadata
        $activeUser = ""
        try {
            $activeUser = (Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue).UserName
        } catch { $activeUser = $env:USERNAME }

        $sysInfo = Get-SystemInfo
        $filename = Split-Path $filepath -Leaf
        $fileBytes = [System.IO.File]::ReadAllBytes($filepath)
        $fileBase64 = [Convert]::ToBase64String($fileBytes)

        $uploadPayload = @{
            api_key      = $ApiKey
            server_id    = $ServerId
            filename     = $filename
            file_data    = $fileBase64
            hostname     = $sysInfo.hostname
            ip_address   = $sysInfo.ip
            os_info      = $sysInfo.os_info
            active_user  = $activeUser
            captured_at  = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
        } | ConvertTo-Json -Depth 5 -Compress

        $headers = @{
            "Content-Type"    = "application/json"
            "X-Agent-Version" = $AgentVersion
        }

        $response = Invoke-RestMethod -Uri $uploadUrl -Method Post -Body $uploadPayload -Headers $headers -TimeoutSec 30

        if ($response.success) {
            Write-AgentLog "SCREENSHOT: Uploaded $filename successfully"
            # Clean up local file after successful upload
            Remove-Item $filepath -Force -ErrorAction SilentlyContinue
            return $true
        } else {
            Write-AgentLog "SCREENSHOT: Upload rejected: $($response.error)"
            return $false
        }
    } catch {
        Write-AgentLog "SCREENSHOT: Upload failed: $_"
        return $false
    }
}

# ─────────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────────

$sysInfo = Get-SystemInfo
Write-AgentLog "================================================================"
Write-AgentLog "  ServerMonitor Agent v$AgentVersion"
Write-AgentLog "  Hostname:       $($sysInfo.hostname)"
Write-AgentLog "  IP:             $($sysInfo.ip)"
Write-AgentLog "  OS:             $($sysInfo.os_info)"
Write-AgentLog "  Mode:           $MonitoringMode"
Write-AgentLog "  Interval:       ${IntervalSeconds}s"
Write-AgentLog "  Screenshots:    $(if($ScreenshotEnabled){'ON (every ' + $ScreenshotIntervalMinutes + ' min)'}else{'OFF'})"
Write-AgentLog "  API:            $ApiUrl"
Write-AgentLog "================================================================"

# Light mode uses longer intervals
$effectiveInterval = if ($MonitoringMode -eq "light") { [math]::Max($IntervalSeconds, 60) } else { $IntervalSeconds }

# Screenshot timing
$lastScreenshotTime = [datetime]::MinValue
$screenshotIntervalSec = $ScreenshotIntervalMinutes * 60

while ($true) {
    $metrics = Get-SystemMetrics
    $vms = Get-HyperVMs
    $sysInfo = Get-SystemInfo  # Refresh in case IP changes
    $activeUser = ""
    try {
        $activeUser = (Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue).UserName
    } catch {}
    if (-not $activeUser) {
        $activeUser = $env:USERNAME
    }

    $payload = @{
        api_key         = $ApiKey
        server_id       = $ServerId
        hostname        = $sysInfo.hostname
        ip              = $sysInfo.ip
        os_info         = $sysInfo.os_info
        serial_number   = $sysInfo.serial_number
        logged_in_user  = $activeUser
        agent_version   = $AgentVersion
        monitoring_mode = $MonitoringMode
        metrics         = $metrics
        vms             = $vms
        timestamp       = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
        logs            = @(@{ type = "Info"; msg = "Heartbeat at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" })
    }

    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Pushing metrics... " -NoNewline

    $response = Push-Payload $payload

    if ($null -ne $response -and $response.success) {
        Write-Host "OK (server_id: $($response.server_id))" -ForegroundColor Green

        # Check if server config updated screenshot settings
        if ($null -ne $response.screenshot_enabled) {
            if ($ScreenshotEnabled -ne [bool]$response.screenshot_enabled) {
                $ScreenshotEnabled = [bool]$response.screenshot_enabled
                Write-AgentLog "CONFIG: Screenshots is now $(if($ScreenshotEnabled){'ENABLED'}else{'DISABLED'})"
            }
        }
        if ($null -ne $response.screenshot_interval_minutes -and $response.screenshot_interval_minutes -gt 0) {
            $newInterval = [int]$response.screenshot_interval_minutes
            if ($newInterval -ne $ScreenshotIntervalMinutes) {
                $ScreenshotIntervalMinutes = $newInterval
                $screenshotIntervalSec = $ScreenshotIntervalMinutes * 60
                Write-AgentLog "CONFIG: Screenshot interval updated to ${ScreenshotIntervalMinutes}m"
            }
        }

        # Flush local buffer if push succeeded
        Push-BatchBuffer

        # Execute any pending commands from the response
        if ($response.commands -and $response.commands.Count -gt 0) {
            Write-AgentLog "Received $($response.commands.Count) pending command(s)"
            Execute-PendingCommands $response.commands
        }
    } else {
        Write-Host "FAILED" -ForegroundColor Red
        Save-ToBuffer $payload
    }

    # ── Screenshot Capture (runs on its own timer) ──
    if ($ScreenshotEnabled) {
        $elapsed = ((Get-Date) - $lastScreenshotTime).TotalSeconds
        if ($elapsed -ge $screenshotIntervalSec) {
            Write-AgentLog "SCREENSHOT: Timer triggered (interval: ${ScreenshotIntervalMinutes}min)"
            $screenshotPath = Capture-Screenshot
            if ($null -ne $screenshotPath) {
                Upload-Screenshot $screenshotPath | Out-Null
            }
            $lastScreenshotTime = Get-Date
        }
    }

    Start-Sleep -Seconds $effectiveInterval
}
