#!/bin/bash
#
# validate-kmp2-migration.sh
# Pre-migration validation for Kotlin 1.9.x → 2.x + Compose 1.6 → 1.7+ upgrade
#
# Usage: ./scripts/validate-kmp2-migration.sh [--fix] [--verbose]
#
# This script checks for known incompatibilities before migration:
# 1. Dispatchers.IO usage (not available in wasmJs)
# 2. Missing 'override' on interface implementations (causes ClassCastException in WASM)
# 3. Incomplete 'when' expressions missing Platform.WEB branch
# 4. expect declarations needing wasmJsMain actuals
# 5. Deprecated kotlinOptions syntax (needs compilerOptions in 2.x)
# 6. Old compose compiler extension version
# 7. Reflection usage (limited in WASM)
# 8. Okio usage (not supported in WASM)
#
# Lessons learned from CIRISHome WASM deployment baked in.
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MOBILE_ROOT="$(dirname "$SCRIPT_DIR")"
SHARED_DIR="${MOBILE_ROOT}/shared/src"

# Options
FIX_MODE=false
VERBOSE=false
ERRORS=0
WARNINGS=0
FIXED=0

for arg in "$@"; do
    case $arg in
        --fix) FIX_MODE=true ;;
        --verbose) VERBOSE=true ;;
        --help|-h)
            echo "Usage: $0 [--fix] [--verbose]"
            echo ""
            echo "Pre-migration validation for Kotlin 2.x upgrade"
            echo ""
            echo "Options:"
            echo "  --fix      Automatically fix safe issues (Dispatchers.IO, etc.)"
            echo "  --verbose  Show all findings, not just summary"
            exit 0
            ;;
    esac
done

log_header() { echo -e "\n${BOLD}${BLUE}═══════════════════════════════════════════════════════════════${NC}"; echo -e "${BOLD}$1${NC}"; echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"; }
log_check() { echo -e "${BLUE}[CHECK]${NC} $1"; }
log_ok() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; ((WARNINGS++)); }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; ((ERRORS++)); }
log_fix() { echo -e "${GREEN}[FIXED]${NC} $1"; ((FIXED++)); }
log_verbose() { $VERBOSE && echo -e "       $1" || true; }

echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║     KMP 2.x Migration Validator                               ║"
echo "║     Kotlin 1.9.x → 2.x | Compose 1.6 → 1.7+                   ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""
echo "Mobile root: $MOBILE_ROOT"
echo "Fix mode: $FIX_MODE"
echo ""

# =============================================================================
# CHECK 1: Dispatchers.IO usage (not available in wasmJs)
# =============================================================================
log_header "1. Dispatchers.IO Usage (WASM incompatible)"

IO_FILES=$(grep -rl "Dispatchers\.IO\|withContext(IO)\|import kotlinx\.coroutines\.IO$" "$SHARED_DIR/commonMain" 2>/dev/null || true)

if [ -n "$IO_FILES" ]; then
    IO_COUNT=$(echo "$IO_FILES" | wc -l)
    log_warn "Found $IO_COUNT files using Dispatchers.IO (not available in wasmJs)"

    for f in $IO_FILES; do
        rel_path="${f#$SHARED_DIR/}"
        log_verbose "  - $rel_path"

        if $FIX_MODE; then
            # Remove standalone IO import
            sed -i '/import kotlinx\.coroutines\.IO$/d' "$f"
            # Replace Dispatchers.IO with Dispatchers.Default
            sed -i 's/Dispatchers\.IO/Dispatchers.Default/g' "$f"
            # Replace withContext(IO) with withContext(Dispatchers.Default)
            sed -i 's/withContext(IO)/withContext(Dispatchers.Default)/g' "$f"
            log_fix "  Fixed: $rel_path"
        fi
    done

    if ! $FIX_MODE; then
        echo ""
        echo "  Fix: Replace Dispatchers.IO with Dispatchers.Default"
        echo "  Or run: $0 --fix"
    fi
else
    log_ok "No Dispatchers.IO usage found"
fi

# =============================================================================
# CHECK 2: Interface implementations missing 'override' (ClassCastException in WASM)
# =============================================================================
log_header "2. Interface Implementations (WASM ClassCastException risk)"

