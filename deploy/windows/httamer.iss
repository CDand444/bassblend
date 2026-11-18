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
Name: "{group}\htTamer manual"; Filename: "{app}\htTamer.exe"; Parameters: "manual"
Name: "{group}\Uninstall htTamer"; Filename: "{uninstallexe}"
Name: "{userdesktop}\htTamer"; Filename: "{app}\htTamer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\htTamer.exe"; Description: "Start htTamer now"; Flags: nowait postinstall skipifsilent
; an in-app update runs the installer silently: start htTamer again afterwards
Filename: "{app}\htTamer.exe"; Flags: nowait runasoriginaluser; Check: WizardSilent

[Code]
{ Network mode, and the name and port htTamer answers at: written to network.json in the data folder, the same
  file Tools > Network name changes. A silent (in-app) update leaves it as it is. }
var
  NetPage: TInputQueryWizardPage;
  NetBox: TNewCheckBox;

function NetFile: String;
begin
  Result := ExpandConstant('{localappdata}\htTamer\data\network.json');
end;

procedure InitializeWizard;
var
  S: AnsiString;
  T, Name, Port: String;
  P: Integer;
  Lan: Boolean;
begin
  Lan := False;
  Name := 'httamer';
  Port := '8765';
  if LoadStringFromFile(NetFile, S) then begin
    T := String(S);
    Lan := Pos('"lan": true', T) > 0;
    P := Pos('"name": "', T);
    if P > 0 then begin
      T := Copy(T, P + 9, 70);
      if Pos('"', T) > 1 then Name := Copy(T, 1, Pos('"', T) - 1);
    end;
    T := String(S);
    P := Pos('"port": ', T);
    if P > 0 then begin
      T := Copy(T, P + 8, 5);
      P := 1;
      while (P <= Length(T)) and (T[P] >= '0') and (T[P] <= '9') do P := P + 1;
      if P > 1 then Port := Copy(T, 1, P - 1);
    end;
  end;
  NetPage := CreateInputQueryPage(wpSelectTasks, 'Network', 'Open htTamer from a phone or another computer?',
    'htTamer normally listens only to this computer. In network mode a phone or tablet on your home network ' +
    'opens it at http://<name>.local:<port> and signs in with a PIN you choose on this computer first. ' +
    'Windows may ask once whether htTamer may use the network: allow it on private networks. ' +
    'You can change this later in Tools > Network name.');
  NetPage.Add('Network name (letters, digits and dashes):', False);
  NetPage.Add('Port (1024 to 65535; 8765 unless something else uses it):', False);
  NetPage.Values[0] := Name;
  NetPage.Values[1] := Port;
  NetBox := TNewCheckBox.Create(NetPage);
  NetBox.Parent := NetPage.Surface;
  NetBox.Caption := 'Open htTamer to my home network';
  NetBox.Top := NetPage.Edits[1].Top + NetPage.Edits[1].Height + ScaleY(16);
  NetBox.Width := NetPage.SurfaceWidth;
  NetBox.Height := ScaleY(20);
  NetBox.Checked := Lan;
end;

function NameOk(N: String): Boolean;
var
  I: Integer;
  C: Char;
begin
  Result := (Length(N) >= 1) and (Length(N) <= 63) and (N[1] <> '-') and (N[Length(N)] <> '-');
  for I := 1 to Length(N) do begin
    C := N[I];
    if not (((C >= 'a') and (C <= 'z')) or ((C >= '0') and (C <= '9')) or (C = '-')) then Result := False;
  end;
end;

function PortOk(S: String): Boolean;
var
  N: Integer;
begin
  N := StrToIntDef(S, 0);
  Result := (Length(S) >= 4) and (Length(S) <= 5) and (N >= 1024) and (N <= 65535) and (N <> 5353) and (IntToStr(N) = S);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = NetPage.ID then begin
    NetPage.Values[0] := Lowercase(Trim(NetPage.Values[0]));
    if not NameOk(NetPage.Values[0]) then begin
      MsgBox('Use 1 to 63 letters, digits or dashes (not at the start or end), e.g. httamer.', mbError, MB_OK);
      Result := False;
    end else begin
      NetPage.Values[1] := Trim(NetPage.Values[1]);
      if not PortOk(NetPage.Values[1]) then begin
        MsgBox('Use a port from 1024 to 65535 (not 5353), e.g. 8765.', mbError, MB_OK);
        Result := False;
      end;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Lan: String;
begin
  if (CurStep = ssPostInstall) and not WizardSilent then begin
    if NetBox.Checked then Lan := 'true' else Lan := 'false';
    ForceDirectories(ExtractFileDir(NetFile));
    SaveStringToFile(NetFile, '{"lan": ' + Lan + ', "name": "' + NetPage.Values[0] + '", "port": ' + NetPage.Values[1] + '}', False);
  end;
end;
