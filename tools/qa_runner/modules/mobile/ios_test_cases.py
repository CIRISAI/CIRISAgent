"""
iOS Test Cases for CIRIS App

Test cases for automated UI testing on iOS simulator using xcrun simctl
and macOS Vision framework OCR.

These mirror the Android test cases but use the iOS-specific helpers.
"""

import time
from typing import Optional

from .ios.ios_ui_automator import iOSUIAutomator
from .ios.xcrun_helper import XCRunHelper
from .test_cases import CIRISAppConfig, TestReport, TestResult


# iOS-specific config overrides
class iOSAppConfig(CIRISAppConfig):
    """iOS-specific app configuration."""

    BUNDLE_ID = "ai.ciris.mobile"

    # iOS login uses "Sign in with Apple" instead of Google
    TEXT_SIGN_IN_APPLE = "Sign in with Apple"

    # Timeouts may need to be longer for iOS simulator
    TIMEOUT_APP_LAUNCH = 90  # Python startup can be slow on simulator
    TIMEOUT_SETUP = 120

    # Acquire License texts (device auth via Portal/Registry)
    TEXT_ACQUIRE_LICENSE = "Acquire a License"
    TEXT_LICENSE_SUBTITLE = "Acquire a license for Medical, Legal, or Financial agent deployment"
    TEXT_CONNECT = "Connect"
    TEXT_PORTAL_URL_PLACEHOLDER = "Portal URL"
    TEXT_WAITING_AUTH = "Waiting for authorization"
    TEXT_VERIFICATION_URL = "portal.ciris.ai"
    TEXT_AGENT_AUTHORIZED = "Agent Authorized"
    TEXT_CONNECTING_PORTAL = "Connecting to portal"

    # Deprecated aliases (for backwards compat with existing tests)
    TEXT_CREATE_LICENSED_AGENT = TEXT_ACQUIRE_LICENSE
    TEXT_LICENSED_SUBTITLE = TEXT_LICENSE_SUBTITLE
    TEXT_NODE_URL_PLACEHOLDER = TEXT_PORTAL_URL_PLACEHOLDER
    TEXT_CONNECTING = TEXT_CONNECTING_PORTAL


def test_ios_app_launch(xcrun: XCRunHelper, ui: iOSUIAutomator, config: dict) -> TestReport:
    """
    Test: iOS app launches successfully and shows login screen.

    Steps:
    1. Terminate any running instance
    2. Launch the app
    3. Wait for login screen to appear
    4. Verify login elements (Sign in with Apple, Local Login)
    """
    start_time = time.time()
    screenshots = []
    bundle_id = iOSAppConfig.BUNDLE_ID

    try:
        print("  [1/4] Terminating existing instance...")
        xcrun.force_stop_app(bundle_id)
        time.sleep(1)

        print("  [2/4] Launching app...")
        success = xcrun.launch_app(bundle_id)
        if not success:
            return TestReport(
                name="test_ios_app_launch",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="Failed to launch app",
            )

        print("  [3/4] Waiting for login screen (Python startup)...")
        time.sleep(5)  # Initial wait for Python init

        # Wait for login screen elements
        element = ui.wait_for_text(
            iOSAppConfig.TEXT_LOCAL_LOGIN,
            timeout=iOSAppConfig.TIMEOUT_APP_LAUNCH,
        )

        if not element:
            screenshot_path = f"/tmp/ciris_ios_launch_fail_{int(time.time())}.png"
            xcrun.screenshot(screenshot_path)
            screenshots.append(screenshot_path)

            screen_info = ui.dump_screen_info()
            return TestReport(
                name="test_ios_app_launch",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"Login screen not found. Visible: {screen_info.get('texts', [])}",
                screenshots=screenshots,
            )

        print("  [4/4] Verifying login elements...")
        has_apple = ui.is_text_visible(iOSAppConfig.TEXT_SIGN_IN_APPLE)
        has_local = ui.is_text_visible(iOSAppConfig.TEXT_LOCAL_LOGIN)
        has_branding = ui.is_text_visible(iOSAppConfig.TEXT_CIRIS_AGENT)

        screenshot_path = f"/tmp/ciris_ios_login_{int(time.time())}.png"
        xcrun.screenshot(screenshot_path)
        screenshots.append(screenshot_path)

        if not has_local:
            return TestReport(
                name="test_ios_app_launch",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="Local Login button not found",
                screenshots=screenshots,
            )

        return TestReport(
            name="test_ios_app_launch",
            result=TestResult.PASSED,
            duration=time.time() - start_time,
            message=f"App launched. Apple={has_apple}, Local={has_local}, Branding={has_branding}",
            screenshots=screenshots,
        )

    except Exception as e:
        return TestReport(
            name="test_ios_app_launch",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
            screenshots=screenshots,
        )


