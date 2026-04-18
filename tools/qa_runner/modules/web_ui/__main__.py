#!/usr/bin/env python3
"""
Desktop App / Web UI QA Runner CLI

End-to-end UI testing for CIRIS Desktop app and web interface.

Usage:
    python -m tools.qa_runner.modules.web_ui [command] [options]

Commands:
    desktop         Test the CIRIS Desktop app (uses TestAutomationServer)
    desktop-login   Test login flow on desktop app
    desktop-chat    Test chat interaction on desktop app
    e2e             Run full end-to-end test flow (browser-based, legacy)
    setup           Test only setup wizard steps (browser-based)
    interact        Test only interaction steps (browser-based)
    models          Test only model listing feature (browser-based)
    licensed_agent  First-time licensed agent flow (Portal device auth)
    list            List available tests

Examples:
    # Test desktop app (requires CIRIS_TEST_MODE=true)
    python -m tools.qa_runner.modules.web_ui desktop

    # Test desktop app login flow
    python -m tools.qa_runner.modules.web_ui desktop-login

    # Test desktop app chat
    python -m tools.qa_runner.modules.web_ui desktop-chat

    # Legacy browser-based E2E test
    python -m tools.qa_runner.modules.web_ui e2e --wipe

    # Use mock LLM (no API key needed)
    python -m tools.qa_runner.modules.web_ui e2e --mock-llm
"""

import argparse
import asyncio
import glob
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import requests

from .browser_helper import BrowserConfig, ensure_playwright_installed
from .desktop_app_helper import DesktopAppConfig, DesktopAppHelper, check_desktop_app_running
from .server_manager import ServerConfig
from .test_cases import WebUITestConfig
from .test_runner import WebUITestRunner, run_web_ui_tests


@dataclass
class DesktopTestResult:
    """Result of a desktop app test."""

    name: str
    success: bool
    duration_ms: float
    error: Optional[str] = None
    screen: Optional[str] = None


