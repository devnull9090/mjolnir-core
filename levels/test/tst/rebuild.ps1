#Requires -Version 7.0
<#
.SYNOPSIS
Rebuild TST's classic Halo CE map from its checked-in authoring scripts.
.DESCRIPTION
Requires Blender 5.1, the externally installed Halo Toolset Release 425,
Python and the classic HEK. Downloads nothing. Logs remain in .dream-loop.
The source scenario is saved beside this script; BSP, bitmap and map outputs
remain in the HEK. Do not edit authoring scripts while this command runs.
.EXAMPLE
pwsh -File levels/test/tst/rebuild.ps1
.EXAMPLE
pwsh -File levels/test/tst/rebuild.ps1 -SkipGeometry
.EXAMPLE
pwsh -File levels/test/tst/rebuild.ps1 -SplitFacilityDetail -FacilityOutputDir C:/work/tst-split-build -HekRoot C:/work/tst-fresh-hek
#>
[CmdletBinding()]
param(
    [string]$HekRoot = 'C:\haloce\hek',
    [string]$BlenderExe = 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe',
    [string]$PythonExe = 'python',
    [string]$AddonRoot = 'C:\haloce\tools\halo-blender-425\addons\io_scene_halo',
    [string]$MccTagsRoot = 'C:\Program Files (x86)\Steam\steamapps\common\HCEEK\tags',
    [switch]$SkipGeometry,
    [switch]$SplitFacilityDetail,
    [string]$FacilityOutputDir = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$SourceRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$RepoRoot = [IO.Path]::GetFullPath((Join-Path $SourceRoot '..\..\..'))
$HekRoot = (Resolve-Path -LiteralPath $HekRoot).Path
$AddonRoot = (Resolve-Path -LiteralPath $AddonRoot).Path
$ToolExe = Join-Path $HekRoot 'tool.exe'
$TagsRoot = Join-Path $HekRoot 'tags'
$MapsRoot = [IO.Path]::GetFullPath((Join-Path $HekRoot 'maps'))
$ScenarioTag = 'levels\test\tst\tst'
$ScenarioFile = Join-Path $TagsRoot "$ScenarioTag.scenario"
$BspFile = Join-Path $TagsRoot "$ScenarioTag.scenario_structure_bsp"
$LightmapFile = Join-Path $TagsRoot "$ScenarioTag.bitmap"
$MapFile = Join-Path $MapsRoot 'tst.map'
$SourceJms = Join-Path $SourceRoot 'data\levels\test\tst\models\tst.JMS'
$WaterSource = Join-Path $TagsRoot 'levels\b30\shaders\water.shader_transparent_water'
$WaterTarget = Join-Path $TagsRoot 'levels\test\tst\shaders\tst_water.shader_transparent_water'
$CliffSource = Join-Path $TagsRoot 'levels\b30\shaders\cliffs.shader_environment'
$CliffTarget = Join-Path $TagsRoot 'levels\test\tst\shaders\tst_cliffs.shader_environment'
$AmberSource = Join-Path $SourceRoot 'tags\levels\test\tst\shaders\tst_lights_amber.shader_environment'
$AmberTarget = Join-Path $TagsRoot 'levels\test\tst\shaders\tst_lights_amber.shader_environment'
$StockInputs = @(
    'levels\b30\shaders\beach.shader_environment',
    'levels\b30\shaders\cliffs.shader_environment',
    'levels\b30\bitmaps\beach.bitmap'
)
$BitmapMap = [IO.Path]::GetFullPath((Join-Path $MapsRoot 'bitmaps.map'))
$BitmapBackup = [IO.Path]::GetFullPath((Join-Path $MapsRoot 'bitmaps.map.tst-build-backup'))
$BitmapCreated = [IO.Path]::GetFullPath((Join-Path $MapsRoot 'bitmaps.map.tst-build-created'))
$LogRoot = Join-Path $RepoRoot '.dream-loop\tst-rebuild'
$RunLogs = Join-Path $LogRoot ([DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fff'))

# The partitioned workflow is opt-in and writes all authored outputs to a
# new bundle. A dedicated HEK with no prior TST outputs prevents overwriting
# an existing project or publishing a stale receipt after a partial failure.
if ($SplitFacilityDetail) {
    if ($SkipGeometry) { throw '-SplitFacilityDetail requires a fresh full geometry export; omit -SkipGeometry.' }
    if (-not $FacilityOutputDir) { throw '-FacilityOutputDir must name a new output directory.' }
    $BundleCandidate = [IO.Path]::GetFullPath($FacilityOutputDir)
    if (Test-Path -LiteralPath $BundleCandidate) { throw "Facility output already exists: $BundleCandidate" }
    $BundleParent = (Resolve-Path -LiteralPath (Split-Path -Parent $BundleCandidate)).Path
    $Bundle = [IO.Path]::GetFullPath((Join-Path $BundleParent (Split-Path -Leaf $BundleCandidate)))
    foreach ($Root in @($HekRoot,$TagsRoot,$MapsRoot,$BundleParent)) {
        $item = Get-Item -LiteralPath $Root -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Split-build root is a link: $Root" }
    }
    $Ancestor = $BundleParent
    while ($Ancestor) {
        if ((Get-Item -LiteralPath $Ancestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "Facility output parent has a linked ancestor: $Ancestor"
        }
        $Next = Split-Path -Parent $Ancestor
        if (-not $Next -or $Next -eq $Ancestor) { break }
        $Ancestor = $Next
    }
    if ($Bundle.StartsWith($HekRoot+'\',[StringComparison]::OrdinalIgnoreCase) -or
        $Bundle.StartsWith($SourceRoot+'\',[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Facility output must be outside the HEK and map source directories.'
    }
    $HekModels = Join-Path $HekRoot 'data\levels\test\tst\models'
    $HekInputJms = Join-Path $HekModels 'tst.JMS'
    $SourceSurfaceLibrary = Join-Path $SourceRoot 'surfaces.json'
    $Partitioner = Join-Path $RepoRoot 'tools\level\partition_tst_facility.py'
    $ReceiptMaker = Join-Path $RepoRoot 'tools\level\make_tst_facility_receipt.py'
    $ReceiptVerifier = Join-Path $RepoRoot 'tools\level\verify_tst_facility_receipt.py'
    foreach ($RequiredSplit in @($SourceSurfaceLibrary,$Partitioner,$ReceiptMaker,$ReceiptVerifier,(Join-Path $SourceRoot 'bundle_textures.py'))) {
        if (-not (Test-Path -LiteralPath $RequiredSplit -PathType Leaf)) { throw "Missing split-build input: $RequiredSplit" }
    }
    $SplitSurfaces = Get-Content -LiteralPath $SourceSurfaceLibrary -Raw | ConvertFrom-Json
    $OriginalLibraryHash = (Get-FileHash -LiteralPath $SourceSurfaceLibrary -Algorithm SHA256).Hash
    $ReservedSplit = @($HekInputJms,$WaterTarget,$CliffTarget,$AmberTarget,$BspFile,$ScenarioFile,$LightmapFile,$MapFile)
    foreach ($Property in $SplitSurfaces.surfaces.PSObject.Properties) {
        $ReservedSplit += Join-Path $TagsRoot ($Property.Value.tag + '.shader_environment')
    }
    foreach ($Reserved in $ReservedSplit) {
        $FullReserved = [IO.Path]::GetFullPath($Reserved)
        if (-not $FullReserved.StartsWith($HekRoot+'\',[StringComparison]::OrdinalIgnoreCase)) {
            throw "Split-build output escapes the dedicated HEK: $FullReserved"
        }
        $Ancestor = Split-Path -Parent $FullReserved
        while ($Ancestor.Length -ge $HekRoot.Length) {
            if (Test-Path -LiteralPath $Ancestor) {
                if ((Get-Item -LiteralPath $Ancestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                    throw "Split-build output has a linked ancestor: $Ancestor"
                }
            }
            if ([string]::Equals($Ancestor,$HekRoot,[StringComparison]::OrdinalIgnoreCase)) { break }
            $Ancestor = Split-Path -Parent $Ancestor
        }
        if (Test-Path -LiteralPath $Reserved) { throw "Split build requires an unused TST HEK destination: $Reserved" }
    }
    $AuthoringOut = Join-Path $Bundle 'authoring'
    $SurfaceLibrary = Join-Path $AuthoringOut 'surfaces.json'
    $SourceJms = Join-Path $AuthoringOut 'data\levels\test\tst\models\tst.JMS'
    $PlacementInput = Join-Path $AuthoringOut 'placements.json'
    $PartitionOut = Join-Path $Bundle 'partition'
    $CeJms = Join-Path $PartitionOut 'tst-ce-structure.JMS'
    $DetailGltf = Join-Path $PartitionOut 'tst-facility-detail.gltf'
} elseif ($FacilityOutputDir) {
    throw '-FacilityOutputDir requires -SplitFacilityDetail.'
} else {
    $PlacementInput = Join-Path $SourceRoot 'placements.json'
}

foreach ($Required in @($ToolExe, $WaterSource,
        (Join-Path $AddonRoot 'file_tag\tag_interface\tag_interface.py'),
        (Join-Path $SourceRoot 'build_scenario.py'),
        (Join-Path $SourceRoot 'amber_light.py'),
        (Join-Path $SourceRoot 'amber_light.json'),
        (Join-Path $TagsRoot 'levels\test\bloodgulch\shaders\mp lights small strips.shader_environment'),
        (Join-Path $SourceRoot 'annotate_blend.py'),
        (Join-Path $SourceRoot 'terrain_form.py'),
        (Join-Path $SourceRoot 'perimeter_architecture.py'),
        (Join-Path $SourceRoot 'perimeter_dressing.py'),
        (Join-Path $MapsRoot 'sounds.map'), (Join-Path $MapsRoot 'loc.map'), $BitmapMap)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) {
        throw "Required rebuild input is missing: $Required"
    }
}
# These installed MCC tags retain their original references. Only missing
# classic HEK files are staged; existing vendor assets are never overwritten.
foreach ($Relative in $StockInputs) {
    $StockSource = Join-Path $MccTagsRoot $Relative
    $StockTarget = Join-Path $TagsRoot $Relative
    if (-not (Test-Path -LiteralPath $StockSource -PathType Leaf)) {
        throw "Required installed MCC tag is missing: $StockSource"
    }
    if ((Test-Path -LiteralPath $StockTarget) -and
        (Get-FileHash -LiteralPath $StockSource).Hash -ne (Get-FileHash -LiteralPath $StockTarget).Hash) {
        throw "Existing HEK tag differs from the installed MCC source; refusing to overwrite: $StockTarget"
    }
}
$PythonCommand = Get-Command $PythonExe -CommandType Application -ErrorAction Stop | Select-Object -First 1
$PythonExe = $PythonCommand.Source
if (-not $SkipGeometry -and -not (Test-Path -LiteralPath $BlenderExe -PathType Leaf)) {
    throw "Blender executable is missing: $BlenderExe"
}

# Every map move below is confined to these explicit, checked sibling paths.
foreach ($Candidate in @($BitmapMap, $BitmapBackup, $BitmapCreated)) {
    if (-not [string]::Equals([IO.Path]::GetDirectoryName($Candidate), $MapsRoot,
            [StringComparison]::OrdinalIgnoreCase)) {
        throw "Bitmap-map path escapes the intended HEK maps directory: $Candidate"
    }
}
foreach ($Reserved in @($BitmapBackup, $BitmapCreated)) {
    if (Test-Path -LiteralPath $Reserved) {
        throw "Refusing an ambiguous previous bitmap-map backup. Inspect and restore it first: $Reserved"
    }
}

$Busy = @(Get-Process -Name tool, tool_x2, tool_x4, sapien, guerilla -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and [string]::Equals([IO.Path]::GetDirectoryName($_.Path),
        $HekRoot, [StringComparison]::OrdinalIgnoreCase) })
if ($Busy.Count) {
    throw "Close the HEK processes before rebuilding: $($Busy.ProcessName -join ', ')"
}
New-Item -ItemType Directory -Path $RunLogs -Force | Out-Null
# File sharing provides an exclusive lock without deleting any lock file.
$BuildLock = [IO.File]::Open((Join-Path $LogRoot 'tst-rebuild.lock'),
    [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)

function Invoke-RebuildStage {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Executable,
        [Parameter(Mandatory)][string[]]$Arguments,
        [string]$WorkingDirectory = $SourceRoot,
        [string]$ExpectedFile,
        [switch]$HekStage
    )
    $BeforeWrite = if ($ExpectedFile -and (Test-Path -LiteralPath $ExpectedFile)) {
        (Get-Item -LiteralPath $ExpectedFile).LastWriteTimeUtc
    } else { [DateTime]::MinValue }
    $DebugFile = Join-Path $HekRoot 'debug.txt'
    $DebugBefore = if ($HekStage -and (Test-Path -LiteralPath $DebugFile)) {
        [IO.File]::ReadAllText($DebugFile)
    } else { '' }
    $ProcessInfo = [Diagnostics.ProcessStartInfo]::new()
    $ProcessInfo.FileName = $Executable
    $ProcessInfo.WorkingDirectory = $WorkingDirectory
    $ProcessInfo.UseShellExecute = $false
    $ProcessInfo.CreateNoWindow = $true
    $ProcessInfo.RedirectStandardOutput = $true
    $ProcessInfo.RedirectStandardError = $true
    foreach ($Argument in $Arguments) { $ProcessInfo.ArgumentList.Add($Argument) }
    $Process = [Diagnostics.Process]::new()
    $Process.StartInfo = $ProcessInfo
    Write-Host "TST: $Name"
    try {
        if (-not $Process.Start()) { throw "Could not start $Name" }
        # Drain both pipes concurrently so verbose native tools cannot deadlock.
        $StdoutTask = $Process.StandardOutput.ReadToEndAsync()
        $StderrTask = $Process.StandardError.ReadToEndAsync()
        $Process.WaitForExit()
        $Stdout = $StdoutTask.GetAwaiter().GetResult()
        $Stderr = $StderrTask.GetAwaiter().GetResult()
        $ExitCode = $Process.ExitCode
    } finally {
        $Process.Dispose()
    }
    $LogFile = Join-Path $RunLogs "$Name.log"
    $Content = "$Stdout`n$Stderr"
    if ($HekStage -and (Test-Path -LiteralPath $DebugFile)) {
        $DebugAfter = [IO.File]::ReadAllText($DebugFile)
        $DebugDelta = if ($DebugAfter.StartsWith($DebugBefore, [StringComparison]::Ordinal)) {
            $DebugAfter.Substring($DebugBefore.Length)
        } else { $DebugAfter }
        $Content += "`nHEK debug.txt additions:`n$DebugDelta"
    }
    [IO.File]::WriteAllText($LogFile, $Content)
    if ($ExitCode -ne 0) { throw "$Name exited with $ExitCode. See $LogFile" }

    # Classic tool.exe can report fatal geometry/tag errors while returning 0.
    # Its missing toolbeta.map diagnostic is an expected retail-HEK warning.
    $OptionalGeometryWarnings = @(
        'PIL not found. Unable to create image node.',
        'lxml not found. Unable to generate bitmaps for Halo 3 era imports.'
    )
    $EmbeddedBitmapCache = $Name -eq 'cache' -and $Content -match 'successfully built cache file\.'
    $FailureLines = @($Content -split '\r?\n' | Where-Object {
        $OptionalGeometryWarning = $Name -eq 'geometry' -and $_.Trim() -cin $OptionalGeometryWarnings
        -not ($EmbeddedBitmapCache -and $_ -match '^(Failed to read data file header bitmaps|### FAILED TO OPEN DATA-CACHE FILE\.)$') -and
        -not $OptionalGeometryWarning -and
        $_ -notmatch '(?i)couldn.t read map file.*toolbeta\.map' -and
        ($_ -cmatch '\bERROR\b' -or
         $_ -match "(?i)(###\s*ERROR\b|\bERROR:|\bEXCEPTION\b|\bassertion failed\b|\bFATAL\b|\bfailed to\b|\bcould(?:n't| not) (?:open|read|write|load|build)|\bunable to\b|\bBUILD FAILED\b|\bTraceback \(most recent call last\))")
    })
    if ($FailureLines.Count) {
        throw "$Name reported an error despite exit code 0: $($FailureLines[0]). See $LogFile"
    }
    if ($SplitFacilityDetail) {
        if ($Content -match '(?i)\bEXCEPTION(?:\b|_)') { throw "$Name reported an exception; see $LogFile" }
        if ($Name -eq 'structure' -and ($Content -notmatch '(?i)structure bsp' -or
                $Content -notmatch '(?i)clusters' -or $Content -notmatch '(?i)without debug information' -or
                $Content -match "(?i)couldn.t allocate subcluster")) {
            throw "Structure did not report a complete BSP; see $LogFile"
        }
        if ($Name -eq 'lightmaps' -and ($Content -notmatch '(?i)finished\s+levels[\\/]+test[\\/]+tst[\\/]+tst\b' -or
                $Content -notmatch '(?i)\bdone\b')) { throw "Lightmaps did not report completion; see $LogFile" }
        if ($Name -eq 'cache' -and -not $EmbeddedBitmapCache) { throw "Cache did not report success; see $LogFile" }
    }
    if ($ExpectedFile) {
        if (-not (Test-Path -LiteralPath $ExpectedFile -PathType Leaf)) {
            throw "$Name did not produce $ExpectedFile. See $LogFile"
        }
        $Produced = Get-Item -LiteralPath $ExpectedFile
        if ($Produced.Length -eq 0 -or $Produced.LastWriteTimeUtc -le $BeforeWrite) {
            throw "$Name did not refresh its output: $ExpectedFile. See $LogFile"
        }
    }
    Write-Host "TST: $Name passed ($LogFile)"
}

try {
    if ($SplitFacilityDetail) {
        # Creating a new bundle, without -Force, preserves any earlier work.
        New-Item -ItemType Directory -Path $Bundle -ErrorAction Stop | Out-Null
    }
    foreach ($Relative in $StockInputs) {
        $StockSource = Join-Path $MccTagsRoot $Relative
        $StockTarget = Join-Path $TagsRoot $Relative
        if (-not (Test-Path -LiteralPath $StockTarget)) {
            if ($SplitFacilityDetail) {
                $Ancestor = Split-Path -Parent $StockTarget
                while ($Ancestor.Length -ge $HekRoot.Length) {
                    if ((Test-Path -LiteralPath $Ancestor) -and
                        ((Get-Item -LiteralPath $Ancestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                        throw "Stock tag destination has a linked ancestor: $Ancestor"
                    }
                    if ([string]::Equals($Ancestor,$HekRoot,[StringComparison]::OrdinalIgnoreCase)) { break }
                    $Ancestor = Split-Path -Parent $Ancestor
                }
            }
            New-Item -ItemType Directory -Path (Split-Path -Parent $StockTarget) -Force | Out-Null
            if ($SplitFacilityDetail) { [IO.File]::Copy($StockSource,$StockTarget,$false) }
            else { Copy-Item -LiteralPath $StockSource -Destination $StockTarget }
        }
    }
    if (-not $SkipGeometry) {
        $PreviousAddons = $env:HALO_BLENDER_ADDONS
        try {
            $env:HALO_BLENDER_ADDONS = Split-Path -Parent $AddonRoot
            $GeometryArguments = @(
                '--background', '--factory-startup', '--python-exit-code', '1',
                '--python', (Join-Path $SourceRoot 'build_geometry.py'))
            if ($SplitFacilityDetail) { $GeometryArguments += @('--','--out-dir',$AuthoringOut,'--bundle-textures') }
            Invoke-RebuildStage -Name 'geometry' -Executable $BlenderExe -Arguments $GeometryArguments -ExpectedFile $SourceJms
            if ($SplitFacilityDetail) {
                if ((Get-FileHash -LiteralPath $SourceSurfaceLibrary -Algorithm SHA256).Hash -ne $OriginalLibraryHash) {
                    throw 'Source surface library changed during geometry export.'
                }
                [IO.File]::Copy($SourceSurfaceLibrary,$SurfaceLibrary,$false)
                if ((Get-FileHash -LiteralPath $SurfaceLibrary -Algorithm SHA256).Hash -ne $OriginalLibraryHash) {
                    throw 'Bundled surface library does not match the source.'
                }
                $TextureHashes = [ordered]@{}
                foreach ($Property in $SplitSurfaces.surfaces.PSObject.Properties) {
                    foreach ($Key in @('albedo','roughness_map','normal_map')) {
                        $TextureProperty = $Property.Value.PSObject.Properties[$Key]
                        if (-not $TextureProperty) { continue }
                        $RelativeTexture = [string]$TextureProperty.Value
                        if ([IO.Path]::IsPathRooted($RelativeTexture)) { throw "Bundled texture path is absolute: $RelativeTexture" }
                        $Texture = [IO.Path]::GetFullPath((Join-Path $AuthoringOut $RelativeTexture))
                        if (-not $Texture.StartsWith($AuthoringOut+'\',[StringComparison]::OrdinalIgnoreCase) -or
                            -not (Test-Path -LiteralPath $Texture -PathType Leaf) -or
                            ((Get-Item -LiteralPath $Texture -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                            throw "Bundled texture is missing or outside the bundle: $RelativeTexture"
                        }
                        $TextureHashes[$RelativeTexture] = (Get-FileHash -LiteralPath $Texture -Algorithm SHA256).Hash.ToLowerInvariant()
                    }
                }
            }
            # Annotation runs only after the clean JMS export. It adds
            # inspection empties/camera and a source README to the .blend;
            # placement JSON and the exported game geometry stay unchanged.
            $AnnotateArguments = @(
                '--background', '--factory-startup', '--python-exit-code', '1',
                '--python', (Join-Path $SourceRoot 'annotate_blend.py'))
            $AnnotatedBlend = Join-Path $SourceRoot 'tst.blend'
            if ($SplitFacilityDetail) {
                $AnnotatedBlend = Join-Path $AuthoringOut 'tst.blend'
                $AnnotateArguments += @('--','--blend',$AnnotatedBlend,'--placements',$PlacementInput)
            }
            Invoke-RebuildStage -Name 'annotate' -Executable $BlenderExe -Arguments $AnnotateArguments `
                -ExpectedFile $AnnotatedBlend
        } finally {
            $env:HALO_BLENDER_ADDONS = $PreviousAddons
        }
    }
    foreach ($Required in @($SourceJms, $PlacementInput)) {
        if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) {
            throw "Authoring input is missing: $Required"
        }
    }
    $HekModels = Join-Path $HekRoot 'data\levels\test\tst\models'
    New-Item -ItemType Directory -Path $HekModels, (Split-Path -Parent $WaterTarget) -Force | Out-Null
    if ($SplitFacilityDetail) {
        Invoke-RebuildStage -Name 'facility-partition' -Executable $PythonExe -Arguments @(
            '-B',$Partitioner,'--source',$SourceJms,'--surfaces',$SurfaceLibrary,'--out-dir',$PartitionOut) `
            -ExpectedFile (Join-Path $PartitionOut 'manifest.json')
        if (Test-Path -LiteralPath $HekInputJms) { throw "HEK JMS destination appeared during build: $HekInputJms" }
        Copy-Item -LiteralPath $CeJms -Destination $HekInputJms
        if ((Get-FileHash -LiteralPath $CeJms).Hash -ne (Get-FileHash -LiteralPath $HekInputJms).Hash) {
            throw 'HEK input JMS does not match the CE partition.'
        }
    } else {
        Copy-Item -LiteralPath $SourceJms -Destination (Join-Path $HekModels 'tst.JMS') -Force
    }
    if ($SplitFacilityDetail -and (Test-Path -LiteralPath $WaterTarget)) { throw "Water destination appeared: $WaterTarget" }
    if ($SplitFacilityDetail) { [IO.File]::Copy($WaterSource,$WaterTarget,$false) }
    else { Copy-Item -LiteralPath $WaterSource -Destination $WaterTarget -Force }
    # HEK resolves a bare "cliffs" material to levels/test/mirror/cliffs.
    # A uniquely named local copy keeps B30's unchanged bitmap references.
    if ($SplitFacilityDetail -and (Test-Path -LiteralPath $CliffTarget)) { throw "Cliff destination appeared: $CliffTarget" }
    if ($SplitFacilityDetail) { [IO.File]::Copy($CliffSource,$CliffTarget,$false) }
    else { Copy-Item -LiteralPath $CliffSource -Destination $CliffTarget -Force }

    # Distinct authored slots survive the CE intermediate. Classic CE uses
    # these stock fallback tags; the native build binds surfaces.json's PBR art.
    $Surfaces = Get-Content -LiteralPath (Join-Path $SourceRoot 'surfaces.json') -Raw | ConvertFrom-Json
    foreach ($Property in $Surfaces.surfaces.PSObject.Properties) {
        $Surface = $Property.Value
        $Fallback = Join-Path $TagsRoot ("levels\b30\shaders\" + $Surface.fallback + '.shader_environment')
        $Target = Join-Path $TagsRoot ($Surface.tag + '.shader_environment')
        if (-not (Test-Path -LiteralPath $Fallback)) { throw "Missing stock metal shader: $Fallback" }
        if ($SplitFacilityDetail -and (Test-Path -LiteralPath $Target)) { throw "Surface destination appeared: $Target" }
        if ($SplitFacilityDetail) { [IO.File]::Copy($Fallback,$Target,$false) }
        else { Copy-Item -LiteralPath $Fallback -Destination $Target -Force }
    }

    # Derive the status-lens color in a real CE shader, preserving the stock
    # atlas references. Generate/read-back in source first, then stage for HEK.
    $AmberBuildOutput = if ($SplitFacilityDetail) { Join-Path $Bundle 'tst_lights_amber.shader_environment' } else { $AmberSource }
    if ($SplitFacilityDetail -and (Test-Path -LiteralPath $AmberBuildOutput)) { throw "Amber destination appeared: $AmberBuildOutput" }
    Invoke-RebuildStage -Name 'amber-shader' -Executable $PythonExe -Arguments @(
        '-B', (Join-Path $SourceRoot 'amber_light.py'), '--hek', $HekRoot,
        '--addon', $AddonRoot, '--output', $AmberBuildOutput) -ExpectedFile $AmberBuildOutput
    if ($SplitFacilityDetail) { [IO.File]::Copy($AmberBuildOutput,$AmberTarget,$false) }
    else { Copy-Item -LiteralPath $AmberSource -Destination $AmberTarget -Force }

    if ($SplitFacilityDetail -and (Test-Path -LiteralPath $BspFile)) { throw "BSP destination appeared: $BspFile" }
    $StructureStart = [DateTime]::UtcNow
    Invoke-RebuildStage -Name 'structure' -Executable $ToolExe -WorkingDirectory $HekRoot `
        -Arguments @('structure', 'levels\test\tst', 'tst') -ExpectedFile $BspFile -HekStage
    if ($SplitFacilityDetail) {
        $Evidence = Join-Path $Bundle 'evidence'
        New-Item -ItemType Directory -Path $Evidence -ErrorAction Stop | Out-Null
        $FrozenBsp = Join-Path $Evidence 'structure-before-lightmaps.scenario_structure_bsp'
        $StructureLog = Join-Path $Evidence 'structure.log'
        $InputManifest = Join-Path $Evidence 'build-input-manifest.json'
        Copy-Item -LiteralPath $BspFile -Destination $FrozenBsp
        Copy-Item -LiteralPath (Join-Path $RunLogs 'structure.log') -Destination $StructureLog
        $InputHashes = [ordered]@{
            jms=(Get-FileHash -LiteralPath $HekInputJms -Algorithm SHA256).Hash.ToLowerInvariant()
            bsp=(Get-FileHash -LiteralPath $FrozenBsp -Algorithm SHA256).Hash.ToLowerInvariant()
            surfaces=(Get-FileHash -LiteralPath $SurfaceLibrary -Algorithm SHA256).Hash.ToLowerInvariant()
            source_jms=(Get-FileHash -LiteralPath $SourceJms -Algorithm SHA256).Hash.ToLowerInvariant()
            partition_manifest=(Get-FileHash -LiteralPath (Join-Path $PartitionOut 'manifest.json') -Algorithm SHA256).Hash.ToLowerInvariant()
            placements=(Get-FileHash -LiteralPath $PlacementInput -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        if ($InputHashes.jms -ne (Get-FileHash -LiteralPath $CeJms -Algorithm SHA256).Hash.ToLowerInvariant() -or
            $InputHashes.bsp -ne (Get-FileHash -LiteralPath $BspFile -Algorithm SHA256).Hash.ToLowerInvariant()) {
            throw 'HEK input or structure BSP changed while freezing the build evidence.'
        }
        [ordered]@{schema=1;created_utc=[DateTime]::UtcNow.ToString('o');hashes=$InputHashes;texture_hashes=$TextureHashes} |
            ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $InputManifest -Encoding utf8
    }
    # A fresh HEK's structure compiler may itself create an initial scenario.
    # It was absent at preflight, so accept only one freshly produced by this
    # structure stage; the authored scenario builder then replaces that stub.
    if ($SplitFacilityDetail -and (Test-Path -LiteralPath $ScenarioFile) -and
        (Get-Item -LiteralPath $ScenarioFile).LastWriteTimeUtc -lt $StructureStart.AddSeconds(-2)) {
        throw "Scenario destination predates this structure build: $ScenarioFile"
    }
    Invoke-RebuildStage -Name 'scenario' -Executable $PythonExe -Arguments @(
        '-B', (Join-Path $SourceRoot 'build_scenario.py'), '--hek', $HekRoot,
        '--addon', $AddonRoot, '--placements', $PlacementInput) `
        -ExpectedFile $ScenarioFile
    $SourceScenario = Join-Path $SourceRoot 'tags\levels\test\tst\tst.scenario'
    if ($SplitFacilityDetail) {
        $SourceScenario = Join-Path $Evidence 'tst.scenario'
        Copy-Item -LiteralPath $ScenarioFile -Destination $SourceScenario
        $ScenarioLog = Join-Path $Evidence 'scenario.log'
        Copy-Item -LiteralPath (Join-Path $RunLogs 'scenario.log') -Destination $ScenarioLog
    } else {
        New-Item -ItemType Directory -Path (Split-Path -Parent $SourceScenario) -Force | Out-Null
        Copy-Item -LiteralPath $ScenarioFile -Destination $SourceScenario -Force
    }

    if ($SplitFacilityDetail -and (Test-Path -LiteralPath $LightmapFile) -and
        (Get-Item -LiteralPath $LightmapFile).LastWriteTimeUtc -lt $StructureStart.AddSeconds(-2)) {
        throw "Lightmap destination predates this structure build: $LightmapFile"
    }
    Invoke-RebuildStage -Name 'lightmaps' -Executable $ToolExe -WorkingDirectory $HekRoot `
        -Arguments @('lightmaps', $ScenarioTag, 'tst', '0', '0.1') -ExpectedFile $LightmapFile -HekStage
    if ($SplitFacilityDetail) {
        $LightmapLog = Join-Path $Evidence 'lightmaps.log'
        $EvidenceBitmap = Join-Path $Evidence 'tst.bitmap'
        Copy-Item -LiteralPath (Join-Path $RunLogs 'lightmaps.log') -Destination $LightmapLog
        Copy-Item -LiteralPath $LightmapFile -Destination $EvidenceBitmap
        if ((Get-FileHash -LiteralPath $EvidenceBitmap -Algorithm SHA256).Hash -ne
            (Get-FileHash -LiteralPath $LightmapFile -Algorithm SHA256).Hash) { throw 'Frozen lightmap bitmap differs from the HEK output.' }
    }

    # Embedding the new lightmap requires temporarily hiding the shared bitmap cache.
    # Finally restores the original even if cache compilation or validation fails.
    $BitmapMoved = $false
    try {
        if ($SplitFacilityDetail -and (Test-Path -LiteralPath $MapFile)) { throw "Map destination appeared: $MapFile" }
        if ($SplitFacilityDetail) { $BitmapOriginalHash = (Get-FileHash -LiteralPath $BitmapMap -Algorithm SHA256).Hash }
        Move-Item -LiteralPath $BitmapMap -Destination $BitmapBackup
        $BitmapMoved = $true
        Invoke-RebuildStage -Name 'cache' -Executable $ToolExe -WorkingDirectory $HekRoot `
            -Arguments @('build-cache-file', $ScenarioTag) -ExpectedFile $MapFile -HekStage
    } finally {
        if ($BitmapMoved) {
            if (Test-Path -LiteralPath $BitmapMap) {
                if ((Get-Item -LiteralPath $BitmapMap).Length -eq 0) {
                    # tool creates an empty placeholder when bitmaps are embedded.
                    Remove-Item -LiteralPath $BitmapMap
                } else {
                    Move-Item -LiteralPath $BitmapMap -Destination $BitmapCreated
                    Write-Warning "Preserved a newly created bitmap cache at $BitmapCreated"
                }
            }
            Move-Item -LiteralPath $BitmapBackup -Destination $BitmapMap
            if ($SplitFacilityDetail -and (Get-FileHash -LiteralPath $BitmapMap -Algorithm SHA256).Hash -ne $BitmapOriginalHash) {
                throw 'Dedicated HEK bitmap cache did not restore to its original hash.'
            }
        }
    }
    if ($SplitFacilityDetail) {
        # Keep immutable, inspectable evidence in the new bundle. The canonical
        # receipt is published only after the completed cache and a second
        # verification. Partial builds never leave a canonical receipt.
        $CacheLog = Join-Path $Evidence 'cache.log'
        $BundledMap = Join-Path $Bundle 'tst.map'
        $PendingReceipt = Join-Path $Bundle '.tst-facility-ce-build-receipt.pending'
        $Receipt = Join-Path $Bundle 'tst-facility-ce-build-receipt.json'
        foreach ($Output in @($CacheLog,$BundledMap,$PendingReceipt,$Receipt)) {
            if (Test-Path -LiteralPath $Output) { throw "Split-build evidence destination appeared: $Output" }
        }
        [IO.File]::Copy((Join-Path $RunLogs 'cache.log'),$CacheLog,$false)
        [IO.File]::Copy($MapFile,$BundledMap,$false)
        if ((Get-FileHash -LiteralPath $BundledMap -Algorithm SHA256).Hash -ne
            (Get-FileHash -LiteralPath $MapFile -Algorithm SHA256).Hash) { throw 'Bundled CE map differs from the HEK output.' }
        foreach ($RelativeTexture in $TextureHashes.Keys) {
            $Texture = [IO.Path]::GetFullPath((Join-Path $AuthoringOut $RelativeTexture))
            if ((Get-FileHash -LiteralPath $Texture -Algorithm SHA256).Hash.ToLowerInvariant() -ne $TextureHashes[$RelativeTexture]) {
                throw "Bundled texture changed during the build: $RelativeTexture"
            }
        }
        $ReceiptArguments = @('--partition-dir',$PartitionOut,'--detail',$DetailGltf,'--source-jms',$SourceJms,
            '--surfaces',$SurfaceLibrary,'--map',$BundledMap,'--input-manifest',$InputManifest,
            '--hek-input-jms',$HekInputJms,'--frozen-bsp',$FrozenBsp,'--structure-log',$StructureLog,
            '--scenario-log',$ScenarioLog,'--lightmap-log',$LightmapLog,'--lightmap-bitmap',$EvidenceBitmap,
            '--cache-log',$CacheLog)
        Invoke-RebuildStage -Name 'facility-build-receipt' -Executable $PythonExe -Arguments (@('-B',$ReceiptMaker)+$ReceiptArguments+@('--out',$PendingReceipt)) `
            -ExpectedFile $PendingReceipt
        Invoke-RebuildStage -Name 'facility-receipt-verify' -Executable $PythonExe -Arguments @(
            '-B',$ReceiptVerifier,'--partition-dir',$PartitionOut,'--detail',$DetailGltf,
            '--source-jms',$SourceJms,'--surfaces',$SurfaceLibrary,'--map',$BundledMap,'--receipt',$PendingReceipt)
        [IO.File]::Move($PendingReceipt,$Receipt,$false)
        Write-Host "Experimental split build bundle: $Bundle"
        Write-Host "Full JMS: $SourceJms"
        Write-Host "CE map: $BundledMap"
        Write-Host "Native detail: $DetailGltf"
        Write-Host "Verified CE build receipt: $Receipt"
    }
    Write-Host "TST CE map rebuilt: $MapFile"
    Write-Host "Authored scenario saved: $SourceScenario"
    Write-Host "Logs: $RunLogs"
} finally {
    $BuildLock.Dispose()
}
