#Requires -Version 7.0
<#
.SYNOPSIS
Build a map-owned Pelican with ten usable passenger seats for PWR.
.DESCRIPTION
Clones the installed game's vehicle tag and retains its model, physics and
Blueprint. Only passenger seat flags change; the pilot remains AI-only.
Writes containers to an output directory. Does not install or alter stock tags.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Paks,
    [Parameter(Mandatory=$true)][string]$OutDir,
    [string]$Mjolnir = '',
    [string]$Oodle = ''
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
if (-not $Mjolnir) { $Mjolnir = Join-Path $repo 'target\release\mjolnir.exe' }
foreach ($path in @($Paks, $Mjolnir)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing required input: $path" }
}
$destination = [IO.Path]::GetFullPath($OutDir)
if ([string]::Equals($destination, [IO.Path]::GetFullPath($Paks), [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Build to a staging directory; installation is a separate step.'
}
New-Item -ItemType Directory -Path $destination -Force | Out-Null
$arguments = @(
    'new-tag', '--paks', $Paks, '--group', 'vehicle',
    '--from', 'objects/Vehicles/human/pelican/pelican-vehicle',
    '--to', 'objects\mjolnir\warfare\pelican\pwr_pelican',
    '--out-dir', $destination, '--name', 'pakchunk971-MJOLNIRPWRPELICAN'
)
if ($Oodle) { $arguments += @('--oodle', $Oodle) }
# CU4 stock passenger indices 1..10 are l01..l05,r01..r05.
# Preserve allows-weapons, AI-passenger, disallow-AI-shooting and local-aiming.
# l04/l05/r04/r05 already have this exact set; the other six lose only 0x2000.
$passengerFlags = 'allows weapons | allow AI noncombatants | disallow AI shooting | local aiming'
foreach ($seat in 1..10) {
    $arguments += @('--set', "unit.seats[$seat].flags=$passengerFlags")
}
& $Mjolnir @arguments
if ($LASTEXITCODE -ne 0) { throw "Pelican clone failed: $LASTEXITCODE" }
$files = @(Get-ChildItem -LiteralPath $destination -File -Filter 'pakchunk971-MJOLNIRPWRPELICAN_P.*')
foreach ($extension in @('.utoc','.ucas','.pak')) {
    if (-not ($files | Where-Object Extension -eq $extension)) {
        throw "Missing built container $extension"
    }
}
$receipt = [ordered]@{
    schema_version = 1
    tag = 'objects\mjolnir\warfare\pelican\pwr_pelican'
    donor = 'objects\vehicles\human\pelican\pelican'
    passenger_seats = @('pelican_p_l01','pelican_p_l02','pelican_p_l03','pelican_p_l04','pelican_p_l05',
                         'pelican_p_r01','pelican_p_r02','pelican_p_r03','pelican_p_r04','pelican_p_r05')
    runtime_seat_and_replication_test = 'required'
    files = @($files | ForEach-Object {
        [ordered]@{ name=$_.Name; bytes=$_.Length; sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
    })
}
$receipt | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $destination 'pelican-build.json') -Encoding utf8
Write-Host "Staged PWR passenger Pelican: $destination"

