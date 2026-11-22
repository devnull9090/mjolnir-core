<#
.SYNOPSIS
    Start mjolnir-agent.ps1 at every logon, in the signed-in desktop session.

.DESCRIPTION
    The agent has to live in the desktop session: an SSH session has no
    desktop, so screenshots, input and starting Steam fail from there. A logon
    task puts it in the right session, and `schtasks /run` (or -Start) starts it
    again from SSH without anyone at the PC.

    Run on the target PC from the folder holding mjolnir-agent.ps1, as the user
    who plays (over SSH is fine):

        powershell -ExecutionPolicy Bypass -File .\register-agent-task.ps1 -Start

    -Restart stops a running agent first. The task runs with the user's normal
    rights, like a player's game: Steam started by an elevated agent would be
    elevated too.
#>
param(
    [string]$TaskName = "MJOLNIR Agent",
    [string]$AgentScript = (Join-Path $PSScriptRoot "mjolnir-agent.ps1"),
    [switch]$Start,
    [switch]$Restart
)
$ErrorActionPreference = "Stop"
if (-not (Test-Path $AgentScript)) { throw "no agent at $AgentScript" }
# $env:USERDOMAIN reads WORKGROUP under SSH; the token has the real account.
$user = [Security.Principal.WindowsIdentity]::GetCurrent().Name

$action = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory (Split-Path $AgentScript) `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Minimized -File `"$AgentScript`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
"registered '$TaskName' for $user -> $AgentScript"

function Get-Agent {
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
        Where-Object { $_.CommandLine -like "*mjolnir-agent.ps1*" }
}
if ($Restart) {
    Get-Agent | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; "stopped agent pid $($_.ProcessId)" }
    Start-Sleep -Milliseconds 500
}
if ($Start -or $Restart) {
    Start-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 3
    $running = @(Get-Agent)
    if ($running) { "agent running: pid $($running.ProcessId -join ', ') in session $((Get-Process -Id $running[0].ProcessId).SessionId)" }
    else { "agent not running yet; is $env:USERNAME signed in at the desktop? (the task runs only in a signed-in session)" }
}
