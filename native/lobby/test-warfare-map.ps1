param([string]$VcVars)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$objDir = Join-Path $here 'obj\warfare-map-test'
New-Item -ItemType Directory -Force $objDir | Out-Null
$src = Join-Path $here 'test_warfare_map.c'
$exe = Join-Path $objDir 'test_warfare_map.exe'
$object = Join-Path $objDir 'test_warfare_map.obj'
$compile = "cl /nologo /std:c11 /O2 /W4 /WX /MD `"$src`" /Fo`"$object`" /Fe:`"$exe`" /link /NOLOGO /Brepro"
if (-not $VcVars -and (Get-Command cl.exe -ErrorAction SilentlyContinue)) { cmd /c $compile }
else {
    if (-not $VcVars) {
        $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
        $install = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if ($install) { $VcVars = Join-Path $install 'VC\Auxiliary\Build\vcvars64.bat' }
    }
    if (-not $VcVars -or -not (Test-Path $VcVars)) { throw 'MSVC x64 toolset not found' }
    cmd /c "`"$VcVars`" >nul && $compile"
}
if ($LASTEXITCODE -ne 0) { throw 'Warfare map test build failed' }
& $exe
if ($LASTEXITCODE -ne 0) { throw 'Warfare map tests failed' }
