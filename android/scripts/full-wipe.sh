#!/bin/bash
# Full wipe of CIRIS app data on Android device
# This forces a complete reset including template reload
#
# Uses Android's pm clear which properly wipes all app data

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Detect if running in WSL2
is_wsl() {
    if [[ -f /proc/version ]]; then
        grep -qi "microsoft\|wsl" /proc/version 2>/dev/null && return 0
    fi
    [[ -d /mnt/c/Windows ]] && return 0
    return 1
}

# Find ADB with environment-aware fallback locations
find_adb() {
    local adb_paths=()

    if is_wsl; then
        # WSL2: Prefer Windows ADB for USB device access
        adb_paths=(
            "/mnt/c/Users/moore/AppData/Local/Android/Sdk/platform-tools/adb.exe"
            "/mnt/c/Users/*/AppData/Local/Android/Sdk/platform-tools/adb.exe"
            "/mnt/c/Program Files/Android/Android Studio/platform-tools/adb.exe"
            "$ANDROID_HOME/platform-tools/adb"
            "$HOME/Android/Sdk/platform-tools/adb"
            "$(which adb 2>/dev/null)"
        )
    else
        # Native Linux: Prefer Linux ADB
        adb_paths=(
            "$ANDROID_HOME/platform-tools/adb"
            "$HOME/Android/Sdk/platform-tools/adb"
            "/opt/android-sdk/platform-tools/adb"
            "/usr/lib/android-sdk/platform-tools/adb"
            "/usr/bin/adb"
            "$(which adb 2>/dev/null)"
        )
    fi

    for adb in "${adb_paths[@]}"; do
        # Handle glob patterns (e.g., /mnt/c/Users/*)
        for expanded in $adb; do
            if [[ -x "$expanded" ]]; then
                echo "$expanded"
                return 0
            fi
        done
    done

    return 1
}

# Find ADB
if ! ADB=$(find_adb); then
    echo "ERROR: adb not found. Please set ANDROID_HOME or install Android SDK."
    exit 1
fi

PACKAGE="ai.ciris.mobile"

echo "=============================================="
echo "  CIRIS Full Data Wipe"
echo "=============================================="
echo ""
echo "WARNING: This will delete ALL app data including:"
echo "  - Databases (conversations, memory, audit)"
echo "  - Configuration files"
echo "  - OAuth tokens and secrets"
echo "  - Encryption keys"
echo "  - Logs"
echo ""

# Check for --yes flag to skip confirmation
if [[ "$1" != "--yes" && "$1" != "-y" ]]; then
    read -p "Are you sure? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
fi

echo "Clearing all app data..."
$ADB shell "pm clear $PACKAGE"

echo ""
echo "Restarting app..."
sleep 1
$ADB shell "monkey -p $PACKAGE -c android.intent.category.LAUNCHER 1" 2>/dev/null || true

echo ""
echo "=============================================="
echo "  Full wipe complete - app restarted fresh"
echo "=============================================="
echo ""
echo "The app will now initialize with default settings."
echo "You will need to:"
echo "  1. Sign in again"
echo "  2. Reconfigure any adapters (Home Assistant, etc.)"
