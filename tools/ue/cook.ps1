# Cook and package the Meteorite project (unreal/MJOLNIRMaterials) into IoStore
# containers at below-normal priority, on every core unless a mask limits it
# (-Mask or MJ_CPU_MASK, hex: every process UAT starts - the editor, shader
# compile workers, UnrealPak - inherits the affinity). The build box has cut
# power under all-core load; a mask such as 0x0F is the way to keep a cook
# light while that is being investigated.
#
#   powershell -File tools/ue/cook.ps1 [-Mask 0x0F] [-Map /Game/Levels/X/X] [-TaggedProperties] [-Classes A,B]
#                                      [-NeverCook /Game/A+/Game/B]
#
# -Map also cooks that world (only /Game/MJOLNIR is cooked by default);
# -TaggedProperties cooks properties tagged rather than unversioned (the
# landscape spike's contrast case, see unreal/MJOLNIRMapKit/README.md);
# -Classes the classes the retarget below re-encodes (default materials;
# add StaticMesh when the cook carries meshes of ours, the cliffs' Nanite
# meshes in chunk 983).
#
# After a cook (unversioned) every staged chunk container that holds
# materials is rewritten with them re-encoded in the game's property layout
# (`mjolnir ue retarget --rewrite`; MJOLNIR names the CLI, else this
# checkout's target/release or target/debug build). Copy containers out of
# staging only after this script returns.
#
# The project enables CommonUI (MJOLNIR's menu screens derive from
# CommonActivatableWidget), which makes UAT treat it as a code project: the
# editor target (our plugins and a receipt) is compiled before the cook, so
# there is no -nocompileeditor.
param([int64]$Mask = 0, [string]$Map = "", [switch]$TaggedProperties, [string]$Classes = "Material,MaterialInstanceConstant",
      [string]$NeverCook = "")
