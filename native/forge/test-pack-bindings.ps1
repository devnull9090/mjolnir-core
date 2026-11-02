<# Build and run the portable pack, layout, utility and snapshot tests. #>
param([string]$VcVars)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$objDir = Join-Path $here "obj\pack-bindings-test"
New-Item -ItemType Directory -Force $objDir | Out-Null
foreach ($name in @("test_pack_bindings", "test_layout_files", "test_layout_blf", "test_utility_properties", "test_forge_liveness")) {
$src = Join-Path $here "$name.c"
$exe = Join-Path $objDir "$name.exe"
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
if ($LASTEXITCODE -ne 0) { throw "$name test build failed" }
& $exe
if ($LASTEXITCODE -ne 0) { throw "$name tests failed" }
}
