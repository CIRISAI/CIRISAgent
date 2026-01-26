"""
Mobile QA Runner CLI entry point.

Usage:
    python -m tools.qa_runner.modules.mobile [command] [options]

Commands:
    test [tests]      - Run UI automation tests (default)
    pull-logs         - Pull device logs and files for debugging
    go-screen         - Navigate to a specific app screen and take a screenshot

Examples:
    # Run full flow test with test account
    python -m tools.qa_runner.modules.mobile test full_flow --email ciristest1@gmail.com

    # Run just app launch test
    python -m tools.qa_runner.modules.mobile test app_launch

    # Run with specific device
    python -m tools.qa_runner.modules.mobile test full_flow -d emulator-5554

    # Pull device logs
    python -m tools.qa_runner.modules.mobile pull-logs
    python -m tools.qa_runner.modules.mobile pull-logs -d R5CRC3BWLRZ -o ./my_logs

    # Navigate to a screen and take screenshot
    python -m tools.qa_runner.modules.mobile go-screen billing
    python -m tools.qa_runner.modules.mobile go-screen telemetry -o ./screenshots
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from tools.qa_runner.modules.mobile.adb_helper import ADBHelper
from tools.qa_runner.modules.mobile.test_runner import MobileTestConfig, MobileTestRunner
from tools.qa_runner.modules.mobile.ui_automator import UIAutomator

# ========== Screen Registry ==========
# Extensible registry of app screens and how to navigate to them
# Format: screen_name -> (menu_text, content_desc, description)
# menu_text: Text to click in the overflow menu (Settings/Telemetry/etc.)
# content_desc: Content description to find (for hamburger menu items)
# description: Human-readable description of the screen

SCREEN_REGISTRY: Dict[str, Tuple[str, Optional[str], str]] = {
    "interact": (None, None, "Main chat/interaction screen (default)"),
    "settings": ("Settings", "Settings", "App settings screen"),
    "billing": ("Buy Credits", "Buy Credits", "Purchase credits screen"),
    "telemetry": ("Telemetry", "Telemetry", "System telemetry/metrics screen"),
    "sessions": ("Sessions", "Sessions", "Active sessions screen"),
    "adapters": ("Adapters", "Adapters", "Adapter management screen"),
    "wise_authority": ("Wise Authority", "Wise Authority", "Wise Authority deferrals screen"),
    "services": ("Services", "Services", "Service status management screen"),
    "runtime": ("Runtime", "Runtime", "Runtime control panel screen"),
}


def register_screen(name: str, menu_text: Optional[str], content_desc: Optional[str], description: str) -> None:
    """
    Register a new screen for go-screen navigation.

    Args:
        name: Short name for the screen (used as CLI argument)
        menu_text: Text to click in the menu to navigate to this screen
        content_desc: Content description of the menu item (alternative to text)
        description: Human-readable description
    """
    SCREEN_REGISTRY[name] = (menu_text, content_desc, description)


def load_secret_file(path: str) -> str:
    """Load secret from file, stripping whitespace."""
    expanded = os.path.expanduser(path)
    if os.path.exists(expanded):
        with open(expanded) as f:
            return f.read().strip()
    return ""


def pull_logs_command(args) -> int:
    """Handle the pull-logs subcommand."""
    print("\n" + "=" * 60)
    print("CIRIS Mobile Device Log Collector")
    print("=" * 60 + "\n")

    try:
        adb = ADBHelper(adb_path=args.adb_path, device_serial=args.device)
    except Exception as e:
        print(f"[ERROR] Failed to initialize ADB: {e}")
        return 1

    # Check device connection
    devices = adb.get_devices()
    connected = [d for d in devices if d.state == "device"]

    if not connected:
        print("[ERROR] No devices connected")
        return 1

    if args.device:
        device = next((d for d in connected if d.serial == args.device), None)
        if not device:
            print(f"[ERROR] Device {args.device} not found")
            print(f"  Available: {[d.serial for d in connected]}")
            return 1
    else:
        device = connected[0]
        if len(connected) > 1:
            print(f"[INFO] Multiple devices found, using: {device.serial}")
            print(f"  Use -d to specify: {[d.serial for d in connected]}")

    print(f"[INFO] Device: {device.serial} ({device.model or 'unknown model'})")

    # Pull logs
    results = adb.pull_device_logs(output_dir=args.output_dir, package=args.package, verbose=True)

    # Print quick analysis hints
    print("\nQuick analysis:")
    print(f"  grep -i error {results['output_dir']}/logs/incidents_latest.log")
    print(f"  tail -100 {results['output_dir']}/logs/latest.log")
    print(f"  cat {results['output_dir']}/logcat_app.txt | grep -i 'EnvFileUpdater\\|billing\\|token'")

    return 0


def go_screen_command(args) -> int:
    """Handle the go-screen subcommand."""
    print("\n" + "=" * 60)
    print("CIRIS Mobile Screen Navigator")
    print("=" * 60 + "\n")

    screen_name = args.screen.lower()

    # Validate screen name
    if screen_name not in SCREEN_REGISTRY:
        print(f"[ERROR] Unknown screen: {screen_name}")
        print("\nAvailable screens:")
        for name, (_, _, desc) in SCREEN_REGISTRY.items():
            print(f"  {name:15} - {desc}")
        return 1

    menu_text, content_desc, description = SCREEN_REGISTRY[screen_name]
    print(f"[INFO] Navigating to: {screen_name} ({description})")

    try:
        adb = ADBHelper(adb_path=args.adb_path, device_serial=args.device)
    except Exception as e:
        print(f"[ERROR] Failed to initialize ADB: {e}")
        return 1

    # Check device connection
    devices = adb.get_devices()
    connected = [d for d in devices if d.state == "device"]

    if not connected:
        print("[ERROR] No devices connected")
        return 1

    if args.device:
        device = next((d for d in connected if d.serial == args.device), None)
        if not device:
            print(f"[ERROR] Device {args.device} not found")
            print(f"  Available: {[d.serial for d in connected]}")
            return 1
    else:
        device = connected[0]
        if len(connected) > 1:
            print(f"[INFO] Multiple devices found, using: {device.serial}")

    print(f"[INFO] Device: {device.serial} ({device.model or 'unknown model'})")

    # Initialize UI Automator
    ui = UIAutomator(adb)

    # Ensure app is in foreground
    package = args.package
    print(f"[INFO] Bringing {package} to foreground...")
    adb._run_adb(["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"])
    time.sleep(2)

    # Navigate to the screen
    if screen_name == "interact":
        # Already on interact screen by default after app launch
        print("[INFO] Already on interact screen (default)")
    else:
        # Need to open overflow menu and click the screen item
        print(f"[INFO] Opening overflow menu...")

        # First try to click "More options" (three dots menu) or "More" text
        ui.refresh_hierarchy()

        # Look for overflow menu button (could be "More options", "More", "MoreVert", etc.)
        overflow_clicked = False
        overflow_options = ["More options", "MoreVert", "overflow", "More"]

        for option in overflow_options:
            element = ui.find_by_content_desc(option, exact=False)
            if element:
                print(f"[INFO] Found overflow menu by content_desc: {option}")
                ui.click(element)
                overflow_clicked = True
                time.sleep(0.5)
                break

        if not overflow_clicked:
            # Try by text (some UIs show "More" as text)
            element = ui.find_by_text("More", exact=True)
            if element:
                print("[INFO] Found overflow menu by text: More")
                ui.click(element)
                overflow_clicked = True
                time.sleep(0.5)

        if not overflow_clicked:
            # Try finding by clickable icon in the top bar area
            elements = ui.get_elements(refresh=True)
            for elem in elements:
                if elem.clickable and elem.bounds[1] < 200:  # Top bar area
                    if "more" in elem.content_desc.lower() or "option" in elem.content_desc.lower():
                        print(f"[INFO] Found potential overflow: {elem.content_desc}")
                        ui.click(elem)
                        overflow_clicked = True
                        time.sleep(0.5)
                        break

        if not overflow_clicked:
            print("[WARN] Could not find overflow menu, trying direct navigation...")

        # Wait for menu to appear and click target
        time.sleep(0.5)
        ui.refresh_hierarchy()

        target_clicked = False

        # Try clicking by text first
        if menu_text:
            element = ui.find_by_text(menu_text, exact=False)
            if element:
                print(f"[INFO] Found menu item by text: {menu_text}")
                ui.click(element)
                target_clicked = True
                time.sleep(1)

        # Try content description if text didn't work
        if not target_clicked and content_desc:
            element = ui.find_by_content_desc(content_desc, exact=False)
            if element:
                print(f"[INFO] Found menu item by content_desc: {content_desc}")
                ui.click(element)
                target_clicked = True
                time.sleep(1)

        # If still not found, the menu might need to be expanded - try clicking "More" submenu
        if not target_clicked:
            print("[INFO] Target not found, trying to expand 'More' submenu...")
            more_element = ui.find_by_text("More", exact=True)
            if more_element:
                print("[INFO] Clicking 'More' to expand submenu")
                ui.click(more_element)
                time.sleep(0.5)
                ui.refresh_hierarchy()

                # Now try again
                if menu_text:
                    element = ui.find_by_text(menu_text, exact=False)
                    if element:
                        print(f"[INFO] Found menu item in submenu by text: {menu_text}")
                        ui.click(element)
                        target_clicked = True
                        time.sleep(1)

                if not target_clicked and content_desc:
                    element = ui.find_by_content_desc(content_desc, exact=False)
                    if element:
                        print(f"[INFO] Found menu item in submenu by content_desc: {content_desc}")
                        ui.click(element)
                        target_clicked = True
                        time.sleep(1)

        if not target_clicked:
            print(f"[ERROR] Could not find menu item for screen: {screen_name}")
            print("[DEBUG] Available text on screen:")
            screen_texts = ui.get_screen_text()
            for text in screen_texts[:20]:  # First 20 items
                print(f"  - {text}")
            return 1

    # Wait for screen to load
    time.sleep(1)

    # Take screenshot
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_path = output_dir / f"screen_{screen_name}_{timestamp}.png"

    print(f"[INFO] Taking screenshot...")
    if adb.screenshot(str(screenshot_path)):
        print(f"[SUCCESS] Screenshot saved: {screenshot_path}")
        # Print absolute path for easy access
        print(f"[PATH] {screenshot_path.absolute()}")
    else:
        print(f"[ERROR] Failed to take screenshot")
        return 1

    return 0


def test_command(args) -> int:
    """Handle the test subcommand."""
    print("\n" + "=" * 60)
    print("CIRIS Mobile QA Runner")
    print("=" * 60)

    # Build APK if requested
    if args.build:
        print("\nBuilding APK...")
        import subprocess

        result = subprocess.run(
            ["./gradlew", ":androidApp:assembleDebug"],
            cwd=Path(__file__).parent.parent.parent.parent.parent / "mobile",
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"Build failed:\n{result.stderr}")
            return 1
        print("Build successful!")

    # Load secrets from files
    test_password = load_secret_file(args.password_file)
    llm_api_key = args.llm_key or load_secret_file(args.llm_key_file)

    if not test_password:
        print(f"\nNote: No password file found at {args.password_file}")
        print("      Google Sign-In will rely on pre-authenticated account on device")

    if not llm_api_key:
        print(f"\nNote: No LLM API key found at {args.llm_key_file}")
        print("      Setup wizard will use default/mock LLM")

    # Create config
    config = MobileTestConfig(
        device_serial=args.device,
        adb_path=args.adb_path,
        apk_path=args.apk,
        reinstall_app=not args.no_reinstall,
        clear_data=not args.no_clear,
        test_email=args.email,
        test_password=test_password,
        llm_api_key=llm_api_key,
        llm_provider=args.llm_provider,
        test_message=args.message,
        output_dir=args.output_dir,
        save_screenshots=not args.no_screenshots,
        save_logcat=not args.no_logcat,
        verbose=args.verbose,
    )

    # Print config summary
    print(f"\nConfiguration:")
    print(f"  Test email: {config.test_email}")
    print(f"  LLM provider: {config.llm_provider}")
    print(f"  LLM API key: {'*' * 8 if llm_api_key else '(not set)'}")
    print(f"  Tests: {', '.join(args.tests)}")
    print(f"  Reinstall app: {config.reinstall_app}")
    print(f"  Clear data: {config.clear_data}")

    # Run tests
    runner = MobileTestRunner(config)

    if not runner.setup():
        print("\nSetup failed!")
        return 1

    try:
        suite = runner.run_tests(args.tests)
        return 0 if suite.success else 1
    finally:
        runner.teardown()


def main():
    """CLI entry point for mobile QA runner."""
    import argparse

    parser = argparse.ArgumentParser(
        description="CIRIS Mobile QA Runner - Testing and Debugging Tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ========== pull-logs subcommand ==========
    pull_parser = subparsers.add_parser(
        "pull-logs",
        help="Pull device logs and files for debugging",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Collects from device:
  - Python logs (latest.log, incidents_latest.log)
  - Database files (.db)
  - Shared preferences (.xml)
  - Logcat output (python, crashes, app logs)
  - .env file (tokens redacted)
  - App info and storage usage

Examples:
  python -m tools.qa_runner.modules.mobile pull-logs
  python -m tools.qa_runner.modules.mobile pull-logs -d R5CRC3BWLRZ
  python -m tools.qa_runner.modules.mobile pull-logs -o ./my_logs
""",
    )
    pull_parser.add_argument("--device", "-d", help="Device serial number (uses first device if not specified)")
    pull_parser.add_argument("--adb-path", help="Path to adb binary")
    pull_parser.add_argument(
        "--output-dir",
        "-o",
        default="mobile_qa_reports",
        help="Directory for logs (default: mobile_qa_reports)",
    )
    pull_parser.add_argument(
        "--package",
        default="ai.ciris.mobile",
        help="Android package name (default: ai.ciris.mobile)",
    )

    # ========== go-screen subcommand ==========
    screen_list = "\n".join([f"  {name:15} - {desc}" for name, (_, _, desc) in SCREEN_REGISTRY.items()])
    go_screen_parser = subparsers.add_parser(
        "go-screen",
        help="Navigate to a specific app screen and take a screenshot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Available screens:
{screen_list}

Examples:
  python -m tools.qa_runner.modules.mobile go-screen billing
  python -m tools.qa_runner.modules.mobile go-screen telemetry -o ./screenshots
  python -m tools.qa_runner.modules.mobile go-screen settings -d emulator-5554
""",
    )
    go_screen_parser.add_argument(
        "screen",
        help="Screen to navigate to (see list above)",
    )
    go_screen_parser.add_argument("--device", "-d", help="Device serial number (uses first device if not specified)")
    go_screen_parser.add_argument("--adb-path", help="Path to adb binary")
    go_screen_parser.add_argument(
        "--output-dir",
        "-o",
        default="mobile_qa_reports",
        help="Directory for screenshots (default: mobile_qa_reports)",
    )
    go_screen_parser.add_argument(
        "--package",
        default="ai.ciris.mobile",
        help="Android package name (default: ai.ciris.mobile)",
    )

    # ========== test subcommand ==========
    test_parser = subparsers.add_parser(
        "test",
        help="Run UI automation tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Available tests:
  app_launch        - Test that app launches and shows login screen
  google_signin     - Test Google Sign-In flow with test account
  local_login       - Test local login (BYOK mode)
  setup_wizard      - Test completing the setup wizard
  chat_interaction  - Test sending a message and receiving response
  full_flow         - Run complete end-to-end flow (default)

Examples:
  python -m tools.qa_runner.modules.mobile test full_flow
  python -m tools.qa_runner.modules.mobile test app_launch --no-reinstall
""",
    )
    test_parser.add_argument(
        "tests",
        nargs="*",
        default=["full_flow"],
        help="Tests to run (default: full_flow)",
    )
    test_parser.add_argument("--device", "-d", help="Device serial number (uses default if not specified)")
    test_parser.add_argument("--adb-path", help="Path to adb binary")
    test_parser.add_argument(
        "--apk",
        default="mobile/androidApp/build/outputs/apk/debug/androidApp-debug.apk",
        help="Path to APK file",
    )
    test_parser.add_argument("--no-reinstall", action="store_true", help="Don't reinstall the app")
    test_parser.add_argument("--no-clear", action="store_true", help="Don't clear app data before tests")
    test_parser.add_argument(
        "--email",
        default="ciristest1@gmail.com",
        help="Test Google account email (default: ciristest1@gmail.com)",
    )
    test_parser.add_argument(
        "--password-file",
        default="~/.ciristest1_password",
        help="Path to file containing test account password",
    )
    test_parser.add_argument("--llm-key", help="LLM API key for setup wizard")
    test_parser.add_argument(
        "--llm-key-file",
        default="~/.groq_key",
        help="Path to file containing LLM API key",
    )
    test_parser.add_argument("--llm-provider", default="groq", help="LLM provider for setup")
    test_parser.add_argument(
        "--message",
        default="Hello CIRIS! This is an automated test. Please respond briefly.",
        help="Test message to send in chat",
    )
    test_parser.add_argument(
        "--output-dir",
        default="mobile_qa_reports",
        help="Directory for test reports (default: mobile_qa_reports)",
    )
    test_parser.add_argument("--no-screenshots", action="store_true", help="Don't save screenshots")
    test_parser.add_argument("--no-logcat", action="store_true", help="Don't capture logcat")
    test_parser.add_argument("--build", "-b", action="store_true", help="Build APK before running tests")
    test_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Default to pull-logs if no command specified (backward compat: check if first arg looks like a test name)
    if args.command is None:
        # Check if user passed test names directly (backward compatibility)
        if len(sys.argv) > 1 and sys.argv[1] in [
            "full_flow",
            "app_launch",
            "google_signin",
            "local_login",
            "setup_wizard",
            "chat_interaction",
        ]:
            # Reparse with 'test' prepended
            sys.argv.insert(1, "test")
            args = parser.parse_args()
        else:
            parser.print_help()
            return 0

    if args.command == "pull-logs":
        return pull_logs_command(args)
    elif args.command == "go-screen":
        return go_screen_command(args)
    elif args.command == "test":
        return test_command(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
