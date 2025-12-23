# CIRIS Mobile Kotlin Multiplatform Migration Plan

## Executive Summary

**Goal:** Unify Android and iOS mobile apps using Kotlin Multiplatform + Compose Multiplatform

**Status:** Ready to execute - scaffold complete, immediate cutover possible

**License:** ✅ Apache 2.0 (Compose) compatible with AGPL 3.0 (CIRIS)

**Timeline:** Immediate start - parallel development with existing Android app

---

## Project Structure

```
mobile/
├── shared/                           # KMP shared code (Android + iOS)
│   ├── src/
│   │   ├── commonMain/kotlin/       # Shared UI + Business Logic
│   │   │   ├── api/                 # ✅ CIRISApiClient (replaces OkHttp)
│   │   │   ├── models/              # ✅ Data models
│   │   │   ├── viewmodels/          # ✅ InteractViewModel
│   │   │   ├── ui/screens/          # ✅ InteractScreen (Compose)
│   │   │   └── CIRISApp.kt          # ✅ Main app entry
│   │   ├── androidMain/kotlin/      # Android-specific
│   │   └── iosMain/kotlin/          # iOS-specific
│   └── build.gradle.kts             # ✅ Created
├── androidApp/                       # Android wrapper
│   ├── build.gradle                 # ✅ Created (with Chaquopy)
│   └── src/main/kotlin/             # Thin wrapper
└── iosApp/                          # iOS wrapper (native Swift)
    └── iosApp/                      # Swift UI wrapper
```

---

## Phase 1: IMMEDIATE (Days 1-3) - Core Infrastructure

### ✅ COMPLETED
- [x] Project scaffold created
- [x] Gradle configuration (root, shared, androidApp)
- [x] Shared models (ChatMessage, SystemStatus, Auth)
- [x] CIRISApiClient (Ktor - replaces OkHttp)
- [x] InteractViewModel (shared business logic)
- [x] InteractScreen (Compose UI - replaces InteractActivity.kt + XML)

### 🔧 TODO: Build System
- [ ] Copy `android/app/wheels/` to `mobile/androidApp/wheels/` (pydantic-core wheels)
- [ ] Test Gradle build: `cd mobile && ./gradlew :shared:build`
- [ ] Test Android build: `./gradlew :androidApp:assembleDebug`
- [ ] Verify Chaquopy Python runtime initialization
- [ ] Test CIRIS engine startup (FastAPI on localhost:8080)

### 🔧 TODO: Android Wrapper App
- [ ] Create `androidApp/src/main/kotlin/ai/ciris/mobile/MainActivity.kt`
  - Initialize Python runtime (Chaquopy)
  - Show startup splash with 22 service lights
  - Launch Compose UI when ready
  - Handle authentication (Google Sign-In)

```kotlin
// mobile/androidApp/src/main/kotlin/ai/ciris/mobile/MainActivity.kt
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Initialize Python (from original android/app MainActivity.kt)
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }

        // Start CIRIS runtime (existing logic)
        startCIRISRuntime()

        // Launch Compose UI
        setContent {
            CIRISApp(
                accessToken = getAccessToken(),
                baseUrl = "http://localhost:8080"
            )
        }
    }
}
```

- [ ] Copy Python initialization logic from `android/app/src/main/java/ai/ciris/mobile/MainActivity.kt:150-400`
- [ ] Copy splash screen animation from `android/app/src/main/java/ai/ciris/mobile/MainActivity.kt:95-135`
- [ ] Copy auth logic from `android/app/src/main/java/ai/ciris/mobile/auth/`

---

## Phase 2: PRIORITY (Days 4-7) - Migrate Core Screens

### Day 4: Settings Screen
**From:** `android/app/src/main/java/ai/ciris/mobile/SettingsActivity.kt` + `activity_settings.xml`
**To:** `shared/src/commonMain/kotlin/ai/ciris/mobile/shared/ui/screens/SettingsScreen.kt`

- [ ] Create SettingsViewModel
- [ ] Create SettingsScreen (Compose)
- [ ] Implement preferences (expect/actual for storage)
  - Android: EncryptedSharedPreferences
  - iOS: UserDefaults (Keychain for secrets)