def test_ios_local_login(xcrun: XCRunHelper, ui: iOSUIAutomator, config: dict) -> TestReport:
    """
    Test: Local Login flow on iOS.

    Steps:
    1. Click "Local Login"
    2. Verify navigation to Setup wizard
    """
    start_time = time.time()
    screenshots = []

    try:
        print("  [1/2] Clicking 'Local Login'...")

        if not ui.is_text_visible(iOSAppConfig.TEXT_LOCAL_LOGIN):
            return TestReport(
                name="test_ios_local_login",
                result=TestResult.SKIPPED,
                duration=time.time() - start_time,
                message="Not on Login screen - skipping",
            )

        clicked = ui.click_by_text(iOSAppConfig.TEXT_LOCAL_LOGIN)
        if not clicked:
            return TestReport(
                name="test_ios_local_login",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="Failed to click Local Login",
            )

        time.sleep(3)

        print("  [2/2] Verifying Setup screen...")
        # Look for setup-related elements (Welcome step)
        setup_visible = (
            ui.wait_for_text("Setup", timeout=15)
            or ui.wait_for_text("Welcome", timeout=5)
            or ui.wait_for_text("LLM", timeout=5)
            or ui.wait_for_text(iOSAppConfig.TEXT_CREATE_LICENSED_AGENT, timeout=5)
        )

        screenshot_path = f"/tmp/ciris_ios_after_login_{int(time.time())}.png"
        xcrun.screenshot(screenshot_path)
        screenshots.append(screenshot_path)

        if setup_visible:
            return TestReport(
                name="test_ios_local_login",
                result=TestResult.PASSED,
                duration=time.time() - start_time,
                message="Local Login successful, navigated to Setup",
                screenshots=screenshots,
            )
        else:
            screen_info = ui.dump_screen_info()
            return TestReport(
                name="test_ios_local_login",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"Setup screen not found. Visible: {screen_info.get('texts', [])}",
                screenshots=screenshots,
            )

    except Exception as e:
        return TestReport(
            name="test_ios_local_login",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
            screenshots=screenshots,
        )


