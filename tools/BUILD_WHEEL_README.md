# CIRIS Agent Test Wheel Builder

Build a local test wheel for the CIRIS Agent with bundled GUI assets.

## Overview

This script mimics the GitHub Actions CI build process to create a pip-installable wheel that includes:
- CIRIS Agent Python code
- Bundled Next.js GUI static assets
- Templates and configuration files
- CLI entrypoint

## Prerequisites

**Required:**
- Python 3.12+
- Node.js 20+
- npm
- git

**Python packages (auto-installed):**
- build
- twine

## Usage

### Option 1: Bash Script (Linux/macOS)

```bash
./tools/build_test_wheel.sh
```

### Option 2: Python Script (Cross-platform)

```bash
python tools/build_test_wheel.py
```

## Build Process

The script performs the following steps:

### 1. Clean Previous Builds
- Removes `dist/`, `build/`, `*.egg-info`
- Removes `ciris_engine/gui_static/`
- Removes temporary GUI clone

### 2. Build GUI Assets
- Clones [CIRISGUI-Standalone](https://github.com/CIRISAI/CIRISGUI-Standalone)
- Finds Next.js app directory
- Configures for static export (`output: 'export'`)
- Runs `npm ci` to install dependencies
- Runs `npm run build` to build static assets
- Exports to `out/` directory

### 3. Copy GUI Assets
- Copies built GUI to `ciris_engine/gui_static/`
- Verifies file count (should be 100+ files)

### 4. Install Build Tools
- Upgrades pip
- Installs `build` and `twine` packages

### 5. Build Python Wheel
- Runs `python -m build --wheel`
- Creates wheel in `dist/` directory
- Includes GUI assets from `ciris_engine/gui_static/`

### 6. Verify Wheel Contents
- Lists files in wheel
- Checks for `gui_static` assets
- Checks for `covenant` files
- Checks for `main.py`
- Shows total file count

### 7. Cleanup
- Removes temporary GUI clone directory

## Output

The wheel file will be created in:
```
dist/ciris_agent-1.6.5-py3-none-any.whl
```

The version number comes from `ciris_engine/constants.py`.

## Installing the Wheel

### Local Installation

```bash
pip install dist/ciris_agent-1.6.5-py3-none-any.whl
```

### Test the Installation

```bash
ciris-agent --help
ciris-agent --version
ciris-agent --adapter api
```

### First-Run Setup

After installation, the first run will launch the setup wizard:

```bash
ciris-agent --adapter api
```

Then visit: http://localhost:8080 for the GUI setup wizard

## Uploading to PyPI

**For maintainers only:**

```bash
python -m twine upload dist/ciris_agent-1.6.5-py3-none-any.whl
```

Requires PyPI credentials or token.

## Troubleshooting

### GUI Build Fails

**Problem:** `npm run build` fails

**Solution:**
1. Check Node.js version: `node --version` (should be 20+)
2. Clear npm cache: `npm cache clean --force`
3. Delete `cirisgui_temp/` and retry

### No GUI Files in Wheel

**Problem:** `gui_static` directory is empty

**Solution:**
1. Check `ciris_engine/gui_static/` exists and has files
2. Verify `MANIFEST.in` includes: `recursive-include ciris_engine/gui_static *`
3. Check `setup.py` has `include_package_data=True`

### Wheel Build Fails

**Problem:** `python -m build --wheel` fails

**Solution:**
1. Upgrade build tools: `pip install --upgrade pip build setuptools`
2. Check `setup.py` syntax
3. Ensure `ciris_engine/constants.py` exists

## Files Included in Wheel

- **Python Code:** `ciris_engine/**/*.py`
- **GUI Assets:** `ciris_engine/gui_static/**/*`
- **Templates:** `ciris_engine/ciris_templates/*.yaml`
- **Covenant:** `ciris_engine/covenant/**/*`
- **CLI:** `main.py` (entrypoint: `ciris-agent`)
- **Metadata:** `setup.py`, `pyproject.toml`, `requirements.txt`

## Directory Structure After Build

```
CIRISAgent/
├── dist/
│   └── ciris_agent-1.6.5-py3-none-any.whl  ← Built wheel
├── ciris_engine/
│   └── gui_static/                         ← Bundled GUI (included in wheel)
│       ├── _next/
│       ├── index.html
│       └── ...
└── tools/
    ├── build_test_wheel.sh                 ← Bash build script
    └── build_test_wheel.py                 ← Python build script
```

## CI/CD Integration

This script replicates the GitHub Actions workflow in `.github/workflows/build.yml`:

- **Job:** `build-gui` - Builds GUI assets
- **Job:** `build-wheel` - Bundles GUI and builds wheel
- **Job:** `build` - Builds Docker images

The local build produces the same wheel artifact as CI.

## Version Management

The wheel version is automatically read from:
```python
# ciris_engine/constants.py
CIRIS_VERSION = "1.6.5-stable"
```

To bump the version before building:
```bash
python tools/dev/bump_version.py patch  # 1.6.5 → 1.6.6
python tools/dev/bump_version.py minor  # 1.6.5 → 1.7.0
python tools/dev/bump_version.py major  # 1.6.5 → 2.0.0
```

## Notes

- **Build Time:** 5-10 minutes (most time is GUI build)
- **Wheel Size:** ~10-20 MB (includes GUI assets)
- **Platform:** Platform-independent (pure Python)
- **Python Version:** Requires Python 3.12+

## Support

For issues with:
- **Build script:** Open issue in CIRISAgent repo
- **GUI build:** Check CIRISGUI-Standalone repo
- **Wheel installation:** Check pip/setuptools version
