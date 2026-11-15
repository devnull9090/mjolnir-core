param(
    [string]$Stages='foliage,swap,collision',
    [switch]$RefreshProbes,
    [switch]$NoMasters,
    [string]$LogSuffix=''
)
$ErrorActionPreference='Stop'
if ($LogSuffix -and $LogSuffix -notmatch '^[a-zA-Z0-9_-]+$') { throw 'Invalid log suffix' }
$allowed=@('land','foliage','swap','collision','editor','cook','bake','assemble')
$selected=@($Stages.Split(',') | Where-Object { $_ })
if (!$RefreshProbes -and (!$selected.Count -or @($selected | Where-Object { $_ -notin $allowed }).Count)) {
    throw 'Choose only land, foliage, swap, collision, editor, cook, bake, assemble. Installation is a separate reviewed operation.'
}
$repo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../..'))
$world='C:/haloce/ce_conversions/warfare/PWR/expansion/world-bases-v1'
$logRoot=Join-Path $repo 'out/pwr/base-runtime/pipeline/logs'
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
Set-Location -LiteralPath $repo
$env:HCE_GAME='C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved'
$env:HCE_PAKS=Join-Path $env:HCE_GAME 'Meteorite/Content/Paks'
$env:MJOLNIR=(Join-Path $repo 'out/pwr/toolchain-v3/mjolnir.exe').Replace('\','/')
$env:MJOLNIR_DEBUG=$env:MJOLNIR
$env:MJOLNIR_EXAMPLES=(Join-Path $repo 'target/release/examples').Replace('\','/')
$env:EXAMPLES=$env:MJOLNIR_EXAMPLES
$env:OODLE='C:/Program Files/Epic Games/UE_5.5/Engine/Binaries/DotNET/AutomationTool/oo2core_9_win64.dll'
$env:PYTHONUTF8='1'
if (!(Test-Path -LiteralPath $env:MJOLNIR)) { throw "Missing pinned collision/bake CLI: $env:MJOLNIR" }
$tail=if ($LogSuffix) { '-'+$LogSuffix } else { '' }
if ($RefreshProbes) {
    $label='refresh-native-probes'
    $pipelineArgs=@('levels/warfare/pwr/refresh_native_probes.py','--world',$world,
        '--out','out/pwr/base-runtime/native-refresh',
        '--vehicle-spawn-policy','levels/warfare/pwr/vehicle-spawn-policy-v1.json',
        '--architecture-contract',($world+'/source-build/base-architecture-contract.json'),
        '--additional-probe-plan','out/pwr/base-runtime/base-probe-plan.json','--apply')
} else {
    $label=$Stages.Replace(',','-')
    $pipelineArgs=@('levels/warfare/pwr/bases_v1/run_upgrade.py','--stages',$Stages)
    if ($NoMasters) { $pipelineArgs+='--no-masters' }
}
$log=Join-Path $logRoot ($label+$tail+'.log')
Write-Output "Running $label; log: $log"
# Native programs write progress to stderr; preserve it without PowerShell 5
# converting successful progress output to a terminating NativeCommandError.
$ErrorActionPreference='Continue'
uv run --python 3.12 --with-requirements tools/level/requirements-alpine.txt --with OpenEXR python @pipelineArgs > $log 2>&1
$result=$LASTEXITCODE
$ErrorActionPreference='Stop'
if ($result -ne 0) { Get-Content -LiteralPath $log -Tail 65; exit $result }
if (!$RefreshProbes -and 'bake' -in $selected) {
    uv run --python 3.12 --with-requirements tools/level/requirements-alpine.txt --with OpenEXR python 'levels/warfare/pwr/bases_v1/install_candidate.py' 'record-bake' >> $log 2>&1
    if ($LASTEXITCODE -ne 0) { Get-Content -LiteralPath $log -Tail 65; exit $LASTEXITCODE }
}
if (!$RefreshProbes -and 'assemble' -in $selected) {
    uv run --python 3.12 python 'levels/warfare/pwr/bases_v1/prepare_runtime_candidate.py' 'finalize-level' >> $log 2>&1
    if ($LASTEXITCODE -ne 0) { Get-Content -LiteralPath $log -Tail 65; exit $LASTEXITCODE }
}
Get-Content -LiteralPath $log -Tail 20
exit 0
