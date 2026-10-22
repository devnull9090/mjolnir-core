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
#>
[CmdletBinding()]
param(
    [string]$HekRoot = 'C:\haloce\hek',
    [string]$BlenderExe = 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe',
    [string]$PythonExe = 'python',
    [string]$AddonRoot = 'C:\haloce\tools\halo-blender-425\addons\io_scene_halo',
    [string]$MccTagsRoot = 'C:\Program Files (x86)\Steam\steamapps\common\HCEEK\tags',
    [switch]$SkipGeometry
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

foreach ($Required in @($ToolExe, $WaterSource,
        (Join-Path $AddonRoot 'file_tag\tag_interface\tag_interface.py'),
        (Join-Path $SourceRoot 'build_scenario.py'),
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
    foreach ($Relative in $StockInputs) {
        $StockSource = Join-Path $MccTagsRoot $Relative
        $StockTarget = Join-Path $TagsRoot $Relative
        if (-not (Test-Path -LiteralPath $StockTarget)) {
            New-Item -ItemType Directory -Path (Split-Path -Parent $StockTarget) -Force | Out-Null
            Copy-Item -LiteralPath $StockSource -Destination $StockTarget
        }
    }
    if (-not $SkipGeometry) {
        $PreviousAddons = $env:HALO_BLENDER_ADDONS
        try {
            $env:HALO_BLENDER_ADDONS = Split-Path -Parent $AddonRoot
            Invoke-RebuildStage -Name 'geometry' -Executable $BlenderExe -Arguments @(
                '--background', '--factory-startup', '--python-exit-code', '1',
                '--python', (Join-Path $SourceRoot 'build_geometry.py')) -ExpectedFile $SourceJms
            # Annotation runs only after the clean JMS export. It adds
            # inspection empties/camera and a source README to the .blend;
            # placement JSON and the exported game geometry stay unchanged.
            Invoke-RebuildStage -Name 'annotate' -Executable $BlenderExe -Arguments @(
                '--background', '--factory-startup', '--python-exit-code', '1',
                '--python', (Join-Path $SourceRoot 'annotate_blend.py')) `
                -ExpectedFile (Join-Path $SourceRoot 'tst.blend')
        } finally {
            $env:HALO_BLENDER_ADDONS = $PreviousAddons
        }
    }
    foreach ($Required in @($SourceJms, (Join-Path $SourceRoot 'placements.json'))) {
        if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) {
            throw "Authoring input is missing: $Required"
        }
    }
    $HekModels = Join-Path $HekRoot 'data\levels\test\tst\models'
    New-Item -ItemType Directory -Path $HekModels, (Split-Path -Parent $WaterTarget) -Force | Out-Null
    Copy-Item -LiteralPath $SourceJms -Destination (Join-Path $HekModels 'tst.JMS') -Force
    Copy-Item -LiteralPath $WaterSource -Destination $WaterTarget -Force
    # HEK resolves a bare "cliffs" material to levels/test/mirror/cliffs.
    # A uniquely named local copy keeps B30's unchanged bitmap references.
    Copy-Item -LiteralPath $CliffSource -Destination $CliffTarget -Force

    Invoke-RebuildStage -Name 'structure' -Executable $ToolExe -WorkingDirectory $HekRoot `
        -Arguments @('structure', 'levels\test\tst', 'tst') -ExpectedFile $BspFile -HekStage
    Invoke-RebuildStage -Name 'scenario' -Executable $PythonExe -Arguments @(
        '-B', (Join-Path $SourceRoot 'build_scenario.py'), '--hek', $HekRoot,
        '--addon', $AddonRoot, '--placements', (Join-Path $SourceRoot 'placements.json')) `
        -ExpectedFile $ScenarioFile
    $SourceScenario = Join-Path $SourceRoot 'tags\levels\test\tst\tst.scenario'
    New-Item -ItemType Directory -Path (Split-Path -Parent $SourceScenario) -Force | Out-Null
    Copy-Item -LiteralPath $ScenarioFile -Destination $SourceScenario -Force

    Invoke-RebuildStage -Name 'lightmaps' -Executable $ToolExe -WorkingDirectory $HekRoot `
        -Arguments @('lightmaps', $ScenarioTag, 'tst', '0', '0.1') -ExpectedFile $LightmapFile -HekStage

    # Embedding the new lightmap requires temporarily hiding the shared bitmap cache.
    # Finally restores the original even if cache compilation or validation fails.
    $BitmapMoved = $false
    try {
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
        }
    }
    Write-Host "TST CE map rebuilt: $MapFile"
    Write-Host "Authored scenario saved: $SourceScenario"
    Write-Host "Logs: $RunLogs"
} finally {
    $BuildLock.Dispose()
}
