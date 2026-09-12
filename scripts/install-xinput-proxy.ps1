<#
.SYNOPSIS
    Install (or remove) the xinput1_4 proxy that drives the local bot player.

.DESCRIPTION
    Drops the built proxy into the game's Win64 folder as xinput1_4.dll, and
    copies the real system DLL beside it as xinput1_4_orig.dll for pass-through.
    The game ships no xinput1_4.dll of its own (it loads the System32 copy), so
    the app-directory copy shadows it cleanly. Nothing shipped is modified;
    -Uninstall removes both files.

    Build the proxy first:
        cargo build --release --manifest-path native/xinput-proxy/Cargo.toml

.EXAMPLE
    .\scripts\install-xinput-proxy.ps1
    .\scripts\install-xinput-proxy.ps1 -Uninstall
#>
param(
    [switch]$Uninstall,
    [string]$GameDir
)
$ErrorActionPreference = "Stop"

function Find-GameBinDir {
    param([string]$Override)
    if ($Override) { return $Override }
    $candidates = @(
        "C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved",
        "C:\Program Files\Steam\steamapps\common\Halo Campaign Evolved",
        "D:\SteamLibrary\steamapps\common\Halo Campaign Evolved",
        "E:\SteamLibrary\steamapps\common\Halo Campaign Evolved"
    )
    foreach ($c in $candidates) {
        $bin = Join-Path $c "Meteorite\Binaries\Win64"
        if (Test-Path (Join-Path $bin "HaloCampaignEvolved.exe")) { return $bin }
    }
    throw "Could not find the game. Pass -GameDir '<...>\Meteorite\Binaries\Win64'."
}

$bin = Find-GameBinDir -Override $GameDir
$proxyDest = Join-Path $bin "xinput1_4.dll"
$origDest  = Join-Path $bin "xinput1_4_orig.dll"

if ($Uninstall) {
    foreach ($f in @($proxyDest, $origDest)) {
        if (Test-Path $f) { Remove-Item $f -Force; Write-Output "removed $f" }
        else { Write-Output "absent  $f" }
    }
    Write-Output "Done. The game falls back to the System32 xinput1_4.dll."
    return
}

$built = Join-Path $PSScriptRoot "..\native\xinput-proxy\target\release\xinput1_4.dll"
if (-not (Test-Path $built)) {
    throw "Proxy not built. Run: cargo build --release --manifest-path native/xinput-proxy/Cargo.toml"
}

# Guard: never let a stale proxy become the 'real' pass-through target. Only
# seed xinput1_4_orig.dll from the genuine System32 DLL, and only if absent.
if (-not (Test-Path $origDest)) {
    $system = Join-Path $env:WINDIR "System32\xinput1_4.dll"
    if (-not (Test-Path $system)) { throw "System xinput1_4.dll not found at $system" }
    Copy-Item $system $origDest -Force
    Write-Output "seeded  $origDest (from System32)"
} else {
    Write-Output "kept    $origDest (already present)"
}

Copy-Item $built $proxyDest -Force
Write-Output "installed $proxyDest"

$padDir = Join-Path $bin "ue4ss\mjolnir-bridge"
if (-not (Test-Path $padDir)) { New-Item -ItemType Directory -Force -Path $padDir | Out-Null }
Write-Output ""
Write-Output "Proxy installed. Synthetic pad = XInput user index 1 (override with MJOLNIR_PAD_INDEX)."
Write-Output "Command file: $padDir\pad1.txt"
Write-Output "Restart the game for it to load the proxy."
