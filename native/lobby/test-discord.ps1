<# Build the RPC test variant; it only connects to its own mock pipe. #>
param([string]$VcVars, [string]$Python = "python")
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path $here "..\..")).Path
$objDir = Join-Path $here "obj\discord-test"
New-Item -ItemType Directory -Force $objDir | Out-Null
$src = Join-Path $here "discord_presence.c"
$dll = Join-Path $objDir "discord_presence_test.dll"
$compile = "cl /nologo /O2 /W4 /WX /MD /LD /DMJOLNIR_DISCORD_TEST `"$src`" /Fo`"$objDir\\`" /Fe:`"$dll`" /link /NOLOGO /Brepro /IMPLIB:`"$objDir\discord_presence_test.lib`""
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
if ($LASTEXITCODE -ne 0) { throw "Discord test build failed" }
& $Python (Join-Path $repo "tools\tests\test_discord_rpc.py") $dll
if ($LASTEXITCODE -ne 0) { throw "Discord RPC tests failed" }
