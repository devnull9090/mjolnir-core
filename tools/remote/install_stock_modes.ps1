# Install (or undo) the stock game types test build on this PC. Run it on BOTH
# PCs, with the game closed, from a kit folder that holds Win64\ and Paks\:
#
#   powershell -ExecutionPolicy Bypass -File install_stock_modes.ps1
#   powershell -ExecutionPolicy Bypass -File install_stock_modes.ps1 -Restore
#   powershell -ExecutionPolicy Bypass -File install_stock_modes.ps1 -Check
#
# Install backs up every file it replaces into backup\ beside this script (once;
# a second install keeps the first backup), then copies the kit's Win64 and Paks
# folders over the game's, and adds King, Oddball and Race to Blood Gulch and
# Prisoner in this PC's own MJOLNIRMaps\maps.json. Restore puts it all back.
# Check prints hashes: both PCs must print the same lines.
param(
    [string]$Game = "C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved",
    [switch]$Restore,
    [switch]$Check
)
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$win64 = Join-Path $Game "Meteorite\Binaries\Win64"
$dest = @{ "Win64" = $win64; "Paks" = Join-Path $Game "Meteorite\Content\Paks" }
$backup = Join-Path $here "backup"
$list = Join-Path $win64 "ue4ss\MJOLNIRMaps\maps.json"
$savedList = Join-Path $backup "maps.json"
foreach ($d in $dest.Values) { if (-not (Test-Path $d)) { throw "Not found: $d (pass -Game <install folder>)" } }

if ($Check) {
    $mods = Join-Path $win64 "ue4ss\Mods"
    $names = @(
        "MJOLNIRLevelLoader\native\mjolnir_map_registry.dll",
        "MJOLNIRLobby\native\mjolnir_lobby.dll",
        "MJOLNIRLevelLoader\variants\team_koth.mglo",
        "MJOLNIRLevelLoader\variants\stalker.mglo",
        "MJOLNIRHud\Scripts\hill.lua"
    )
    foreach ($n in $names) {
        $p = Join-Path $mods $n
        if (Test-Path $p) { "{0}  {1}" -f (Get-FileHash $p -Algorithm SHA256).Hash.Substring(0, 12), $n }
        else { "MISSING       $n" }
    }
    return
}

if (Get-Process -Name HaloCampaignEvolved -ErrorAction SilentlyContinue) { throw "Close the game first." }

# A hub map's chunk number differs between PCs (Prisoner is 914 on one, 915 on
# the other), so its containers go in under the name this PC already has: a
# second name would mount the map twice.
function Installed-Name([string]$name) {
    if ($name -notmatch '^pakchunk\d+(-MJOLNIRHUB-.+)$') { return $name }
    $found = @(Get-ChildItem -File (Join-Path $dest["Paks"] ("pakchunk*" + $Matches[1])))
    if ($found.Count -ne 1) { throw "$name is not installed here once ($($found.Count) found). Install the map from the hub first." }
    return $found[0].Name
}

$files = foreach ($top in "Win64", "Paks") {
    Get-ChildItem -Recurse -File (Join-Path $here $top) | ForEach-Object {
        $rel = $_.FullName.Substring((Join-Path $here $top).Length + 1)
        if ($top -eq "Paks") { $rel = Installed-Name $rel }
        [pscustomobject]@{ Rel = $rel; Top = $top; Src = $_.FullName }
    }
}

if ($Restore) {
    if (-not (Test-Path $backup)) { throw "No backup\ folder: nothing to restore." }
    foreach ($f in $files) {
        $target = Join-Path $dest[$f.Top] $f.Rel
        $saved = Join-Path $backup (Join-Path $f.Top $f.Rel)
        if (Test-Path $saved) { Copy-Item -Force $saved $target; "restored  $($f.Top)\$($f.Rel)" }
        elseif (Test-Path $target) { Remove-Item -Force $target; "removed   $($f.Top)\$($f.Rel) (not there before)" }
    }
    if (Test-Path $savedList) { Copy-Item -Force $savedList $list; "restored  maps.json" }
    $choice = Join-Path $win64 "ue4ss\Mods\MJOLNIRLevelLoader\match_variant.txt"
    if (Test-Path $choice) { Remove-Item -Force $choice }
    return
}

$fresh = -not (Test-Path $backup)
if ($fresh) {
    foreach ($f in $files) {
        $target = Join-Path $dest[$f.Top] $f.Rel
        if (Test-Path $target) {
            $saved = Join-Path $backup (Join-Path $f.Top $f.Rel)
            New-Item -ItemType Directory -Force (Split-Path $saved) | Out-Null
            Copy-Item $target $saved
        }
    }
    Copy-Item $list $savedList
    "backed up the originals to $backup"
} else { "kept the existing backup in $backup" }

foreach ($f in $files) {
    $target = Join-Path $dest[$f.Top] $f.Rel
    New-Item -ItemType Directory -Force (Split-Path $target) | Out-Null
    Copy-Item -Force $f.Src $target
}
"installed $($files.Count) files"

# This PC's own list, so its other maps stay as they are. Plain text edits: the
# loader reads the file, so it keeps its shape and gains no byte order mark.
$text = [IO.File]::ReadAllText($list)
$engines = '"modes": ["slayer", "ctf", "koth", "oddball", "race"]'
$options = [Text.RegularExpressions.RegexOptions]::Singleline
foreach ($code in "BGL", "PRS") {
    $pattern = '("code"\s*:\s*"' + $code + '"(?:(?!"code").)*?)"modes"\s*:\s*\[[^\]]*\]'
    if (-not [regex]::IsMatch($text, $pattern, $options)) { throw "$code has no modes in maps.json" }
    $text = [regex]::Replace($text, $pattern, { param($m) $m.Groups[1].Value + $engines }, $options)
}
[IO.File]::WriteAllText($list, $text, (New-Object Text.UTF8Encoding($false)))
"maps.json: Blood Gulch and Prisoner now list King, Oddball and Race"
"Done. Start the game from Steam, not the MJOLNIR launcher, and choose Not Now if it offers to fix mods."
