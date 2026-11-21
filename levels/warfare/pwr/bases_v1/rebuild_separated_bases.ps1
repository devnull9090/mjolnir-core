# Import, repair and cook the base meshes whose coplanar faces were separated
# (tools/level/separate_coplanar.py) in the isolated wide-gate project, ready for
# stage_interiors.splice (round.sh BASES_COOKED / BASES_MANIFEST).
#
#   powershell -File rebuild_separated_bases.ps1 -Art <dir with import.manifest.json, frames.manifest.json>
#
# import.manifest.json names every changed mesh; frames.manifest.json the architecture meshes,
# whose tangent frames the attributed builder leaves unusable (repair_pwr_base_frames.py).
param([Parameter(Mandatory = $true)][string]$Art)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\..')).Path
$art = (Resolve-Path $Art).Path
$project = Join-Path $root 'out\pwr\base-polish\gate6-native\Meteorite\Meteorite.uproject'
$editor = 'C:\Program Files\Epic Games\UE_5.5\Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
$scripts = Join-Path $root 'unreal\MJOLNIRMaterials\Scripts'
foreach ($step in @(@('import.manifest.json', 'build_pwr_bases.py', 'MJOLNIR PWR BASE BUILD COMPLETE'),
                    @('frames.manifest.json', 'repair_pwr_base_frames.py', 'PWR base frames repaired'))) {
    $env:MJ_PWR_BASE_MANIFEST = Join-Path $art $step[0]
    $log = Join-Path $art ($step[1] + '.log')
    & $editor $project '-run=pythonscript' "-script=$(Join-Path $scripts $step[1])" -unattended -nop4 -nosplash -stdout -FullStdOutLogOutput *> $log
    if (-not (Select-String -Path $log -Pattern $step[2] -Quiet)) { throw "$($step[1]) did not finish: $log" }
}
$cook = Join-Path $art 'cook.log'
& 'C:\Program Files\Epic Games\UE_5.5\Engine\Build\BatchFiles\RunUAT.bat' BuildCookRun "-project=$project" -noP4 -platform=Win64 `
    -clientconfig=Shipping -cook -stage -pak -iostore -skipbuild -nocompileeditor -unattended -utf8output -skipcookingeditorcontent *> $cook
if ($LASTEXITCODE) { throw "cook failed: $cook" }
"cooked: $(Join-Path (Split-Path $project) 'Saved\StagedBuilds\Windows\Meteorite\Content\Paks')"
