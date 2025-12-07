#!/bin/bash
# Full wipe of CIRIS app data on Android device
# This forces a complete reset including template reload
#
# Uses Android's pm clear which properly wipes all app data

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Find ADB
if [[ -f "/mnt/c/Users/moore/AppData/Local/Android/Sdk/platform-tools/adb.exe" ]]; then
    ADB="/mnt/c/Users/moore/AppData/Local/Android/Sdk/platform-tools/adb.exe"
elif command -v adb &> /dev/null; then
    ADB="adb"
else
    echo "ERROR: adb not found"
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
