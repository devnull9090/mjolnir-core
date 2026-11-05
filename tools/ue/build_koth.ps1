<#
.SYNOPSIS
    Build and package only the KOTH material container (shader chunk 966).
.DESCRIPTION
    Produces a dated package with logs and SHA-256 hashes. -Install explicitly
    copies that package's three KOTH files into a stopped game's Paks folder,
    backing up previous files first. No Lua, other chunks, or releases change.
.EXAMPLE
    powershell -NoProfile -File tools/ue/build_koth.ps1
.EXAMPLE
    powershell -NoProfile -File tools/ue/build_koth.ps1 -Install -GameDir "C:\Games\Halo Campaign Evolved"
#>
[CmdletBinding()]
param(
    [ValidateRange(1, [long]::MaxValue)][long]$Mask = 0x0F,
    [string]$OutputDir,
    [switch]$Install,
    [string]$GameDir = $env:MJOLNIR_GAME_DIR
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$project = Join-Path $repo 'unreal\MJOLNIRMaterials'
$builder = Join-Path $project 'Scripts\build_koth_materials.py'
$stem = 'pakchunk966-MJOLNIRKOTH-Windows'
$extensions = @('pak', 'utoc', 'ucas')

function Assert-GameStopped {
    if (Get-Process -Name HaloCampaignEvolved -ErrorAction SilentlyContinue) {
        throw 'Close Halo Campaign Evolved before using -Install. No game process is stopped by this helper.'
    }
}

function Find-GamePaks {
    param([string]$Requested)
    $candidates = @()
    if ($Requested) {
        $candidates = @($Requested)
    } else {
        $steamRoots = @('C:\Program Files (x86)\Steam', 'C:\Program Files\Steam')
        if ($env:LOCALAPPDATA) { $steamRoots += Join-Path $env:LOCALAPPDATA 'Steam' }
        foreach ($steamRoot in @($steamRoots)) {
            $index = Join-Path $steamRoot 'steamapps\libraryfolders.vdf'
            if (Test-Path -LiteralPath $index) {
                foreach ($match in [regex]::Matches((Get-Content -LiteralPath $index -Raw), '"path"\s+"([^"]+)"')) {
                    $steamRoots += $match.Groups[1].Value.Replace('\\', '\')
                }
            }
        }
        $candidates = @($steamRoots | Select-Object -Unique | ForEach-Object {
            Join-Path $_ 'steamapps\common\Halo Campaign Evolved'
        })
    }
    foreach ($candidate in $candidates) {
        $executables = @('Win64', 'WinGDK') | ForEach-Object {
            Join-Path $candidate "Meteorite\Binaries\$_\HaloCampaignEvolved.exe"
        }
        if ($executables | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }) {
            return (Resolve-Path -LiteralPath (Join-Path $candidate 'Meteorite\Content\Paks')).Path
        }
    }
    throw 'Game install not found. Pass -GameDir as the directory containing Meteorite (Xbox: the Content directory).'
}

function Assert-BuildLog {
    param([string]$Path, [datetime]$Started)
    $file = Get-Item -LiteralPath $Path -ErrorAction Stop
    if ($file.LastWriteTimeUtc -lt $Started.AddSeconds(-2)) { throw "Stale build log: $Path" }
    $body = Get-Content -LiteralPath $Path -Raw
    if ($body -match '(?im)\b(?:Error|Fatal error):|BUILD FAILED|Shader compiler errors|Failed to compile Material|Default Material will be used|doesn.t have a valid ShaderMap|Shadermap pointer is null') {
        throw "Build errors recorded in $Path"
    }
    if ($body -notmatch 'fork layouts:.*\b0 do not\b') {
        throw "Fork layout validation is missing or failed in $Path"
    }
    return $body
}

function Get-InputHashes {
    param([string]$Root, [string[]]$Paths)
    $hashes = [ordered]@{}
    foreach ($relative in $Paths) {
        $hashes[$relative] = (Get-FileHash -LiteralPath (Join-Path $Root $relative) -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    return $hashes
}

function Assert-InputsUnchanged {
    param([string]$Root, [System.Collections.IDictionary]$Snapshot)
    $current = Get-InputHashes $Root @($Snapshot.Keys)
    foreach ($relative in $Snapshot.Keys) {
        if ($current[$relative] -ne $Snapshot[$relative]) {
            throw "Build input changed during the cook: $relative. Discard this run and rebuild."
        }
    }
}

function Install-KothPackage {
    param([string]$ContentDirectory, [string]$PaksDirectory, [string]$BackupDirectory,
          [System.Collections.IDictionary]$FileHashes, [string]$FailureReceipt)
    $paksRoot = (Resolve-Path -LiteralPath $PaksDirectory).Path.TrimEnd([IO.Path]::DirectorySeparatorChar)
    $backupRoot = (Resolve-Path -LiteralPath $BackupDirectory).Path
    $names = @('pak', 'utoc', 'ucas') | ForEach-Object { "pakchunk966-MJOLNIRKOTH-Windows.$_" }
    if ($FileHashes.Count -ne 3) { throw 'KOTH installation requires exactly the named container triple.' }
    $targets, $previous, $touched = [ordered]@{}, [ordered]@{}, @()
    foreach ($name in $names) {
        if (-not $FileHashes.Contains($name)) { throw "Missing KOTH file hash: $name" }
        $target = [IO.Path]::GetFullPath((Join-Path $paksRoot $name))
        if ([IO.Path]::GetDirectoryName($target) -ne $paksRoot) { throw "Target escapes Paks directory: $target" }
        $targets[$name] = $target
    }
    try {
        Assert-GameStopped
        # Verify every backup before replacing any file. Track existence so a
        # first installation can remove only the exact files it created.
        foreach ($name in $names) {
            $target = $targets[$name]
            $previous[$name] = $null
            if (Test-Path -LiteralPath $target) {
                if ((Get-Item -LiteralPath $target).PSIsContainer) { throw "Expected a file: $target" }
                $oldHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
                $saved = Join-Path $backupRoot $name
                Copy-Item -LiteralPath $target -Destination $saved -ErrorAction Stop
                if ((Get-FileHash -LiteralPath $saved -Algorithm SHA256).Hash -ne $oldHash) {
                    throw "Backup verification failed: $saved"
                }
                $previous[$name] = $oldHash
            }
        }
        foreach ($name in $names) {
            Assert-GameStopped
            $touched += $name # A failing copy may already have truncated its target.
            Copy-Item -LiteralPath (Join-Path $ContentDirectory $name) -Destination $targets[$name] -Force -ErrorAction Stop
            if ((Get-FileHash -LiteralPath $targets[$name] -Algorithm SHA256).Hash.ToLowerInvariant() -ne $FileHashes[$name]) {
                throw "Installed hash mismatch: $name"
            }
        }
    } catch {
        $installFailure = $_
        $rollback = [ordered]@{}
        for ($i = $touched.Count - 1; $i -ge 0; $i--) {
            $name = $touched[$i]
            try {
                Assert-GameStopped
                if ($previous[$name]) {
                    Copy-Item -LiteralPath (Join-Path $backupRoot $name) -Destination $targets[$name] -Force -ErrorAction Stop
                    if ((Get-FileHash -LiteralPath $targets[$name] -Algorithm SHA256).Hash -ne $previous[$name]) {
                        throw "Restored hash mismatch: $name"
                    }
                    $rollback[$name] = 'restored'
                } else {
                    if (Test-Path -LiteralPath $targets[$name]) {
                        if ((Get-Item -LiteralPath $targets[$name]).PSIsContainer) { throw 'Refusing to remove a directory.' }
                        Remove-Item -LiteralPath $targets[$name] -Force -ErrorAction Stop
                    }
                    $rollback[$name] = 'removed-new-file'
                }
            } catch { $rollback[$name] = 'failed: ' + $_.Exception.Message }
        }
        [ordered]@{status='failed'; error=$installFailure.Exception.Message; game_paks=$paksRoot;
                   backup=$backupRoot; touched=$touched; rollback=$rollback} | ConvertTo-Json -Depth 5 |
            Set-Content -LiteralPath $FailureReceipt -Encoding UTF8
        throw "KOTH installation failed: $($installFailure.Exception.Message). Rollback results: $FailureReceipt"
    }
}

if (-not (Test-Path -LiteralPath $builder -PathType Leaf)) { throw "Missing material builder: $builder" }
foreach ($receipt in @('MeteoriteEditor.target', 'Meteorite-Win64-Shipping.target')) {
    if (-not (Test-Path -LiteralPath (Join-Path $project "Binaries\Win64\$receipt"))) {
        throw "Missing $receipt. Build the Unreal project targets first; see docs/koth_visuals.md."
    }
}
$cli = $env:MJOLNIR
if (-not $cli) {
    $cli = @('target\release\mjolnir.exe', 'target\debug\mjolnir.exe') | ForEach-Object {
        Join-Path $repo $_
    } | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
}
if (-not $cli -or -not (Test-Path -LiteralPath $cli -PathType Leaf)) {
    throw 'Build blam-cli first or set MJOLNIR to its executable; fork retargeting is required.'
}
if ($Install) { Assert-GameStopped; $gamePaks = Find-GamePaks $GameDir }
if (-not $OutputDir) { $OutputDir = Join-Path $repo '.dream-loop\koth-package' }
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
$runName = [datetime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 6)
$package = Join-Path $OutputDir $runName
$content = Join-Path $package 'content'
New-Item -ItemType Directory -Path $content -Force | Out-Null

# Hold the same re-entrant mutex as both wrappers across build, cook and copy,
# so another conversion cannot replace staging between verification and copy.
$lock = New-Object System.Threading.Mutex($false, 'MjolnirMeteoriteProject')
try { [void]$lock.WaitOne() } catch [System.Threading.AbandonedMutexException] { }
$previousMask, $previousCli = $env:MJ_CPU_MASK, $env:MJOLNIR
$watcher = $null
$stage = 'input snapshot'
try {
    $inputPaths = @('unreal/MJOLNIRMaterials/Scripts/build_koth_materials.py',
                    'unreal/MJOLNIRMaterials/Scripts/build_ce_materials.py',
                    'unreal/MJOLNIRMaterials/Config/DefaultEngine.ini',
                    'unreal/MJOLNIRMaterials/Config/DefaultGame.ini',
                    'unreal/MJOLNIRMaterials/Config/ForkUniformBuffers.json',
                    'unreal/MJOLNIRMaterials/Meteorite.uproject',
                    'assets/koth/plasma-filaments.png')
    $inputSnapshot = Get-InputHashes $repo $inputPaths
    $inputSnapshot | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $package 'input-snapshot.json') -Encoding UTF8
    # An explicit bounded mask wins over an inherited all-core setting.
    $env:MJ_CPU_MASK = $Mask.ToString('X')
    $env:MJOLNIR = (Resolve-Path -LiteralPath $cli).Path
    # The editor resets affinity after startup. Re-pin only this invocation's
    # descendants, never another project's editor or shader workers.
    $watcher = Start-Job -ArgumentList $PID, $Mask -ScriptBlock {
        param($ownerProcessId, $cpuMask)
        while (Get-Process -Id $ownerProcessId -ErrorAction SilentlyContinue) {
            $processes = @(Get-CimInstance Win32_Process)
            $descendants = @([int]$ownerProcessId)
            do {
                $children = @($processes | Where-Object {
                    $_.ParentProcessId -in $descendants -and $_.ProcessId -notin $descendants
                })
                $descendants += @($children.ProcessId)
            } while ($children.Count)
            foreach ($process in $processes | Where-Object {
                $_.ProcessId -in $descendants -and $_.Name -match '^(UnrealEditor-Cmd|ShaderCompileWorker|UnrealPak)\.exe$'
            }) {
                try {
                    $running = Get-Process -Id $process.ProcessId -ErrorAction Stop
                    $running.ProcessorAffinity = [IntPtr]$cpuMask
                    $running.PriorityClass = [Diagnostics.ProcessPriorityClass]::BelowNormal
                } catch { } # Processes may finish between enumeration and pinning.
            }
            Start-Sleep -Seconds 1
        }
    }
    $stage = 'material build'
    $started = [datetime]::UtcNow
    & (Join-Path $PSScriptRoot 'editor_cmd.ps1') -Script 'Scripts/build_koth_materials.py' -Mask $Mask *> (Join-Path $package 'editor-wrapper.log')
    $editorOutput = Get-Content -LiteralPath (Join-Path $package 'editor-wrapper.log') -Raw
    $editorLog = Join-Path $project 'Saved_build_koth_materials.log'
    Copy-Item -LiteralPath $editorLog -Destination (Join-Path $package 'editor.log')
    if ($editorOutput -notmatch '(?m)^editor exit 0,') { throw "Editor failed; inspect $package" }
    $null = Assert-BuildLog $editorLog $started

    $stage = 'cook'
    $started = [datetime]::UtcNow
    & {
        # Windows PowerShell treats redirected native stderr as ErrorRecords.
        # Let cook.ps1 read the CLI exit code; validate its explicit result below.
        $ErrorActionPreference = 'Continue'
        & (Join-Path $PSScriptRoot 'cook.ps1') -Mask $Mask -Classes 'Material,MaterialInstanceConstant'
    } *> (Join-Path $package 'cook-wrapper.log')
    $cookOutput = Get-Content -LiteralPath (Join-Path $package 'cook-wrapper.log') -Raw
    $cookLog = Join-Path $project 'Saved_cook.log'
    Copy-Item -LiteralPath $cookLog -Destination (Join-Path $package 'cook.log')
    $cookBody = Assert-BuildLog $cookLog $started
    if ($cookOutput -notmatch '(?m)^cook exit 0\s*$' -or $cookBody -notmatch 'BUILD SUCCESSFUL') {
        throw "Cook failed; inspect $package"
    }
    if ($cookOutput -match 'NOT re-encoded|failed; its materials|WARNING: retarget') {
        throw "Cook retarget failed; inspect $package\cook-wrapper.log"
    }
    $retarget = [regex]::Match($cookOutput, '(?m)^retarget pakchunk966-Windows: (\d+) package\(s\) re-encoded,')
    if (-not $retarget.Success -or [int]$retarget.Groups[1].Value -lt 2) {
        throw 'Chunk 966 must freshly retarget both KOTH materials before packaging.'
    }

    $stage = 'input verification'
    Assert-InputsUnchanged $repo $inputSnapshot
    $stage = 'packaging'
    $staged = Join-Path $project 'Saved\StagedBuilds\Windows\Meteorite\Content\Paks'
    $files = [ordered]@{}
    foreach ($extension in $extensions) {
        $source = Join-Path $staged "pakchunk966-Windows.$extension"
        if ((Get-Item -LiteralPath $source).Length -eq 0) { throw "Empty staged file: $source" }
        $destination = Join-Path $content "$stem.$extension"
        Copy-Item -LiteralPath $source -Destination $destination
        $files["$stem.$extension"] = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $receipt = [ordered]@{
        schema_version = 1
        chunk = 966
        created_utc = [datetime]::UtcNow.ToString('o')
        material_paths = @('/Game/MJOLNIR/KOTH/M_KOTH_Field', '/Game/MJOLNIR/KOTH/M_KOTH_Beacon')
        builder_sha256 = $inputSnapshot['unreal/MJOLNIRMaterials/Scripts/build_koth_materials.py']
        inputs = $inputSnapshot
        cpu_mask = '0x' + $Mask.ToString('X')
        retargeted_packages = [int]$retarget.Groups[1].Value
        files = $files
    }
    $receipt | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $package 'receipt.json') -Encoding UTF8
    Write-Host "Verified KOTH package: $package"
} catch {
    $buildFailure = $_
    [ordered]@{status='failed'; stage=$stage; error=$buildFailure.Exception.Message;
               created_utc=[datetime]::UtcNow.ToString('o')} | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $package 'failed.json') -Encoding UTF8
    throw $buildFailure
} finally {
    try {
        if ($watcher) { Stop-Job -Job $watcher; Remove-Job -Job $watcher }
    } finally {
        $env:MJ_CPU_MASK, $env:MJOLNIR = $previousMask, $previousCli
        $lock.ReleaseMutex()
        $lock.Dispose()
    }
}

if ($Install) {
    Assert-GameStopped
    $backup = Join-Path $package 'previous-install'
    New-Item -ItemType Directory -Path $backup | Out-Null
    Install-KothPackage -ContentDirectory $content -PaksDirectory $gamePaks -BackupDirectory $backup `
        -FileHashes $files -FailureReceipt (Join-Path $package 'install-failed.json')
    [ordered]@{game_paks=$gamePaks; backup=$backup; files=$files} | ConvertTo-Json -Depth 4 |
        Set-Content -LiteralPath (Join-Path $package 'installed.json') -Encoding UTF8
    Write-Host "Installed only $stem.{pak,utoc,ucas}; previous files: $backup"
}
