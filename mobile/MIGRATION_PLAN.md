# MainActivity.kt Migration Plan for KMP

## Overview

Migrate 2986-line monolithic `android/app/.../MainActivity.kt` (81 methods) to modular KMP architecture in `mobile/` with minimal code changes and test-driven approach.

## Source Analysis

**File:** `android/app/src/main/java/ai/ciris/mobile/MainActivity.kt`
- **Lines:** 2986
- **Methods:** 81
- **Key Dependencies:** Chaquopy, Google Sign-In, Play Billing, Play Integrity

### Logical Sections Identified

| Section | Lines | Methods | Purpose |
|---------|-------|---------|---------|
| **Startup/UI** | 212-720 | 15 | Splash, lights, phases, elapsed timer |
| **Python Runtime** | 721-860 | 5 | Chaquopy init, config injection |
| **Server Management** | 1241-1660 | 10 | Start/stop/health check server |
| **WebView/JS Bridge** | 854-1240 | 12 | WebView setup, JS interface |
| **Auth/Token** | 1830-2030 | 8 | Google OAuth, token exchange |
| **Navigation** | 2030-2550 | 15 | Fragment navigation, menu |
| **Setup Detection** | 1859-1900 | 3 | First-run detection |
| **Billing Integration** | 2678-2986 | 8 | Credits, token refresh |

---

## Migration Strategy: "Extract → Test → Integrate"

### Principle: Minimal Code Changes
- **Copy** working methods from android/ → don't rewrite
- **Wrap** platform-specific code with expect/actual
- **Test** each module independently before integration

---

## Phase 1: Core Infrastructure

### 1.1 Extract PythonRuntimeManager
**Source:** Lines 721-860, 1485-1660
**Target:** `shared/src/commonMain/.../platform/PythonRuntimeManager.kt`

Methods to extract:
- initializePythonAndStartServer() → split into init + start
- injectPythonConfig()
- startPythonServer()
- setupPythonOutputRedirect() → logcat parsing

**Test Strategy:**
- Test: initialize returns success on valid python home
- Test: startServer launches mobile_main
- Test: logcat parser extracts service counts
- Test: health check returns true when server responds

### 1.2 Extract ServerManager
**Source:** Lines 1241-1480
**Target:** `shared/src/commonMain/.../services/ServerManager.kt`

Methods to extract:
- isExistingServerRunning()
- shutdownExistingServer()
- tryAuthenticatedShutdown()
- waitForServerShutdown()
- checkServerHealth()

**Test Strategy:**
- Test: health check parses JSON response correctly
- Test: shutdown handles 401 unauthorized
- Test: shutdown handles server not running

---

## Phase 2: Startup UI

### 2.1 Enhance StartupViewModel (existing)
**Source:** Lines 199-210, 431-620
**Target:** `shared/src/commonMain/.../viewmodels/StartupViewModel.kt`

State to manage:
- currentPhase: StartupPhase
- servicesOnline: Int (0-22)
- prepStepsCompleted: Int (0-6)
- elapsedSeconds: Int
- errorMessage: String?
- hasError: Boolean

Methods to extract:
- setPhase()
- onPrepStepCompleted()
- onServiceStarted()
- onErrorDetected()
- startElapsedTimer() / stopElapsedTimer()

**Test Strategy:**
- Test: phase transitions correctly from INITIALIZING to LOADING_RUNTIME
- Test: service count increments uniquely (no duplicates)
- Test: error detection sets hasError flag
- Test: elapsed timer increments every second

### 2.2 Enhance StartupScreen (existing)
**Source:** Lines 504-574 (light creation/animation)
**Target:** `shared/src/commonMain/.../ui/screens/StartupScreen.kt`

Enhancements needed:
- Add prep lights (6 lights for pydantic setup)
- Add phase indicator text
- Add "Show Logs" / "Back to Splash" toggle
- Match exact colors from android/

---

## Phase 3: Setup Wizard

### 3.1 Create SetupViewModel
**Source:** `android/app/.../setup/SetupViewModel.kt` (167 lines)
**Target:** `shared/src/commonMain/.../viewmodels/SetupViewModel.kt`

State to manage:
- currentStep: Int (0-2)
- isGoogleAuth: Boolean
- llmMode: LlmMode (CIRIS_PROXY / BYOK)
- llmProvider: String
- llmApiKey: String
- llmModel: String
- username: String (for local auth)
- password: String (for local auth)

**Test Strategy:**
- Test: Google auth defaults to CIRIS_PROXY mode
- Test: non-Google auth forces BYOK mode
- Test: validation fails without API key in BYOK mode
- Test: admin password is auto-generated (32 chars)

### 3.2 Create SetupScreen (Compose Multiplatform)
**Source:** SetupWizardActivity + 3 Fragments (combined ~800 lines)
**Target:** `shared/src/commonMain/.../ui/screens/SetupScreen.kt`

Single Composable with internal step navigation:
- Step 0: WelcomeStep (context-aware for Google vs non-Google)
- Step 1: LlmConfigStep (CIRIS proxy vs BYOK)
- Step 2: ConfirmStep (summary for Google, account creation for local)

---

## Phase 4: Auth Management

### 4.1 Extract AuthManager
**Source:** Lines 1903-2030
**Target:** `shared/src/commonMain/.../platform/AuthManager.kt` (expect/actual)

```kotlin
expect class AuthManager {
    suspend fun exchangeGoogleIdToken(idToken: String): Result<TokenResponse>
    suspend fun authenticateLocal(username: String, password: String): Result<TokenResponse>
    suspend fun refreshToken(): Result<String>
    fun isGoogleAuthAvailable(): Boolean
}
```

