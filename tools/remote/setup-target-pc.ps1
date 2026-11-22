<#
.SYNOPSIS
    Make a Windows PC on the LAN a remote test target: SSH in, the game agent's
    port open, never asleep.

.DESCRIPTION
    Run once on the new PC, as the player's account (it asks for admin):

        powershell -ExecutionPolicy Bypass -File .\setup-target-pc.ps1 -PublicKey "ssh-ed25519 AAAA... name"

    The key is the development PC's public key (make a dedicated one:
    ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519_<pc>). Safe to run again.
    Writes a report beside itself (or to -Report) for the development PC to
    read. Everything after this happens over SSH: tools/remote/README.md.

    What it changes, and why:
      - The network profile to Private. Windows often files a new network as
        Public, which drops every inbound connection (RDP included) silently.
      - OpenSSH Server, automatic, with PowerShell as its shell. Windows can
        report the capability Installed (or InstallPending until a reboot)
        with no sshd service at all; then it falls back to Microsoft's
        OpenSSH package from winget.
      - The key into administrators_authorized_keys, locked to Administrators
        and SYSTEM (any other ACL and sshd ignores the file without a word),
        and into the user's own authorized_keys for a non-admin account.
      - Firewall: TCP 22 (SSH) and 47820 (mjolnir-agent.ps1) on private
        networks, plus Remote Desktop.
      - Power: no sleep, hibernate or monitor-off on AC; Windows Update does not
        restart while someone is signed in.
#>
param(
    [Parameter(Mandatory = $true)][string]$PublicKey,
    [string]$Report
)
$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell -Verb RunAs -ArgumentList "-NoExit -ExecutionPolicy Bypass -File `"$PSCommandPath`" -PublicKey `"$PublicKey`""
    return
}
if (-not $Report) { $Report = Join-Path $PSScriptRoot "setup-report-$env:COMPUTERNAME.txt" }
try { Start-Transcript -Path $Report -Force | Out-Null } catch { $Report = "$env:TEMP\setup-report-$env:COMPUTERNAME.txt"; Start-Transcript -Path $Report -Force | Out-Null }
$ProgressPreference = 'SilentlyContinue'

function Step($name, [scriptblock]$body) {
    $ErrorActionPreference = 'Stop'
    try { & $body; Write-Host "[ok]   $name" -ForegroundColor Green }
    catch { Write-Host "[FAIL] $name : $($_.Exception.Message)" -ForegroundColor Red }
}

Step "network profile -> Private" { Get-NetConnectionProfile | Set-NetConnectionProfile -NetworkCategory Private }

Step "OpenSSH Server present" {
    $cap = 'OpenSSH.Server~~~~0.0.1.0'
    if (-not (Get-Service sshd -ErrorAction SilentlyContinue)) {
        $state = (Get-WindowsCapability -Online -Name $cap).State
        if ($state -ne 'Installed') { Add-WindowsCapability -Online -Name $cap | Out-Null }
    }
    if (-not (Get-Service sshd -ErrorAction SilentlyContinue)) {
        Write-Host "  no sshd service after the capability; installing Microsoft.OpenSSH.Preview"
        winget install --id Microsoft.OpenSSH.Preview -e --silent --accept-package-agreements --accept-source-agreements --scope machine | Out-Host
    }
    if (-not (Get-Service sshd -ErrorAction SilentlyContinue)) { throw "still no sshd service; reboot and run this again" }
}
Step "sshd running + automatic" { Set-Service sshd -StartupType Automatic; Start-Service sshd }
Step "ssh default shell = PowerShell" {
    New-Item HKLM:\SOFTWARE\OpenSSH -Force | Out-Null
    New-ItemProperty HKLM:\SOFTWARE\OpenSSH -Name DefaultShell -Value "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" -PropertyType String -Force | Out-Null
}
Step "development PC key authorized" {
    $ak = "$env:ProgramData\ssh\administrators_authorized_keys"
    New-Item -ItemType Directory -Force (Split-Path $ak) | Out-Null
    if (-not ((Test-Path $ak) -and (Select-String -Path $ak -SimpleMatch $PublicKey -Quiet))) { Add-Content $ak $PublicKey -Encoding ascii }
    icacls $ak /inheritance:r /grant '*S-1-5-32-544:F' /grant '*S-1-5-18:F' | Out-Null
    $profileDir = [Environment]::GetFolderPath('UserProfile')
    New-Item -ItemType Directory -Force "$profileDir\.ssh" | Out-Null
    $uk = "$profileDir\.ssh\authorized_keys"
    if (-not ((Test-Path $uk) -and (Select-String -Path $uk -SimpleMatch $PublicKey -Quiet))) { Add-Content $uk $PublicKey -Encoding ascii }
}
Step "firewall: 22, 47820, Remote Desktop" {
    foreach ($r in @(@{n = 'MJOLNIR SSH'; p = 22 }, @{n = 'MJOLNIR agent'; p = 47820 })) {
        Remove-NetFirewallRule -DisplayName $r.n -ErrorAction SilentlyContinue
        New-NetFirewallRule -DisplayName $r.n -Direction Inbound -Protocol TCP -LocalPort $r.p -Profile Private, Domain -Action Allow | Out-Null
    }
    Enable-NetFirewallRule -Group '@FirewallAPI.dll,-28752'
}
Step "never sleep / hibernate / monitor off (AC)" {
    powercfg /change standby-timeout-ac 0
    powercfg /change hibernate-timeout-ac 0
    powercfg /change monitor-timeout-ac 0
    powercfg /hibernate off
}
Step "no update restart while signed in" {
    New-Item HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU -Force | Out-Null
    Set-ItemProperty HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU -Name NoAutoRebootWithLoggedOnUsers -Value 1 -Type DWord
}

Write-Host "`n===== REPORT ====="
"user: $(whoami)   profile: $([Environment]::GetFolderPath('UserProfile'))"
Get-Service sshd -ErrorAction SilentlyContinue | Format-Table Name, Status, StartType -AutoSize | Out-String
"listening on 22: $([bool](Get-NetTCPConnection -LocalPort 22 -State Listen -ErrorAction SilentlyContinue))"
Get-NetConnectionProfile | Format-Table Name, InterfaceAlias, NetworkCategory -AutoSize | Out-String
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } | Format-Table InterfaceAlias, IPAddress -AutoSize | Out-String
Get-CimInstance Win32_VideoController | Format-Table Name, CurrentHorizontalResolution, CurrentVerticalResolution -AutoSize | Out-String
"steam: $(Test-Path "${env:ProgramFiles(x86)}\Steam\steam.exe")"
Stop-Transcript | Out-Null
Write-Host "`nReport saved to $Report" -ForegroundColor Cyan