# Look for actual class implementations that implement interfaces
# This is a heuristic - look for "actual class X : Interface" patterns
ACTUAL_CLASSES=$(grep -rn "actual class.*:" "$SHARED_DIR" --include="*.kt" 2>/dev/null | grep -v "actual class.*actual constructor" || true)

if [ -n "$ACTUAL_CLASSES" ]; then
    log_check "Found actual class implementations - checking for override modifiers"

    MISSING_OVERRIDE=0
    while IFS= read -r line; do
        file=$(echo "$line" | cut -d: -f1)

        # Check if file has interface methods without override
        # Look for "actual fun" or "actual val" without "actual override"
        if grep -q "actual fun\|actual val" "$file" 2>/dev/null; then
            if grep -q "actual fun" "$file" && ! grep -q "actual override fun" "$file"; then
                rel_path="${file#$SHARED_DIR/}"
                log_warn "Possible missing 'override' in: $rel_path"
                log_verbose "  Pattern: 'actual fun' without 'actual override fun'"
                ((MISSING_OVERRIDE++))
            fi
        fi
    done <<< "$ACTUAL_CLASSES"

    if [ $MISSING_OVERRIDE -eq 0 ]; then
        log_ok "All actual implementations appear to have override modifiers"
    else
        echo ""
        echo "  CRITICAL: Missing 'override' causes silent ClassCastException in WASM!"
        echo "  Fix: Add 'override' to ALL interface method implementations"
        echo "  Example: actual override fun methodName() instead of actual fun methodName()"
    fi
else
    log_ok "No actual class implementations to check"
fi

# =============================================================================
# CHECK 3: Platform.WEB branch in when expressions
# =============================================================================
log_header "3. Platform when() Expressions (missing WEB branch)"

# Find when expressions on Platform enum that don't have WEB
WHEN_PLATFORM=$(grep -rn "when.*[Pp]latform\|Platform\.[A-Z]* ->" "$SHARED_DIR/commonMain" --include="*.kt" 2>/dev/null || true)

if [ -n "$WHEN_PLATFORM" ]; then
    # Check if any file has Platform.DESKTOP but not Platform.WEB
    MISSING_WEB=0

    while IFS= read -r file; do
        if grep -q "Platform\.DESKTOP\|Platform\.IOS\|Platform\.ANDROID" "$file" 2>/dev/null; then
            if ! grep -q "Platform\.WEB" "$file" 2>/dev/null; then
                rel_path="${file#$SHARED_DIR/}"
                log_warn "Missing Platform.WEB branch: $rel_path"
                ((MISSING_WEB++))
            fi
        fi
    done < <(grep -rl "when.*[Pp]latform\|Platform\.[A-Z]* ->" "$SHARED_DIR/commonMain" --include="*.kt" 2>/dev/null || true)

    if [ $MISSING_WEB -eq 0 ]; then
        log_ok "All Platform when expressions have WEB branch (or don't need it)"
    else
        echo ""
        echo "  Fix: Add Platform.WEB -> ... branches to exhaustive when expressions"
    fi
else
    log_ok "No Platform when expressions found"
fi

# =============================================================================
# CHECK 4: expect declarations needing wasmJsMain actuals
# =============================================================================
log_header "4. expect/actual Declarations (wasmJsMain needed)"

EXPECT_COUNT=$(grep -rh "^expect " "$SHARED_DIR/commonMain" --include="*.kt" 2>/dev/null | wc -l || echo "0")
log_check "Found $EXPECT_COUNT expect declarations in commonMain"

# List them
if [ "$EXPECT_COUNT" -gt 0 ] && $VERBOSE; then
    echo ""
    grep -rh "^expect " "$SHARED_DIR/commonMain" --include="*.kt" 2>/dev/null | head -20 | while read -r line; do
        echo "  - $line"
    done
    [ "$EXPECT_COUNT" -gt 20 ] && echo "  ... and $((EXPECT_COUNT - 20)) more"
fi

