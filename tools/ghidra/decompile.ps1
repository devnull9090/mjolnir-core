<#
.SYNOPSIS
    Decompile functions (or list references) in an analysed Ghidra project, headless.

.DESCRIPTION
    Wraps analyzeHeadless with DecompileRvas.java / ListRefs.java. The program
    must have been imported and analysed once, e.g. for the simulation DLL:

        analyzeHeadless.bat C:\ghidra_proj\sim HaloSim -import <dll> -max-cpu 24

.EXAMPLE
    .\decompile.ps1 -Out C:\tmp\dec 4b7db0 4b7440
    .\decompile.ps1 -Out C:\tmp\dec -Refs ca2824 ca2ef0
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Mandatory)] [string]$Out,
    [switch]$Refs,
    [string]$ProjectDir = "C:\ghidra_proj\sim",
    [string]$Project = "HaloSim",
    [string]$Program = "HaloSimulation_tag_release.dll",
    [string]$Ghidra = "C:\Tools\ghidra_12.1.3_PUBLIC",
    [Parameter(ValueFromRemainingArguments)] [string[]]$Rvas
)
$env:GHIDRA_HEADLESS_MAXMEM = "24G"
if (-not $env:JAVA_HOME) { $env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-21.0.11.10-hotspot" }
$script = if ($Refs) { "ListRefs.java" } else { "DecompileRvas.java" }
$log = Join-Path $Out "headless.log"
New-Item -ItemType Directory -Path $Out -Force | Out-Null
& "$Ghidra\support\analyzeHeadless.bat" $ProjectDir $Project -process $Program -noanalysis -readOnly `
    -scriptPath (Join-Path $PSScriptRoot "scripts") -postScript $script $Out @Rvas *> $log
Get-Content $log | Select-String "decompiled|refs to|no function|ERROR|Exception" | ForEach-Object { $_.Line.Trim() }
