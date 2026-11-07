<#
.SYNOPSIS
    Bring this PC's MJOLNIR install up to date through its own launcher.

.DESCRIPTION
    Run by mjolnir-agent.ps1 (POST /launcher/update), in its own process,
    because an update can take many minutes and the agent answers one request
    at a time. It does what a player does on the Updates screen, so the
    launcher's own order applies: the launcher first (it restarts and finishes
    the rest itself), then the core, the code mods and the hub mods.

    The launcher is started with WebView2's remote debugging port (local only)
    and its page driven over the DevTools protocol: open Updates, wait for the
    check, press "Update all". Progress goes to launcher-update.json and
    launcher-update.log beside this script; mjolnir-agent.ps1 serves both.

    When the launcher updates itself it restarts without the debugging port,
    and the restarted one carries on with the rest from the note it left
    itself. From then on progress comes from the launcher's own
    --check-updates, until nothing is out of date. A launcher too old to carry
    on by itself is started and driven a second time.

    Never presses Launch: that would set aside the bridge and every hand-
    installed mod (unsupported.rs). The game is started through Steam, as ever.

    With -Uninstall <slug> it takes that hub mod off through the launcher's own
    command instead, which leaves the PC as one that never had it: the way to
    test an install from the game's map menu (docs/live_map_install.md).
#>
param(
    [Parameter(Mandatory)][string]$Exe,
    [int]$Port = 9333,
    [int]$Minutes = 90,
    [ValidatePattern('^[a-z0-9-]*$')][string]$Uninstall = ""
)

$ErrorActionPreference = "Stop"
$Utf8 = New-Object System.Text.UTF8Encoding($false)
$StateFile = Join-Path $PSScriptRoot "launcher-update.json"
$LogFile = Join-Path $PSScriptRoot "launcher-update.log"
$Deadline = (Get-Date).AddMinutes($Minutes)
$Started = (Get-Date).ToString("s")
[System.IO.File]::WriteAllText($LogFile, "", $Utf8)

function Log([string]$text) {
    $line = "$((Get-Date).ToString('HH:mm:ss')) $text"
    [System.IO.File]::AppendAllText($LogFile, "$line`r`n", $Utf8)
}

function Set-State([string]$state, [string]$step, $check = $null) {
    $value = @{ state = $state; step = $step; started = $Started; at = (Get-Date).ToString("s"); check = $check }
    [System.IO.File]::WriteAllText($StateFile, ($value | ConvertTo-Json -Depth 6), $Utf8)
    Log "$state $step"
}

function Get-Launcher { @(Get-Process mjolnir-launcher -ErrorAction SilentlyContinue) }

function Stop-Launcher {
    $running = Get-Launcher
    if ($running.Count) {
        $running | Stop-Process -Force
        foreach ($p in $running) { $p.WaitForExit(10000) | Out-Null }
    }
}

