# ServerMonitorAgent.ps1 - Production Multi-Tenant Agent v3.1
# Collects: CPU, RAM, Disk, active app, window title, idle time, running apps, Hyper-V VMs
# Sends: JSON payload every 10s to /api/metrics
# Screenshots: every 10 minutes via /api/screenshot

param(
    [string]$ApiKey = "d5c6640cc90b120592c8469d58030fb3f13a7f2d91cc472e20098fc0ba3de17f",
    [string]$ServerUrl = "http://localhost:3000"
)

# ── Win32 API for idle detection and foreground window ──
Add-Type @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public class Win32 {
    [StructLayout(LayoutKind.Sequential)]
    public struct LASTINPUTINFO {
        public uint cbSize;
        public uint dwTime;
    }
    [DllImport("user32.dll")]
    public static extern bool GetLastInputInfo(ref LASTINPUTINFO plii);
    
    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();
    
    [DllImport("user32.dll")]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
    
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
}
'@

function Get-IdleTime {
    $lii = New-Object Win32+LASTINPUTINFO
    $lii.cbSize = [System.Runtime.InteropServices.Marshal]::SizeOf($lii)
    if ([Win32]::GetLastInputInfo([ref]$lii)) {
        $idleMs = [Environment]::TickCount - $lii.dwTime
        return [math]::Round($idleMs / 1000, 0)
    }
    return 0
}

function Get-ActiveWindowTitle {
    $hwnd = [Win32]::GetForegroundWindow()
    $sb = New-Object System.Text.StringBuilder 256
    [Win32]::GetWindowText($hwnd, $sb, $sb.Capacity) | Out-Null
    return $sb.ToString()
}

function Get-ActiveApp {
    try {
        $hwnd = [Win32]::GetForegroundWindow()
        $procId = 0
        [Win32]::GetWindowThreadProcessId($hwnd, [ref]$procId) | Out-Null
        if ($procId -gt 0) {
            $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
            if ($proc) { return $proc.Name }
        }
    }
    catch {}
    return "Unknown"
}

function Get-RunningApps {
    # Top 20 apps by CPU, excluding system processes
    try {
        $apps = Get-Process | Where-Object { $_.MainWindowTitle -ne "" } |
        Sort-Object CPU -Descending |
        Select-Object -First 20 |
        ForEach-Object { $_.Name }
        return ($apps -join ", ")
    }
    catch {}
    return ""
}

function Get-Metrics {
    $cpu = 0
    try {
        $cpu = (Get-Counter '\Processor(_Total)\% Processor Time' -ErrorAction SilentlyContinue).CounterSamples.CookedValue
    }
    catch {}

    $mem = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
    $ram = if ($mem) { (($mem.TotalVisibleMemorySize - $mem.FreePhysicalMemory) / $mem.TotalVisibleMemorySize) * 100 } else { 0 }

    $disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'" -ErrorAction SilentlyContinue
    $disk_usage = if ($disk) { (($disk.Size - $disk.FreeSpace) / $disk.Size) * 100 } else { 0 }

    return @{
        cpu  = [math]::Round($cpu, 2)
        ram  = [math]::Round($ram, 2)
        disk = [math]::Round($disk_usage, 2)
    }
}

function Get-VMs {
    try {
        if (Get-Command Get-VM -ErrorAction SilentlyContinue) {
            return @(Get-VM | ForEach-Object {
                    @{
                        name  = $_.Name
                        state = $_.State.ToString()
                        cpu   = $_.CPUUsage
                        ram   = [math]::Round($_.MemoryAssigned / 1MB, 0)
                    }
                })
        }
    }
    catch {}
    return @()
}

