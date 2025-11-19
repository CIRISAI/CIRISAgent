# GUI Integration Evaluation: CI Artifact Injection Approach

**Date**: 2025-11-19
**Status**: Evaluation Complete
**Decision**: Recommended Approach

## Executive Summary

This document evaluates the feasibility of integrating CIRISGUI into CIRISAgent via **CI artifact injection** - building GUI static assets during CIRISAgent CI and bundling them into a Python wheel for pip-installable deployment.

**User Requirements:**
- "I am ok having a big package" - Accepts 50-100MB wheel size
- "building GUI artifacts in agent CI" - CI-time injection preferred
- "default to no docker" - Python-native experience as default
- "serving the assets from fastapi" - Static file mounting via FastAPI

**Recommendation: ✅ PROCEED with CI Artifact Injection**

This approach aligns with Python packaging conventions, provides excellent developer experience, and leverages existing FastAPI infrastructure.

---

## Current State Analysis

### CIRISAgent Architecture

**Current Installation Method:**
```bash
bash scripts/install.sh --docker  # Docker-based deployment
bash scripts/install.sh --local   # Local Python deployment
```

**Key Findings:**
1. ❌ **No Python packaging** - No setup.py, minimal pyproject.toml, no wheel distribution
2. ✅ **FastAPI infrastructure ready** - 18 routers mounted at /v1, all 22 services in app.state
3. ✅ **CI builds Docker images** - build.yml workflow runs tests, mypy, builds containers
4. ✅ **Local runtime mode exists** - All 22 services run in single Python process (no Docker required)

**FastAPI Structure** (`ciris_engine/logic/adapters/api/app.py`):
```python
app = FastAPI(
    title="CIRIS API v1",
    description="Autonomous AI Agent Interaction and Observability API",
    version="1.0.0",
    lifespan=lifespan,
    root_path=root_path,  # Reverse proxy support
)

# 18 v1 routers: agent, billing, memory, system, config, telemetry, audit, wa, auth, etc.
for router in v1_routers:
    app.include_router(router, prefix="/v1")
```

---

## Proposed Architecture

### Overview: Three-Mode Deployment

```
┌─────────────────────────────────────────────────────────────────┐
│                     pip install ciris-agent                      │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
              ┌──────────────────────────────────┐
              │   CIRISAgent Python Wheel        │
              │   • Python code (22 services)    │
              │   • GUI static assets (bundled)  │
              │   • CLI entrypoint               │
              └──────────────────────────────────┘
                                 │
                 ┌───────────────┼───────────────┐
                 ▼               ▼               ▼
          ┌───────────┐   ┌───────────┐   ┌───────────┐
          │ CLI Mode  │   │ API Mode  │   │Docker Mode│
          │  (basic)  │   │ (w/ GUI)  │   │(production)│
          └───────────┘   └───────────┘   └───────────┘
```

**Mode 1: CLI (Basic) - No GUI**
```bash
ciris-agent --adapter cli
```
- Terminal-only interaction
- Minimal resource usage
- Scriptable/automatable

**Mode 2: API with GUI (Python-native, DEFAULT)**
```bash
ciris-agent --adapter api --port 8000
# Opens browser to http://localhost:8000
```
- FastAPI serves GUI static assets at `/` (root)
- API endpoints at `/v1/*`
- Single Python process (no Docker)
- Development-friendly

**Mode 3: Docker (Production)**
```bash
docker run ghcr.io/cirisai/ciris-agent:latest
```
- Current production deployment
- Docker Compose orchestration
- Nginx reverse proxy
- Multi-agent deployments

---

## Technical Implementation Plan

### 1. Python Packaging Setup

**Create `setup.py` or enhance `pyproject.toml`:**

```python
# setup.py
from setuptools import setup, find_packages

setup(
    name="ciris-agent",
    version="1.6.2",
    packages=find_packages(),
    include_package_data=True,  # CRITICAL - includes non-Python files
    package_data={
        "ciris_engine": [
            "gui_static/**/*",  # All GUI assets
        ],
    },
    entry_points={
        "console_scripts": [
            "ciris-agent=ciris_engine.cli:main",
        ],
    },
    install_requires=[
        # ... from requirements.txt
    ],
)
```

