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
   - **OpenAI**: `https://api.openai.com/v1` + your API key
   - **Together.ai**: `https://api.together.ai/v1` + your API key
   - **Local LLM**: `http://192.168.1.100:8080/v1` + any key
3. Save and restart the app

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

- `OPENAI_API_BASE`: LLM endpoint URL
- `OPENAI_API_KEY`: LLM API key
- `CIRIS_OFFLINE_MODE`: Always `true` (no cloud sync)
- `CIRIS_MAX_WORKERS`: `1` (single worker)
- `CIRIS_LOG_LEVEL`: `WARNING` (reduce overhead)

### SharedPreferences

Persisted settings in `SettingsActivity`:

- `openai_api_base`: User-configured LLM endpoint
- `openai_api_key`: User-configured API key

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

### High Memory Usage

**Symptom**: App crashes or slows down

**Solutions**:
1. Reduce max workers to 1 (should be default)
2. Lower log level to ERROR
3. Clear database: Settings → Clear Data
4. Disable unnecessary adapters in startup
5. Profile with Android Profiler

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

## License

Same as CIRIS: Apache 2.0

## Support

- **Issues**: GitHub Issues
- **Docs**: `/android/README.md` (this file)
- **Source**: `android/` directory

---

**Remember**: 100% of Python and UI runs on-device. Only LLM inference is remote. No ciris.ai cloud components.