- [ ] Migrate settings options:
  - LLM API key management
  - Model selection
  - App theme
  - Logout

**Estimate:** 4-6 hours

### Day 5: Purchase Flow
**From:** `android/app/src/main/java/ai/ciris/mobile/PurchaseActivity.kt` + `activity_purchase.xml`
**To:** `shared/src/commonMain/kotlin/ai/ciris/mobile/shared/ui/screens/PurchaseScreen.kt`

- [ ] Create BillingClient abstraction (expect/actual)
  ```kotlin
  // shared/src/commonMain/kotlin/platform/BillingClient.kt
  expect class BillingClient {
      suspend fun queryProducts(): List<Product>
      suspend fun purchase(productId: String): PurchaseResult
  }

  // shared/src/androidMain/kotlin/platform/BillingClient.android.kt
  actual class BillingClient {
      // Use Google Play Billing
  }

  // shared/src/iosMain/kotlin/platform/BillingClient.ios.kt
  actual class BillingClient {
      // Use StoreKit 2
  }
  ```
- [ ] Create PurchaseViewModel
- [ ] Create PurchaseScreen (Compose)
- [ ] Product listing (100, 250, 600 credits)
- [ ] Purchase flow
- [ ] Server verification via CIRISApiClient

**Estimate:** 8-10 hours

### Days 6-7: Setup Wizard
**From:**
- `android/app/src/main/java/ai/ciris/mobile/setup/SetupWizardActivity.kt`
- `android/app/src/main/java/ai/ciris/mobile/setup/SetupWelcomeFragment.kt`
- `android/app/src/main/java/ai/ciris/mobile/setup/SetupLlmFragment.kt`
- `android/app/src/main/java/ai/ciris/mobile/setup/SetupConfirmFragment.kt`

**To:** `shared/src/commonMain/kotlin/ai/ciris/mobile/shared/ui/screens/setup/`

- [ ] Create SetupViewModel
- [ ] Create SetupWelcomeScreen
- [ ] Create SetupLlmScreen (API key input, provider selection)
- [ ] Create SetupConfirmScreen
- [ ] Navigation flow using Compose Navigation
- [ ] Save setup state to secure storage

**Estimate:** 6-8 hours

---

## Phase 3: ADVANCED (Days 8-12) - Complex Features

### Days 8-9: Runtime Monitor
**From:** `android/app/src/main/java/ai/ciris/mobile/RuntimeActivity.kt` + animations

- [ ] Create RuntimeViewModel
- [ ] Create RuntimeScreen (Compose)
- [ ] Implement 22-service light grid animation
  ```kotlin
  @Composable
  fun ServiceLightsGrid(services: Map<String, ServiceHealth>) {
      LazyVerticalGrid(columns = GridCells.Fixed(11)) {
          items(services.entries.toList()) { (name, health) ->
              ServiceLight(
                  name = name,
                  healthy = health.healthy,
                  animated = true
              )
          }
      }
  }
  ```
- [ ] Real-time service health polling
- [ ] Console output view (scrolling logs)
- [ ] Prep phase (6 lights for pydantic-core setup)

**Estimate:** 8-10 hours

### Days 10-11: Telemetry Dashboard
**From:** `android/app/src/main/java/ai/ciris/mobile/TelemetryFragment.kt`

- [ ] Create TelemetryViewModel
- [ ] Create TelemetryScreen (Compose)
- [ ] Service health cards
- [ ] Metrics display (uptime, cognitive state, memory usage)
- [ ] Consider: `io.github.koalaplot:koalaplot-core:0.5.1` for charts

**Estimate:** 6-8 hours

### Day 12: Sessions View
**From:** `android/app/src/main/java/ai/ciris/mobile/SessionsFragment.kt`

- [ ] Create SessionsViewModel
- [ ] Create SessionsScreen (Compose)
- [ ] List conversation sessions
- [ ] Session selection and restoration

**Estimate:** 4-6 hours

---

## Phase 4: iOS NATIVE (Days 13-17) - iOS App

### Day 13-14: iOS Python Runtime
**Critical:** Replace BeeWare/Toga with native Swift + Python C API

