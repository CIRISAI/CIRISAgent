#!/bin/bash
# Verification script for KMP Agent 1 extraction

echo "========================================="
echo "KMP Migration Agent 1 - Verification"
echo "========================================="
echo ""

# Check files exist
echo "Checking files..."
files=(
  "src/commonMain/kotlin/ai/ciris/mobile/shared/services/ServerManager.kt"
  "src/androidMain/kotlin/ai/ciris/mobile/shared/services/PlatformHttp.android.kt"
  "src/commonMain/kotlin/ai/ciris/mobile/shared/config/CIRISConfig.kt"
  "src/commonMain/kotlin/ai/ciris/mobile/shared/platform/PythonRuntime.kt"
  "src/androidMain/kotlin/ai/ciris/mobile/shared/platform/PythonRuntime.android.kt"
)

all_exist=true
for file in "${files[@]}"; do
  if [ -f "$file" ]; then
    echo "✓ $file"
  else
    echo "✗ $file - MISSING"
    all_exist=false
  fi
done

echo ""
echo "File sizes:"
ls -lh src/commonMain/kotlin/ai/ciris/mobile/shared/services/ServerManager.kt 2>/dev/null || echo "Missing"
ls -lh src/androidMain/kotlin/ai/ciris/mobile/shared/services/PlatformHttp.android.kt 2>/dev/null || echo "Missing"
ls -lh src/commonMain/kotlin/ai/ciris/mobile/shared/config/CIRISConfig.kt 2>/dev/null || echo "Missing"

echo ""
echo "Line counts:"
echo "PythonRuntime.kt (expect): $(wc -l < src/commonMain/kotlin/ai/ciris/mobile/shared/platform/PythonRuntime.kt 2>/dev/null || echo 0) lines"
echo "PythonRuntime.android.kt (actual): $(wc -l < src/androidMain/kotlin/ai/ciris/mobile/shared/platform/PythonRuntime.android.kt 2>/dev/null || echo 0) lines"
echo "ServerManager.kt: $(wc -l < src/commonMain/kotlin/ai/ciris/mobile/shared/services/ServerManager.kt 2>/dev/null || echo 0) lines"
echo "PlatformHttp.android.kt: $(wc -l < src/androidMain/kotlin/ai/ciris/mobile/shared/services/PlatformHttp.android.kt 2>/dev/null || echo 0) lines"

echo ""
echo "Checking for extracted methods in ServerManager.kt..."
methods=(
  "isExistingServerRunning"
  "checkServerHealth"
  "waitForServerShutdown"
  "shutdownExistingServer"
  "tryAuthenticatedShutdown"
)

for method in "${methods[@]}"; do
  if grep -q "fun $method" src/commonMain/kotlin/ai/ciris/mobile/shared/services/ServerManager.kt 2>/dev/null; then
    echo "✓ $method()"
  else
    echo "✗ $method() - MISSING"
  fi
done

echo ""
echo "Checking for platform HTTP functions..."
platform_fns=(
  "platformHttpGet"
  "platformHttpPost"
  "platformHttpPostWithAuth"
  "platformGetAuthToken"
)

for fn in "${platform_fns[@]}"; do
  if grep -q "actual suspend fun $fn" src/androidMain/kotlin/ai/ciris/mobile/shared/services/PlatformHttp.android.kt 2>/dev/null; then
    echo "✓ $fn()"
  else
    echo "✗ $fn() - MISSING"
  fi
done

echo ""
echo "Checking PythonRuntime enhancements..."
runtime_methods=(
  "startPythonServer"
  "injectPythonConfig"
  "serverUrl"
)

for method in "${runtime_methods[@]}"; do
  if grep -q "$method" src/commonMain/kotlin/ai/ciris/mobile/shared/platform/PythonRuntime.kt 2>/dev/null; then
    echo "✓ $method (expect)"
  else
    echo "✗ $method (expect) - MISSING"
  fi

  if grep -q "$method" src/androidMain/kotlin/ai/ciris/mobile/shared/platform/PythonRuntime.android.kt 2>/dev/null; then
    echo "✓ $method (actual)"
  else
    echo "✗ $method (actual) - MISSING"
  fi
done

echo ""
if [ "$all_exist" = true ]; then
  echo "✅ All files created successfully!"
else
  echo "❌ Some files are missing!"
fi

echo ""
echo "Detailed report: EXTRACTION_REPORT.md"
echo "========================================="
