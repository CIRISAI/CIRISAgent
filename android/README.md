# CIRIS Android - 100% On-Device Packaging

**Architecture**: All Python code and UI run on-device. Only LLM inference is remote.

## What Runs Where

### On-Device (Android App)
- ✅ Python 3.10+ runtime (via Chaquopy)
- ✅ Complete CIRIS Python codebase
- ✅ FastAPI server (localhost:8000)
- ✅ Web UI (bundled assets in WebView)
- ✅ SQLite database
- ✅ All business logic, agents, tools

### Remote (OpenAI-Compatible Endpoint)
- ☁️ LLM inference only
- ☁️ Supports: OpenAI, Together.ai, local LLMs, any OpenAI-compatible API

### NOT Included
- ❌ No ciris.ai cloud components
- ❌ No cloud sync
- ❌ No external dependencies except LLM endpoint

## Build Requirements

- **Android Studio**: Hedgehog (2023.1.1) or newer
- **JDK**: 17 or higher
- **Python**: 3.10 or higher (for building)
- **Gradle**: 8.0+ (included in Android Studio)
- **Min Android SDK**: 24 (Android 7.0+)
- **Target Android SDK**: 34 (Android 14)

## Quick Start

### 1. Install Dependencies

```bash
# Install Python dependencies for Chaquopy
pip install chaquopy

# Ensure you have Android SDK and NDK installed
# Via Android Studio SDK Manager:
# - Android SDK Platform 34
# - Android SDK Build-Tools
# - NDK (Side by side)
```

### 2. Build the APK

```bash
cd android
./gradlew assembleDebug

# APK output: app/build/outputs/apk/debug/app-debug.apk
```

### 3. Install on Device

```bash
adb install app/build/outputs/apk/debug/app-debug.apk
```

### 4. Configure LLM Endpoint

On first launch:
1. Open Settings (menu → Settings)
2. Enter your LLM endpoint:
   - **ciris.ai** (recommended): `https://ciris.ai/v1` + Google Sign-In (see below)
   - **OpenAI**: `https://api.openai.com/v1` + your API key
   - **Together.ai**: `https://api.together.ai/v1` + your API key
   - **Local LLM**: `http://192.168.1.100:8080/v1` + any key
3. Save and restart the app

### 5. ciris.ai LLM Proxy (Recommended for Android)

The ciris.ai proxy uses Google Sign-In for authentication, eliminating the need to manage API keys:

1. **First Launch**: Tap "Sign in with Google" on the setup screen
2. **Authentication**: Complete Google Sign-In flow
3. **Auto-Configuration**: The app automatically configures:
   - Endpoint: `https://ciris.ai/v1`
   - API Key: Your Google ID token (auto-refresh)

**Token Refresh Flow** (handled automatically):

```
┌────────────────────────────────────────────────────────────────┐
│                    Token Refresh Cycle                         │
├────────────────────────────────────────────────────────────────┤
│  1. Python LLM service receives 401 from ciris.ai              │
│  2. Python writes `.token_refresh_needed` signal file          │
│  3. Android TokenRefreshManager detects signal (polls 10s)     │
│  4. Android calls silentSignIn() to get fresh Google ID token  │
│  5. Android updates .env with new OPENAI_API_KEY               │
│  6. Android writes `.config_reload` signal file                │
│  7. Python ResourceMonitor detects signal (polls 1s)           │
│  8. Python reloads .env, emits token_refreshed signal          │
│  9. Python LLM service resets circuit breaker, reinits client  │
│  10. Retry LLM request with fresh token                        │
└────────────────────────────────────────────────────────────────┘
```

**Key Files**:
- `auth/TokenRefreshManager.kt`: Android token refresh polling
- `ciris_engine/logic/services/infrastructure/resource_monitor/service.py`: Signal detection
- `ciris_engine/logic/services/runtime/llm_service/service.py`: Circuit breaker reset

## Architecture Details

### Python Runtime (Chaquopy)

