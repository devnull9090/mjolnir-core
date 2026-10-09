# Cook and package the Meteorite project (unreal/MJOLNIRMaterials) into IoStore
# containers at below-normal priority, on every core unless a mask limits it
# (-Mask or MJ_CPU_MASK, hex: every process UAT starts - the editor, shader
# compile workers, UnrealPak - inherits the affinity). The build box has cut
# power under all-core load; a mask such as 0x0F is the way to keep a cook
# light while that is being investigated.
#
#   powershell -File tools/ue/cook.ps1 [-Mask 0x0F]
#
# The project enables CommonUI (MJOLNIR's menu screens derive from
# CommonActivatableWidget), which makes UAT treat it as a code project: the
# editor target (our plugins and a receipt) is compiled before the cook, so
# there is no -nocompileeditor.
param([int64]$Mask = 0)
# MJ_CPU_MASK (hex) limits a whole batch, e.g. 0x0F for four cores; 0 or unset is every core.
if ($env:MJ_CPU_MASK) { $Mask = [Convert]::ToInt64($env:MJ_CPU_MASK, 16) }
$project = Join-Path $PSScriptRoot "..\..\unreal\MJOLNIRMaterials" | Resolve-Path
$log = Join-Path $project "Saved_cook.log"
$uat = "C:\Program Files\Epic Games\UE_5.5\Engine\Build\BatchFiles\RunUAT.bat"
$args = "/c `"`"$uat`" BuildCookRun -project=`"$project\Meteorite.uproject`" -noP4 -platform=Win64 -clientconfig=Shipping -cook -stage -pak -iostore -skipbuild -unattended -utf8output -skipcookingeditorcontent > `"$log`" 2>&1`""
$p = Start-Process -FilePath cmd.exe -ArgumentList $args -PassThru -WindowStyle Hidden
if ($Mask -ne 0) { $p.ProcessorAffinity = [IntPtr]$Mask }
$p.PriorityClass = [System.Diagnostics.ProcessPriorityClass]::BelowNormal
$p.WaitForExit()
"cook exit $($p.ExitCode)"
Select-String -Path $log -Pattern "fork layouts:|Shader compiler errors|BUILD SUCCESSFUL|BUILD FAILED" | ForEach-Object { $_.Line.Substring(0, [Math]::Min(200, $_.Line.Length)) }