**Create `MANIFEST.in`:**
```
# Include GUI static assets
recursive-include ciris_engine/gui_static *
```

**Package structure after build:**
```
ciris_engine/
├── logic/
│   ├── adapters/
│   │   └── api/
│   │       └── app.py
│   └── ...
├── gui_static/           # ← GUI assets bundled here
│   ├── _next/
│   │   ├── static/
│   │   └── chunks/
│   ├── index.html
│   ├── favicon.ico
│   └── ...
└── ...
```

### 2. FastAPI Static File Mounting

**Modify `ciris_engine/logic/adapters/api/app.py`:**

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os

def create_app(runtime: Any = None, adapter_config: Any = None) -> FastAPI:
    app = FastAPI(...)

    # ... existing middleware and route setup ...

    # Mount GUI static assets (if available)
    gui_static_dir = Path(__file__).parent.parent.parent / "gui_static"

    if gui_static_dir.exists():
        # Serve GUI at root (/) - MUST be mounted LAST
        app.mount("/", StaticFiles(directory=str(gui_static_dir), html=True), name="gui")
        print(f"✅ GUI enabled at / (static assets: {gui_static_dir})")
    else:
        # No GUI - API-only mode
        @app.get("/")
        def root():
            return {
                "name": "CIRIS API",
                "version": "1.0.0",
                "endpoints": "/docs",
                "gui": "not_available"
            }
        print("ℹ️  API-only mode (no GUI assets found)")

    return app