# Nested uv/PowerShell sessions can inherit another edition's PSModulePath.
# Load the host's utilities explicitly before a cook needs hashes/JSON.
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1') -ErrorAction Stop
# MJ_CPU_MASK (hex) limits a whole batch, e.g. 0x0F for four cores; 0 or unset is every core.
if ($env:MJ_CPU_MASK) { $Mask = [Convert]::ToInt64($env:MJ_CPU_MASK, 16) }
$project = Join-Path $PSScriptRoot "..\..\unreal\MJOLNIRMaterials" | Resolve-Path
$log = Join-Path $project "Saved_cook.log"
$uat = "C:\Program Files\Epic Games\UE_5.5\Engine\Build\BatchFiles\RunUAT.bat"
$extra = ""
if ($Map) { $extra += " -map=$Map" }
# -NeverCook: /Game folders (a+b) this cook leaves out as DirectoriesToNeverCook
# would: the stand-ins of a Halo 1 map's own textures (tools/level/clad_materials.py).
$cooker = @()
if ($TaggedProperties) { $cooker += "-ini:Engine:[Core.System]:CanUseUnversionedPropertySerialization=False" }
if ($NeverCook) { $cooker += "-NEVERCOOKDIR=$NeverCook" }
if ($cooker.Count) { $extra += " `"-AdditionalCookerOptions=$($cooker -join ' ')`"" }
$args = "/c `"`"$uat`" BuildCookRun -project=`"$project\Meteorite.uproject`" -noP4 -platform=Win64 -clientconfig=Shipping -cook -stage -pak -iostore -skipbuild -unattended -utf8output -skipcookingeditorcontent$extra > `"$log`" 2>&1`""
# One Unreal process on the project at a time: conversions may run side by
# side (their staging, collision, lightmaps and bakes are their own), but the
# editor imports and the cook share unreal/MJOLNIRMaterials and its staging
# folder, so every editor commandlet and cook waits for this named mutex.
$lock = New-Object System.Threading.Mutex($false, "MjolnirMeteoriteProject")
try { [void]$lock.WaitOne() } catch [System.Threading.AbandonedMutexException] { }
try {
    $p = Start-Process -FilePath cmd.exe -ArgumentList $args -PassThru -WindowStyle Hidden -ErrorAction Stop
    if ($Mask -ne 0) { $p.ProcessorAffinity = [IntPtr]$Mask }
    $p.PriorityClass = [System.Diagnostics.ProcessPriorityClass]::BelowNormal
    $p.WaitForExit()
    "cook exit $($p.ExitCode)"
    Select-String -Path $log -Pattern "fork layouts:|Shader compiler errors|BUILD SUCCESSFUL|BUILD FAILED" | ForEach-Object { $_.Line.Substring(0, [Math]::Min(200, $_.Line.Length)) }
    if ($p.ExitCode -ne 0) { throw "Cook failed ($($p.ExitCode)); see $log" }
    # The stock editor writes property blocks in stock 5.5's layout and 343's
    # engine reads them in its own, so every cooked material was misread from
    # the first shifted slot on (bUsedWithNanite arrived as bUsesDistortion:
    # Nanite cladding drew through its fallback mesh, 2026-10-12). Rewrite
    # each staged chunk container with its materials re-encoded in the game's
    # layout, shader library and all, before anything copies it out.
    if ($p.ExitCode -eq 0 -and -not $TaggedProperties) {
        $repo = Join-Path $PSScriptRoot "..\.." | Resolve-Path
        if ($env:MJOLNIR_RETARGET_SNAPSHOT) {
            # Preserve an actual stock-layout input before any in-place rewrite.
            $snapshotRoot = [IO.Path]::GetFullPath($env:MJOLNIR_RETARGET_SNAPSHOT)
            if (Test-Path -LiteralPath $snapshotRoot) { throw "Retarget snapshot already exists: $snapshotRoot" }
            $snapshotChunks = @($env:MJOLNIR_RETARGET_SNAPSHOT_CHUNKS -split ',' | Sort-Object -Unique)
            if (-not $snapshotChunks.Count -or @($snapshotChunks | Where-Object { $_ -notmatch '^[1-9][0-9]*$' }).Count) {
                throw 'Retarget snapshot requires explicit numeric chunk IDs'
            }
            New-Item -ItemType Directory -Path $snapshotRoot -ErrorAction Stop | Out-Null
            $snapshotStaged = Join-Path $project 'Saved\StagedBuilds\Windows\Meteorite\Content\Paks'
            $snapshotFiles = @()
            foreach ($snapshotStem in (@('global') + @($snapshotChunks | ForEach-Object { 'pakchunk'+$_+'-Windows' }))) {
                foreach ($snapshotExt in @('utoc','ucas')) {
                    $snapshotName = $snapshotStem+'.'+$snapshotExt
                    $snapshotSource = Join-Path $snapshotStaged $snapshotName
                    $snapshotTarget = Join-Path $snapshotRoot $snapshotName
                    Copy-Item -LiteralPath $snapshotSource -Destination $snapshotTarget -ErrorAction Stop
                    $sourceHash = (Get-FileHash -LiteralPath $snapshotSource -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
                    if ((Get-FileHash -LiteralPath $snapshotTarget -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant() -ne $sourceHash) {
                        throw 'Retarget snapshot copy differs from stock source'
                    }
                    $snapshotFiles += [pscustomobject]@{name=$snapshotName;sha256=$sourceHash;bytes=(Get-Item -LiteralPath $snapshotTarget).Length}
                }
            }
            [pscustomobject]@{schema='mjolnir-stock-retarget-snapshot-v1';before_any_retarget=$true;files=$snapshotFiles} |
                ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $snapshotRoot 'receipt.json') -Encoding UTF8 -ErrorAction Stop
        }
        # An isolated retarget build can add fork-layout support without changing
        # the pinned conversion/collision CLI used by the rest of the pipeline.
        $mjolnir = $env:MJOLNIR_RETARGET
        if (-not $mjolnir) { $mjolnir = $env:MJOLNIR }
        if (-not $mjolnir) {
            $mjolnir = @("target\release\mjolnir.exe", "target\debug\mjolnir.exe") | ForEach-Object { Join-Path $repo $_ } |
                Where-Object { Test-Path $_ } | Select-Object -First 1
        }
        if (-not $mjolnir) {
            throw 'No mjolnir.exe (set MJOLNIR or build blam-cli); refusing assets without game property encoding'
        } else {
            $staged = Join-Path $project "Saved\StagedBuilds\Windows\Meteorite\Content\Paks"
            Get-ChildItem $staged -Filter "pakchunk*-Windows.utoc" | Where-Object { $_.BaseName -ne "pakchunk0-Windows" } | ForEach-Object {
                # The rewrite stores every chunk uncompressed (a container
                # grows 1.1x to 1.7x): sizes printed, the hub caps archives.
                $ucas = Join-Path $staged ($_.BaseName + ".ucas")
                $before = (Get-Item $ucas).Length
                $out = & $mjolnir ue retarget --paks $staged --container $_.BaseName --classes $Classes `
                    --rewrite --out-dir $staged --name $_.BaseName 2>&1
                if ($LASTEXITCODE -ne 0) { throw "Retarget of $($_.BaseName) failed; refusing misencoded cooked assets: $($out | Select-Object -Last 3)" }
                $after = (Get-Item $ucas).Length
                "retarget $($_.BaseName): $($out | Select-Object -Last 1) [ucas $([math]::Round($before / 1MB, 1)) -> $([math]::Round($after / 1MB, 1)) MB]"
            }
        }
    }
    'MJOLNIR cook and retarget complete'
} finally { $lock.ReleaseMutex() }
