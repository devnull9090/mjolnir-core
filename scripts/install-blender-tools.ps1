<#
.SYNOPSIS
    Set up Blender for the MJOLNIR level pipeline.

.DESCRIPTION
    Installs two addons into the newest Blender found under Program Files and
    enables them persistently:

      - mjolnir_level (from this repo) — the level authoring panels + exporter
      - blender-mcp (downloaded from github.com/ahujasid/blender-mcp, MIT) —
        the socket bridge that lets Claude drive Blender live

    The blender-mcp MCP *server* half runs via `uvx blender-mcp` and is
    registered in the repo's .mcp.json; install uv (`pip install uv`) if
    `uvx` is not on PATH.

    Safe to re-run: both installs overwrite.

.EXAMPLE
    .\install-blender-tools.ps1
#>
param(
    [string]$BlenderExe
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

# blender-mcp's addon is a single file in its repo.
$mcpAddon = Join-Path $env:TEMP "blender_mcp_addon.py"
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/ahujasid/blender-mcp/main/addon.py" -OutFile $mcpAddon
Write-Host "  downloaded blender-mcp addon ($((Get-Item $mcpAddon).Length) bytes)"

# The mjolnir_level package installs as a zip.
$zip = Join-Path $env:TEMP "mjolnir_level.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path (Join-Path $RepoRoot "tools\blender\mjolnir_level") -DestinationPath $zip

$py = @"
import bpy
bpy.ops.preferences.addon_install(filepath=r'$mcpAddon', overwrite=True)
bpy.ops.preferences.addon_enable(module='blender_mcp_addon')
bpy.ops.preferences.addon_install(filepath=r'$zip', overwrite=True)
bpy.ops.preferences.addon_enable(module='mjolnir_level')
bpy.ops.wm.save_userpref()
print('MJOLNIR: both addons installed and enabled')
"@
$script = Join-Path $env:TEMP "mjolnir_blender_setup.py"
Set-Content -Path $script -Value $py -Encoding utf8

& $BlenderExe --background --python $script 2>&1 | Select-String -Pattern "MJOLNIR|Error|Traceback"

Write-Host ""
Write-Host "Done. In Blender: sidebar (N) -> MJOLNIR for level authoring,"
Write-Host "BlenderMCP -> 'Connect to MCP server' for Claude (or let Claude start it)."
