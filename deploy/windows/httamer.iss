; Inno Setup script for the htTamer Windows installer. Build after PyInstaller:
;   iscc /DAppVersion=1.0.0 deploy\windows\httamer.iss
; Per-user install (no admin rights needed). Settings and measurements live in
; %LOCALAPPDATA%\htTamer and are kept when htTamer is uninstalled or updated.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6C1E3A52-9B7D-4C8E-A4F1-3D2B7E9C0A15}
AppName=htTamer
AppVersion={#AppVersion}
AppPublisher=the htTamer authors
DefaultDirName={localappdata}\Programs\htTamer
DefaultGroupName=htTamer
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=htTamer-{#AppVersion}-windows-setup
Compression=lzma2
SolidCompression=yes
LicenseFile=..\..\LICENSE.md
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayName=htTamer
CloseApplications=force
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\..\dist\htTamer\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\htTamer"; Filename: "{app}\htTamer.exe"
Name: "{group}\htTamer manual"; Filename: "http://127.0.0.1:8765/manual"
Name: "{group}\Uninstall htTamer"; Filename: "{uninstallexe}"
Name: "{userdesktop}\htTamer"; Filename: "{app}\htTamer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\htTamer.exe"; Description: "Start htTamer now"; Flags: nowait postinstall skipifsilent
; an in-app update runs the installer silently: start htTamer again afterwards
Filename: "{app}\htTamer.exe"; Flags: nowait runasoriginaluser; Check: WizardSilent
