"""
Mobile QA Runner CLI entry point.

Usage:
    python -m tools.qa_runner.modules.mobile [command] [options]

Commands:
    test [tests]      - Run UI automation tests (default)
    pull-logs         - Pull device logs and files for debugging

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
"""

import os
import sys
from pathlib import Path

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from tools.qa_runner.modules.mobile.adb_helper import ADBHelper
from tools.qa_runner.modules.mobile.test_runner import MobileTestConfig, MobileTestRunner


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
    elif args.command == "test":
        return test_command(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
