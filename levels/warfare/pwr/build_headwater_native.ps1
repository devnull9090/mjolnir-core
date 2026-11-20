param(
    [string]$EngineRoot = 'C:/Program Files/Epic Games/UE_5.5',
    [string]$Python = '',
    [string]$OutputPath = 'out/pwr/headwater-lake',
    [switch]$RiverApron,
    [switch]$RiverBasin,
    [ValidateSet('All','PrepareEditor','Editor','Physics','Package')]
    [string]$Step = 'All'
)
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
Push-Location -LiteralPath $workspace
try {
    $result = [IO.Path]::GetFullPath($OutputPath,$workspace)
    [IO.Directory]::CreateDirectory($result) | Out-Null
    $control = Join-Path $workspace 'out/pwr/sweep-polish/round31/editor/Meteorite'
    if ($RiverBasin) { $control=Join-Path $workspace 'out/pwr/river-apron/finish37/editor/Meteorite' }
    $projectDir = Join-Path $result 'editor/Meteorite'
    $project = Join-Path $projectDir 'Meteorite.uproject'
    $pakDir = Join-Path $workspace 'out/pwr/playtest-20261121/rehearsal-game/Meteorite/Content/Paks'
    $cli = Join-Path $workspace 'out/pwr/toolchain-grass-v7/r2/mjolnir.exe'
    $editor = Join-Path $EngineRoot 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'
    $editorScript = Join-Path $workspace 'unreal/MJOLNIRMaterials/Scripts/apply_pwr_headwater.py'
    if ($RiverApron) { $env:PWR_RIVER_APRON = '1' }
    if ($RiverBasin) { $env:PWR_RIVER_BASIN = '1' }
    $env:PWR_HEADWATER_ROOT = $workspace
    $env:PWR_HEADWATER_OUTPUT = $result

    if ($Step -ne 'PrepareEditor') {
        foreach ($inputFile in 'terrain/runtime-master.r16','dressing/decor-moves.json') {
            if (!(Test-Path -LiteralPath (Join-Path $result $inputFile))) {
                throw "Build the headwater terrain and shoreline dressing before the native cook. Missing $inputFile"
            }
        }
    }
    if (!$Python) {
        $Python = Join-Path $result 'python/Scripts/python.exe'
        if (!(Test-Path -LiteralPath $Python)) {
            & uv venv --python 3.12 (Join-Path $result 'python')
            if ($LASTEXITCODE) {throw 'Could not create headwater Python runtime'}
        }
        & uv pip install --python $Python numpy scipy matplotlib triangle
        if ($LASTEXITCODE) {throw 'Could not prepare collision authoring packages'}
    }

    if ($RiverApron -and $Step -in 'All','Editor','Physics') {
        $survey = Join-Path $result 'bank/survey.json'
        $ready = Test-Path -LiteralPath $survey
        if ($ready) {
            $proof = Get-Content -Raw -LiteralPath $survey | ConvertFrom-Json
            $ready = $proof.terrain_sha256 -eq (Get-FileHash (Join-Path $result 'terrain/runtime-master.r16')).Hash -and
                     $proof.rock_ledger_sha256 -eq (Get-FileHash (Join-Path $result 'dressing/decor-moves.json')).Hash
        }
        if (!$ready) {
            & $Python levels/warfare/pwr/plan_outlet_bank.py
            if ($LASTEXITCODE) {throw 'Native bank surface and support survey failed'}
        }
    }

    if ($Step -in 'All','PrepareEditor','Editor') {
        if (!(Test-Path -LiteralPath $project)) {
            & robocopy $control $projectDir /E /XD Saved Intermediate DerivedDataCache .vs .git /NFL /NDL /NJH /NJS /NP
            if ($LASTEXITCODE -ge 8) {throw 'Could not isolate the sealed .31 editor project'}
        }
        $sourceModule = Join-Path $workspace 'unreal/MJOLNIRMaterials/Plugins/MjolnirUIBuilder/Source/MjolnirUIBuilder'
        $module = Join-Path $projectDir 'Plugins/MjolnirUIBuilder/Source/MjolnirUIBuilder'
        # Import only the new reflected heightfield function into the release's matching plugin version.
        Copy-Item -LiteralPath (Join-Path $sourceModule 'Private/MjolnirLandscapeHeights.cpp') -Destination (Join-Path $module 'Private/MjolnirLandscapeHeights.cpp')
        $headerPath = Join-Path $module 'Public/MjolnirUIBuilderLibrary.h'
        $header = [IO.File]::ReadAllText($headerPath)
        if (!$header.Contains('PatchLandscapeHeights(')) {
            $declaration = [regex]::Match([IO.File]::ReadAllText((Join-Path $sourceModule 'Public/MjolnirUIBuilderLibrary.h')), '(?m)^[ \t]+UFUNCTION\(BlueprintCallable, Category = "MJOLNIR\|Landscape"\)\r?\n[ \t]+static bool PatchLandscapeHeights\([^;]+;')
            if (!$declaration.Success -or !$header.Contains('public:')) {throw 'Editor module signature is unrecognised'}
            [IO.File]::WriteAllText($headerPath,$header.Replace('public:',"public:`n"+$declaration.Value))
        }
        $buildPath = Join-Path $module 'MjolnirUIBuilder.Build.cs'
        $dependency = [IO.File]::ReadAllText($buildPath)
        if (!$dependency.Contains('"Foliage"')) {
            [IO.File]::WriteAllText($buildPath,$dependency.Replace('PCHUsage =','PrivateDependencyModuleNames.Add("Foliage"); PCHUsage ='))
        }
        & (Join-Path $EngineRoot 'Engine/Build/BatchFiles/Build.bat') UnrealEditor Win64 Development "-Project=$project" -NoHotReloadFromIDE -DisableUnity -DisablePlugin=MjolnirForkLayouts *> (Join-Path $result 'editor-build.log')
        if ($LASTEXITCODE) {throw 'Editor plugin build failed'}
        if ($Step -eq 'PrepareEditor') { return }

        function Invoke-EditorStep([string]$inputProject,[string]$step) {
            & $editor $inputProject '-run=pythonscript' "-script=$editorScript" -AllowCommandletRendering -DisablePlugins=MjolnirForkLayouts -unattended -nop4 -nosplash -stdout -FullStdOutLogOutput *> (Join-Path $result "$step.log")
            if ($LASTEXITCODE) {throw "Native editor pass failed in $step"}
        }
        $env:PWR_HEADWATER_INVENTORY = '1'
        $env:PWR_HEADWATER_VERIFY = $null
        if (!(Test-Path -LiteralPath (Join-Path $result 'native-scene-inventory.json'))) {
            Invoke-EditorStep $project 'editor-source-inventory'
        }
        $env:PWR_HEADWATER_INVENTORY = $null
        & $Python levels/warfare/pwr/plan_headwater_instances.py
        if ($LASTEXITCODE) {throw 'Foliage projection failed'}
        if (!(Test-Path -LiteralPath (Join-Path $result 'editor-dressing.json'))) {
            Invoke-EditorStep $project 'editor-dressing'
        }
        $env:PWR_HEADWATER_VERIFY = '1'
        if ((!$RiverApron -or !(Test-Path -LiteralPath (Join-Path $result 'bank/material.json'))) -and
            (!$RiverBasin -or !(Test-Path -LiteralPath (Join-Path $result 'basin-plant-counts.json')))) {
            Invoke-EditorStep $project 'editor-final-verify'
        }
        if ($RiverBasin) {
            & $Python levels/warfare/pwr/plan_basin_shoulder.py
            if ($LASTEXITCODE) {throw 'Basin shoulder plan failed'}
            $editorScript = Join-Path $workspace 'unreal/MJOLNIRMaterials/Scripts/apply_pwr_basin_shoulder.py'
            $env:PWR_HEADWATER_VERIFY=$null
            if (!(Test-Path (Join-Path $result 'basin-plant-counts.json'))) {Invoke-EditorStep $project 'basin-strand-apply'}
            $env:PWR_HEADWATER_VERIFY='1'
            Invoke-EditorStep $project 'basin-strand-verify'
        }
        if ($RiverApron) {
            $baseProof = Join-Path $result 'editor-verified.json'
            if (!(Test-Path -LiteralPath $baseProof)) { throw 'Landscape readback is missing' }
            $parentArt = Join-Path $workspace 'out/pwr/river-erosion/shore-finish/editor/Meteorite/Content/MJOLNIR/GrassPilot/Playable'
            $targetArt = Join-Path $projectDir 'Content/MJOLNIR/GrassPilot/Playable'
            foreach ($name in 'T_PWR_RiverCobble_BC.uasset','T_PWR_RiverCobble_N.uasset') {
                Copy-Item -LiteralPath (Join-Path $parentArt $name) -Destination (Join-Path $targetArt $name)
            }
            $editorScript = Join-Path $workspace 'unreal/MJOLNIRMaterials/Scripts/apply_pwr_riverbank_finish.py'
            $env:PWR_HEADWATER_VERIFY = $null
            if (!(Test-Path -LiteralPath (Join-Path $result 'bank/placements.json'))) {
                Invoke-EditorStep $project 'outlet-bank-art'
            }
            $env:PWR_HEADWATER_VERIFY = '1'
            Invoke-EditorStep $project 'outlet-bank-reopen'
        }
        & (Join-Path $EngineRoot 'Engine/Build/BatchFiles/RunUAT.bat') BuildCookRun "-project=$project" -noP4 -platform=Win64 -clientconfig=Shipping -cook -stage -pak -iostore -skipbuild -nocompileeditor -unattended -utf8output -skipcookingeditorcontent '-map=/Game/Levels/Halo1/Solo/LPE/LPE' *> (Join-Path $result 'cook.log')
        if ($LASTEXITCODE) {throw 'Windows shipping cook failed'}
        & $Python levels/warfare/pwr/package_pwr_headwater.py --prepare
        if ($LASTEXITCODE) {throw 'Terrain shader packaging failed'}
    }
    if ($Step -in 'All','Physics') {
        & $Python levels/warfare/pwr/cook_headwater_collision.py
        if ($LASTEXITCODE) {throw 'Native physical source build failed'}
        if ($RiverBasin) {
            & $Python levels/warfare/pwr/verify_basin_joins.py
            if ($LASTEXITCODE) {throw 'Revised native collision failed to meet the inherited perimeter'}
        }
        $physics = Join-Path $result 'native/physics'
        & $cli level collision (Join-Path $physics 'collision_scene.json') --paks $pakDir --own-bsp --bsp-index 0 --receipt (Join-Path $physics 'native-collision-receipt.json') --out (Join-Path $physics 'pwr.sbsp') *> (Join-Path $physics 'native-final.log')
        if ($LASTEXITCODE) {throw 'Native BSP cook failed'}
        & $Python levels/warfare/pwr/verify_headwater_collision.py
        if ($LASTEXITCODE) {throw 'Native physical face readback failed'}
    }
    if ($Step -in 'All','Package') {
        & $Python levels/warfare/pwr/package_pwr_headwater.py
        if ($LASTEXITCODE) {throw 'Playable-world packaging failed'}
    }
} finally {
    $env:PWR_HEADWATER_VERIFY = $null
    $env:PWR_HEADWATER_INVENTORY = $null
    $env:PWR_HEADWATER_OUTPUT = $null
    $env:PWR_RIVER_APRON = $null
    $env:PWR_RIVER_BASIN = $null
    Pop-Location
}
