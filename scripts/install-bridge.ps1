<#
.SYNOPSIS
    Install the MJOLNIR bridge mod into the game so tools can drive it.

.DESCRIPTION
    Copies mods\MJOLNIRBridge into the game's UE4SS Mods folder, enables it in
    mods.txt, and creates the directory the bridge talks through. Nothing that
    ships with the game is modified; removing the mod folder and its mods.txt
    line undoes all of it.

    Safe to re-run: it overwrites the mod and leaves mods.txt alone if the entry
    is already there. Run it again after editing the Lua -- UE4SS reads mods
    from disk at startup, so a copy plus a restart is the whole edit loop.

.PARAMETER GameDir
    Install root, the folder containing Meteorite\. Found automatically for a
    default Steam install.

.EXAMPLE
    .\install-bridge.ps1
#>
param(
    [string]$GameDir,
    [string[]]$Mods = @("MJOLNIRBridge")
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path "$PSScriptRoot\.."

if (-not $GameDir) {
    $candidates = @(
        "C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved",
        "C:\Program Files\Steam\steamapps\common\Halo Campaign Evolved"
    )
    # Other Steam libraries, from the index Steam keeps for itself.
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

if (-not $GameDir -or -not (Test-Path (Join-Path $GameDir "Meteorite\Binaries\Win64\HaloCampaignEvolved.exe"))) {
    Write-Error "Halo Campaign Evolved not found. Pass -GameDir <install root>."
    exit 1
}

$Ue4ss = Join-Path $GameDir "Meteorite\Binaries\Win64\ue4ss"
if (-not (Test-Path $Ue4ss)) {
    Write-Error "UE4SS is not installed at $Ue4ss. Install the modpack first."
    exit 1
}

$ModsDir = Join-Path $Ue4ss "Mods"
$ModsTxt = Join-Path $ModsDir "mods.txt"

Write-Host "Game:  $GameDir"
Write-Host "UE4SS: $Ue4ss"
Write-Host ""

foreach ($mod in $Mods) {
    $source = Join-Path $RepoRoot "mods\$mod"
    if (-not (Test-Path $source)) {
        Write-Warning "no such mod in the repository: $source"
        continue
    }
    $destination = Join-Path $ModsDir $mod
    if (Test-Path $destination) { Remove-Item $destination -Recurse -Force }
    Copy-Item $source $destination -Recurse
    Write-Host "  copied $mod" -ForegroundColor Green

    $lines = if (Test-Path $ModsTxt) { @(Get-Content $ModsTxt) } else { @() }
    if ($lines | Where-Object { $_ -match "^\s*$([regex]::Escape($mod))\s*:" }) {
        Write-Host "  already enabled in mods.txt" -ForegroundColor DarkGray
    }
    else {
        # Keybinds is documented in mods.txt as having to stay last, so add
        # above the comment that introduces it rather than at the end.
        $anchor = ($lines | Select-String -Pattern "Built-in keybinds" | Select-Object -First 1)
        if ($anchor) {
            $index = $anchor.LineNumber - 1
            $lines = $lines[0..($index - 1)] + "$mod : 1" + $lines[$index..($lines.Count - 1)]
        }
        else {
            $lines += "$mod : 1"
        }
        # No BOM: UE4SS reads mods.txt line by line, and a BOM would ride along
        # on the first mod name and stop that mod from loading.
        [System.IO.File]::WriteAllLines($ModsTxt, $lines, (New-Object System.Text.UTF8Encoding($false)))
        Write-Host "  enabled in mods.txt" -ForegroundColor Green
    }
}

$BridgeDir = Join-Path $Ue4ss "mjolnir-bridge"
New-Item -ItemType Directory -Path $BridgeDir -Force | Out-Null
Write-Host "  bridge directory: $BridgeDir" -ForegroundColor Green

Write-Host ""
Write-Host "Done. Restart the game for UE4SS to pick this up." -ForegroundColor Cyan
