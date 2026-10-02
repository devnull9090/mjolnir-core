# Run a Meteorite editor commandlet on a limited set of cores, at below-normal
# priority (full-machine shader compiles have powered this box off).
#
#   powershell -File tools/ue/editor_cmd.ps1 -Script Scripts/build_ce_materials.py [-Mask 0xFF]
#
# The editor resets its own affinity once it is up; run a watcher that
# re-pins UnrealEditor-Cmd and ShaderCompileWorker alongside (see cook.ps1).
param([Parameter(Mandatory = $true)][string]$Script, [int64]$Mask = 0xFF)
$project = Join-Path $PSScriptRoot "..\..\unreal\MJOLNIRMaterials" | Resolve-Path
$Script = Join-Path $project $Script
$log = Join-Path $project ("Saved_" + [IO.Path]::GetFileNameWithoutExtension($Script) + ".log")
$exe = "C:\Program Files\Epic Games\UE_5.5\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
$cmd = "/c `"`"$exe`" `"$project\Meteorite.uproject`" -run=pythonscript -script=`"$Script`" -unattended -nop4 -nosplash -stdout -FullStdOutLogOutput > `"$log`" 2>&1`""
$p = Start-Process -FilePath cmd.exe -ArgumentList $cmd -PassThru -WindowStyle Hidden -WorkingDirectory $project
$p.ProcessorAffinity = [IntPtr]$Mask
$p.PriorityClass = [System.Diagnostics.ProcessPriorityClass]::BelowNormal
$p.WaitForExit()
"editor exit $($p.ExitCode), log $log"
Select-String -Path $log -Pattern "fork shaders:|fork layouts:|MJOLNIR|Error:|LogPython: Error" | Select-Object -First 30 | ForEach-Object { $_.Line }