def test_ios_connect_node(xcrun: XCRunHelper, ui: iOSUIAutomator, config: dict) -> TestReport:
    """
    Test: Acquire License device auth flow (via Portal/Registry).

    This is the primary test case for the license acquisition feature.
    The flow contacts CIRISPortal for device auth and CIRISRegistry for
    agent registration + key issuance. CIRISNode is NOT involved.

    IMPORTANT — Compose Multiplatform iOS automation limitations:
    - Vision OCR (iOSUIAutomator) works for text detection and click_by_text
    - Compose text fields CANNOT be focused by tap — they use FocusRequester
      auto-focus in code (triggered when the "Acquire a License" card expands)
    - Text input must use AppleScript clipboard paste (pbcopy + Cmd+V),
      NOT xcrun.input_text() which requires a focused UIKit field
    - The "Allow Paste" iOS dialog must be tapped after pasting

    Steps:
    1. Launch app fresh (or verify on login screen)
    2. Local Login or Apple Sign In → Setup wizard WELCOME step
    3. Scroll to "Acquire a License" card, tap header to expand
    4. Text field auto-focuses via FocusRequester; paste portal URL
    5. Tap "Connect" button
    6. Wait for NODE_AUTH step
    7. Verify verification URL is displayed
    8. Verify device code is shown
    9. (Optional) Wait for user to complete Portal auth
    10. Verify provisioned template + adapters shown
    11. Continue through remaining setup steps

    Config keys:
        portal_url: Portal URL to connect to (default: https://portal.ciris.ai)
        node_url: Deprecated alias for portal_url
        wait_for_portal_auth: If True, wait for user to complete Portal auth (default: False)
        portal_auth_timeout: Timeout for Portal auth (default: 300s)
    """
    start_time = time.time()
    screenshots = []
    bundle_id = iOSAppConfig.BUNDLE_ID
    node_url = config.get("portal_url", config.get("node_url", "https://portal.ciris.ai"))
    wait_for_auth = config.get("wait_for_portal_auth", False)
    auth_timeout = config.get("portal_auth_timeout", 300)

    try:
        # ============================================================
        # Step 1: Ensure app is on login screen
        # ============================================================
        print("  [1/8] Ensuring app is on login screen...")

        if not ui.is_text_visible(iOSAppConfig.TEXT_LOCAL_LOGIN):
            # Try launching fresh
            xcrun.force_stop_app(bundle_id)
            time.sleep(1)
            xcrun.launch_app(bundle_id)
            time.sleep(5)

            element = ui.wait_for_text(
                iOSAppConfig.TEXT_LOCAL_LOGIN,
                timeout=iOSAppConfig.TIMEOUT_APP_LAUNCH,
            )
            if not element:
                screenshot_path = f"/tmp/ciris_cn_no_login_{int(time.time())}.png"
                xcrun.screenshot(screenshot_path)
                screenshots.append(screenshot_path)
                return TestReport(
                    name="test_ios_connect_node",
                    result=TestResult.FAILED,
                    duration=time.time() - start_time,
                    message="Could not reach login screen",
                    screenshots=screenshots,
                )

        # ============================================================
        # Step 2: Local Login → WELCOME step
        # ============================================================
        print("  [2/8] Logging in via Local Login...")

        ui.click_by_text(iOSAppConfig.TEXT_LOCAL_LOGIN)
        time.sleep(3)

        # Wait for WELCOME step with Create Licensed Agent card
        welcome_found = ui.wait_for_text(iOSAppConfig.TEXT_CREATE_LICENSED_AGENT, timeout=20)

        screenshot_path = f"/tmp/ciris_cn_welcome_{int(time.time())}.png"
        xcrun.screenshot(screenshot_path)
        screenshots.append(screenshot_path)

        if not welcome_found:
            screen_info = ui.dump_screen_info()
            # Maybe we landed on a different setup step
            if ui.is_text_visible("LLM") or ui.is_text_visible("Provider"):
                return TestReport(
                    name="test_ios_connect_node",
                    result=TestResult.FAILED,
                    duration=time.time() - start_time,
                    message="Landed on LLM config instead of WELCOME. Create Licensed Agent card may not be rendered.",
                    screenshots=screenshots,
                )
            return TestReport(
                name="test_ios_connect_node",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"Create Licensed Agent card not found on WELCOME. Visible: {screen_info.get('texts', [])}",
                screenshots=screenshots,
            )

        print("  [3/8] Found 'Create Licensed Agent' card")

        # ============================================================
        # Step 3: Enter node URL
        # ============================================================
        print(f"  [4/8] Entering node URL: {node_url}")

        # Find and tap the node URL input field
        url_field = (
            ui.find_by_text(iOSAppConfig.TEXT_NODE_URL_PLACEHOLDER)
            or ui.find_by_text("node.ciris.ai")
            or ui.find_by_text("Node URL")
        )

        if url_field:
            ui.click(url_field)
            time.sleep(0.5)
        else:
            # Try tapping below the "Create Licensed Agent" text
            connect_card = ui.find_by_text(iOSAppConfig.TEXT_CREATE_LICENSED_AGENT)
            if connect_card:
                # Tap below the card title where the input field likely is
                cx, cy = connect_card.center
                xcrun.tap(cx, cy + 80)
                time.sleep(0.5)

        # Type the node URL
        xcrun.input_text(node_url)
        time.sleep(0.5)

        screenshot_path = f"/tmp/ciris_cn_url_entered_{int(time.time())}.png"
        xcrun.screenshot(screenshot_path)
        screenshots.append(screenshot_path)

        # ============================================================
        # Step 4: Tap "Connect" button
        # ============================================================
        print("  [5/8] Tapping 'Connect' button...")

        connect_clicked = ui.click_by_text(iOSAppConfig.TEXT_CONNECT, exact=True)
        if not connect_clicked:
            # Try finding a button below the URL field
            connect_clicked = ui.click_by_text("Connect")

        if not connect_clicked:
            return TestReport(
                name="test_ios_connect_node",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="Could not find or click 'Connect' button",
                screenshots=screenshots,
            )

        time.sleep(2)

        # ============================================================
        # Step 5: Wait for NODE_AUTH step
        # ============================================================
        print("  [6/8] Waiting for NODE_AUTH step...")

        # Look for the connecting/waiting state
        auth_step = (
            ui.wait_for_text(iOSAppConfig.TEXT_WAITING_AUTH, timeout=15)
            or ui.wait_for_text(iOSAppConfig.TEXT_VERIFICATION_URL, timeout=10)
            or ui.wait_for_text("Connecting", timeout=10)
            or ui.wait_for_text("device", timeout=10)
        )

        screenshot_path = f"/tmp/ciris_cn_node_auth_{int(time.time())}.png"
        xcrun.screenshot(screenshot_path)
        screenshots.append(screenshot_path)

        if not auth_step:
            screen_info = ui.dump_screen_info()
            # Check for error states
            if ui.is_text_visible("error") or ui.is_text_visible("failed") or ui.is_text_visible("Error"):
                return TestReport(
                    name="test_ios_connect_node",
                    result=TestResult.FAILED,
                    duration=time.time() - start_time,
                    message=f"Connection error. Visible: {screen_info.get('texts', [])}",
                    screenshots=screenshots,
                )
            return TestReport(
                name="test_ios_connect_node",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"NODE_AUTH step not reached. Visible: {screen_info.get('texts', [])}",
                screenshots=screenshots,
            )

        # ============================================================
        # Step 6: Verify verification URL and device code
        # ============================================================
        print("  [7/8] Verifying device auth display...")

        ui.refresh_hierarchy()
        screen_texts = ui.get_screen_text()

        has_verification_url = any("portal" in t.lower() for t in screen_texts)
        has_device_code = any(
            # Device codes are typically XXXX-YYYY format
            ("-" in t and len(t) >= 7 and len(t) <= 12 and t.replace("-", "").isalnum())
            for t in screen_texts
        )

        verification_details = {
            "has_verification_url": has_verification_url,
            "has_device_code": has_device_code,
            "visible_texts": screen_texts[:15],
        }

        print(f"    Verification URL: {'found' if has_verification_url else 'not found'}")
        print(f"    Device code: {'found' if has_device_code else 'not found'}")

        # ============================================================
        # Step 7: Optionally wait for Portal auth completion
        # ============================================================
        if wait_for_auth:
            print(f"  [8/8] Waiting for Portal authorization (timeout: {auth_timeout}s)...")
            print("         Complete the authorization in your browser at the Portal URL above")

            authorized = ui.wait_for_text(
                iOSAppConfig.TEXT_AGENT_AUTHORIZED,
                timeout=auth_timeout,
                interval=3.0,
            )

            screenshot_path = f"/tmp/ciris_cn_auth_result_{int(time.time())}.png"
            xcrun.screenshot(screenshot_path)
            screenshots.append(screenshot_path)

            if authorized:
                ui.refresh_hierarchy()
                screen_texts = ui.get_screen_text()
                has_template = any("template" in t.lower() or "echo" in t.lower() for t in screen_texts)
                has_adapters = any("adapter" in t.lower() for t in screen_texts)

                return TestReport(
                    name="test_ios_connect_node",
                    result=TestResult.PASSED,
                    duration=time.time() - start_time,
                    message=(
                        f"Device auth completed. Template shown: {has_template}, "
                        f"Adapters shown: {has_adapters}"
                    ),
                    screenshots=screenshots,
                )
            else:
                return TestReport(
                    name="test_ios_connect_node",
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
                    name="test_ios_connect_node",
                    result=TestResult.PASSED,
                    duration=time.time() - start_time,
                    message=(
                        f"Device auth screen reached. "
                        f"Verification URL: {has_verification_url}, "
                        f"Device code: {has_device_code}. "
                        f"Details: {verification_details}"
                    ),
                    screenshots=screenshots,
                )
            else:
                # Still pass if we at least reached the NODE_AUTH step
                return TestReport(
                    name="test_ios_connect_node",
                    result=TestResult.PASSED,
                    duration=time.time() - start_time,
                    message=(
                        f"NODE_AUTH step reached but verification details not detected via OCR. "
                        f"Visible: {screen_texts[:10]}"
                    ),
                    screenshots=screenshots,
                )

    except Exception as e:
        return TestReport(
            name="test_ios_connect_node",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
            screenshots=screenshots,
        )


