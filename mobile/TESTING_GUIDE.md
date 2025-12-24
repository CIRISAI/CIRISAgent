# Testing Guide - KMP Mobile with Validation

## Test Philosophy

**Every feature gets tests before shipping to both platforms.**

```
Code without tests = Code that doesn't work on iOS
```

---

## Test Layers

### 1. Shared Unit Tests (`shared/commonTest/`)
- **Run on:** JVM (during development), Android (instrumented), iOS (XCTest)
- **Test:** Business logic, ViewModels, models, utilities
- **Speed:** Fast (milliseconds)
- **Run command:** `./gradlew :shared:test`

### 2. Platform-Specific Tests
- **Android:** `androidApp/src/androidTest/`
- **iOS:** `iosApp/iosAppTests/`
- **Test:** Platform APIs (expect/actual implementations)
- **Speed:** Slower (seconds, requires device/simulator)

### 3. Integration Tests
- **Test:** Full stack (Python + FastAPI + UI)
- **Speed:** Slowest (minutes)
- **Run:** Manual testing on devices

---

## Test Structure

### Shared ViewModel Test Example

```kotlin
// shared/src/commonTest/kotlin/viewmodels/InteractViewModelTest.kt
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.*
import kotlin.test.*

@OptIn(ExperimentalCoroutinesApi::class)
class InteractViewModelTest {

    private val testDispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setup() {
        Dispatchers.setMain(testDispatcher)
    }

    @AfterTest
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun sendMessage_addsUserMessageImmediately() = runTest {
        val fakeApiClient = FakeCIRISApiClient()
        val viewModel = InteractViewModel(fakeApiClient)

        viewModel.onInputTextChanged("Hello")
        viewModel.sendMessage()

        advanceUntilIdle()

        assertTrue(viewModel.messages.value.any {
            it.text == "Hello" && it.type == MessageType.USER
        })
    }

    @Test
    fun sendMessage_clearsInput() = runTest {
        val fakeApiClient = FakeCIRISApiClient()
        val viewModel = InteractViewModel(fakeApiClient)

        viewModel.onInputTextChanged("Test")
        viewModel.sendMessage()

        advanceUntilIdle()

        assertEquals("", viewModel.inputText.value)
    }

    @Test
    fun sendMessage_apiFailure_showsErrorMessage() = runTest {
        val fakeApiClient = FakeCIRISApiClient(shouldFail = true)
        val viewModel = InteractViewModel(fakeApiClient)

        viewModel.onInputTextChanged("Test")
        viewModel.sendMessage()

        advanceUntilIdle()

        assertTrue(viewModel.messages.value.any {
            it.type == MessageType.SYSTEM &&
            it.text.contains("Failed", ignoreCase = true)
        })
    }
}
```

### Fake Test Doubles

```kotlin
// shared/src/commonTest/kotlin/fakes/FakeCIRISApiClient.kt
class FakeCIRISApiClient(
    private val shouldFail: Boolean = false,
    private val delayMs: Long = 100
) : CIRISApiClient("http://localhost:8080", "test-token") {

    private var messagesSent = mutableListOf<String>()

    override suspend fun sendMessage(message: String, channelId: String): InteractResponse {
        delay(delayMs)

        if (shouldFail) {
            throw Exception("Network error")
        }

        messagesSent.add(message)

        return InteractResponse(
            response = "Echo: $message",
            message_id = "msg_${messagesSent.size}",
            reasoning = null
        )
    }

    override suspend fun getSystemStatus(): SystemStatus {
        delay(delayMs)

        if (shouldFail) {
            throw Exception("Network error")
        }

        return SystemStatus(
            status = "healthy",
            cognitive_state = "WORK",
            services_online = 22,
            services_total = 22
        )
    }

    fun getMessagesSent(): List<String> = messagesSent.toList()
}
```

---

## Running Tests

