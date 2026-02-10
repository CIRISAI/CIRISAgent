"""
Web UI Test Runner

Orchestrates end-to-end web UI testing for CIRIS.
Manages server lifecycle, browser automation, and test execution.
"""

import asyncio
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .browser_helper import BrowserConfig, BrowserHelper
from .server_manager import ServerConfig, ServerManager, ServerStatus
from .test_cases import (
    TestReport,
    TestResult,
    WebUITestConfig,
    test_complete_setup,
    test_enter_api_key,
    test_full_e2e_flow,
    test_live_model_listing,
    test_load_models,
    test_load_setup_wizard,
    test_login_after_setup,
    test_navigate_to_llm_config,
    test_receive_response,
    test_select_model,
    test_select_provider,
    test_send_message,
)


@dataclass
class WebUITestSuite:
    """Results of a web UI test suite run."""

    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    server_status: Optional[ServerStatus] = None
    reports: List[TestReport] = field(default_factory=list)
    success: bool = False
    error: Optional[str] = None

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
        """Get count of error tests."""
        return sum(1 for r in self.reports if r.result == TestResult.ERROR)

    @property
    def skipped_count(self) -> int:
        """Get count of skipped tests."""
        return sum(1 for r in self.reports if r.result == TestResult.SKIPPED)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration,
            "success": self.success,
            "error": self.error,
            "summary": {
                "total": len(self.reports),
                "passed": self.passed_count,
                "failed": self.failed_count,
                "errors": self.error_count,
                "skipped": self.skipped_count,
            },
            "reports": [
                {
                    "name": r.name,
                    "result": r.result.value,
                    "duration_seconds": r.duration_seconds,
                    "message": r.message,
                    "screenshots": r.screenshots,
                    "details": r.details,
                }
                for r in self.reports
            ],
        }


