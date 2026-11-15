<#
.SYNOPSIS
    Set up Blender for the MJOLNIR level pipeline.

.DESCRIPTION
    Installs two addons into the newest Blender found under Program Files and
    enables them persistently:

      - mjolnir_level (from this repo) — the level authoring panels + exporter
      - MCP for Blender (the addon bundled with the pinned MCP package, MIT)
        — the socket bridge used for live Blender authoring

    The MCP server version matches .mcp.json. Install uv from Astral if
    `uvx` is not on PATH. Updating the server and addon together avoids
    incompatible protocol versions.

    Safe to re-run: both installs overwrite.

.EXAMPLE
    .\install-blender-tools.ps1
#>
param(
    [string]$BlenderExe,
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$McpVersion = '2.2.7'
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path "$PSScriptRoot\.."

if (-not $BlenderExe) {
    $found = Get-ChildItem "C:\Program Files\Blender Foundation" -Directory -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | Select-Object -First 1
    if (-not $found) { throw "Blender not found under Program Files; pass -BlenderExe" }
    $BlenderExe = Join-Path $found.FullName "blender.exe"
}
Write-Host "Blender: $BlenderExe"

# Use the release's bundled addon, never an unrelated moving main-branch file.
if (-not (Get-Command uvx -ErrorAction SilentlyContinue)) { throw 'Install uv from https://docs.astral.sh/uv/ first.' }
$blenderVersionLine = (& $BlenderExe --version | Select-Object -First 1)
if ($blenderVersionLine -notmatch '^Blender (\d+\.\d+)') { throw "Cannot identify Blender: $blenderVersionLine" }
$addons = Join-Path $env:APPDATA "Blender Foundation\Blender\$($Matches[1])\scripts\addons"
$previousEncoding = $env:PYTHONIOENCODING
try {
    $env:PYTHONIOENCODING = 'utf-8'
    & uvx --from "mcp-for-blender==$McpVersion" mcp-for-blender install-addon --addons-dir $addons
    if ($LASTEXITCODE -ne 0) { throw 'MCP addon installation failed.' }
} finally {
    $env:PYTHONIOENCODING = $previousEncoding
}

# The mjolnir_level package installs as a zip.
$setupDir = Join-Path $env:TEMP ('mjolnir-blender-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $setupDir | Out-Null
$zip = Join-Path $setupDir 'mjolnir_level.zip'
Compress-Archive -Path (Join-Path $RepoRoot "tools\blender\mjolnir_level") -DestinationPath $zip

$py = @"
import bpy
if 'blender_mcp_addon' in bpy.context.preferences.addons:
    bpy.ops.preferences.addon_disable(module='blender_mcp_addon')
bpy.ops.preferences.addon_enable(module='blender_mcp')
bpy.ops.preferences.addon_install(filepath=r'$zip', overwrite=True)
bpy.ops.preferences.addon_enable(module='mjolnir_level')
bpy.ops.wm.save_userpref()
print('MJOLNIR: both addons installed and enabled')
"@
$script = Join-Path $setupDir 'mjolnir_blender_setup.py'
Set-Content -Path $script -Value $py -Encoding utf8

& $BlenderExe --background --python-exit-code 1 --python $script 2>&1 | Select-String -Pattern "MJOLNIR|Error|Traceback"
if ($LASTEXITCODE -ne 0) { throw 'Blender could not enable the authoring addons.' }

Write-Host ""
Write-Host "Done. In Blender: sidebar (N) -> MJOLNIR for level authoring,"
Write-Host "MCP for Blender starts its server when Blender opens."