function Send-Screenshot {
    try {
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing

        $screen = [System.Windows.Forms.Screen]::PrimaryScreen
        $width = $screen.Bounds.Width
        $height = $screen.Bounds.Height

        $bitmap = New-Object System.Drawing.Bitmap $width, $height
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        $graphics.CopyFromScreen($screen.Bounds.Left, $screen.Bounds.Top, 0, 0, $bitmap.Size)

        $tempPath = [System.IO.Path]::GetTempFileName() + ".jpg"
        $bitmap.Save($tempPath, [System.Drawing.Imaging.ImageFormat]::Jpeg)
        $graphics.Dispose()
        $bitmap.Dispose()

        # Upload via multipart form manually (PowerShell 5.1 compatible)
        $uri = "$ServerUrl/api/screenshot?api_key=$ApiKey"
        $boundary = [System.Guid]::NewGuid().ToString()
        $LF = "`r`n"
        
        # Proper multipart binary generation
        $fileBytes = [System.IO.File]::ReadAllBytes($tempPath)
        $boundaryBytes = [System.Text.Encoding]::ASCII.GetBytes("--$boundary$LF")
        $headerBytes = [System.Text.Encoding]::ASCII.GetBytes("Content-Disposition: form-data; name=`"file`"; filename=`"screenshot.jpg`"$LF$LF")
        $trailerBytes = [System.Text.Encoding]::ASCII.GetBytes("$LF--$boundary--$LF")

        $memoryStream = New-Object System.IO.MemoryStream
        $memoryStream.Write($boundaryBytes, 0, $boundaryBytes.Length)
        $memoryStream.Write($headerBytes, 0, $headerBytes.Length)
        $memoryStream.Write($fileBytes, 0, $fileBytes.Length)
        $memoryStream.Write($trailerBytes, 0, $trailerBytes.Length)

        $request = [System.Net.WebRequest]::Create($uri)
        $request.Method = "POST"
        $request.ContentType = "multipart/form-data; boundary=$boundary"
        $request.ContentLength = $memoryStream.Length

        $requestStream = $request.GetRequestStream()
        $memoryStream.Position = 0
        $memoryStream.CopyTo($requestStream)
        $requestStream.Close()

        $response = $request.GetResponse()
        $response.Close()
        
        Remove-Item $tempPath -ErrorAction SilentlyContinue
        Write-Host "  Screenshot captured and uploaded." -ForegroundColor Green
    }
    catch {
        Write-Host "  Screenshot failed: $_" -ForegroundColor Yellow
    }
}

# ── Main Loop ──
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  ServerMonitor Agent v3.1" -ForegroundColor Cyan
Write-Host "  Server : $ServerUrl" -ForegroundColor Cyan
Write-Host "  Host   : $env:COMPUTERNAME" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

$lastScreenshot = (Get-Date).AddMinutes(-11)  # Force first screenshot on start
$loopCount = 0
$featurePolicy = @{
    system_metrics = $true; productivity = $true; screenshots = $true
    process_inventory = $true; installed_software = $true
    hyperv_inventory = $true; browser_activity = $true
}

function Feature-Enabled([string]$name) {
    return $featurePolicy[$name] -ne $false
}

while ($true) {
    $loopCount++

    $payload = @{
        api_key        = $ApiKey
        hostname       = $env:COMPUTERNAME
        logged_in_user = $env:USERNAME
        idle_time      = Get-IdleTime
    }
    if (Feature-Enabled 'system_metrics') { $payload.metrics = Get-Metrics }
    if (Feature-Enabled 'productivity') {
        $payload.active_app = Get-ActiveApp
        $payload.window_title = Get-ActiveWindowTitle
    }
    if (Feature-Enabled 'process_inventory') { $payload.running_apps = Get-RunningApps }
    if (Feature-Enabled 'hyperv_inventory') { $payload.vms = Get-VMs }

    try {
        # 1. Push metrics
        $resp = Invoke-RestMethod -Uri "$ServerUrl/api/metrics" `
            -Method Post `
            -Body ($payload | ConvertTo-Json -Depth 10) `
            -ContentType "application/json" `
            -TimeoutSec 5

        if ($resp.features) {
            foreach ($feature in $resp.features.PSObject.Properties) {
                $featurePolicy[$feature.Name] = [bool]$feature.Value
            }
        }

        if ($loopCount % 6 -eq 1) {
            # Log every ~60s
            $cpuLog = if ($payload.metrics) { "$([math]::Round($payload.metrics.cpu,1))%" } else { 'disabled' }
            $ramLog = if ($payload.metrics) { "$([math]::Round($payload.metrics.ram,1))%" } else { 'disabled' }
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Heartbeat sent. CPU=$cpuLog RAM=$ramLog Idle=$($payload.idle_time)s" -ForegroundColor Gray
        }

        # 2. Screenshot (every 10 minutes)
        if ((Feature-Enabled 'screenshots') -and (Get-Date) -gt $lastScreenshot.AddMinutes(10)) {
            Send-Screenshot
            $lastScreenshot = Get-Date
        }

        # 3. Poll for remote commands
        $cmdResponse = Invoke-RestMethod -Uri "$ServerUrl/api/command" `
            -Method Post `
            -Body (@{ api_key = $ApiKey } | ConvertTo-Json) `
            -ContentType "application/json" `
            -TimeoutSec 5

        if ($cmdResponse.commands -and $cmdResponse.commands.Count -gt 0) {
            foreach ($cmd in $cmdResponse.commands) {
                Write-Host "  >> Executing: $($cmd.command)" -ForegroundColor Yellow
                try {
                    switch -Regex ($cmd.command) {
                        "^screenshot$" { Send-Screenshot }
                        "^restart$" { Restart-Computer -Force }
                        "^shutdown$" { Stop-Computer -Force }
                        "^RESTART_AGENT$" { Write-Host "Agent restart requested"; exit 0 }
                        "install" { Start-Process msiexec.exe -ArgumentList "/i $($cmd.params) /qn" -Wait }
                        default { Invoke-Expression $cmd.command }
                    }
                }
                catch {
                    Write-Host "  Command failed: $_" -ForegroundColor Red
                }
            }
        }
    }
    catch {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Connection error: $_" -ForegroundColor Red
    }

    Start-Sleep -Seconds 10
}