The app uses [Chaquopy](https://chaquo.com/chaquopy/) to embed Python 3.10 in the Android APK:

- **Entry Point**: `mobile_main.py` launches the FastAPI server
- **Dependencies**: Bundled via `pip {}` block in `app/build.gradle`
- **Source Code**: Complete CIRIS codebase included in APK
- **Runtime**: Single-threaded, optimized for <500MB RAM

### FastAPI Server

Runs on `localhost:8000` within the app:

```python
# mobile_main.py
async def start_mobile_server():
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=8000,
        workers=1,  # Low-resource optimization
        log_level="warning",
    )
    server = uvicorn.Server(config)
    await server.serve()
```

### WebView UI

The bundled CIRIS web UI loads in a WebView pointing to `http://127.0.0.1:8000`:

- **Source**: `ciris_engine/gui_static/*` bundled as assets
- **JavaScript**: Fully enabled for interactive UI
- **Storage**: DOM storage and database enabled for client state
- **Navigation**: All links stay within WebView

### LLM Integration

All LLM calls route to the configured remote endpoint:

```kotlin
// SettingsActivity.kt saves these to environment
System.setProperty("OPENAI_API_BASE", apiBase)
System.setProperty("OPENAI_API_KEY", apiKey)
```

Python code reads these via `os.environ` and uses `httpx` to call the remote API.

## Performance Optimization

### Memory (<500MB Target)

- Single Uvicorn worker (`workers=1`)
- No auto-reload
- Minimal logging (`LOG_LEVEL=WARNING`)
- SQLite with WAL mode for concurrency
- No large ML models on-device

### Battery

- Server runs only when app is in foreground
- Disable SSE streaming when backgrounded
- Connection pooling with short timeouts
- Optional: Stop server on background, restart on resume

### Storage

- App size: ~50MB (Python runtime + dependencies)
- Database: <10MB typical usage
- Logs: Rotate daily, max 7 days
- Total footprint: <100MB

## Testing

### Local Testing

```bash
# Run Python server locally to verify
python mobile_main.py
# Visit http://127.0.0.1:8000

# Run Android instrumentation tests
./gradlew connectedAndroidTest
```

### On-Device Smoke Test

```bash
# Via ADB shell
adb shell

# Test API is responding
curl http://127.0.0.1:8000/v1/health

# Test LLM integration
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -d '{"messages":[{"role":"user","content":"ping"}]}'
```

## Build Variants

### Debug Build

```bash
./gradlew assembleDebug
```

- Includes debug symbols
- Enables logging
- No code obfuscation

### Release Build

```bash
./gradlew assembleRelease
```

- Optimized and minified
- ProGuard enabled (configure in `proguard-rules.pro`)
- Requires signing configuration

## Configuration

### Environment Variables

Set in `mobile_main.py` or via Android settings:

- `OPENAI_API_BASE`: LLM endpoint URL (e.g., `https://ciris.ai/v1`)
- `OPENAI_API_KEY`: LLM API key (Google ID Token for ciris.ai, auto-refreshed)
- `CIRIS_OFFLINE_MODE`: Always `true` (no cloud sync)
- `CIRIS_MAX_WORKERS`: `1` (single worker)
- `CIRIS_LOG_LEVEL`: `WARNING` (reduce overhead)
- `CIRIS_HOME`: App data directory (set automatically by `setup_android_environment()`)

**ciris.ai specific** (managed by TokenRefreshManager):
- `.token_refresh_needed`: Signal file written by Python when 401 received
- `.config_reload`: Signal file written by Android after token refresh
- `.env`: Contains OPENAI_API_KEY (Google ID Token) and endpoint config

### SharedPreferences

Persisted settings in `SettingsActivity`:

- `openai_api_base`: User-configured LLM endpoint
- `openai_api_key`: User-configured API key
- `billing_api_url`: CIRISBilling server URL
- `google_user_id`: User's Google account ID (for billing)

## Google Play Billing Integration

The app supports in-app purchases via Google Play for buying CIRIS credits.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Android Device                          │
├─────────────────────────────────────────────────────────────┤
│  CIRIS Agent (on-device)     │  Google Play Billing Client  │
│  - FastAPI @ localhost:8000  │  - BillingClient SDK 7.1.1   │
│  - Python via Chaquopy       │  - Purchase flow UI          │
│  - SQLite DB                 │  - Returns purchaseToken     │
└──────────────┬───────────────┴───────────────┬──────────────┘
               │                               │
               │ LLM Requests                  │ Verify Token
               ▼                               ▼
┌──────────────────────────┐   ┌──────────────────────────────┐
│   Remote LLM Provider    │   │      CIRISBilling API        │
│   (OpenAI-compatible)    │   │   POST /google-play/verify   │
└──────────────────────────┘   └──────────────────────────────┘
```

### Available Products

Products must be configured in Google Play Console with these exact IDs:

| Product ID   | Credits | Description |
|--------------|---------|-------------|
| credits_100  | 100     | 100 Credits |
| credits_250  | 250     | 250 Credits |
| credits_600  | 600     | 600 Credits |

### Purchase Flow

1. User taps "Buy Credits" in the app menu
2. User selects a credit package
3. Google Play purchase flow launches
4. On success, app sends `purchaseToken` to CIRISBilling server
5. Server verifies token with Google Play Developer API
6. Server grants credits to user's account (idempotent)
7. Server acknowledges purchase with Google
8. App displays new balance

### Key Files

- `billing/BillingManager.kt`: Google Play Billing client wrapper
- `billing/BillingApiClient.kt`: HTTP client for CIRISBilling API
- `PurchaseActivity.kt`: Credit purchase UI

### Setup for Production

1. **Google Play Console**: Create products matching the IDs above
2. **CIRISBilling Server**: Deploy with Google Play credentials
3. **App Config**: Set `billing_api_url` to your CIRISBilling URL

### Testing Purchases

Use Google Play's license testing:
1. Add test accounts in Google Play Console
2. Test with sandbox purchases (no real charges)
3. Verify idempotency by re-submitting tokens

## Development & Debugging

### Build Commands

```bash
# Set Java version (required for Gradle)
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64

# Build debug APK
cd /home/emoore/CIRISAgent/android
./gradlew assembleDebug
# Output: app/build/outputs/apk/debug/app-debug.apk

# Build release APK
./gradlew assembleRelease
# Output: app/build/outputs/apk/release/app-release.apk

# Clean build
./gradlew clean assembleRelease
```

### Build & Deploy Scripts

Located in `android/scripts/`, these scripts automate common development tasks:

#### deploy-debug.sh - Quick Debug Deploy

Build and deploy debug APK to connected device:

```bash
cd /home/emoore/CIRISAgent/android

# Full build and deploy (rebuilds web assets + APK)
./scripts/deploy-debug.sh

# Skip web asset rebuild (faster, use when only Kotlin changed)
./scripts/deploy-debug.sh --skip-web

# Skip build, deploy existing APK
./scripts/deploy-debug.sh --skip-web --skip-build

# Skip install, just build
./scripts/deploy-debug.sh --skip-install
```

**Features**:
- Auto-detects ADB path (Windows via WSL or native Linux)
- Sets correct JAVA_HOME
- Copies web assets from Next.js build
- Builds debug APK
- Installs and launches on device
- Shows helpful log commands after deploy

#### full-rebuild.sh - Complete Clean Build

Performs a complete rebuild including web assets and optional pydantic wheels:

```bash
# Standard full rebuild
./scripts/full-rebuild.sh

# Include pydantic wheel rebuild (takes longer)
./scripts/full-rebuild.sh --rebuild-wheels

# Build release instead of debug
./scripts/full-rebuild.sh --release

# Skip web rebuild
./scripts/full-rebuild.sh --skip-web
```

**Build Steps**:
1. Cleans Gradle cache
2. Rebuilds Next.js web UI (`npm run build`)
3. Copies assets to all 3 locations
4. Optionally rebuilds pydantic wheels for ARM64
5. Builds APK (debug or release)

#### pull-device-logs.sh - Collect Device Logs

Pull all logs from device for debugging:

```bash
# Pull all logs to /tmp/ciris-logs/YYYYMMDD_HHMMSS/
./scripts/pull-device-logs.sh

# Live tail Python logs
./scripts/pull-device-logs.sh --live

# Specify output directory
./scripts/pull-device-logs.sh --output /path/to/logs
```

**Collected Files**:
- `logs/` - All Python log files
- `logcat_python.txt` - Python stdout/stderr from logcat
- `logcat_crashes.txt` - AndroidRuntime crash logs
- `logcat_full.txt` - Complete logcat dump
- `databases/` - SQLite databases
- `shared_prefs/` - SharedPreferences XML files
- `app_info.txt` - Device/app version info

**Note**: For debug builds, uses `run-as` to access private app data. Release builds can only pull logcat.

### ADB Commands (Windows via WSL)

```bash
# ADB path on Windows (accessed from WSL)
ADB="/mnt/c/Users/moore/AppData/Local/Android/Sdk/platform-tools/adb.exe"

# List connected devices
$ADB devices -l

# Target specific device (Samsung example)
$ADB -s R5CRC3BWLRZ <command>

# Install APK
$ADB install "$(wslpath -w /home/emoore/CIRISAgent/android/app/build/outputs/apk/release/app-release.apk)"

# Uninstall (clears all data including database)
$ADB uninstall ai.ciris.mobile

# Launch app
$ADB shell monkey -p ai.ciris.mobile -c android.intent.category.LAUNCHER 1

# Clear logcat and start fresh
$ADB logcat -c
```

### Log File Locations (On-Device)

All logs are stored in the app's private data directory:

```
/data/data/ai.ciris.mobile/files/ciris/
├── logs/
│   ├── latest.log              # Symlink to current day's log
│   ├── incidents_latest.log    # Symlink to current day's incidents
│   ├── ciris_agent_YYYYMMDD_HHMMSS.log    # Full application log
│   └── incidents_YYYYMMDD_HHMMSS.log      # Warnings/errors only
├── data/
│   └── ciris_engine.db         # SQLite database
└── .env                        # Configuration (created after setup)
```

### Reading Logs via ADB

```bash
ADB="/mnt/c/Users/moore/AppData/Local/Android/Sdk/platform-tools/adb.exe"
DEVICE="R5CRC3BWLRZ"  # Samsung device ID

# Read latest application log
$ADB -s $DEVICE shell "run-as ai.ciris.mobile cat /data/data/ai.ciris.mobile/files/ciris/logs/latest.log" | tail -200

# Read incidents log (warnings/errors only)
$ADB -s $DEVICE shell "run-as ai.ciris.mobile cat /data/data/ai.ciris.mobile/files/ciris/logs/incidents_latest.log" | tail -100

# Search for specific patterns
$ADB -s $DEVICE shell "run-as ai.ciris.mobile cat /data/data/ai.ciris.mobile/files/ciris/logs/latest.log" | grep -iE "oauth|setup|error"

# List all log files
$ADB -s $DEVICE shell "run-as ai.ciris.mobile ls -la /data/data/ai.ciris.mobile/files/ciris/logs/"
```

### Android Logcat (Native/WebView Logs)

```bash
ADB="/mnt/c/Users/moore/AppData/Local/Android/Sdk/platform-tools/adb.exe"

# All CIRIS-related logs
$ADB logcat -d 2>&1 | grep -i "CIRIS\|CIRISMobile"

# WebView console logs (JavaScript)
$ADB logcat -d 2>&1 | grep "chromium.*CONSOLE"

# Setup wizard logs
$ADB logcat -d 2>&1 | grep "chromium.*Setup"

# Native auth injection logs
$ADB logcat -d 2>&1 | grep "CIRISMobile.*Inject"

# Filter by tag
$ADB logcat -s CIRISMobile:V
```

### Rebuilding Web UI (Next.js Static Assets)

When modifying the web UI, you must rebuild and copy assets:

```bash
# 1. Build Next.js static export
cd /home/emoore/CIRISAgent/android/.web-build/CIRISGUI-Android/apps/agui
npm run build

# 2. Copy to android_gui_static
rm -rf /home/emoore/CIRISAgent/android_gui_static/*
cp -r out/* /home/emoore/CIRISAgent/android_gui_static/

# 3. Copy to Android assets
rm -rf /home/emoore/CIRISAgent/android/app/src/main/assets/public/*
cp -r /home/emoore/CIRISAgent/android_gui_static/* /home/emoore/CIRISAgent/android/app/src/main/assets/public/

# 4. Rebuild APK
cd /home/emoore/CIRISAgent/android
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
./gradlew assembleRelease
```

### Key Source Files

**Android Native (Kotlin)**:
- `app/src/main/java/ai/ciris/mobile/MainActivity.kt` - Main activity, WebView, auth injection
- `app/src/main/java/ai/ciris/mobile/auth/LoginActivity.kt` - Google Sign-In flow
- `app/src/main/java/ai/ciris/mobile/billing/BillingManager.kt` - Google Play Billing

**Python Backend**:
- `ciris_engine/logic/adapters/api/routes/setup.py` - Setup wizard API
- `ciris_engine/logic/adapters/api/routes/auth.py` - OAuth/auth endpoints
- `ciris_engine/logic/setup/first_run.py` - First-run detection

**Web UI (Next.js)**:
- `android/.web-build/CIRISGUI-Android/apps/agui/app/setup/page.tsx` - Setup wizard
- `android/.web-build/CIRISGUI-Android/apps/agui/lib/ciris-sdk/` - TypeScript SDK

### Log Collection Script

Use the script at `/tmp/collect_ciris_logs.sh` to collect all logs for analysis:

```bash
/tmp/collect_ciris_logs.sh
# Logs saved to /tmp/ciris_logs_YYYYMMDD_HHMMSS/
```

## Troubleshooting

### Server Won't Start

**Symptom**: WebView shows "Server Error"

**Solutions**:
1. Check logcat: `adb logcat -s CIRISMobile`
2. Verify Python dependencies in `app/build.gradle`
3. Ensure LLM endpoint is configured
4. Try clean rebuild: `./gradlew clean assembleDebug`

### WebView Shows Blank Screen

**Symptom**: App loads but WebView is empty

**Solutions**:
1. Check server is running: `adb shell curl http://127.0.0.1:8000`
2. Verify UI assets bundled: Check `app/build/intermediates/assets/`
3. Enable WebView debugging: `WebView.setWebContentsDebuggingEnabled(true)`
4. Check Chrome DevTools: `chrome://inspect`

### LLM Calls Failing

**Symptom**: Chat doesn't respond, errors in logs

**Solutions**:
1. Verify endpoint in Settings matches your LLM provider
2. Check API key is valid
3. Test endpoint directly: `curl $OPENAI_API_BASE/models`
4. Check network permissions in AndroidManifest.xml
5. For LAN endpoints, ensure device is on same network

### ciris.ai Token Refresh Issues

**Symptom**: 401 errors persist, LLM calls keep failing

**Solutions**:
1. Check Google Sign-In is active: `adb logcat -s GoogleSignIn`
2. Verify signal files exist: `ls $CIRIS_HOME/.token_refresh_needed .config_reload`
3. Check TokenRefreshManager is polling: `adb logcat -s TokenRefreshManager`
4. Force fresh sign-in: Settings → Sign Out → Sign In Again
5. Check circuit breaker state in ResourceMonitor logs
6. Verify .env has OPENAI_API_KEY after refresh

**Symptom**: Token refreshes but calls still fail

**Solutions**:
1. Check the circuit breaker cooldown (5 minutes for billing errors)
2. Verify LLM client was reinitialized: `adb logcat -s LLMService`
3. Clear app data and re-authenticate

### High Memory Usage

**Symptom**: App crashes or slows down

**Solutions**:
1. Reduce max workers to 1 (should be default)
2. Lower log level to ERROR
3. Clear database: Settings → Clear Data
4. Disable unnecessary adapters in startup
5. Profile with Android Profiler

### Billing Issues

**Symptom**: Purchase fails or credits not added

**Solutions**:
1. Check Google account is signed in
2. Verify billing endpoint in logs: `adb logcat -s CIRISBillingAPI`
3. Test server connectivity: `curl https://billing.ciris.ai/health`
4. Check purchase wasn't already processed (idempotent)
5. For test purchases, use license testers in Play Console

**Symptom**: Products not loading

**Solutions**:
1. Verify products exist in Google Play Console with exact IDs
2. Check Play Billing connection: `adb logcat -s CIRISBilling`
3. Ensure app is signed with correct certificate
4. Wait 24h after creating products for propagation

## Security Considerations

### API Key Storage

- Stored in SharedPreferences (encrypted on API 23+)
- Never logged or transmitted except to configured LLM endpoint
- User responsible for securing their device

### Network Security

For production:
1. Use TLS endpoints only (`https://`)
2. For LAN endpoints, pin certificates in `network_security_config.xml`
3. Disable cleartext traffic except for localhost

### Code Obfuscation

In `proguard-rules.pro`:
```proguard
# Keep Python-Java bridge
-keep class com.chaquo.python.** { *; }

# Keep CIRIS models
-keep class ai.ciris.mobile.** { *; }
```

## Deployment Checklist

- [ ] Configure release signing in `app/build.gradle`
- [ ] Set production LLM endpoint
- [ ] Enable ProGuard for release builds
- [ ] Test on target devices (min SDK 24)
- [ ] Verify memory usage <500MB
- [ ] Test offline capability (LLM remote but UI/logic on-device)
- [ ] Document LLM endpoint setup for users
- [ ] Prepare Google Play Store assets
- [ ] Configure in-app products in Google Play Console
- [ ] Deploy CIRISBilling server with Google Play credentials
- [ ] Test sandbox purchases with license testers
- [ ] Verify purchase verification flow end-to-end

## License

Same as CIRIS: Apache 2.0

## Support

- **Issues**: GitHub Issues
- **Docs**: `/android/README.md` (this file)
- **Source**: `android/` directory

---

**Remember**: 100% of Python and UI runs on-device. Only LLM inference is remote. No ciris.ai cloud components.
