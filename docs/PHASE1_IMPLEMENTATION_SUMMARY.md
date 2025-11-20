# Phase 1 Implementation Summary: Python Packaging Foundation

**Date**: 2025-11-19
**Status**: Ready for Implementation

## Pre-flight Check Results ✅

CIRISGUI is **static export compatible**:
- ✅ No `getServerSideProps` in source code
- ✅ No `/pages/api/*` or `/app/api/*` routes
- ✅ Minimal `next.config.js` ready for `output: 'export'`

## Architecture Understanding

### Current System
- **Entry point**: `python main.py --adapter api --port 8000`
- **CLI framework**: Click (not typer)
- **Runtime**: `CIRISRuntime` coordinates all 22 services
- **Adapters**: cli, api, discord, reddit, modular services
- **API creation**: `ApiPlatform` (adapter.py:76) calls `create_app(runtime, config)` from app.py
- **Routes mounted**: 18 v1 routers + emergency routes (app.py:158-186)

### Key Files
1. `main.py` - Main entrypoint with Click CLI
2. `ciris_engine/logic/adapters/api/app.py` - FastAPI app factory (create_app)
3. `ciris_engine/logic/adapters/api/adapter.py` - ApiPlatform adapter class

## Phase 1 Tasks

### Task 1: Modify FastAPI app.py to Support GUI Static Files ✅

**File**: `ciris_engine/logic/adapters/api/app.py`

**Changes needed** (around line 187, AFTER all routes are mounted):

```python
# Mount GUI static assets (if available) - MUST be LAST for proper route priority
gui_static_dir = Path(__file__).parent.parent.parent / "gui_static"

if gui_static_dir.exists() and any(gui_static_dir.iterdir()):
    from fastapi.staticfiles import StaticFiles

    # Serve GUI at root (/) - catch-all, lowest priority
    app.mount("/", StaticFiles(directory=str(gui_static_dir), html=True), name="gui")
    print(f"✅ GUI enabled at / (static assets: {gui_static_dir})")
else:
    # No GUI - API-only mode
    @app.get("/")
    def root():
        return {
            "name": "CIRIS API",
            "version": "1.0.0",
            "docs": "/docs",
            "gui": "not_available"
        }
    print("ℹ️  API-only mode (no GUI assets found)")
```

**Route priority** (FastAPI matches in order):
1. `/v1/*` - API routes (highest priority)
2. `/emergency/*` - Emergency routes
3. `/docs`, `/redoc`, `/openapi.json` - FastAPI docs
4. `/*` - GUI static assets (lowest priority, catch-all)

### Task 2: Update CLI Entrypoint ✅

**File**: `ciris_engine/cli.py`

**Simplified approach** - Just wrap main.py:

```python
"""
CIRIS Agent CLI - Thin wrapper around main.py
"""
import sys
from pathlib import Path

def main():
    """Entry point that delegates to main.py"""
    # Add parent directory to path
    parent_dir = Path(__file__).parent.parent
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))

    # Import and run main
    import main as ciris_main
    ciris_main.main()

if __name__ == "__main__":
    main()
```

**Why this works**: Preserves all existing Click functionality, just provides a `ciris-agent` command that runs `main.py`.

### Task 3: Python Packaging (setup.py) ✅

**Files created**:
- `setup.py` - Package configuration
- `MANIFEST.in` - Include non-Python files

**Changes needed** in `setup.py`:
- Remove typer dependency (use click instead)
- Keep simple wrapper CLI

```python
entry_points={
    "console_scripts": [
        "ciris-agent=ciris_engine.cli:main",  # Just wraps main.py
    ],
},
```

### Task 4: Add Missing Dependencies

**File**: `requirements.txt`

**Add**:
- `click>=8.0.0` (already present, verify)
- **Remove**: `typer>=0.9.0` (not needed, using click)

### Task 5: Test Local Installation

```bash
# 1. Build wheel (WITHOUT GUI first)
python -m build --wheel

# 2. Verify wheel contents
unzip -l dist/ciris_agent-1.6.2-py3-none-any.whl | grep cli.py

# 3. Install locally
pip install --force-reinstall dist/ciris_agent-1.6.2-py3-none-any.whl

# 4. Test CLI wrapper
ciris-agent --adapter api --port 8000 --mock-llm

# 5. Test API-only mode (no GUI yet)
curl http://localhost:8000/
# Should return: {"name": "CIRIS API", "gui": "not_available"}

# 6. Test API endpoints still work
curl http://localhost:8000/v1/system/health
```

## Phase 2 Preview: CI GUI Build

Once Phase 1 is validated, Phase 2 will:

1. **Update CIRISGUI next.config.js**:
   ```javascript
   module.exports = {
     output: 'export',
     images: { unoptimized: true },
     trailingSlash: true,
   }
   ```

2. **Add CI job to build.yml**:
   ```yaml
   build-gui:
     - Checkout CIRISGUI
     - Setup Node.js 20 + pnpm
     - pnpm install && pnpm build
     - Upload out/ as artifact

   build-wheel:
     needs: [test, build-gui]
     - Download GUI artifact → ciris_engine/gui_static/
     - python -m build --wheel
     - Result: Wheel with GUI bundled
   ```

3. **Test with GUI**:
   ```bash
   pip install dist/ciris_agent-1.6.2-py3-none-any.whl
   ciris-agent --adapter api --port 8000
   # Should open browser with GUI
   ```

## Success Criteria for Phase 1

- ✅ `python -m build --wheel` creates wheel successfully
- ✅ `pip install dist/*.whl` installs without errors
- ✅ `ciris-agent --help` shows Click help (delegates to main.py)
- ✅ `ciris-agent --adapter api` starts API server
- ✅ `curl http://localhost:8000/` returns JSON (API-only mode)
- ✅ `curl http://localhost:8000/v1/system/health` works
- ✅ All existing tests pass: `pytest -n 16 tests/`

## Files Modified Summary

1. **`ciris_engine/logic/adapters/api/app.py`** - Add GUI static mounting
2. **`ciris_engine/cli.py`** - Simplify to thin wrapper
3. **`setup.py`** - Fix to use click, not typer
4. **`requirements.txt`** - Remove typer line (if added)

## Next Immediate Steps

1. Fix `ciris_engine/cli.py` to be a thin wrapper
2. Modify `app.py` to add GUI static file support
3. Fix `setup.py` to remove typer dependency
4. Rebuild wheel and test local installation
5. Document results

---

**Key Insight**: Don't reinvent the CLI - just wrap the existing `main.py` with a simple `ciris-agent` command that preserves all Click functionality.