# The launcher's --check-updates (preflight.rs): what is out of date, as the
# Updates screen would list it. Runs ahead of the launcher's single-instance
# check, so it answers while a launcher window is open. A windowed exe: wait
# for it, and give up on one too old to know the flag (it opens a window).
function Get-Check {
    # Older ones open their window instead.
    $version = [version]((Get-Item $Exe).VersionInfo.ProductVersion -replace '[^0-9.].*$', '')
    if ($version -lt [version]"0.17.0") { throw "launcher $version is older than 0.17.0, the first to answer --check-updates" }
    $out = Join-Path ([System.IO.Path]::GetTempPath()) "mjolnir-launcher-check.json"
    Remove-Item $out -ErrorAction SilentlyContinue
    $p = Start-Process $Exe -ArgumentList @("--check-updates", "--out", "`"$out`"") -PassThru
    if (-not $p.WaitForExit(180000)) { $p | Stop-Process -Force; throw "--check-updates did not finish in 3 minutes" }
    if (-not (Test-Path $out)) { throw "--check-updates wrote nothing (a launcher older than 0.17.0?)" }
    return (Get-Content $out -Raw | ConvertFrom-Json)
}

function Format-Check($check) {
    $items = @($check.items | ForEach-Object { "$($_.name) $($_.installed) -> $($_.latest)" })
    $text = if ($items.Count) { "$($items.Count) out of date: $($items -join '; ')" } else { "nothing out of date" }
    if (@($check.unreachable).Count) { $text += "; could not check $(@($check.unreachable) -join ', ')" }
    return $text
}

# --- DevTools ------------------------------------------------------------------

function Get-PageSocket {
    try {
        $pages = Invoke-RestMethod "http://127.0.0.1:$Port/json" -TimeoutSec 3
    } catch { return $null }
    $page = @($pages | Where-Object { $_.type -eq "page" }) | Select-Object -First 1
    if ($page) { return $page.webSocketDebuggerUrl }
    return $null
}

# Runtime.evaluate on the launcher's page; the value of the expression (a
# promise is awaited). One connection per call: simple, and survives reloads.
function Invoke-Page([string]$expression) {
    $url = Get-PageSocket
    if (-not $url) { throw "the launcher's page is not there" }
    $socket = New-Object System.Net.WebSockets.ClientWebSocket
    $cancel = [System.Threading.CancellationToken]::None
    try {
        $socket.ConnectAsync([Uri]$url, $cancel).Wait(10000) | Out-Null
        if ($socket.State -ne "Open") { throw "could not connect to the launcher's page" }
        $message = @{ id = 1; method = "Runtime.evaluate"; params = @{ expression = $expression; awaitPromise = $true; returnByValue = $true } } |
            ConvertTo-Json -Depth 5 -Compress
        $bytes = $Utf8.GetBytes($message)
        $socket.SendAsync((New-Object System.ArraySegment[byte] -ArgumentList @(, $bytes)), "Text", $true, $cancel).Wait(10000) | Out-Null
        $buffer = New-Object byte[] 65536
        while ($true) {
            $text = New-Object System.Text.StringBuilder
            do {
                $task = $socket.ReceiveAsync((New-Object System.ArraySegment[byte] -ArgumentList @(, $buffer)), $cancel)
                if (-not $task.Wait(30000)) { throw "the launcher's page did not answer" }
                [void]$text.Append($Utf8.GetString($buffer, 0, $task.Result.Count))
            } while (-not $task.Result.EndOfMessage)
            $reply = $text.ToString() | ConvertFrom-Json
            if ($reply.id -ne 1) { continue }
            if ($reply.result.exceptionDetails) { throw "page script failed: $($reply.result.exceptionDetails.exception.description)" }
            return $reply.result.result.value
        }
    } finally {
        $socket.Dispose()
    }
}

# What the Updates screen shows (Updates.tsx): its heading and the apply
# button's label, or null before the screen is open.
$ReadScreen = @'
(() => {
  const h2 = [...document.querySelectorAll("h2")].map(e => e.textContent.trim())
    .find(t => /^(Checking for updates|\d+ updates? available|Could not check every source|Everything is up to date)/.test(t));
  const button = [...document.querySelectorAll("button")].map(b => b.textContent.trim())
    .find(t => /^(Update all|Update selected|Updating)/.test(t));
  return JSON.stringify({ heading: h2 ?? null, button: button ?? null });
})()
'@

$OpenUpdates = @'
(() => {
  const nav = [...document.querySelectorAll("button, a")].find(e => e.textContent.trim() === "Updates");
  if (!nav) return "no Updates button";
  nav.click();
  return "opened";
})()
'@

$PressUpdateAll = @'
(() => {
  const b = [...document.querySelectorAll("button")].find(e => /^Update all/.test(e.textContent.trim()));
  if (!b) return "no Update all button";
  if (b.disabled) return "Update all is disabled";
  b.click();
  return "pressed " + b.textContent.trim();
})()
'@

function Read-Screen { return (Invoke-Page $ReadScreen | ConvertFrom-Json) }

function Start-Debuggable {
    Stop-Launcher
    # Read by WebView2 when the launcher makes its webview; the port answers
    # on 127.0.0.1 only.
    $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = "--remote-debugging-port=$Port"
    try { Start-Process $Exe | Out-Null } finally { Remove-Item Env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS }
    for ($i = 0; $i -lt 60; $i++) {
        if (Get-PageSocket) {
            try { if ((Invoke-Page "document.readyState") -eq "complete") { return } } catch { }
        }
        Start-Sleep -Seconds 1
    }
    throw "the launcher started without its debugging port (is another launcher still open?)"
}

# One pass: open Updates, wait for its check, press Update all, and watch
# until the run ends. Returns "done" (nothing left on screen), "restarted"
# (the launcher went away mid-run: it is updating itself) or "nothing".
function Invoke-UpdateAll {
    Set-State "running" "starting the launcher"
    Start-Debuggable
    $opened = Invoke-Page $OpenUpdates
    if ($opened -ne "opened") { throw $opened }
    Set-State "running" "checking for updates"
    do {
        if ((Get-Date) -gt $Deadline) { throw "timed out on the launcher's check" }
        Start-Sleep -Seconds 2
        $screen = Read-Screen
    } while (-not $screen.heading -or $screen.heading -match "^Checking")
    Log "screen: $($screen.heading)"
    $script:Heading = $screen.heading
    if (-not $screen.button) { return "nothing" }
    Set-State "running" ((Invoke-Page $PressUpdateAll) + "; $($screen.heading)")
    $last = ""
    while ((Get-Date) -lt $Deadline) {
        Start-Sleep -Seconds 3
        # A page gone, or emptied as its process goes, is the launcher
        # restarting into its new self, not the end of the run.
        try { $screen = Read-Screen } catch { return "restarted" }
        if (-not $screen.heading) { return "restarted" }
        $now = "$($screen.heading) / $($screen.button)"
        if ($now -ne $last) { Log "screen: $now"; $last = $now }
        if ($screen.button -notmatch "^Updating") { return "done" }
    }
    throw "timed out while the launcher was updating"
}

# --- Run -----------------------------------------------------------------------

# The check, or null from a launcher too old to answer it (the Updates screen
# is then the only word on what is left).
function Find-Check {
    try { return Get-Check } catch { Log "no check: $_"; return $null }
}

try {
    if (Get-Process HaloCampaignEvolved -ErrorAction SilentlyContinue) { throw "the game is running; quit it first" }
    if ($Uninstall) {
        Set-State "running" "uninstalling $Uninstall"
        Start-Debuggable
        $left = Invoke-Page "window.__TAURI_INTERNALS__.invoke('hub_uninstall', { slug: '$Uninstall' }).then((s) => s.installed.length)"
        Stop-Launcher
        Set-State "done" "uninstalled $Uninstall; $left hub mods installed"
        exit 0
    }
    Set-State "running" "asking what is out of date"
    $before = Find-Check
    if ($before) {
        Log "before: $(Format-Check $before)"
        if (-not @($before.items).Count) {
            Set-State "done" "nothing out of date" $before
            exit 0
        }
    }

    $drives = 0
    while ($drives -lt 3) {
        $drives++
        $outcome = Invoke-UpdateAll
        Log "pass ${drives}: $outcome"
        if ($outcome -eq "nothing") { break }
        if ($outcome -eq "restarted") {
            # The launcher is installing its new self, and the new one finishes
            # the run from its note. Wait for it, then watch --check-updates.
            Set-State "running" "the launcher is updating itself"
            $back = $false
            for ($i = 0; $i -lt 18 -and -not $back; $i++) {
                Start-Sleep -Seconds 10
                $back = [bool](Get-Launcher).Count
            }
            # The installer did not start it again: the next pass starts it,
            # and it carries on from its note as it would have.
            if (-not $back) { Log "no launcher came back; starting it again"; continue }
            $stable = 0
            $previous = ""
            while ((Get-Date) -lt $Deadline) {
                Start-Sleep -Seconds 20
                $check = Find-Check
                # Still too old to ask (it did not update itself): drive it again.
                if (-not $check) { break }
                $text = Format-Check $check
                Set-State "running" "the new launcher is finishing the run: $text" $check
                if (-not @($check.items).Count) { break }
                # Unchanged for two minutes: a launcher too old to carry on by
                # itself, or a run that stopped. Drive it again.
                if ($text -eq $previous) { $stable++ } else { $stable = 0; $previous = $text }
                if ($stable -ge 6) { break }
            }
        }
        # The next pass's screen says what is left when there is no check.
        $after = Find-Check
        if ($after -and -not @($after.items).Count) { break }
        if ($after) { Log "still out of date: $(Format-Check $after)" }
    }
    Stop-Launcher
    $after = Find-Check
    if (-not $after) {
        if ($outcome -ne "nothing") { Set-State "failed" "after $drives passes the launcher still lists updates (and is too old to ask)"; exit 1 }
        Set-State "done" "the launcher's Updates screen says: $script:Heading (it is too old to ask)"
        exit 0
    }
    $text = Format-Check $after
    if (@($after.items).Count) { Set-State "failed" "after $drives passes: $text" $after; exit 1 }
    Set-State "done" "up to date after $drives pass$(if ($drives -ne 1) { 'es' }): $text" $after
    exit 0
} catch {
    Set-State "failed" "$_"
    exit 1
}
