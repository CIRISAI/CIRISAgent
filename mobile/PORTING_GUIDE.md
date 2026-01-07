# Porting Guide - Android to KMP Shared Code

## Strategy: Port with Tests

**Rule:** Every feature gets tests as it's ported. Test-driven migration ensures both platforms work correctly.

---

## Core Principle: Shared First, Platform When Necessary

```kotlin
// ❌ DON'T: Copy Android code directly
android/app/.../SomeActivity.kt → androidApp/.../SomeActivity.kt

// ✅ DO: Extract to shared, test, then wire to platform
android/app/.../SomeActivity.kt →
    shared/commonMain/.../SomeViewModel.kt (business logic + tests)
    shared/commonMain/.../SomeScreen.kt (UI + tests)
    androidApp/.../MainActivity.kt (thin wrapper)
    iosApp/.../ContentView.swift (thin wrapper)
```

---

## What to Port Where

### shared/commonMain/ (95% of code)
- ✅ **API clients** - All HTTP/networking
- ✅ **ViewModels** - All business logic
- ✅ **UI Screens** - All Compose UI
- ✅ **Models** - All data classes
- ✅ **Utilities** - String formatting, date handling, etc.

### androidMain/ (2.5% of code)
- ❌ **Platform APIs only:**
  - Google Play Billing
  - Google Sign-In
  - EncryptedSharedPreferences
  - Chaquopy Python runtime

### iosMain/ (2.5% of code)
- ❌ **Platform APIs only:**
  - StoreKit 2 billing
  - Sign in with Apple
  - Keychain
  - Python C API runtime

---

## Porting Process with Tests

### Step 1: Identify Feature

Example: Python runtime management from MainActivity.kt

### Step 2: Create Shared Interface

```kotlin
// shared/src/commonMain/kotlin/platform/PythonRuntime.kt
expect class PythonRuntime {
    /**
     * Initialize Python interpreter
     * @param pythonHome Path to Python installation
     */
    suspend fun initialize(pythonHome: String): Result<Unit>

    /**
     * Start CIRIS FastAPI server
     * @return Server URL
     */
    suspend fun startServer(): Result<String>

    /**
     * Check if server is healthy
     */
    suspend fun checkHealth(): Result<Boolean>

    /**
     * Shutdown Python runtime
     */
    fun shutdown()
}
```

### Step 3: Write Tests FIRST

```kotlin
// shared/src/commonTest/kotlin/platform/PythonRuntimeTest.kt
class PythonRuntimeTest {
    @Test
    fun initialize_succeeds() = runTest {
        val runtime = PythonRuntime()
        val result = runtime.initialize("/path/to/python")
        assertTrue(result.isSuccess)
    }

    @Test
    fun startServer_returnsUrl() = runTest {
        val runtime = PythonRuntime()
        runtime.initialize("/path/to/python")

        val result = runtime.startServer()
        assertTrue(result.isSuccess)
        assertEquals("http://localhost:8080", result.getOrNull())
    }

    @Test
    fun checkHealth_returnsTrueWhenHealthy() = runTest {
        val runtime = PythonRuntime()
        runtime.initialize("/path/to/python")
        runtime.startServer()

        delay(2000) // Wait for server startup

        val result = runtime.checkHealth()
        assertTrue(result.isSuccess)
        assertTrue(result.getOrNull() == true)
    }
}
```

### Step 4: Implement Android Version

```kotlin
// shared/src/androidMain/kotlin/platform/PythonRuntime.android.kt
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

actual class PythonRuntime {
    private var python: Python? = null
    private var serverStarted = false

    actual suspend fun initialize(pythonHome: String): Result<Unit> {
        return try {
            if (!Python.isStarted()) {
                Python.start(AndroidPlatform(getApplicationContext()))
            }
            python = Python.getInstance()
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    actual suspend fun startServer(): Result<String> {
        return try {
            val py = python ?: return Result.failure(Exception("Python not initialized"))

            // Call mobile_main.py
            val mobileMain = py.getModule("mobile_main")
            mobileMain.callAttr("start_ciris_runtime")

            serverStarted = true
            Result.success("http://localhost:8080")
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    actual suspend fun checkHealth(): Result<Boolean> {
        return try {
            val url = URL("http://localhost:8080/v1/system/health")
            val conn = url.openConnection() as HttpURLConnection
            conn.connectTimeout = 5000
            conn.requestMethod = "GET"

            val healthy = conn.responseCode == 200
            conn.disconnect()

            Result.success(healthy)
        } catch (e: Exception) {
            Result.success(false) // Not healthy yet
        }
    }

    actual fun shutdown() {
        // Python runtime persists for app lifetime
        serverStarted = false
    }
}
```