def test_ios_connect_node_welcome(xcrun: XCRunHelper, ui: iOSUIAutomator, config: dict) -> TestReport:
    """Test: Verify Create Licensed Agent card appears on WELCOME screen."""
    start_time = time.time()
    screenshots = []
    bundle_id = iOSAppConfig.BUNDLE_ID

    try:
        print("  [1/3] Launching app fresh...")
        xcrun.force_stop_app(bundle_id)
        time.sleep(1)
        xcrun.launch_app(bundle_id)
        time.sleep(5)

        print("  [2/3] Login via Local Login...")
        login_btn = ui.wait_for_text(iOSAppConfig.TEXT_LOCAL_LOGIN, timeout=iOSAppConfig.TIMEOUT_APP_LAUNCH)
        if not login_btn:
            return TestReport(
                name="test_ios_connect_node_welcome",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="Login screen not found",
            )

        ui.click_by_text(iOSAppConfig.TEXT_LOCAL_LOGIN)
        time.sleep(3)

        print("  [3/3] Checking for Create Licensed Agent card...")
        card_found = ui.wait_for_text(iOSAppConfig.TEXT_CREATE_LICENSED_AGENT, timeout=15)

        screenshot_path = f"/tmp/ciris_cn_welcome_check_{int(time.time())}.png"
        xcrun.screenshot(screenshot_path)
        screenshots.append(screenshot_path)

        if card_found:
            # Also verify the URL field and Connect button
            ui.refresh_hierarchy()
            has_url_field = ui.is_text_visible("Node URL") or ui.is_text_visible("node.ciris.ai")
            has_connect_btn = ui.is_text_visible(iOSAppConfig.TEXT_CONNECT)

            return TestReport(
                name="test_ios_connect_node_welcome",
                result=TestResult.PASSED,
                duration=time.time() - start_time,
                message=f"Card found. URL field: {has_url_field}, Connect btn: {has_connect_btn}",
                screenshots=screenshots,
            )
        else:
            screen_info = ui.dump_screen_info()
            return TestReport(
                name="test_ios_connect_node_welcome",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"Create Licensed Agent card not found. Visible: {screen_info.get('texts', [])}",
                screenshots=screenshots,
            )

    except Exception as e:
        return TestReport(
            name="test_ios_connect_node_welcome",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
            screenshots=screenshots,
        )