### Shared Tests (JVM)
```bash
# Run all shared tests
./gradlew :shared:test

# Run specific test class
./gradlew :shared:test --tests "StartupViewModelTest"

# Run with coverage
./gradlew :shared:testDebugUnitTest --coverage

# View results
open shared/build/reports/tests/testDebugUnitTest/index.html
```

### Android Tests
```bash
# Connect device or start emulator
adb devices

# Run instrumented tests
./gradlew :androidApp:connectedAndroidTest

# Run specific test
./gradlew :androidApp:connectedAndroidTest -Pandroid.testInstrumentationRunnerArguments.class=MainActivityTest

# View results
open androidApp/build/reports/androidTests/connected/index.html
```

### iOS Tests
```bash
cd iosApp

# Run all tests
xcodebuild test -scheme iosApp -destination 'platform=iOS Simulator,name=iPhone 15'

# Run specific test
xcodebuild test -scheme iosApp -destination 'platform=iOS Simulator,name=iPhone 15' \
  -only-testing:iosAppTests/StartupViewModelTests

# View in Xcode
open iosApp.xcworkspace
```

---

## Test Validation Checklist

### Before Committing Code

- [ ] All shared tests pass: `./gradlew :shared:test`
- [ ] No compilation errors on commonMain
- [ ] No compilation errors on androidMain
- [ ] No compilation errors on iosMain
- [ ] Code formatted: `./gradlew :shared:ktlintFormat`

### Before Merging to Main

- [ ] Android instrumented tests pass
- [ ] Tested on real Android device (not just emulator)
- [ ] iOS tests compile (may not fully pass if platform code not done)
- [ ] Manual smoke test: App launches and core feature works

### Before Production Release

- [ ] Android tests pass on min SDK (Android 7.0)
- [ ] Android tests pass on latest SDK (Android 15)
- [ ] iOS tests pass on min version (iOS 15)
- [ ] iOS tests pass on latest version (iOS 18)
- [ ] Performance tests pass (60 FPS on Android, 50+ FPS on iOS)
- [ ] Memory tests pass (<200MB on Android, <250MB on iOS)

---

## Test Coverage Targets

| Component | Target Coverage | Current |
|-----------|----------------|---------|
| ViewModels | 80% | TBD |
| API Client | 70% | TBD |
| Models | 60% | TBD |
| UI Screens | 50% | TBD |
| Platform Code | 60% | TBD |

**Run coverage:** `./gradlew :shared:testDebugUnitTest --coverage`

---

## Common Testing Patterns

### Testing Coroutines

```kotlin
@OptIn(ExperimentalCoroutinesApi::class)
@Test
fun asyncOperation_updatesState() = runTest {
    val viewModel = MyViewModel()

    viewModel.doAsyncOperation()

    // Advance virtual time
    advanceTimeBy(1000)
    runCurrent()

    assertEquals(ExpectedState, viewModel.state.value)
}
```

### Testing StateFlow

```kotlin
@Test
fun stateFlow_emitsValues() = runTest {
    val viewModel = MyViewModel()
    val emissions = mutableListOf<State>()

    // Collect in background
    val job = launch {
        viewModel.state.collect { emissions.add(it) }
    }

    // Trigger state changes
    viewModel.doSomething()
    advanceUntilIdle()

    // Verify emissions
    assertEquals(listOf(Initial, Loading, Success), emissions)

    job.cancel()
}
```

### Testing Expect/Actual

```kotlin
// In commonTest
@Test
fun platformCode_behavesCorrectly() = runTest {
    val platform = createPlatformDependency()

    val result = platform.doSomething()

    // Test contract, not implementation
    assertNotNull(result)
    assertTrue(result.isValid())
}
```

---

## Debugging Failing Tests

### JVM Tests Failing

```bash
# Run with stack traces
./gradlew :shared:test --stacktrace

# Run single test with debug output
./gradlew :shared:test --tests "MyTest.myMethod" --debug
```

### Android Tests Failing