### Step 5: Create Mock for iOS (Initial)

```kotlin
// shared/src/iosMain/kotlin/platform/PythonRuntime.ios.kt
actual class PythonRuntime {
    actual suspend fun initialize(pythonHome: String): Result<Unit> {
        // TODO: Implement Python C API integration
        return Result.failure(Exception("iOS Python runtime not yet implemented"))
    }

    actual suspend fun startServer(): Result<String> {
        return Result.failure(Exception("iOS Python runtime not yet implemented"))
    }

    actual suspend fun checkHealth(): Result<Boolean> {
        return Result.success(false)
    }

    actual fun shutdown() {
        // TODO
    }
}
```

### Step 6: Run Tests

```bash
# Run shared tests on JVM
./gradlew :shared:test

# Run on Android device
./gradlew :shared:connectedAndroidTest

# Run on iOS (when implemented)
xcodebuild test -scheme shared -destination 'platform=iOS Simulator,name=iPhone 15'
```

### Step 7: Create Shared ViewModel

```kotlin
// shared/src/commonMain/kotlin/viewmodels/StartupViewModel.kt
class StartupViewModel(
    private val pythonRuntime: PythonRuntime,
    private val apiClient: CIRISApiClient
) : ViewModel() {

    private val _phase = MutableStateFlow(StartupPhase.INITIALIZING)
    val phase: StateFlow<StartupPhase> = _phase.asStateFlow()

    private val _servicesOnline = MutableStateFlow(0)
    val servicesOnline: StateFlow<Int> = _servicesOnline.asStateFlow()

    private val _totalServices = MutableStateFlow(22)
    val totalServices: StateFlow<Int> = _totalServices.asStateFlow()

    private val _errorMessage = MutableStateFlow<String?>(null)
    val errorMessage: StateFlow<String?> = _errorMessage.asStateFlow()

    suspend fun startCIRIS() {
        _phase.value = StartupPhase.INITIALIZING_PYTHON

        // Initialize Python runtime
        val initResult = pythonRuntime.initialize("/path/to/python")
        if (initResult.isFailure) {
            _errorMessage.value = "Failed to initialize Python: ${initResult.exceptionOrNull()?.message}"
            _phase.value = StartupPhase.ERROR
            return
        }

        _phase.value = StartupPhase.STARTING_SERVER

        // Start FastAPI server
        val serverResult = pythonRuntime.startServer()
        if (serverResult.isFailure) {
            _errorMessage.value = "Failed to start server: ${serverResult.exceptionOrNull()?.message}"
            _phase.value = StartupPhase.ERROR
            return
        }

        _phase.value = StartupPhase.WAITING_FOR_SERVICES

        // Poll for service health
        var attempts = 0
        while (attempts < 60) { // 60 attempts = 2 minutes max
            delay(2000)

            val healthResult = pythonRuntime.checkHealth()
            if (healthResult.isSuccess && healthResult.getOrNull() == true) {
                // Get detailed telemetry
                val telemetry = apiClient.getTelemetry()
                _servicesOnline.value = telemetry.services_online
                _totalServices.value = telemetry.services_total

                if (telemetry.services_online == telemetry.services_total) {
                    _phase.value = StartupPhase.READY
                    return
                }
            }

            attempts++
        }

        _errorMessage.value = "Timeout waiting for services"
        _phase.value = StartupPhase.ERROR
    }
}

enum class StartupPhase {
    INITIALIZING,
    INITIALIZING_PYTHON,
    STARTING_SERVER,
    WAITING_FOR_SERVICES,
    READY,
    ERROR
}
```

### Step 8: Test ViewModel

