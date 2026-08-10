# Builds the Chocolatey package for the `mjolnir` command line, and optionally
# pushes it to chocolatey.org.
#
#   ./packaging/chocolatey/pack.ps1 -ZipDir artifacts            # build only
#   ./packaging/chocolatey/pack.ps1 -ZipDir artifacts -Push      # build + push
#
# Run without -Push locally to inspect the .nupkg before anything is published.
# Called by the `chocolatey` job in .github/workflows/release-cli.yml, which
# supplies VERSION, SHA256 and CHOCO_API_KEY through the environment.
[CmdletBinding()]
param(
  # Directory holding the release zip built by the workflow.
  [string]$ZipDir = "artifacts",
  # Version to package. Defaults to the workflow's VERSION.
  [string]$Version = $env:VERSION,
  # SHA-256 of the zip, recorded in VERIFICATION.txt for the moderators.
  [string]$Sha256 = $env:SHA256,
  [switch]$Push
)

$ErrorActionPreference = "Stop"
$here = $PSScriptRoot

if ([string]::IsNullOrWhiteSpace($Version)) {
  throw "No version. Pass -Version or set VERSION."
}

$zipName = "mjolnir-$Version-x86_64-pc-windows-msvc.zip"
$zip = Join-Path $ZipDir $zipName
if (-not (Test-Path $zip)) {
  throw "$zip not found. It is the archive the build job produced; pass -ZipDir to point at it."
}

# Rebuilt from scratch every run: tools/ holds an unpacked binary, and a stale
# one from a previous version would be packaged silently.
$tools = Join-Path $here "tools"
if (Test-Path $tools) { Remove-Item $tools -Recurse -Force }
New-Item -ItemType Directory -Path $tools | Out-Null

$unpack = Join-Path $env:TEMP "mjolnir-choco-$Version"
if (Test-Path $unpack) { Remove-Item $unpack -Recurse -Force }
Expand-Archive -Path $zip -DestinationPath $unpack

$exe = Get-ChildItem -Path $unpack -Filter "mjolnir.exe" -Recurse | Select-Object -First 1
if (-not $exe) { throw "no mjolnir.exe inside $zip" }
# Everything else is taken relative to the binary rather than searched for
# again, so this cannot assemble a package out of two different archives.
$root = $exe.Directory.FullName

Copy-Item $exe.FullName (Join-Path $tools "mjolnir.exe")
Copy-Item (Join-Path $root "LICENSE") (Join-Path $tools "LICENSE.txt")

# `mjolnir compile` reads the recovered function table, and looks for it next to
# its own executable — which for a Chocolatey install is the package's tools
# directory, not the shim on PATH.
$defs = Join-Path $tools "defs\hce"
New-Item -ItemType Directory -Path $defs -Force | Out-Null
Copy-Item (Join-Path $root "defs\hce\scripting.json") $defs

# Required for any package that embeds a binary: it tells a moderator, and
# anyone else, how to confirm the .exe in this package is the one the release
# published rather than something substituted on the way.
$actual = (Get-FileHash (Join-Path $tools "mjolnir.exe") -Algorithm SHA256).Hash.ToLower()
@"
VERIFICATION

Verification is intended to assist the Chocolatey moderators and any user
inspecting this package.

mjolnir.exe is embedded here from the official release archive, built in public
CI from the sources in this repository:

  https://github.com/devnull9090/mjolnir-core/releases/tag/cli-v$Version

Download that release's $zipName and compare:

  SHA-256 of $zipName    $Sha256
  SHA-256 of mjolnir.exe  $actual

  Get-FileHash .\$zipName -Algorithm SHA256

The checksum of the archive is also published in the release notes, in
checksums-cli-v$Version.txt on the release, and at
https://releases.mjolnircore.com/cli/$Version/checksums.txt

LICENSE.txt in this directory is the MIT license the software is distributed
under, copied verbatim from the release archive.
"@ | Out-File (Join-Path $tools "VERIFICATION.txt") -Encoding utf8

$out = Join-Path $here "out"
if (Test-Path $out) { Remove-Item $out -Recurse -Force }
New-Item -ItemType Directory -Path $out | Out-Null

choco pack (Join-Path $here "mjolnir-cli.nuspec") --version $Version --out $out
if ($LASTEXITCODE -ne 0) { throw "choco pack failed" }

$nupkg = Get-ChildItem -Path $out -Filter "*.nupkg" | Select-Object -First 1
Write-Host "packed $($nupkg.FullName)"

if (-not $Push) {
  Write-Host "not pushing (-Push was not given)"
  exit 0
}

if ([string]::IsNullOrWhiteSpace($env:CHOCO_API_KEY)) {
  throw "CHOCO_API_KEY is not set; cannot push."
}
choco apikey --source https://push.chocolatey.org/ --api-key $env:CHOCO_API_KEY | Out-Null
choco push $nupkg.FullName --source https://push.chocolatey.org/
if ($LASTEXITCODE -ne 0) { throw "choco push failed" }
Write-Host "pushed mjolnir-cli $Version"