- [ ] Create `mobile/iosApp/` Xcode project
- [ ] Integrate KMP shared framework
  ```swift
  // ContentView.swift
  import SwiftUI
  import shared

  struct ContentView: View {
      var body: some View {
          ComposeView()
              .ignoresSafeArea()
      }
  }

  struct ComposeView: UIViewControllerRepresentable {
      func makeUIViewController(context: Context) -> UIViewController {
          return MainKt.MainViewController()
      }
      func updateUIViewController(_ uiViewController: UIViewController, context: Context) {}
  }
  ```
- [ ] Embed Python runtime via Python C API (NOT BeeWare)
  - Link against Python framework
  - Initialize Python interpreter
  - Set PYTHONPATH to bundled CIRIS engine
  - Start FastAPI server on localhost:8080
- [ ] Test CIRIS runtime startup on iOS simulator
- [ ] Test on physical iOS device

**Estimate:** 16-20 hours (most complex part)

**Resources needed:**
- Python C API documentation
- iOS Python embedding examples
- Test devices (iPhone 12+, iOS 15+)

### Days 15-16: iOS Platform Features

- [ ] Implement iOS BillingClient (StoreKit 2)
  ```swift
  // BillingClient.ios.swift
  import StoreKit

  @available(iOS 15.0, *)
  class IOSBillingClient {
      func queryProducts() async -> [Product] {
          let products = try? await Product.products(for: productIds)
          return products ?? []
      }
  }
  ```
- [ ] Implement iOS secure storage (Keychain)
- [ ] Implement Sign in with Apple
- [ ] Test purchase flow end-to-end

**Estimate:** 10-12 hours

### Day 17: iOS Polish

- [ ] Test all screens on iOS
- [ ] Fix iOS-specific bugs
- [ ] Platform-specific UI adjustments (safe areas, navigation)
- [ ] Performance profiling (ensure >50 FPS scrolling)

**Estimate:** 8 hours

---

## Phase 5: CUTOVER (Days 18-20) - Production Migration

### Day 18: Parallel Testing

- [ ] Run QA tests on both old Android app and new KMP app
  ```bash
  # Old app
  cd android && ./gradlew assembleDebug && ./gradlew connectedAndroidTest

  # New KMP app
  cd mobile && ./gradlew :androidApp:assembleDebug && ./gradlew :androidApp:connectedAndroidTest
  ```
- [ ] Compare performance (startup time, memory, battery)
- [ ] Verify feature parity (checklist below)
- [ ] Test on multiple devices (Android 7-15, iOS 15-18)

### Day 19: Alpha Release

- [ ] Deploy KMP Android app to internal testing track (Google Play)
- [ ] Deploy iOS app to TestFlight
- [ ] Gather feedback from alpha testers
- [ ] Fix critical bugs

### Day 20: Production Cutover

- [ ] Bump version: `2.0.0` (KMP unified version)
- [ ] Update release notes (highlight unified codebase)
- [ ] Deploy to production (Google Play + App Store)
- [ ] Monitor crash reports (Firebase Crashlytics)
- [ ] Keep old `android/` codebase for 1 release cycle (rollback safety)

---

## Feature Parity Checklist

### ✅ Authentication
- [ ] Google Sign-In (Android)
- [ ] Sign in with Apple (iOS)
- [ ] Token refresh management
- [ ] Secure credential storage
- [ ] Logout

### ✅ Chat Interface
- [x] Message sending/receiving (InteractScreen created)
- [ ] Real-time status updates
- [ ] Reasoning display
- [ ] Conversation history (20 messages)
- [ ] Agent status indicator
- [ ] Graceful/emergency shutdown controls

### ✅ Billing
- [ ] Product listing (100, 250, 600 credits)
- [ ] Purchase flow (Google Play / App Store)
- [ ] Server-side verification
- [ ] Purchase history
- [ ] Credit display

### ✅ Settings
- [ ] LLM API key management
- [ ] Model selection
- [ ] App preferences
- [ ] Account management
- [ ] Logout

### ✅ Runtime Management
- [ ] 22-service health monitoring
- [ ] Startup animation (lights)
- [ ] Console logs
- [ ] Service restart controls
- [ ] Error handling