```kotlin
// shared/src/commonTest/kotlin/viewmodels/StartupViewModelTest.kt
class StartupViewModelTest {
    @Test
    fun startCIRIS_successfulStartup_phasesCorrect() = runTest {
        val mockRuntime = FakePythonRuntime(healthy = true)
        val mockApiClient = FakeCIRISApiClient(servicesOnline = 22)
        val viewModel = StartupViewModel(mockRuntime, mockApiClient)

        viewModel.startCIRIS()

        assertEquals(StartupPhase.READY, viewModel.phase.value)
        assertEquals(22, viewModel.servicesOnline.value)
        assertNull(viewModel.errorMessage.value)
    }

    @Test
    fun startCIRIS_pythonFails_showsError() = runTest {
        val mockRuntime = FakePythonRuntime(initFails = true)
        val mockApiClient = FakeCIRISApiClient()
        val viewModel = StartupViewModel(mockRuntime, mockApiClient)

        viewModel.startCIRIS()

        assertEquals(StartupPhase.ERROR, viewModel.phase.value)
        assertNotNull(viewModel.errorMessage.value)
    }
}

// Test doubles
class FakePythonRuntime(
    private val healthy: Boolean = true,
    private val initFails: Boolean = false
) : PythonRuntime() {
    override suspend fun initialize(pythonHome: String): Result<Unit> {
        return if (initFails) Result.failure(Exception("Init failed"))
        else Result.success(Unit)
    }

    override suspend fun startServer(): Result<String> {
        return Result.success("http://localhost:8080")
    }

    override suspend fun checkHealth(): Result<Boolean> {
        return Result.success(healthy)
    }

    override fun shutdown() {}
}
```

### Step 9: Create Shared UI

```kotlin
// shared/src/commonMain/kotlin/ui/screens/StartupScreen.kt
@Composable
fun StartupScreen(viewModel: StartupViewModel) {
    val phase by viewModel.phase.collectAsState()
    val servicesOnline by viewModel.servicesOnline.collectAsState()
    val totalServices by viewModel.totalServices.collectAsState()
    val errorMessage by viewModel.errorMessage.collectAsState()

    LaunchedEffect(Unit) {
        viewModel.startCIRIS()
    }

    when (phase) {
        StartupPhase.ERROR -> ErrorView(errorMessage)
        StartupPhase.READY -> {
            // Navigate to main app
        }
        else -> {
            SplashView(
                phase = phase,
                servicesOnline = servicesOnline,
                totalServices = totalServices
            )
        }
    }
}

@Composable
private fun SplashView(
    phase: StartupPhase,
    servicesOnline: Int,
    totalServices: Int
) {
    Column(
        modifier = Modifier.fillMaxSize(),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Text(
            text = "CIRIS",
            style = MaterialTheme.typography.displayLarge
        )

        Spacer(Modifier.height(32.dp))

        // Service lights grid (22 lights)
        ServiceLightsGrid(servicesOnline, totalServices)

        Spacer(Modifier.height(16.dp))

        Text(text = phase.name)
        Text(text = "$servicesOnline / $totalServices services online")
    }
}
```

### Step 10: Wire to Android

```kotlin
// androidApp/src/main/kotlin/MainActivity.kt
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContent {
            CIRISTheme {
                val pythonRuntime = remember { PythonRuntime() }
                val apiClient = remember { CIRISApiClient() }
                val viewModel = remember { StartupViewModel(pythonRuntime, apiClient) }

                val phase by viewModel.phase.collectAsState()

                when (phase) {
                    StartupPhase.READY -> {
                        // Show main app
                        CIRISApp(
                            accessToken = "token",
                            baseUrl = "http://localhost:8080"
                        )
                    }
                    else -> {
                        // Show startup screen
                        StartupScreen(viewModel)
                    }
                }
            }
        }
    }
}
```

### Step 11: Validate on Device

```bash
# Build
./gradlew :androidApp:assembleDebug

# Install
adb install androidApp/build/outputs/apk/debug/androidApp-debug.apk

# Monitor logs
adb logcat | grep -E "CIRIS|Python|StartupViewModel"

# Expected behavior:
# 1. App launches
# 2. Splash screen shows "INITIALIZING_PYTHON"
# 3. Switches to "STARTING_SERVER"
# 4. Switches to "WAITING_FOR_SERVICES"
# 5. Lights turn on one by one (0/22 → 22/22)
# 6. Switches to "READY"
# 7. Main app appears
```

---

## Test Plan Checklist

For each ported feature:

### Unit Tests (shared/commonTest/)
- [ ] Happy path works
- [ ] Error handling works
- [ ] Edge cases handled
- [ ] State management correct

### Android Integration Tests (androidApp/androidTest/)
- [ ] Feature works on real Android device
- [ ] Platform-specific code works (Chaquopy, Play Services, etc.)
- [ ] UI appears correctly
- [ ] Performance acceptable