```bash
# View logcat during test run
adb logcat -c  # Clear
./gradlew :androidApp:connectedAndroidTest
adb logcat | grep -E "TestRunner|AndroidJUnitRunner"

# Re-run single test
./gradlew :androidApp:connectedAndroidTest \
  -Pandroid.testInstrumentationRunnerArguments.class=MyTest#myMethod
```

### iOS Tests Failing

```bash
# View simulator logs
xcrun simctl spawn booted log stream --level debug

# Run with verbose output
xcodebuild test -scheme iosApp -destination 'platform=iOS Simulator,name=iPhone 15' -verbose
```

---

## Continuous Integration

### GitHub Actions Workflow

```yaml
name: KMP Tests

on: [push, pull_request]

jobs:
  test-shared:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-java@v3
        with:
          java-version: 17
      - name: Run shared tests
        run: ./gradlew :shared:test

  test-android:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-java@v3
        with:
          java-version: 17
      - name: Run Android tests
        uses: reactivecircus/android-emulator-runner@v2
        with:
          api-level: 29
          script: ./gradlew :androidApp:connectedAndroidTest

  test-ios:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run iOS tests
        run: |
          cd iosApp
          xcodebuild test -scheme iosApp -destination 'platform=iOS Simulator,name=iPhone 15'
```

---

## Test Utilities

### Test Fixtures

```kotlin
// shared/src/commonTest/kotlin/fixtures/TestFixtures.kt
object TestFixtures {
    fun createChatMessage(
        id: String = "msg_1",
        text: String = "Test message",
        type: MessageType = MessageType.USER
    ): ChatMessage {
        return ChatMessage(
            id = id,
            text = text,
            type = type,
            timestamp = Clock.System.now()
        )
    }

    fun createSystemStatus(
        healthy: Boolean = true,
        servicesOnline: Int = 22
    ): SystemStatus {
        return SystemStatus(
            status = if (healthy) "healthy" else "degraded",
            cognitive_state = "WORK",
            services_online = servicesOnline,
            services_total = 22
        )
    }
}
```

### Assertion Helpers

```kotlin
// shared/src/commonTest/kotlin/utils/Assertions.kt
fun assertEventually(
    timeoutMs: Long = 5000,
    intervalMs: Long = 100,
    message: String = "Condition never became true",
    condition: () -> Boolean
) = runBlocking {
    val startTime = System.currentTimeMillis()
    while (System.currentTimeMillis() - startTime < timeoutMs) {
        if (condition()) return@runBlocking
        delay(intervalMs)
    }
    fail(message)
}

// Usage:
assertEventually { viewModel.isReady.value == true }
```

---

## Performance Testing

### Memory Usage

```kotlin
@Test
fun viewModel_doesNotLeak() = runTest {
    val runtime = Runtime.getRuntime()
    runtime.gc()
    val before = runtime.totalMemory() - runtime.freeMemory()

    repeat(100) {
        val viewModel = InteractViewModel(FakeCIRISApiClient())
        viewModel.sendMessage()
    }

    runtime.gc()
    val after = runtime.totalMemory() - runtime.freeMemory()

    val leaked = after - before
    assertTrue(leaked < 10_000_000) // Less than 10MB leaked
}
```

### Response Time

```kotlin
@Test
fun apiCall_respondsUnder500ms() = runTest {
    val client = CIRISApiClient("http://localhost:8080", "token")

    val startTime = System.currentTimeMillis()
    client.sendMessage("Hello")
    val duration = System.currentTimeMillis() - startTime

    assertTrue(duration < 500)
}
```

---

## Next Steps

1. **Write tests first** - TDD ensures both platforms work
2. **Run tests frequently** - `./gradlew :shared:test` after every change
3. **Fix failing tests immediately** - Don't let them accumulate
4. **Add tests for bugs** - Regression prevention
5. **Review coverage** - Target 80% for ViewModels

**Test early, test often, ship with confidence! 🚀**
