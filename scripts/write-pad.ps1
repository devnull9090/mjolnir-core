<#
.SYNOPSIS
    Write one pad state to the bot's command file (read by the xinput proxy).

.DESCRIPTION
    Emits a single line: "<ttl> <lx> <ly> <rx> <ry> <lt> <rt> <buttons_hex>".
    Sticks are -1..1, triggers 0..1, buttons a hex XInput mask. The proxy treats
    the file as stale once it is older than <ttl> ms and reverts the pad to
    neutral, so a single write with -Ttl 3000 makes the bot hold that input for
    ~3 seconds and then stop on its own -- no polling loop needed.

    Left stick moves; right stick aims. Button bits (hex): A=1000 B=2000
    X=4000 Y=8000 LB=0100 RB=0200 START=0010 BACK=0020 DPAD U/D/L/R=0001/2/4/8.

.EXAMPLE
    # Walk forward for 3 seconds
    .\scripts\write-pad.ps1 -LY 1.0 -Ttl 3000
    # Neutral (stop now)
    .\scripts\write-pad.ps1
    # Forward while firing
    .\scripts\write-pad.ps1 -LY 1.0 -RT 1.0 -Buttons 0000 -Ttl 2000
#>
param(
    [double]$LX = 0,
    [double]$LY = 0,
    [double]$RX = 0,
    [double]$RY = 0,
    [double]$LT = 0,
    [double]$RT = 0,
    [string]$Buttons = "0000",
    [int]$Ttl = 500,
    [string]$PadFile,
    [string]$GameDir
)
$ErrorActionPreference = "Stop"

if (-not $PadFile) {
    $bin = $GameDir
    if (-not $bin) {
        $candidates = @(
            "C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved",
            "C:\Program Files\Steam\steamapps\common\Halo Campaign Evolved",
            "D:\SteamLibrary\steamapps\common\Halo Campaign Evolved",
            "E:\SteamLibrary\steamapps\common\Halo Campaign Evolved"
        )
        foreach ($c in $candidates) {
            $b = Join-Path $c "Meteorite\Binaries\Win64"
            if (Test-Path (Join-Path $b "HaloCampaignEvolved.exe")) { $bin = $b; break }
        }
    }
    if (-not $bin) { throw "Could not find the game. Pass -PadFile or -GameDir." }
    $padDir = Join-Path $bin "ue4ss\mjolnir-bridge"
    if (-not (Test-Path $padDir)) { New-Item -ItemType Directory -Force -Path $padDir | Out-Null }
    $PadFile = Join-Path $padDir "pad1.txt"
}

$ci = [System.Globalization.CultureInfo]::InvariantCulture
$line = "{0} {1} {2} {3} {4} {5} {6} {7}" -f `
    $Ttl,
    $LX.ToString($ci), $LY.ToString($ci), $RX.ToString($ci), $RY.ToString($ci),
    $LT.ToString($ci), $RT.ToString($ci), $Buttons
# ASCII, no BOM, no trailing newline needed (proxy splits on whitespace).
[System.IO.File]::WriteAllText($PadFile, $line, [System.Text.Encoding]::ASCII)
Write-Output "wrote [$line] -> $PadFile"
