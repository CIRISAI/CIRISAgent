# Building CIRIS for Android

Complete guide to building the CIRIS Android APK with 100% on-device packaging.

## Prerequisites

### Required Software

1. **Android Studio** (Hedgehog 2023.1.1 or newer)
   ```bash
   # Download from: https://developer.android.com/studio
   ```

2. **Java Development Kit 17**
   ```bash
   # Check version
   java -version
   # Should show 17.x.x

   # Install if needed
   # Ubuntu/Debian:
   sudo apt install openjdk-17-jdk

   # macOS:
   brew install openjdk@17
   ```

3. **Python 3.10+** (for building)
   ```bash
   # Check version
   python3 --version
   # Should show 3.10.x or higher

   # Install if needed
   # Ubuntu/Debian:
   sudo apt install python3.10

   # macOS:
   brew install python@3.10
   ```

4. **Android SDK Components**
   - Install via Android Studio SDK Manager:
     - Android SDK Platform 34
     - Android SDK Build-Tools 34.0.0
     - NDK (Side by side) - version 25.1.8937393 or newer

### Verify Installation

```bash
# Check Android SDK
echo $ANDROID_HOME
# Should point to SDK location (e.g., ~/Android/Sdk)

# Check Gradle
./gradlew --version
# Should show Gradle 8.0+

# Check Python
python3 --version
# Should show 3.10+
```

## Build Steps

### 1. Clone and Setup

```bash
# Clone repository
git clone https://github.com/CIRISAI/CIRISAgent.git
cd CIRISAgent

# Switch to Android branch
git checkout android/on-device-packaging

# Verify structure
ls -la android/
# Should see: app/, build.gradle, settings.gradle
```

### 2. Configure Environment

Create `android/local.properties`:
```properties
# Path to Android SDK
sdk.dir=/home/username/Android/Sdk

# Path to NDK (if not using SDK Manager version)
ndk.dir=/home/username/Android/Sdk/ndk/25.1.8937393
```

### 3. Build Debug APK

```bash
cd android

# Clean build
./gradlew clean

# Build debug APK
./gradlew assembleDebug

# APK location:
# app/build/outputs/apk/debug/app-debug.apk
```

### 4. Build Release APK

First, configure signing in `android/app/build.gradle`:

```gradle
android {
    signingConfigs {
        release {
            storeFile file("../keystore.jks")
            storePassword System.getenv("KEYSTORE_PASSWORD")
            keyAlias "ciris-release"
            keyPassword System.getenv("KEY_PASSWORD")
        }
    }

    buildTypes {
        release {
            signingConfig signingConfigs.release
            minifyEnabled true
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
        }
    }
}
```

Then build:

```bash
# Create keystore (first time only)
keytool -genkey -v -keystore android/keystore.jks \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -alias ciris-release

# Set environment variables
export KEYSTORE_PASSWORD="your-keystore-password"
export KEY_PASSWORD="your-key-password"

# Build release APK
./gradlew assembleRelease

# APK location:
# app/build/outputs/apk/release/app-release.apk
```

## Build Variants

### Debug Build
- **Use case**: Development and testing
- **Size**: ~60MB (includes debug symbols)
- **Obfuscation**: None
- **Logging**: Verbose

```bash
./gradlew assembleDebug
```

### Release Build
- **Use case**: Production deployment
- **Size**: ~45MB (optimized)
- **Obfuscation**: ProGuard enabled
- **Logging**: Minimal

```bash
./gradlew assembleRelease
```

## Installation

### Install on Connected Device

```bash
# Install debug APK
adb install app/build/outputs/apk/debug/app-debug.apk

# Or install release APK
adb install app/build/outputs/apk/release/app-release.apk

# Uninstall if already installed
adb uninstall ai.ciris.mobile
adb install app/build/outputs/apk/debug/app-debug.apk
```

### Install on Emulator

```bash
# List emulators
emulator -list-avds

# Start emulator
emulator -avd <avd-name> &

# Install APK
adb install app/build/outputs/apk/debug/app-debug.apk
```

## Troubleshooting Build Issues

### Issue: Gradle sync failed

**Error**: "Could not resolve com.chaquo.python:gradle"

**Solution**:
```bash
# Update Gradle wrapper
./gradlew wrapper --gradle-version=8.1

# Clear Gradle cache
rm -rf ~/.gradle/caches/
./gradlew clean
```

### Issue: Python dependencies not found

