#!/bin/bash
# Prepares the source code for the iOS build by copying it into the Briefcase project structure.

set -e

BASE_DIR="$(pwd)"
IOS_SRC_DIR="$BASE_DIR/ios/CirisiOS/src"

echo "=== Preparing iOS Source ==="

# Clean old copies
rm -rf "$IOS_SRC_DIR/ciris_engine"
rm -rf "$IOS_SRC_DIR/ciris_adapters"
rm -rf "$IOS_SRC_DIR/ciris_sdk"

# Copy new source
echo "Copying ciris_engine..."
cp -r "$BASE_DIR/ciris_engine" "$IOS_SRC_DIR/"

echo "Copying ciris_adapters..."
cp -r "$BASE_DIR/ciris_adapters" "$IOS_SRC_DIR/"

echo "Copying ciris_sdk..."
cp -r "$BASE_DIR/ciris_sdk" "$IOS_SRC_DIR/"

# Remove artifacts that might be in the source
find "$IOS_SRC_DIR" -name "__pycache__" -type d -exec rm -rf {} +
find "$IOS_SRC_DIR" -name "*.pyc" -delete
find "$IOS_SRC_DIR" -name ".DS_Store" -delete

echo "Source preparation complete."
