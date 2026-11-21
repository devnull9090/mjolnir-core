<# Build and run portable warfare insertion, descent, ownership and lifecycle tests. #>
param([string]$VcVars)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
& python (Join-Path $here "generate_warfare_layout.py") --check
if ($LASTEXITCODE -ne 0) { throw "Warfare layout is stale" }
$objDir = Join-Path $here "obj\warfare-test"
New-Item -ItemType Directory -Force $objDir | Out-Null
$src = Join-Path $here "test_warfare.c"
$exe = Join-Path $objDir "test_warfare.exe"
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
if ($LASTEXITCODE -ne 0) { throw "Warfare test build failed" }
& $exe
if ($LASTEXITCODE -ne 0) { throw "Warfare tests failed" }