**Error**: "Could not install requirements"

**Solution**:
```bash
# Ensure Python 3.10+ is in PATH
which python3
python3 --version

# Update build.gradle to use correct Python
python {
    buildPython "/usr/bin/python3.10"  # Explicit version
    // ...
}
```

### Issue: NDK not found

**Error**: "NDK is not configured"

**Solution**:
1. Open Android Studio
2. Tools → SDK Manager → SDK Tools
3. Check "NDK (Side by side)"
4. Click Apply to install
5. Update `local.properties`:
   ```properties
   ndk.dir=/path/to/sdk/ndk/25.1.8937393
   ```

### Issue: Out of memory during build

**Error**: "Java heap space"

**Solution**:
Edit `gradle.properties`:
```properties
org.gradle.jvmargs=-Xmx4096m -Dfile.encoding=UTF-8
```

### Issue: Build succeeds but APK doesn't install

**Error**: "INSTALL_FAILED_UPDATE_INCOMPATIBLE"

**Solution**:
```bash
# Uninstall old version first
adb uninstall ai.ciris.mobile

# Then install new APK
adb install app/build/outputs/apk/debug/app-debug.apk
```

## Build Performance Tips

### Speed Up Builds

1. **Enable Gradle daemon** (gradle.properties):
   ```properties
   org.gradle.daemon=true
   org.gradle.parallel=true
   org.gradle.configureondemand=true
   ```

2. **Use build cache**:
   ```bash
   ./gradlew assembleDebug --build-cache
   ```

3. **Skip tests for faster builds**:
   ```bash
   ./gradlew assembleDebug -x test -x lint
   ```

### Reduce APK Size

1. **Enable resource shrinking** (build.gradle):
   ```gradle
   buildTypes {
       release {
           shrinkResources true
           minifyEnabled true
       }
   }
   ```

2. **Use APK splits** for different architectures:
   ```gradle
   splits {
       abi {
           enable true
           reset()
           include "arm64-v8a", "armeabi-v7a"
           universalApk false
       }
   }
   ```

3. **Analyze APK size**:
   ```bash
   ./gradlew assembleRelease
   # Then in Android Studio: Build → Analyze APK
   ```

## Testing the Build

### Run Unit Tests

```bash
./gradlew test
```

### Run Instrumentation Tests

```bash
# On connected device
./gradlew connectedAndroidTest

# On specific device
adb devices
./gradlew connectedAndroidTest -Pandroid.testInstrumentationRunnerArguments.deviceId=<device-id>
```

### Verify APK Contents

```bash
# Unzip APK to inspect
unzip -l app/build/outputs/apk/debug/app-debug.apk

# Check Python files are included
unzip -l app/build/outputs/apk/debug/app-debug.apk | grep "\.pyc"

# Check GUI static assets
unzip -l app/build/outputs/apk/debug/app-debug.apk | grep "gui_static"
```

## Build for Different Targets

### ARM64 Only (Modern Devices)

```gradle
ndk {
    abiFilters "arm64-v8a"
}
```

### ARM32 + ARM64 (Wider Compatibility)

```gradle
ndk {
    abiFilters "arm64-v8a", "armeabi-v7a"
}
```

### All Architectures (Maximum Compatibility)

```gradle
ndk {
    abiFilters "arm64-v8a", "armeabi-v7a", "x86", "x86_64"
}
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Build Android APK

on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Set up JDK 17
      uses: actions/setup-java@v3
      with:
        java-version: '17'
        distribution: 'temurin'

    - name: Setup Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'

    - name: Build Debug APK
      run: |
        cd android
        chmod +x gradlew
        ./gradlew assembleDebug

    - name: Upload APK
      uses: actions/upload-artifact@v3
      with:
        name: app-debug
        path: android/app/build/outputs/apk/debug/app-debug.apk
```

## Next Steps

After successful build:

1. **Test on device**: Install and verify basic functionality
2. **Configure LLM endpoint**: Settings → Enter OpenAI-compatible URL
3. **Test API**: `adb shell curl http://127.0.0.1:8000/v1/health`
4. **Review logs**: `adb logcat -s CIRISMobile`

## Support

- **Build issues**: Check [Troubleshooting](#troubleshooting-build-issues)
- **Chaquopy docs**: https://chaquo.com/chaquopy/doc/current/
- **Android docs**: https://developer.android.com/studio/build
- **CIRIS issues**: https://github.com/CIRISAI/CIRISAgent/issues