### iOS Integration Tests (iosApp/iosAppTests/)
- [ ] Feature works on iOS simulator
- [ ] Platform-specific code works (Python C API, StoreKit, etc.)
- [ ] UI appears correctly
- [ ] Performance acceptable

### Manual Testing
- [ ] Test on Android 7.0 (min SDK)
- [ ] Test on Android 15 (latest)
- [ ] Test on iOS 15 (min version)
- [ ] Test on iOS 18 (latest)
- [ ] Test on low-end device (performance)

---

## Features to Port (Priority Order)

### 1. Python Runtime Management ⚡ CRITICAL
**From:** `android/app/.../MainActivity.kt` lines 150-400
**To:** `shared/commonMain/platform/PythonRuntime.kt`
**Tests:** Initialize, start server, check health, shutdown

### 2. Startup State Management ⚡ CRITICAL
**From:** `android/app/.../MainActivity.kt` StartupPhase enum
**To:** `shared/commonMain/viewmodels/StartupViewModel.kt`
**Tests:** Phase transitions, service counting, error handling

### 3. Service Health Monitoring ✅ DONE
**From:** `android/app/.../MainActivity.kt` health check logic
**To:** `shared/commonMain/api/CIRISApiClient.kt`
**Tests:** Already has getTelemetry()

### 4. Splash Screen UI 🎨 UI
**From:** `android/app/res/layout/activity_main.xml` + splash logic
**To:** `shared/commonMain/ui/screens/StartupScreen.kt`
**Tests:** UI state reflects ViewModel, lights animate correctly

### 5. Settings Management 📱 FEATURE
**From:** `android/app/.../SettingsActivity.kt`
**To:**
- `shared/commonMain/viewmodels/SettingsViewModel.kt`
- `shared/commonMain/ui/screens/SettingsScreen.kt`
- `shared/*/platform/SecureStorage.kt` (expect/actual)
**Tests:** Save settings, load settings, secure storage works

### 6. Purchase Flow 💰 FEATURE
**From:** `android/app/.../PurchaseActivity.kt` + billing/
**To:**
- `shared/commonMain/viewmodels/PurchaseViewModel.kt`
- `shared/commonMain/ui/screens/PurchaseScreen.kt`
- `shared/*/platform/BillingClient.kt` (expect/actual)
**Tests:** Query products, purchase, verify, restore

### 7. Authentication 🔐 FEATURE
**From:** `android/app/auth/`
**To:**
- `shared/commonMain/viewmodels/AuthViewModel.kt`
- `shared/commonMain/ui/screens/LoginScreen.kt`
- `shared/*/platform/AuthProvider.kt` (expect/actual)
**Tests:** Login, logout, token refresh, OAuth flow

### 8. Runtime Monitor 📊 FEATURE
**From:** `android/app/.../RuntimeActivity.kt`
**To:**
- `shared/commonMain/viewmodels/RuntimeViewModel.kt`
- `shared/commonMain/ui/screens/RuntimeScreen.kt`
**Tests:** Service list, health updates, restart controls

---

## Testing Commands

```bash
# Shared unit tests (runs on JVM)
./gradlew :shared:test

# Android instrumented tests
./gradlew :androidApp:connectedAndroidTest

# iOS tests (when implemented)
cd iosApp && xcodebuild test -scheme iosApp -destination 'platform=iOS Simulator,name=iPhone 15'

# Run all tests
./gradlew test && ./gradlew connectedAndroidTest
```

---

## Validation Criteria

Before marking a feature as "ported":

1. ✅ **Shared code compiles** for commonMain, androidMain, iosMain
2. ✅ **Unit tests pass** on JVM
3. ✅ **Android tests pass** on real device
4. ✅ **Feature works** identically to original Android app
5. ✅ **No regressions** in existing features
6. ⏳ **iOS compiles** (may not be functional yet)
7. ⏳ **iOS tests pass** (when iOS platform code is implemented)

---

## Next: Start Porting

1. **Read next:** `TESTING_GUIDE.md` - Detailed test patterns
2. **Then start:** Port Python runtime management with tests
3. **Validate:** Run tests on every change
4. **Ship:** When all tests pass, feature is ported

**Remember:** Tests first, implementation second. This ensures both platforms work correctly from day one.
