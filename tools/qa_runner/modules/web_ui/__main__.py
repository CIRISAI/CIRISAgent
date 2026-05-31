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
from typing import Dict, List, Optional

import requests

from .browser_helper import BrowserConfig, ensure_playwright_installed
from .desktop_app_helper import DesktopAppConfig, DesktopAppHelper, check_desktop_app_running
from .federation_walk_test import FederationWalkTest
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
            "federation",
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

    # Federation walk-test options
    parser.add_argument(
        "--launch",
        action="store_true",
        help="For federation: wipe + launch backend + desktop app before walking (full bring-up)",
    )
    parser.add_argument(
        "--json-report",
        default=None,
        help="For federation: write the FederationWalkReport JSON to this path",
    )
    parser.add_argument(
        "--android",
        action="store_true",
        help="For federation --launch: target an Android emulator instead of the desktop app. "
        "Starts/discovers an emulator, installs the debug APK, port-forwards 8091→9091, "
        "then runs the walk-test against the Android TestAutomationServer.",
    )
    parser.add_argument(
        "--android-avd",
        default="Medium_Phone_API_36.1_2",
        help="AVD name to boot when no emulator is running (default: Medium_Phone_API_36.1_2)",
    )
    parser.add_argument(
        "--android-device",
        default=None,
        help="Explicit ADB device serial to target (default: first emulator-* device)",
    )
    parser.add_argument(
        "--ios",
        action="store_true",
        help="For federation --launch: target a physical iOS device instead of the desktop app. "
        "Launches ai.ciris.mobile with CIRIS_TEST_MODE=true via devicectl, then iproxy-forwards "
        "host:18091→device:9091 (test server) and host:18080→device:8080 (embedded backend). "
        "Walk-test points at the forwarded ports.",
    )
    parser.add_argument(
        "--ios-device-id",
        default=None,
        help="For --ios: specific physical-device UDID (libimobiledevice). "
        "If unset, the first connected device is used.",
    )
    parser.add_argument(
        "--ios-bundle-id",
        default="ai.ciris.mobile",
        help="For --ios: bundle ID to launch (default: ai.ciris.mobile).",
    )
    parser.add_argument(
        "--api-port",
        type=int,
        default=None,
        help="Backend API port the walk-test queries for state assertions. "
        "Defaults: 8080 for desktop/android, 18080 for --ios. Set explicitly to override.",
    )

    args = parser.parse_args()
    _apply_platform_defaults(args)
    return args


def _apply_platform_defaults(args: argparse.Namespace) -> None:
    """Fill in port defaults that depend on the target platform.

    - desktop (default): test-server :8091, API :8080
    - --android:          test-server :8091 forwards to device :9091; API :8080→8080
    - --ios:              test-server :18091→9091; API :18080→8080 (iproxy convention)

    Honors any explicit user override (--desktop-port / --api-port).
    """
    if getattr(args, "ios", False):
        # iOS uses the iproxy 18xxx convention to avoid collision with any
        # locally-running host backend. Bump defaults only if the user hasn't
        # explicitly overridden them.
        if args.desktop_port == 8091:
            args.desktop_port = 18091
        if args.api_port is None:
            args.api_port = 18080
    if args.api_port is None:
        args.api_port = 8080


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
        glob.glob(str(repo_root / "client" / "desktopApp" / "build" / "compose" / "jars" / "CIRIS-*.jar")),
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


ANDROID_PACKAGE = "ai.ciris.mobile.debug"
ANDROID_ACTIVITY = "ai.ciris.mobile.MainActivity"


def _android_sdk_paths() -> Dict[str, Path]:
    """Locate the Android SDK binaries we need."""
    sdk_root = Path(os.environ.get("ANDROID_SDK_ROOT", "")) if os.environ.get("ANDROID_SDK_ROOT") else None
    if not sdk_root or not sdk_root.exists():
        sdk_root = Path.home() / "Android" / "Sdk"
    return {
        "adb": sdk_root / "platform-tools" / "adb",
        "emulator": sdk_root / "emulator" / "emulator",
    }


