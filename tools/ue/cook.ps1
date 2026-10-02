# Cook and package the Meteorite project (unreal/MJOLNIRMaterials) into IoStore
# containers, gently: below-normal priority, pinned to a few logical CPUs
# (every process UAT starts - the editor, shader compile workers, UnrealPak -
# inherits the affinity). Sustained all-core load has cut power on this box.
#
#   powershell -File tools/ue/cook.ps1 [-Mask 0xFF]
param([int64]$Mask = 0xFF)
$project = Join-Path $PSScriptRoot "..\..\unreal\MJOLNIRMaterials" | Resolve-Path
$log = Join-Path $project "Saved_cook.log"
$uat = "C:\Program Files\Epic Games\UE_5.5\Engine\Build\BatchFiles\RunUAT.bat"
$args = "/c `"`"$uat`" BuildCookRun -project=`"$project\Meteorite.uproject`" -noP4 -platform=Win64 -clientconfig=Shipping -cook -stage -pak -iostore -skipbuild -unattended -utf8output -nocompileeditor -skipcookingeditorcontent > `"$log`" 2>&1`""
$p = Start-Process -FilePath cmd.exe -ArgumentList $args -PassThru -WindowStyle Hidden
$p.ProcessorAffinity = [IntPtr]$Mask
$p.PriorityClass = [System.Diagnostics.ProcessPriorityClass]::BelowNormal
$p.WaitForExit()
"cook exit $($p.ExitCode)"
Select-String -Path $log -Pattern "fork layouts:|Shader compiler errors|BUILD SUCCESSFUL|BUILD FAILED" | ForEach-Object { $_.Line.Substring(0, [Math]::Min(200, $_.Line.Length)) }
