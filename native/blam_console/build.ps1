<#
.SYNOPSIS
    Build the MJOLNIR Blam Console native DLL with MSVC.

.DESCRIPTION
    Compiles mjolnir_blam_console.c into mods\MJOLNIRBlamConsole\native\ so the
    Lua mod next to it can load it with package.loadlib.

    Finds the compiler three ways, in order: `cl` already on PATH (a Developer
    PowerShell, or CI after msvc-dev-cmd), vswhere, then the Community
    edition's default location. Needs the x64 C++ toolset from Visual Studio
    2022 or the Build Tools.

    The link is reproducible (/Brepro): the same source and toolset give the
    same bytes, so a reviewer can rebuild the artifact CI shipped and compare
    hashes.

.PARAMETER VcVars
    Path to vcvars64.bat, if the automatic search should be skipped.

.EXAMPLE
    .\native\blam_console\build.ps1
#>
param(
    [string]$VcVars
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Resolve-Path (Join-Path $here "..\..")
$outDir = Join-Path $repo "mods\MJOLNIRBlamConsole\native"
$objDir = Join-Path $here "obj"
New-Item -ItemType Directory -Force $outDir | Out-Null
New-Item -ItemType Directory -Force $objDir | Out-Null

$src = Join-Path $here "mjolnir_blam_console.c"
$dll = Join-Path $outDir "mjolnir_blam_console.dll"

# /MD: share the process's ucrtbase, the same CRT the simulation DLL uses.
$compile = "cl /nologo /O2 /W4 /WX /MD /LD `"$src`" /Fo`"$objDir\\`" /Fe:`"$dll`" /link /NOLOGO /Brepro /IMPLIB:`"$objDir\mjolnir_blam_console.lib`""

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
    if (-not $VcVars) {
        $VcVars = "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
    }
    if (-not (Test-Path $VcVars)) {
        throw "no MSVC x64 toolset found (looked for cl on PATH, vswhere, and $VcVars); pass -VcVars"
    }
    Write-Host "using $VcVars"
    cmd /c "`"$VcVars`" >nul && $compile"
}
if ($LASTEXITCODE -ne 0) { throw "cl failed with exit code $LASTEXITCODE" }

$hash = (Get-FileHash $dll -Algorithm SHA256).Hash.ToLower()
Write-Host "built $dll"
Write-Host "sha256 $hash"
