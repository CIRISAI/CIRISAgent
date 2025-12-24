# CIRIS Mobile KMP - Immediate Action Tasks

## 🚀 START HERE - First 30 Minutes

### Task 1: Copy Dependencies
```bash
# Copy pydantic-core wheels from existing android project
cp -r /home/user/CIRISAgent/android/app/wheels /home/user/CIRISAgent/mobile/androidApp/

# Verify
ls -la /home/user/CIRISAgent/mobile/androidApp/wheels/
```

### Task 2: Create Gradle Wrapper
```bash
cd /home/user/CIRISAgent/mobile

# Copy from existing android project
cp -r ../android/gradle ./
cp ../android/gradlew ./
cp ../android/gradlew.bat ./

# Make executable
chmod +x gradlew
```

### Task 3: Test Shared Module Build
```bash
cd /home/user/CIRISAgent/mobile
./gradlew :shared:build
```

**Expected output:**
```
BUILD SUCCESSFUL in Xs
```

**If fails:** Check error messages, likely missing dependencies or version conflicts.

---

## 📋 TODAY - Core Build Setup (2-4 hours)

### Task 4: Create Missing Android Resources
```bash
cd /home/user/CIRISAgent/mobile/androidApp/src/main

# Create launcher icons (copy from existing app)
mkdir -p res/mipmap-hdpi res/mipmap-mdpi res/mipmap-xhdpi res/mipmap-xxhdpi res/mipmap-xxxhdpi
cp /home/user/CIRISAgent/android/app/src/main/res/mipmap-*/ic_launcher.png res/mipmap-*/
cp /home/user/CIRISAgent/android/app/src/main/res/mipmap-*/ic_launcher_round.png res/mipmap-*/
```

### Task 5: Create CIRISApplication.kt
```bash
# Create application class
cat > /home/user/CIRISAgent/mobile/androidApp/src/main/kotlin/ai/ciris/mobile/CIRISApplication.kt << 'EOF'
package ai.ciris.mobile

import android.app.Application

class CIRISApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        // TODO: Initialize any global state
    }
}
EOF
```

### Task 6: Test Android Build
```bash
cd /home/user/CIRISAgent/mobile
./gradlew :androidApp:assembleDebug
```

**Expected:** APK created at `androidApp/build/outputs/apk/debug/androidApp-debug.apk`

### Task 7: Install & Test on Device
```bash
# Connect Android device or start emulator
adb devices

# Install
./gradlew :androidApp:installDebug

# View logs
adb logcat | grep -E "CIRIS|Python|MainActivity"
```

**Expected behavior:**
- App launches
- Shows splash screen "Initializing CIRIS..."
- Python runtime starts (see logs)
- May fail to connect to FastAPI (expected - need to port Python startup)

---

## 🔧 THIS WEEK - Port Core Features (Days 1-5)

### Day 1: Python Runtime Initialization

**File:** `mobile/androidApp/src/main/kotlin/ai/ciris/mobile/PythonRuntimeManager.kt`

**Port from:** `android/app/src/main/java/ai/ciris/mobile/MainActivity.kt:150-400`

**Tasks:**
- [ ] Create PythonRuntimeManager class
- [ ] Port Python module loading logic
- [ ] Port mobile_main.py invocation
- [ ] Port FastAPI server startup
- [ ] Port service health polling

**Code skeleton:**
```kotlin
package ai.ciris.mobile

import com.chaquo.python.Python
import kotlinx.coroutines.delay

class PythonRuntimeManager {
    private var python: Python? = null
    private var serverStarted = false

    suspend fun initialize(onProgress: (String) -> Unit) {
        onProgress("Starting Python runtime...")
        python = Python.getInstance()

        onProgress("Loading CIRIS engine...")
        val mobileMain = python?.getModule("mobile_main")

        onProgress("Starting FastAPI server...")
        // TODO: Call mobile_main.start_server()

        onProgress("Waiting for services...")
        // TODO: Poll localhost:8080/v1/system/health

        serverStarted = true
        onProgress("Ready!")
    }

    fun isReady() = serverStarted
}
```

### Day 2: Splash Screen Animation

**File:** `mobile/shared/src/commonMain/kotlin/ai/ciris/mobile/shared/ui/screens/SplashScreen.kt`

**Port from:** `android/app/src/main/java/ai/ciris/mobile/MainActivity.kt:95-135`

**Tasks:**
- [ ] Create ServiceLight composable (12dp circle, animates color)
- [ ] Create 22-light grid (2 rows of 11)
- [ ] Animate lights as services come online
- [ ] Show status text below lights
- [ ] Add elapsed time counter

