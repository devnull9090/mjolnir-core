# Pack this machine's working MJOLNIR install into one zip for a second test
# PC: the UE4SS loader, every mod, the installed maps and the MJOLNIR
# containers, exactly as they run here, plus install_test_bundle.ps1 and a
# README (docs/two_pc_test.md). Logs, crash dumps and run-state files stay
# behind.
#
#   powershell -File tools/mp/make_test_bundle.ps1 [-Out C:\haloce\twopc]
param(
    [string]$Game = "C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved",
    [string]$Out = "C:\haloce\twopc"
)
$ErrorActionPreference = "Stop"
$win64 = Join-Path $Game "Meteorite\Binaries\Win64"
$paks = Join-Path $Game "Meteorite\Content\Paks"
$ue4ss = Join-Path $win64 "ue4ss"
$stamp = Get-Date -Format "yyyyMMdd-HHmm"
$stage = Join-Path $Out "mjolnir-test-$stamp"
if (Test-Path $stage) { throw "$stage already exists" }
New-Item -ItemType Directory -Force (Join-Path $stage "Win64\ue4ss") | Out-Null
New-Item -ItemType Directory -Force (Join-Path $stage "Paks") | Out-Null

Copy-Item (Join-Path $win64 "dwmapi.dll") (Join-Path $stage "Win64")
foreach ($f in "UE4SS.dll", "UE4SS-settings.ini") { Copy-Item (Join-Path $ue4ss $f) (Join-Path $stage "Win64\ue4ss") }
foreach ($d in "UE4SS_Signatures", "Mods", "MJOLNIRMaps") {
    Copy-Item -Recurse (Join-Path $ue4ss $d) (Join-Path $stage "Win64\ue4ss\$d")
}
# Run state and logs are this machine's.
Get-ChildItem -Recurse (Join-Path $stage "Win64\ue4ss\Mods") -Include *.log, running.txt, pending_variant.txt, last_game.txt, last_match.txt |
    Remove-Item -Force
Get-ChildItem $paks -Filter "*MJOLNIR*" | Copy-Item -Destination (Join-Path $stage "Paks")

$repo = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Copy-Item (Join-Path $PSScriptRoot "install_test_bundle.ps1") $stage
Copy-Item (Join-Path $repo "docs\two_pc_test.md") (Join-Path $stage "README.md")

$zip = "$stage.zip"
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -CompressionLevel Optimal
$n = (Get-ChildItem -Recurse -File $stage).Count
"bundle: $zip ($n files, {0:N0} MB)" -f ((Get-Item $zip).Length / 1MB)
