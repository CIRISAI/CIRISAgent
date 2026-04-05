# CIRIS Unified Agent UX (Kotlin Multiplatform)

**NOTE: "mobile" is a misnomer.** This is the **unified CIRIS agent UX** - the cross-platform user interface for interacting with CIRIS agents, targeting:
- **Android** (phone, tablet)
- **iOS** (iPhone, iPad)
- **Windows** (x64)
- **macOS** (x64, arm64)
- **Linux** (x64, arm64, arm32)

## Architecture

The `shared/` module contains **95% of the code** and runs on ALL platforms:

```
shared/
├── commonMain/     # Cross-platform code (ALL platforms)
│   ├── api/        # Ktor HTTP client
│   ├── models/     # Data models
│   ├── viewmodels/ # Business logic (StartupViewModel, ChatViewModel, etc.)
│   ├── ui/         # Compose Multiplatform UI
│   └── platform/   # expect declarations (interfaces)
├── androidMain/    # Android actual implementations
├── iosMain/        # iOS actual implementations
└── desktopMain/    # Desktop actual implementations (Windows, macOS, Linux)
```

## Platform-Specific Code

Each platform has `actual` implementations for `expect` declarations:

| Feature | Android | iOS | Desktop |
|---------|---------|-----|---------|
| Python Runtime | Chaquopy | PythonKit | Subprocess |
| Secure Storage | EncryptedSharedPrefs | Keychain | keyring |
| Logging | Logcat | os_log | println |
| App Restart | ProcessPhoenix | exit(0) | System.exit |

## Console Output Parsing

The Python backend outputs status messages to stdout that drive UI animations:

```
[CIRISVerify] FFI init starting         → Verify step 1/8
[CIRISVerify] TPM: device nodes detected → Verify step 2/8
[CIRISVerify] LicenseEngine: init...     → Verify step 3/8
[CIRISVerify] Ed25519 signer init...     → Verify step 4/8
[CIRISVerify] DNS cross-check            → Verify step 5/8
[CIRISVerify] HTTPS query complete       → Verify step 6/8
[CIRISVerify] Binary check               → Verify step 7/8
[CIRISVerify] Unified attestation...     → Verify step 8/8

[SERVICE 1/22] STARTED                   → Service step 1/22
[SERVICE 2/22] STARTED                   → Service step 2/22
...
```

**Cross-platform parsing:**
- Android: Parse `python.stdout` via logcat
- iOS: Redirect stdout to callback
- Desktop: Read subprocess stdout

## Key ViewModels

- `StartupViewModel` - Manages startup sequence (verify, prep, services)
- `ChatViewModel` - Chat interaction with CIRIS
- `SettingsViewModel` - LLM configuration (CIRIS Proxy vs BYOK)
- `TrustViewModel` - Device attestation status

## Testing

```bash
# Shared unit tests (all platforms)
./gradlew :shared:allTests

# Android instrumented tests
./gradlew :androidApp:connectedAndroidTest

# Desktop tests
./gradlew :shared:desktopTest
```

## Desktop UI Test Automation

The desktop app includes an embedded HTTP server for automated UI testing and driving the UI programmatically.

### Enabling Test Mode

```bash
# Via unified entry point (starts Python backend + desktop app)
export CIRIS_TEST_MODE=true
ciris-agent

# Via Gradle (development - desktop only, needs separate backend)
export CIRIS_TEST_MODE=true
./gradlew :desktopApp:run

# Build development JAR (outputs to build/compose/jars/CIRIS-*.jar)
./gradlew :desktopApp:packageUberJarForCurrentOS

# Custom test server port
export CIRIS_TEST_MODE=true
export CIRIS_TEST_PORT=9000
ciris-agent
```

### Test Server Endpoints

The server runs on `http://localhost:8091` by default:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (`{"status":"ok","testMode":true}`) |
| `/screen` | GET | Current screen name (`{"screen":"Login"}`) |
| `/tree` | GET | Full UI element tree with positions |
| `/click` | POST | Click element by testTag |
| `/input` | POST | Input text to element |
| `/wait` | POST | Wait for element to appear |
| `/element/{tag}` | GET | Get specific element info |
| `/act` | POST | **Combined action + view** (preferred for automation) |

### The `/act` Endpoint (Preferred)

