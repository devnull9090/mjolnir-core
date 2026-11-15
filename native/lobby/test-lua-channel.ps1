<# Build and run the Lua channel tests: lua_channel.h against a stand-in for UE4SS's LuaMadeSimple::Lua built from the same C++ declarations. #>
param([string]$VcVars)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$objDir = Join-Path $here "obj\lua-channel-test"
New-Item -ItemType Directory -Force $objDir | Out-Null
$fakeSrc = Join-Path $here "test_lua_channel_fake.cpp"
$fake = Join-Path $objDir "fake_ue4ss.dll"
$src = Join-Path $here "test_lua_channel.c"
$exe = Join-Path $objDir "test_lua_channel.exe"
$compileFake = "cl /nologo /std:c++17 /EHsc /O2 /W4 /WX /MD /LD `"$fakeSrc`" /Fo`"$objDir\\`" /Fe:`"$fake`" /link /NOLOGO /IMPLIB:`"$objDir\fake_ue4ss.lib`" /Brepro"
$compileTest = "cl /nologo /std:c11 /O2 /W4 /WX /MD `"$src`" /Fo`"$objDir\\`" /Fe:`"$exe`" /link /NOLOGO /Brepro"
if (-not $VcVars -and -not (Get-Command cl.exe -ErrorAction SilentlyContinue)) {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path $vswhere) {
        $install = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if ($install) { $VcVars = Join-Path $install "VC\Auxiliary\Build\vcvars64.bat" }
    }
    if (-not $VcVars -or -not (Test-Path $VcVars)) { throw "MSVC x64 toolset not found" }
}
foreach ($compile in @($compileFake, $compileTest)) {
    if ($VcVars) { cmd /c "`"$VcVars`" >nul && $compile" } else { cmd /c $compile }
    if ($LASTEXITCODE -ne 0) { throw "Lua channel test build failed" }
}
& $exe $fake
if ($LASTEXITCODE -ne 0) { throw "Lua channel tests failed" }
