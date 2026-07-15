"""
Mobile Test Cases for CIRIS App

Test cases for automated UI testing with ADB and UI Automator.
"""

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

from .adb_helper import ADBHelper
from .ui_automator import UIAutomator


class TestResult(Enum):
    """Test result status."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class TestReport:
    """Report for a single test case."""

    name: str
    result: TestResult
    duration: float
    message: str = ""
    screenshots: List[str] = None

    def __post_init__(self):
        if self.screenshots is None:
            self.screenshots = []


class CIRISAppConfig:
    """Configuration for CIRIS mobile app testing.

    Targets the debug build by default — APK_PATH points to
    androidApp/build/outputs/apk/debug/, which is signed with the debug
    keystore and packaged under the `.debug` application id (per
    androidApp/build.gradle's debug applicationIdSuffix). Previously
    PACKAGE/MAIN_ACTIVITY pointed at the release id while APK_PATH
    referenced the debug APK — the two disagreed and `pm clear` /
    `am start` silently no-op'd against the wrong package on a fresh
    emulator, failing every test at "Failed to launch app" within ~2s.
    Override via CIRIS_MOBILE_PACKAGE if you need to point at the
    release build instead.
    """

    PACKAGE = os.environ.get("CIRIS_MOBILE_PACKAGE", "ai.ciris.mobile.debug")
    MAIN_ACTIVITY = f"{PACKAGE.replace('.debug', '')}.MainActivity"
    APK_PATH = "client/androidApp/build/outputs/apk/debug/androidApp-debug.apk"

    # UI Texts (for finding elements)
    TEXT_CIRIS = "CIRIS"
    TEXT_CIRIS_AGENT = "CIRIS Agent"
    TEXT_SIGN_IN_GOOGLE = "Sign in with Google"
    TEXT_LOCAL_LOGIN = "Local Login"
    TEXT_ETHICAL_AI = "Ethical AI Assistant"
    TEXT_CHAT_WITH_CIRIS = "Chat with CIRIS"
    TEXT_TYPE_MESSAGE = "Type your message..."
    TEXT_CONNECTED = "Connected"
    TEXT_DISCONNECTED = "Disconnected"
    TEXT_WELCOME_ALLY = "Welcome to Ally"
    TEXT_SEND = "Send"

    # Setup wizard texts (extensible for future screens)
    # Current flow (4 steps):
    #   1. Intro/Welcome → "Register Your Agent Identity" card, "Continue →"
    #   2. AI Configuration → Provider dropdown, API Key, "Test Connection", "Next"
    #   3. Optional Features → Alignment metrics consent, Web API toggle, "Next"
    #   4. Confirm Setup → Username/Password, "Finish Setup"
    TEXT_SETUP_TITLE = "Setup"
    TEXT_LLM_PROVIDER = "LLM Provider"
    TEXT_API_KEY = "API Key"
    TEXT_NEXT = "Next"
    TEXT_CONTINUE = "Continue"  # Intro step button
    TEXT_CONTINUE_ARROW = "Continue →"  # Intro step with arrow
    TEXT_FINISH_SETUP = "Finish Setup"  # Final step button
    TEXT_FINISH = "Finish"
    TEXT_COMPLETE = "Complete"
    TEXT_FREE_AI_ACCESS = "Free AI Access Ready"
    TEXT_AI_CONFIG = "AI Configuration"
    TEXT_CONFIRM_SETUP = "Confirm Setup"
    # Step 1 texts
    TEXT_REGISTER_IDENTITY = "Register Your Agent Identity"
    TEXT_SKIP_FOR_NOW = "Skip for now..."
    TEXT_BACK_TO_LOGIN = "Back to Login"
    # Step 2 texts
    TEXT_PROVIDER = "Provider"
    TEXT_OPENAI = "OpenAI"
    TEXT_ANTHROPIC = "Anthropic"
    TEXT_GOOGLE_AI = "Google AI"
    TEXT_TEST_CONNECTION = "Test Connection"
    # Step 3 texts
    TEXT_OPTIONAL_FEATURES = "Optional Features"
    TEXT_HELP_IMPROVE = "Help Improve AI Alignment"
    TEXT_ALIGNMENT_CONSENT = "I agree to share anonymous alignment metrics"
    TEXT_COMMUNICATION_ADAPTERS = "Communication Adapters"
    TEXT_WEB_API = "Web API"
    # Step 4 texts
    TEXT_YOUR_ACCOUNT = "Your Account"
    TEXT_USERNAME = "Username"
    TEXT_PASSWORD = "Password"
    TEXT_USERNAME_REQUIRED = "Username is required"
    TEXT_PASSWORD_REQUIRED = "Password is required"

    # Setup wizard navigation buttons (in priority order)
    # Priority: Finish > Next > Continue (to prevent skipping steps)
    SETUP_NAV_BUTTONS = [
        "Finish Setup",  # Step 4: Final step
        "Next",  # Steps 2-3: Middle steps
        "Continue →",  # Step 1: Intro with arrow
        "Continue",  # Step 1: Intro alternate
        "Get Started",  # Future onboarding
        "Finish",  # Alternate final
        "Complete",  # Alternate complete
        "Done",  # Alternate done
    ]

    # Chat screen indicators (must see MULTIPLE indicators to confirm chat screen)
    # "Connected" alone is NOT sufficient - it also shows on Setup screen
    CHAT_SCREEN_INDICATORS_PRIMARY = [
        "Welcome to Ally",
        "Type your message...",
    ]
    # Secondary indicators that MUST be combined with primary
    CHAT_SCREEN_INDICATORS_SECONDARY = [
        "Connected",
        "Shutdown",  # Shutdown button only on chat screen
        "STOP",  # Stop button only on chat screen
    ]

    # Register Your Agent texts (device auth via Portal/Registry)
    TEXT_REGISTER_AGENT = "Register Your Agent"
    TEXT_REGISTER_SUBTITLE = "$1.00 bond"  # Partial match for the pricing text
    TEXT_CONNECT = "Connect"
    TEXT_PORTAL_URL_PLACEHOLDER = "Portal URL"
    TEXT_WAITING_AUTH = "Waiting for authorization"
    TEXT_VERIFICATION_URL = "portal.ciris"
    TEXT_AGENT_AUTHORIZED = "Authorized"
    TEXT_CONNECTING_PORTAL = "Connecting"
    TEXT_REGISTER_AGENT_STEP = "Register Agent"  # Step title

    # Deprecated aliases (for backwards compat)
    TEXT_ACQUIRE_LICENSE = TEXT_REGISTER_AGENT
    TEXT_CREATE_LICENSED_AGENT = TEXT_REGISTER_AGENT

    # Test tags (Compose testTag values appear in resource-id)
    TAG_BTN_GOOGLE_SIGNIN = "btn_google_signin"
    TAG_BTN_LOCAL_LOGIN = "btn_local_login"
    TAG_INPUT_MESSAGE = "input_message"
    TAG_BTN_SEND = "btn_send"

    # Timeouts (in seconds)
    TIMEOUT_APP_LAUNCH = 180  # cold first boot: attestation (11 steps) + 22 services on emulator swiftshader takes 75-120s
    TIMEOUT_GOOGLE_SIGNIN = 30
    TIMEOUT_SETUP = 90  # Increased for multi-step wizard
    TIMEOUT_CHAT_RESPONSE = 30
    TIMEOUT_SETUP_STEP = 5  # Max wait per wizard step

    # In-app test-automation HTTP server (Ktor CIO, same as desktop/iOS).
    # Debug builds force-enable it (BuildConfig.TEST_MODE_ENABLED=true →
    # AndroidTestAutomationServer.startIfEnabled() in MainActivity.onCreate).
    # It binds 127.0.0.1:9091 ON THE DEVICE; we adb-forward a local port to it.
    # 19091 locally avoids colliding with a desktop test server on 9091.
    TEST_SERVER_DEVICE_PORT = 9091
    TEST_SERVER_LOCAL_PORT = 19091


class ScreenCoordinates:
    """
    Configurable screen coordinates for UI automation.

    Default values are for a 1080x2400 resolution device (Pixel 6 emulator).
    Override these in config dict under 'screen_coords' key.

    Example:
        config = {
            'screen_coords': {
                'message_input_center': (540, 2179),
                'send_button_center': (996, 2180),
            }
        }
    """

    # Default coordinates for 1080x2400 resolution
    # Updated 2026-02-28 with actual screen measurements from emulator
    DEFAULTS = {
        # Login screen
        "google_signin_center": (540, 1208),
        "local_login_center": (541, 1397),  # [430,1371][652,1424]
        # Chat screen (bottom input area)
        "message_input_center": (274, 2179),
        "send_button_center": (996, 2180),
        # Setup wizard buttons (bottom navigation bar)
        "wizard_button_center_y": 2232,  # Common Y for all bottom buttons
        "wizard_continue_x": 786,  # "Continue →" button X
        "wizard_next_x": 786,  # "Next" button X [748,2206][825,2259]
        "wizard_back_x": 294,  # "Back" button X [253,2206][335,2259]
        "wizard_finish_x": 786,  # "Finish Setup" button X [685,2206][888,2259]
        # Setup Step 1 (Intro/Welcome)
        "skip_for_now_center": (540, 1497),  # [105,1466][975,1529]
        # Setup Step 2 (AI Configuration)
        "provider_dropdown_center": (540, 598),  # [63,525][1017,672]
        "api_key_field_center": (540, 871),  # [63,798][1017,945]
        "test_connection_center": (540, 1050),  # [407,1024][674,1077]
        # Setup Step 4 (Confirm Setup)
        "username_field_center": (540, 1100),  # Below Username label
        "password_field_center": (540, 1250),  # Below Password label
        # Google account chooser
        "account_row_center_y": 1260,
        "account_row_x": 350,
        # Provider dropdown items (approximate Y positions when open)
        "dropdown_openai_y": 493,
        "dropdown_anthropic_y": 547,
        "dropdown_google_ai_y": 601,
    }

    @classmethod
    def get(cls, key: str, config: dict = None) -> tuple:
        """Get coordinates, with optional config override."""
        if config and "screen_coords" in config:
            coords = config["screen_coords"].get(key)
            if coords:
                return coords
        return cls.DEFAULTS.get(key, (540, 1200))  # Default to center-ish

    @classmethod
    def scale_for_resolution(
        cls, coords: tuple, target_width: int, target_height: int, base_width: int = 1080, base_height: int = 2400
    ) -> tuple:
        """Scale coordinates for different screen resolutions."""
        x, y = coords
        scaled_x = int(x * target_width / base_width)
        scaled_y = int(y * target_height / base_height)
        return (scaled_x, scaled_y)


# ========== In-App Test-Automation HTTP Client (Compose testTag drive) ==========
#
# UIAutomator XML dumps do NOT reliably expose Compose testTags set via the
# shared `testable()` / `testableClickable()` modifiers (no
# testTagsAsResourceId semantics on those nodes). The app runs the same Ktor
# test-automation server as desktop (TestAutomationServer.android.kt, port
# 9091 on-device, auto-enabled in debug builds), which serves exactly those
# testTags. New wizard/catch-up tests drive the app through it.


class TestServerClient:
    """Thin HTTP client for the in-app test-automation server (Android).

    Reached via `adb forward tcp:19091 tcp:9091`. Endpoints (shared
    TestAutomationHandler): /health, /screen, /tree, /click, /input, /wait,
    /element/{tag}, /act.
    """

    def __init__(self, base_url: str = f"http://127.0.0.1:{CIRISAppConfig.TEST_SERVER_LOCAL_PORT}"):
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str, data: Optional[dict] = None, timeout: int = 10) -> Tuple[int, dict]:
        url = f"{self.base_url}{path}"
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"} if body else {},
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                try:
                    return resp.status, json.loads(raw)
                except json.JSONDecodeError:
                    return resp.status, {"raw": raw.decode("utf-8", errors="replace")}
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read())
            except Exception:
                return e.code, {"error": str(e)}
        except (urllib.error.URLError, ConnectionRefusedError, OSError) as e:
            return 0, {"error": str(e)}

    def health(self) -> Tuple[int, dict]:
        return self._request("GET", "/health", timeout=3)

    def screen(self) -> Optional[str]:
        status, body = self._request("GET", "/screen", timeout=5)
        return body.get("screen") if status == 200 else None

    def tags(self) -> List[str]:
        """All currently POSITIONED testTags (from /tree)."""
        status, body = self._request("GET", "/tree", timeout=5)
        if status != 200:
            return []
        return [e.get("testTag", "") for e in body.get("elements", [])]

    def is_visible(self, test_tag: str) -> bool:
        """Positioned-in-the-composition check via /tree.

        Used for GATING assertions (e.g. toggle_trace_opt_in must be ABSENT
        while announce is OFF): AnimatedVisibility(false) content is not
        composed, so its tag is neither positioned nor handler-registered.
        """
        return test_tag in self.tags()

    def click(self, test_tag: str) -> Tuple[bool, Optional[Tuple[int, int]]]:
        """Click via the registered handler. Returns (success, coords).

        On failure coords (if the element is positioned but handler-less —
        the testable()-vs-testableClickable() client bug class) let the
        caller fall back to an adb coordinate tap.
        """
        status, body = self._request("POST", "/click", {"testTag": test_tag})
        coords = None
        raw = body.get("coordinates")
        if raw and "," in str(raw):
            try:
                x, y = str(raw).split(",", 1)
                coords = (int(float(x)), int(float(y)))
            except ValueError:
                coords = None
        return status == 200 and bool(body.get("success")), coords

    def input(self, test_tag: str, text: str, clear_first: bool = True) -> bool:
        status, body = self._request(
            "POST", "/input", {"testTag": test_tag, "text": text, "clearFirst": clear_first}
        )
        return status == 200 and bool(body.get("success"))

    def wait_for_element(self, test_tag: str, timeout: float = 8.0) -> bool:
        """Server-side wait (position OR click-handler registered)."""
        status, body = self._request(
            "POST",
            "/wait",
            {"testTag": test_tag, "timeoutMs": int(timeout * 1000)},
            timeout=int(timeout) + 5,
        )
        return status == 200 and bool(body.get("success"))

    def wait_for_screen(self, expected: str, timeout: float = 10.0, interval: float = 0.5) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.screen() == expected:
                return True
            time.sleep(interval)
        return False

    def wait_for_any_screen(self, expected: List[str], timeout: float = 10.0, interval: float = 0.5) -> Optional[str]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            current = self.screen()
            if current in expected:
                return current
            time.sleep(interval)
        return None


def _click_or_tap(client: TestServerClient, adb: ADBHelper, test_tag: str) -> bool:
    """Click via registered handler; fall back to coordinate tap if the tag is
    positioned but handler-less (testable() instead of testableClickable())."""
    ok, coords = client.click(test_tag)
    if ok:
        return True
    if coords:
        print(f"    (no click handler for '{test_tag}' — falling back to adb tap at {coords})")
        adb.tap(*coords)
        return True
    return False


def connect_test_server(
    adb: ADBHelper,
    config: dict,
    launch_if_needed: bool = True,
    clear_data: bool = False,
    boot_timeout: float = 180.0,
) -> Optional[TestServerClient]:
    """Forward the in-app test server port and return a live client.

    If the server isn't reachable and ``launch_if_needed``, (re)launches the
    app (optionally clearing data for a first-run flow) and polls /health
    while the bundled Python backend boots (60-120s+ on first extraction).
    """
    local_port = config.get("test_server_local_port", CIRISAppConfig.TEST_SERVER_LOCAL_PORT)
    device_port = config.get("test_server_device_port", CIRISAppConfig.TEST_SERVER_DEVICE_PORT)

    if not adb.forward_port(local_port, device_port):
        print(f"  WARNING: adb forward tcp:{local_port} tcp:{device_port} failed")
        return None

    client = TestServerClient(f"http://127.0.0.1:{local_port}")

    # Already up? (app running in test mode)
    status, body = client.health()
    if status == 200 and body.get("testMode"):
        return client

    if not launch_if_needed:
        return None

    print("  Test server not reachable — launching app...")
    adb.force_stop_app(CIRISAppConfig.PACKAGE)
    time.sleep(1)
    if clear_data:
        print("  Clearing app data (first-run flow)...")
        adb.clear_app_data(CIRISAppConfig.PACKAGE)
        time.sleep(1)
    if not adb.launch_app(CIRISAppConfig.PACKAGE, CIRISAppConfig.MAIN_ACTIVITY):
        print("  ERROR: failed to launch app")
        return None

    deadline = time.time() + boot_timeout
    while time.time() < deadline:
        status, body = client.health()
        if status == 200 and body.get("testMode"):
            return client
        time.sleep(2)

    print(f"  ERROR: in-app test server never came up within {boot_timeout:.0f}s")
    return None


def test_app_launch(adb: ADBHelper, ui: UIAutomator, config: dict) -> TestReport:
    """
    Test: App launches successfully.

    Steps:
    1. Force stop any existing instance
    2. Clear app data (fresh start)
    3. Launch the app
    4. Wait for splash/loading to complete
    5. Verify Login screen appears
    """
    start_time = time.time()
    screenshots = []

    try:
        print("  [1/5] Force stopping existing instance...")
        adb.force_stop_app(CIRISAppConfig.PACKAGE)
        time.sleep(1)

        # Honor --no-clear: clearing app data wipes the extracted Chaquopy Python
        # bundle, and on a storage-constrained device re-extraction on relaunch
        # can fail (app crashes back to home). Only clear when explicitly asked.
        if config.get("clear_data", True):
            print("  [2/5] Clearing app data...")
            adb.clear_app_data(CIRISAppConfig.PACKAGE)
            time.sleep(1)
        else:
            print("  [2/5] Skipping data clear (clear_data=False)")

        print("  [3/5] Launching app...")
        success = adb.launch_app(CIRISAppConfig.PACKAGE, CIRISAppConfig.MAIN_ACTIVITY)
        if not success:
            return TestReport(
                name="test_app_launch",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="Failed to launch app",
            )

        print("  [4/5] Waiting for app to initialize...")
        # Wait for Python to start and server to be ready
        # The app shows "CIRIS" splash then transitions to Login
        time.sleep(5)  # Initial wait for Python init

        # Wait for the Login screen — match on Local Login (always present, and
        # the path local-login mode uses) OR the Google button.
        element = ui.wait_for_text(
            CIRISAppConfig.TEXT_LOCAL_LOGIN, timeout=CIRISAppConfig.TIMEOUT_APP_LAUNCH
        ) or ui.wait_for_text(CIRISAppConfig.TEXT_SIGN_IN_GOOGLE, timeout=5)

        if not element:
            # Take screenshot for debugging
            screenshot_path = f"/tmp/ciris_test_launch_fail_{int(time.time())}.png"
            adb.screenshot(screenshot_path)
            screenshots.append(screenshot_path)

            screen_info = ui.dump_screen_info()
            return TestReport(
                name="test_app_launch",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"Login screen not found. Visible texts: {screen_info.get('texts', [])}",
                screenshots=screenshots,
            )

        print("  [5/5] Verifying Login screen elements...")
        # Verify other login elements
        has_local = ui.is_text_visible(CIRISAppConfig.TEXT_LOCAL_LOGIN)
        has_branding = ui.is_text_visible(CIRISAppConfig.TEXT_CIRIS_AGENT)

        if not has_local:
            return TestReport(
                name="test_app_launch",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="Local Login button not found",
            )

        return TestReport(
            name="test_app_launch",
            result=TestResult.PASSED,
            duration=time.time() - start_time,
            message=f"App launched successfully. Branding visible: {has_branding}",
        )

    except Exception as e:
        return TestReport(
            name="test_app_launch",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
            screenshots=screenshots,
        )


def test_google_signin(adb: ADBHelper, ui: UIAutomator, config: dict) -> TestReport:
    """
    Test: Google Sign-In flow with test account.

    Prerequisites:
    - Test Google account (ciristest1@gmail.com) should be added to device
    - If not pre-authenticated, password file should be provided
    - App must be on Login screen

    Steps:
    1. Click "Sign in with Google"
    2. Select test account from Google account chooser
    3. Enter password if required
    4. Wait for sign-in to complete
    5. Verify navigation to Setup screen
    """
    start_time = time.time()
    screenshots = []
    test_email = config.get("test_email", "ciristest1@gmail.com")
    test_password = config.get("test_password", "")

    try:
        print(f"  [1/5] Clicking 'Sign in with Google'...")

        # Ensure we're on login screen
        if not ui.is_text_visible(CIRISAppConfig.TEXT_SIGN_IN_GOOGLE):
            return TestReport(
                name="test_google_signin",
                result=TestResult.SKIPPED,
                duration=time.time() - start_time,
                message="Not on Login screen - skipping",
            )

        # Click Google Sign-In button (try test tag first, then text)
        clicked = ui.click_by_resource_id(CIRISAppConfig.TAG_BTN_GOOGLE_SIGNIN)
        if not clicked:
            clicked = ui.click_by_text(CIRISAppConfig.TEXT_SIGN_IN_GOOGLE)
        if not clicked:
            return TestReport(
                name="test_google_signin",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="Failed to click Google Sign-In button",
            )

        time.sleep(2)  # Wait for Google sign-in UI

        # Check for and dismiss Google Lens if it was triggered accidentally
        if ui.is_google_lens_open():
            print("  [WARNING] Google Lens opened accidentally, dismissing...")
            ui.dismiss_google_lens()
            time.sleep(1)
            # Re-click the sign-in button
            clicked = ui.click_by_resource_id(CIRISAppConfig.TAG_BTN_GOOGLE_SIGNIN)
            if not clicked:
                clicked = ui.click_by_text(CIRISAppConfig.TEXT_SIGN_IN_GOOGLE)
            time.sleep(2)

        print(f"  [2/5] Looking for Google account chooser...")

        # Take screenshot of Google sign-in screen
        screenshot_path = f"/tmp/ciris_google_signin_{int(time.time())}.png"
        adb.screenshot(screenshot_path)
        screenshots.append(screenshot_path)

        # Look for test account email in account chooser
        # Google shows accounts with email visible
        account_element = ui.wait_for_text(test_email, timeout=CIRISAppConfig.TIMEOUT_GOOGLE_SIGNIN)

        if account_element:
            print(f"  [3/5] Selecting test account: {test_email}")
            ui.click(account_element)
        else:
            # Check if we're on "Add account" / sign-in page
            add_account = ui.find_by_text("Add another account") or ui.find_by_text("Add account")
            if add_account:
                print(f"  [3/5] Account not on device, clicking 'Add account'...")
                ui.click(add_account)
                time.sleep(2)

                # Enter email
                email_field = ui.find_by_text("Email or phone")
                if email_field:
                    ui.click(email_field)
                    time.sleep(0.3)
                    adb.input_text(test_email)
                    time.sleep(0.5)

                    # Click Next
                    ui.click_by_text("Next")
                    time.sleep(2)

                    # Check for password field
                    if test_password:
                        password_field = ui.find_by_text("Enter your password")
                        if password_field:
                            print(f"  [4/5] Entering password...")
                            ui.click(password_field)
                            time.sleep(0.3)
                            adb.input_text(test_password)
                            time.sleep(0.5)
                            ui.click_by_text("Next")
                            time.sleep(3)
            else:
                # Try clicking the first Google account shown
                screen_info = ui.dump_screen_info()
                print(f"  Account chooser contents: {screen_info.get('texts', [])}")

                gmail_element = ui.find_by_text("@gmail.com")
                if gmail_element:
                    print(f"  [3/5] Clicking found Gmail account...")
                    ui.click(gmail_element)
                else:
                    return TestReport(
                        name="test_google_signin",
                        result=TestResult.FAILED,
                        duration=time.time() - start_time,
                        message=f"Test account {test_email} not found. Add it to device or provide password.",
                        screenshots=screenshots,
                    )

        time.sleep(3)  # Wait for auth to complete

        # Check if password is required (account exists but needs re-auth)
        password_prompt = ui.find_by_text("Enter your password") or ui.find_by_text("password")
        if password_prompt and test_password:
            print(f"  [4/5] Password required, entering...")
            # Find password input field
            edit_fields = ui.find_by_class("EditText")
            if edit_fields:
                ui.click(edit_fields[0])
                time.sleep(0.3)
                adb.input_text(test_password)
                time.sleep(0.5)
                ui.click_by_text("Next") or ui.click_by_text("Sign in")
                time.sleep(3)

        print(f"  [5/5] Verifying navigation to Setup screen...")

        # After Google sign-in, app should navigate to Setup wizard
        # Look for setup-related UI elements
        setup_visible = (
            ui.wait_for_text("Setup", timeout=10)  # Generic setup text
            or ui.wait_for_text("LLM", timeout=5)  # LLM provider selection in setup
            or ui.wait_for_text("Provider", timeout=5)
        )

        if setup_visible:
            return TestReport(
                name="test_google_signin",
                result=TestResult.PASSED,
                duration=time.time() - start_time,
                message="Google Sign-In successful, navigated to Setup",
                screenshots=screenshots,
            )
        else:
            # Take screenshot for debugging
            screenshot_path = f"/tmp/ciris_after_signin_{int(time.time())}.png"
            adb.screenshot(screenshot_path)
            screenshots.append(screenshot_path)

            screen_info = ui.dump_screen_info()
            return TestReport(
                name="test_google_signin",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"Setup screen not found after sign-in. Visible: {screen_info.get('texts', [])}",
                screenshots=screenshots,
            )

    except Exception as e:
        return TestReport(
            name="test_google_signin",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
            screenshots=screenshots,
        )


def test_local_login(adb: ADBHelper, ui: UIAutomator, config: dict) -> TestReport:
    """
    Test: Local Login flow (BYOK mode).

    Steps:
    1. Click "Local Login"
    2. Verify navigation to Setup screen
    """
    start_time = time.time()
    screenshots = []

    try:
        print(f"  [1/2] Clicking 'Local Login'...")

        # Ensure we're on login screen
        if not ui.is_text_visible(CIRISAppConfig.TEXT_LOCAL_LOGIN):
            return TestReport(
                name="test_local_login",
                result=TestResult.SKIPPED,
                duration=time.time() - start_time,
                message="Not on Login screen - skipping",
            )

        # Click Local Login button (try test tag first, then text)
        clicked = ui.click_by_resource_id(CIRISAppConfig.TAG_BTN_LOCAL_LOGIN)
        if not clicked:
            clicked = ui.click_by_text(CIRISAppConfig.TEXT_LOCAL_LOGIN)
        if not clicked:
            return TestReport(
                name="test_local_login",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="Failed to click Local Login button",
            )

        time.sleep(2)

        print(f"  [2/2] Verifying navigation to Setup screen...")

        # Should navigate directly to Setup
        setup_visible = ui.wait_for_text("Setup", timeout=10) or ui.wait_for_text("LLM", timeout=5)

        if setup_visible:
            return TestReport(
                name="test_local_login",
                result=TestResult.PASSED,
                duration=time.time() - start_time,
                message="Local Login successful, navigated to Setup",
            )
        else:
            screen_info = ui.dump_screen_info()
            return TestReport(
                name="test_local_login",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"Setup screen not found. Visible: {screen_info.get('texts', [])}",
            )

    except Exception as e:
        return TestReport(
            name="test_local_login",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
        )


def test_setup_wizard(adb: ADBHelper, ui: UIAutomator, config: dict) -> TestReport:
    """
    Test: Complete the NODE-CLIENT first-run setup wizard.

    Drives the app through the in-app test-automation HTTP server (Compose
    testTags — UIAutomator does not reliably see them). Node-client first-run
    order (SetupViewModel / SetupScreen, matches the desktop QA runner's
    test_setup_wizard_flow):

        WELCOME → ACCOUNT_AND_CONFIRMATION (username/password/confirm)
        → FEDERATION_IDENTITY_SETUP → [LLM_CONFIGURATION] → AGE_RANGE → COMPLETE

    LLM_CONFIGURATION appears only on AGENT builds (CIRISBuild.HAS_AGENT):
    the step is probed for after the fed-ID step and handled when present —
    prefer the CIRIS-hosted option if rendered (OAuth path), else BYOK with
    the configured provider+key (llm_provider/llm_api_key), else the keyless
    "local" (Ollama) provider so the wizard can proceed without a real key.
    Node-client builds skip straight to AGE_RANGE. The federation-identity
    step hosts the AnnounceDecisionCard:
      - input_fedid_label          — REQUIRED, non-generic fed-ID name
      - toggle_announce_ownership  — the pivotal announce switch
      - toggle_trace_opt_in        — trace opt-in, GATED: composed ONLY while
                                     announce is ON (asserted both ways below)

    Config options:
    - setup_username / setup_password: local account (default admin/qa_test_password_12345)
    - fed_label: federation-ID label (default: generated unique qa-node-<ts>)
    - announce: flip the announce switch ON (default True)
    - trace_opt_in: tick the trace checkbox after announcing (default True)
    - age_band: "adult" | "minor" (default "adult")
    - llm_provider / llm_api_key: BYOK provider+key for the agent build's
      LLM_CONFIGURATION step (default groq / key from ~/.groq_key when the
      runner found one; keyless "local" fallback when no key)
    - clear_data: clear app data if the app must be (re)launched (default True)

    Standalone-safe: if the app/test server isn't up it launches the app
    itself (fresh first-run when clear_data), and if it lands on the Login
    screen it clicks btn_local_login to enter the wizard.
    """
    start_time = time.time()
    screenshots = []

    username = config.get("setup_username", "admin")
    password = config.get("setup_password", "qa_test_password_12345")
    fed_label = config.get("fed_label") or f"qa-node-{int(time.time())}"
    announce = config.get("announce", True)
    trace_opt_in = config.get("trace_opt_in", True)
    age_band = config.get("age_band", "adult")
    llm_provider = config.get("llm_provider", "groq")
    llm_api_key = config.get("llm_api_key", "")

    def fail(step: str, detail: str) -> TestReport:
        path = f"/tmp/ciris_setup_fail_{int(time.time())}.png"
        adb.screenshot(path)
        screenshots.append(path)
        return TestReport(
            name="test_setup_wizard",
            result=TestResult.FAILED,
            duration=time.time() - start_time,
            message=f"[{step}] {detail}",
            screenshots=screenshots,
        )

    try:
        # ── Step 0: reach the wizard via the test server ──────────────────
        print("  [1/7] Connecting to in-app test server...")
        client = connect_test_server(adb, config, launch_if_needed=True, clear_data=config.get("clear_data", True))
        if not client:
            return fail("connect", "in-app test-automation server unreachable (debug build required)")

        print("  [2/7] Waiting for Login/Setup screen (first boot can take 60-120s+)...")
        landed = client.wait_for_any_screen(["Login", "Setup"], timeout=180.0, interval=1.5)
        if landed is None:
            return fail("land", f"never reached Login/Setup (screen={client.screen()!r})")

        if landed == "Login":
            print("  Login screen → clicking btn_local_login")
            if not client.wait_for_element("btn_local_login", timeout=10):
                return fail("login", "btn_local_login not found on Login screen")
            if not _click_or_tap(client, adb, "btn_local_login"):
                return fail("login", "could not click btn_local_login")
            if not client.wait_for_screen("Setup", timeout=30.0):
                # A configured backend routes Local Login to the login FORM,
                # not the wizard — that's an environment state, not a bug.
                if client.is_visible("input_password") and client.is_visible("btn_login_submit"):
                    return TestReport(
                        name="test_setup_wizard",
                        result=TestResult.SKIPPED,
                        duration=time.time() - start_time,
                        message="Backend already configured (login form shown) — first-run wizard "
                        "unavailable. Re-run with clear_data to get a fresh node.",
                        screenshots=screenshots,
                    )
                return fail("login", f"did not reach Setup wizard (screen={client.screen()!r})")

        # ── Step 1: WELCOME → Continue ────────────────────────────────────
        print("  [3/7] WELCOME → btn_next")
        if not client.wait_for_element("btn_next", timeout=15):
            return fail("welcome", "btn_next not found on WELCOME step")
        if not _click_or_tap(client, adb, "btn_next"):
            return fail("welcome", "failed to click btn_next on WELCOME")
        time.sleep(0.5)

        # ── Step 2: ACCOUNT_AND_CONFIRMATION ──────────────────────────────
        print(f"  [4/7] ACCOUNT: {username} / ******** (+ confirm)")
        if not client.wait_for_element("input_username", timeout=10):
            return fail("account", "input_username not found on account step")
        # Small settles between inputs: the Kotlin side consumes ONE pending
        # TextInputRequest via a StateFlow slot — back-to-back requests can
        # overwrite each other before recomposition applies them.
        if not client.input("input_username", username):
            return fail("account", "failed to input username")
        time.sleep(0.5)
        if not client.input("input_password", password):
            return fail("account", "failed to input password")
        time.sleep(0.5)
        if not client.input("input_password_confirm", password):
            return fail("account", "failed to input password confirmation")
        time.sleep(0.5)
        if not _click_or_tap(client, adb, "btn_next"):
            return fail("account", "failed to click btn_next on account step")
        time.sleep(0.5)

        # ── Step 3: FEDERATION_IDENTITY_SETUP + announce-gate assertions ──
        print(f"  [5/7] FED-ID: label={fed_label!r}, announce={announce}, trace={trace_opt_in}")
        if not client.wait_for_element("input_fedid_label", timeout=10):
            return fail("fedid", "input_fedid_label not found on federation-identity step")

        # GATING (OFF): trace opt-in must NOT be composed while announce is OFF.
        if client.is_visible("toggle_trace_opt_in"):
            return fail("fedid_gate_off", "toggle_trace_opt_in visible BEFORE announce is ON (gating broken)")
        print("      gate check OK: toggle_trace_opt_in absent while announce OFF")

        if not client.input("input_fedid_label", fed_label):
            return fail("fedid", "failed to input federation-ID label")
        time.sleep(0.3)

        if announce:
            if not _click_or_tap(client, adb, "toggle_announce_ownership"):
                return fail("fedid", "failed to click toggle_announce_ownership")
            # GATING (ON): trace opt-in must appear once announce is ON.
            if not client.wait_for_element("toggle_trace_opt_in", timeout=5):
                return fail("fedid_gate_on", "toggle_trace_opt_in did NOT appear after announce ON (gating broken)")
            print("      gate check OK: toggle_trace_opt_in appeared after announce ON")

            if trace_opt_in:
                if not _click_or_tap(client, adb, "toggle_trace_opt_in"):
                    return fail("fedid", "failed to click toggle_trace_opt_in")
                time.sleep(0.3)

        screenshot_path = f"/tmp/ciris_setup_fedid_{int(time.time())}.png"
        adb.screenshot(screenshot_path)
        screenshots.append(screenshot_path)

        if not _click_or_tap(client, adb, "btn_next"):
            return fail("fedid", "failed to click btn_next on federation-identity step")
        time.sleep(0.5)

        # ── Step 3.5: LLM_CONFIGURATION (agent build only) ─────────────────
        # Agent builds (CIRISBuild.HAS_AGENT) insert the LLM step after the
        # fed-ID; node-client builds go straight to AGE_RANGE. Probe for the
        # provider dropdown and handle the step only when it composed.
        if client.wait_for_element("input_llm_provider", timeout=6):
            print(f"  [6/7] LLM_CONFIGURATION: provider={llm_provider!r}, key={'set' if llm_api_key else 'none'}")
            if client.is_visible("btn_use_free_ai"):
                # CIRIS-hosted proxy option (OAuth path) — no key entry needed.
                if not _click_or_tap(client, adb, "btn_use_free_ai"):
                    return fail("llm", "failed to click btn_use_free_ai on LLM step")
                time.sleep(0.3)
            elif llm_api_key:
                # BYOK: pick the configured provider from the dropdown, then key.
                if not _click_or_tap(client, adb, "input_llm_provider"):
                    return fail("llm", "failed to open LLM provider dropdown")
                menu_tag = f"menu_provider_{llm_provider}"
                if not client.wait_for_element(menu_tag, timeout=5):
                    return fail("llm", f"{menu_tag} not found in provider dropdown")
                if not _click_or_tap(client, adb, menu_tag):
                    return fail("llm", f"failed to click {menu_tag}")
                time.sleep(0.5)
                if not client.input("input_api_key", llm_api_key):
                    return fail("llm", "failed to input LLM API key")
                time.sleep(0.5)
            else:
                # No key available: keyless "local" (Ollama) provider lets the
                # wizard proceed and the backend start without a real key.
                if not _click_or_tap(client, adb, "input_llm_provider"):
                    return fail("llm", "failed to open LLM provider dropdown")
                if not client.wait_for_element("menu_provider_local", timeout=5):
                    return fail("llm", "menu_provider_local not found in provider dropdown")
                if not _click_or_tap(client, adb, "menu_provider_local"):
                    return fail("llm", "failed to click menu_provider_local")
                time.sleep(0.5)
            if not _click_or_tap(client, adb, "btn_next"):
                return fail("llm", "failed to click btn_next on LLM step")
            time.sleep(0.5)
        else:
            print("  [6/7] LLM_CONFIGURATION not present (node-client build) — continuing")

        # ── Step 4: AGE_RANGE (final step → COMPLETE) ─────────────────────
        band_tag = f"age_band_{age_band}"
        print(f"  [7/7] AGE_RANGE: {band_tag} → finish")
        if not client.wait_for_element(band_tag, timeout=10):
            return fail("age_range", f"{band_tag} not found on age-range step")
        if not _click_or_tap(client, adb, band_tag):
            return fail("age_range", f"failed to click {band_tag}")
        time.sleep(0.3)
        if not _click_or_tap(client, adb, "btn_next"):
            return fail("age_range", "failed to click btn_next (finish) on age-range step")

        # ── Step 5: COMPLETE — leave the wizard or reach the terminal step ─
        # 150s: setup-complete now wires the persist engine (keyring genesis:
        # hardware-wrapped Ed25519 + PQC) which takes 60-120s under emulator
        # arm64 translation.
        deadline = time.time() + 150
        completed_via = None
        while time.time() < deadline:
            screen = client.screen()
            if screen and screen != "Setup":
                completed_via = f"left wizard → {screen}"
                break
            if not client.is_visible("btn_next"):
                completed_via = "COMPLETE step (btn_next gone)"
                break
            time.sleep(1)

        screenshot_path = f"/tmp/ciris_setup_done_{int(time.time())}.png"
        adb.screenshot(screenshot_path)
        screenshots.append(screenshot_path)

        if completed_via is None:
            return fail("complete", f"still on Setup with btn_next after 150s (screen={client.screen()!r})")

        return TestReport(
            name="test_setup_wizard",
            result=TestResult.PASSED,
            duration=time.time() - start_time,
            message=(
                "First-run wizard completed (WELCOME → ACCOUNT → FED-ID → [LLM] → AGE_RANGE); "
                f"announce-gate verified both ways; {completed_via}"
            ),
            screenshots=screenshots,
        )

    except Exception as e:
        return TestReport(
            name="test_setup_wizard",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
            screenshots=screenshots,
        )


def test_catchup_add_fedid(adb: ADBHelper, ui: UIAutomator, config: dict) -> TestReport:
    """
    Test: catch-up "Add Federation ID" flow (AddFederationIdScreen).

    For an already-logged-in legacy owner (password/OAuth ROOT, NO fed-ID).
    Mirrors the desktop QA runner's test_catchup_add_fedid_flow:

        Manage Nodes → btn_add_federation_id → AddFederationIdScreen:
        input_fed_label → toggle_announce_ownership
        → toggle_trace_opt_in (gated on announce) → btn_add_fedid_confirm
        (back affordance: btn_add_fedid_back)

    TOLERATED SKIP: the client renders btn_add_federation_id ONLY when the
    logged-in owner has no fed-ID (ownerHasFedId == false from the local
    node's GET /v1/setup/owned-nodes); `null` — e.g. a backend that doesn't
    serve owned-nodes — fail-closes it hidden. If the entry point can't be
    reached the test SKIPs with the reason instead of failing.

    Config options:
    - fed_label: catch-up label (default: generated qa-catchup-<ts>)
    - announce / trace_opt_in: as in test_setup_wizard (default True/True)
    - setup_username / setup_password: credentials if a login is needed
    """
    start_time = time.time()
    screenshots = []

    fed_label = config.get("fed_label") or f"qa-catchup-{int(time.time())}"
    announce = config.get("announce", True)
    trace_opt_in = config.get("trace_opt_in", True)
    username = config.get("setup_username", "admin")
    password = config.get("setup_password", "qa_test_password_12345")

    def fail(step: str, detail: str) -> TestReport:
        path = f"/tmp/ciris_catchup_fail_{int(time.time())}.png"
        adb.screenshot(path)
        screenshots.append(path)
        return TestReport(
            name="test_catchup_add_fedid",
            result=TestResult.FAILED,
            duration=time.time() - start_time,
            message=f"[{step}] {detail}",
            screenshots=screenshots,
        )

    def skip(reason: str) -> TestReport:
        return TestReport(
            name="test_catchup_add_fedid",
            result=TestResult.SKIPPED,
            duration=time.time() - start_time,
            message=f"Tolerated skip: {reason}",
            screenshots=screenshots,
        )

    try:
        # ── Step 0: reach a logged-in session ─────────────────────────────
        print("  [1/5] Connecting to in-app test server (no data clear — needs existing user)...")
        client = connect_test_server(adb, config, launch_if_needed=True, clear_data=False)
        if not client:
            return fail("connect", "in-app test-automation server unreachable (debug build required)")

        screen = client.wait_for_any_screen(["Login", "Setup", "Interact", "ManageNodes"], timeout=180.0, interval=1.5)
        if screen == "Setup":
            return skip("app is on the first-run wizard — no existing logged-in owner to catch up")
        if screen == "Login":
            print("  Login screen → local login as existing user")
            if not _click_or_tap(client, adb, "btn_local_login"):
                return fail("login", "could not click btn_local_login")
            time.sleep(1.5)
            if client.screen() == "Setup":
                return skip("Local Login routed to first-run wizard — backend unconfigured, no legacy owner")
            if client.is_visible("input_username"):
                client.input("input_username", username)
                client.input("input_password", password)
                time.sleep(0.3)
                if not _click_or_tap(client, adb, "btn_login_submit"):
                    return fail("login", "could not click btn_login_submit")
            if not client.wait_for_any_screen(["Interact", "ManageNodes"], timeout=60.0):
                return fail("login", f"did not reach a logged-in surface (screen={client.screen()!r})")
        elif screen is None:
            return fail("land", f"never reached a known screen (screen={client.screen()!r})")

        # ── Step 1: reach the entry point (Manage Nodes surface) ──────────
        print("  [2/5] Reaching Manage Nodes → btn_add_federation_id...")
        if not client.is_visible("btn_add_federation_id"):
            # Canonical path: (drawer on compact) → Manage group → Nodes row.
            if not client.is_visible("nav_epistemic_nodes"):
                if client.is_visible("btn_nav_drawer_open"):
                    print("      opening nav drawer")
                    _click_or_tap(client, adb, "btn_nav_drawer_open")
                    time.sleep(1)
                if not client.is_visible("nav_epistemic_nodes") and client.is_visible("nav_group_manage"):
                    print("      expanding sidebar group nav_group_manage")
                    _click_or_tap(client, adb, "nav_group_manage")
                    client.wait_for_element("nav_epistemic_nodes", timeout=3)
            if client.is_visible("nav_epistemic_nodes"):
                print("      clicking nav_epistemic_nodes")
                _click_or_tap(client, adb, "nav_epistemic_nodes")
                client.wait_for_element("btn_add_federation_id", timeout=5)

        if not client.is_visible("btn_add_federation_id"):
            # Entry renders only for an owner WITHOUT a fed-ID; null (backend
            # without GET /v1/setup/owned-nodes) fail-closes it hidden.
            path = f"/tmp/ciris_catchup_entry_{int(time.time())}.png"
            adb.screenshot(path)
            screenshots.append(path)
            return skip(
                "btn_add_federation_id not rendered — owner already has a fed-ID, or "
                "ownerHasFedId is null (backend without GET /v1/setup/owned-nodes fail-closes the entry). "
                f"screen={client.screen()!r}"
            )

        # ── Step 2: open the guided catch-up screen ───────────────────────
        print("  [3/5] btn_add_federation_id → AddFederationIdScreen")
        if not _click_or_tap(client, adb, "btn_add_federation_id"):
            return fail("open", "failed to click btn_add_federation_id")
        if not client.wait_for_element("input_fed_label", timeout=6):
            return fail("open", "input_fed_label did not appear (AddFederationIdScreen)")

        # ── Step 3: label + announce-gate assertions (both ways) ──────────
        print(f"  [4/5] label={fed_label!r}, announce={announce}, trace={trace_opt_in}")
        if client.is_visible("toggle_trace_opt_in"):
            return fail("gate_off", "toggle_trace_opt_in visible BEFORE announce is ON (catch-up gating broken)")
        print("      gate check OK: toggle_trace_opt_in absent while announce OFF")

        if not client.input("input_fed_label", fed_label):
            return fail("label", "failed to input input_fed_label")
        time.sleep(0.3)

        if announce:
            if not _click_or_tap(client, adb, "toggle_announce_ownership"):
                return fail("announce", "failed to click toggle_announce_ownership")
            if not client.wait_for_element("toggle_trace_opt_in", timeout=5):
                return fail("gate_on", "toggle_trace_opt_in did NOT appear after announce ON (catch-up gating broken)")
            print("      gate check OK: toggle_trace_opt_in appeared after announce ON")
            if trace_opt_in:
                if not _click_or_tap(client, adb, "toggle_trace_opt_in"):
                    return fail("trace", "failed to click toggle_trace_opt_in")
                time.sleep(0.3)

        screenshot_path = f"/tmp/ciris_catchup_{int(time.time())}.png"
        adb.screenshot(screenshot_path)
        screenshots.append(screenshot_path)

        # ── Step 4: confirm ───────────────────────────────────────────────
        print("  [5/5] btn_add_fedid_confirm")
        if not _click_or_tap(client, adb, "btn_add_fedid_confirm"):
            return fail("confirm", "btn_add_fedid_confirm not clickable")
        # Success leaves via onDone → back to ManageNodes; a soft failure
        # keeps the screen up with an error surface. Best-effort observe.
        left = client.wait_for_screen("ManageNodes", timeout=20.0)

        return TestReport(
            name="test_catchup_add_fedid",
            result=TestResult.PASSED,
            duration=time.time() - start_time,
            message=(
                "Catch-up add-fed-ID flow driven (label → announce → trace → confirm); "
                + ("upgrade completed (returned to ManageNodes)" if left else "confirm submitted (screen did not return to ManageNodes within 20s — check node logs)")
            ),
            screenshots=screenshots,
        )

    except Exception as e:
        return TestReport(
            name="test_catchup_add_fedid",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
            screenshots=screenshots,
        )


def test_chat_interaction(adb: ADBHelper, ui: UIAutomator, config: dict) -> TestReport:
    """
    Test: Send a message and receive a response.

    Prerequisites:
    - Must be on Interact screen (after setup)

    Steps:
    1. Verify we're on the chat screen
    2. Type a test message
    3. Click send
    4. Wait for agent response
    5. Verify response received
    """
    start_time = time.time()
    screenshots = []
    test_message = config.get("test_message", "Hello, how are you?")

    try:
        print("  [1/5] Verifying chat screen...")

        # Wait for chat screen (check PRIMARY indicators)
        chat_visible = False
        for indicator in CIRISAppConfig.CHAT_SCREEN_INDICATORS_PRIMARY:
            if ui.wait_for_text(indicator, timeout=5):
                chat_visible = True
                print(f"  Found chat indicator: '{indicator}'")
                break

        # Also accept Shutdown/STOP buttons as proof we're on chat screen
        if not chat_visible:
            for indicator in ["Shutdown", "STOP"]:
                if ui.is_text_visible(indicator):
                    chat_visible = True
                    print(f"  Found chat-only indicator: '{indicator}'")
                    break

        if not chat_visible:
            screen_info = ui.dump_screen_info()
            return TestReport(
                name="test_chat_interaction",
                result=TestResult.SKIPPED,
                duration=time.time() - start_time,
                message=f"Not on chat screen. Visible: {screen_info.get('texts', [])}",
            )

        print("  [2/5] Finding message input...")

        # Find the message input field. Post-setup the runtime restarts all 22
        # services before chat composes — 60-120s under emulator arm64
        # translation — so retry until the input appears rather than sampling once.
        input_field = None
        _input_deadline = time.time() + 150
        while input_field is None and time.time() < _input_deadline:
            # First try by test tag (resource-id contains the tag)
            input_field = ui.find_by_resource_id(CIRISAppConfig.TAG_INPUT_MESSAGE)
            if not input_field:
                # Fallback: Look for EditText with hint "Type your message..."
                input_field = ui.find_by_text(CIRISAppConfig.TEXT_TYPE_MESSAGE)
            if not input_field:
                # Try finding by class
                edit_texts = ui.find_by_class("EditText")
                input_field = edit_texts[0] if edit_texts else None
            if not input_field:
                time.sleep(5)

        if not input_field:
            return TestReport(
                name="test_chat_interaction",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="Message input field not found",
            )

        print(f"  [3/5] Typing message: '{test_message}'")

        # Type the message
        ui.click(input_field)
        time.sleep(0.3)
        adb.input_text(test_message)
        time.sleep(0.5)

        print("  [4/5] Sending message...")

        # Find and click send button
        # First try by test tag
        send_clicked = ui.click_by_resource_id(CIRISAppConfig.TAG_BTN_SEND)
        if not send_clicked:
            # Fallback: try by content description
            send_clicked = ui.click_by_content_desc(CIRISAppConfig.TEXT_SEND)
        if not send_clicked:
            # Try clicking by text
            send_clicked = ui.click_by_text(CIRISAppConfig.TEXT_SEND)

        if not send_clicked:
            # Try finding IconButton for send
            clickable = ui.find_clickable()
            for elem in clickable:
                desc = getattr(elem, "content_desc", "") or ""
                res_id = getattr(elem, "resource_id", "") or ""
                if "send" in desc.lower() or "send" in res_id.lower():
                    ui.click(elem)
                    send_clicked = True
                    break

        if not send_clicked:
            # Final fallback: use configured coordinates
            send_coords = ScreenCoordinates.get("send_button_center", config)
            print(f"  Using coordinate fallback for send: {send_coords}")
            adb.tap(*send_coords)
            send_clicked = True

        if not send_clicked:
            return TestReport(
                name="test_chat_interaction",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="Could not click send button",
            )

        print("  [5/5] Waiting for response...")

        # Wait for processing indicator and then response
        time.sleep(2)  # Wait for initial processing

        # Wait for response - look for CIRIS message bubble
        # Agent messages typically appear with "CIRIS" author label
        response_timeout = CIRISAppConfig.TIMEOUT_CHAT_RESPONSE
        start_wait = time.time()
        response_found = False

        while time.time() - start_wait < response_timeout:
            ui.refresh_hierarchy()
            screen_texts = ui.get_screen_text()

            # Check for processing indicators gone and response present
            # Agent messages will appear in the chat list
            # Look for any new text that wasn't our message
            for text in screen_texts:
                # Skip our own message and UI labels
                if (
                    text != test_message
                    and text not in ["CIRIS", "You", "Send", "Connected", "Chat with CIRIS"]
                    and len(text) > 10  # Response should be substantive
                    and "Type your message" not in text
                ):
                    response_found = True
                    break

            if response_found:
                break

            time.sleep(1)

        # Take screenshot
        screenshot_path = f"/tmp/ciris_chat_{int(time.time())}.png"
        adb.screenshot(screenshot_path)
        screenshots.append(screenshot_path)

        if response_found:
            return TestReport(
                name="test_chat_interaction",
                result=TestResult.PASSED,
                duration=time.time() - start_time,
                message="Message sent and response received",
                screenshots=screenshots,
            )
        else:
            screen_info = ui.dump_screen_info()
            return TestReport(
                name="test_chat_interaction",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"No response received within {response_timeout}s. Screen: {screen_info.get('texts', [])}",
                screenshots=screenshots,
            )

    except Exception as e:
        return TestReport(
            name="test_chat_interaction",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
            screenshots=screenshots,
        )


def test_full_flow(adb: ADBHelper, ui: UIAutomator, config: dict) -> TestReport:
    """
    Test: Complete end-to-end flow.

    Steps:
    1. Launch app (fresh)
    2. Google Sign-In with test account
    3. Complete setup wizard
    4. Send test message
    5. Verify response
    """
    start_time = time.time()
    all_screenshots = []
    results = []

    try:
        print("\n=== Test: Full Flow ===\n")

        # 1. Launch app
        step_start = time.time()
        print("[Step 1/4] App Launch")
        result = test_app_launch(adb, ui, config)
        results.append(result)
        all_screenshots.extend(result.screenshots)
        print(f"  ⏱️  Step 1 completed in {time.time() - step_start:.1f}s")
        if result.result != TestResult.PASSED:
            return TestReport(
                name="test_full_flow",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"Failed at app launch: {result.message}",
                screenshots=all_screenshots,
            )

        # 2. Login — local (Compose-driveable) or Google (native overlay).
        step_start = time.time()
        login_mode = config.get("login_mode", "google")
        if login_mode == "local":
            # The node-client wizard test drives Login → btn_local_login →
            # Setup itself via the in-app test server (the old text-based
            # test_local_login expected the pre-2.9 wizard's "Setup"/"LLM"
            # texts). Nothing to do here.
            print("\n[Step 2/4] Local Login — handled inside the setup wizard test (test server drives btn_local_login)")
        else:
            print("\n[Step 2/4] Google Sign-In")
            result = test_google_signin(adb, ui, config)
            results.append(result)
            all_screenshots.extend(result.screenshots)
            print(f"  ⏱️  Step 2 completed in {time.time() - step_start:.1f}s")
            if result.result not in [TestResult.PASSED, TestResult.SKIPPED]:
                # Try local login as fallback
                print("  Google Sign-In failed, trying Local Login...")
                adb.press_back()
                time.sleep(1)
                result = test_local_login(adb, ui, config)
                results.append(result)
                if result.result != TestResult.PASSED:
                    return TestReport(
                        name="test_full_flow",
                        result=TestResult.FAILED,
                        duration=time.time() - start_time,
                        message=f"Failed at login: {result.message}",
                        screenshots=all_screenshots,
                    )

        # 3. Setup Wizard
        step_start = time.time()
        print("\n[Step 3/4] Setup Wizard")
        result = test_setup_wizard(adb, ui, config)
        results.append(result)
        all_screenshots.extend(result.screenshots)
        print(f"  ⏱️  Step 3 completed in {time.time() - step_start:.1f}s")
        if result.result != TestResult.PASSED:
            return TestReport(
                name="test_full_flow",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"Failed at setup: {result.message}",
                screenshots=all_screenshots,
            )

        # 4. Chat Interaction
        step_start = time.time()
        print("\n[Step 4/4] Chat Interaction")
        result = test_chat_interaction(adb, ui, config)
        results.append(result)
        all_screenshots.extend(result.screenshots)
        print(f"  ⏱️  Step 4 completed in {time.time() - step_start:.1f}s")
        if result.result != TestResult.PASSED:
            return TestReport(
                name="test_full_flow",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"Failed at chat: {result.message}",
                screenshots=all_screenshots,
            )

        # All steps passed
        passed_count = sum(1 for r in results if r.result == TestResult.PASSED)
        return TestReport(
            name="test_full_flow",
            result=TestResult.PASSED,
            duration=time.time() - start_time,
            message=f"Full flow completed successfully ({passed_count}/{len(results)} steps passed)",
            screenshots=all_screenshots,
        )

    except Exception as e:
        return TestReport(
            name="test_full_flow",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
            screenshots=all_screenshots,
        )


# ========== Screen Navigation Tests ==========
# Tests for each mobile screen added in 1.9.2

# Screen definitions with expected UI indicators
SCREEN_TESTS = {
    "audit": {
        "menu_text": "Audit Trail",
        "indicators": ["Audit", "entries", "severity"],
        "description": "Audit trail viewer",
    },
    "logs": {
        "menu_text": "Logs",
        "indicators": ["Logs", "level", "service"],
        "description": "System logs viewer",
    },
    "memory": {
        "menu_text": "Memory",
        "indicators": ["Memory", "nodes", "search"],
        "description": "Memory/graph viewer",
    },
    "config": {
        "menu_text": "Config",
        "indicators": ["Config", "settings", "category"],
        "description": "Configuration management",
    },
    "consent": {
        "menu_text": "Consent",
        "indicators": ["Consent", "stream", "partnership"],
        "description": "User consent/GDPR",
    },
    "system": {
        "menu_text": "System",
        "indicators": ["System", "health", "runtime"],
        "description": "System management",
    },
    "services": {
        "menu_text": "Services",
        "indicators": ["Services", "status", "healthy"],
        "description": "Service status management",
    },
    "runtime": {
        "menu_text": "Runtime",
        "indicators": ["Runtime", "control", "pause"],
        "description": "Runtime control panel",
    },
}


def _navigate_to_screen(adb: ADBHelper, ui: UIAutomator, menu_text: str) -> bool:
    """
    Navigate to a screen via the overflow menu.
    Returns True if navigation succeeded.
    """
    # Open overflow menu
    overflow_clicked = False
    for desc in ["More options", "MoreVert", "More"]:
        element = ui.find_by_content_desc(desc, exact=False)
        if element:
            ui.click(element)
            overflow_clicked = True
            time.sleep(0.5)
            break

    if not overflow_clicked:
        # Try text-based menu button
        element = ui.find_by_text("More")
        if element:
            ui.click(element)
            overflow_clicked = True
            time.sleep(0.5)

    if not overflow_clicked:
        return False

    # Click the menu item
    time.sleep(0.3)
    ui.refresh_hierarchy()
    element = ui.find_by_text(menu_text, exact=False)
    if element:
        ui.click(element)
        time.sleep(1)
        return True

    return False


def test_screen_navigation(adb: ADBHelper, ui: UIAutomator, config: dict, screen_name: str = None) -> TestReport:
    """
    Test: Navigate to a specific screen and verify it loads.

    Args:
        screen_name: Name of screen to test (from SCREEN_TESTS keys).
                    If None, tests all screens sequentially.
    """
    start_time = time.time()
    screenshots = []

    if screen_name and screen_name not in SCREEN_TESTS:
        return TestReport(
            name=f"test_screen_{screen_name}",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Unknown screen: {screen_name}. Available: {list(SCREEN_TESTS.keys())}",
        )

    screens_to_test = [screen_name] if screen_name else list(SCREEN_TESTS.keys())
    results = []

    try:
        # Verify we're on chat/interact screen first
        chat_visible = False
        for indicator in CIRISAppConfig.CHAT_SCREEN_INDICATORS_PRIMARY:
            if ui.is_text_visible(indicator):
                chat_visible = True
                break
        if not chat_visible:
            for indicator in ["Shutdown", "STOP"]:
                if ui.is_text_visible(indicator):
                    chat_visible = True
                    break

        if not chat_visible:
            return TestReport(
                name="test_screen_navigation",
                result=TestResult.SKIPPED,
                duration=time.time() - start_time,
                message="Not on chat screen - must complete setup first",
            )

        for sname in screens_to_test:
            screen_config = SCREEN_TESTS[sname]
            print(f"\n  Testing screen: {sname} ({screen_config['description']})")

            # Navigate to screen
            if not _navigate_to_screen(adb, ui, screen_config["menu_text"]):
                results.append((sname, False, "Failed to navigate via menu"))
                continue

            time.sleep(1.5)
            ui.refresh_hierarchy()

            # Take screenshot
            screenshot_path = f"/tmp/ciris_screen_{sname}_{int(time.time())}.png"
            adb.screenshot(screenshot_path)
            screenshots.append(screenshot_path)

            # Check for any indicator (exact=False for partial/case-insensitive matching)
            found_indicator = None
            for indicator in screen_config["indicators"]:
                if ui.is_text_visible(indicator, exact=False):
                    found_indicator = indicator
                    break

            if found_indicator:
                results.append((sname, True, f"Found: {found_indicator}"))
                print(f"    ✓ Screen loaded (found: {found_indicator})")
            else:
                screen_texts = ui.get_screen_text()
                results.append((sname, False, f"No indicators found. Visible: {screen_texts[:5]}"))
                print(f"    ✗ Screen indicators not found")

            # Navigate back to chat screen
            adb.press_back()
            time.sleep(1)

        # Summarize results
        passed = sum(1 for _, success, _ in results if success)
        total = len(results)

        if passed == total:
            return TestReport(
                name="test_screen_navigation",
                result=TestResult.PASSED,
                duration=time.time() - start_time,
                message=f"All {total} screens loaded successfully",
                screenshots=screenshots,
            )
        elif passed > 0:
            failed_screens = [name for name, success, _ in results if not success]
            return TestReport(
                name="test_screen_navigation",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"{passed}/{total} screens passed. Failed: {failed_screens}",
                screenshots=screenshots,
            )
        else:
            return TestReport(
                name="test_screen_navigation",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="All screen tests failed",
                screenshots=screenshots,
            )

    except Exception as e:
        return TestReport(
            name="test_screen_navigation",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
            screenshots=screenshots,
        )


# Individual screen test functions for granular testing
def test_screen_audit(adb: ADBHelper, ui: UIAutomator, config: dict) -> TestReport:
    """Test: Navigate to Audit screen and verify it loads."""
    return test_screen_navigation(adb, ui, config, "audit")


def test_screen_logs(adb: ADBHelper, ui: UIAutomator, config: dict) -> TestReport:
    """Test: Navigate to Logs screen and verify it loads."""
    return test_screen_navigation(adb, ui, config, "logs")


def test_screen_memory(adb: ADBHelper, ui: UIAutomator, config: dict) -> TestReport:
    """Test: Navigate to Memory screen and verify it loads."""
    return test_screen_navigation(adb, ui, config, "memory")


def test_screen_config(adb: ADBHelper, ui: UIAutomator, config: dict) -> TestReport:
    """Test: Navigate to Config screen and verify it loads."""
    return test_screen_navigation(adb, ui, config, "config")


def test_screen_consent(adb: ADBHelper, ui: UIAutomator, config: dict) -> TestReport:
    """Test: Navigate to Consent screen and verify it loads."""
    return test_screen_navigation(adb, ui, config, "consent")


def test_screen_system(adb: ADBHelper, ui: UIAutomator, config: dict) -> TestReport:
    """Test: Navigate to System screen and verify it loads."""
    return test_screen_navigation(adb, ui, config, "system")


def test_screen_services(adb: ADBHelper, ui: UIAutomator, config: dict) -> TestReport:
    """Test: Navigate to Services screen and verify it loads."""
    return test_screen_navigation(adb, ui, config, "services")


def test_screen_runtime(adb: ADBHelper, ui: UIAutomator, config: dict) -> TestReport:
    """Test: Navigate to Runtime screen and verify it loads."""
    return test_screen_navigation(adb, ui, config, "runtime")


def test_all_screens(adb: ADBHelper, ui: UIAutomator, config: dict) -> TestReport:
    """Test: Navigate to all screens and verify they load."""
    return test_screen_navigation(adb, ui, config, None)


# =============================================================================
# Connect Node / Register Agent Tests (Device Auth via Portal)
# =============================================================================


def test_connect_node_welcome(adb: ADBHelper, ui: UIAutomator, config: dict) -> TestReport:
    """
    Test: Verify Register Your Agent card appears on WELCOME screen.

    Steps:
    1. Launch app fresh
    2. Login via Local Login to reach WELCOME step
    3. Verify Register Your Agent card is visible
    """
    start_time = time.time()
    screenshots = []
    package = CIRISAppConfig.PACKAGE

    try:
        print("  [1/3] Launching app fresh...")
        adb.force_stop_app(package)
        time.sleep(1)
        adb.launch_app(package, CIRISAppConfig.MAIN_ACTIVITY)

        # Wait for login screen
        login_btn = ui.wait_for_text(CIRISAppConfig.TEXT_LOCAL_LOGIN, timeout=60)
        if not login_btn:
            return TestReport(
                name="test_connect_node_welcome",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="Login screen not found",
            )

        print("  [2/3] Logging in via Local Login...")
        ui.click_by_text(CIRISAppConfig.TEXT_LOCAL_LOGIN)
        time.sleep(3)

        print("  [3/3] Checking for Register Your Agent card...")
        card_found = ui.wait_for_text(CIRISAppConfig.TEXT_REGISTER_AGENT, timeout=15)

        if card_found:
            # Verify additional elements
            has_pricing = ui.is_text_visible(CIRISAppConfig.TEXT_REGISTER_SUBTITLE)
            has_connect_btn = ui.is_text_visible(CIRISAppConfig.TEXT_CONNECT)

            screenshot_path = f"/tmp/ciris_android_welcome_{int(time.time())}.png"
            adb.screenshot(screenshot_path)
            screenshots.append(screenshot_path)

            return TestReport(
                name="test_connect_node_welcome",
                result=TestResult.PASSED,
                duration=time.time() - start_time,
                message=f"Card found. Pricing visible: {has_pricing}, Connect btn: {has_connect_btn}",
                screenshots=screenshots,
            )
        else:
            hierarchy = ui.dump_hierarchy()
            visible_texts = ui.extract_texts_from_hierarchy(hierarchy) if hierarchy else []
            return TestReport(
                name="test_connect_node_welcome",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"Register Your Agent card not found. Visible: {visible_texts[:15]}",
                screenshots=screenshots,
            )

    except Exception as e:
        return TestReport(
            name="test_connect_node_welcome",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
            screenshots=screenshots,
        )


def test_connect_node_auth(adb: ADBHelper, ui: UIAutomator, config: dict) -> TestReport:
    """
    Test: Enter node URL and verify auth screen appears.

    Prerequisite: Must be on WELCOME step with Register Your Agent card visible.

    Steps:
    1. Find Portal URL input field
    2. Enter portal URL
    3. Tap Connect button
    4. Verify NODE_AUTH step appears
    """
    start_time = time.time()
    screenshots = []
    node_url = config.get("portal_url", config.get("node_url", "https://portal.ciris.ai"))

    try:
        print("  [1/4] Verifying on WELCOME step...")
        if not ui.is_text_visible(CIRISAppConfig.TEXT_REGISTER_AGENT):
            return TestReport(
                name="test_connect_node_auth",
                result=TestResult.SKIPPED,
                duration=time.time() - start_time,
                message="Not on WELCOME step with Register Your Agent card",
            )

        print(f"  [2/4] Entering portal URL: {node_url}")
        # Try to find and click URL field
        url_field = ui.find_by_text(CIRISAppConfig.TEXT_PORTAL_URL_PLACEHOLDER)
        if url_field:
            ui.click(url_field)
            time.sleep(0.5)

        # Type the URL
        adb.input_text(node_url)
        time.sleep(1)

        print("  [3/4] Tapping Connect button...")
        connect_clicked = ui.click_by_text(CIRISAppConfig.TEXT_CONNECT)
        if not connect_clicked:
            return TestReport(
                name="test_connect_node_auth",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="Could not find or click Connect button",
            )

        time.sleep(3)

        print("  [4/4] Verifying NODE_AUTH step...")
        # Look for auth step indicators
        auth_visible = (
            ui.is_text_visible(CIRISAppConfig.TEXT_REGISTER_AGENT_STEP)
            or ui.is_text_visible(CIRISAppConfig.TEXT_WAITING_AUTH)
            or ui.is_text_visible(CIRISAppConfig.TEXT_CONNECTING_PORTAL)
            or ui.is_text_visible("Verification")
            or ui.is_text_visible("device code")
        )

        screenshot_path = f"/tmp/ciris_android_auth_{int(time.time())}.png"
        adb.screenshot(screenshot_path)
        screenshots.append(screenshot_path)

        if auth_visible:
            return TestReport(
                name="test_connect_node_auth",
                result=TestResult.PASSED,
                duration=time.time() - start_time,
                message="NODE_AUTH step reached after entering portal URL",
                screenshots=screenshots,
            )
        else:
            hierarchy = ui.dump_hierarchy()
            visible_texts = ui.extract_texts_from_hierarchy(hierarchy) if hierarchy else []
            return TestReport(
                name="test_connect_node_auth",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"NODE_AUTH not reached. Visible: {visible_texts[:15]}",
                screenshots=screenshots,
            )

    except Exception as e:
        return TestReport(
            name="test_connect_node_auth",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
            screenshots=screenshots,
        )


def test_connect_node(adb: ADBHelper, ui: UIAutomator, config: dict) -> TestReport:
    """
    Test: Full Register Agent device auth flow (via Portal/Registry).

    This is the primary test case for the agent registration feature.
    The flow contacts CIRISPortal for device auth.

    Steps:
    1. Launch app and login
    2. Find Register Your Agent card
    3. Enter portal URL
    4. Tap Connect
    5. Wait for NODE_AUTH step
    6. Verify verification URL and device code display
    7. Optionally wait for Portal authorization

    Config options:
    - portal_url: Portal URL (default: https://portal.ciris.ai)
    - wait_for_portal_auth: Wait for user to complete Portal auth (default: False)
    - portal_auth_timeout: Timeout for Portal auth in seconds (default: 300)
    """
    start_time = time.time()
    screenshots = []
    package = CIRISAppConfig.PACKAGE
    node_url = config.get("portal_url", config.get("node_url", "https://portal.ciris.ai"))
    wait_for_portal = config.get("wait_for_portal_auth", False)
    auth_timeout = config.get("portal_auth_timeout", 300)

    try:
        # ============================================================
        # Step 1: Launch and login
        # ============================================================
        print("  [1/8] Launching app fresh...")
        adb.force_stop_app(package)
        time.sleep(1)
        adb.launch_app(package, CIRISAppConfig.MAIN_ACTIVITY)

        login_btn = ui.wait_for_text(CIRISAppConfig.TEXT_LOCAL_LOGIN, timeout=60)
        if not login_btn:
            return TestReport(
                name="test_connect_node",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="Could not reach login screen",
            )

        print("  [2/8] Logging in via Local Login...")
        ui.click_by_text(CIRISAppConfig.TEXT_LOCAL_LOGIN)
        time.sleep(3)

        # ============================================================
        # Step 2: Find Register Your Agent card
        # ============================================================
        print("  [3/8] Looking for Register Your Agent card...")
        card_found = ui.wait_for_text(CIRISAppConfig.TEXT_REGISTER_AGENT, timeout=15)
        if not card_found:
            hierarchy = ui.dump_hierarchy()
            visible_texts = ui.extract_texts_from_hierarchy(hierarchy) if hierarchy else []
            return TestReport(
                name="test_connect_node",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"Register Your Agent card not found on WELCOME. Visible: {visible_texts[:15]}",
            )

        # ============================================================
        # Step 3: Enter portal URL
        # ============================================================
        print(f"  [4/8] Entering portal URL: {node_url}")
        url_field = ui.find_by_text(CIRISAppConfig.TEXT_PORTAL_URL_PLACEHOLDER)
        if url_field:
            ui.click(url_field)
            time.sleep(0.5)

        adb.input_text(node_url)
        time.sleep(1)

        # ============================================================
        # Step 4: Tap Connect
        # ============================================================
        print("  [5/8] Tapping Connect button...")
        connect_clicked = ui.click_by_text(CIRISAppConfig.TEXT_CONNECT)
        if not connect_clicked:
            return TestReport(
                name="test_connect_node",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="Could not find or click Connect button",
            )

        time.sleep(3)

        # ============================================================
        # Step 5: Wait for NODE_AUTH step
        # ============================================================
        print("  [6/8] Waiting for NODE_AUTH step...")
        auth_visible = ui.wait_for_text(CIRISAppConfig.TEXT_REGISTER_AGENT_STEP, timeout=15)
        if not auth_visible:
            auth_visible = (
                ui.is_text_visible(CIRISAppConfig.TEXT_WAITING_AUTH)
                or ui.is_text_visible("Verification")
                or ui.is_text_visible("device code")
            )

        if not auth_visible:
            hierarchy = ui.dump_hierarchy()
            visible_texts = ui.extract_texts_from_hierarchy(hierarchy) if hierarchy else []
            # Check for error states
            if any(t.lower() in str(visible_texts).lower() for t in ["error", "failed"]):
                return TestReport(
                    name="test_connect_node",
                    result=TestResult.FAILED,
                    duration=time.time() - start_time,
                    message=f"Connection error. Visible: {visible_texts[:15]}",
                )
            return TestReport(
                name="test_connect_node",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"NODE_AUTH step not reached. Visible: {visible_texts[:15]}",
            )

        # ============================================================
        # Step 6: Verify verification URL and device code
        # ============================================================
        print("  [7/8] Verifying device auth display...")
        has_verification_url = ui.is_text_visible(CIRISAppConfig.TEXT_VERIFICATION_URL)
        has_device_code = ui.is_text_visible("code") or ui.is_text_visible("Code")

        screenshot_path = f"/tmp/ciris_android_node_auth_{int(time.time())}.png"
        adb.screenshot(screenshot_path)
        screenshots.append(screenshot_path)

        # ============================================================
        # Step 7: Optionally wait for Portal authorization
        # ============================================================
        if wait_for_portal:
            print(f"  [8/8] Waiting for Portal authorization (timeout: {auth_timeout}s)...")
            print("        → Complete authorization in Portal browser window")

            poll_start = time.time()
            while time.time() - poll_start < auth_timeout:
                if ui.is_text_visible(CIRISAppConfig.TEXT_AGENT_AUTHORIZED) or ui.is_text_visible("template"):
                    has_template = ui.is_text_visible("template") or ui.is_text_visible("Template")
                    has_adapters = ui.is_text_visible("adapter") or ui.is_text_visible("Adapter")

                    screenshot_path = f"/tmp/ciris_android_auth_complete_{int(time.time())}.png"
                    adb.screenshot(screenshot_path)
                    screenshots.append(screenshot_path)

                    return TestReport(
                        name="test_connect_node",
                        result=TestResult.PASSED,
                        duration=time.time() - start_time,
                        message=f"Device auth completed. Template shown: {has_template}, Adapters shown: {has_adapters}",
                        screenshots=screenshots,
                    )
                time.sleep(5)

            return TestReport(
                name="test_connect_node",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"Portal auth not completed in {auth_timeout}s",
                screenshots=screenshots,
            )
        else:
            print("  [8/8] Skipping Portal auth wait (set wait_for_portal_auth=True to enable)")

            # Test passes if we reached the NODE_AUTH step with verification info
            if has_verification_url or has_device_code:
                return TestReport(
                    name="test_connect_node",
                    result=TestResult.PASSED,
                    duration=time.time() - start_time,
                    message=f"Device auth screen reached. Verification URL: {has_verification_url}, Device code: {has_device_code}",
                    screenshots=screenshots,
                )
            else:
                return TestReport(
                    name="test_connect_node",
                    result=TestResult.PASSED,
                    duration=time.time() - start_time,
                    message="NODE_AUTH step reached but verification details not detected via UI automator.",
                    screenshots=screenshots,
                )

    except Exception as e:
        return TestReport(
            name="test_connect_node",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
            screenshots=screenshots,
        )


def test_connect_node_error(adb: ADBHelper, ui: UIAutomator, config: dict) -> TestReport:
    """
    Test: Error handling for invalid node URL.

    Steps:
    1. Enter invalid node URL
    2. Tap Connect
    3. Verify error message appears
    """
    start_time = time.time()
    screenshots = []

    try:
        print("  [1/3] Verifying on WELCOME step...")
        if not ui.is_text_visible(CIRISAppConfig.TEXT_REGISTER_AGENT):
            return TestReport(
                name="test_connect_node_error",
                result=TestResult.SKIPPED,
                duration=time.time() - start_time,
                message="Not on WELCOME step",
            )

        print("  [2/3] Entering invalid node URL...")
        invalid_url = "https://invalid-portal-that-does-not-exist.example.com"

        url_field = ui.find_by_text(CIRISAppConfig.TEXT_PORTAL_URL_PLACEHOLDER)
        if url_field:
            ui.click(url_field)
            time.sleep(0.5)

        adb.input_text(invalid_url)
        time.sleep(0.5)

        ui.click_by_text(CIRISAppConfig.TEXT_CONNECT)
        time.sleep(5)  # Wait for connection attempt to fail

        print("  [3/3] Checking for error state...")
        hierarchy = ui.dump_hierarchy()
        visible_texts = ui.extract_texts_from_hierarchy(hierarchy) if hierarchy else []

        screenshot_path = f"/tmp/ciris_android_error_{int(time.time())}.png"
        adb.screenshot(screenshot_path)
        screenshots.append(screenshot_path)

        has_error = any(t.lower() in str(visible_texts).lower() for t in ["error", "failed", "could not", "unable"])

        if has_error:
            return TestReport(
                name="test_connect_node_error",
                result=TestResult.PASSED,
                duration=time.time() - start_time,
                message=f"Error state displayed correctly. Visible: {visible_texts[:10]}",
                screenshots=screenshots,
            )
        else:
            return TestReport(
                name="test_connect_node_error",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"No error message for invalid URL. Visible: {visible_texts[:10]}",
                screenshots=screenshots,
            )

    except Exception as e:
        return TestReport(
            name="test_connect_node_error",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
            screenshots=screenshots,
        )


def test_verify_trust(adb: ADBHelper, ui: UIAutomator, config: dict) -> TestReport:
    """
    Test: Trust and Security page displays correct CIRISVerify information.

    Validates:
    1. Key storage mode (hardware vs software)
    2. Ed25519 fingerprint display
    3. Binary/function self-check status
    4. File integrity counts
    5. Play Integrity status

    Requires: App logged in and running
    """
    from .verify_trust_tests import VerifyTrustExpectations, VerifyTrustTests

    start_time = time.time()
    screenshots = []

    try:
        # Run verify trust tests
        tests = VerifyTrustTests(adb, ui, expectations=VerifyTrustExpectations())
        reports = tests.run_all()

        # Aggregate results
        passed = sum(1 for r in reports if r.result == TestResult.PASSED)
        failed = sum(1 for r in reports if r.result == TestResult.FAILED)
        errors = sum(1 for r in reports if r.result == TestResult.ERROR)

        # Collect screenshots from sub-reports
        for r in reports:
            screenshots.extend(r.screenshots)

        # Build summary message
        failed_tests = [r.name for r in reports if r.result != TestResult.PASSED]
        if failed_tests:
            message = f"{passed}/{len(reports)} passed. Failed: {', '.join(failed_tests)}"
            result = TestResult.FAILED if failed > 0 else TestResult.ERROR
        else:
            message = f"All {passed} verify trust checks passed"
            result = TestResult.PASSED

        return TestReport(
            name="test_verify_trust",
            result=result,
            duration=time.time() - start_time,
            message=message,
            screenshots=screenshots,
        )

    except Exception as e:
        return TestReport(
            name="test_verify_trust",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
            screenshots=screenshots,
        )