class WebUITestRunner:
    """
    Orchestrates web UI testing for CIRIS.

    Manages:
    - Server lifecycle (wipe, start, stop)
    - Browser automation
    - Test execution
    - Report generation
    """

    # Available test functions
    TESTS: Dict[str, Callable] = {
        "load_setup": test_load_setup_wizard,
        "navigate_llm": test_navigate_to_llm_config,
        "select_provider": test_select_provider,
        "enter_key": test_enter_api_key,
        "load_models": test_load_models,
        "live_model_listing": test_live_model_listing,
        "select_model": test_select_model,
        "complete_setup": test_complete_setup,
        "login": test_login_after_setup,
        "send_message": test_send_message,
        "receive_response": test_receive_response,
    }

    def __init__(
        self,
        server_config: Optional[ServerConfig] = None,
        browser_config: Optional[BrowserConfig] = None,
        test_config: Optional[WebUITestConfig] = None,
        keep_open: bool = False,
    ):
        self.server_config = server_config or ServerConfig()
        self.browser_config = browser_config or BrowserConfig()
        self.test_config = test_config or WebUITestConfig.from_env()
        self.keep_open = keep_open

        # Sync base URL
        self.test_config.base_url = f"http://{self.server_config.host}:{self.server_config.port}"

        self._server: Optional[ServerManager] = None
        self._browser: Optional[BrowserHelper] = None

        # Output directory
        self.output_dir = Path(self.browser_config.screenshot_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def setup(self) -> ServerStatus:
        """
        Set up the test environment.

        1. Kill any existing servers
        2. Wipe data (if configured)
        3. Start server
        4. Start browser

        Returns:
            ServerStatus
        """
        print("\n" + "=" * 60)
        print("🧪 CIRIS Web UI QA Test Runner")
        print("=" * 60 + "\n")

        # Initialize server manager
        self._server = ServerManager(self.server_config)

        # Kill existing servers
        self._server.kill_existing_servers()

        # Start server
        status = self._server.start()

        if not status.healthy:
            print(f"❌ Server failed to start: {status.error}")
            return status

        # Start browser
        print("\n🌐 Starting browser...")
        self._browser = BrowserHelper(self.browser_config)
        await self._browser.start()
        print("✅ Browser ready")

        return status

    async def teardown(self) -> None:
        """Clean up test environment."""
        if self.keep_open:
            print("\n🔓 Keep-open mode: Browser and server will remain running")
            print(f"   Server: http://{self.server_config.host}:{self.server_config.port}")
            print("   Press Ctrl+C to stop when done")
            try:
                # Keep running until interrupted
                while True:
                    await asyncio.sleep(1)
            except (KeyboardInterrupt, asyncio.CancelledError):
                print("\n🛑 Shutting down...")

        print("\n🧹 Cleaning up...")

        if self._browser:
            await self._browser.stop()
            self._browser = None

        if self._server:
            self._server.stop()
            self._server = None

        print("✅ Cleanup complete")

    async def run_test(self, test_name: str) -> TestReport:
        """
        Run a single test by name.

        Args:
            test_name: Name of the test to run

        Returns:
            TestReport
        """
        if test_name not in self.TESTS:
            return TestReport(
                name=test_name,
                result=TestResult.ERROR,
                message=f"Unknown test: {test_name}. Available: {list(self.TESTS.keys())}",
            )

        if not self._browser:
            return TestReport(
                name=test_name,
                result=TestResult.ERROR,
                message="Browser not started. Call setup() first.",
            )

        test_func = self.TESTS[test_name]
        return await test_func(self._browser, self.test_config)

    async def run_e2e_flow(self) -> WebUITestSuite:
        """
        Run the full end-to-end test flow.

        Returns:
            WebUITestSuite with all results
        """
        suite = WebUITestSuite()

        try:
            # Setup
            status = await self.setup()
            suite.server_status = status

            if not status.healthy:
                suite.error = f"Server failed to start: {status.error}"
                suite.end_time = datetime.now()
                return suite

            # Run full E2E flow
            print("\n" + "-" * 40)
            print("📋 Running End-to-End Test Flow")
            print("-" * 40 + "\n")

            reports = await test_full_e2e_flow(self._browser, self.test_config)
            suite.reports = reports

            # Print results as we go
            for report in reports:
                icon = {
                    TestResult.PASSED: "✅",
                    TestResult.FAILED: "❌",
                    TestResult.SKIPPED: "⏭️",
                    TestResult.ERROR: "💥",
                }.get(report.result, "❓")

                print(f"  {icon} {report.name}: {report.message or report.result.value}")

            # Determine overall success
            suite.success = suite.failed_count == 0 and suite.error_count == 0

        except Exception as e:
            suite.error = str(e)
            print(f"\n💥 Test error: {e}")

        finally:
            suite.end_time = datetime.now()
            await self.teardown()

        return suite

    async def run_selected_tests(self, test_names: List[str]) -> WebUITestSuite:
        """
        Run selected tests.

        Args:
            test_names: List of test names to run

        Returns:
            WebUITestSuite with results
        """
        suite = WebUITestSuite()

        try:
            # Setup
            status = await self.setup()
            suite.server_status = status

            if not status.healthy:
                suite.error = f"Server failed to start: {status.error}"
                suite.end_time = datetime.now()
                return suite

            # Run selected tests
            print("\n" + "-" * 40)
            print(f"📋 Running {len(test_names)} Selected Tests")
            print("-" * 40 + "\n")

            for test_name in test_names:
                report = await self.run_test(test_name)
                suite.reports.append(report)

                icon = {
                    TestResult.PASSED: "✅",
                    TestResult.FAILED: "❌",
                    TestResult.SKIPPED: "⏭️",
                    TestResult.ERROR: "💥",
                }.get(report.result, "❓")

                print(f"  {icon} {report.name}: {report.message or report.result.value}")

            suite.success = suite.failed_count == 0 and suite.error_count == 0

        except Exception as e:
            suite.error = str(e)
            print(f"\n💥 Test error: {e}")

        finally:
            suite.end_time = datetime.now()
            await self.teardown()

        return suite

    def save_report(self, suite: WebUITestSuite, filename: Optional[str] = None) -> str:
        """
        Save test report to JSON file.

        Args:
            suite: Test suite results
            filename: Optional filename (auto-generated if not provided)

        Returns:
            Path to saved report
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"web_ui_qa_report_{timestamp}.json"

        filepath = self.output_dir / filename

        with open(filepath, "w") as f:
            json.dump(suite.to_dict(), f, indent=2)

        return str(filepath)

    def print_summary(self, suite: WebUITestSuite) -> None:
        """Print test suite summary."""
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)

        print(f"\n  Duration: {suite.duration:.1f}s")
        print(f"  Total:    {len(suite.reports)}")
        print(f"  Passed:   {suite.passed_count} ✅")
        print(f"  Failed:   {suite.failed_count} ❌")
        print(f"  Errors:   {suite.error_count} 💥")
        print(f"  Skipped:  {suite.skipped_count} ⏭️")

        if suite.success:
            print("\n  🎉 ALL TESTS PASSED!")
        else:
            print("\n  ⚠️  SOME TESTS FAILED")

            # List failures
            failures = [r for r in suite.reports if r.result in (TestResult.FAILED, TestResult.ERROR)]
            if failures:
                print("\n  Failed tests:")
                for f in failures:
                    print(f"    - {f.name}: {f.message}")

        # List screenshots
        all_screenshots = []
        for r in suite.reports:
            all_screenshots.extend(r.screenshots)

        if all_screenshots:
            print(f"\n  📸 Screenshots: {len(all_screenshots)}")
            print(f"     Location: {self.output_dir}")

        print("\n" + "=" * 60 + "\n")


async def run_web_ui_tests(
    wipe_data: bool = True,
    headless: bool = False,
    provider: str = "openrouter",
    api_key: Optional[str] = None,
    mock_llm: bool = False,
    tests: Optional[List[str]] = None,
) -> WebUITestSuite:
    """
    Convenience function to run web UI tests.

    Args:
        wipe_data: Whether to wipe data before testing
        headless: Run browser in headless mode
        provider: LLM provider to use
        api_key: API key (or loaded from file)
        mock_llm: Use mock LLM instead of real
        tests: Specific tests to run (None = full E2E)

    Returns:
        WebUITestSuite
    """
    server_config = ServerConfig(
        wipe_data=wipe_data,
        mock_llm=mock_llm,
    )

    browser_config = BrowserConfig(
        headless=headless,
    )

    test_config = WebUITestConfig.from_env()
    test_config.llm_provider = provider
    if api_key:
        test_config.llm_api_key = api_key

    runner = WebUITestRunner(
        server_config=server_config,
        browser_config=browser_config,
        test_config=test_config,
    )

    if tests:
        suite = await runner.run_selected_tests(tests)
    else:
        suite = await runner.run_e2e_flow()

    runner.print_summary(suite)
    report_path = runner.save_report(suite)
    print(f"📄 Report saved: {report_path}")

    return suite