class DesktopAppTestRunner:
    """
    Test runner for CIRIS Desktop app.

    Uses the embedded TestAutomationServer for native Compose automation.
    """

    def __init__(self, config: Optional[DesktopAppConfig] = None, verbose: bool = False):
        self.config = config or DesktopAppConfig()
        self.verbose = verbose
        self.helper: Optional[DesktopAppHelper] = None
        self.results: List[DesktopTestResult] = []

    async def start(self) -> "DesktopAppTestRunner":
        """Start the test runner and connect to desktop app."""
        self.helper = DesktopAppHelper(self.config)
        await self.helper.start()
        return self

    async def stop(self) -> None:
        """Stop the test runner."""
        if self.helper:
            await self.helper.stop()
            self.helper = None

    def _log(self, msg: str) -> None:
        """Log a message if verbose mode is enabled."""
        if self.verbose:
            print(f"  {msg}")

    async def run_test(self, name: str, test_fn) -> DesktopTestResult:
        """Run a single test and record result."""
        start = datetime.now()
        try:
            await test_fn()
            duration = (datetime.now() - start).total_seconds() * 1000
            screen = await self.helper.get_screen() if self.helper else None
            result = DesktopTestResult(
                name=name,
                success=True,
                duration_ms=duration,
                screen=screen,
            )
            print(f"  ✅ {name} ({duration:.0f}ms)")
        except Exception as e:
            duration = (datetime.now() - start).total_seconds() * 1000
            screen = await self.helper.get_screen() if self.helper else None
            result = DesktopTestResult(
                name=name,
                success=False,
                duration_ms=duration,
                error=str(e),
                screen=screen,
            )
            print(f"  ❌ {name}: {e}")

        self.results.append(result)
        return result

    async def test_login_flow(self, username: str = "admin", password: str = "qa_test_password_12345") -> bool:
        """Test the login flow on the desktop app."""
        print("\n🔐 Testing Login Flow")

        if not self.helper:
            raise RuntimeError("Test runner not started")

        # Wait for login screen
        async def wait_for_login():
            self._log("Waiting for login screen...")
            if not await self.helper.wait_for_screen("Login", timeout=30000):
                raise RuntimeError("Login screen did not appear")
            self._log(f"Current screen: {self.helper.current_screen}")

        await self.run_test("wait_for_login_screen", wait_for_login)

        # Wait for username input
        async def wait_for_username_input():
            self._log("Waiting for username input...")
            if not await self.helper.wait_for_element("input_username", timeout=10000):
                raise RuntimeError("Username input not found")

        await self.run_test("wait_for_username_input", wait_for_username_input)

        # Enter username
        async def enter_username():
            self._log(f"Entering username: {username}")
            if not await self.helper.input_text("input_username", username):
                raise RuntimeError("Failed to enter username")

        await self.run_test("enter_username", enter_username)

        # Enter password
        async def enter_password():
            self._log(f"Entering password: {'*' * len(password)}")
            if not await self.helper.input_text("input_password", password):
                raise RuntimeError("Failed to enter password")

        await self.run_test("enter_password", enter_password)

        # Click login button
        async def click_login():
            self._log("Clicking login button...")
            if not await self.helper.click("btn_login_submit"):
                raise RuntimeError("Failed to click login button")

        await self.run_test("click_login_button", click_login)

        # Wait for next screen (Interact or Setup)
        async def wait_for_post_login():
            self._log("Waiting for post-login screen...")
            start = datetime.now()
            while (datetime.now() - start).total_seconds() < 30:
                screen = await self.helper.get_screen()
                if screen in ["Interact", "Setup", "Startup"]:
                    self._log(f"Navigated to: {screen}")
                    return
                await asyncio.sleep(0.5)
            raise RuntimeError(f"Still on Login screen after 30s")

        await self.run_test("wait_for_post_login", wait_for_post_login)

        # Return overall success
        return all(r.success for r in self.results)

    async def test_chat_flow(self, message: str = "Hello, can you hear me?") -> bool:
        """Test the chat interaction flow on the desktop app."""
        print("\n💬 Testing Chat Flow")

        if not self.helper:
            raise RuntimeError("Test runner not started")

        # Wait for Interact screen
        async def wait_for_interact():
            self._log("Waiting for Interact screen...")
            if not await self.helper.wait_for_screen("Interact", timeout=30000):
                raise RuntimeError("Interact screen did not appear")

        await self.run_test("wait_for_interact_screen", wait_for_interact)

        # Wait for message input
        async def wait_for_input():
            self._log("Waiting for message input...")
            if not await self.helper.wait_for_element("input_message", timeout=10000):
                raise RuntimeError("Message input not found")

        await self.run_test("wait_for_message_input", wait_for_input)

        # Enter message
        async def enter_message():
            self._log(f"Entering message: {message}")
            if not await self.helper.input_text("input_message", message):
                raise RuntimeError("Failed to enter message")

        await self.run_test("enter_message", enter_message)

        # Click send button
        async def click_send():
            self._log("Clicking send button...")
            if not await self.helper.click("btn_send"):
                raise RuntimeError("Failed to click send button")

        await self.run_test("click_send_button", click_send)

        # Wait a bit for response (we don't have a way to detect response yet)
        async def wait_for_response():
            self._log("Waiting for response (5s)...")
            await asyncio.sleep(5)

        await self.run_test("wait_for_response", wait_for_response)

        return all(r.success for r in self.results)

    async def test_element_tree(self) -> bool:
        """Debug test - print current element tree."""
        print("\n🌳 Element Tree")

        if not self.helper:
            raise RuntimeError("Test runner not started")

        elements = await self.helper.get_elements()
        screen = await self.helper.get_screen()

        print(f"\nScreen: {screen}")
        print(f"Elements ({len(elements)}):")
        for elem in sorted(elements, key=lambda e: e.test_tag):
            print(f"  • {elem.test_tag:30s} at ({elem.center_x}, {elem.center_y})")

        return True

    def print_summary(self) -> None:
        """Print test summary."""
        passed = sum(1 for r in self.results if r.success)
        failed = sum(1 for r in self.results if not r.success)
        total = len(self.results)

        print(f"\n{'=' * 50}")
        print(f"📊 Test Summary: {passed}/{total} passed")

        if failed > 0:
            print(f"\n❌ Failed tests:")
            for r in self.results:
                if not r.success:
                    print(f"   • {r.name}: {r.error}")

        print(f"{'=' * 50}")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="CIRIS Desktop App / Web UI QA Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Desktop app testing (primary)
  %(prog)s desktop                       Test desktop app (show element tree)
  %(prog)s desktop-login                 Test login flow on desktop app
  %(prog)s desktop-chat                  Test chat flow on desktop app

  # Legacy browser-based testing
  %(prog)s e2e --wipe                    Full E2E test with clean slate
  %(prog)s setup --provider anthropic    Test setup wizard with Anthropic
  %(prog)s e2e --headless --mock-llm     Headless with mock LLM
        """,
    )

    # Commands
    parser.add_argument(
        "command",
        nargs="?",
        default="desktop",
        choices=[
            "desktop",
            "desktop-login",
            "desktop-chat",
            "desktop-up",
            "e2e",
            "setup",
            "interact",
            "models",
            "licensed_agent",
            "list",
        ],
        help="Test command to run (default: desktop)",
    )

    # Server options
    parser.add_argument(
        "--wipe",
        action="store_true",
        default=True,
        help="Wipe all data before testing (clean slate) - enabled by default",
    )
    parser.add_argument(
        "--no-wipe",
        action="store_true",
        help="Don't wipe data (continue from existing state)",
    )
    parser.add_argument(
        "--mock-llm",
        action="store_true",
        help="Use mock LLM (no API key needed)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Server port (default: 8080)",
    )

    # Desktop app options
    parser.add_argument(
        "--desktop-port",
        type=int,
        default=8091,
        help="Desktop app test automation server port (default: 8091)",
    )
    parser.add_argument(
        "--no-desktop",
        action="store_true",
        help="For desktop-up: start backend + setup admin, but don't launch the desktop app",
    )
    parser.add_argument(
        "--username",
        default=None,
        help="Username for desktop login test (default: admin)",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="Password for desktop login test (default: qa_test_password_12345)",
    )
    parser.add_argument(
        "--message",
        default=None,
        help="Message for desktop chat test (default: 'Hello, can you hear me?')",
    )

    # Browser options
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode (no window)",
    )
    parser.add_argument(
        "--slow-mo",
        type=int,
        default=0,
        help="Slow down browser actions by N milliseconds",
    )

    # LLM options
    parser.add_argument(
        "--provider",
        default="openrouter",
        choices=["openai", "anthropic", "openrouter", "groq", "google", "together", "local"],
        help="LLM provider (default: openrouter)",
    )
    parser.add_argument(
        "--api-key",
        help="API key (or set LLM_API_KEY env var, or use ~/.provider_key file)",
    )
    parser.add_argument(
        "--model",
        help="Specific model to select (default: auto-select recommended)",
    )

    # Portal options (for licensed_agent flow)
    parser.add_argument(
        "--portal-url",
        default="https://portal.ciris.ai",
        help="CIRIS Portal URL for device auth (default: https://portal.ciris.ai)",
    )
    parser.add_argument(
        "--poll-timeout",
        type=int,
        default=300,
        help="Timeout for Portal authorization polling in seconds (default: 300)",
    )

    # Test options
    parser.add_argument(
        "--tests",
        help="Comma-separated list of specific tests to run",
    )
    parser.add_argument(
        "--output-dir",
        default="web_ui_qa_reports",
        help="Directory for screenshots and reports",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Server startup timeout in seconds",
    )

    # Verbosity
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output",
    )

    # Keep open
    parser.add_argument(
        "--keep-open",
        action="store_true",
        help="Keep browser and server running after tests (for demos)",
    )

    return parser.parse_args()


def list_tests() -> None:
    """List available tests."""
    print("\n📋 Available Tests:\n")

    test_info = {
        "load_setup": "Load the setup wizard page",
        "navigate_llm": "Navigate to LLM configuration step",
        "select_provider": "Select LLM provider (OpenAI, Anthropic, etc.)",
        "enter_key": "Enter API key",
        "load_models": "Load available models (live model listing)",
        "select_model": "Select a model from the list",
        "complete_setup": "Complete remaining setup steps",
        "send_message": "Send a test message to the agent",
        "receive_response": "Wait for and validate agent response",
    }

    for name, desc in test_info.items():
        print(f"  • {name:20s} - {desc}")

    print("\n🔄 Test Groups:\n")
    print("  • e2e            - All tests in sequence")
    print("  • setup          - Setup wizard tests only (load_setup through complete_setup)")
    print("  • interact       - Interaction tests only (send_message, receive_response)")
    print("  • models         - Model listing tests only (load_setup through load_models)")
    print("  • licensed_agent - First-time licensed agent flow (Portal device auth)")

    print("\n💡 Examples:\n")
    print("  python -m tools.qa_runner.modules.web_ui e2e --wipe")
    print("  python -m tools.qa_runner.modules.web_ui --tests load_setup,enter_key,load_models")
    print("  python -m tools.qa_runner.modules.web_ui licensed_agent --provider groq")
    print()


def get_test_list(command: str, specific_tests: Optional[str]) -> Optional[List[str]]:
    """Get list of tests to run based on command and specific tests."""
    if specific_tests:
        return [t.strip() for t in specific_tests.split(",")]

    test_groups = {
        "e2e": None,  # Full flow
        "setup": [
            "load_setup",
            "navigate_llm",
            "select_provider",
            "enter_key",
            "load_models",
            "select_model",
            "complete_setup",
        ],
        "interact": [
            "send_message",
            "receive_response",
        ],
        "models": [
            "load_setup",
            "navigate_llm",
            "select_provider",
            "enter_key",
            "load_models",
        ],
        "licensed_agent": ["licensed_agent"],  # Special flow
    }

    return test_groups.get(command)


TEST_ADMIN_USERNAME = "admin"
TEST_ADMIN_PASSWORD = "qa_test_password_12345"


def _kill_port(port: int) -> None:
    """SIGKILL whatever is listening on a port."""
    try:
        out = subprocess.run(
            ["lsof", "-tiTCP:" + str(port), "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        for pid in out.splitlines():
            try:
                os.kill(int(pid), 9)
            except Exception:
                pass
    except Exception:
        pass


def _wipe_dev_data() -> None:
    """Wipe every data location the CIRIS backend may use in dev mode.

    The server picks paths from env/cwd, so both ~/ciris/data and the
    repo-local data/ must be cleared. Signing key is preserved so
    device identity survives across resets.
    """
    home_ciris = Path.home() / "ciris"
    repo_root = Path(__file__).resolve().parents[4]
    signing_key = home_ciris / "agent_signing.key"
    key_backup = None
    if signing_key.exists():
        key_backup = signing_key.read_bytes()

    for data_dir in [home_ciris / "data", repo_root / "data"]:
        if data_dir.exists():
            shutil.rmtree(data_dir, ignore_errors=True)
            print(f"  🧹 wiped {data_dir}")
        data_dir.mkdir(parents=True, exist_ok=True)

    # Restore signing key
    if key_backup:
        signing_key.write_bytes(key_backup)
        (repo_root / "data" / "agent_signing.key").write_bytes(key_backup)

    # Rewrite minimal .env so the server doesn't re-enter first-run after setup completes
    env_path = home_ciris / ".env"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text('CIRIS_CONFIGURED="true"\n')


def _find_desktop_jar() -> Optional[Path]:
    """Locate the built desktop uber jar."""
    repo_root = Path(__file__).resolve().parents[4]
    candidates = sorted(
        glob.glob(str(repo_root / "mobile" / "desktopApp" / "build" / "compose" / "jars" / "CIRIS-*.jar")),
        key=os.path.getmtime,
        reverse=True,
    )
    return Path(candidates[0]) if candidates else None


def _complete_setup(base_url: str, mock_llm: bool) -> bool:
    """Call /v1/setup/complete to create the known-password admin user.

    Mirrors qa_runner.server.APIServerManager._complete_qa_setup.
    """
    payload = {
        "llm_provider": "mock" if mock_llm else "openai",
        "llm_api_key": "test-key-for-qa",
        "llm_model": "mock-model" if mock_llm else "gpt-4",
        "template_id": "default",
        "enabled_adapters": ["api"],
        "adapter_config": {},
        "admin_username": TEST_ADMIN_USERNAME,
        "admin_password": TEST_ADMIN_PASSWORD,
        "agent_port": int(base_url.rsplit(":", 1)[-1]),
    }
    try:
        r = requests.post(f"{base_url}/v1/setup/complete", json=payload, timeout=30)
        if r.status_code == 200:
            return True
        print(f"  ❌ /v1/setup/complete: {r.status_code} {r.text[:200]}")
        return False
    except Exception as e:
        print(f"  ❌ /v1/setup/complete error: {e}")
        return False


async def run_desktop_up(args: argparse.Namespace) -> int:
    """End-to-end: wipe → start backend in first-run → setup → launch desktop → login.

    Leaves backend + desktop running so a human (or agent) can drive the UI.
    This is the canonical repeatable path for getting a clean, logged-in
    desktop app up.
    """
    from .server_manager import ServerConfig, ServerManager

    print("🚀 CIRIS desktop-up")

    # 1. Clean slate
    print("[1/5] Stopping anything on 8080/8091 and wiping dev data...")
    _kill_port(args.port)
    _kill_port(args.desktop_port)
    subprocess.run(["pkill", "-9", "-f", "CIRIS-macos"], capture_output=True)
    subprocess.run(["pkill", "-9", "-f", "CIRIS-linux"], capture_output=True)
    time.sleep(1)
    _wipe_dev_data()

    # 2. Start backend in first-run mode
    # CIRIS_TESTING_MODE relaxes the setup validator that otherwise rejects 'admin'
    os.environ["CIRIS_TESTING_MODE"] = "true"
    print("[2/5] Starting backend (first-run mode, CIRIS_TESTING_MODE=true)...")
    cfg = ServerConfig(
        port=args.port,
        mock_llm=args.mock_llm,
        wipe_data=False,  # we already did it
        first_run_mode=True,
        startup_timeout=args.timeout,
    )
    server = ServerManager(cfg)
    status = server.start()
    if not status.running:
        print(f"  ❌ backend failed: {status.error}")
        return 1

    # 3. Complete setup
    print("[3/5] Completing setup wizard via /v1/setup/complete...")
    if not _complete_setup(server.base_url, args.mock_llm):
        server.stop()
        return 1
    print(f"  ✅ admin created: {TEST_ADMIN_USERNAME} / {TEST_ADMIN_PASSWORD}")

    # Restart backend without CIRIS_FORCE_FIRST_RUN so /v1/setup/status
    # returns is_first_run=false and the desktop goes to the Login screen,
    # not the Setup wizard.
    print("  🔄 restarting backend in configured mode...")
    server.stop()
    cfg2 = ServerConfig(
        port=args.port,
        mock_llm=args.mock_llm,
        wipe_data=False,
        first_run_mode=False,
        startup_timeout=args.timeout,
    )
    server = ServerManager(cfg2)
    status = server.start()
    if not status.running:
        print(f"  ❌ backend restart failed: {status.error}")
        return 1

    # 4. Launch desktop app
    if not args.no_desktop:
        print("[4/5] Launching desktop app (CIRIS_TEST_MODE=true)...")
        jar = _find_desktop_jar()
        if not jar:
            print("  ❌ No desktop jar found — run: cd mobile && ./gradlew :desktopApp:packageUberJarForCurrentOS")
            server.stop()
            return 1
        env = os.environ.copy()
        env["CIRIS_TEST_MODE"] = "true"
        env["CIRIS_TEST_PORT"] = str(args.desktop_port)
        env["CIRIS_API_URL"] = server.base_url
        log_path = Path("/tmp") / "ciris_desktop_up.log"
        with open(log_path, "w") as log:
            subprocess.Popen(
                ["java", "-jar", str(jar)],
                stdout=log,
                stderr=subprocess.STDOUT,
                env=env,
                start_new_session=True,
            )
        print(f"  logs: {log_path}")

        # Wait for test server
        deadline = time.time() + 60
        server_url = f"http://localhost:{args.desktop_port}"
        while time.time() < deadline:
            try:
                if requests.get(f"{server_url}/health", timeout=2).status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            print("  ⚠️  desktop test server didn't come up; continuing anyway")

        # 5. Log in via the UI
        print("[5/5] Logging in via UI...")
        helper = DesktopAppHelper(DesktopAppConfig(server_url=server_url))
        await helper.start()
        try:
            await helper.wait_for_screen("Login", timeout=60000)
            await helper.input_text("input_username", TEST_ADMIN_USERNAME)
            await helper.input_text("input_password", TEST_ADMIN_PASSWORD)
            await helper.click("btn_login_submit")
            # Any post-login screen is success
            deadline = time.time() + 30
            while time.time() < deadline:
                s = await helper.get_screen()
                if s and s != "Login":
                    print(f"  ✅ logged in → {s}")
                    break
                await asyncio.sleep(0.5)
            else:
                print("  ⚠️  still on Login after 30s")
        finally:
            await helper.stop()
    else:
        print("[4/5] Skipping desktop launch (--no-desktop)")

    print()
    print(f"✅ Ready. Backend: {server.base_url}  Desktop test server: http://localhost:{args.desktop_port}")
    print(f"   Admin: {TEST_ADMIN_USERNAME} / {TEST_ADMIN_PASSWORD}")
    print("   Processes left running — kill with: pkill -9 -f 'CIRIS-macos|main.py --adapter api'")
    return 0


async def run_desktop_tests(args: argparse.Namespace) -> int:
    """Run desktop app tests."""
    # Check if desktop app is running
    print("🔍 Checking CIRIS Desktop app...")
    server_url = f"http://localhost:{args.desktop_port}"

    if not await check_desktop_app_running(server_url):
        print(f"\n❌ CIRIS Desktop app is not running with test mode enabled.")
        print(f"\nTo start the desktop app with test mode:")
        print(f"  export CIRIS_TEST_MODE=true")
        print(f"  cd mobile && ./gradlew :desktopApp:run")
        return 1

    print("✅ Desktop app running with test mode")

    # Create and start runner
    config = DesktopAppConfig(
        server_url=server_url,
        screenshot_dir=args.output_dir,
    )
    runner = DesktopAppTestRunner(config=config, verbose=args.verbose)

    try:
        await runner.start()

        if args.command == "desktop":
            # Just show element tree
            await runner.test_element_tree()
            return 0

        elif args.command == "desktop-login":
            success = await runner.test_login_flow(
                username=args.username or "admin",
                password=args.password or "qa_test_password_12345",
            )
            runner.print_summary()
            return 0 if success else 1

        elif args.command == "desktop-chat":
            success = await runner.test_chat_flow(
                message=args.message or "Hello, can you hear me?",
            )
            runner.print_summary()
            return 0 if success else 1

    finally:
        await runner.stop()

    return 0


async def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Handle list command
    if args.command == "list":
        list_tests()
        return 0

    # Handle desktop-up (full orchestration: wipe → setup → launch → login)
    if args.command == "desktop-up":
        return await run_desktop_up(args)

    # Handle desktop commands (connect to already-running app)
    if args.command.startswith("desktop"):
        return await run_desktop_tests(args)

    # Legacy browser-based testing
    # Ensure Playwright is installed
    print("🔍 Checking Playwright installation...")
    try:
        ensure_playwright_installed()
        print("✅ Playwright ready")
    except Exception as e:
        print(f"❌ Playwright setup failed: {e}")
        print("   Run: pip install playwright && playwright install firefox")
        return 1

    # Build configs
    server_config = ServerConfig(
        port=args.port,
        wipe_data=args.wipe and not args.no_wipe,
        mock_llm=args.mock_llm,
        startup_timeout=args.timeout,
    )

    browser_config = BrowserConfig(
        headless=args.headless,
        slow_mo=args.slow_mo,
        screenshot_dir=args.output_dir,
    )

    test_config = WebUITestConfig.from_env()
    test_config.llm_provider = args.provider

    if args.api_key:
        test_config.llm_api_key = args.api_key

    if args.model:
        test_config.llm_model = args.model

    # Get tests to run
    tests = get_test_list(args.command, args.tests)

    # Create runner
    runner = WebUITestRunner(
        server_config=server_config,
        browser_config=browser_config,
        test_config=test_config,
        keep_open=args.keep_open,
    )

    # Run tests
    if tests:
        suite = await runner.run_selected_tests(tests)
    else:
        suite = await runner.run_e2e_flow()

    # Print summary and save report
    runner.print_summary(suite)
    report_path = runner.save_report(suite)
    print(f"📄 Report saved: {report_path}")

    return 0 if suite.success else 1


def run() -> None:
    """Entry point for console script."""
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
        sys.exit(130)


if __name__ == "__main__":
    run()