**Android actual:** Uses GoogleSignInHelper, calls `/v1/auth/google/token`
**iOS actual:** Stub for now (returns failure)

**Test Strategy:**
- Test: token exchange parses access_token from response
- Test: token exchange handles 401 error
- Test: local auth works with valid credentials

---

## Phase 5: Navigation & Integration

### 5.1 Update CIRISApp.kt
**Target:** `shared/src/commonMain/.../CIRISApp.kt`

Add navigation states:
- Screen.Startup → existing
- Screen.Setup → NEW (first-run wizard)
- Screen.Interact → existing
- Screen.Settings → existing

Add first-run detection:
- Check for .env file existence
- Route to Setup if first-run, else to Startup

### 5.2 Update MainActivity.kt (mobile/)
**Target:** `mobile/androidApp/.../MainActivity.kt`

Minimal changes:
- Pass isFirstRun to CIRISApp
- Pass Google auth state if available
- Handle setup completion callback

---

## Sub-Agent Assignments

### Agent 1: PythonRuntimeManager + ServerManager
```
Tasks:
1. Extract methods from MainActivity.kt lines 721-860, 1241-1660
2. Create expect/actual structure
3. Write unit tests
4. Integrate with existing PythonRuntime.android.kt
```

### Agent 2: StartupViewModel + StartupScreen Enhancement
```
Tasks:
1. Enhance existing StartupViewModel with phases, prep steps
2. Add prep lights row to StartupScreen
3. Add phase indicator and elapsed timer
4. Match colors/styling from android/
5. Write unit tests
```

### Agent 3: SetupViewModel + SetupScreen
```
Tasks:
1. Port SetupViewModel from android/setup/
2. Create SetupScreen with 3 steps (Compose)
3. Implement validation logic
4. Wire up API calls (/v1/setup/complete)
5. Write unit tests
```

### Agent 4: AuthManager + First-Run Detection
```
Tasks:
1. Create expect/actual AuthManager
2. Port token exchange logic
3. Implement first-run detection (check .env)
4. Update CIRISApp navigation
5. Write integration tests
```

---

## File Changes Summary

### New Files to Create
```
shared/src/commonMain/kotlin/ai/ciris/mobile/shared/
├── services/
│   └── ServerManager.kt
├── viewmodels/
│   └── SetupViewModel.kt
├── ui/screens/
│   └── SetupScreen.kt
└── platform/
    └── AuthManager.kt (expect)

shared/src/androidMain/kotlin/ai/ciris/mobile/shared/
└── platform/
    └── AuthManager.android.kt (actual)

shared/src/commonTest/kotlin/
├── StartupViewModelTest.kt
├── SetupViewModelTest.kt
└── ServerManagerTest.kt
```

### Files to Modify
```
shared/.../CIRISApp.kt                    # Add Setup screen, first-run routing
shared/.../viewmodels/StartupViewModel.kt # Add phases, prep steps
shared/.../ui/screens/StartupScreen.kt    # Add prep lights
shared/.../platform/PythonRuntime.kt      # Add config injection
shared/androidMain/.../PythonRuntime.android.kt  # Enhanced implementation
mobile/androidApp/.../MainActivity.kt     # Pass auth state, handle setup
```

### Files to Copy (reference only)
```
FROM android/app/src/main/java/ai/ciris/mobile/
├── setup/SetupViewModel.kt      → Reference for SetupViewModel
├── setup/SetupWizardActivity.kt → Reference for SetupScreen
├── auth/GoogleSignInHelper.kt   → Copy to androidMain
├── auth/TokenRefreshManager.kt  → Copy to androidMain
└── config/CIRISConfig.kt        → Copy to shared
```

---

## Execution Order (Parallel Sub-Agents)

```
┌─────────────────────────────────────────────────────────────────┐
│ Phase 1: Agent 1 (Python/Server) ─────────────────────────────▶ │
│ Phase 2: Agent 2 (Startup UI) ────────────────────────────────▶ │
│                                                                 │
│ Phase 3: Agent 3 (Setup Wizard) ──────────────────────────────▶ │
│ Phase 4: Agent 4 (Auth + First-Run) ──────────────────────────▶ │
│                                                                 │
│ Phase 5: Integration (Sequential) ────────────────────────────▶ │
│ Phase 6: QA/Testing ──────────────────────────────────────────▶ │
└─────────────────────────────────────────────────────────────────┘
```

Agents 1+2 run in parallel (no dependencies)
Agents 3+4 run in parallel (no dependencies)
Integration waits for all agents to complete

---

## Success Criteria

1. **Build passes:** `./gradlew :androidApp:assembleDebug`
2. **All tests pass:** `./gradlew :shared:allTests`
3. **Fresh install:** Shows setup wizard, completes successfully
4. **Repeat install:** Skips setup, shows 22 lights, reaches READY
5. **First-run mode:** 10/10 minimal services start (waiting for setup)
6. **Full mode:** 22/22 services start after setup complete

---

## QA Test Matrix

| Scenario | Expected Result |
|----------|-----------------|
| Fresh install | Setup wizard appears |
| Google OAuth available | "Free AI" option shown |
| No Google OAuth | BYOK only |
| Setup complete | .env created, full services start |
| Second launch | Skip setup, 22 lights animate |
| Server health fail | Error state, red lights |
| Timeout (60s) | Error message shown |