The `/act` endpoint combines action + wait + tree into a single call, reducing 3 HTTP requests to 1:

```bash
# Click and get resulting UI state
curl -X POST http://localhost:8091/act \
  -H "Content-Type: application/json" \
  -d '{"testTag": "menu_adapters", "action": "click", "waitMs": 1000}'

# Input text and get filtered elements
curl -X POST http://localhost:8091/act \
  -H "Content-Type: application/json" \
  -d '{
    "testTag": "input_skill_md",
    "action": "input",
    "text": "---\nname: My Skill\n---",
    "clearFirst": true,
    "waitMs": 500,
    "filterTags": ["skill", "preview", "import"]
  }'
```

**Request fields:**
- `action`: "click", "input", or "wait"
- `testTag`: Target element's testTag
- `text`: Text to input (for "input" action)
- `clearFirst`: Clear existing text before input (default: true)
- `waitMs`: Milliseconds to wait after action before reading tree (default: 500)
- `filterTags`: Optional list of substrings to filter returned elements

**Response:**
```json
{
  "actionResult": {"success": true, "element": "menu_adapters", "action": "click"},
  "screen": "Adapters",
  "elements": [{"testTag": "btn_add_menu", "x": 100, "y": 200, ...}],
  "elementCount": 15
}
```

### Example: Automated Login

```bash
# Check current screen
curl http://localhost:8091/screen

# Enter credentials
curl -X POST http://localhost:8091/input \
  -H "Content-Type: application/json" \
  -d '{"testTag": "input_username", "text": "admin"}'

curl -X POST http://localhost:8091/input \
  -H "Content-Type: application/json" \
  -d '{"testTag": "input_password", "text": "password"}'

# Submit login
curl -X POST http://localhost:8091/click \
  -H "Content-Type: application/json" \
  -d '{"testTag": "btn_login_submit"}'

# Wait for chat screen
curl -X POST http://localhost:8091/wait \
  -H "Content-Type: application/json" \
  -d '{"testTag": "input_message", "timeoutMs": 10000}'
```

### Adding Testable Elements

Use the `testable` modifier (cross-platform):

```kotlin
import ai.ciris.mobile.shared.platform.testable

Button(
    onClick = { ... },
    modifier = Modifier.testable("my_button")
)
```

This modifier:
- **Desktop + test mode**: Tracks element position for automation via Ktor HTTP server
- **iOS + test mode**: Tracks element position for automation via POSIX socket HTTP server
- **Normal mode (all platforms)**: Applies `testTag` only

**Full API documentation:** `desktopApp/src/main/kotlin/ai/ciris/desktop/testing/README.md`

### End-to-End UI Automation Workflow

The test automation HTTP server runs on **all platforms** when `CIRIS_TEST_MODE=true`:
- **Desktop**: Ktor CIO server (started from `Main.kt`) + java.awt.Robot for screenshots/mouse
- **iOS**: POSIX socket server (started from `CIRISApp` LaunchedEffect) — same endpoints minus screenshot/mouse
- **Android**: TODO (Ktor CIO planned, currently use Espresso)

**Desktop E2E workflow:**
```bash
# 1. Launch with test mode
CIRIS_TEST_MODE=true python3 -m ciris_engine.cli

# 2. Wait for test server
curl http://localhost:8091/health

# 3. Drive UI via HTTP
curl -X POST http://localhost:8091/input -d '{"testTag":"input_username","text":"admin","clearFirst":true}'
curl -X POST http://localhost:8091/click -d '{"testTag":"btn_login_submit"}'
curl http://localhost:8091/screen  # -> {"screen":"Interact"}

# 4. Screenshots (desktop only - java.awt.Robot)
curl -X POST http://localhost:8091/screenshot -d '{"path":"/tmp/screenshot.png"}'

# 5. Mouse click (desktop only - for dropdowns, popups)
curl -X POST http://localhost:8091/mouse-click -d '{"testTag":"input_llm_provider"}'

# 6. Full E2E test script (wipe → setup wizard → verify)
bash tools/test_desktop_wipe_setup.sh
```