### ✅ Setup Wizard
- [ ] First-run onboarding
- [ ] LLM configuration
- [ ] API key entry
- [ ] Setup completion

### ✅ Additional Features
- [ ] Telemetry dashboard
- [ ] Session history
- [ ] Offline mode
- [ ] Deep linking (OAuth callbacks)

---

## Migration Strategy: Old vs New

### Parallel Development (Recommended)

**Keep `android/` running while building `mobile/`:**

```
CIRISAgent/
├── android/              # OLD - Keep for now
│   └── app/
│       ├── build.gradle  # v1.7.42
│       └── src/
├── mobile/               # NEW - Build in parallel
│   ├── shared/
│   ├── androidApp/       # v2.0.0
│   └── iosApp/
```

**Advantages:**
- Zero risk to production Android app
- Validate KMP approach before committing
- Easy rollback if issues arise
- Compare performance side-by-side

**When to remove `android/`:**
- After 2.0.0 is stable in production (1-2 release cycles)
- After iOS app is also in production
- After confirming no regression in metrics

### Direct Cutover (Aggressive)

**Replace `android/` immediately:**
```bash
cd /home/user/CIRISAgent
mv android android_backup_v1.7.42
mv mobile android
```

**Advantages:**
- Faster unified development
- Cleaner repo structure
- Forces commitment to KMP

**Disadvantages:**
- ❌ Risky - no easy rollback
- ❌ Breaks existing workflows
- ❌ High stakes for first KMP release

**Recommendation:** Use parallel development first.

---

## Code Reuse Analysis

### Already Shared (99%)
- ✅ **CIRIS Engine:** 640 Python files (100% reused)
- ✅ **Python Runtime:** Chaquopy (Android) + Python C API (iOS) - same codebase

### Now Shared with KMP (90%)
- ✅ **API Client:** CIRISApiClient (Ktor) - replaces Android OkHttp
- ✅ **Models:** All data classes (ChatMessage, SystemStatus, Auth, etc.)
- ✅ **ViewModels:** Business logic (InteractViewModel, etc.)
- ✅ **UI:** Compose screens (InteractScreen, SettingsScreen, etc.)

### Platform-Specific (10%)
- **Android:**
  - Google Play Billing client
  - Google Sign-In integration
  - EncryptedSharedPreferences
  - Play Integrity API
  - Chrome Custom Tabs (OAuth)

- **iOS:**
  - StoreKit 2 billing client
  - Sign in with Apple
  - Keychain storage
  - Python C API embedding
  - Safari View Controller (OAuth)

### Code Reduction

| Component | Before (Lines) | After (Lines) | Savings |
|-----------|----------------|---------------|---------|
| **UI Code** | 11K Android + 5K WebView = 16K | 6K shared | **62%** |
| **API Client** | 2K Android OkHttp | 500 shared Ktor | **75%** |
| **ViewModels** | 3K Android | 1.5K shared | **50%** |
| **Total Platform Code** | ~16K Android | ~8K (6K shared + 2K platform) | **50%** |

**And iOS gets it all for FREE!**

---

## Build Commands

### Shared Module
```bash
cd mobile
./gradlew :shared:build                    # Build shared code
./gradlew :shared:test                     # Run unit tests
./gradlew :shared:assembleDebugXCFramework # Build iOS framework
```

### Android App
```bash
cd mobile
./gradlew :androidApp:assembleDebug        # Build debug APK
./gradlew :androidApp:assembleRelease      # Build release APK
./gradlew :androidApp:installDebug         # Install on device
adb logcat | grep CIRIS                    # View logs
```

### iOS App
```bash
cd mobile/iosApp
xcodebuild -workspace iosApp.xcworkspace \
           -scheme iosApp \
           -configuration Debug \
           -destination 'platform=iOS Simulator,name=iPhone 15'
```

---

## Testing Strategy

### Unit Tests (Shared)
```kotlin
// shared/src/commonTest/kotlin/api/CIRISApiClientTest.kt
class CIRISApiClientTest {
    @Test
    fun testSendMessage() = runTest {
        val client = CIRISApiClient("http://localhost:8080", "test_token")
        val response = client.sendMessage("Hello")
        assertEquals("msg_", response.message_id.substring(0, 4))
    }
}
```