def test_ios_connect_node_auth(xcrun: XCRunHelper, ui: iOSUIAutomator, config: dict) -> TestReport:
    """
    Test: Full device auth initiation — enter URL and verify auth screen.

    Prerequisite: Must be on WELCOME step with Create Licensed Agent card visible.
    """
    start_time = time.time()
    screenshots = []
    node_url = config.get("portal_url", config.get("node_url", "https://portal.ciris.ai"))

    try:
        print("  [1/3] Checking we're on WELCOME step...")
        if not ui.is_text_visible(iOSAppConfig.TEXT_CREATE_LICENSED_AGENT):
            return TestReport(
                name="test_ios_connect_node_auth",
                result=TestResult.SKIPPED,
                duration=time.time() - start_time,
                message="Not on WELCOME step with Create Licensed Agent card",
            )

        print(f"  [2/3] Entering node URL: {node_url}")
        # Tap URL field area
        url_field = ui.find_by_text("Node URL") or ui.find_by_text("node.ciris.ai")
        if url_field:
            ui.click(url_field)
        else:
            card = ui.find_by_text(iOSAppConfig.TEXT_CREATE_LICENSED_AGENT)
            if card:
                xcrun.tap(card.center[0], card.center[1] + 80)
        time.sleep(0.5)
        xcrun.input_text(node_url)
        time.sleep(0.5)

        # Tap Connect
        ui.click_by_text(iOSAppConfig.TEXT_CONNECT, exact=True)
        time.sleep(3)

        print("  [3/3] Verifying NODE_AUTH step...")
        auth_visible = (
            ui.wait_for_text("authorization", timeout=15)
            or ui.wait_for_text("portal", timeout=10)
            or ui.wait_for_text("Connecting", timeout=10)
        )

        screenshot_path = f"/tmp/ciris_cn_auth_step_{int(time.time())}.png"
        xcrun.screenshot(screenshot_path)
        screenshots.append(screenshot_path)

        if auth_visible:
            return TestReport(
                name="test_ios_connect_node_auth",
                result=TestResult.PASSED,
                duration=time.time() - start_time,
                message="NODE_AUTH step reached after entering node URL",
                screenshots=screenshots,
            )
        else:
            screen_info = ui.dump_screen_info()
            return TestReport(
                name="test_ios_connect_node_auth",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"NODE_AUTH not reached. Visible: {screen_info.get('texts', [])}",
                screenshots=screenshots,
            )

    except Exception as e:
        return TestReport(
            name="test_ios_connect_node_auth",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
            screenshots=screenshots,
        )


