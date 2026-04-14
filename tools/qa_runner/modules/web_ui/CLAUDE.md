# Web UI Module - CLAUDE.md

Desktop app and browser-based end-to-end UI testing for CIRIS.

## Two Test Modes

### 1. Desktop App Testing (native Compose, preferred)

Uses the **TestAutomationServer** embedded in the CIRIS Desktop app (Ktor HTTP on port 8091). No browser needed — interacts directly with Compose UI elements via `testTag` identifiers.

#### Building the Desktop App

The desktop app can be built/run in several ways:

```bash
# Quick run (development) - JIT compilation, fastest iteration
cd mobile && CIRIS_TEST_MODE=true ./gradlew :desktopApp:run

# Build runnable JAR (production-like)
cd mobile && ./gradlew :desktopApp:createDistributable
# Output: mobile/desktopApp/build/compose/binaries/main/app/

# Build native installer package (DMG/MSI/DEB)
cd mobile && ./gradlew :desktopApp:packageDistributionForCurrentOS
# Output: mobile/desktopApp/build/compose/binaries/main/
```

**Prerequisite**: Desktop app running with `CIRIS_TEST_MODE=true`

```bash
# Start desktop app with test mode
cd mobile && CIRIS_TEST_MODE=true ./gradlew :desktopApp:run

# Quick CLI
python3 -m tools.qa_runner.modules.web_ui.desktop_test status
python3 -m tools.qa_runner.modules.web_ui.desktop_test login
python3 -m tools.qa_runner.modules.web_ui.desktop_test navigate Adapters
python3 -m tools.qa_runner.modules.web_ui.desktop_test click btn_send
python3 -m tools.qa_runner.modules.web_ui.desktop_test input input_message "hello"

# Full test suite
python3 -m tools.qa_runner.modules.web_ui desktop
python3 -m tools.qa_runner.modules.web_ui desktop-login
python3 -m tools.qa_runner.modules.web_ui desktop-chat
```

### 2. Browser Testing (Playwright + Firefox)

For web UI testing when the desktop app isn't available. Uses Playwright with Firefox.

```bash
python3 -m tools.qa_runner.modules.web_ui setup      # Setup wizard flow
python3 -m tools.qa_runner.modules.web_ui interact    # Agent interaction
python3 -m tools.qa_runner.modules.web_ui licensed    # Licensed agent first-start
```

## Files

| File | Purpose |
|------|---------|
| `__main__.py` | CLI entry point — dispatches to desktop or browser test runners |
| `desktop_app_helper.py` | `DesktopAppHelper` class — async HTTP client for TestAutomationServer |
| `desktop_test.py` | Standalone CLI for quick desktop app interaction |
| `browser_helper.py` | `BrowserHelper` class — Playwright browser lifecycle and utilities |
| `server_manager.py` | `ServerManager` — API server lifecycle (start, stop, health, data wipe) |
| `test_cases.py` | Modular test functions for setup wizard flow (8 steps) |
| `test_runner.py` | `WebUITestRunner` — orchestrates server + browser + test execution |
| `licensed_agent_flow.py` | End-to-end licensed agent first-start flow via browser |

## Desktop App Test Automation Architecture

Three-layer stack:

```
TestAutomationServer.kt    (Ktor HTTP server, port 8091)
    ↓ delegates to
TestAutomation.kt          (expect/actual, commonMain)
    ↓ uses
TestableModifier.kt        (Compose Modifier extensions)
```

### HTTP Endpoints (port 8091)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Server status + test mode check |
| `/tree` | GET | All visible elements with position, size, text |
| `/screen` | GET | Current screen name |
| `/element/{tag}` | GET | Single element info by testTag |
| `/act` | POST | **Combined action + view** (preferred for automation) |
| `/click` | POST | Click element: `{"testTag": "btn_send"}` |
| `/input` | POST | Input text: `{"testTag": "input_message", "text": "hello", "clearFirst": true}` |
| `/wait` | POST | Wait for element: `{"testTag": "btn_login", "timeoutMs": 5000}` |
| `/navigate` | POST | Navigate to screen: `{"screen": "Settings"}` |

### The `/act` Endpoint (Preferred for Automation)

Combines action + wait + tree into one call. Reduces 3 HTTP requests to 1:

```bash
# Click and get resulting UI state with filtered elements
curl -X POST http://localhost:8091/act \
  -H "Content-Type: application/json" \
  -d '{
    "testTag": "btn_skill_workshop",
    "action": "click",
    "waitMs": 500,
    "filterTags": ["skill", "import"]
  }'
```

**Request:** `{"action": "click|input|wait", "testTag": "...", "text": "...", "clearFirst": true, "waitMs": 500, "filterTags": ["..."]}`

**Response:** `{"actionResult": {...}, "screen": "SkillImport", "elements": [...], "elementCount": 5}`

### testable() vs testableClickable()

- **`testable("tag")`** — Registers element position only. Element is visible in `/tree` but cannot be clicked via `/click`.
- **`testableClickable("tag") { action() }`** — Registers position AND click handler. Element responds to `/click` endpoint.

**If a button doesn't respond to automation**, check that it uses `testableClickable()` not `testable()`.

### DesktopAppHelper API

```python
helper = DesktopAppHelper(DesktopAppConfig(server_url="http://localhost:8091"))
await helper.start()

# Queries
status = await helper.status()          # {"screen": "Interact", "elements": [...], "count": 15}
element = await helper.get_element("btn_send")  # ElementInfo or None
visible = await helper.is_element_visible("btn_send")

# Combined action + view (PREFERRED - reduces 3 calls to 1)
result = await helper.act("btn_login_submit", "click", wait_ms=1000)
print(f"Now on: {result['screen']}, elements: {result['elementCount']}")

result = await helper.act(
    "input_skill_md", "input",
    text="---\nname: My Skill\n---",
    filter_tags=["skill", "preview"]
)

# Individual actions (use act() instead when possible)
await helper.click("btn_send")
await helper.input_text("input_message", "hello", clear_first=True)

# Waiting
await helper.wait_for_element("btn_login", timeout=5000)
await helper.wait_for_screen("Interact", timeout=10000)

# High-level
await helper.login(username="admin", password="qa_test_password_12345")
await helper.navigate_to("Adapters")
await helper.click_and_wait_for_screen("btn_login_submit", "Interact")

await helper.stop()
```

### Common testTag Names

**Login screen**: `input_username`, `input_password`, `btn_login_submit`
**Top bar**: `btn_menu`, `btn_settings`, `btn_trust_shield`
**Interact**: `input_message`, `btn_send`
**Navigation menu**: `menu_adapters`, `menu_services`, etc.
**Trust page**: `item_tier_1` through `item_tier_5`, `btn_trust_back`, `btn_trust_refresh`
**Settings**: `btn_back`

## Known Issues (macOS QA, 2.0.11)

1. **BUG (FIXED 2.0.11)**: `btn_send` used `testable()` instead of `testableClickable()` — couldn't click programmatically
2. **BUG (FIXED 2.0.11)**: `btn_settings` used `testable()` instead of `testableClickable()`
3. **Minor**: Login screen OAuth/local toggle buttons use `testable()` — not automatable
4. **Minor**: 29 text input fields don't observe `textInputRequests` flow — can't set text programmatically via `/input` on all fields
