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

## Windows 7 SP1 support tier (CIRISAgent#875)

CIRIS commits to a best-effort **Windows 7 SP1 x64** tier — old hardware is
where the mission's highest-need users live. "If we can support arm32, we can
support Win7." Win7 runs with honest degradations, surfaced in-app, never
hidden.

**Substrate (done).** The whole quad is Win7-SP1-loadable as of the #881
adoption floor — persist 5.5.5 / edge 2.2.1 / verify 5.1.3 / lens-core 1.3.0,
each built with the Tier-3 `x86_64-win7-windows-msvc` lane (the Win8/10 std
symbols become dynamic `GetProcAddress`-with-fallback, absent from the static
import table — verify by *parsing the PE import directory*, not a substring
scan). Closed: CIRISEdge#94, CIRISPersist#205, CIRISLensCore#48, CIRISVerify#67.

**Installer (this tier).**
- `MinVersion=6.1sp1` in the `.iss` — Setup refuses cleanly below Win7 SP1.
- **JRE**: CI builds the trimmed jlink runtime from **BellSoft Liberica** JDK 17
  (`distribution: 'liberica'`), not Temurin — Temurin 17 dropped Win7; Liberica
  and Zulu retain it. `bundle-jre.ps1` soft-warns if it detects a Temurin host.
- **UCRT**: Win7 needs the Universal CRT (KB2999226) for the `api-ms-win-crt-*`
  import-sets every bundled binary carries. CI fetches the redist best-effort
  into `redist/` (gitignored); the `.iss` bundles it (`skipifsourcedoesntexist`)
  and installs it via `wusa` on Win7-only when `ucrtbase.dll` is absent. If the
  fetch rots, the installer still builds — Win7 users hand-provision KB2999226.
- **Attestation tier**: Win7 predates TPM 2.0 TBS, so CIRISVerify runs at the
  software-key tier — the same degradation path unsupported Android SoCs take.
  A one-time post-install note sets the expectation; the Trust page shows it
  in-app. Everything else (engine, lens fold, federation, desktop GUI) is normal.

**Still open (the honest residual):**
1. **PyInstaller CPython payload** — `actions/setup-python` ships official CPython,
   which gates on Win8.1+ (`PathCch*` / api-set imports). The Win7 tier needs the
   PyInstaller bundle built against a **Win7-capable CPython**. **Scaffolded** as
   an opt-in lane: `.github/workflows/windows7-installer.yml` (`workflow_dispatch`)
   builds `CIRIS-Setup-<ver>-win7-x64.exe` against the community-patched
   adang1345/PythonVista (née PythonWin7) interpreter, with a **fail-closed
   SHA256 gate** — the dispatcher must paste a hash they verified upstream or the
   build aborts (no unverified interpreter is ever bundled). The mainline
   universal installer stays on official CPython.
   ⚠️ **Supply-chain go/no-go is the owner's call**: this embeds a third-party-
   patched interpreter in a signed security/attestation product. The artifact is
   labelled `win7-EXPERIMENTAL` and is NOT wired into Publish Release — promotion
   is gated on (a) accepting that supply-chain and (b) the on-device test below.
2. **On-device acceptance** — a clean Windows 7 SP1 x64 VM must install, boot to
   WORK with all 22 services, seal a trace via lens-core, and show the software
   attestation tier. This is the gate that closes #875 (the checkbox folded in
   from CIRISVerify#67).
