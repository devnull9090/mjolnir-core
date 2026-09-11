# Start GhidraMCP's headless HTTP server (no Ghidra GUI) against a binary or a
# Ghidra project, for `bridge-mcp-ghidra` / curl to talk to on port 8089.
#
#   tools\re\ghidra_mcp_headless.ps1 -File C:\ghidra_proj\cu4\HaloSimulation_tag_release.dll
#   tools\re\ghidra_mcp_headless.ps1 -Project C:\ghidra_proj\HCE_Analysis -Program CU4/HaloCampaignEvolved.exe
#
# Needs the GhidraMCP extension jar (bethington/ghidra-mcp release
# `GhidraMCP-<ver>.zip`, unpacked) and a Ghidra install; both default to where
# this box keeps them. A headless analysis (`analyzeHeadless`) holds the
# project lock, so open a project only once that has finished; `-File` imports
# into a temporary project and analyses on request (`POST /run_analysis`).
param(
    [string]$File,
    [string]$Project,
    [string]$Program,
    [int]$Port = 8089,
    [string]$Ghidra = $(if ($env:GHIDRA_INSTALL_DIR) { $env:GHIDRA_INSTALL_DIR } else { "C:\tools\ghidra_12.1.3_PUBLIC" }),
    [string]$McpJar = "$env:APPDATA\ghidra\ghidra_12.1.3_PUBLIC\Extensions\GhidraMCP\lib\GhidraMCP-6.0.0.jar",
    [string]$Heap = "6g"
)
$jars = Get-ChildItem -Path "$Ghidra\Ghidra" -Recurse -Filter *.jar |
    Where-Object { $_.FullName -match '\\lib\\' } | ForEach-Object { $_.FullName }
$cp = "$McpJar;" + ($jars -join ';')
$args = @("--port", "$Port")
if ($File) { $args += @("--file", $File) }
if ($Project) { $args += @("--project", $Project) }
if ($Program) { $args += @("--program", $Program) }
Set-Location $Ghidra
& java "-Xmx$Heap" -cp $cp com.xebyte.headless.GhidraMCPHeadlessServer @args