**iOS E2E workflow:**
```bash
DEVICE_ID="A53DA92F-..."  # CoreDevice UUID
IDEVICE_ID="00008110-..."  # idevice UUID

# 1. Launch with test mode (env var set via devicectl)
xcrun devicectl device process launch -d $DEVICE_ID \
  --terminate-existing \
  --environment-variables '{"CIRIS_TEST_MODE":"true"}' \
  ai.ciris.mobile

# 2. Port forward test server + API
iproxy 18091 8091 -u $IDEVICE_ID &
iproxy 18080 8080 -u $IDEVICE_ID &

# 3. Drive UI (same endpoints as desktop)
curl http://127.0.0.1:18091/health   # {"status":"ok","testMode":true}
curl http://127.0.0.1:18091/screen   # {"screen":"Login"}
curl -X POST http://127.0.0.1:18091/click -d '{"testTag":"btn_local_login"}'
curl -X POST http://127.0.0.1:18091/input -d '{"testTag":"input_username","text":"admin","clearFirst":true}'

# 4. Screenshots (via pymobiledevice3, not test server)
python3 -m pymobiledevice3 developer dvt screenshot /tmp/ios_screen.png

# 5. HA adapter setup (API-driven, OAuth via Chrome + iproxy callback)
TOKEN=$(curl -s -X POST http://127.0.0.1:18080/v1/auth/login ...)
curl -X POST http://127.0.0.1:18080/v1/system/adapters/home_assistant/configure/start ...
# Discovery → select URL → OAuth in browser → forward callback via iproxy → features → complete
```

**Important iOS notes:**
- Text input needs **2-second delay** between fields (StateFlow propagation)
- `--terminate-existing` flag needed to force-kill previous app instance
- OAuth callbacks redirect to `127.0.0.1:8080` — forward via `iproxy 18080 8080`
- API step_data must be nested: `{"step_data":{"selected_url":"..."}}`
- Screenshots use `pymobiledevice3` (requires `sudo tunneld` running)
- `.env` must contain `CIRIS_CONFIGURED="true"` to NOT be first-run (file existence alone is not enough)

**Shared endpoints (all platforms):**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/screen` | GET | Current screen name |
| `/tree` | GET | All UI elements with positions |
| `/act` | POST | **Combined action + view** (preferred) |
| `/click` | POST | Click by testTag (programmatic) |
| `/input` | POST | Text input to element |
| `/wait` | POST | Wait for element to appear |
| `/element/{tag}` | GET | Get element info |

**Desktop-only endpoints:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/mouse-click` | POST | Real AWT mouse click by testTag |
| `/mouse-click-xy` | POST | Real AWT mouse click at coordinates |
| `/screenshot` | GET/POST | Capture window via java.awt.Robot |
| `/navigate` | POST | Navigate to screen |

**Key test tags for common flows:**
- Login: `input_username`, `input_password`, `btn_login_submit`, `btn_local_login`, `btn_apple_signin`
- Navigation: `btn_adapters_menu`, `menu_adapters`, `btn_data_menu`, `menu_data_management`
- Setup: `btn_next`, `btn_back`, `input_llm_provider`, `input_api_key`, `input_llm_model_text`
- Dropdowns: `input_llm_provider` (testableClickable toggles expansion), `menu_provider_openrouter`
- Trust: `btn_trust_shield`, `btn_trust_refresh`, `btn_trust_back`
- Data: `btn_reset_account`, `btn_reset_confirm`
- Chat: `input_message`, `btn_send`, `btn_attach`
- Adapters: `btn_add_adapter`, `item_adapter_type_home_assistant`, `item_discovered_*`
- Wizard: `btn_wizard_next`, `btn_wizard_complete`, `btn_wizard_dismiss`, `btn_oauth_sign_in`

## Build Targets

```bash
# Android APK
./gradlew :androidApp:assembleDebug

# iOS Framework
./gradlew :shared:assembleDebugXCFramework

# Desktop JAR (Windows/macOS/Linux)
./gradlew :desktopApp:packageDistributionForCurrentOS
```

## Device Preferences

**IMPORTANT**: When multiple Android devices are connected, always prefer the **older/lower-versioned device** for testing. This ensures compatibility with a wider range of devices.

**Primary test device**: `330016f5b40463cd` (older Samsung without StrongBox - good for testing hardware security fallbacks)

```bash
# Install to specific device when multiple are connected
~/Android/Sdk/platform-tools/adb -s 330016f5b40463cd install -r androidApp/build/outputs/apk/debug/androidApp-debug.apk

# List connected devices
~/Android/Sdk/platform-tools/adb devices
```
