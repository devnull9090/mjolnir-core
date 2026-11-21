param([string]$Engine='C:/Program Files/Epic Games/UE_5.5',[ValidateSet('All','Apply','Verify','Cook','Physics','Package')][string]$Step='All',[ValidateRange(41,9999)][int]$Version=43)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$out=Join-Path $root 'out/pwr/river-riparian'
$projectDir=Join-Path $out 'editor/Meteorite'
$project=Join-Path $projectDir 'Meteorite.uproject'
$editor=Join-Path $Engine 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'
$env:PWR_HEADWATER_ROOT=$root
$env:PWR_SHORE_VERSION="$Version"
$python=Join-Path $root 'out/pwr/headwater-lake/python/Scripts/python.exe'
if ($Step -in 'All','Apply') {
    $surveys=@{
        'cutbank/surface.json'='plan_cutbank_roots.py'
        'cascade/surface.json'='terrain/plan_spring_cascade.py'
        'planting/planting.json'='plan_riparian_canopy.py'
    }
    foreach ($data in $surveys.Keys) {
        if (!(Test-Path -LiteralPath (Join-Path $out $data))) {
            & $python (Join-Path $PSScriptRoot $surveys[$data])
            if ($LASTEXITCODE) {throw "Failed to generate $data"}
        }
    }
}
if (!(Test-Path -LiteralPath $project)) {
    & robocopy (Join-Path $root 'out/pwr/river-basin/shore-contact/native/editor/Meteorite') $projectDir /E /XD Saved Intermediate DerivedDataCache .vs .git /NFL /NDL /NJH /NJS /NP
    if ($LASTEXITCODE -ge 8) {throw 'Could not copy the .39 editor project'}
}
try {
    foreach ($phase in 'Apply','Verify') {
        if ($Step -notin 'All',$phase) {continue}
        $env:PWR_HEADWATER_VERIFY=if ($phase -eq 'Verify') {'1'} else {'0'}
        $script=Join-Path $root 'unreal/MJOLNIRMaterials/Scripts/apply_pwr_riparian_shore.py'
        & $editor $project '-run=pythonscript' "-script=$script" -AllowCommandletRendering -DisablePlugins=MjolnirForkLayouts -unattended -nop4 -nosplash -stdout -FullStdOutLogOutput *> (Join-Path $out "editor-$phase.log")
        if ($LASTEXITCODE) {throw "Lake $phase failed"}
    }
    if ($Step -in 'All','Cook') {
        & (Join-Path $Engine 'Engine/Build/BatchFiles/RunUAT.bat') BuildCookRun "-project=$project" -noP4 -platform=Win64 -clientconfig=Shipping -cook -stage -pak -iostore -skipbuild -nocompileeditor -unattended -utf8output -skipcookingeditorcontent '-map=/Game/Levels/Halo1/Solo/LPE/LPE' *> (Join-Path $out 'cook.log')
        if ($LASTEXITCODE) {throw 'Windows shipping cook failed'}
    }
    if ($Step -in 'All','Physics') {
        $proof=Join-Path $out 'native/physics/native-readback.json'
        $scene=Join-Path $out 'native/physics/collision_scene.json'
        $support=(Get-FileHash -LiteralPath (Join-Path $out 'cutbank/support.npz')).Hash
        $reuse=(Test-Path $proof) -and (Test-Path $scene) -and ((Get-Content $scene -Raw | ConvertFrom-Json).riparian_cutbank.support_sha256 -eq $support)
        if (!$reuse) {
            & $python (Join-Path $PSScriptRoot 'cook_riparian_toe.py')
            if ($LASTEXITCODE) {throw 'Native bank collision failed'}
        }
    }
    if ($Step -in 'All','Package') {
        & $python (Join-Path $PSScriptRoot 'package_riparian_shore.py') --version $Version
        if ($LASTEXITCODE) {throw 'Lake release verification failed'}
    }
} finally {
    $env:PWR_HEADWATER_VERIFY=$null
}
