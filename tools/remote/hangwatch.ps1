# Watches one game start for the start-up stall seen on PC 3 (2026-11-25):
# the engine never ticks, UE4SS's scan gives up ("Fatal Error: AOB scans could
# not be completed" in UE4SS.log, 120 s in), and the game's own hang detector
# closes it ("Application Hang Detected"). It leaves no crash report, event or
# log, so this dumps the stuck game (hangdump.ps1) into hangs\ beside the
# agent while it is still there.
#
# Started by the agent's POST /launch, detached. Ends quietly once a Lua mod
# starts (a healthy start), or after -Seconds.
param(
    [Parameter(Mandatory = $true)][string]$Log,
    [int]$Seconds = 240
)
$ErrorActionPreference = "SilentlyContinue"
$started = Get-Date
$out = Join-Path $PSScriptRoot "hangs"

function Read-Log {
    # The game keeps the log open for writing.
    try {
        $stream = [System.IO.File]::Open($Log, "Open", "Read", "ReadWrite")
        $reader = New-Object System.IO.StreamReader($stream)
        $text = $reader.ReadToEnd()
        $reader.Close()
        return $text
    } catch { return "" }
}

while (((Get-Date) - $started).TotalSeconds -lt $Seconds) {
    Start-Sleep -Seconds 3
    # UE4SS writes a new log each start: one older than this start is the last one's.
    $item = Get-Item $Log
    if (-not $item -or $item.LastWriteTime -lt $started) { continue }
    $text = Read-Log
    if ($text -match "Starting Lua mod") { exit 0 }
    if ($text -match "Fatal Error: AOB scans could not be completed") {
        New-Item -ItemType Directory -Force $out | Out-Null
        $stamp = (Get-Date).ToString("yyyyMMdd-HHmmss")
        $dump = Join-Path $out "halo_hang_$stamp.dmp"
        $report = & (Join-Path $PSScriptRoot "hangdump.ps1") -Out $dump
        $lines = @("start-up stall at $stamp, $([int]((Get-Date) - $started).TotalSeconds) s after the launch") + $report
        [System.IO.File]::WriteAllLines((Join-Path $out "halo_hang_$stamp.txt"), [string[]]$lines)
        # Keep the last five.
        Get-ChildItem $out -Filter "halo_hang_*.dmp" | Sort-Object LastWriteTime -Descending | Select-Object -Skip 5 |
            ForEach-Object { Remove-Item $_.FullName; Remove-Item ([IO.Path]::ChangeExtension($_.FullName, ".txt")) }
        exit 0
    }
}