def _adb(args: List[str], serial: Optional[str] = None, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run an adb command, optionally targeting a specific device serial."""
    paths = _android_sdk_paths()
    cmd: List[str] = [str(paths["adb"])]
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _adb_devices(only_ready: bool = True) -> List[str]:
    """Return list of device serials; if only_ready, filter to 'device' state."""
    out = _adb(["devices"]).stdout
    serials: List[str] = []
    for line in out.strip().splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            serial, state = parts[0], parts[1]
            if (not only_ready) or state == "device":
                serials.append(serial)
    return serials


def _pick_emulator_serial(preferred: Optional[str] = None) -> Optional[str]:
    """Pick an emulator serial; prefer the explicit one, else the first emulator-* device."""
    serials = _adb_devices(only_ready=True)
    if preferred and preferred in serials:
        return preferred
    for s in serials:
        if s.startswith("emulator-"):
            return s
    return None


def _wait_for_boot(serial: str, timeout: int = 120) -> bool:
    """Poll until the emulator is fully booted (sys.boot_completed == 1)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = _adb(["shell", "getprop", "sys.boot_completed"], serial=serial, timeout=5)
            if r.stdout.strip() == "1":
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def _start_emulator(avd: str) -> Optional[subprocess.Popen]:
    """Start the named AVD as a background process. Returns the Popen handle."""
    paths = _android_sdk_paths()
    if not paths["emulator"].exists():
        print(f"  ❌ emulator binary not found at {paths['emulator']}")
        return None
    cmd = [
        str(paths["emulator"]),
        "-avd",
        avd,
        "-no-snapshot-save",
        "-no-audio",
        "-no-boot-anim",
    ]
    log_path = Path("/tmp") / "ciris_android_emulator.log"
    log_file = open(log_path, "w")
    print(f"  emulator: starting {avd} (log: {log_path})")
    return subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, start_new_session=True)


def _ensure_emulator(args: argparse.Namespace) -> Optional[str]:
    """Make sure an emulator is up. Returns its adb serial, or None on failure."""
    # Already running?
    serial = _pick_emulator_serial(args.android_device)
    if serial:
        print(f"  emulator already up: {serial}")
        return serial

    # No emulator → boot the requested AVD.
    paths = _android_sdk_paths()
    list_out = subprocess.run([str(paths["emulator"]), "-list-avds"], capture_output=True, text=True, timeout=10).stdout
    avds = [a.strip() for a in list_out.splitlines() if a.strip()]
    if not avds:
        print("  ❌ no AVDs configured — create one with `avdmanager create avd ...`")
        return None
    avd = args.android_avd if args.android_avd in avds else avds[0]
    if avd != args.android_avd:
        print(f"  ⚠️  AVD '{args.android_avd}' not found, using '{avd}'")

    if _start_emulator(avd) is None:
        return None

    # Wait for the device to appear in adb.
    deadline = time.time() + 90
    while time.time() < deadline:
        serial = _pick_emulator_serial(args.android_device)
        if serial:
            break
        time.sleep(2)
    else:
        print("  ❌ emulator did not appear in adb within 90s")
        return None

    print(f"  emulator: {serial} attached, waiting for boot…")
    if not _wait_for_boot(serial, timeout=180):
        print("  ❌ emulator never finished booting")
        return None
    print(f"  emulator: {serial} booted")
    return serial


def _find_debug_apk() -> Optional[Path]:
    repo_root = Path(__file__).resolve().parents[4]
    candidate = repo_root / "client" / "androidApp" / "build" / "outputs" / "apk" / "debug" / "androidApp-debug.apk"
    return candidate if candidate.exists() else None