### Android Tests
```kotlin
// androidApp/src/androidTest/kotlin/MainActivityTest.kt
@Test
fun testPythonRuntimeStarts() {
    val scenario = launchActivity<MainActivity>()
    onView(withText("Connected")).check(matches(isDisplayed()))
}
```

### iOS Tests
```swift
// iosApp/iosAppTests/CIRISAppTests.swift
func testComposeUILoads() throws {
    let app = XCUIApplication()
    app.launch()
    XCTAssertTrue(app.staticTexts["Chat with CIRIS"].exists)
}
```

### Integration Tests
- [ ] End-to-end chat flow
- [ ] Authentication flow (Google + Apple)
- [ ] Purchase flow (test products)
- [ ] Runtime monitoring
- [ ] Offline mode

---

## Performance Targets

### Android (Must Match or Exceed Current)
- **Startup time:** <5 seconds (cold start to UI ready)
- **Chat scroll:** 60 FPS (current native XML performance)
- **Memory:** <200 MB (without Python engine)
- **APK size:** <60 MB (similar to current)

### iOS (New Baseline)
- **Startup time:** <6 seconds (Python init + UI)
- **Chat scroll:** >50 FPS (acceptable for Compose iOS)
- **Memory:** <250 MB (Python + UI)
- **IPA size:** <70 MB

### Shared
- **API response time:** <100ms (local FastAPI)
- **Message latency:** <200ms (send to response)
- **Battery:** <5% drain per hour (idle)

---

## Risk Mitigation

### High Risk: iOS Python Runtime Embedding

**Risk:** Python C API embedding on iOS is non-trivial, may hit issues with:
- Dynamic library loading
- pydantic-core native extensions
- App Store review (dynamic code execution)

**Mitigation:**
1. **Proof of concept first** (2 days dedicated)
2. **Test on real device early** (simulator != device for native libs)
3. **Consult Python iOS community** (e.g., BeeWare team, python-apple-support)
4. **Fallback:** Keep iOS with BeeWare + shared business logic only (70% sharing vs 95%)

### Medium Risk: Compose iOS Performance

**Risk:** iOS Compose may have layout jank or high CPU usage

**Mitigation:**
1. **Profile early** with Instruments
2. **Optimize aggressively** (remember(), keys, derivedStateOf)
3. **Fallback:** Native SwiftUI for complex screens + shared ViewModels

### Low Risk: Billing Abstraction

**Risk:** Google Play Billing + StoreKit 2 APIs differ significantly

**Mitigation:**
1. **Shared interface is simple** (query products, purchase, verify)
2. **Platform-specific implementations** handle complexity
3. **Well-tested pattern** (many KMP apps do this)

---

## Rollback Plan

If KMP migration fails or has critical issues:

### Stage 1: Hotfix in KMP
- Fix bugs in `mobile/` codebase
- Deploy patched version

### Stage 2: Rollback to v1.7.42
```bash
# If kept android/ directory
cd /home/user/CIRISAgent
mv mobile mobile_kmp_backup
mv android_backup_v1.7.42 android

# Rebuild old version
cd android
./gradlew assembleRelease

# Deploy to Google Play (rollback)
```

### Stage 3: Revert in Git
```bash
git revert <migration-commit>
git push origin main
```

**Prevention:** Keep `android/` for 2 release cycles before removing.

---

## Success Criteria

### Must Have (Required for Cutover)
- ✅ All current Android features work in KMP version
- ✅ Performance matches or exceeds current Android app
- ✅ iOS app reaches feature parity with Android
- ✅ Zero regressions in QA testing
- ✅ Passes internal alpha testing (10+ users, 7 days)

### Nice to Have (Post-Cutover)
- 🎯 iOS App Store approval (may take 2-3 submissions)
- 🎯 Positive user feedback on iOS
- 🎯 Improved development velocity (50% faster features)
- 🎯 Reduced bug count (fewer platform-specific bugs)

