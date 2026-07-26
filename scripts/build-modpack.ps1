<#
.SYNOPSIS
    Build the MJOLNIR modpack zip and manifest for distribution.

.DESCRIPTION
    Assembles UE4SS binaries + MJOLNIR mods + signatures + config into a
    distributable zip. Computes SHA-256 for every file and generates manifest.json.

.PARAMETER Ue4ssZipPath
    Path to the UE4SS release zip (e.g., UE4SS_v3.0.1.zip from GitHub Releases).
    The zip should contain dwmapi.dll, UE4SS.dll, etc.

.PARAMETER OutputDir
    Directory to write modpack.zip and manifest.json. Defaults to ./dist/modpack/

.EXAMPLE
    .\build-modpack.ps1 -Ue4ssZipPath "C:\Downloads\UE4SS_v3.0.1.zip"
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$Ue4ssZipPath,

    [string]$OutputDir = "$PSScriptRoot\..\dist\modpack",

    [string]$ModpackVersion = "1.0.0",
    [string]$Ue4ssVersion = "3.0.1"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path "$PSScriptRoot\.."

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  MJOLNIR Modpack Builder" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# ── Validate inputs ──
if (-not (Test-Path $Ue4ssZipPath)) {
    Write-Error "UE4SS zip not found: $Ue4ssZipPath"
    exit 1
}

# ── Create staging directory ──
$stagingDir = Join-Path ([System.IO.Path]::GetTempPath()) "mjolnir-modpack-staging"
if (Test-Path $stagingDir) { Remove-Item $stagingDir -Recurse -Force }
New-Item -ItemType Directory -Path $stagingDir | Out-Null
Write-Host "[1/6] Created staging directory: $stagingDir"

# ── Extract UE4SS release ──
Write-Host "[2/6] Extracting UE4SS release..."
$ue4ssExtractDir = Join-Path $stagingDir "_ue4ss_raw"
Expand-Archive -Path $Ue4ssZipPath -DestinationPath $ue4ssExtractDir -Force

# Copy dwmapi.dll (the proxy DLL) to root
$dwmapiSource = Get-ChildItem -Path $ue4ssExtractDir -Filter "dwmapi.dll" -Recurse | Select-Object -First 1
if (-not $dwmapiSource) {
    Write-Error "dwmapi.dll not found in UE4SS zip"
    exit 1
}
Copy-Item $dwmapiSource.FullName (Join-Path $stagingDir "dwmapi.dll")

# Copy ue4ss directory contents
$ue4ssDir = Join-Path $stagingDir "ue4ss"
New-Item -ItemType Directory -Path $ue4ssDir | Out-Null

# Look for UE4SS.dll
$ue4ssDll = Get-ChildItem -Path $ue4ssExtractDir -Filter "UE4SS.dll" -Recurse | Select-Object -First 1
if ($ue4ssDll) {
    Copy-Item $ue4ssDll.FullName (Join-Path $ue4ssDir "UE4SS.dll")
}

# Copy any other DLLs from the ue4ss directory in the zip
$rawUe4ssDir = Get-ChildItem -Path $ue4ssExtractDir -Directory -Filter "ue4ss" -Recurse | Select-Object -First 1
if ($rawUe4ssDir) {
    Get-ChildItem -Path $rawUe4ssDir.FullName -Recurse | ForEach-Object {
        $relativePath = $_.FullName.Substring($rawUe4ssDir.FullName.Length + 1)
        $destPath = Join-Path $ue4ssDir $relativePath
        if ($_.PSIsContainer) {
            New-Item -ItemType Directory -Path $destPath -Force | Out-Null
        }
        else {
            $destParent = Split-Path $destPath -Parent
            if (-not (Test-Path $destParent)) { New-Item -ItemType Directory -Path $destParent -Force | Out-Null }
            Copy-Item $_.FullName $destPath -Force
        }
    }
}

# ── Copy UE4SS settings ──
Write-Host "[3/7] Copying UE4SS-settings.ini..."
Copy-Item (Join-Path $RepoRoot "config\UE4SS-settings.ini") (Join-Path $ue4ssDir "UE4SS-settings.ini") -Force