# Check if wasmJsMain exists
if [ -d "$SHARED_DIR/wasmJsMain" ]; then
    ACTUAL_COUNT=$(grep -rh "^actual " "$SHARED_DIR/wasmJsMain" --include="*.kt" 2>/dev/null | wc -l || echo "0")
    log_ok "wasmJsMain exists with $ACTUAL_COUNT actual declarations"

    if [ "$ACTUAL_COUNT" -lt "$EXPECT_COUNT" ]; then
        log_warn "wasmJsMain may be missing some actual implementations ($ACTUAL_COUNT < $EXPECT_COUNT)"
    fi
else
    log_warn "No wasmJsMain source set - needs to be created for WASM support"
    echo ""
    echo "  Fix: Create shared/src/wasmJsMain/kotlin/ with actual implementations"
    echo "  See: CIRISHome/mobile-web/shared/src/wasmJsMain/ for examples"
fi

# =============================================================================
# CHECK 5: Deprecated kotlinOptions syntax
# =============================================================================
log_header "5. Deprecated kotlinOptions Syntax (Kotlin 2.x)"

KOTLIN_OPTIONS=$(grep -rn "kotlinOptions" "$MOBILE_ROOT" --include="*.gradle.kts" --include="*.gradle" 2>/dev/null || true)

if [ -n "$KOTLIN_OPTIONS" ]; then
    KO_COUNT=$(echo "$KOTLIN_OPTIONS" | wc -l)
    log_warn "Found $KO_COUNT uses of deprecated 'kotlinOptions' syntax"

    echo "$KOTLIN_OPTIONS" | head -10 | while read -r line; do
        log_verbose "  $line"
    done

    echo ""
    echo "  Fix: Replace kotlinOptions with compilerOptions:"
    echo "    OLD: kotlinOptions { jvmTarget = \"17\" }"
    echo "    NEW: compilerOptions { jvmTarget.set(JvmTarget.JVM_17) }"
else
    log_ok "No deprecated kotlinOptions syntax found"
fi

# =============================================================================
# CHECK 6: Old compose compiler extension version
# =============================================================================
log_header "6. Compose Compiler Extension Version"

COMPOSE_EXT=$(grep -rn "kotlinCompilerExtensionVersion" "$MOBILE_ROOT" --include="*.gradle.kts" --include="*.gradle" 2>/dev/null || true)

if [ -n "$COMPOSE_EXT" ]; then
    log_warn "Found kotlinCompilerExtensionVersion - should be removed in Kotlin 2.x"
    echo "$COMPOSE_EXT" | while read -r line; do
        log_verbose "  $line"
    done
    echo ""
    echo "  Fix: Remove kotlinCompilerExtensionVersion (now managed by kotlin(\"plugin.compose\"))"
else
    log_ok "No legacy kotlinCompilerExtensionVersion found"
fi

# =============================================================================
# CHECK 7: Reflection usage (limited in WASM)
# =============================================================================
log_header "7. Reflection Usage (limited in WASM)"

REFLECTION=$(grep -rn "::class\|KClass\|qualifiedName\|simpleName\|isInstance\|kotlin\.reflect" "$SHARED_DIR/commonMain" --include="*.kt" 2>/dev/null | grep -v "// " | head -20 || true)

if [ -n "$REFLECTION" ]; then
    REFL_COUNT=$(grep -rn "::class\|KClass\|qualifiedName" "$SHARED_DIR/commonMain" --include="*.kt" 2>/dev/null | wc -l || echo "0")
    log_warn "Found $REFL_COUNT potential reflection usages"

    if $VERBOSE; then
        echo "$REFLECTION" | while read -r line; do
            log_verbose "  $line"
        done
    fi

    echo ""
    echo "  Note: Basic ::class works, but qualifiedName increases binary size"
    echo "  Consider: Replace reflection with sealed class hierarchies where possible"
else
    log_ok "No significant reflection usage found"
fi

# =============================================================================
# CHECK 8: Okio usage (not supported in WASM)
# =============================================================================
log_header "8. Okio Usage (not supported in WASM)"

OKIO=$(grep -rn "okio\|Okio\|BufferedSource\|BufferedSink" "$SHARED_DIR/commonMain" --include="*.kt" 2>/dev/null || true)