### Metrics to Track
- **Development velocity:** Time to implement new feature (before vs after)
- **Bug count:** Platform-specific bugs (Android vs iOS)
- **Code review time:** Less code to review
- **Test coverage:** Unit test coverage % (target 80%)
- **User satisfaction:** App Store ratings (target 4.5+)

---

## Next Steps - START TODAY

### Immediate Actions (Next 2 Hours)

1. **Copy wheels directory**
   ```bash
   cp -r android/app/wheels mobile/androidApp/wheels
   ```

2. **Create Android wrapper MainActivity**
   ```bash
   mkdir -p mobile/androidApp/src/main/kotlin/ai/ciris/mobile
   # Create MainActivity.kt (template in Phase 1)
   ```

3. **Test build**
   ```bash
   cd mobile
   ./gradlew :shared:build
   ./gradlew :androidApp:assembleDebug
   ```

4. **Verify Python runtime**
   ```bash
   adb install androidApp/build/outputs/apk/debug/androidApp-debug.apk
   adb logcat | grep -E "CIRIS|Python|FastAPI"
   ```

5. **Test Compose UI**
   - Launch app
   - Verify chat screen appears
   - Test message input (may fail if FastAPI not started yet)

### This Week (Days 1-5)

- [ ] Complete Phase 1 (build system)
- [ ] Implement Phase 2 (Settings + Purchase screens)
- [ ] Start Phase 3 (Runtime monitor)

### Next Week (Days 6-10)

- [ ] Complete Phase 3 (all advanced screens)
- [ ] Start Phase 4 (iOS app)

### Week 3 (Days 11-15)

- [ ] Complete iOS native app
- [ ] Parallel testing
- [ ] Alpha release

### Week 4 (Days 16-20)

- [ ] Production cutover
- [ ] Monitor stability
- [ ] Begin iOS App Store submission

---

## Resources & Documentation

### Official Docs
- [Kotlin Multiplatform](https://kotlinlang.org/docs/multiplatform.html)
- [Compose Multiplatform](https://www.jetbrains.com/lp/compose-multiplatform/)
- [Ktor Client](https://ktor.io/docs/getting-started-ktor-client.html)
- [Python C API](https://docs.python.org/3/c-api/)

### Community Examples
- [JetBrains KMP Samples](https://github.com/Kotlin/kmm-production-sample)
- [Compose Multiplatform iOS](https://github.com/JetBrains/compose-multiplatform-ios-android-template)

### Support
- Kotlin Slack: #multiplatform, #compose-ios
- Stack Overflow: [kotlin-multiplatform]
- CIRIS Internal: Check with team on Python iOS embedding

---

## Appendix: File Mapping

### Android Activities → Compose Screens

| Old (android/) | New (mobile/shared/) | Status |
|----------------|----------------------|--------|
| `InteractActivity.kt` (372 lines) | `InteractScreen.kt` (180 lines) | ✅ Created |
| `SettingsActivity.kt` (250 lines) | `SettingsScreen.kt` (120 lines) | ⏳ TODO |
| `PurchaseActivity.kt` (400 lines) | `PurchaseScreen.kt` (200 lines) | ⏳ TODO |
| `RuntimeActivity.kt` (500 lines) | `RuntimeScreen.kt` (250 lines) | ⏳ TODO |
| `SetupWizardActivity.kt` (300 lines) | `setup/SetupFlow.kt` (150 lines) | ⏳ TODO |
| `TelemetryFragment.kt` (200 lines) | `TelemetryScreen.kt` (100 lines) | ⏳ TODO |
| `SessionsFragment.kt` (150 lines) | `SessionsScreen.kt` (80 lines) | ⏳ TODO |
| `LoginActivity.kt` (300 lines) | `AuthScreen.kt` (150 lines) | ⏳ TODO |

**Total:** ~2,500 lines → ~1,200 lines (52% reduction)

---

## Conclusion

**We're ready to move.** The scaffold is complete, licensing is clear, and the path forward is defined.

**Start with Phase 1 today** - get the build working, then incrementally migrate screens. Keep `android/` as backup until v2.0.0 is proven stable.

**iOS will catch up instantly** once the shared code is complete - that's the power of KMP.

Let's ship unified CIRIS mobile apps. 🚀
