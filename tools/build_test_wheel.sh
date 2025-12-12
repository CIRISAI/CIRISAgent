#!/bin/bash
# Build test wheel with bundled GUI for local testing
# This script mimics the GitHub Actions CI build process

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "=================================="
echo "CIRIS Agent Test Wheel Builder"
echo "=================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print colored messages
print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo "ℹ️  $1"
}

# Step 1: Clean previous builds
echo "Step 1: Cleaning previous builds..."
rm -rf dist/ build/ *.egg-info ciris_engine/gui_static/ cirisgui_temp/
print_success "Cleaned build directories"
echo ""

# Step 2: Clone and build GUI
echo "Step 2: Building GUI assets..."
print_info "Cloning CIRISGUI-Standalone repository..."

if [ ! -d "cirisgui_temp" ]; then
    git clone https://github.com/CIRISAI/CIRISGUI-Standalone.git cirisgui_temp
else
    print_warning "Using existing cirisgui_temp directory"
fi

# Find the Next.js app directory (look for next.config.mjs or next.config.js)
print_info "Finding Next.js app directory..."
GUI_DIR=$(find cirisgui_temp -name "next.config.mjs" -o -name "next.config.js" | head -1 | xargs dirname)

if [ -z "$GUI_DIR" ]; then
    print_error "Could not find Next.js app in CIRISGUI-Standalone repo"
    exit 1
fi

print_success "Found Next.js app in: $GUI_DIR"

# Verify next.config exists
if [ -f "$GUI_DIR/next.config.mjs" ]; then
    print_success "Found next.config.mjs"
    NEXT_CONFIG="$GUI_DIR/next.config.mjs"
elif [ -f "$GUI_DIR/next.config.js" ]; then
    print_success "Found next.config.js"
    NEXT_CONFIG="$GUI_DIR/next.config.js"
else
    print_warning "next.config not found in $GUI_DIR"
    NEXT_CONFIG=""
fi

# Configure for static export
print_info "Configuring for static export..."
cd "$GUI_DIR"

if [ -n "$NEXT_CONFIG" ] && [ -f "$NEXT_CONFIG" ]; then
    CONFIG_FILE=$(basename "$NEXT_CONFIG")
    if ! grep -q "output.*:.*['\"]export['\"]" "$CONFIG_FILE" 2>/dev/null; then
        print_warning "Adding output: 'export' to $CONFIG_FILE"
        cp "$CONFIG_FILE" "${CONFIG_FILE}.bak"
        sed -i "s/const nextConfig = {/const nextConfig = {\n  output: 'export',/" "$CONFIG_FILE" || true
    fi
    print_success "Static export configuration verified"
fi

# Install dependencies
print_info "Installing Node.js dependencies..."
npm install

# Build static assets
print_info "Building static assets (this may take a few minutes)..."
npm run build

# Check for static export
if [ -d "out" ]; then
    print_success "Using static export from out/"
    BUILD_OUTPUT="out"
elif [ -d ".next/standalone" ]; then
    print_success "Using standalone build from .next/standalone"
    BUILD_OUTPUT=".next/standalone"
elif [ -d ".next/static" ]; then
    print_success "Using static build from .next/static"
    BUILD_OUTPUT=".next/static"
else
    print_error "No build output found (checked: out/, .next/standalone, .next/static)"
    ls -la
    exit 1
fi

FILE_COUNT=$(find "$BUILD_OUTPUT" -type f | wc -l)
print_success "GUI build complete - $FILE_COUNT files generated"
echo ""

# Step 3: Copy GUI assets to ciris_engine
echo "Step 3: Copying GUI assets to ciris_engine/gui_static/..."
cd "$PROJECT_ROOT"
mkdir -p ciris_engine/gui_static
cp -r "$GUI_DIR/$BUILD_OUTPUT"/* ciris_engine/gui_static/

# Verify copy
COPIED_FILES=$(find ciris_engine/gui_static -type f | wc -l)
if [ "$COPIED_FILES" -lt 5 ]; then
    print_warning "Very few GUI files found: $COPIED_FILES"
else
    print_success "Copied $COPIED_FILES GUI files to ciris_engine/gui_static/"
fi
echo ""

# Step 4: Install build tools
echo "Step 4: Installing Python build tools..."
pip install --upgrade pip build twine
print_success "Build tools installed"
echo ""

# Step 5: Build wheel
echo "Step 5: Building Python wheel..."
python -m build --wheel
print_success "Wheel built successfully"
echo ""

# Step 6: Verify wheel contents
echo "Step 6: Verifying wheel contents..."
WHEEL_FILE=$(ls dist/*.whl)
print_info "Wheel file: $WHEEL_FILE"

echo ""
print_info "Checking for gui_static assets in wheel..."
unzip -l "$WHEEL_FILE" | grep "gui_static" | head -10 || print_warning "No gui_static files found in wheel"

echo ""
print_info "Checking for covenant files..."
unzip -l "$WHEEL_FILE" | grep "covenant" | head -5 || print_warning "No covenant files found in wheel"

echo ""
print_info "Checking for main.py..."
unzip -l "$WHEEL_FILE" | grep "main.py" || print_warning "main.py not found in wheel"

echo ""
print_info "Total files in wheel:"
unzip -l "$WHEEL_FILE" | tail -1
echo ""

# Step 7: Cleanup
echo "Step 7: Cleaning up temporary files..."
rm -rf cirisgui_temp/
print_success "Cleanup complete"
echo ""

# Final summary
echo "=================================="
echo "Build Complete!"
echo "=================================="
echo ""
print_success "Wheel file: $WHEEL_FILE"
echo ""
print_info "To install locally:"
echo "  pip install $WHEEL_FILE"
echo ""
print_info "To test the installation:"
echo "  pip install $WHEEL_FILE"
echo "  ciris-agent --help"
echo ""
print_info "To upload to PyPI (if you have credentials):"
echo "  python -m twine upload $WHEEL_FILE"
echo ""
