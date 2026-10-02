# Install an MJOLNIR test bundle (make_test_bundle.ps1) into this PC's Steam
# copy of Halo: Campaign Evolved. Run from the unzipped bundle folder with
# the game closed:
#
#   powershell -ExecutionPolicy Bypass -File .\install_test_bundle.ps1 [-Game "D:\SteamLibrary\steamapps\common\Halo Campaign Evolved"]
#
# Anything it would overwrite is copied to <game>\mjolnir-backup-<time> first,
# and -Uninstall puts the game back the way that backup and the bundle's file
# list describe.
param([string]$Game = "", [switch]$Uninstall)
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot

function Find-Game {
    $steam = (Get-ItemProperty "HKCU:\Software\Valve\Steam" -ErrorAction SilentlyContinue).SteamPath
    $roots = @()
    if ($steam) {
        $roots += $steam
        $vdf = Join-Path $steam "steamapps\libraryfolders.vdf"
        if (Test-Path $vdf) {
            foreach ($m in [regex]::Matches((Get-Content $vdf -Raw), '"path"\s+"([^"]+)"')) {
                $roots += $m.Groups[1].Value -replace '\\\\', '\'
            }
        }
    }
    $roots += "C:\Program Files (x86)\Steam"
    foreach ($r in $roots) {
        $p = Join-Path $r "steamapps\common\Halo Campaign Evolved"
        if (Test-Path (Join-Path $p "Meteorite\Binaries\Win64\HaloCampaignEvolved.exe")) { return $p }
    }
    return $null
}

if (-not $Game) { $Game = Find-Game }
if (-not $Game -or -not (Test-Path (Join-Path $Game "Meteorite\Binaries\Win64\HaloCampaignEvolved.exe"))) {
    throw "Halo: Campaign Evolved not found; pass -Game <install folder>"
}
$exe = (Resolve-Path (Join-Path $Game "Meteorite\Binaries\Win64\HaloCampaignEvolved.exe")).Path
if (Get-Process HaloCampaignEvolved -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exe }) {
    throw "Close the game first."
}
$win64 = Join-Path $Game "Meteorite\Binaries\Win64"
$paks = Join-Path $Game "Meteorite\Content\Paks"

# Every file the bundle installs, relative to its folder.
$files = Get-ChildItem -Recurse -File $here | Where-Object {
    $_.FullName.StartsWith((Join-Path $here "Win64")) -or $_.FullName.StartsWith((Join-Path $here "Paks"))
} | ForEach-Object { $_.FullName.Substring($here.Length + 1) }

function Target($rel) {
    if ($rel.StartsWith("Win64\")) { return Join-Path $win64 $rel.Substring(6) }
    return Join-Path $paks $rel.Substring(5)
}

if ($Uninstall) {
    $backup = Get-ChildItem $Game -Directory -Filter "mjolnir-backup-*" | Sort-Object Name | Select-Object -Last 1
    foreach ($rel in $files) {
        $t = Target $rel
        if (Test-Path $t) { Remove-Item -Force $t }
        if ($backup -and (Test-Path (Join-Path $backup.FullName $rel))) {
            Copy-Item (Join-Path $backup.FullName $rel) $t
        }
    }
    "uninstalled ($($files.Count) files)" + $(if ($backup) { "; restored from $($backup.Name)" } else { "" })
    return
}

$backup = Join-Path $Game ("mjolnir-backup-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
$saved = 0
foreach ($rel in $files) {
    $t = Target $rel
    if (Test-Path $t) {
        $b = Join-Path $backup $rel
        New-Item -ItemType Directory -Force (Split-Path $b) | Out-Null
        Copy-Item $t $b
        $saved++
    }
    New-Item -ItemType Directory -Force (Split-Path $t) | Out-Null
    Copy-Item -Force (Join-Path $here $rel) $t
}
"installed $($files.Count) files into $Game" + $(if ($saved) { "; $saved overwritten file(s) backed up in $backup" } else { "" })
