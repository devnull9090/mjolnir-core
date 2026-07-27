<#
.SYNOPSIS
    Send keyboard and mouse input to the game window.

.DESCRIPTION
    Menus, and anything that is not exposed as a console command, still need
    real input. Posted window messages do not work here: the game reads input
    through RawInput/DirectInput, which only sees what the OS input queue
    actually delivered. So this uses SendInput with hardware scan codes, which
    means the window has to be in the foreground -- this steals focus for as
    long as the sequence runs.

    Steps are JSON, one object each:

        {"key":"Enter"}            press and release
        {"key":"W","hold":800}     hold for 800 ms, then release
        {"key":"Shift","down":true}  press without releasing
        {"key":"Shift","up":true}    release
        {"mouse":"left","hold":60}   click
        {"move":[120,-40]}           move the cursor, relative, for looking
        {"wait":500}                 do nothing for 500 ms

.EXAMPLE
    .\input.ps1 -Steps '[{"key":"Escape"},{"wait":400},{"key":"Enter"}]'
#>
param(
    [string]$ProcessName = "HaloCampaignEvolved",
    [Parameter(Mandatory = $true)][string]$Steps,
    [int]$DefaultHoldMs = 40,
    [int]$GapMs = 60
)

$ErrorActionPreference = "Stop"

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class MjolnirInput {
    [StructLayout(LayoutKind.Sequential)] public struct MOUSEINPUT {
        public int dx; public int dy; public uint mouseData; public uint dwFlags; public uint time; public IntPtr dwExtraInfo;
    }
    [StructLayout(LayoutKind.Sequential)] public struct KEYBDINPUT {
        public ushort wVk; public ushort wScan; public uint dwFlags; public uint time; public IntPtr dwExtraInfo;
    }
    [StructLayout(LayoutKind.Explicit)] public struct INPUTUNION {
        [FieldOffset(0)] public MOUSEINPUT mi;
        [FieldOffset(0)] public KEYBDINPUT ki;
    }
    [StructLayout(LayoutKind.Sequential)] public struct INPUT {
        public uint type; public INPUTUNION u;
    }
    [DllImport("user32.dll", SetLastError=true)] public static extern uint SendInput(uint nInputs, INPUT[] pInputs, int cbSize);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);

    public const uint KEYEVENTF_EXTENDEDKEY = 0x0001;
    public const uint KEYEVENTF_KEYUP       = 0x0002;
    public const uint KEYEVENTF_SCANCODE    = 0x0008;

    public static void Key(ushort scan, bool extended, bool up) {
        INPUT[] inputs = new INPUT[1];
        inputs[0].type = 1;
        inputs[0].u.ki.wVk = 0;
        inputs[0].u.ki.wScan = scan;
        uint flags = KEYEVENTF_SCANCODE;
        if (extended) flags |= KEYEVENTF_EXTENDEDKEY;
        if (up) flags |= KEYEVENTF_KEYUP;
        inputs[0].u.ki.dwFlags = flags;
        SendInput(1, inputs, Marshal.SizeOf(typeof(INPUT)));
    }

    public static void Mouse(uint flags, int dx, int dy) {
        INPUT[] inputs = new INPUT[1];
        inputs[0].type = 0;
        inputs[0].u.mi.dx = dx;
        inputs[0].u.mi.dy = dy;
        inputs[0].u.mi.dwFlags = flags;
        SendInput(1, inputs, Marshal.SizeOf(typeof(INPUT)));
    }
}
"@

# Set 1 scan codes. The game reads scan codes, not virtual keys, so a layout
# that is not US does not change any of this.
$SCAN = @{
    escape=0x01; '1'=0x02; '2'=0x03; '3'=0x04; '4'=0x05; '5'=0x06; '6'=0x07; '7'=0x08; '8'=0x09; '9'=0x0A; '0'=0x0B
    minus=0x0C; equals=0x0D; backspace=0x0E; tab=0x0F
    q=0x10; w=0x11; e=0x12; r=0x13; t=0x14; y=0x15; u=0x16; i=0x17; o=0x18; p=0x19
    lbracket=0x1A; rbracket=0x1B; enter=0x1C; ctrl=0x1D; lctrl=0x1D
    a=0x1E; s=0x1F; d=0x20; f=0x21; g=0x22; h=0x23; j=0x24; k=0x25; l=0x26
    semicolon=0x27; apostrophe=0x28; grave=0x29; tilde=0x29
    shift=0x2A; lshift=0x2A; backslash=0x2B
    z=0x2C; x=0x2D; c=0x2E; v=0x2F; b=0x30; n=0x31; m=0x32
    comma=0x33; period=0x34; slash=0x35; rshift=0x36
    alt=0x38; lalt=0x38; space=0x39; capslock=0x3A
    f1=0x3B; f2=0x3C; f3=0x3D; f4=0x3E; f5=0x3F; f6=0x40; f7=0x41; f8=0x42; f9=0x43; f10=0x44; f11=0x57; f12=0x58
}
$EXTENDED = @{
    up=0x48; down=0x50; left=0x4B; right=0x4D
    insert=0x52; delete=0x53; home=0x47; 'end'=0x4F; pageup=0x49; pagedown=0x51
    rctrl=0x1D; ralt=0x38
}