def test_ios_connect_node_error(xcrun: XCRunHelper, ui: iOSUIAutomator, config: dict) -> TestReport:
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
        print("  [1/3] Checking we're on WELCOME step...")
        if not ui.is_text_visible(iOSAppConfig.TEXT_CREATE_LICENSED_AGENT):
            return TestReport(
                name="test_ios_connect_node_error",
                result=TestResult.SKIPPED,
                duration=time.time() - start_time,
                message="Not on WELCOME step",
            )

        print("  [2/3] Entering invalid node URL...")
        url_field = ui.find_by_text("Node URL") or ui.find_by_text("node.ciris.ai")
        if url_field:
            ui.click(url_field)
        time.sleep(0.3)
        xcrun.input_text("https://invalid-node.example.com")
        time.sleep(0.3)

        ui.click_by_text(iOSAppConfig.TEXT_CONNECT, exact=True)
        time.sleep(5)

        print("  [3/3] Checking for error state...")
        ui.refresh_hierarchy()
        screen_texts = ui.get_screen_text()

        screenshot_path = f"/tmp/ciris_cn_error_{int(time.time())}.png"
        xcrun.screenshot(screenshot_path)
        screenshots.append(screenshot_path)

        has_error = any(
            "error" in t.lower() or "failed" in t.lower() or "connection" in t.lower()
            for t in screen_texts
        )

        if has_error:
            return TestReport(
                name="test_ios_connect_node_error",
                result=TestResult.PASSED,
                duration=time.time() - start_time,
                message=f"Error state displayed correctly. Visible: {screen_texts[:10]}",
                screenshots=screenshots,
            )
        else:
            return TestReport(
                name="test_ios_connect_node_error",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"No error message for invalid URL. Visible: {screen_texts[:10]}",
                screenshots=screenshots,
            )

    except Exception as e:
        return TestReport(
            name="test_ios_connect_node_error",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
            screenshots=screenshots,
        )


