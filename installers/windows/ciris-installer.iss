; Inno Setup script for the Windows CIRIS Agent fat installer.
;
; Bundles three things into one signed (eventually) .exe:
;   1. ciris-agent.exe + supporting files (PyInstaller --onedir output) — the
;      Python runtime + ciris_engine + every dependency, all wired up.
;   2. A trimmed JRE produced by `bundle-jre.ps1` (~30 MB) — handles the
;      "Java 17+ required" first-run failure.
;   3. The Compose Multiplatform desktop JAR, built by the existing matrix
;      Windows wheel job, copied alongside.
;
; Per-user install (no admin / UAC prompt). Install location:
;     %LOCALAPPDATA%\CIRIS\
; Start menu shortcut and (optional) desktop shortcut. Uninstall through
; standard "Add or remove programs" entry.
;
; Build:
;     iscc ciris-installer.iss /DCirisVersion=2.7.6
;
; The /DCirisVersion symbol is required so the version is consistent with
; what the bundled binaries report (no point shipping a 2.7.6 EXE inside a
; 2.7.5-named installer).
;
; Output: dist\CIRIS-Setup-{version}-x64.exe

#ifndef CirisVersion
#error "CirisVersion must be defined: iscc ciris-installer.iss /DCirisVersion=X.Y.Z"
#endif

#define MyAppName       "CIRIS"
#define MyAppPublisher  "CIRIS L3C"
#define MyAppURL        "https://ciris.ai"
#define MyAppExeName    "ciris-agent.exe"
#define MyAppId         "{{F2C1A8E9-7D4B-4C5A-B7E3-1F0A9D2C5E88}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#CirisVersion}
AppVerName={#MyAppName} {#CirisVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Per-user install — no admin prompt. The {localappdata} constant resolves
; to %LOCALAPPDATA% (typically C:\Users\<user>\AppData\Local). Users who
; want a system-wide install can be served by a separate admin variant of
; this script later — for now, per-user covers the "just let me install"
; case that motivated the fat installer.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
LicenseFile=
OutputDir=..\..\dist
OutputBaseFilename=CIRIS-Setup-{#CirisVersion}-x64
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName} {#CirisVersion}
UninstallDisplayIcon={app}\{#MyAppExeName}
; Code signing wired in via /SSignTool=... when ISCC is invoked from CI.
; Until the Authenticode cert lands we ship unsigned and accept the
; SmartScreen warning on first run.
SignTool=signtool
SignedUninstaller=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; \
    GroupDescription: "Additional shortcuts:"

[Files]
; PyInstaller --onedir output — the entire ciris-agent\ folder. The /R
; flag recursively copies subdirectories (which include every Python dep
; and the bundled data files declared in ciris-agent.spec).
Source: "..\..\dist\ciris-agent\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

; Trimmed JRE (~30 MB). The desktop_launcher prefers a JRE bundled at
; <app>\runtime\ — see the launcher's _ensure_bundled_jre_executable
; logic. We drop it there directly.
Source: "..\..\dist\runtime\*"; DestDir: "{app}\runtime"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

; Compose Multiplatform desktop JAR. find_desktop_jar() in
; ciris_engine/desktop_launcher.py searches first under the package's
; desktop_app directory. PyInstaller bundles ciris_engine into
; <app>\_internal\ciris_engine\, so the JAR needs to land there.
Source: "..\..\client\desktopApp\build\compose\jars\CIRIS-windows-*.jar"; \
    DestDir: "{app}\_internal\ciris_engine\desktop_app"; \
    Flags: ignoreversion

; CIRISVerify Rust FFI binary (license verification, audit hash chain).
; The loader (ciris_adapters/ciris_verify/ffi_bindings/client.py) imports
; the `ciris_verify` package and probes its directory — release/2.7.4
; landed that fix. PyInstaller pulls this in via `import ciris_verify`,
; so usually it's already inside the bundle. The fallback Files entry
; below is a safety net.
Source: "..\..\dist\ciris-agent\_internal\ciris_verify\*.dll"; \
    DestDir: "{app}\_internal\ciris_verify"; \
    Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
    WorkingDir: "{app}"; Comment: "Launch CIRIS"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
    WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; Optional post-install launch. NoUiCheck so silent installs don't pop a
; window the user didn't ask for.
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; CIRIS_HOME (where logs / data / .env live) is at %USERPROFILE%\ciris\
; per ciris_engine/logic/utils/path_resolution.py. We deliberately do
; NOT delete it — the user's agent data, identity keys, and audit chain
; survive uninstall. They can manually rm -rf if they really want a
; clean slate.
;
; Only delete files we created in the install dir.
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{app}\_internal"
