param([string]$Engine='C:/Program Files/Epic Games/UE_5.5',[string]$Step='All')
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
Push-Location -LiteralPath $root
try {
    $env:PWR_HEADWATER_ROOT=$root
    $src=Join-Path $root 'out/pwr/river-apron'
    $out=Join-Path $src 'finish37'
    $projectDir=Join-Path $out 'editor/Meteorite'
    $project=Join-Path $projectDir 'Meteorite.uproject'
    $editor=Join-Path $Engine 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'
    $script=Join-Path $root 'unreal/MJOLNIRMaterials/Scripts/apply_pwr_outlet_finish.py'
    $python=Join-Path $root 'out/pwr/headwater-lake/python/Scripts/python.exe'
    New-Item -Path $out -ItemType Directory -Force | Out-Null
    if (!(Test-Path (Join-Path $out 'survey.json'))) {
        & $python levels/warfare/pwr/finish_outlet_alluvium.py
        if ($LASTEXITCODE) {throw 'Survey failed'}
    }
    Copy-Item -LiteralPath (Join-Path $src 'bank/support.npz') -Destination (Join-Path $out 'support.npz')
    if (!(Test-Path -LiteralPath $project)) {
        & robocopy (Join-Path $src 'editor/Meteorite') $projectDir /E /XD Saved Intermediate DerivedDataCache .vs .git /NFL /NDL /NJH /NJS /NP
        if ($LASTEXITCODE -ge 8) {throw 'Could not copy native .36 source'}
    }
    if ($Step -eq 'All') {
        foreach ($phase in 'apply','verify') {
            if ($phase -eq 'apply' -and (Test-Path (Join-Path $out 'vegetation-applied.json'))) {continue}
            $env:PWR_HEADWATER_VERIFY=if ($phase -eq 'verify') {'1'} else {'0'}
            & $editor $project '-run=pythonscript' "-script=$script" -AllowCommandletRendering -DisablePlugins=MjolnirForkLayouts -unattended -nop4 -nosplash -stdout -FullStdOutLogOutput *> (Join-Path $out "editor-$phase.log")
            if ($LASTEXITCODE) { throw "Editor $phase failed" }
        }
        & (Join-Path $Engine 'Engine/Build/BatchFiles/RunUAT.bat') BuildCookRun "-project=$project" -noP4 -platform=Win64 -clientconfig=Shipping -cook -stage -pak -iostore -skipbuild -nocompileeditor -unattended -utf8output -skipcookingeditorcontent '-map=/Game/Levels/Halo1/Solo/LPE/LPE' *> (Join-Path $out 'cook.log')
        if ($LASTEXITCODE) {throw 'Windows shipping cook failed'}
    }
    & $python levels/warfare/pwr/package_outlet_finish.py
    if ($LASTEXITCODE) {throw 'Playable package check failed'}
} finally {
    $env:PWR_HEADWATER_VERIFY=$null
    Pop-Location
}