if [ -n "$OKIO" ]; then
    OKIO_COUNT=$(echo "$OKIO" | wc -l)
    log_warn "Found $OKIO_COUNT Okio usages in commonMain (not WASM compatible)"

    if $VERBOSE; then
        echo "$OKIO" | head -10 | while read -r line; do
            log_verbose "  $line"
        done
    fi

    echo ""
    echo "  Fix: Move Okio usage to platform-specific source sets"
    echo "  Or: Use Ktor/browser APIs for wasmJsMain"
else
    log_ok "No Okio usage in commonMain"
fi

# =============================================================================
# CHECK 9: Gradle wrapper version
# =============================================================================
log_header "9. Gradle Wrapper Version"

if [ -f "$MOBILE_ROOT/gradle/wrapper/gradle-wrapper.properties" ]; then
    GRADLE_VERSION=$(grep "distributionUrl" "$MOBILE_ROOT/gradle/wrapper/gradle-wrapper.properties" | sed 's/.*gradle-\([0-9.]*\).*/\1/')

    # Extract major.minor for comparison
    GRADLE_MAJOR=$(echo "$GRADLE_VERSION" | cut -d. -f1)
    GRADLE_MINOR=$(echo "$GRADLE_VERSION" | cut -d. -f2)

    if [ "$GRADLE_MAJOR" -lt 8 ] || ([ "$GRADLE_MAJOR" -eq 8 ] && [ "$GRADLE_MINOR" -lt 7 ]); then
        log_warn "Gradle $GRADLE_VERSION needs upgrade to 8.7+ for AGP 8.5+"
        echo ""
        echo "  Fix: ./gradlew wrapper --gradle-version=8.7"
    else
        log_ok "Gradle $GRADLE_VERSION is compatible"
    fi
else
    log_warn "gradle-wrapper.properties not found"
fi

# =============================================================================
# CHECK 10: AGP version
# =============================================================================
log_header "10. Android Gradle Plugin Version"

AGP_VERSION=$(grep -h "com.android.application.*version\|id.*com.android" "$MOBILE_ROOT/build.gradle.kts" 2>/dev/null | grep -oP '\d+\.\d+\.\d+' | head -1 || true)

if [ -n "$AGP_VERSION" ]; then
    AGP_MAJOR=$(echo "$AGP_VERSION" | cut -d. -f1)
    AGP_MINOR=$(echo "$AGP_VERSION" | cut -d. -f2)

    if [ "$AGP_MAJOR" -lt 8 ] || ([ "$AGP_MAJOR" -eq 8 ] && [ "$AGP_MINOR" -lt 5 ]); then
        log_warn "AGP $AGP_VERSION needs upgrade to 8.5+ for Kotlin 2.x"
        echo ""
        echo "  Fix: Update to version(\"8.5.2\") or higher in build.gradle.kts"
    else
        log_ok "AGP $AGP_VERSION is compatible"
    fi
else
    log_warn "Could not detect AGP version"
fi

# =============================================================================
# SUMMARY
# =============================================================================
log_header "Migration Readiness Summary"

echo ""
if [ $ERRORS -gt 0 ]; then
    echo -e "${RED}${BOLD}ERRORS: $ERRORS${NC} - Must be fixed before migration"
fi

if [ $WARNINGS -gt 0 ]; then
    echo -e "${YELLOW}${BOLD}WARNINGS: $WARNINGS${NC} - Should be addressed"
fi

if [ $FIXED -gt 0 ]; then
    echo -e "${GREEN}${BOLD}FIXED: $FIXED${NC} - Auto-fixed issues"
fi

echo ""
if [ $ERRORS -eq 0 ] && [ $WARNINGS -le 5 ]; then
    echo -e "${GREEN}${BOLD}✓ READY FOR MIGRATION${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Run: ./scripts/migrate-to-kmp2.sh"
    echo "  2. Clean build: ./gradlew clean"
    echo "  3. Build: ./gradlew :shared:compileKotlinWasmJs"
    echo "  4. Test arm32: adb -s <device> install ..."
else
    echo -e "${YELLOW}${BOLD}⚠ REVIEW WARNINGS BEFORE MIGRATION${NC}"
    echo ""
    echo "Run with --fix to auto-fix safe issues:"
    echo "  $0 --fix"
fi

echo ""
exit $ERRORS