**Code skeleton:**
```kotlin
@Composable
fun SplashScreen(
    servicesOnline: Int,
    totalServices: Int,
    statusMessage: String,
    elapsedSeconds: Int
) {
    Column(
        modifier = Modifier.fillMaxSize(),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        // Logo
        Text("CIRIS", style = MaterialTheme.typography.displayLarge)

        Spacer(Modifier.height(32.dp))

        // Service lights grid
        ServiceLightsGrid(servicesOnline, totalServices)

        Spacer(Modifier.height(16.dp))

        // Status
        Text(statusMessage)
        Text("${servicesOnline}/${totalServices} services online")
        Text("Elapsed: ${elapsedSeconds}s")
    }
}

@Composable
fun ServiceLightsGrid(online: Int, total: Int) {
    // TODO: 2 rows of 11 lights
    LazyVerticalGrid(
        columns = GridCells.Fixed(11),
        modifier = Modifier.size(300.dp, 60.dp)
    ) {
        items(total) { index ->
            ServiceLight(isOn = index < online)
        }
    }
}

@Composable
fun ServiceLight(isOn: Boolean) {
    val color by animateColorAsState(
        targetValue = if (isOn) Color(0xFF00d4ff) else Color(0xFF2a2a3e)
    )
    Box(
        modifier = Modifier
            .size(12.dp)
            .background(color, CircleShape)
    )
}
```

### Day 3: Settings Screen

**File:** `mobile/shared/src/commonMain/kotlin/ai/ciris/mobile/shared/ui/screens/SettingsScreen.kt`

**Port from:** `android/app/src/main/java/ai/ciris/mobile/SettingsActivity.kt`

**Tasks:**
- [ ] Create SettingsViewModel
- [ ] Create SettingsScreen (Compose)
- [ ] LLM API key input
- [ ] Model selection dropdown
- [ ] Account info display
- [ ] Logout button
- [ ] Implement secure storage (expect/actual)

**Estimate:** 4 hours

### Day 4: Purchase Flow

**File:** `mobile/shared/src/commonMain/kotlin/ai/ciris/mobile/shared/ui/screens/PurchaseScreen.kt`

**Port from:** `android/app/src/main/java/ai/ciris/mobile/PurchaseActivity.kt`

**Tasks:**
- [ ] Create BillingClient abstraction (expect/actual)
- [ ] Create PurchaseViewModel
- [ ] Create PurchaseScreen (Compose)
- [ ] Product listing (100, 250, 600 credits)
- [ ] Purchase flow
- [ ] Server verification

**Estimate:** 6-8 hours

### Day 5: Authentication

**Files:**
- `mobile/shared/src/commonMain/kotlin/ai/ciris/mobile/shared/ui/screens/LoginScreen.kt`
- `mobile/androidApp/src/main/kotlin/ai/ciris/mobile/auth/GoogleSignInHelper.kt`

**Port from:** `android/app/src/main/java/ai/ciris/mobile/auth/`

**Tasks:**
- [ ] Create LoginViewModel
- [ ] Create LoginScreen (Compose)
- [ ] Google Sign-In (Android-specific)
- [ ] Token management
- [ ] OAuth callback handling

**Estimate:** 6 hours

---

## 📝 QUICK REFERENCE - Commands

### Build
```bash
cd /home/user/CIRISAgent/mobile

# Shared module
./gradlew :shared:build
./gradlew :shared:test

# Android app
./gradlew :androidApp:assembleDebug
./gradlew :androidApp:assembleRelease

# Install
./gradlew :androidApp:installDebug
```

### Debug
```bash
# View all logs
adb logcat

# Filter CIRIS logs
adb logcat | grep CIRIS

# Filter Python logs
adb logcat | grep Python

# Filter errors only
adb logcat *:E
```

### Clean Build
```bash
./gradlew clean
rm -rf .gradle build
./gradlew :shared:build
```

---

## 🐛 Troubleshooting

### Issue: "Python not found"
**Solution:** Ensure Python 3.10 is installed and `buildPython` path is correct in `androidApp/build.gradle`

### Issue: "pydantic_core not found"
**Solution:** Verify wheels are copied: `ls mobile/androidApp/wheels/`

### Issue: "Compose not found"
**Solution:** Check Compose version in `mobile/build.gradle.kts` and ensure Compose plugin is applied

### Issue: Build fails with "duplicate class"
**Solution:** Clean build: `./gradlew clean`, then rebuild

### Issue: App crashes on startup
**Solution:** Check logcat for Python initialization errors: `adb logcat | grep -E "Python|Chaquopy"`

---

## ✅ Success Criteria for Today

- [ ] Shared module builds successfully
- [ ] Android app builds successfully
- [ ] APK installs on device
- [ ] App launches (may show splash indefinitely - OK for now)
- [ ] Python runtime initializes (check logcat)
- [ ] No crashes

**If all checked:** You're ready for Day 2 (porting Python runtime logic)

---

## 📞 Need Help?

1. **Build errors:** Check `mobile/build/` directory for detailed logs
2. **Python errors:** `adb logcat | grep Python`
3. **Compose errors:** Ensure Compose version is compatible with Kotlin version
4. **Chaquopy errors:** Check `androidApp/build/python/` directory

**Next:** Once build works, move to Day 1 tasks (Python runtime initialization)
