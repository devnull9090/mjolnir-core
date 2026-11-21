#Requires -Version 7.0
<# Install the local prototype runtime with a file-by-file backup receipt.
   Build native/lobby and blam-cli, plus the Pelican and canopy containers first.
   The map itself is installed by upgrade.py --stages install --local-install.
   -SoloPreview creates a one-player, five-second warmup for local testing. #>
[CmdletBinding()]
param(
    [string]$Game = 'C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved',
    [string]$Pelican = '',
    [string]$Canopy = '',
    [string]$Mjolnir = '',
    [switch]$SoloPreview
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$gameRoot = [IO.Path]::GetFullPath($Game).TrimEnd('\')
$paks = Join-Path $gameRoot 'Meteorite\Content\Paks'
$mods = Join-Path $gameRoot 'Meteorite\Binaries\Win64\ue4ss\Mods'
$cli = if ($Mjolnir) { [IO.Path]::GetFullPath($Mjolnir) } else { Join-Path $repo 'target\release\mjolnir.exe' }
if (Get-Process -Name 'HaloCampaignEvolved','HaloCampaignEvolved-Win64-Shipping','Meteorite-Win64-Shipping' -ErrorAction SilentlyContinue) {
    throw 'Close the game before replacing the native DLL or mounted containers.'
}
if (-not $Pelican) { $Pelican = Join-Path $repo 'out\pwr\pelican' }
if (-not $Canopy) { $Canopy = Join-Path $repo 'out\pwr\canopy' }
$staging = Join-Path $repo ('out\pwr\runtime-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $staging | Out-Null
$variant = Join-Path $staging 'warfare.mglo'
$arguments = @('megalo','write','--mode','warfare','--vehicle-label-pool','--out',$variant)
if ($SoloPreview) { $arguments += @('--minimum-players','1','--warmup-seconds','5') }
& $cli @arguments
if ($LASTEXITCODE -ne 0) { throw 'Warfare variant build failed.' }
$copies = [Collections.Generic.List[object]]::new()
function Add-Copy([string]$Source, [string]$Destination) {
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) { throw "Missing runtime input: $Source" }
    $absolute = [IO.Path]::GetFullPath($Destination)
    if (-not $absolute.StartsWith($gameRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Outside game: $absolute" }
    $copies.Add(@{ source=[IO.Path]::GetFullPath($Source); destination=$absolute })
}
# These entrypoints and their helpers form a versioned runtime. Copying only
# changed files onto an older installed release leaves missing helper APIs.
foreach ($module in @('MJOLNIRLevelLoader','MJOLNIRLobby','MJOLNIRHud')) {
    $sourceRoot = Join-Path $repo "mods\$module\Scripts"
    foreach ($file in Get-ChildItem -LiteralPath $sourceRoot -File -Recurse) {
        $relative = [IO.Path]::GetRelativePath($sourceRoot, $file.FullName)
        Add-Copy $file.FullName (Join-Path $mods "$module\Scripts\$relative")
    }
}
foreach ($relative in @('MJOLNIRLobby\native\mjolnir_lobby.dll','MJOLNIRLevelLoader\native\mjolnir_map_registry.dll')) {
    Add-Copy (Join-Path $repo ('mods\' + $relative)) (Join-Path $mods $relative)
}
foreach ($extension in @('mglo','layout.json')) {
    Add-Copy (Join-Path $staging ('warfare.' + $extension)) (Join-Path $mods ('MJOLNIRLevelLoader\variants\warfare.' + $extension))
}
foreach ($directory in @($Pelican, $Canopy) | Where-Object { $_ }) {
    $containers = @(Get-ChildItem -LiteralPath $directory -Filter '*.utoc' -File)
    if (-not $containers.Count) { throw "No containers in $directory" }
    foreach ($container in $containers) {
        foreach ($extension in @('pak','utoc','ucas')) {
            $name = $container.BaseName + '.' + $extension
            Add-Copy (Join-Path $directory $name) (Join-Path $paks $name)
        }
    }
}
$backup = Join-Path $staging 'backup'
$receipt = [Collections.Generic.List[object]]::new()
foreach ($copy in $copies) {
    $relative = [IO.Path]::GetRelativePath($gameRoot, $copy.destination)
    $old = $null
    if (Test-Path -LiteralPath $copy.destination) {
        $old = Join-Path $backup $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $old) -Force | Out-Null
        Copy-Item -LiteralPath $copy.destination -Destination $old
    }
    $receipt.Add([ordered]@{ destination=$copy.destination; backup=$old; source=$copy.source;
        sha256=(Get-FileHash -LiteralPath $copy.source -Algorithm SHA256).Hash.ToLowerInvariant() })
}
# Write the recovery record before the first game-file replacement.
[ordered]@{ schema=1; solo_preview=[bool]$SoloPreview; files=@($receipt) } |
    ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $staging 'install-receipt.json') -Encoding utf8
foreach ($copy in $copies) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $copy.destination) -Force | Out-Null
    Copy-Item -LiteralPath $copy.source -Destination $copy.destination -Force
}
Write-Host "PWR runtime installed. Recovery receipt: $staging\install-receipt.json"
