<#
.SYNOPSIS
    Tell one game window it is the active app, without bringing it forward.

.DESCRIPTION
    A copy of the game whose window is not in front holds back online work
    (its fireteam lobby is never created). Posting WM_ACTIVATEAPP and
    WM_ACTIVATE to its own window makes it act as active, while the desktop's
    real foreground window, the cursor and the keyboard stay with whoever is
    using the PC. Used by tools/remote/instances.mjs.

.EXAMPLE
    .\activate.ps1 -ProcessId 12345
#>
param([Parameter(Mandatory = $true)][int]$ProcessId)

$ErrorActionPreference = "Stop"
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class MjolnirActivate {
    public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr lParam);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr hWnd, StringBuilder name, int max);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
    public static IntPtr GameWindow(uint wanted) {
        IntPtr found = IntPtr.Zero;
        EnumWindows((h, l) => {
            uint pid;
            GetWindowThreadProcessId(h, out pid);
            if (pid != wanted) return true;
            var name = new StringBuilder(64);
            GetClassName(h, name, 64);
            if (name.ToString() == "UnrealWindow") { found = h; return false; }
            return true;
        }, IntPtr.Zero);
        return found;
    }
}
"@
$hwnd = [MjolnirActivate]::GameWindow([uint32]$ProcessId)
if ($hwnd -eq [IntPtr]::Zero) { Write-Output "no game window for pid $ProcessId"; exit 1 }
# WM_ACTIVATEAPP (wParam TRUE), then WM_ACTIVATE (WA_ACTIVE).
[void][MjolnirActivate]::PostMessage($hwnd, 0x001C, [IntPtr]1, [IntPtr]0)
[void][MjolnirActivate]::PostMessage($hwnd, 0x0006, [IntPtr]1, [IntPtr]0)
Write-Output "activated pid $ProcessId window $hwnd"
