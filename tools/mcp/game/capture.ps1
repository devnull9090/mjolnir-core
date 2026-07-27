<#
.SYNOPSIS
    Capture the game window to a PNG.

.DESCRIPTION
    Two ways to photograph a window, tried in order, because neither works
    everywhere:

      PrintWindow with PW_RENDERFULLCONTENT asks the window to redraw itself
      into a bitmap. It does not need focus and does not care what is on top,
      which is what you want from a tool that runs while someone else is using
      the machine. Some D3D12 swap chains return a blank frame.

      CopyFromScreen reads the desktop where the window is. It always shows
      what a D3D swap chain presented, but only if the window is visible, so it
      is the fallback rather than the default.

    "Blank" is decided by sampling rather than assumed, so the fallback fires on
    evidence. Exclusive fullscreen defeats both; launch the game windowed.

    Prints one line of JSON so a caller can branch on which method was used.

.EXAMPLE
    .\capture.ps1 -ProcessName HaloCampaignEvolved -OutFile shot.png
#>
param(
    [string]$ProcessName = "HaloCampaignEvolved",
    [Parameter(Mandatory = $true)][string]$OutFile,
    [int]$MaxWidth = 1280,
    [switch]$ForceForeground
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class MjolnirWin {
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdcBlt, uint nFlags);
    [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr hWnd, out RECT lpRect);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
    [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr hWnd, ref POINT lpPoint);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
}
"@

function Fail($message) {
    ConvertTo-Json -Compress @{ ok = $false; error = $message }
    exit 1
}

$process = Get-Process -Name $ProcessName -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowHandle -ne 0 } |
    Select-Object -First 1
if (-not $process) { Fail "no window found for process '$ProcessName'" }

$hwnd = $process.MainWindowHandle

$clientRect = New-Object MjolnirWin+RECT
if (-not [MjolnirWin]::GetClientRect($hwnd, [ref]$clientRect)) { Fail "GetClientRect failed" }
$width = $clientRect.Right - $clientRect.Left
$height = $clientRect.Bottom - $clientRect.Top
if ($width -le 0 -or $height -le 0) { Fail "window has no client area ($width x $height)" }

# Sample a grid instead of every pixel: enough to tell a rendered frame from a
# blank one, cheap enough to run on every capture.
function Test-Blank([System.Drawing.Bitmap]$bitmap) {
    $lit = 0
    for ($x = 4; $x -lt $bitmap.Width; $x += [math]::Max(1, [int]($bitmap.Width / 16))) {
        for ($y = 4; $y -lt $bitmap.Height; $y += [math]::Max(1, [int]($bitmap.Height / 16))) {
            $pixel = $bitmap.GetPixel($x, $y)
            if (($pixel.R + $pixel.G + $pixel.B) -gt 24) { $lit++ }
        }
    }
    return ($lit -lt 3)
}

$method = "PrintWindow"
$bitmap = New-Object System.Drawing.Bitmap($width, $height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$hdc = $graphics.GetHdc()
$printed = [MjolnirWin]::PrintWindow($hwnd, $hdc, 2)   # PW_RENDERFULLCONTENT
$graphics.ReleaseHdc($hdc)
$graphics.Dispose()

if (-not $printed -or (Test-Blank $bitmap) -or $ForceForeground) {
    $bitmap.Dispose()
    $method = "CopyFromScreen"

    if ([MjolnirWin]::IsIconic($hwnd)) { [MjolnirWin]::ShowWindow($hwnd, 9) | Out-Null }  # SW_RESTORE
    if ([MjolnirWin]::GetForegroundWindow() -ne $hwnd) {
        [MjolnirWin]::SetForegroundWindow($hwnd) | Out-Null
        Start-Sleep -Milliseconds 250
    }

    $origin = New-Object MjolnirWin+POINT
    $origin.X = $clientRect.Left
    $origin.Y = $clientRect.Top
    [MjolnirWin]::ClientToScreen($hwnd, [ref]$origin) | Out-Null

    $bitmap = New-Object System.Drawing.Bitmap($width, $height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.CopyFromScreen($origin.X, $origin.Y, 0, 0, (New-Object System.Drawing.Size($width, $height)))
    $graphics.Dispose()
}

$blank = Test-Blank $bitmap

# Downscale on the way out: a 4K frame is megabytes of base64 for no extra
# legibility once it reaches a model.
$outputBitmap = $bitmap
if ($MaxWidth -gt 0 -and $width -gt $MaxWidth) {
    $scaledHeight = [int][math]::Round($height * ($MaxWidth / $width))
    $outputBitmap = New-Object System.Drawing.Bitmap($MaxWidth, $scaledHeight)
    $graphics = [System.Drawing.Graphics]::FromImage($outputBitmap)
    $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $graphics.DrawImage($bitmap, 0, 0, $MaxWidth, $scaledHeight)
    $graphics.Dispose()
}

$directory = Split-Path -Parent $OutFile
if ($directory -and -not (Test-Path $directory)) { New-Item -ItemType Directory -Path $directory -Force | Out-Null }
$outputBitmap.Save($OutFile, [System.Drawing.Imaging.ImageFormat]::Png)

$result = @{
    ok      = $true
    method  = $method
    path    = $OutFile
    width   = $outputBitmap.Width
    height  = $outputBitmap.Height
    source  = "$width x $height"
    blank   = $blank
    pid     = $process.Id
}
if ($outputBitmap -ne $bitmap) { $outputBitmap.Dispose() }
$bitmap.Dispose()

ConvertTo-Json -Compress $result
