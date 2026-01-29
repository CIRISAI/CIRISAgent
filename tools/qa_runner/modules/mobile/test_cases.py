"""
Mobile Test Cases for CIRIS App

Test cases for automated UI testing with ADB and UI Automator.
"""

import time
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

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
    """Configuration for CIRIS mobile app testing."""

    PACKAGE = "ai.ciris.mobile"
    MAIN_ACTIVITY = "ai.ciris.mobile.MainActivity"
    APK_PATH = "mobile/androidApp/build/outputs/apk/debug/androidApp-debug.apk"

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
    # Current flow: Intro → AI Config → Confirm → (future screens) → Chat
    TEXT_SETUP_TITLE = "Setup"
    TEXT_LLM_PROVIDER = "LLM Provider"
    TEXT_API_KEY = "API Key"
    TEXT_NEXT = "Next"
    TEXT_CONTINUE = "Continue"  # Intro step button
    TEXT_FINISH_SETUP = "Finish Setup"  # Final step button
    TEXT_FINISH = "Finish"
    TEXT_COMPLETE = "Complete"
    TEXT_FREE_AI_ACCESS = "Free AI Access Ready"
    TEXT_AI_CONFIG = "AI Configuration"
    TEXT_CONFIRM_SETUP = "Confirm Setup"

    # Setup wizard navigation buttons (in priority order)
    # Add new button texts here as screens are added
    SETUP_NAV_BUTTONS = [
        "Finish Setup",  # Final step
        "Get Started",  # Future onboarding
        "Next",  # Middle steps
        "Continue",  # Intro step
        "Continue →",  # Alternate continue
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

    # Test tags (Compose testTag values appear in resource-id)
    TAG_BTN_GOOGLE_SIGNIN = "btn_google_signin"
    TAG_BTN_LOCAL_LOGIN = "btn_local_login"
    TAG_INPUT_MESSAGE = "input_message"
    TAG_BTN_SEND = "btn_send"

    # Timeouts (in seconds)
    TIMEOUT_APP_LAUNCH = 60
    TIMEOUT_GOOGLE_SIGNIN = 30
    TIMEOUT_SETUP = 90  # Increased for multi-step wizard
    TIMEOUT_CHAT_RESPONSE = 30
    TIMEOUT_SETUP_STEP = 5  # Max wait per wizard step


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
    DEFAULTS = {
        # Login screen
        "google_signin_center": (540, 1208),
        "local_login_center": (540, 1397),
        # Chat screen (bottom input area)
        "message_input_center": (274, 2179),
        "send_button_center": (996, 2180),
        # Setup wizard buttons (typically centered near bottom)
        "wizard_button_center_y": 2274,
        "wizard_continue_x": 540,  # Centered
        "wizard_next_x": 786,  # Right side
        "wizard_back_x": 294,  # Left side
        # Google account chooser
        "account_row_center_y": 1260,
        "account_row_x": 350,
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

        print("  [2/5] Clearing app data...")
        adb.clear_app_data(CIRISAppConfig.PACKAGE)
        time.sleep(1)

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

        # Wait for login screen (up to 60 seconds for Python startup)
        element = ui.wait_for_text(CIRISAppConfig.TEXT_SIGN_IN_GOOGLE, timeout=CIRISAppConfig.TIMEOUT_APP_LAUNCH)

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
    Test: Complete the setup wizard.

    Prerequisites:
    - Must be on Setup screen (after login)

    The wizard currently has 3 steps (extensible):
    1. Welcome/Intro (button: "Continue →")
    2. AI Configuration (button: "Next")
    3. Confirm Setup (button: "Finish Setup")

    Additional screens can be added - the test will navigate through
    any number of steps using the SETUP_NAV_BUTTONS priority list.
    """
    start_time = time.time()
    screenshots = []

    api_key = config.get("llm_api_key", "")
    max_steps = config.get("setup_max_steps", 15)  # Configurable for future screens

    try:
        print("  [1/4] Checking Setup screen...")

        # Wait for setup screen elements
        time.sleep(2)
        screen_info = ui.dump_screen_info()
        print(f"  Setup screen elements: {screen_info.get('texts', [])[:15]}")

        # Take screenshot
        screenshot_path = f"/tmp/ciris_setup_{int(time.time())}.png"
        adb.screenshot(screenshot_path)
        screenshots.append(screenshot_path)

        print("  [2/4] Navigating setup wizard...")

        # Navigate through wizard steps
        for step in range(max_steps):
            time.sleep(1.5)
            ui.refresh_hierarchy()

            # Check if we've completed setup (reached chat screen)
            # Must find a PRIMARY indicator - "Connected" alone is not sufficient
            for indicator in CIRISAppConfig.CHAT_SCREEN_INDICATORS_PRIMARY:
                if ui.is_text_visible(indicator):
                    print(f"  Setup completed! Found primary indicator '{indicator}' after {step + 1} clicks")
                    return TestReport(
                        name="test_setup_wizard",
                        result=TestResult.PASSED,
                        duration=time.time() - start_time,
                        message=f"Setup completed in {step + 1} steps (found: {indicator})",
                        screenshots=screenshots,
                    )

            # Also check for secondary indicators WITH primary context
            # If we see Shutdown/STOP buttons, we're definitely on chat screen
            for indicator in CIRISAppConfig.CHAT_SCREEN_INDICATORS_SECONDARY:
                if indicator in ["Shutdown", "STOP"] and ui.is_text_visible(indicator):
                    # Shutdown/STOP only appear on chat screen
                    print(f"  Setup completed! Found chat-only indicator '{indicator}' after {step + 1} clicks")
                    return TestReport(
                        name="test_setup_wizard",
                        result=TestResult.PASSED,
                        duration=time.time() - start_time,
                        message=f"Setup completed in {step + 1} steps (found: {indicator})",
                        screenshots=screenshots,
                    )

            # Look for API key input (for BYOK mode)
            if ui.is_text_visible("API Key") or ui.is_text_visible("api_key"):
                if api_key:
                    edit_fields = ui.find_by_class("EditText")
                    if edit_fields:
                        ui.set_text(edit_fields[0], api_key)
                        time.sleep(0.5)

            # Enable covenant metrics consent if the checkbox is visible
            # The checkbox text is "I agree to share anonymous alignment metrics"
            if config.get("enable_covenant_metrics", True):
                covenant_text = "I agree to share anonymous alignment metrics"
                if ui.is_text_visible(covenant_text):
                    # Find and click the checkbox or the text row
                    if ui.click_by_text(covenant_text):
                        print(f"  Step {step + 1}: Enabled covenant metrics consent")
                        time.sleep(0.5)

            # Try clicking navigation buttons in priority order
            next_clicked = False
            for button_text in CIRISAppConfig.SETUP_NAV_BUTTONS:
                if ui.click_by_text(button_text):
                    print(f"  Step {step + 1}: Clicked '{button_text}'")
                    next_clicked = True
                    break

            if not next_clicked:
                # Try finding any clickable button (not Back)
                screen_texts = ui.get_screen_text()
                print(f"  Step {step + 1}: No nav button found. Screen: {screen_texts[:10]}")

                # Last resort: find clickable elements
                clickable = ui.find_clickable()
                for elem in clickable:
                    # Skip Back button and other non-forward elements
                    elem_text = getattr(elem, "text", "") or ""
                    if any(skip in elem_text for skip in ["Back", "Cancel", "Skip"]):
                        continue
                    # Click forward-looking buttons
                    if "Button" in elem.class_name:
                        ui.click(elem)
                        print(f"  Step {step + 1}: Clicked fallback button")
                        next_clicked = True
                        break

                if not next_clicked:
                    # Check if we're stuck on a step that needs special handling
                    print(f"  Step {step + 1}: No clickable forward button found")

            time.sleep(1)

        # If we get here, setup didn't complete
        screenshot_path = f"/tmp/ciris_setup_stuck_{int(time.time())}.png"
        adb.screenshot(screenshot_path)
        screenshots.append(screenshot_path)

        screen_info = ui.dump_screen_info()
        return TestReport(
            name="test_setup_wizard",
            result=TestResult.FAILED,
            duration=time.time() - start_time,
            message=f"Setup wizard did not complete after {max_steps} steps. Final screen: {screen_info.get('texts', [])[:10]}",
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

        # Find the message input field
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
        print("[Step 1/4] App Launch")
        result = test_app_launch(adb, ui, config)
        results.append(result)
        all_screenshots.extend(result.screenshots)
        if result.result != TestResult.PASSED:
            return TestReport(
                name="test_full_flow",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"Failed at app launch: {result.message}",
                screenshots=all_screenshots,
            )

        # 2. Google Sign-In
        print("\n[Step 2/4] Google Sign-In")
        result = test_google_signin(adb, ui, config)
        results.append(result)
        all_screenshots.extend(result.screenshots)
        if result.result not in [TestResult.PASSED, TestResult.SKIPPED]:
            # Try local login as fallback
            print("  Google Sign-In failed, trying Local Login...")
            # Go back if needed
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
        print("\n[Step 3/4] Setup Wizard")
        result = test_setup_wizard(adb, ui, config)
        results.append(result)
        all_screenshots.extend(result.screenshots)
        if result.result != TestResult.PASSED:
            return TestReport(
                name="test_full_flow",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"Failed at setup: {result.message}",
                screenshots=all_screenshots,
            )

        # 4. Chat Interaction
        print("\n[Step 4/4] Chat Interaction")
        result = test_chat_interaction(adb, ui, config)
        results.append(result)
        all_screenshots.extend(result.screenshots)
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
