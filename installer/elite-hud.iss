; Inno Setup script for elite-hud.
;
; Build (from the repository root, after tools/build_exe.py has produced
; dist/elite-hud/):
;
;     iscc /DAppVersion=0.2.0 installer\elite-hud.iss
;
; The AppId below must stay in sync with APP_ID in elite_hud/installation.py,
; and AppMutex with APP_MUTEX_NAME. The updater uses both to recognise an
; installed copy and to let Setup close a running HUD before replacing files.

#define AppName "elite-hud"
#define AppExeName "elite-hud.exe"
#define AppPublisher "madne5"
#define AppURL "https://github.com/madne5/edhud"
#define AppId "{{8F2C4A91-3D7E-4B62-9A15-C6E0B84D5F37}"

; The release workflow passes the tag; a bare local build still works.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription=Elite Dangerous journal HUD overlay
VersionInfoProductName={#AppName}

DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes

; Administrator install by default (Program Files). "dialog" additionally lets
; the user pick a per-user install, which makes silent self-updates possible
; without a UAC prompt -- the updater honours whichever was chosen.
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog commandline

; Keep the previous directory and task selections when updating in place.
UsePreviousAppDir=yes
UsePreviousTasks=yes

; The HUD is closed automatically (Restart Manager) before files are replaced,
; and restarted afterwards. This is what makes a silent update work.
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=yes
AppMutex=elite-hud-single-instance-mutex

OutputDir=..\dist
OutputBaseFilename=elite-hud-setup-{#AppVersion}
SetupIconFile=elite-hud.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName} {#AppVersion}

Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
MinVersion=10.0

; Inno Setup 6.3 renamed the architecture identifiers.
#if VER >= EncodeVer(6,3,0,0)
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
#else
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[CustomMessages]
english.CreateDesktopIcon=Create a &desktop shortcut
english.AutoStart=Start elite-hud when I sign in to Windows
english.LaunchApp=Launch elite-hud
russian.CreateDesktopIcon=Создать ярлык на &рабочем столе
russian.AutoStart=Запускать elite-hud при входе в Windows
russian.LaunchApp=Запустить elite-hud

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
; Autostart is offered but deliberately off by default: a HUD that appears
; before the game is launched is noise for most commanders.
Name: "autostart"; Description: "{cm:AutoStart}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\elite-hud\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: autostart

[Run]
; Interactive install: offer to launch at the end.
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent runasoriginaluser
; Silent install, i.e. a self-update: bring the HUD straight back up, and note
; that Setup closed it. runasoriginaluser matters here -- an elevated HUD cannot
; draw over a game running as the normal user, and it would be a poor habit.
Filename: "{app}\{#AppExeName}"; Flags: nowait skipifnotsilent runasoriginaluser

[UninstallDelete]
; The updater caches downloads inside the install directory for portable
; copies; make sure an uninstall does not leave them behind.
Type: filesandordirs; Name: "{app}\updates"