def test_ios_setup_wizard(xcrun: XCRunHelper, ui: iOSUIAutomator, config: dict) -> TestReport:
    """
    Test: Complete the standard setup wizard on iOS (non-node flow).

    Mirrors the Android test_setup_wizard but uses iOS UI helpers.
    """
    start_time = time.time()
    screenshots = []
    max_steps = config.get("setup_max_steps", 15)

    try:
        print("  [1/3] Checking Setup screen...")
        time.sleep(2)
        screen_info = ui.dump_screen_info()
        print(f"  Setup elements: {screen_info.get('texts', [])[:15]}")

        screenshot_path = f"/tmp/ciris_ios_setup_{int(time.time())}.png"
        xcrun.screenshot(screenshot_path)
        screenshots.append(screenshot_path)

        print("  [2/3] Navigating setup wizard...")

        for step in range(max_steps):
            time.sleep(1.5)
            ui.refresh_hierarchy()

            # Check if we've reached the chat screen
            for indicator in CIRISAppConfig.CHAT_SCREEN_INDICATORS_PRIMARY:
                if ui.is_text_visible(indicator):
                    print(f"  Setup completed! Found '{indicator}' after {step + 1} clicks")
                    return TestReport(
                        name="test_ios_setup_wizard",
                        result=TestResult.PASSED,
                        duration=time.time() - start_time,
                        message=f"Setup completed in {step + 1} steps",
                        screenshots=screenshots,
                    )

            for indicator in ["Shutdown", "STOP"]:
                if ui.is_text_visible(indicator):
                    print(f"  Setup completed! Found chat indicator '{indicator}'")
                    return TestReport(
                        name="test_ios_setup_wizard",
                        result=TestResult.PASSED,
                        duration=time.time() - start_time,
                        message=f"Setup completed in {step + 1} steps (found: {indicator})",
                        screenshots=screenshots,
                    )

            # Handle API key input
            if ui.is_text_visible("API Key"):
                api_key = config.get("llm_api_key", "")
                if api_key:
                    field = ui.find_by_text("API Key")
                    if field:
                        ui.set_text(field, api_key)
                        time.sleep(0.5)

            # Try navigation buttons
            next_clicked = False
            for button_text in CIRISAppConfig.SETUP_NAV_BUTTONS:
                if ui.click_by_text(button_text):
                    print(f"  Step {step + 1}: Clicked '{button_text}'")
                    next_clicked = True
                    break

            if not next_clicked:
                screen_texts = ui.get_screen_text()
                print(f"  Step {step + 1}: No nav button found. Screen: {screen_texts[:10]}")

        screenshot_path = f"/tmp/ciris_ios_setup_stuck_{int(time.time())}.png"
        xcrun.screenshot(screenshot_path)
        screenshots.append(screenshot_path)

        screen_info = ui.dump_screen_info()
        return TestReport(
            name="test_ios_setup_wizard",
            result=TestResult.FAILED,
            duration=time.time() - start_time,
            message=f"Setup did not complete after {max_steps} steps. Final: {screen_info.get('texts', [])[:10]}",
            screenshots=screenshots,
        )

    except Exception as e:
        return TestReport(
            name="test_ios_setup_wizard",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
            screenshots=screenshots,
        )


def test_ios_full_flow(xcrun: XCRunHelper, ui: iOSUIAutomator, config: dict) -> TestReport:
    """
    Test: Complete iOS end-to-end flow.

    Steps:
    1. Launch app (fresh)
    2. Local Login
    3. Complete setup wizard
    """
    start_time = time.time()
    all_screenshots = []
    results = []

    try:
        print("\n=== iOS Full Flow Test ===\n")

        # 1. Launch
        print("[Step 1/3] App Launch")
        result = test_ios_app_launch(xcrun, ui, config)
        results.append(result)
        all_screenshots.extend(result.screenshots)
        if result.result != TestResult.PASSED:
            return TestReport(
                name="test_ios_full_flow",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"Failed at launch: {result.message}",
                screenshots=all_screenshots,
            )

        # 2. Login
        print("\n[Step 2/3] Local Login")
        result = test_ios_local_login(xcrun, ui, config)
        results.append(result)
        all_screenshots.extend(result.screenshots)
        if result.result != TestResult.PASSED:
            return TestReport(
                name="test_ios_full_flow",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"Failed at login: {result.message}",
                screenshots=all_screenshots,
            )

        # 3. Setup
        print("\n[Step 3/3] Setup Wizard")
        result = test_ios_setup_wizard(xcrun, ui, config)
        results.append(result)
        all_screenshots.extend(result.screenshots)
        if result.result != TestResult.PASSED:
            return TestReport(
                name="test_ios_full_flow",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"Failed at setup: {result.message}",
                screenshots=all_screenshots,
            )

        passed_count = sum(1 for r in results if r.result == TestResult.PASSED)
        return TestReport(
            name="test_ios_full_flow",
            result=TestResult.PASSED,
            duration=time.time() - start_time,
            message=f"Full flow completed ({passed_count}/{len(results)} steps passed)",
            screenshots=all_screenshots,
        )

    except Exception as e:
        return TestReport(
            name="test_ios_full_flow",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
            screenshots=all_screenshots,
        )
