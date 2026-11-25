# A stacks-only minidump of the running game (thread stacks, thread info,
# handles, unloaded modules; ~2 MB), its threads' states and its windows. Run by
# hangwatch.ps1 when a start-up stalls; by hand: hangdump.ps1 -Out <file>.
param([string]$Out = (Join-Path $env:TEMP "halo_hang.dmp"))
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class Dump {
    [DllImport("dbghelp.dll", SetLastError = true)]
    public static extern bool MiniDumpWriteDump(IntPtr hProcess, uint pid, IntPtr hFile, uint type,
        IntPtr exceptionParam, IntPtr userStreamParam, IntPtr callbackParam);
}
"@
$p = Get-Process HaloCampaignEvolved -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $p) { "no game process"; exit 1 }
"pid $($p.Id) started $($p.StartTime.ToString('HH:mm:ss')) responding $($p.Responding) title [$($p.MainWindowTitle)]"
"threads $($p.Threads.Count); waiting: " + (($p.Threads | Group-Object { "$($_.ThreadState)/$($_.WaitReason)" } | ForEach-Object { "$($_.Name)=$($_.Count)" }) -join ", ")
$f = [System.IO.File]::Create($Out)
# MiniDumpNormal (stacks) | WithThreadInfo 0x1000 | WithUnloadedModules 0x20 | WithHandleData 0x4
$ok = [Dump]::MiniDumpWriteDump($p.Handle, [uint32]$p.Id, $f.SafeFileHandle.DangerousGetHandle(), 0x1024, [IntPtr]::Zero, [IntPtr]::Zero, [IntPtr]::Zero)
$f.Close()
"dump $ok $Out $((Get-Item $Out).Length) bytes"
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class Wins {
    public delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f, IntPtr l);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
}
"@
$target = [uint32]$p.Id
$found = New-Object System.Collections.Generic.List[string]
[Wins]::EnumWindows({ param($h, $l)
    $wp = [uint32]0
    [void][Wins]::GetWindowThreadProcessId($h, [ref]$wp)
    if ($wp -eq $target) {
        $t = New-Object System.Text.StringBuilder 256; [void][Wins]::GetWindowText($h, $t, 256)
        $c = New-Object System.Text.StringBuilder 256; [void][Wins]::GetClassName($h, $c, 256)
        $found.Add("window [$t] class $c visible $([Wins]::IsWindowVisible($h))")
    }
    $true }, [IntPtr]::Zero) | Out-Null
$found
