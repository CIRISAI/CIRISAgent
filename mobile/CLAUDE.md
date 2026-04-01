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
- **Desktop + test mode**: Tracks element position for automation
- **Desktop + normal mode**: Applies `testTag` only
- **Mobile**: Applies `testTag` only

**Full API documentation:** `desktopApp/src/main/kotlin/ai/ciris/desktop/testing/README.md`

### End-to-End UI Automation Workflow

The desktop test automation server enables fully scripted E2E flows via HTTP.
The `testable()` and `testableClickable()` modifiers apply `testTag` on ALL
platforms, but the HTTP automation server only runs on **desktop** (macOS/Linux/Windows).

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

# 4. Screenshots (java.awt.Robot, test mode only)
curl -X POST http://localhost:8091/screenshot -d '{"path":"/tmp/screenshot.png"}'
curl http://localhost:8091/screenshot > screenshot.png  # Raw PNG

# 5. Mouse click (for dropdowns, popups - real AWT events)
curl -X POST http://localhost:8091/mouse-click -d '{"testTag":"input_llm_provider"}'
curl -X POST http://localhost:8091/mouse-click-xy -d '{"x":600,"y":400}'

# 6. Full E2E test script (wipe → setup wizard → verify)
bash tools/test_desktop_wipe_setup.sh
```

**Endpoints:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/screen` | GET | Current screen name |
| `/tree` | GET | All UI elements with positions |
| `/click` | POST | Click by testTag (programmatic, falls back to mouse) |
| `/mouse-click` | POST | Real AWT mouse click by testTag |
| `/mouse-click-xy` | POST | Real AWT mouse click at coordinates |
| `/input` | POST | Text input to element |
| `/wait` | POST | Wait for element to appear |
| `/screenshot` | GET/POST | Capture window (GET=raw PNG, POST=save to path) |
| `/element/{tag}` | GET | Get element info |
| `/navigate` | POST | Navigate to screen |

**iOS/Android**: `testTag` is applied via `testable()` modifier for use with
platform-native UI testing (Espresso `onView(withTag())`, XCTest accessibility
identifiers). The HTTP server does NOT run on mobile — use `adb` + Espresso
for Android or XCTest for iOS automation.

**Key test tags for common flows:**
- Login: `input_username`, `input_password`, `btn_login_submit`
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