```

**Route Priority:**
1. `/v1/*` - API routes (highest priority)
2. `/emergency/*` - Emergency routes (no auth)
3. `/docs`, `/redoc`, `/openapi.json` - FastAPI docs
4. `/*` - GUI static assets (lowest priority, catch-all)

### 3. CI Workflow Modifications

**Enhance `.github/workflows/build.yml`:**

```yaml
jobs:
  test:
    # ... existing test job ...

  build-gui:
    name: Build GUI Assets
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          repository: CIRISAI/CIRISGUI
          path: gui-repo

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install pnpm
        run: npm install -g pnpm

      - name: Build GUI
        working-directory: gui-repo
        run: |
          pnpm install
          pnpm build

      - name: Upload GUI artifacts
        uses: actions/upload-artifact@v4
        with:
          name: gui-static
          path: gui-repo/out/  # Next.js static export output
          retention-days: 1

  build-wheel:
    name: Build Python Wheel
    needs: [test, build-gui]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Download GUI artifacts
        uses: actions/download-artifact@v4
        with:
          name: gui-static
          path: ciris_engine/gui_static/

      - name: Verify GUI artifacts
        run: |
          echo "GUI assets:"
          ls -lh ciris_engine/gui_static/
          du -sh ciris_engine/gui_static/

      - name: Build wheel
        run: |
          pip install build
          python -m build --wheel

      - name: Upload wheel
        uses: actions/upload-artifact@v4
        with:
          name: ciris-wheel
          path: dist/*.whl

  build-docker:
    name: Build Docker Images
    needs: build-wheel
    # ... use wheel in Docker image ...
```

### 4. Next.js Static Export Configuration

**CIRISGUI must be configured for static export:**

```javascript
// next.config.js
module.exports = {
  output: 'export',  // Static HTML export
  images: {
    unoptimized: true,  // No Next.js Image Optimization API
  },
  trailingSlash: true,  // Ensure proper routing
  assetPrefix: process.env.ASSET_PREFIX || '',
}
```

**Build command:**
```bash
pnpm build  # Outputs to out/ directory
```

**Output structure:**
```
out/
├── _next/
│   ├── static/
│   │   ├── chunks/
│   │   ├── css/
│   │   └── media/
│   └── ...
├── index.html
├── agent.html
├── settings.html
├── favicon.ico
└── ...
```

**Size estimate:** 5-20MB (depends on dependencies, images)

---

## Implementation Phases

### Phase 1: Python Packaging Foundation (Week 1)
**Goal:** Create pip-installable package WITHOUT GUI

```bash
pip install ciris-agent
ciris-agent --adapter cli  # Works
ciris-agent --adapter api  # Works (API-only mode)
```

**Tasks:**
1. Create `setup.py` with proper metadata
2. Create `MANIFEST.in` for non-Python files
3. Add `console_scripts` entrypoint
4. Test wheel build: `python -m build --wheel`
5. Test local install: `pip install dist/ciris_agent-1.6.2-py3-none-any.whl`
6. Verify all adapters work (cli, api, discord)

**Success Criteria:**
- ✅ `pip install ciris-agent` installs all dependencies
- ✅ `ciris-agent --help` shows CLI help
- ✅ `ciris-agent --adapter cli` starts CLI
- ✅ All tests pass: `pytest -n 16 tests/`

### Phase 2: CI GUI Build (Week 2)
**Goal:** Build GUI assets in CI, bundle in wheel

```bash
pip install ciris-agent  # Now includes GUI
ciris-agent --adapter api  # Opens browser with GUI
```

**Tasks:**
1. Add `build-gui` job to `.github/workflows/build.yml`
2. Checkout CIRISGUI in CI
3. Build with `pnpm build`
4. Upload as artifact
5. Download in `build-wheel` job
6. Copy to `ciris_engine/gui_static/`
7. Build wheel with GUI assets

**Success Criteria:**
- ✅ CI successfully builds GUI
- ✅ Wheel includes `ciris_engine/gui_static/`
- ✅ Wheel size: 50-100MB (acceptable per user)
- ✅ `ciris-agent --adapter api` serves GUI at `/`

### Phase 3: FastAPI Static Mounting (Week 3)
**Goal:** Serve GUI from FastAPI

**Tasks:**
1. Modify `ciris_engine/logic/adapters/api/app.py`
2. Add `StaticFiles` mount at `/` (lowest priority)
3. Detect presence of `gui_static/` directory
4. Fallback to API-only mode if not present
5. Test route priority (API routes take precedence)
6. Add browser auto-open on startup

**Success Criteria:**
- ✅ `http://localhost:8000/` serves GUI
- ✅ `http://localhost:8000/v1/system/health` serves API
- ✅ GUI can call API endpoints
- ✅ CORS configured correctly
- ✅ WebSocket support (if needed)

### Phase 4: Integration Testing (Week 4)
**Goal:** End-to-end testing

**Tasks:**
1. Install from wheel: `pip install dist/*.whl`
2. Start API mode: `ciris-agent --adapter api`
3. Open browser, verify GUI loads
4. Test authentication flow
5. Test agent interaction
6. Test all GUI features
7. Test on multiple platforms (Linux, macOS, Windows)

**Success Criteria:**
- ✅ GUI loads in <3 seconds
- ✅ API requests complete in <1 second
- ✅ Authentication works
- ✅ WebSocket streaming works
- ✅ All QA tests pass: `python -m tools.qa_runner`

---

## Technical Considerations

### Next.js Static Export Limitations

**✅ Compatible Features:**
- Client-side routing (React Router)
- Client-side data fetching (fetch, axios)
- Static assets (images, fonts, CSS)
- Environment variables (build-time)
- API routes → External API calls (CIRIS API)

**❌ Incompatible Features (Not Usable):**
- Server-side rendering (SSR)
- API routes (`pages/api/`)
- Dynamic routes with `getServerSideProps`
- Incremental Static Regeneration (ISR)
- Image Optimization API (use `unoptimized: true`)

**CIRISGUI must use:**
- Client-side rendering only
- Client-side routing (e.g., React Router, Next.js App Router with static export)
- API calls to CIRIS FastAPI at `/v1/*`
- Static assets only

### FastAPI Route Priority

**Mount order (in `app.py`):**
```python
# 1. Include specific routes FIRST (highest priority)
app.include_router(auth.router, prefix="/v1")
app.include_router(agent.router, prefix="/v1")
# ... all v1 routers ...

app.include_router(emergency.router)  # No prefix

# 2. Mount static files LAST (catch-all, lowest priority)
app.mount("/", StaticFiles(directory="gui_static", html=True), name="gui")
```

**Why this works:**
- FastAPI matches routes in order of registration
- Specific paths (`/v1/auth/login`) match before catch-all (`/*`)
- StaticFiles acts as fallback for unmatched routes

**Test coverage needed:**
```bash
# Should serve API
curl http://localhost:8000/v1/system/health

# Should serve GUI
curl http://localhost:8000/
curl http://localhost:8000/agent
curl http://localhost:8000/settings
```

### Package Size Analysis

**Current ciris-agent size (without GUI):**
- Python code: ~10MB
- Dependencies: ~200MB (installed, not in wheel)
- Total wheel: ~10MB

**With GUI (estimated):**
- Python code: ~10MB
- GUI static assets: ~5-20MB
  - Next.js runtime: ~1-2MB
  - React/dependencies: ~2-5MB
  - Application code: ~1-3MB
  - Images/fonts: ~1-10MB
- **Total wheel: ~15-30MB**

**Acceptable per user:**
> "I am ok having a big package"

**Comparison to other tools:**
- `torch`: ~800MB wheel
- `tensorflow`: ~500MB wheel
- `pandas`: ~50MB wheel
- `ciris-agent` (with GUI): ~15-30MB ✅

### CORS Configuration

**Current CORS (`app.py:80-86`):**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Too permissive
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Recommended for production:**
```python
# Serve GUI at same origin → No CORS issues
# API and GUI both at http://localhost:8000
allow_origins=[
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "https://agents.ciris.ai",
]
```

**Why this works:**
- GUI served from `/` (same origin as API at `/v1/`)
- No cross-origin requests needed
- Simpler security model

---

## Alternative Approaches (Rejected)

### ❌ Alternative 1: Separate GUI Download

**Approach:**
```bash
pip install ciris-agent  # Python only
ciris-agent --install-gui  # Downloads GUI separately
```

**Rejected because:**
- ❌ Two-step installation (poor UX)
- ❌ Version mismatch risks
- ❌ Network dependency at runtime
- ❌ Doesn't match user preference: "building GUI artifacts in agent CI"

### ❌ Alternative 2: Monorepo

**Approach:**
```
CIRISAgent/
├── backend/  # Python code
├── frontend/  # Next.js code
└── ...
```

**Rejected because:**
- ❌ Bloats git history with frontend assets
- ❌ Slower CI (builds everything always)
- ❌ Doesn't follow Python conventions
- ❌ Complex repository structure

### ❌ Alternative 3: Docker-Only GUI

**Approach:**
```bash
pip install ciris-agent  # Python only (no GUI)
docker run ciris-agent   # GUI available in Docker only
```

**Rejected because:**
- ❌ Violates user requirement: "default to no docker"
- ❌ Poor Python developer experience
- ❌ Doesn't match Python packaging conventions
- ❌ Forces Docker dependency for GUI access

---

## Risk Assessment

### High Risks

**1. Next.js Static Export Compatibility**
- **Risk:** CIRISGUI may use SSR/API routes incompatible with static export
- **Mitigation:** Audit CIRISGUI codebase, refactor to client-side only
- **Impact if not addressed:** Cannot bundle GUI in wheel

**2. Wheel Size Exceeds PyPI Limits**
- **Risk:** PyPI has 100MB limit for wheels
- **Mitigation:** Optimize GUI assets, use tree-shaking, compression
- **Impact if not addressed:** Cannot publish to PyPI (use GitHub releases instead)

**3. CI Build Time**
- **Risk:** Building GUI in CI adds 5-10 minutes per build
- **Mitigation:** Cache pnpm dependencies, parallelize jobs
- **Impact if not addressed:** Slower CI, developer frustration

### Medium Risks

**4. Route Collision**
- **Risk:** GUI routes conflict with API routes (e.g., `/v1` page in GUI)
- **Mitigation:** Document reserved routes, test coverage
- **Impact if not addressed:** 404 errors, broken functionality

**5. WebSocket Support**
- **Risk:** GUI may need WebSocket for real-time updates
- **Mitigation:** FastAPI supports WebSocket out of the box
- **Impact if not addressed:** Degraded UX (polling instead of push)

**6. Cross-Platform Compatibility**
- **Risk:** GUI assets may not work on Windows (path separators, etc.)
- **Mitigation:** Use `pathlib.Path`, test on Windows
- **Impact if not addressed:** Windows users cannot use GUI

### Low Risks

**7. Version Mismatch**
- **Risk:** GUI version doesn't match API version
- **Mitigation:** Version check on startup, display in GUI
- **Impact if not addressed:** Confusing errors, support burden

**8. Asset Caching**
- **Risk:** Browser caches old GUI assets after update
- **Mitigation:** Next.js uses content hashes in filenames
- **Impact if not addressed:** Users see stale UI

---

## Success Criteria

### Must-Have (Phase 1-3)
- ✅ `pip install ciris-agent` installs package with GUI
- ✅ `ciris-agent --adapter api` serves GUI at `/`
- ✅ All API endpoints remain functional at `/v1/*`
- ✅ GUI can authenticate and interact with API
- ✅ All existing tests pass
- ✅ CI builds and bundles GUI automatically

### Should-Have (Phase 4)
- ✅ GUI loads in <3 seconds
- ✅ API requests complete in <1 second
- ✅ WebSocket streaming works
- ✅ Works on Linux, macOS, Windows
- ✅ Comprehensive integration tests

### Nice-to-Have (Future)
- ✅ Browser auto-opens on startup
- ✅ GUI theme persistence
- ✅ Multi-language support
- ✅ Progressive Web App (PWA) support
- ✅ Offline mode

---

## Recommended Next Steps

### Immediate Actions (This Week)

1. **Verify CIRISGUI static export compatibility**
   ```bash
   cd CIRISGUI
   grep -r "getServerSideProps\|pages/api" .
   # Should return no results (or refactor if found)
   ```

2. **Create Python packaging configuration**
   ```bash
   cd CIRISAgent
   touch setup.py MANIFEST.in
   # Implement setup.py from template above
   ```

3. **Test local wheel build (no GUI)**
   ```bash
   python -m build --wheel
   pip install dist/*.whl
   ciris-agent --adapter api  # Should work (API-only mode)
   ```

### Short-Term (Next 2 Weeks)

4. **Implement CI GUI build job**
   - Add `build-gui` job to `.github/workflows/build.yml`
   - Test artifact upload/download

5. **Implement FastAPI static mounting**
   - Modify `ciris_engine/logic/adapters/api/app.py`
   - Add detection for `gui_static/` directory

6. **End-to-end testing**
   - Install wheel with GUI
   - Verify all features work
   - Run QA suite: `python -m tools.qa_runner`

### Medium-Term (Next Month)

7. **Publish to PyPI** (if wheel <100MB)
   ```bash
   python -m build
   twine upload dist/*
   ```

8. **Update documentation**
   - Installation guide
   - GUI user guide
   - Developer guide for packaging

9. **Production deployment**
   - Test on agents.ciris.ai
   - Monitor performance
   - Gather user feedback

---

## Conclusion

**The CI artifact injection approach is technically sound and aligns with user requirements.**

### Key Advantages
1. ✅ **Python-native experience** - `pip install ciris-agent` just works
2. ✅ **No Docker dependency** - Default mode runs in Python process
3. ✅ **Single package** - GUI and API bundled together
4. ✅ **CI automation** - No manual GUI download steps
5. ✅ **FastAPI ready** - Existing infrastructure supports static mounting

### Prerequisites
1. ⚠️ **CIRISGUI must support static export** - No SSR, no API routes
2. ⚠️ **Wheel size must be reasonable** - Target <100MB for PyPI
3. ⚠️ **CI must have Node.js** - Build GUI during CI

### Recommendation
**✅ PROCEED with CI artifact injection approach.**

This matches Python ecosystem conventions (see: Jupyter, Streamlit, Gradio) and provides the best developer experience. The user has explicitly confirmed acceptance of this approach.

---

**Next Step:** Verify CIRISGUI static export compatibility, then implement Phase 1 (Python packaging).