# ── Copy signatures (Steam + Game Pass) ──
Write-Host "[4/7] Copying signatures..."
$sigDir = Join-Path $ue4ssDir "UE4SS_Signatures"
New-Item -ItemType Directory -Path $sigDir -Force | Out-Null

# Copy repo's own signatures first
Get-ChildItem (Join-Path $RepoRoot "signatures") -File | ForEach-Object {
    Copy-Item $_.FullName (Join-Path $sigDir $_.Name)
}

# Copy Game Pass signatures from the custom game configs
$gameConfigsZip = Join-Path (Split-Path $Ue4ssZipPath -Parent) "zCustomGameConfigs.zip"
if (Test-Path $gameConfigsZip) {
    Write-Host "  Found custom game configs, extracting HCE signatures..."
    $cfgExtract = Join-Path ([System.IO.Path]::GetTempPath()) "mjolnir-configs-extract"
    if (Test-Path $cfgExtract) { Remove-Item $cfgExtract -Recurse -Force }
    Expand-Archive -Path $gameConfigsZip -DestinationPath $cfgExtract -Force

    $hceSigDir = Join-Path $cfgExtract "Halo Campaign Evolved\UE4SS_Signatures"
    if (Test-Path $hceSigDir) {
        # Copy upstream Steam signatures (overwrite repo's if newer)
        Get-ChildItem $hceSigDir -File | ForEach-Object {
            Copy-Item $_.FullName (Join-Path $sigDir $_.Name) -Force
            Write-Host "    Steam sig: $($_.Name)" -ForegroundColor DarkGray
        }

        # Copy Game Pass signatures into gamepass/ subdirectory
        $gpSigSource = Join-Path $hceSigDir "gamepass"
        if (Test-Path $gpSigSource) {
            $gpSigDest = Join-Path $sigDir "gamepass"
            New-Item -ItemType Directory -Path $gpSigDest -Force | Out-Null
            Get-ChildItem $gpSigSource -File | ForEach-Object {
                Copy-Item $_.FullName (Join-Path $gpSigDest $_.Name)
                Write-Host "    Game Pass sig: gamepass/$($_.Name)" -ForegroundColor DarkGray
            }
        }
    }

    Remove-Item $cfgExtract -Recurse -Force
} else {
    Write-Host "  No zCustomGameConfigs.zip found alongside UE4SS zip. Skipping Game Pass signatures."
    Write-Host "  To include Game Pass support, place zCustomGameConfigs.zip in the same directory as the UE4SS zip."
}

# ── Copy MJOLNIR mods ──
Write-Host "[5/6] Copying MJOLNIR mods..."
$modsDir = Join-Path $ue4ssDir "Mods"
New-Item -ItemType Directory -Path $modsDir -Force | Out-Null

$mjolnirMods = @(
    "MJOLNIRCore",
    "MJOLNIRConsoleEnabler",
    "MJOLNIRFlyCam",
    "MJOLNIRDiscovery",
    "MJOLNIRMultiplayer"
)

foreach ($mod in $mjolnirMods) {
    $modSource = Join-Path $RepoRoot "mods\$mod"
    if (Test-Path $modSource) {
        Copy-Item $modSource (Join-Path $modsDir $mod) -Recurse
    }
    else {
        Write-Warning "Mod directory not found: $modSource"
    }
}

# Also copy any shared UE4SS mods that exist in the extracted zip's Mods dir
$rawModsDir = Get-ChildItem -Path $ue4ssExtractDir -Directory -Filter "Mods" -Recurse | Select-Object -First 1
if ($rawModsDir) {
    Get-ChildItem -Path $rawModsDir.FullName -Directory | ForEach-Object {
        $destMod = Join-Path $modsDir $_.Name
        if (-not (Test-Path $destMod)) {
            Copy-Item $_.FullName $destMod -Recurse
        }
    }
    # Copy mods.txt if it exists from UE4SS
    $rawModsTxt = Join-Path $rawModsDir.FullName "mods.txt"
    if (Test-Path $rawModsTxt) {
        Copy-Item $rawModsTxt (Join-Path $modsDir "mods.txt") -Force
    }
}

