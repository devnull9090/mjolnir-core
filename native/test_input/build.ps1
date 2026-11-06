<#
.SYNOPSIS
    Build the MJOLNIR test input DLL with MSVC.

.DESCRIPTION
    Compiles mjolnir_test_input.c into mods\MJOLNIRBridge\native\, where
    scripts\install-bridge.ps1 picks it up. Nothing loads the DLL unless a test
    asks for it (game_input does), and neither CI nor a release builds it.

    Finds the compiler like the other native builds: `cl` already on PATH,
    vswhere, then the Community edition's default location.

.PARAMETER Test
    Also build and run test_test_input.c. It maps the exe on disk to check that
    ReadInput and its vtable slot are still found, so run it after a game
    update. It reads the game's files and never touches a running game.

.PARAMETER Exe
    The exe for -Test. Defaults to a default Steam install.

.PARAMETER VcVars
    Path to vcvars64.bat, if the automatic search should be skipped.

.EXAMPLE
    .\native\test_input\build.ps1 -Test
#>
param(
    [switch]$Test,
    [string]$Exe = "C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved\Meteorite\Binaries\Win64\HaloCampaignEvolved.exe",
    [string]$VcVars
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Resolve-Path (Join-Path $here "..\..")
$outDir = Join-Path $repo "mods\MJOLNIRBridge\native"
$objDir = Join-Path $here "obj"
New-Item -ItemType Directory -Force $outDir | Out-Null
New-Item -ItemType Directory -Force $objDir | Out-Null

$src = Join-Path $here "mjolnir_test_input.c"
$dll = Join-Path $outDir "mjolnir_test_input.dll"
$testSrc = Join-Path $here "test_test_input.c"
$testExe = Join-Path $objDir "test_test_input.exe"

# /MD: share the process's ucrtbase, the same CRT the simulation DLL uses.
$compile = "cl /nologo /O2 /W4 /WX /MD /LD `"$src`" /Fo`"$objDir\\`" /Fe:`"$dll`" /link /NOLOGO /Brepro /IMPLIB:`"$objDir\mjolnir_test_input.lib`""
if ($Test) {
    $compile += " && cl /nologo /O2 /W4 /WX /MD `"$testSrc`" /Fo`"$objDir\\`" /Fe:`"$testExe`" /link /NOLOGO"
}

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

if ($Test) {
    & $testExe $Exe
    if ($LASTEXITCODE -ne 0) { throw "test_test_input failed" }
}
