<#
.SYNOPSIS
    Let a second PC's game be driven from the development PC over the LAN.

.DESCRIPTION
    Two-PC tests (docs/two_pc_test.md) need the second PC's game files replaced,
    its logs read and its game started again many times an hour, and doing that
    by zip and USB stick is most of the time a test takes. This is a small HTTP
    server for that PC, driven by tools/remote/remote.mjs on the development PC:

        GET  /status                          game process, bridge heartbeat
        POST /bridge?op=lua|console|ping      a call through the MJOLNIR bridge
        POST /launch                          start the game through Steam
        POST /quit[?force=1]                  close it
        GET  /file?root=R&path=P              read a file
        PUT  /file?root=R&path=P              write one (a loaded DLL is moved
                                              aside first, so it can be replaced
                                              while the game runs)
        GET  /list?root=R&path=P              a directory listing
        POST /install-bridge                  install the bundled bridge mod
        POST /input                           keyboard and mouse steps for the
                                              game window (input.ps1 beside this
                                              script; steals focus while it runs)
        POST /restart-agent                   start this script again (after its
                                              files were replaced) and exit

    Roots: "ue4ss" (the game's UE4SS folder, Mods under it), "saved"
    (%LOCALAPPDATA%\Meteorite\Saved: crash reports, config) and "agent" (this
    script's folder, so the agent can be updated from the development PC).
    Paths cannot leave their root. A token holder can already run Lua in the
    game, and now replace and restart this agent and run its input script, so
    the token is as good as a login to this PC's game account: keep it to the
    LAN and the development PC.

    Every request needs the token in an X-Mjolnir-Token header, and only
    private-network addresses are served. The token is made on the first run
    and kept in agent-token.txt beside this script. Close this window to stop.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\mjolnir-agent.ps1
#>
param(
    [int]$Port = 47820,
    [string]$GameDir
)

$ErrorActionPreference = "Stop"
$AgentVersion = "2"

# --- Where things are --------------------------------------------------------

if (-not $GameDir) {
    $candidates = @(
        "C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved",
        "C:\Program Files\Steam\steamapps\common\Halo Campaign Evolved"
    )
    $libraryIndex = "C:\Program Files (x86)\Steam\steamapps\libraryfolders.vdf"
    if (Test-Path $libraryIndex) {
        Select-String -Path $libraryIndex -Pattern '"path"\s+"([^"]+)"' -AllMatches | ForEach-Object {
            foreach ($match in $_.Matches) {
                $candidates += (Join-Path ($match.Groups[1].Value -replace '\\\\', '\') "steamapps\common\Halo Campaign Evolved")
            }
        }
    }
    $GameDir = $candidates | Where-Object {
        Test-Path (Join-Path $_ "Meteorite\Binaries\Win64\HaloCampaignEvolved.exe")
    } | Select-Object -First 1
}
if (-not $GameDir) { throw "Halo Campaign Evolved not found; pass -GameDir <install root>." }

$Ue4ss = Join-Path $GameDir "Meteorite\Binaries\Win64\ue4ss"
$Roots = @{
    ue4ss = $Ue4ss
    saved = Join-Path $env:LOCALAPPDATA "Meteorite\Saved"
    agent = $PSScriptRoot
}
$BridgeDir = Join-Path $Ue4ss "mjolnir-bridge"

$TokenFile = Join-Path $PSScriptRoot "agent-token.txt"
if (-not (Test-Path $TokenFile)) {
    $bytes = New-Object byte[] 16
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    [System.IO.File]::WriteAllText($TokenFile, (($bytes | ForEach-Object { $_.ToString("x2") }) -join ""))
}
$Token = (Get-Content $TokenFile -Raw).Trim()
$Utf8 = New-Object System.Text.UTF8Encoding($false)

# --- Helpers -----------------------------------------------------------------

function Resolve-RootPath([string]$root, [string]$relative) {
    if (-not $Roots.ContainsKey($root)) { throw "unknown root '$root' (ue4ss or saved)" }
    if ($relative -match '\.\.|:' -or $relative.StartsWith("\") -or $relative.StartsWith("/")) {
        throw "path must stay inside its root"
    }
    $full = [System.IO.Path]::GetFullPath((Join-Path $Roots[$root] $relative))
    if (-not $full.StartsWith([System.IO.Path]::GetFullPath($Roots[$root]), [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "path must stay inside its root"
    }
    return $full
}

function Test-Private([System.Net.IPAddress]$address) {
    $b = $address.MapToIPv4().GetAddressBytes()
    return ($b[0] -eq 10) -or ($b[0] -eq 127) -or ($b[0] -eq 192 -and $b[1] -eq 168) -or
        ($b[0] -eq 172 -and $b[1] -ge 16 -and $b[1] -le 31)
}

function Get-Game { Get-Process HaloCampaignEvolved -ErrorAction SilentlyContinue | Select-Object -First 1 }

# The MJOLNIR bridge's wire format (mods/MJOLNIRBridge/Scripts/main.lua).
function Read-BridgeMessage([string]$file) {
    try { $bytes = [System.IO.File]::ReadAllBytes($file) } catch { return $null }
    $text = $Utf8.GetString($bytes)
    $separator = $text.IndexOf("`n--`n")
    if ($separator -lt 0) { return $null }
    $headers = @{}
    foreach ($line in $text.Substring(0, $separator).Split("`n")) {
        if ($line -match '^(\S+)\s*(.*)$') { $headers[$Matches[1]] = $Matches[2] }
    }
    $headBytes = $Utf8.GetByteCount($text.Substring(0, $separator + 4))
    $want = [int]($headers["bytes"])
    if ($bytes.Length - $headBytes -lt $want) { return $null }
    return @{ headers = $headers; body = $Utf8.GetString($bytes, $headBytes, $want) }
}

$script:NextId = [int]((Get-Date).Ticks % 1000000)
function Invoke-Bridge([string]$op, [string]$body, [int]$timeoutMs) {
    New-Item -ItemType Directory -Path $BridgeDir -Force | Out-Null
    $request = Join-Path $BridgeDir "request.txt"
    $response = Join-Path $BridgeDir "response.txt"
    $script:NextId++
    $id = $script:NextId
    Remove-Item $response -ErrorAction SilentlyContinue
    $payload = $Utf8.GetBytes($body)
    $head = $Utf8.GetBytes("mjolnir-bridge 1`nid $id`nop $op`nbytes $($payload.Length)`n--`n")
    $temporary = Join-Path $BridgeDir "request.$id.tmp"
    [System.IO.File]::WriteAllBytes($temporary, $head + $payload)
    Move-Item $temporary $request -Force
    $deadline = (Get-Date).AddMilliseconds($timeoutMs)
    while ((Get-Date) -lt $deadline) {
        $message = Read-BridgeMessage $response
        if ($message -and [int]$message.headers["id"] -eq $id) {
            return @{ ok = ($message.headers["ok"] -eq "1"); body = $message.body }
        }
        if (-not (Get-Game)) { return @{ ok = $false; body = "the game is not running" } }
        Start-Sleep -Milliseconds 50
    }
    return @{ ok = $false; body = "the bridge did not answer within $timeoutMs ms" }
}

function Get-BridgeStatus {
    $message = Read-BridgeMessage (Join-Path $BridgeDir "status.txt")
    if (-not $message) { return $null }
    $fields = @{}
    foreach ($line in $message.body.Split("`n")) { if ($line -match '^(\S+)\s+(.*)$') { $fields[$Matches[1]] = $Matches[2] } }
    return $fields
}

function Install-Bridge {
    $source = Join-Path $PSScriptRoot "MJOLNIRBridge"
    if (-not (Test-Path $source)) { throw "no MJOLNIRBridge folder beside the agent" }
    $mods = Join-Path $Ue4ss "Mods"
    $destination = Join-Path $mods "MJOLNIRBridge"
    if (Test-Path $destination) { Remove-Item $destination -Recurse -Force }
    Copy-Item $source $destination -Recurse
    $modsTxt = Join-Path $mods "mods.txt"
    $lines = if (Test-Path $modsTxt) { @(Get-Content $modsTxt) } else { @() }
    $note = "already enabled"
    if (-not ($lines | Where-Object { $_ -match '^\s*MJOLNIRBridge\s*:' })) {
        # Keybinds must stay last in mods.txt; add above the comment that introduces it.
        $anchor = ($lines | Select-String -Pattern "Built-in keybinds" | Select-Object -First 1)
        if ($anchor) {
            $index = $anchor.LineNumber - 1
            $lines = $lines[0..($index - 1)] + "MJOLNIRBridge : 1" + $lines[$index..($lines.Count - 1)]
        } else {
            $lines += "MJOLNIRBridge : 1"
        }
        [System.IO.File]::WriteAllLines($modsTxt, $lines, $Utf8)   # no BOM: UE4SS would read it into the first name
        $note = "enabled in mods.txt"
    }
    New-Item -ItemType Directory -Path $BridgeDir -Force | Out-Null
    return "bridge installed, $note; restart the game to load it"
}

# Replace a file even while the game holds it open: a loaded DLL can be renamed
# though not overwritten.
function Write-RootFile([string]$full, [byte[]]$bytes) {
    New-Item -ItemType Directory -Path (Split-Path $full) -Force | Out-Null
    if (Test-Path $full) {
        try {
            [System.IO.File]::WriteAllBytes($full, $bytes)
            return "written"
        } catch {
            $aside = "$full.old-$((Get-Date).ToString('HHmmss'))"
            Move-Item $full $aside
            [System.IO.File]::WriteAllBytes($full, $bytes)
            return "written; the open file was moved to $(Split-Path $aside -Leaf)"
        }
    }
    [System.IO.File]::WriteAllBytes($full, $bytes)
    return "written"
}

# --- HTTP --------------------------------------------------------------------

function Send-Response($stream, [int]$status, [byte[]]$body, [string]$type = "application/json") {
    $reason = @{ 200 = "OK"; 400 = "Bad Request"; 401 = "Unauthorized"; 403 = "Forbidden"; 404 = "Not Found"; 500 = "Internal Server Error" }[$status]
    $head = $Utf8.GetBytes("HTTP/1.1 $status $reason`r`nContent-Type: $type`r`nContent-Length: $($body.Length)`r`nConnection: close`r`n`r`n")
    $stream.Write($head, 0, $head.Length)
    $stream.Write($body, 0, $body.Length)
}

function Send-Json($stream, [int]$status, $value) {
    Send-Response $stream $status ($Utf8.GetBytes(($value | ConvertTo-Json -Depth 5 -Compress)))
}

function Read-Request($stream) {
    $head = New-Object System.Collections.Generic.List[byte]
    $one = New-Object byte[] 1
    while ($true) {   # headers, up to the blank line
        $n = $stream.Read($one, 0, 1)
        if ($n -le 0) { return $null }
        $head.Add($one[0])
        $c = $head.Count
        if ($c -ge 4 -and $head[$c - 4] -eq 13 -and $head[$c - 3] -eq 10 -and $head[$c - 2] -eq 13 -and $head[$c - 1] -eq 10) { break }
        if ($c -gt 65536) { throw "headers too long" }
    }
    $lines = @($Utf8.GetString($head.ToArray()) -split "`r`n" | Where-Object { $_ })
    $method, $target = $lines[0].Split(" ")[0, 1]
    $headers = @{}
    foreach ($line in ($lines | Select-Object -Skip 1)) {
        $colon = $line.IndexOf(":")
        if ($colon -gt 0) { $headers[$line.Substring(0, $colon).Trim().ToLower()] = $line.Substring($colon + 1).Trim() }
    }
    $length = [int]($headers["content-length"])
    $body = New-Object byte[] $length
    $read = 0
    while ($read -lt $length) {
        $n = $stream.Read($body, $read, $length - $read)
        if ($n -le 0) { throw "connection closed mid-body" }
        $read += $n
    }
    $path, $query = $target.Split("?", 2)
    $params = @{}
    if ($query) {
        foreach ($pair in $query.Split("&")) {
            $key, $value = $pair.Split("=", 2)
            $params[[System.Uri]::UnescapeDataString($key)] = [System.Uri]::UnescapeDataString([string]$value)
        }
    }
    return @{ method = $method; path = $path; params = $params; headers = $headers; body = $body }
}

function Handle($request, $stream) {
    $p = $request.params
    switch ("$($request.method) $($request.path)") {
        "GET /status" {
            $game = Get-Game
            Send-Json $stream 200 @{
                agent = $AgentVersion; host = $env:COMPUTERNAME; install = $GameDir
                running = [bool]$game; pid = if ($game) { $game.Id } else { $null }
                bridge = Get-BridgeStatus
            }
        }
        "POST /bridge" {
            $timeout = if ($p["timeout"]) { [int]$p["timeout"] } else { 15000 }
            $op = if ($p["op"]) { $p["op"] } else { "lua" }
            Send-Json $stream 200 (Invoke-Bridge $op ($Utf8.GetString($request.body)) $timeout)
        }
        "POST /launch" {
            if (Get-Game) { Send-Json $stream 200 @{ ok = $false; note = "already running" }; return }
            Start-Process "steam://rungameid/2806050"
            Send-Json $stream 200 @{ ok = $true; note = "launched through Steam" }
        }
        "POST /quit" {
            $game = Get-Game
            if (-not $game) { Send-Json $stream 200 @{ ok = $true; note = "not running" }; return }
            if ($p["force"] -eq "1") { Stop-Process -Id $game.Id -Force } else { $game.CloseMainWindow() | Out-Null }
            Send-Json $stream 200 @{ ok = $true; note = "closing pid $($game.Id)" }
        }
        "GET /file" {
            $full = Resolve-RootPath $p["root"] $p["path"]
            if (-not (Test-Path $full -PathType Leaf)) { Send-Json $stream 404 @{ error = "no such file" }; return }
            # FileShare.ReadWrite: the game keeps its logs open for writing.
            $file = [System.IO.File]::Open($full, "Open", "Read", "ReadWrite")
            try {
                $bytes = New-Object byte[] $file.Length
                $read = 0
                while ($read -lt $bytes.Length) { $read += $file.Read($bytes, $read, $bytes.Length - $read) }
            } finally { $file.Close() }
            Send-Response $stream 200 $bytes "application/octet-stream"
        }
        "PUT /file" {
            $full = Resolve-RootPath $p["root"] $p["path"]
            Send-Json $stream 200 @{ ok = $true; note = (Write-RootFile $full $request.body); bytes = $request.body.Length }
        }
        "GET /list" {
            $full = Resolve-RootPath $p["root"] ([string]$p["path"])
            if (-not (Test-Path $full -PathType Container)) { Send-Json $stream 404 @{ error = "no such directory" }; return }
            $items = @(Get-ChildItem $full | Sort-Object LastWriteTime -Descending | ForEach-Object {
                @{ name = $_.Name; dir = $_.PSIsContainer; size = if ($_.PSIsContainer) { 0 } else { $_.Length }; modified = $_.LastWriteTime.ToString("s") }
            })
            Send-Json $stream 200 @{ items = $items }
        }
        "POST /install-bridge" { Send-Json $stream 200 @{ ok = $true; note = (Install-Bridge) } }
        "POST /input" {
            $script = Join-Path $PSScriptRoot "input.ps1"
            if (-not (Test-Path $script)) { Send-Json $stream 404 @{ error = "input.ps1 is not beside the agent (remote.mjs deploy-agent)" }; return }
            if (-not (Get-Game)) { Send-Json $stream 200 @{ ok = $false; error = "the game is not running" }; return }
            $out = & powershell -NoProfile -ExecutionPolicy Bypass -File $script -Steps ($Utf8.GetString($request.body)) 2>&1 | Out-String
            Send-Json $stream 200 @{ ok = ($LASTEXITCODE -eq 0); output = $out.Trim() }
        }
        "POST /restart-agent" {
            Send-Json $stream 200 @{ ok = $true; note = "restarting" }
            $stream.Flush()
            Start-Process powershell -ArgumentList @("-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"", "-Port", $Port)
            $script:Restart = $true
        }
        default { Send-Json $stream 404 @{ error = "unknown endpoint" } }
    }
}

# --- Serve -------------------------------------------------------------------

$addresses = @()
try {
    $addresses = @([System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName()) |
        Where-Object { $_.AddressFamily -eq "InterNetwork" -and -not $_.ToString().StartsWith("169.254.") } |
        ForEach-Object { $_.ToString() })
} catch { }
$listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Any, $Port)
for ($try = 0; ; $try++) {
    # A restarted agent starts while the old one is still answering.
    try { $listener.Start(); break } catch { if ($try -ge 20) { throw }; Start-Sleep -Milliseconds 500 }
}
$Restart = $false
Write-Host ""
Write-Host "MJOLNIR agent $AgentVersion on port $Port" -ForegroundColor Cyan
Write-Host "  game:    $GameDir"
Write-Host "  address: $($addresses -join ', ')"
Write-Host "  token:   $Token" -ForegroundColor Yellow
Write-Host "Give the address and token to the development PC. Close this window to stop." -ForegroundColor Cyan
Write-Host ""

while ($true) {
    $client = $listener.AcceptTcpClient()
    $remote = $client.Client.RemoteEndPoint
    $stream = $client.GetStream()
    $stream.ReadTimeout = 15000
    $line = "$((Get-Date).ToString('HH:mm:ss')) $($remote.Address)"
    try {
        if (-not (Test-Private $remote.Address)) {
            Send-Json $stream 403 @{ error = "private networks only" }
            $line += " refused (not a private address)"
        } else {
            $request = Read-Request $stream
            if (-not $request) { $line += " (empty)" }
            elseif ($request.headers["x-mjolnir-token"] -ne $Token) {
                Send-Json $stream 401 @{ error = "bad or missing token" }
                $line += " $($request.method) $($request.path) refused (token)"
            } else {
                $line += " $($request.method) $($request.path)"
                try { Handle $request $stream }
                catch { Send-Json $stream 500 @{ error = "$_" }; $line += " failed: $_" }
            }
        }
    } catch {
        $line += " dropped: $_"
    } finally {
        $client.Close()
    }
    Write-Host $line
    if ($Restart) { $listener.Stop(); Write-Host "restarting"; break }
}
