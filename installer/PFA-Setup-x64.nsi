Unicode true
!include "MUI2.nsh"

!ifndef APP_VERSION
  !define APP_VERSION "0.1.0-beta.1"
!endif
!ifndef APP_SOURCE
  !define APP_SOURCE "dist\POWER_FAULT_ANALYZER"
!endif
!ifndef OUTPUT_PATH
  !define OUTPUT_PATH "dist\release\PFA-Setup-x64.exe"
!endif

Name "POWER_FAULT_ANALYZER ${APP_VERSION}"
OutFile "${OUTPUT_PATH}"
InstallDir "$LOCALAPPDATA\Programs\POWER_FAULT_ANALYZER"
InstallDirRegKey HKCU "Software\POWER_FAULT_ANALYZER" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID zlib
ShowInstDetails show
ShowUninstDetails show

VIProductVersion "${APP_VERSION_RESOURCE}"
VIAddVersionKey /LANG=1033 "ProductName" "POWER_FAULT_ANALYZER"
VIAddVersionKey /LANG=1033 "ProductVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=1033 "CompanyName" "POWER_FAULT_ANALYZER contributors"
VIAddVersionKey /LANG=1033 "FileDescription" "Power-system engineering workbench"
VIAddVersionKey /LANG=1033 "LegalCopyright" "GPL-3.0-or-later; see installed LICENSE and NOTICE.md"

!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\POWER_FAULT_ANALYZER.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Launch POWER_FAULT_ANALYZER"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${APP_SOURCE}\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

Section "Install" SEC_MAIN
  SetShellVarContext current
  SetOutPath "$INSTDIR"
  File /r "${APP_SOURCE}\*.*"

  WriteRegStr HKCU "Software\POWER_FAULT_ANALYZER" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\POWER_FAULT_ANALYZER" "DisplayName" "POWER_FAULT_ANALYZER ${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\POWER_FAULT_ANALYZER" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\POWER_FAULT_ANALYZER" "Publisher" "POWER_FAULT_ANALYZER contributors"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\POWER_FAULT_ANALYZER" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\POWER_FAULT_ANALYZER" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  CreateDirectory "$SMPROGRAMS\POWER_FAULT_ANALYZER"
  CreateShortcut "$SMPROGRAMS\POWER_FAULT_ANALYZER\POWER_FAULT_ANALYZER.lnk" "$INSTDIR\POWER_FAULT_ANALYZER.exe"
  CreateShortcut "$SMPROGRAMS\POWER_FAULT_ANALYZER\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\POWER_FAULT_ANALYZER.lnk" "$INSTDIR\POWER_FAULT_ANALYZER.exe"
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  Delete "$DESKTOP\POWER_FAULT_ANALYZER.lnk"
  Delete "$SMPROGRAMS\POWER_FAULT_ANALYZER\POWER_FAULT_ANALYZER.lnk"
  Delete "$SMPROGRAMS\POWER_FAULT_ANALYZER\Uninstall.lnk"
  RMDir "$SMPROGRAMS\POWER_FAULT_ANALYZER"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\POWER_FAULT_ANALYZER"
  DeleteRegKey HKCU "Software\POWER_FAULT_ANALYZER"
  RMDir /r "$INSTDIR"
SectionEnd
