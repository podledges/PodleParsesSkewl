; Inno Setup installer for the Windows GUI distribution.
; Build with: ISCC.exe /DAppVersion=0.1.0 installer\PodleSkewl.iss
#define AppName "PodleSkewl"
#define AppPublisher "podledges"
#define AppURL "https://github.com/podledges/PodleParsesSkewl"
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{B1E5C3AA-8A7D-4E0A-9D92-0E05C9B7F9A1}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
DefaultDirName={autopf}\PodleSkewl
DefaultGroupName={#AppName}
DisableProgramGroupPage=no
OutputDir=..\dist
OutputBaseFilename=PodleSkewl-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\PodleSkewl.exe
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\dist\PodleSkewl.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\pps.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: isreadme
Source: "..\WINDOWS-SMOKE-TEST.md"; DestDir: "{app}"

[Icons]
Name: "{group}\PodleSkewl"; Filename: "{app}\PodleSkewl.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\PodleSkewl"; Filename: "{app}\PodleSkewl.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\PodleSkewl.exe"; Description: "Launch PodleSkewl"; Flags: nowait postinstall skipifsilent

[Messages]
FinishedLabel=PodleSkewl is installed. ffmpeg and ffprobe are required separately for MP4 processing; see the included README for setup.
