# Cooks the test world, stages it as an IoStore container, and (optionally)
# installs it into the game as an override container.
#
#   .\package.ps1                       # cook + stage + collect artifacts
#   .\package.ps1 -Install              # ... and copy them into the game's Paks
#
# Output artifacts (in <kit>\Artifacts):
#   pakchunk990-MJOLNIRWORLD-Windows_P.utoc
#   pakchunk990-MJOLNIRWORLD-Windows_P.ucas
#   pakchunk990-MJOLNIRWORLD-Windows_P.pak    (stub copied from the game)
#
# Why a stub .pak: the game only discovers a .utoc/.ucas pair when a same-named
# .pak sits beside it, and several shipped containers use exactly this
# stub-pak pattern (verified; see docs/iostore_packaging.md). Our own staged
# .pak is NOT installed because the project is named Meteorite: its staged
# config paths overlap the game's and a _P pak could shadow the game's real
# config files.
#
# Removal: delete the three pakchunk990-MJOLNIRWORLD-* files from the game's
# Paks directory. Nothing shipped is modified.

param(
    [string]$EnginePath = "C:\Program Files\Epic Games\UE_5.5",
    [string]$GamePath = "C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved",
    [switch]$Install
)

$ErrorActionPreference = "Stop"

$kit = Split-Path -Parent $PSScriptRoot
$project = Join-Path $kit "Meteorite.uproject"
$uat = Join-Path $EnginePath "Engine\Build\BatchFiles\RunUAT.bat"
$artifacts = Join-Path $kit "Artifacts"
$containerName = "pakchunk990-MJOLNIRWORLD-Windows_P"

if (-not (Test-Path $uat)) {
    throw "RunUAT.bat not found under '$EnginePath'. Install UE 5.5.x from the Epic Games Launcher, or pass -EnginePath."
}
$umap = Join-Path $kit "Content\Levels\Test\Testing_Shooting_Range\testing_shooting_range.umap"
if (-not (Test-Path $umap)) {
    throw "no world to cook — run generate_world.ps1 first (or author the level in the editor)."
}

# --- cook + stage ------------------------------------------------------------
& $uat BuildCookRun `
    -project="$project" `
    -platform=Win64 `
    -clientconfig=Shipping `
    -cook -map="/Game/Levels/Test/Testing_Shooting_Range/testing_shooting_range" `
    -stage -pak -iostore -compressed `
    -skipbuild -nodebuginfo -unattended -noP4
if ($LASTEXITCODE -ne 0) {
    throw "BuildCookRun failed with exit code $LASTEXITCODE"
}

$staged = Join-Path $kit "Saved\StagedBuilds\Windows\Meteorite\Content\Paks"
$srcUtoc = Join-Path $staged "pakchunk0-Windows.utoc"
$srcUcas = Join-Path $staged "pakchunk0-Windows.ucas"
if (-not (Test-Path $srcUtoc) -or -not (Test-Path $srcUcas)) {
    throw "staging finished but $staged has no pakchunk0-Windows container"
}

# --- collect artifacts -------------------------------------------------------
New-Item -ItemType Directory -Force $artifacts | Out-Null
Copy-Item $srcUtoc (Join-Path $artifacts "$containerName.utoc") -Force
Copy-Item $srcUcas (Join-Path $artifacts "$containerName.ucas") -Force

$stubSource = Join-Path $GamePath "Meteorite\Content\Paks\pakchunk115-Windows.pak"
if (Test-Path $stubSource) {
    Copy-Item $stubSource (Join-Path $artifacts "$containerName.pak") -Force
} else {
    Write-Warning "stub source $stubSource not found; find any small shipped .pak and copy it to $containerName.pak yourself"
}

Get-ChildItem $artifacts -Filter "$containerName.*" | ForEach-Object {
    Write-Host ("  {0,-46} {1,10:N0} bytes" -f $_.Name, $_.Length)
}

# --- install -----------------------------------------------------------------
if ($Install) {
    $paks = Join-Path $GamePath "Meteorite\Content\Paks"
    if (-not (Test-Path $paks)) { throw "game Paks directory not found: $paks" }
    foreach ($ext in "utoc", "ucas", "pak") {
        Copy-Item (Join-Path $artifacts "$containerName.$ext") $paks -Force
    }
    Write-Host "Installed to $paks. Launch the game and run: mjolnir_mission testing_shooting_range"
    Write-Host "(The game must not be running during install — it holds mounted .ucas files open.)"
}
