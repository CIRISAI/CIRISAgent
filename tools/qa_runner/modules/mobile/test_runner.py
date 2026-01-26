"""
Mobile Test Runner for CIRIS App

Orchestrates mobile UI testing using ADB and UI Automator.
"""

import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .adb_helper import ADBHelper
from .test_cases import (
    CIRISAppConfig,
    TestReport,
    TestResult,
    test_app_launch,
    test_chat_interaction,
    test_full_flow,
    test_google_signin,
    test_local_login,
    test_setup_wizard,
    # Screen navigation tests (new in 1.9.2)
    test_all_screens,
    test_screen_audit,
    test_screen_config,
    test_screen_consent,
    test_screen_logs,
    test_screen_memory,
    test_screen_runtime,
    test_screen_services,
    test_screen_system,
)
from .ui_automator import UIAutomator


@dataclass
class MobileTestConfig:
    """Configuration for mobile test runner."""

    # Device settings
    device_serial: Optional[str] = None
    adb_path: Optional[str] = None

    # App settings
    apk_path: str = "mobile/androidApp/build/outputs/apk/debug/androidApp-debug.apk"
    package_name: str = "ai.ciris.mobile"
    reinstall_app: bool = True
    clear_data: bool = True

    # Test account
    test_email: str = "ciristest1@gmail.com"
    test_password: str = ""  # For Google Sign-In if manual entry needed

    # LLM settings for setup
    llm_provider: str = "groq"
    llm_api_key: str = ""
    llm_model: str = "meta-llama/llama-4-maverick-17b-128e-instruct"

    # Test settings
    test_message: str = "Hello CIRIS! This is an automated test. Please respond briefly."
    timeout: int = 300  # Total test timeout in seconds

    # Output settings
    output_dir: str = "mobile_qa_reports"
    save_screenshots: bool = True
    save_logcat: bool = True
    verbose: bool = True


