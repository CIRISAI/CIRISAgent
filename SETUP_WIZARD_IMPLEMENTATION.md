# First-Start Web Setup Wizard - Implementation Summary

## Overview

Moved the CIRIS setup wizard from CLI to a web-based interface that appears before the login screen on first run.

## Changes Made

### 1. New Files Created

#### API Routes (`ciris_engine/logic/adapters/api/routes/setup_wizard.py`)
- **GET /v1/system/setup-status** - Check if setup is required
- **POST /v1/system/setup/llm** - Configure LLM settings (Step 1)
- **POST /v1/system/setup/admin** - Create admin user (Step 2)
- **GET /v1/system/setup/skip** - Skip setup with defaults (dev only)

All endpoints require NO authentication and are only accessible when `is_first_run()` returns `True`.

#### Setup Redirect Middleware (`ciris_engine/logic/adapters/api/middleware/setup_redirect.py`)
- Automatically redirects unauthenticated requests to `/setup-wizard.html` on first run
- Excludes setup wizard endpoints and static assets from redirect
- Returns 503 for API requests when setup is incomplete

#### Web Wizard UI (`ciris_engine/gui_static/setup-wizard.html`)
A beautiful, self-contained HTML page with embedded JavaScript that guides users through:

**Step 1: Welcome**
- Introduction to CIRIS
- Feature highlights
- Overview of setup process

**Step 2: LLM Configuration**
- Provider selection (OpenAI, Local LLM, Other)
- Dynamic form based on provider choice
- API key and endpoint configuration

**Step 3: Admin Account**
- Admin password setup (min 8 characters)
- Password confirmation validation
- Optional email field

**Step 4: Completion**
- Success message
- Educational content about CIRIS features
- Redirect to dashboard/login

### 2. Modified Files

#### `ciris_engine/logic/adapters/api/app.py`
- Added `setup_wizard` to route imports
- Added `SetupRedirectMiddleware` import
- Included setup wizard router in v1 routes (first in list)
- Registered setup redirect middleware after CORS

#### `main.py`
- Updated first-run detection to start API adapter by default
- Removed CLI wizard invocation for interactive environments
- Added welcome message directing users to web interface
- Modified API key check to skip on first run (uses mock LLM for setup)
- Auto-enables mock LLM on first run until user configures real LLM

## User Experience Flow

### Before (CLI Wizard)
1. User runs `python main.py`
2. CLI wizard prompts appear in terminal
3. User enters LLM config via text prompts
4. System creates .env file
5. User manually restarts CIRIS
6. User logs in via web

### After (Web Wizard)
1. User runs `python main.py`
2. CIRIS starts API adapter automatically
3. Welcome message shows: "Setup wizard at http://localhost:8080"
4. User opens browser
5. Middleware redirects to `/setup-wizard.html`
6. Beautiful visual wizard guides setup
7. User completes LLM + admin config
8. System configured automatically
9. User prompted to restart (or auto-login if supported)
10. On restart, redirected to login/dashboard

## Technical Details

### First-Run Detection
Uses existing `is_first_run()` from `ciris_engine/logic/setup/first_run.py`:
- Checks if .env exists in standard locations
- Checks if `CIRIS_CONFIGURED` environment variable is set
- Returns `True` if neither exists

### LLM Configuration
Reuses existing `create_env_file()` from `ciris_engine/logic/setup/wizard.py`:
- Generates encryption keys automatically
- Creates .env with proper formatting
- Supports all provider types (openai, local, other)

### Security
- Setup endpoints only accessible on first run
- Admin password validated (min 8 characters)
- API key not stored in localStorage (secure token handling)
- Middleware blocks all routes except setup when unconfigured

### Compatibility
- CLI wizard still available via `python -m ciris_engine.logic.setup.wizard`
- Environment variable configuration still works
- Docker/non-interactive environments use existing env var setup
- No breaking changes to existing deployments

## Testing

### Manual Testing Steps

1. **First Run - Clean State:**
   ```bash
   # Remove existing config
   rm -f .env ~/.ciris/.env

   # Start CIRIS
   python main.py --adapter api

   # Expected: Welcome message + http://localhost:8080
   ```

2. **Access Wizard:**
   ```bash
   # Open browser to http://localhost:8080
   # Expected: Redirect to /setup-wizard.html
   ```

3. **Complete Setup:**
   - Select LLM provider
   - Enter credentials
   - Set admin password
   - Click "Start CIRIS"
   - Expected: Redirect to login or dashboard

4. **Verify Configuration:**
   ```bash
   # Check .env was created
   ls -la ~/.ciris/.env

   # Verify CIRIS_CONFIGURED=true
   grep CIRIS_CONFIGURED ~/.ciris/.env
   ```

5. **Second Run - Configured State:**
   ```bash
   # Restart CIRIS
   python main.py --adapter api

   # Open browser
   # Expected: Login screen (no wizard redirect)
   ```

### API Testing

```bash
# Check setup status
curl http://localhost:8080/v1/system/setup-status

# Configure LLM
curl -X POST http://localhost:8080/v1/system/setup/llm \
  -H "Content-Type: application/json" \
  -d '{"provider":"openai","api_key":"sk-...","base_url":"","model":""}'

# Create admin
curl -X POST http://localhost:8080/v1/system/setup/admin \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"MySecurePass123","email":"admin@example.com"}'
```

## Future Enhancements

1. **Auto-Restart** - Automatically restart CIRIS after setup completion
2. **Auto-Login** - Use generated token to auto-login after setup
3. **Progress Persistence** - Save progress if user exits mid-setup
4. **Validation** - Test LLM connection before saving
5. **Advanced Options** - Database backend, memory provider, etc.
6. **Multi-Language** - i18n support for wizard UI
7. **Theme Support** - Dark mode for wizard
8. **Accessibility** - ARIA labels, keyboard navigation

## Benefits

✅ **Better UX** - Visual, intuitive setup process
✅ **Educational** - Teaches users about CIRIS features
✅ **Consistent** - Web-based setup matches web-based usage
✅ **Accessible** - Works on any device with a browser
✅ **Beautiful** - Modern, polished UI with animations
✅ **Safe** - Auto-redirects ensure setup can't be skipped
✅ **Flexible** - CLI option still available for advanced users

## Migration Notes

Existing CIRIS installations are unaffected:
- If `.env` exists, wizard is skipped
- Environment variables still work
- CLI wizard still accessible
- No configuration changes required

New installations benefit from the improved wizard automatically.
