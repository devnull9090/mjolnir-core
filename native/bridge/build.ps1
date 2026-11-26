<#
.SYNOPSIS
    Compiles mjolnir_bridge.c into mods\MJOLNIRBridge\native\, the named pipe
    the bridge mod answers on (mods/MJOLNIRBridge/Scripts/main.lua).
.PARAMETER VcVars
    vcvars64.bat to use when cl.exe is not already on PATH.
#>
param(
    [string]$VcVars
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Resolve-Path (Join-Path $here "..\..")
$outDir = Join-Path $repo "mods\MJOLNIRBridge\native"
$objDir = Join-Path $here "obj"
New-Item -ItemType Directory -Force $outDir | Out-Null
New-Item -ItemType Directory -Force $objDir | Out-Null

$src = Join-Path $here "mjolnir_bridge.c"
$dll = Join-Path $outDir "mjolnir_bridge.dll"

# /MD: share the process's ucrtbase, the same CRT the simulation DLL uses.
$compile = "cl /nologo /O2 /W4 /WX /MD /LD `"$src`" /Fo`"$objDir\\`" /Fe:`"$dll`" /link /NOLOGO /Brepro /IMPLIB:`"$objDir\mjolnir_bridge.lib`""

if (-not $VcVars -and (Get-Command cl.exe -ErrorAction SilentlyContinue)) {
    Write-Host "using cl from PATH: $((Get-Command cl.exe).Source)"
    cmd /c $compile
}
else {
    if (-not $VcVars) {
        $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
        if (Test-Path $vswhere) {
            $install = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2>$null
            if ($install) { $VcVars = Join-Path $install "VC\Auxiliary\Build\vcvars64.bat" }
        }
    }
    if (-not $VcVars -or -not (Test-Path $VcVars)) { throw "no MSVC x64 toolset found; pass -VcVars" }
    cmd /c "`"$VcVars`" >nul && $compile"
}
if ($LASTEXITCODE -ne 0) { throw "cl failed with exit code $LASTEXITCODE" }
$hash = (Get-FileHash $dll -Algorithm SHA256).Hash.ToLower()
Write-Host "built $dll"
Write-Host "sha256 $hash"