# Generate mods.txt with MJOLNIR mods enabled (append if it exists)
$modsTxt = Join-Path $modsDir "mods.txt"
$existingContent = ""
if (Test-Path $modsTxt) {
    $existingContent = Get-Content $modsTxt -Raw
}

$modsToAdd = @()
foreach ($mod in $mjolnirMods) {
    if ($existingContent -notmatch [regex]::Escape($mod)) {
        $modsToAdd += "${mod} : 1"
    }
}

if ($modsToAdd.Count -gt 0) {
    $appendText = "`n; MJOLNIR Mods`n" + ($modsToAdd -join "`n") + "`n"
    Add-Content -Path $modsTxt -Value $appendText
}

# ── Build manifest and zip ──
Write-Host "[6/6] Building manifest and zip..."

# Create output dir
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

# Compute SHA-256 for all files
$manifestFiles = @()
Get-ChildItem -Path $stagingDir -File -Recurse | Where-Object { $_.FullName -notlike "*_ue4ss_raw*" } | ForEach-Object {
    $relativePath = $_.FullName.Substring($stagingDir.Length + 1).Replace("\", "/")
    $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
    $manifestFiles += @{
        path   = $relativePath
        sha256 = $hash
        size   = $_.Length
    }
    Write-Host "  $hash  $relativePath" -ForegroundColor DarkGray
}

$manifest = @{
    version       = $ModpackVersion
    ue4ss_version = $Ue4ssVersion
    files         = $manifestFiles
}

$manifestJson = $manifest | ConvertTo-Json -Depth 5
$manifestPath = Join-Path $OutputDir "manifest.json"
$manifestJson | Out-File -FilePath $manifestPath -Encoding utf8
Write-Host "  Manifest: $manifestPath" -ForegroundColor Green

# Create zip (exclude raw ue4ss extract)
$zipPath = Join-Path $OutputDir "modpack.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath }

# Use .NET to create zip from staging (excluding _ue4ss_raw)
Add-Type -AssemblyName System.IO.Compression.FileSystem

$zipStream = [System.IO.File]::Create($zipPath)
$archive = New-Object System.IO.Compression.ZipArchive($zipStream, [System.IO.Compression.ZipArchiveMode]::Create)

Get-ChildItem -Path $stagingDir -File -Recurse | Where-Object { $_.FullName -notlike "*_ue4ss_raw*" } | ForEach-Object {
    $relativePath = $_.FullName.Substring($stagingDir.Length + 1).Replace("\", "/")
    $entry = $archive.CreateEntry($relativePath, [System.IO.Compression.CompressionLevel]::Optimal)
    $entryStream = $entry.Open()
    $fileStream = [System.IO.File]::OpenRead($_.FullName)
    $fileStream.CopyTo($entryStream)
    $fileStream.Close()
    $entryStream.Close()
}

$archive.Dispose()
$zipStream.Close()

$zipSize = (Get-Item $zipPath).Length
Write-Host "  Zip: $zipPath ($([math]::Round($zipSize / 1MB, 2)) MB)" -ForegroundColor Green

# Cleanup staging
Remove-Item $stagingDir -Recurse -Force

Write-Host ""
Write-Host "=========================================" -ForegroundColor Green
Write-Host "  Build complete!" -ForegroundColor Green
Write-Host "  Files: $($manifestFiles.Count)" -ForegroundColor Green
Write-Host "  Version: $ModpackVersion" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green
Write-Host ""
Write-Host "To upload to R2:" -ForegroundColor Yellow
Write-Host "  wrangler r2 object put `"mjolnir-releases/modpack/latest/manifest.json`" --file=`"$manifestPath`" --remote" -ForegroundColor DarkYellow
Write-Host "  wrangler r2 object put `"mjolnir-releases/modpack/latest/modpack.zip`" --file=`"$zipPath`" --remote" -ForegroundColor DarkYellow
