# Builds the template test world headlessly (no editor UI).
#
#   .\generate_world.ps1 [-EnginePath "C:\Program Files\Epic Games\UE_5.5"]
#
# Requires UE 5.5.x. The cooked package format is engine-version locked;
# 5.6+ output will not load in the game.

param(
    [string]$EnginePath = "C:\Program Files\Epic Games\UE_5.5"
)

$ErrorActionPreference = "Stop"

$kit = Split-Path -Parent $PSScriptRoot
$project = Join-Path $kit "Meteorite.uproject"
$script = Join-Path $kit "Content\Python\mjolnir_build_world.py"
$editor = Join-Path $EnginePath "Engine\Binaries\Win64\UnrealEditor-Cmd.exe"

if (-not (Test-Path $editor)) {
    throw "UnrealEditor-Cmd.exe not found under '$EnginePath'. Install UE 5.5.x from the Epic Games Launcher, or pass -EnginePath."
}

& $editor $project -run=pythonscript -script="$script" -stdout -unattended -nosplash
if ($LASTEXITCODE -ne 0) {
    throw "world generation failed with exit code $LASTEXITCODE"
}

$umap = Join-Path $kit "Content\Levels\Test\Testing_Shooting_Range\testing_shooting_range.umap"
if (-not (Test-Path $umap)) {
    throw "editor exited cleanly but $umap was not created"
}
Write-Host "World generated: $umap"
