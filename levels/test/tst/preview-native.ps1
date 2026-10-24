#Requires -Version 7.0
<# Fast Blender design loop. Reads locally installed game assets; no HEK bake or game launch. #>
[CmdletBinding()]
param(
    [string]$BlenderExe = 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe',
    [string]$PythonExe = 'python',
    [string]$Conversion = 'C:\haloce\ce_conversions\community\TST',
    [string]$Paks = 'C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved\Meteorite\Content\Paks',
    [string]$Cyborg = 'C:\haloce\ce_conversions\yoyorast_relit\YOY\staging\models\characters_cyborg_mp_cyborg_mp__bipd.gltf',
    [string]$Out = '.dream-loop/blender-preview/native-current',
    [string[]]$Views = @('exterior','wall','balcony','topdown','side','red-interior','blue-interior','pcg','layout'),
    [int]$Samples = 64,
    [switch]$RebuildGeometry
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$repo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
Push-Location $repo
try {
    $null=New-Item -ItemType Directory -Force -Path $Out
    function Run-Stage([string]$Name,[string]$Executable,[string[]]$Arguments) {
        Write-Host "TST preview: $Name"
        & $Executable @Arguments *> (Join-Path $Out "$Name.log")
        if ($LASTEXITCODE -ne 0) { throw "$Name failed; see $Out/$Name.log" }
    }
    $base=@('--background','--factory-startup','--python-exit-code','1','--python')
    if ($RebuildGeometry) { Run-Stage 'geometry' $BlenderExe ($base+@('levels/test/tst/build_geometry.py','--','--no-export')) }
    Run-Stage 'layout' $BlenderExe ($base+@('levels/test/tst/inspect_layout.py','--','--out',"$Out/layout-check.json"))
    Run-Stage 'annotate' $BlenderExe ($base+@('levels/test/tst/annotate_blend.py'))
    Run-Stage 'scatter-source' $BlenderExe ($base+@('tools/blender/export_scatter_source.py','--','--blend','levels/test/tst/tst.blend','--spec',"$Conversion/materials.spec.json",'--out','.dream-loop/pcg-preview'))
    Run-Stage 'native' $PythonExe @('tools/blender/prepare_native_preview.py','--placements','levels/test/tst/placements.json','--scene',$Conversion,'--staging',"$Conversion/staging",'--cli','target/release/mjolnir.exe','--paks',$Paks,'--cache','.dream-loop/game-assets','--out','.dream-loop/native-preview','--authored-decor','levels/test/tst/perimeter_dressing.json')
    Run-Stage 'native-clearance' $BlenderExe ($base+@('tools/blender/inspect_native_decor.py','--','--native','.dream-loop/native-preview/native-preview.json','--layout',"$Out/layout-check.json",'--out',"$Out/native-clearance.json"))
    Run-Stage 'scatter' $PythonExe @('tools/level/scatter_foliage.py','.dream-loop/pcg-preview/scene.gltf','.dream-loop/pcg-preview/materials.spec.json','.dream-loop/pcg-preview/foliage.json','--bin','.dream-loop/pcg-preview/foliage.bin','--only','grass,short grass,weeds','--rule-scale','grass=0.42','--rule-density','grass=4.0','--rule-cluster','grass=12,0.10,0.60','--sea','-250','--surface-policy','levels/test/tst/tst.surfaces.json','--staging','.dream-loop/native-preview/placement-input','--cliff-shaders','levels_test_tst_shaders_tst_cliffs')
    Run-Stage 'pcg-assets' $PythonExe @('tools/blender/prepare_pcg_preview.py','--foliage','.dream-loop/pcg-preview/foliage.json','--cli','target/release/mjolnir.exe','--paks',$Paks,'--cache','.dream-loop/game-assets')
    $render=$base+@('levels/test/tst/render_preview.py','--','--staging',"$Conversion/staging",'--native-assets','.dream-loop/native-preview/native-preview.json','--pcg-assets','.dream-loop/pcg-preview/pcg-preview.json','--alloy-albedo','levels/test/tst/art/textures/forerunner_titanium_albedo.png','--floor-albedo','levels/test/tst/art/textures/forerunner_floor_albedo.png','--cliff-albedo','levels/test/tst/art/textures/coastal_granite_lichen_albedo.png','--out',$Out,'--samples',"$Samples",'--width','1672','--height','941')
    if ($Cyborg) { $render+=@('--cyborg',$Cyborg) }
    $render+=@('--views')+$Views
    Run-Stage 'render' $BlenderExe $render
    Run-Stage 'architecture-check' $BlenderExe ($base+@('levels/test/tst/inspect_architecture.py','--','--blend',"$Out/preview.blend",'--out',"$Out/architecture-check.json"))
    Write-Host "TST preview ready: $Out/preview.blend"
} finally { Pop-Location }
