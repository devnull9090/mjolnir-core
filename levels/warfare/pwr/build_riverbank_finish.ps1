param(
    [string]$EngineRoot = 'C:/Program Files/Epic Games/UE_5.5',
    [string]$Python = ''
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
Push-Location -LiteralPath $root
try {
    $source = Join-Path $root 'out/pwr/river-erosion'
    $out = Join-Path $source 'shore-finish'
    $projectDir = Join-Path $out 'editor/Meteorite'
    $project = Join-Path $projectDir 'Meteorite.uproject'
    if (!$Python) { $Python = Join-Path $root 'out/pwr/headwater-lake/python/Scripts/python.exe' }
    $script = Join-Path $root 'unreal/MJOLNIRMaterials/Scripts/apply_pwr_riverbank_finish.py'
    $env:PWR_HEADWATER_ROOT = $root
    if (!(Test-Path -LiteralPath (Join-Path $out 'scans/ganges-river-cobble.json'))) {
        throw 'Prepare the Ganges River Pebbles scan and its local checksum manifest before cooking.'
    }
    & $Python (Join-Path $PSScriptRoot 'plan_riverbank_finish.py')
    if ($LASTEXITCODE) { throw 'Shoreline planting plan failed' }
    if (!(Test-Path -LiteralPath $project)) {
        robocopy (Join-Path $source 'editor/Meteorite') $projectDir /E /XD Saved Intermediate DerivedDataCache .vs .git /NFL /NDL /NJH /NJS /NP *> (Join-Path $out 'editor-copy.log')
        if ($LASTEXITCODE -ge 8) { throw 'Could not copy the .34 authoring scene' }
    }
    foreach ($phase in 'apply','verify') {
        $env:PWR_HEADWATER_VERIFY = $null
        if ($phase -eq 'verify') { $env:PWR_HEADWATER_VERIFY = '1' }
        if ($phase -eq 'apply' -and (Test-Path -LiteralPath (Join-Path $out 'placements.json'))) { continue }
        & (Join-Path $EngineRoot 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe') $project '-run=pythonscript' "-script=$script" -AllowCommandletRendering -DisablePlugins=MjolnirForkLayouts -unattended -nop4 -nosplash -stdout -FullStdOutLogOutput *> (Join-Path $out "editor-$phase.log")
        if ($LASTEXITCODE) { throw "Editor $phase failed" }
    }
    & (Join-Path $EngineRoot 'Engine/Build/BatchFiles/RunUAT.bat') BuildCookRun "-project=$project" -noP4 -platform=Win64 -clientconfig=Shipping -cook -stage -pak -iostore -skipbuild -nocompileeditor -unattended -utf8output -skipcookingeditorcontent '-map=/Game/Levels/Halo1/Solo/LPE/LPE' *> (Join-Path $out 'cook.log')
    if ($LASTEXITCODE) { throw 'Unable to cook Windows terrain' }
    & $Python (Join-Path $PSScriptRoot 'package_riverbank_finish.py')
    if ($LASTEXITCODE) { throw 'Native package validation failed' }
} finally {
    $env:PWR_HEADWATER_VERIFY = $null
    Pop-Location
}
