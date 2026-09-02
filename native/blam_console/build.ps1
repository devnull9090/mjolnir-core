<#
.SYNOPSIS
    Build the MJOLNIR Blam Console native DLL with MSVC.

.DESCRIPTION
    Compiles mjolnir_blam_console.c into mods\MJOLNIRBlamConsole\native\ so the
    Lua mod next to it can load it with package.loadlib. Needs Visual Studio
    2022 Build Tools (or Community) with the x64 C++ toolset.

.PARAMETER VcVars
    Path to vcvars64.bat. Defaults to the Community edition's location.

.EXAMPLE
    .\native\blam_console\build.ps1
#>
param(
    [string]$VcVars = "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Resolve-Path (Join-Path $here "..\..")
$outDir = Join-Path $repo "mods\MJOLNIRBlamConsole\native"
New-Item -ItemType Directory -Force $outDir | Out-Null

if (-not (Test-Path $VcVars)) {
    throw "vcvars64.bat not found at $VcVars; pass -VcVars with the path from your Visual Studio install"
}

$objDir = Join-Path $here "obj"
New-Item -ItemType Directory -Force $objDir | Out-Null
$src = Join-Path $here "mjolnir_blam_console.c"
$dll = Join-Path $outDir "mjolnir_blam_console.dll"

# /MD: share the process's ucrtbase, the same CRT the simulation DLL uses.
$cmd = "`"$VcVars`" >nul && cl /nologo /O2 /W4 /MD /LD `"$src`" /Fo`"$objDir\\`" /Fe:`"$dll`" /link /NOLOGO /IMPLIB:`"$objDir\mjolnir_blam_console.lib`""
cmd /c $cmd
if ($LASTEXITCODE -ne 0) { throw "cl failed with exit code $LASTEXITCODE" }
Write-Host "built $dll"
