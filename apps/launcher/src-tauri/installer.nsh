!define MUI_FINISHPAGE_LINK "Join the MJOLNIR Discord Community (discord.gg/9gxYZsByW9)"
!define MUI_FINISHPAGE_LINK_LOCATION "https://discord.gg/9gxYZsByW9"

; Launchers up to 0.9.0 were offered as an MSI, a per-machine product of its
; own. The updater runs this per-user installer, so an MSI user ended up with
; two installs: two entries in Installed apps, and the MSI's shortcuts kept
; opening the copy that never updated, which offered the update again.
; Tauri's template removes an MSI install only on its reinstall page, which a
; silent update skips. This runs in every mode, before the files are copied;
; msiexec asks for elevation once, since the MSI was installed for all users.
!macro NSIS_HOOK_PREINSTALL
  Push $0
  Push $1
  Push $2
  SetRegView 64
  StrCpy $0 0
  mjolnir_msi_loop:
    EnumRegKey $1 HKLM "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall" $0
    StrCmp $1 "" mjolnir_msi_done
    IntOp $0 $0 + 1
    ReadRegStr $2 HKLM "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$1" "DisplayName"
    StrCmp $2 "${PRODUCTNAME}" 0 mjolnir_msi_loop
    ReadRegStr $2 HKLM "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$1" "Publisher"
    StrCmp $2 "${MANUFACTURER}" 0 mjolnir_msi_loop
    ReadRegDWORD $2 HKLM "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$1" "WindowsInstaller"
    StrCmp $2 "1" 0 mjolnir_msi_loop
    DetailPrint "Removing the earlier MSI install of ${PRODUCTNAME} ($1)"
    ExecWait '"$SYSDIR\msiexec.exe" /x $1 /passive /norestart' $2
    DetailPrint "msiexec /x returned $2"
  mjolnir_msi_done:
  SetRegView lastused
  Pop $2
  Pop $1
  Pop $0
!macroend
