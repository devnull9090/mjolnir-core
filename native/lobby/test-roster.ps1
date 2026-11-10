<# Build and run the portable roster tests: the tables it reads and the packed form it hands Lua. #>
param([string]$VcVars)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$objDir = Join-Path $here "obj\roster-test"
New-Item -ItemType Directory -Force $objDir | Out-Null
$src = Join-Path $here "test_roster.c"
$exe = Join-Path $objDir "test_roster.exe"
$compile = "cl /nologo /std:c11 /O2 /W4 /WX /MD `"$src`" /Fo`"$objDir\\`" /Fe:`"$exe`" /link /NOLOGO /Brepro"
if (-not $VcVars -and (Get-Command cl.exe -ErrorAction SilentlyContinue)) {
    cmd /c $compile
} else {
    if (-not $VcVars) {
        $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
        if (Test-Path $vswhere) {
            $install = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
            if ($install) { $VcVars = Join-Path $install "VC\Auxiliary\Build\vcvars64.bat" }
        }
    }
    if (-not $VcVars -or -not (Test-Path $VcVars)) { throw "MSVC x64 toolset not found" }
    cmd /c "`"$VcVars`" >nul && $compile"
}
if ($LASTEXITCODE -ne 0) { throw "Roster test build failed" }
# The packed roster against the fixture tools/tests/test_roster.lua reads
# (MJOLNIRHud's reader): `test_roster.exe --write <fixture>` makes it again.
$fixture = Join-Path $here "..\..\tools\tests\fixtures\roster_eight_players.bin"
& $exe $fixture
if ($LASTEXITCODE -ne 0) { throw "Roster tests failed" }
