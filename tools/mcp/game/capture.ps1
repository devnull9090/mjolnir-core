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

    Two details decide whether the frame is the whole frame:

      The thread is made per-monitor DPI aware first. PowerShell is DPI
      virtualised by default, so on a scaled display GetClientRect reports
      layout units rather than pixels — a 1280x720 client answers 853x480 at
      150% — and every measurement below inherits the lie.

      PrintWindow draws the *window*, chrome included, while the frame we want
      is the *client* area. So the bitmap is sized to the window and cropped to
      the client afterwards. Sizing it to the client instead silently keeps the
      title bar and loses an equal strip off the bottom and right, which is
      where a first-person weapon model lives.

    Prints one line of JSON so a caller can branch on which method was used.

.EXAMPLE
    .\capture.ps1 -ProcessName HaloCampaignEvolved -OutFile shot.png
#>
param(
    [string]$ProcessName = "HaloCampaignEvolved",
    [Parameter(Mandatory = $true)][string]$OutFile,
    [int]$MaxWidth = 800,
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
    [DllImport("user32.dll")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr dpiContext);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr hWnd, System.Text.StringBuilder lpClassName, int nMaxCount);
    delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    // The process's render window: top-level, class UnrealWindow, owned by
    // this pid. FindWindowEx cannot be trusted to see it, so enumerate.
    public static IntPtr GameWindow(uint pid) {
        IntPtr found = IntPtr.Zero;
        EnumWindows((hWnd, lParam) => {
            uint owner;
            GetWindowThreadProcessId(hWnd, out owner);
            if (owner != pid) { return true; }
            var cls = new System.Text.StringBuilder(256);
            GetClassName(hWnd, cls, 256);
            if (cls.ToString() != "UnrealWindow") { return true; }
            found = hWnd;
            return false;
        }, IntPtr.Zero);
        return found;
    }
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
}
"@

# Ask for real pixels before measuring anything. Per-monitor v2 is a thread
# setting and needs no restart; SetProcessDPIAware is the pre-1607 fallback and
# is a no-op once awareness is already set.
try {
    $perMonitorV2 = [IntPtr](-4)
    if ([MjolnirWin]::SetThreadDpiAwarenessContext($perMonitorV2) -eq [IntPtr]::Zero) {
        [MjolnirWin]::SetProcessDPIAware() | Out-Null
    }
} catch {
    try { [MjolnirWin]::SetProcessDPIAware() | Out-Null } catch {}
}

function Fail($message) {
    ConvertTo-Json -Compress @{ ok = $false; error = $message }
    exit 1
}

$process = Get-Process -Name $ProcessName -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowHandle -ne 0 } |
    Select-Object -First 1
if (-not $process) { Fail "no window found for process '$ProcessName'" }

# With the UE4SS GUI console open the process has two top-level windows, and
# MainWindowHandle picks the console -- a screenshot of the log view, not the
# game. The render window is the one of class UnrealWindow (the console is
# ConsoleWindowClass), so pick by class and pid. Titles are not trustworthy
# here: the game's own carries trailing spaces.
$hwnd = [MjolnirWin]::GameWindow($process.Id)
if ($hwnd -eq [IntPtr]::Zero) { $hwnd = $process.MainWindowHandle }

$clientRect = New-Object MjolnirWin+RECT
if (-not [MjolnirWin]::GetClientRect($hwnd, [ref]$clientRect)) { Fail "GetClientRect failed" }
$width = $clientRect.Right - $clientRect.Left
$height = $clientRect.Bottom - $clientRect.Top
if ($width -le 0 -or $height -le 0) { Fail "window has no client area ($width x $height)" }

# Where the client area sits on screen, and inside the window. PrintWindow
# works in window coordinates and CopyFromScreen in screen coordinates, so both
# origins are needed.
$clientOrigin = New-Object MjolnirWin+POINT
$clientOrigin.X = $clientRect.Left
$clientOrigin.Y = $clientRect.Top
[MjolnirWin]::ClientToScreen($hwnd, [ref]$clientOrigin) | Out-Null

$windowRect = New-Object MjolnirWin+RECT
if (-not [MjolnirWin]::GetWindowRect($hwnd, [ref]$windowRect)) { Fail "GetWindowRect failed" }
$windowWidth = $windowRect.Right - $windowRect.Left
$windowHeight = $windowRect.Bottom - $windowRect.Top
$insetX = $clientOrigin.X - $windowRect.Left
$insetY = $clientOrigin.Y - $windowRect.Top

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
# Sized to the whole window, because that is what PrintWindow draws.
$printed = $false
$windowBitmap = New-Object System.Drawing.Bitmap($windowWidth, $windowHeight)
$graphics = [System.Drawing.Graphics]::FromImage($windowBitmap)
$hdc = $graphics.GetHdc()
$printed = [MjolnirWin]::PrintWindow($hwnd, $hdc, 2)   # PW_RENDERFULLCONTENT
$graphics.ReleaseHdc($hdc)
$graphics.Dispose()

# Keep only the client area — the game's frame without the title bar or border.
$bitmap = New-Object System.Drawing.Bitmap($width, $height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.DrawImage(
    $windowBitmap,
    (New-Object System.Drawing.Rectangle(0, 0, $width, $height)),
    (New-Object System.Drawing.Rectangle($insetX, $insetY, $width, $height)),
    [System.Drawing.GraphicsUnit]::Pixel)
$graphics.Dispose()
$windowBitmap.Dispose()

if (-not $printed -or (Test-Blank $bitmap) -or $ForceForeground) {
    $bitmap.Dispose()
    $method = "CopyFromScreen"

    if ([MjolnirWin]::IsIconic($hwnd)) { [MjolnirWin]::ShowWindow($hwnd, 9) | Out-Null }  # SW_RESTORE
    if ([MjolnirWin]::GetForegroundWindow() -ne $hwnd) {
        [MjolnirWin]::SetForegroundWindow($hwnd) | Out-Null
        Start-Sleep -Milliseconds 250
    }

    $bitmap = New-Object System.Drawing.Bitmap($width, $height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.CopyFromScreen($clientOrigin.X, $clientOrigin.Y, 0, 0, (New-Object System.Drawing.Size($width, $height)))
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