def _build_debug_apk() -> bool:
    repo_root = Path(__file__).resolve().parents[4]
    client_dir = repo_root / "client"
    print("  building debug APK (./gradlew :androidApp:assembleDebug)…")
    r = subprocess.run(
        ["./gradlew", ":androidApp:assembleDebug"],
        cwd=str(client_dir),
        capture_output=True,
        text=True,
        timeout=600,
    )
    if r.returncode != 0:
        print(f"  ❌ gradle build failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
        return False
    return True


async def run_android_up(args: argparse.Namespace) -> int:
    """Bring up an Android emulator running the debug APK in test mode.

    Architectural note: the Android app embeds its own Python backend via
    Chaquopy and PythonRuntimeService, listening on the emulator's
    localhost:8080. Unlike the desktop path, we do NOT start a host-side
    backend — it would never be reachable from the emulator. Instead we
    forward host:8080 → emulator:8080 so the federation walk-test's API
    state checks (POST /v1/auth/login, GET /v1/system/agent-mode) land on
    the device's own backend. Setup wizard runs on the device on first
    boot; if the test environment isn't already configured, the walk-test
    will fail at login — that's a real diagnostic the surface needs to
    expose.

    Steps:
      1. Discover or boot an Android emulator.
      2. Build the debug APK if missing.
      3. Force-stop + install + launch with debug.CIRIS_TEST_MODE=true
         (debug builds also flip BuildConfig.TEST_MODE_ENABLED on).
      4. `adb forward tcp:8091 tcp:9091` — TestAutomationServer.
         `adb forward tcp:8080 tcp:8080` — embedded backend (best-effort).
      5. Poll http://localhost:8091/health for {"status":"ok"}.
    """
    print("🤖 CIRIS android-up")

    # 1. Emulator.
    print("[1/5] Discovering / booting Android emulator…")
    serial = _ensure_emulator(args)
    if not serial:
        return 1

    # Free host ports we plan to forward into the emulator. If a host backend
    # or stale forward is bound to 8080/8091, the new adb forward will fail
    # silently (overwriting the old map) or — worse — collide with a real
    # listener and confuse the walk-test about whose API it's hitting.
    _kill_port(args.port)
    _kill_port(args.desktop_port)
    try:
        _adb(["forward", "--remove", f"tcp:{args.desktop_port}"], serial=serial, timeout=5)
        _adb(["forward", "--remove", f"tcp:{args.port}"], serial=serial, timeout=5)
    except Exception:
        pass

    # 2. APK.
    apk = _find_debug_apk()
    if not apk:
        print("  debug APK missing — building")
        if not _build_debug_apk():
            return 1
        apk = _find_debug_apk()
    if not apk:
        print("  ❌ debug APK still missing after build")
        return 1
    print(f"  apk: {apk} ({apk.stat().st_size // (1024 * 1024)} MB)")

    # 3. Install + launch.
    print("[2/5] Installing APK and launching with CIRIS_TEST_MODE=true…")
    _adb(["shell", "am", "force-stop", ANDROID_PACKAGE], serial=serial, timeout=15)
    install = _adb(["install", "-r", str(apk)], serial=serial, timeout=300)
    if "Success" not in install.stdout:
        print(f"  ❌ install failed:\n{install.stdout}\n{install.stderr}")
        return 1
    print("  install: ok")

    # Debug builds flip TEST_MODE_ENABLED=true automatically; set the prop
    # too in case anyone is testing a release build via adb.
    _adb(["shell", "setprop", "debug.CIRIS_TEST_MODE", "true"], serial=serial, timeout=10)

    launch = _adb(
        ["shell", "am", "start", "-n", f"{ANDROID_PACKAGE}/{ANDROID_ACTIVITY}", "--es", "CIRIS_TEST_MODE", "true"],
        serial=serial,
        timeout=15,
    )
    if launch.returncode != 0:
        print(f"  ❌ launch failed: {launch.stderr}")
        return 1
    print("  launch: ok")

    # 4. Port forward host:8091 → device:9091 (test server) AND
    #    host:8080 → device:8080 (embedded backend).
    print("[3/5] Configuring adb port-forwards…")
    forward = _adb(["forward", f"tcp:{args.desktop_port}", "tcp:9091"], serial=serial, timeout=10)
    if forward.returncode != 0:
        print(f"  ❌ adb forward {args.desktop_port}→9091 failed: {forward.stderr}")
        return 1
    print(f"  forward: host:{args.desktop_port} → {serial}:9091 (test server)")

    forward_api = _adb(["forward", f"tcp:{args.port}", f"tcp:{args.port}"], serial=serial, timeout=10)
    if forward_api.returncode == 0:
        print(f"  forward: host:{args.port} → {serial}:{args.port} (embedded backend)")
    else:
        print(
            f"  ⚠️  adb forward {args.port}→{args.port} failed: {forward_api.stderr.strip()}\n"
            "       backend-state assertions in the walk-test will fail; walk continues."
        )

    # 5. Poll /health.
    print("[4/5] Waiting for AndroidTestAutomationServer to come up…")
    server_url = f"http://localhost:{args.desktop_port}"
    deadline = time.time() + 90
    healthy = False
    while time.time() < deadline:
        try:
            r = requests.get(f"{server_url}/health", timeout=2)
            if r.status_code == 200 and r.json().get("status") == "ok":
                healthy = True
                break
        except Exception:
            pass
        time.sleep(2)
    if not healthy:
        print(
            "  ⚠️  /health did not respond within 90s — the test server may not have started.\n"
            "       Common causes: BuildConfig.TEST_MODE_ENABLED is false on this build, or the app\n"
            "       crashed during init. Inspect with: adb logcat -d *:E"
        )
        return 1
    print(f"  ✅ AndroidTestAutomationServer reachable at {server_url}")

    # Best-effort: wait for the device's embedded Python backend too. The
    # mode-change flow in the walk-test depends on it; if it's still booting,
    # the walk will degrade to UI-only assertions.
    print("[5/5] Best-effort wait on embedded Python backend…")
    backend_ok = False
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            r = requests.get(f"http://localhost:{args.port}/v1/system/health", timeout=2)
            if r.status_code in (200, 401, 403):
                backend_ok = True
                break
        except Exception:
            pass
        time.sleep(2)
    if backend_ok:
        print(f"  ✅ embedded backend reachable at http://localhost:{args.port}")
    else:
        print(
            f"  ⚠️  embedded backend not yet ready at http://localhost:{args.port};\n"
            "       walk will proceed but mode-change API assertions may fail."
        )

    # Stash serial for teardown.
    args._android_serial = serial  # type: ignore[attr-defined]
    return 0


def _android_teardown(args: argparse.Namespace, keep_open: bool) -> None:
    """Best-effort: remove the adb forwards and (optionally) force-stop the app."""
    serial = getattr(args, "_android_serial", None)
    if not serial:
        return
    for host_port in (args.desktop_port, args.port):
        try:
            _adb(["forward", "--remove", f"tcp:{host_port}"], serial=serial, timeout=5)
        except Exception:
            pass
    if not keep_open:
        try:
            _adb(["shell", "am", "force-stop", ANDROID_PACKAGE], serial=serial, timeout=10)
        except Exception:
            pass


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
            print("  ❌ No desktop jar found — run: cd client && ./gradlew :desktopApp:packageUberJarForCurrentOS")
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


_IOS_IPROXY_PROCS: List[subprocess.Popen] = []


def _kill_iproxy_children() -> None:
    """Tear down every iproxy process spawned by run_ios_up().

    Idempotent — atexit may invoke this twice on abnormal exit paths.
    """
    while _IOS_IPROXY_PROCS:
        p = _IOS_IPROXY_PROCS.pop()
        try:
            p.terminate()
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
        except Exception:
            pass


async def run_ios_up(args: argparse.Namespace) -> int:
    """End-to-end iOS bring-up: devicectl process launch + iproxy forwards.

    Unlike run_desktop_up (which wipes data + completes setup), the iOS
    flow assumes the device app is already configured — device data is
    sovereign. We just:
      1. Pick the connected device (or honor --ios-device-id)
      2. devicectl process launch --terminate-existing with CIRIS_TEST_MODE=true
      3. Spawn iproxy <desktop_port>->9091 (iOS test server) and iproxy <api_port>->8080
      4. Poll both /health endpoints until ready (or fail)

    iproxy children are registered for cleanup at process exit; killing
    the runner SIGTERMs them so we don't leak port-forwards.
    """
    import atexit

    from ..mobile.ios.idevice_helper import IDeviceHelper

    print("📱 CIRIS ios-up")

    # 1. Resolve device
    # iOS has TWO UDIDs per device, depending on which tool is asking:
    #   - CoreDevice UUID (e.g. "A53DA92F-972A-5A28-86E3-E6E86E02EE79") — used by xcrun devicectl
    #   - libimobiledevice UDID (e.g. "00008110-0016395C1ED9401E") — used by iproxy, ideviceinstaller
    # We need both: devicectl for launching the app, iproxy for port-forwarding.
    try:
        ios = IDeviceHelper(device_id=args.ios_device_id)
    except RuntimeError as e:
        print(f"  ❌ {e}")
        return 1
    devices = ios.get_devices()
    if not devices:
        print("  ❌ No physical iOS device connected. Plug in + trust, then retry.")
        return 1
    # CoreDevice UUID for devicectl
    devicectl_udid = args.ios_device_id or devices[0].identifier
    # libimobiledevice UDID for iproxy — query idevice_id directly
    try:
        idev_result = subprocess.run(["idevice_id", "-l"], capture_output=True, text=True, timeout=10)
        iproxy_udid = idev_result.stdout.strip().splitlines()[0] if idev_result.stdout.strip() else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        iproxy_udid = None
    if not iproxy_udid:
        print(
            "  ❌ Cannot resolve libimobiledevice UDID via `idevice_id -l`. "
            "Install libimobiledevice (brew install libimobiledevice)."
        )
        return 1
    print(f"[1/4] device: devicectl={devicectl_udid}  iproxy={iproxy_udid}")

    # 2. devicectl process launch with test-mode env vars.
    # CIRIS_TEST_MODE  → enables the iOS POSIX test-automation server on :9091
    # CIRIS_TESTING_MODE → relaxes the setup validator so 'admin' / qa creds
    #                      are accepted by /v1/setup/complete (mirrors what
    #                      run_desktop_up sets via os.environ on the host).
    IOS_TEST_ENV = '{"CIRIS_TEST_MODE":"true","CIRIS_TESTING_MODE":"true"}'
    print(f"[2/4] Launching {args.ios_bundle_id} (CIRIS_TEST_MODE=true, CIRIS_TESTING_MODE=true)...")
    launch_cmd = [
        "xcrun",
        "devicectl",
        "device",
        "process",
        "launch",
        "--device",
        devicectl_udid,
        "--terminate-existing",
        "--environment-variables",
        IOS_TEST_ENV,
        args.ios_bundle_id,
    ]
    try:
        result = subprocess.run(
            launch_cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        print("  ❌ devicectl process launch timed out after 60s")
        return 1
    if result.returncode != 0:
        print(f"  ❌ devicectl process launch failed: {result.stderr.strip() or result.stdout.strip()}")
        return 1
    print("  ✅ app launched")

    # 3. iproxy forwards — test-automation server + backend
    # iOS POSIX test server runs on device :9091 (matches Android emulator port,
    # NOT the desktop :8091 — see TestAutomationServer.ios.kt). Backend on :8080.
    IOS_TEST_REMOTE_PORT = 9091
    IOS_BACKEND_REMOTE_PORT = 8080
    print(
        f"[3/4] iproxy {args.desktop_port}->{IOS_TEST_REMOTE_PORT} "
        f"and {args.api_port}->{IOS_BACKEND_REMOTE_PORT}..."
    )
    atexit.register(_kill_iproxy_children)
    for local_port, remote_port, label in (
        (args.desktop_port, IOS_TEST_REMOTE_PORT, "test-automation"),
        (args.api_port, IOS_BACKEND_REMOTE_PORT, "backend api"),
    ):
        try:
            proc = subprocess.Popen(
                ["iproxy", str(local_port), str(remote_port), "-u", iproxy_udid],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            print("  ❌ iproxy not found. Install libimobiledevice (brew install libimobiledevice).")
            _kill_iproxy_children()
            return 1
        _IOS_IPROXY_PROCS.append(proc)
        print(f"  ✅ iproxy {local_port}->{remote_port} ({label}) pid={proc.pid}")
        # Brief settle — iproxy needs a moment before the first connect
        await asyncio.sleep(0.4)

    # 4. Poll both endpoints until healthy
    print("[4/4] Waiting for test-automation + backend to respond...")
    test_url = f"http://localhost:{args.desktop_port}/health"
    api_url = f"http://localhost:{args.api_port}/v1/system/health"
    deadline = time.time() + 60
    test_ok = api_ok = False
    while time.time() < deadline:
        if not test_ok:
            try:
                if requests.get(test_url, timeout=2).status_code == 200:
                    test_ok = True
                    print(f"  ✅ test-automation up at {test_url}")
            except Exception:
                pass
        if not api_ok:
            try:
                # backend health may return 200 OR 503 (degraded) — both prove the
                # process is up and forwarding; the walk-test will surface real
                # health from its own state assertions.
                if requests.get(api_url, timeout=2).status_code in (200, 503):
                    api_ok = True
                    print(f"  ✅ backend api up at {api_url}")
            except Exception:
                pass
        if test_ok and api_ok:
            break
        await asyncio.sleep(1)

    if not test_ok:
        print(f"  ❌ test-automation did not respond at {test_url} within 60s")
        _kill_iproxy_children()
        return 1
    if not api_ok:
        print(f"  ⚠️  backend api did not respond at {api_url} within 60s — walk will still try")

    # 5. First-run detection + auto-setup. If the device is at the Setup wizard,
    # the walk-test's login step will fail (no input_username on a Setup screen).
    # Hit /v1/setup/status via the iproxy-forwarded backend; if first_run is true,
    # POST /v1/setup/complete with the standard QA admin creds, then re-launch the
    # app so StartupViewModel re-checks status and routes to Login.
    api_base = f"http://localhost:{args.api_port}"
    if not await _ios_complete_setup_if_needed(
        api_base=api_base,
        devicectl_udid=devicectl_udid,
        bundle_id=args.ios_bundle_id,
        test_url=test_url,
        api_url=api_url,
    ):
        # Setup failed or relaunch didn't come back healthy. Bail with cleanup.
        _kill_iproxy_children()
        return 1

    print()
    print(
        f"✅ Ready. iOS test-automation: http://localhost:{args.desktop_port}  Backend: http://localhost:{args.api_port}"
    )
    return 0


async def _ios_complete_setup_if_needed(
    api_base: str,
    devicectl_udid: str,
    bundle_id: str,
    test_url: str,
    api_url: str,
) -> bool:
    """If the iOS device is at the Setup wizard, complete setup via API
    and re-launch the app so the UI routes to Login.

    Returns True if the device is ready (already configured OR successfully
    set up + relaunched), False on a real failure that should abort bring-up.

    The relaunch is necessary because iOS StartupViewModel only checks
    /v1/setup/status once at startup; without it, the UI stays on the
    Setup screen even though the backend has been told setup is complete.
    """
    # Probe setup status
    try:
        r = requests.get(f"{api_base}/v1/setup/status", timeout=5)
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️  /v1/setup/status probe failed: {e} — assuming configured, walk may fail at login")
        return True
    if r.status_code != 200:
        print(f"  ⚠️  /v1/setup/status returned {r.status_code} — assuming configured, walk may fail at login")
        return True
    data = r.json().get("data", r.json())  # tolerate either envelope
    first_run = bool(data.get("first_run") or data.get("firstRun") or data.get("is_first_run"))
    if not first_run:
        print(f"  ℹ️  device already configured (first_run=false) — skipping setup")
        return True

    # Device needs setup. POST /v1/setup/complete with QA creds.
    print(f"  🛠  device is first-run — completing setup via {api_base}/v1/setup/complete")
    payload = {
        # On iOS the embedded backend runs without mock-llm — use a placeholder
        # OpenAI config; the walk-test doesn't exercise the LLM path.
        "llm_provider": "openai",
        "llm_api_key": "test-key-for-ios-walk",
        "llm_model": "gpt-4",
        "template_id": "default",
        "enabled_adapters": ["api"],
        "adapter_config": {},
        "admin_username": TEST_ADMIN_USERNAME,
        "admin_password": TEST_ADMIN_PASSWORD,
        # agent_port is the *embedded* backend's port (always 8080 inside the
        # device sandbox), not the host-side iproxy-forwarded port.
        "agent_port": 8080,
    }
    try:
        r = requests.post(f"{api_base}/v1/setup/complete", json=payload, timeout=30)
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ /v1/setup/complete error: {e}")
        return False
    if r.status_code != 200:
        print(f"  ❌ /v1/setup/complete returned {r.status_code}: {r.text[:300]}")
        return False
    print(f"  ✅ setup completed — admin user '{TEST_ADMIN_USERNAME}' created")

    # Re-launch the app so the StartupViewModel re-checks setup status.
    # iproxy children stay running — the kernel-level forward survives the
    # app restart, the iOS-side socket gets rebound when the app comes back.
    print(f"  🔄 re-launching {bundle_id} so the UI routes to Login...")
    relaunch_cmd = [
        "xcrun",
        "devicectl",
        "device",
        "process",
        "launch",
        "--device",
        devicectl_udid,
        "--terminate-existing",
        # Keep both env vars on the relaunch — TESTING_MODE no longer
        # strictly needed (setup already complete) but harmless, and
        # consistent with the initial launch is easier to reason about.
        "--environment-variables",
        '{"CIRIS_TEST_MODE":"true","CIRIS_TESTING_MODE":"true"}',
        bundle_id,
    ]
    try:
        result = subprocess.run(relaunch_cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        print("  ❌ devicectl re-launch timed out after 60s")
        return False
    if result.returncode != 0:
        print(f"  ❌ re-launch failed: {result.stderr.strip() or result.stdout.strip()}")
        return False

    # Wait for both endpoints to come back. Same loop shape as the initial poll
    # — but with a longer test-automation timeout, because Compose has to do a
    # full re-mount before the embedded server rebinds :9091.
    print("  ⏳ waiting for test-automation + backend to come back after re-launch...")
    loop = asyncio.get_event_loop()
    deadline = loop.time() + 90
    test_ok = api_ok = False
    while loop.time() < deadline:
        if not test_ok:
            try:
                if requests.get(test_url, timeout=2).status_code == 200:
                    test_ok = True
                    print("  ✅ test-automation back up after re-launch")
            except Exception:
                pass
        if not api_ok:
            try:
                if requests.get(api_url, timeout=2).status_code in (200, 503):
                    api_ok = True
                    print("  ✅ backend api back up after re-launch")
            except Exception:
                pass
        if test_ok and api_ok:
            return True
        await asyncio.sleep(1)
    print(f"  ❌ post-setup re-launch did not come back healthy (test_ok={test_ok}, api_ok={api_ok})")
    return False


async def run_federation_walk(args: argparse.Namespace) -> int:
    """Walk the federation Network screens via the test-automation server.

    Targets the Compose-Desktop app (default) or a physical iOS device
    (`--platform ios`). On iOS the test-automation server runs in the
    embedded Beeware Python; iproxy forwards device:9091/8080 to host
    :18091/:18080. The walk itself is platform-agnostic — only the
    transport URLs and bring-up path differ.

    Exit codes:
        0 — all walk steps PASS
        1 — at least one FAIL / ERROR (or only-SKIP outside of expected cascade)
        2 — cannot reach the test-automation server
    """
    server_url = f"http://localhost:{args.desktop_port}"
    api_base_url = f"http://localhost:{args.api_port}"
    is_android = bool(getattr(args, "android", False))
    is_ios = bool(getattr(args, "ios", False))
    if is_android and is_ios:
        print("federation: --android and --ios are mutually exclusive")
        return 2
    target_label = "android emulator" if is_android else "ios device" if is_ios else "desktop app"

    # Optional full bring-up: backend + client, then walk.
    if args.launch:
        if is_android:
            print("federation: --launch --android — emulator + adb-forward bring-up")
            rc = await run_android_up(args)
        elif is_ios:
            print("federation: --launch --ios — devicectl + iproxy bring-up")
            rc = await run_ios_up(args)
        else:
            print("federation: --launch requested, bringing up backend + desktop first")
            rc = await run_desktop_up(args)
        if rc != 0:
            print(f"federation: bring-up failed (rc={rc})")
            return rc

    # Verify reachability
    print(f"federation: checking {target_label} test-automation server at {server_url}")
    if not await check_desktop_app_running(server_url):
        print()
        print(f"FATAL: cannot reach the {target_label}'s test-automation server at {server_url}.")
        if is_android:
            print("       Either re-run with --launch --android, or manually:")
            print("         ~/Android/Sdk/platform-tools/adb shell am force-stop ai.ciris.mobile.debug")
            print("         ~/Android/Sdk/platform-tools/adb install -r androidApp-debug.apk")
            print(
                "         ~/Android/Sdk/platform-tools/adb shell am start -n ai.ciris.mobile.debug/ai.ciris.mobile.MainActivity"
            )
            print(f"         ~/Android/Sdk/platform-tools/adb forward tcp:{args.desktop_port} tcp:9091")
        elif is_ios:
            print("       Make sure the iOS app is running with CIRIS_TEST_MODE=true")
            print("       and that iproxy is forwarding the device's :9091/:8080:")
            print()
            print("         xcrun devicectl device process launch -d <UDID> \\")
            print("           --terminate-existing \\")
            print('           --environment-variables \'{"CIRIS_TEST_MODE":"true"}\' \\')
            print("           ai.ciris.mobile")
            print(f"         iproxy {args.desktop_port} 9091 -u <UDID> &")
            print(f"         iproxy {args.api_port} 8080 -u <UDID> &")
            print()
            print("       or use --launch --ios to bring it all up automatically.")
        else:
            print("       Start the desktop app with CIRIS_TEST_MODE=true first, e.g.:")
            print("         export CIRIS_TEST_MODE=true")
            print("         cd client && ./gradlew :desktopApp:run")
            print("       or use --launch to bring up the full stack.")
        return 2

    config = DesktopAppConfig(
        server_url=server_url,
        screenshot_dir=args.output_dir,
    )
    helper = DesktopAppHelper(config)
    await helper.start()
    try:
        walker = FederationWalkTest(
            helper=helper,
            verbose=args.verbose,
            login_username=args.username or "admin",
            login_password=args.password or "qa_test_password_12345",
            api_base_url=api_base_url,
        )
        report = await walker.run()
    finally:
        await helper.stop()
        if is_android and args.launch:
            _android_teardown(args, keep_open=args.keep_open)

    # Output
    report.print_summary()
    if args.json_report:
        Path(args.json_report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_report).write_text(report.to_json())
        print(f"federation: JSON report written to {args.json_report}")

    if report.all_passed:
        return 0
    return 1


async def run_desktop_tests(args: argparse.Namespace) -> int:
    """Run desktop app tests."""
    # Check if desktop app is running
    print("🔍 Checking CIRIS Desktop app...")
    server_url = f"http://localhost:{args.desktop_port}"

    if not await check_desktop_app_running(server_url):
        print(f"\n❌ CIRIS Desktop app is not running with test mode enabled.")
        print(f"\nTo start the desktop app with test mode:")
        print(f"  export CIRIS_TEST_MODE=true")
        print(f"  cd client && ./gradlew :desktopApp:run")
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

    # Federation Network screen walk-test
    if args.command == "federation":
        return await run_federation_walk(args)

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