function Resolve-Key($name) {
    $key = ("" + $name).ToLower()
    if ($EXTENDED.ContainsKey($key)) { return @{ scan = $EXTENDED[$key]; extended = $true } }
    if ($SCAN.ContainsKey($key)) { return @{ scan = $SCAN[$key]; extended = $false } }
    throw "unknown key '$name'"
}

$MOUSE_FLAGS = @{
    left   = @{ down = 0x0002; up = 0x0004 }
    right  = @{ down = 0x0008; up = 0x0010 }
    middle = @{ down = 0x0020; up = 0x0040 }
}

# Focus first: SendInput goes to whatever has focus, so without this the keys
# land in whatever the user happens to be looking at.
$process = Get-Process -Name $ProcessName -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $process) {
    ConvertTo-Json -Compress @{ ok = $false; error = "no window found for process '$ProcessName'" }
    exit 1
}
$hwnd = $process.MainWindowHandle
if ([MjolnirInput]::IsIconic($hwnd)) { [MjolnirInput]::ShowWindow($hwnd, 9) | Out-Null }
if ([MjolnirInput]::GetForegroundWindow() -ne $hwnd) {
    [MjolnirInput]::SetForegroundWindow($hwnd) | Out-Null
    Start-Sleep -Milliseconds 300
}
$focused = ([MjolnirInput]::GetForegroundWindow() -eq $hwnd)

$parsed = $Steps | ConvertFrom-Json
if ($parsed -isnot [System.Array]) { $parsed = @($parsed) }

$done = @()
foreach ($step in $parsed) {
    if ($step.wait) {
        Start-Sleep -Milliseconds ([int]$step.wait)
        $done += "wait $($step.wait)ms"
        continue
    }

    if ($step.move) {
        [MjolnirInput]::Mouse(0x0001, [int]$step.move[0], [int]$step.move[1])   # MOUSEEVENTF_MOVE
        $done += "move $($step.move[0]),$($step.move[1])"
        Start-Sleep -Milliseconds $GapMs
        continue
    }

    if ($step.mouse) {
        $button = ("" + $step.mouse).ToLower()
        if (-not $MOUSE_FLAGS.ContainsKey($button)) { throw "unknown mouse button '$button'" }
        $hold = if ($step.hold) { [int]$step.hold } else { $DefaultHoldMs }
        [MjolnirInput]::Mouse($MOUSE_FLAGS[$button].down, 0, 0)
        Start-Sleep -Milliseconds $hold
        [MjolnirInput]::Mouse($MOUSE_FLAGS[$button].up, 0, 0)
        $done += "click $button ${hold}ms"
        Start-Sleep -Milliseconds $GapMs
        continue
    }

    if ($step.key) {
        $resolved = Resolve-Key $step.key
        if ($step.down) {
            [MjolnirInput]::Key($resolved.scan, $resolved.extended, $false)
            $done += "down $($step.key)"
        }
        elseif ($step.up) {
            [MjolnirInput]::Key($resolved.scan, $resolved.extended, $true)
            $done += "up $($step.key)"
        }
        else {
            $hold = if ($step.hold) { [int]$step.hold } else { $DefaultHoldMs }
            [MjolnirInput]::Key($resolved.scan, $resolved.extended, $false)
            Start-Sleep -Milliseconds $hold
            [MjolnirInput]::Key($resolved.scan, $resolved.extended, $true)
            $done += "press $($step.key) ${hold}ms"
        }
        Start-Sleep -Milliseconds $GapMs
        continue
    }

    throw "step has none of key/mouse/move/wait: $($step | ConvertTo-Json -Compress)"
}

ConvertTo-Json -Compress @{ ok = $true; focused = $focused; steps = $done }