@dataclass
class MobileTestSuite:
    """Results of a mobile test suite run."""

    start_time: datetime
    end_time: Optional[datetime] = None
    config: Optional[MobileTestConfig] = None
    device_info: Dict = field(default_factory=dict)
    reports: List[TestReport] = field(default_factory=list)
    logcat_path: Optional[str] = None
    success: bool = False

    @property
    def duration(self) -> float:
        """Get total duration in seconds."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0

    @property
    def passed_count(self) -> int:
        """Get count of passed tests."""
        return sum(1 for r in self.reports if r.result == TestResult.PASSED)

    @property
    def failed_count(self) -> int:
        """Get count of failed tests."""
        return sum(1 for r in self.reports if r.result == TestResult.FAILED)

    @property
    def error_count(self) -> int:
        """Get count of errored tests."""
        return sum(1 for r in self.reports if r.result == TestResult.ERROR)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration": self.duration,
            "device_info": self.device_info,
            "success": self.success,
            "summary": {
                "total": len(self.reports),
                "passed": self.passed_count,
                "failed": self.failed_count,
                "errored": self.error_count,
            },
            "reports": [
                {
                    "name": r.name,
                    "result": r.result.value,
                    "duration": r.duration,
                    "message": r.message,
                    "screenshots": r.screenshots,
                }
                for r in self.reports
            ],
            "logcat_path": self.logcat_path,
        }


class MobileTestRunner:
    """Runner for mobile UI tests."""

    def __init__(self, config: Optional[MobileTestConfig] = None):
        """
        Initialize mobile test runner.

        Args:
            config: Test configuration. Uses defaults if not provided.
        """
        self.config = config or MobileTestConfig()
        self.adb: Optional[ADBHelper] = None
        self.ui: Optional[UIAutomator] = None
        self.logcat_process: Optional[subprocess.Popen] = None

    def setup(self) -> bool:
        """
        Set up test environment.

        Returns:
            True if setup successful.
        """
        print("\n" + "=" * 60)
        print("CIRIS Mobile QA Runner - Setup")
        print("=" * 60 + "\n")

        try:
            # Initialize ADB
            print("[1/4] Initializing ADB...")
            self.adb = ADBHelper(adb_path=self.config.adb_path, device_serial=self.config.device_serial)
            print(f"      ADB path: {self.adb.adb_path}")

            # Check device connection
            print("[2/4] Checking device connection...")
            if not self.adb.wait_for_device(timeout=30):
                print("      ERROR: No device connected")
                return False

            devices = self.adb.get_devices()
            if devices:
                device = devices[0]
                print(f"      Device: {device.serial} ({device.model or 'unknown'})")
            else:
                print("      ERROR: No devices found")
                return False

            # Initialize UI Automator
            print("[3/4] Initializing UI Automator...")
            self.ui = UIAutomator(self.adb)

            # Install APK if requested
            if self.config.reinstall_app:
                print(f"[4/4] Installing APK: {self.config.apk_path}")
                apk_path = Path(self.config.apk_path)
                if not apk_path.exists():
                    # Try relative to CIRISAgent root
                    apk_path = Path(__file__).parent.parent.parent.parent.parent / self.config.apk_path
                    if not apk_path.exists():
                        print(f"      ERROR: APK not found: {self.config.apk_path}")
                        return False

                if not self.adb.install_apk(str(apk_path)):
                    print("      ERROR: APK installation failed")
                    return False
                print("      APK installed successfully")
            else:
                print("[4/4] Skipping APK installation (reinstall_app=False)")

            print("\nSetup complete!\n")
            return True

        except Exception as e:
            print(f"Setup error: {e}")
            return False

    def teardown(self):
        """Clean up test environment."""
        print("\nTeardown...")

        # Stop logcat capture
        if self.logcat_process:
            self.logcat_process.terminate()
            self.logcat_process = None

        # Force stop app
        if self.adb:
            self.adb.force_stop_app(self.config.package_name)

    def run_tests(self, tests: Optional[List[str]] = None) -> MobileTestSuite:
        """
        Run mobile tests.

        Args:
            tests: List of test names to run. Runs all if None.

        Returns:
            MobileTestSuite with results.
        """
        suite = MobileTestSuite(start_time=datetime.now(), config=self.config)

        # Available tests
        available_tests: Dict[str, Callable] = {
            "app_launch": test_app_launch,
            "google_signin": test_google_signin,
            "local_login": test_local_login,
            "setup_wizard": test_setup_wizard,
            "chat_interaction": test_chat_interaction,
            "full_flow": test_full_flow,
            # Screen navigation tests (new in 1.9.2)
            "all_screens": test_all_screens,
            "screen_audit": test_screen_audit,
            "screen_logs": test_screen_logs,
            "screen_memory": test_screen_memory,
            "screen_config": test_screen_config,
            "screen_consent": test_screen_consent,
            "screen_system": test_screen_system,
            "screen_services": test_screen_services,
            "screen_runtime": test_screen_runtime,
        }

        # Determine which tests to run
        if tests is None:
            tests = ["full_flow"]  # Default to full flow

        tests_to_run = []
        for test_name in tests:
            if test_name in available_tests:
                tests_to_run.append((test_name, available_tests[test_name]))
            else:
                print(f"Warning: Unknown test '{test_name}'")

        if not tests_to_run:
            print("No tests to run!")
            return suite

        # Create output directory
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Start logcat capture
        if self.config.save_logcat:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            logcat_path = output_dir / f"logcat_{timestamp}.txt"
            suite.logcat_path = str(logcat_path)
            self.adb.clear_logcat()
            self.logcat_process = self.adb.start_logcat_capture(
                str(logcat_path), filter_tags=["CIRISApp:V", "MainActivity:V", "python.stdout:I"]
            )

        # Get device info
        devices = self.adb.get_devices()
        if devices:
            suite.device_info = {
                "serial": devices[0].serial,
                "model": devices[0].model,
            }

        # Run tests
        print("\n" + "=" * 60)
        print("Running Mobile Tests")
        print("=" * 60)

        test_config = {
            "test_email": self.config.test_email,
            "test_password": self.config.test_password,
            "llm_provider": self.config.llm_provider,
            "llm_api_key": self.config.llm_api_key,
            "test_message": self.config.test_message,
        }

        for test_name, test_func in tests_to_run:
            print(f"\n--- Test: {test_name} ---")
            try:
                report = test_func(self.adb, self.ui, test_config)
                suite.reports.append(report)

                # Print result
                status_icon = {
                    TestResult.PASSED: "PASS",
                    TestResult.FAILED: "FAIL",
                    TestResult.SKIPPED: "SKIP",
                    TestResult.ERROR: "ERR!",
                }
                print(f"\n  [{status_icon.get(report.result, '????')}] {report.name} " f"({report.duration:.1f}s)")
                if report.message:
                    print(f"        {report.message}")

            except Exception as e:
                error_report = TestReport(
                    name=test_name,
                    result=TestResult.ERROR,
                    duration=0.0,
                    message=f"Exception: {str(e)}",
                )
                suite.reports.append(error_report)
                print(f"\n  [ERR!] {test_name}: {e}")

        # Finalize
        suite.end_time = datetime.now()
        suite.success = suite.failed_count == 0 and suite.error_count == 0

        # Save results
        results_path = output_dir / f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(results_path, "w") as f:
            json.dump(suite.to_dict(), f, indent=2)

        # Print summary
        print("\n" + "=" * 60)
        print("Test Summary")
        print("=" * 60)
        print(f"  Total:   {len(suite.reports)}")
        print(f"  Passed:  {suite.passed_count}")
        print(f"  Failed:  {suite.failed_count}")
        print(f"  Errors:  {suite.error_count}")
        print(f"  Duration: {suite.duration:.1f}s")
        print(f"  Results: {results_path}")
        if suite.logcat_path:
            print(f"  Logcat:  {suite.logcat_path}")
        print("=" * 60 + "\n")

        return suite


def main():
    """CLI entry point for mobile QA runner."""
    import argparse

    parser = argparse.ArgumentParser(description="CIRIS Mobile QA Runner - Automated UI Testing")

    # Test selection
    parser.add_argument(
        "tests",
        nargs="*",
        default=["full_flow"],
        help="Tests to run (default: full_flow). Options: app_launch, google_signin, local_login, setup_wizard, chat_interaction, full_flow, all_screens, screen_audit, screen_logs, screen_memory, screen_config, screen_consent, screen_system, screen_services, screen_runtime",
    )

    # Device settings
    parser.add_argument("--device", "-d", help="Device serial number (uses default if not specified)")
    parser.add_argument("--adb-path", help="Path to adb binary")

    # App settings
    parser.add_argument(
        "--apk",
        default="mobile/androidApp/build/outputs/apk/debug/androidApp-debug.apk",
        help="Path to APK file",
    )
    parser.add_argument("--no-reinstall", action="store_true", help="Don't reinstall the app")
    parser.add_argument("--no-clear", action="store_true", help="Don't clear app data before tests")

    # Test account
    parser.add_argument(
        "--email",
        default="ciristest1@gmail.com",
        help="Test Google account email",
    )

    # LLM settings
    parser.add_argument("--llm-key", help="LLM API key for setup wizard")
    parser.add_argument("--llm-provider", default="groq", help="LLM provider for setup")

    # Output settings
    parser.add_argument(
        "--output-dir",
        default="mobile_qa_reports",
        help="Directory for test reports",
    )
    parser.add_argument("--no-screenshots", action="store_true", help="Don't save screenshots")
    parser.add_argument("--no-logcat", action="store_true", help="Don't capture logcat")

    # Other
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Create config
    config = MobileTestConfig(
        device_serial=args.device,
        adb_path=args.adb_path,
        apk_path=args.apk,
        reinstall_app=not args.no_reinstall,
        clear_data=not args.no_clear,
        test_email=args.email,
        llm_api_key=args.llm_key or "",
        llm_provider=args.llm_provider,
        output_dir=args.output_dir,
        save_screenshots=not args.no_screenshots,
        save_logcat=not args.no_logcat,
        verbose=args.verbose,
    )

    # Run tests
    runner = MobileTestRunner(config)

    if not runner.setup():
        print("Setup failed!")
        return 1

    try:
        suite = runner.run_tests(args.tests)
        return 0 if suite.success else 1
    finally:
        runner.teardown()


if __name__ == "__main__":
    exit(main())
