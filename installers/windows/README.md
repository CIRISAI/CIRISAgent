# Windows Fat Installer

One signed (eventually) `CIRIS-Setup-X.Y.Z-x64.exe` that handles the two
biggest Windows install pain points:

1. **Python local-path issues** — bundled via PyInstaller, so the user
   never installs Python or pip themselves.
2. **Java install** — bundled via a `jlink`-trimmed JRE (~30 MB), so the
   "Java 17+ required" first-run failure goes away.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  CIRIS-Setup-X.Y.Z-x64.exe  (Inno Setup wrapper, ~150–200 MB)    │
│                                                                  │
│  ┌─ ciris-agent.exe + _internal\  (PyInstaller --onedir)         │
│  │    └─ Python 3.12 runtime + ciris_engine + every dep          │
│  │       (httpx, pydantic, instructor, openai, anthropic, …)     │
│  │       + bundled data: prompts, ACCORD text, geo DB, templates │
│  │                                                                │
│  ├─ runtime\  (jlink-trimmed JRE ~30 MB)                         │
│  │    └─ minimal JDK 17 modules: java.base, java.desktop,        │
│  │       java.management, jdk.crypto.ec, jdk.unsupported, …      │
│  │                                                                │
│  └─ _internal\ciris_engine\desktop_app\CIRIS-windows-x64-*.jar   │
│       └─ Compose Multiplatform desktop UI (built by gradle)      │
└──────────────────────────────────────────────────────────────────┘
```

## Pipeline (CI: `build-windows-installer` job)

1. Build the Compose desktop UberJar via `./gradlew :desktopApp:packageUberJarForCurrentOS`.
2. Build the PyInstaller bundle via `pyinstaller ciris-agent.spec` → `dist\ciris-agent\` (one folder, NOT one file — see spec comments).
3. `bundle-jre.ps1` runs `jlink` against `JAVA_HOME` to produce a trimmed JRE in `dist\runtime\`.
4. `iscc ciris-installer.iss /DCirisVersion=$VERSION` produces `dist\CIRIS-Setup-$VERSION-x64.exe`.
5. CI uploads the `.exe` as a workflow artifact (and on tagged main releases, attaches it to the GitHub Release).

## Why the choices

- **PyInstaller `--onedir`**, not `--onefile`. Onefile unpacks to `%TEMP%` on every launch (slow start, antivirus FPs, breaks the relative-path lookups CIRIS does for the desktop JAR / native libs / accord text).
- **Per-user install** (`{localappdata}\CIRIS\`), not `Program Files`. No UAC prompt, no admin needed — the install completes for any signed-in user. A future system-wide variant can be a separate `.iss`.
- **`jlink`-trimmed JRE bundled** instead of relying on system Java. Most Windows desktops don't have JDK/JRE installed, and the ones that do often have Java 8/11 (too old). Bundling a known-good JRE removes the dependency entirely.
- **Unsigned (initially)**. SmartScreen will warn on first run until we wire an Authenticode cert. Tracked separately — defer until adoption justifies the ~$200/yr cost.
- **No bundled Python**. The PyInstaller `python.dll` covers it — no separate CPython install.

## Building locally

You need Windows + JDK 17 + Python 3.12 + Inno Setup 6.

```powershell
# From repo root
cd installers\windows

# 1. Build the desktop JAR (one-time per source change)
cd ..\..\client
.\gradlew :desktopApp:packageUberJarForCurrentOS --no-daemon
cd ..\installers\windows

# 2. Install Python deps
pip install -r ..\..\requirements.txt
pip install pyinstaller

# 3. PyInstaller bundle
pyinstaller ciris-agent.spec --noconfirm
# Output lands at installers\windows\dist\ciris-agent\

# 4. Move bundle to repo-root dist (the .iss expects it there)
mkdir ..\..\dist -ErrorAction SilentlyContinue
Move-Item -Force dist\ciris-agent ..\..\dist\

# 5. Trim JRE (needs JAVA_HOME set to JDK 17+)
$jar = Get-ChildItem ..\..\client\desktopApp\build\compose\jars\CIRIS-windows-*.jar | Select-Object -First 1
.\bundle-jre.ps1 -JarPath $jar.FullName -OutputDir ..\..\dist\runtime

# 6. Inno Setup
$ver = python -c "from ciris_engine.constants import CIRIS_VERSION; print(CIRIS_VERSION.replace('-stable',''))"
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" "/DCirisVersion=$ver" ciris-installer.iss

# Output: ..\..\dist\CIRIS-Setup-$ver-x64.exe
```

## Diagnosing crashes

When `ciris-agent.exe` crashes on a clean install, the failure mode is
almost always one of three things:

1. **`ModuleNotFoundError`** — PyInstaller's static analyzer missed a
   dynamic import. Add the module to the `hiddenimports` list in
   `ciris-agent.spec` and rebuild. `pydantic_core._pydantic_core` and
   `openai.types.*` are the usual suspects.

2. **`java.lang.NoClassDefFoundError`** — the trimmed JRE is missing a
   JDK module. Add it to the `$modules` list in `bundle-jre.ps1`. The
   exception message will name the missing package — map it to its JDK
   module via `jdeps`.

3. **`FileNotFoundError` on a YAML/JSON/SQL file at runtime** — the
   data file isn't in the bundle. Add the glob to the `datas` list in
   `ciris-agent.spec`'s `collect_data_files("ciris_engine", includes=[...])`
   call.

When the installer itself fails the Inno Setup compile, the error is
almost always a missing source file the `.iss` referenced — most often
the desktop JAR (build it first via gradle) or the trimmed JRE
(`bundle-jre.ps1` failed silently — look at jlink stderr).

## Future work

- Authenticode code signing (`/SSignTool=`) once the cert lands.
- macOS `.dmg` and Linux `.AppImage` parallel installers — same architecture (PyInstaller + bundled JRE + native installer wrapper) just different wrappers.
- Auto-update path — Sparkle on macOS, Squirrel.Windows on Windows. Not needed until adoption justifies the maintenance burden.
