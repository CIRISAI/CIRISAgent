"""
iOS Physical Device Test Cases for CIRIS App

Test cases for physical iOS devices using:
- pymobiledevice3 screenshots + Vision OCR for UI verification
- iproxy port forwarding + HTTP API calls for backend verification
- The in-app test-automation HTTP server (port 9091, gated by
  ``CIRIS_TEST_MODE=true``) for real UI interaction via testTag identifiers

API-only tests stay read-only via OCR. The UI-login flow restarts the app
with ``CIRIS_TEST_MODE=true``, forwards port 19091 → 9091 via iproxy, and
drives Compose testTags directly.
"""

import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Tuple

from .ios.idevice_helper import IDeviceHelper
from .ios.vision_helper import TextRegion, VisionHelper
from .test_cases import TestReport, TestResult


class PhysicalDeviceUIHelper:
    """OCR-based UI verification for physical iOS devices.

    Uses pymobiledevice3 screenshots + macOS Vision OCR.
    Read-only — no tap/swipe/input (not supported on physical devices
    without WebDriverAgent).
    """

    def __init__(self, helper: IDeviceHelper):
        self.helper = helper
        self.vision = VisionHelper()
        self._cached_regions: List[TextRegion] = []
        self._screenshot_counter = 0

    def screenshot(self, output_path: Optional[str] = None) -> Optional[str]:
        """Take screenshot and return path."""
        self._screenshot_counter += 1
        if not output_path:
            output_path = f"/tmp/ciris_phys_screen_{self._screenshot_counter}.png"
        ok = self.helper.screenshot(output_path)
        return output_path if ok else None

    def refresh(self) -> List[TextRegion]:
        """Take fresh screenshot and run OCR."""
        path = self.screenshot()
        if path:
            self._cached_regions = self.vision.recognize_text(path)
        else:
            self._cached_regions = []
        return self._cached_regions

    def get_screen_text(self) -> List[str]:
        """Get all visible text on screen."""
        if not self._cached_regions:
            self.refresh()
        return [r.text for r in self._cached_regions]

    def is_text_visible(self, text: str, exact: bool = False) -> bool:
        """Check if text is visible."""
        if not self._cached_regions:
            self.refresh()
        text_lower = text.lower()
        for region in self._cached_regions:
            if exact:
                if region.text == text:
                    return True
            else:
                if text_lower in region.text.lower():
                    return True
        return False

    def wait_for_text(self, text: str, timeout: float = 30.0, interval: float = 2.0) -> bool:
        """Wait for text to appear on screen."""
        start = time.time()
        while time.time() - start < timeout:
            self._cached_regions = []  # Force refresh
            if self.is_text_visible(text):
                return True
            time.sleep(interval)
        return False


class APIClient:
    """Simple HTTP client for CIRIS API via iproxy."""

    def __init__(self, base_url: str = "http://127.0.0.1:18080", token: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.is_first_run = False

    def _request(self, method: str, path: str, data: Optional[dict] = None, timeout: int = 10) -> Tuple[int, dict]:
        """Make HTTP request and return (status_code, json_body)."""
        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body_bytes = resp.read()
                try:
                    return resp.status, json.loads(body_bytes)
                except json.JSONDecodeError:
                    return resp.status, {"raw": body_bytes.decode("utf-8", errors="replace")}
        except urllib.error.HTTPError as e:
            try:
                body_bytes = e.read()
                return e.code, json.loads(body_bytes)
            except (json.JSONDecodeError, Exception):
                return e.code, {"error": str(e)}
        except urllib.error.URLError as e:
            return 0, {"error": str(e)}
        except Exception as e:
            return 0, {"error": str(e)}

    def get(self, path: str, timeout: int = 10) -> Tuple[int, dict]:
        return self._request("GET", path, timeout=timeout)

    def post(self, path: str, data: Optional[dict] = None, timeout: int = 10) -> Tuple[int, dict]:
        return self._request("POST", path, data=data, timeout=timeout)

    def check_first_run(self) -> bool:
        """Check if the app is in first-run setup state."""
        status, body = self.get("/v1/setup/status", timeout=5)
        if status == 200:
            data = body.get("data", body)
            self.is_first_run = data.get("is_first_run", False) or data.get("setup_required", False)
            return self.is_first_run
        return False

    def login(self, username: str = "admin", password: str = "qa_test_password_12345") -> bool:
        """Login and store token. Falls back to first-run check on failure."""
        status, body = self.post("/v1/auth/login", {"username": username, "password": password})
        if status == 200 and "access_token" in body:
            self.token = body["access_token"]
            return True
        # Check if first-run state (no users exist yet)
        self.check_first_run()
        return False


# ========== Test Cases ==========


def test_physical_screenshot(helper: IDeviceHelper, ui: PhysicalDeviceUIHelper, config: dict) -> TestReport:
    """Test: Take a screenshot of the physical device and verify OCR works."""
    start_time = time.time()
    screenshots = []

    try:
        print("  [1/2] Taking screenshot...")
        path = ui.screenshot(f"/tmp/ciris_phys_test_{int(time.time())}.png")
        if not path:
            return TestReport(
                name="test_physical_screenshot",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="pymobiledevice3 screenshot failed (is tunneld running?)",
            )
        screenshots.append(path)

        print("  [2/2] Running OCR...")
        ui.refresh()
        texts = ui.get_screen_text()

        return TestReport(
            name="test_physical_screenshot",
            result=TestResult.PASSED,
            duration=time.time() - start_time,
            message=f"Screenshot OK, OCR found {len(texts)} text regions. Sample: {texts[:5]}",
            screenshots=screenshots,
        )

    except Exception as e:
        return TestReport(
            name="test_physical_screenshot",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
            screenshots=screenshots,
        )


def test_physical_app_state(helper: IDeviceHelper, ui: PhysicalDeviceUIHelper, config: dict) -> TestReport:
    """Test: Verify the app is running and showing expected UI via screenshot OCR."""
    start_time = time.time()
    screenshots = []
    bundle_id = "ai.ciris.mobile"

    try:
        print("  [1/3] Checking app is running...")
        is_running = helper.is_app_running(bundle_id)

        if not is_running:
            print("  [INFO] App not running, launching...")
            helper.launch_app(bundle_id)
            time.sleep(5)

        print("  [2/3] Taking screenshot...")
        path = ui.screenshot(f"/tmp/ciris_phys_app_state_{int(time.time())}.png")
        if not path:
            return TestReport(
                name="test_physical_app_state",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="Screenshot failed",
            )
        screenshots.append(path)

        print("  [3/3] Verifying UI state...")
        ui.refresh()
        texts = ui.get_screen_text()

        # Look for known CIRIS UI elements
        indicators = {
            "login": any("login" in t.lower() or "sign in" in t.lower() for t in texts),
            "setup": any("setup" in t.lower() or "welcome" in t.lower() for t in texts),
            "chat": any("shutdown" in t.lower() or "send" in t.lower() or "interact" in t.lower() for t in texts),
            "ciris": any("ciris" in t.lower() for t in texts),
        }

        detected_state = "unknown"
        if indicators["chat"]:
            detected_state = "chat (running)"
        elif indicators["setup"]:
            detected_state = "setup wizard"
        elif indicators["login"]:
            detected_state = "login screen"
        elif indicators["ciris"]:
            detected_state = "CIRIS app (unidentified screen)"

        return TestReport(
            name="test_physical_app_state",
            result=TestResult.PASSED if indicators["ciris"] or indicators["chat"] else TestResult.FAILED,
            duration=time.time() - start_time,
            message=f"App state: {detected_state}. Indicators: {indicators}. Texts: {texts[:10]}",
            screenshots=screenshots,
        )

    except Exception as e:
        return TestReport(
            name="test_physical_app_state",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
            screenshots=screenshots,
        )


def test_physical_api_health(helper: IDeviceHelper, ui: PhysicalDeviceUIHelper, config: dict) -> TestReport:
    """Test: Verify CIRIS API health via iproxy port forwarding."""
    start_time = time.time()
    local_port = config.get("local_port", 18080)
    remote_port = config.get("remote_port", 8080)

    try:
        print(f"  [1/3] Setting up port forward ({local_port} -> {remote_port})...")
        if not helper.forward_port(local_port, remote_port):
            return TestReport(
                name="test_physical_api_health",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="Failed to start iproxy port forwarding",
            )
        time.sleep(1)

        print("  [2/3] Checking API health...")
        api = APIClient(f"http://127.0.0.1:{local_port}")
        status, body = api.get("/v1/system/health", timeout=10)

        if status == 0:
            return TestReport(
                name="test_physical_api_health",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"API not reachable: {body.get('error', 'unknown')}",
            )

        print("  [3/3] Verifying response...")
        is_healthy = status == 200

        return TestReport(
            name="test_physical_api_health",
            result=TestResult.PASSED if is_healthy else TestResult.FAILED,
            duration=time.time() - start_time,
            message=f"Health check: status={status}, body={body}",
        )

    except Exception as e:
        return TestReport(
            name="test_physical_api_health",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
        )
    finally:
        helper.stop_port_forward()


def test_physical_api_telemetry(helper: IDeviceHelper, ui: PhysicalDeviceUIHelper, config: dict) -> TestReport:
    """Test: Login and check telemetry — verify all services are healthy."""
    start_time = time.time()
    local_port = config.get("local_port", 18080)
    remote_port = config.get("remote_port", 8080)

    try:
        print(f"  [1/4] Port forward ({local_port} -> {remote_port})...")
        if not helper.forward_port(local_port, remote_port):
            return TestReport(
                name="test_physical_api_telemetry",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="iproxy failed",
            )
        time.sleep(1)

        print("  [2/4] Logging in...")
        api = APIClient(f"http://127.0.0.1:{local_port}")
        logged_in = api.login()

        if not logged_in:
            if api.is_first_run:
                # In first-run state, telemetry may still be accessible without auth
                print("  [INFO] First-run state detected, trying telemetry without auth...")
                status, body = api.get("/v1/telemetry/unified", timeout=15)
                if status == 200:
                    online = body.get("services_online", 0)
                    total = body.get("services_total", 0)
                    return TestReport(
                        name="test_physical_api_telemetry",
                        result=TestResult.PASSED,
                        duration=time.time() - start_time,
                        message=f"First-run mode. Services: {online}/{total} healthy (no auth needed)",
                    )
                # Try health at least
                status, body = api.get("/v1/system/health", timeout=5)
                if status == 200:
                    return TestReport(
                        name="test_physical_api_telemetry",
                        result=TestResult.PASSED,
                        duration=time.time() - start_time,
                        message="First-run mode. Health OK (telemetry requires auth).",
                    )
            return TestReport(
                name="test_physical_api_telemetry",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"Login failed. first_run={api.is_first_run}",
            )

        print("  [3/4] Fetching telemetry...")
        status, body = api.get("/v1/telemetry/unified", timeout=15)

        if status != 200:
            # 503 in first-run mode is expected (agent processor not started)
            api.check_first_run()
            if status == 503 and api.is_first_run:
                return TestReport(
                    name="test_physical_api_telemetry",
                    result=TestResult.PASSED,
                    duration=time.time() - start_time,
                    message=f"First-run mode: telemetry unavailable (503) — expected before setup completion",
                )
            return TestReport(
                name="test_physical_api_telemetry",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"Telemetry request failed: status={status}",
            )

        print("  [4/4] Checking service health...")
        online = body.get("services_online", 0)
        total = body.get("services_total", 0)
        unhealthy = []
        for name, svc in body.get("services", {}).items():
            if not svc.get("healthy", False):
                unhealthy.append(name)

        result = TestResult.PASSED if online == total else TestResult.FAILED
        message = f"Services: {online}/{total} healthy"
        if unhealthy:
            message += f". Unhealthy: {unhealthy}"

        return TestReport(
            name="test_physical_api_telemetry",
            result=result,
            duration=time.time() - start_time,
            message=message,
        )

    except Exception as e:
        return TestReport(
            name="test_physical_api_telemetry",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
        )
    finally:
        helper.stop_port_forward()


def test_physical_api_verify_status(helper: IDeviceHelper, ui: PhysicalDeviceUIHelper, config: dict) -> TestReport:
    """Test: Check CIRISVerify attestation status via API."""
    start_time = time.time()
    local_port = config.get("local_port", 18080)
    remote_port = config.get("remote_port", 8080)

    try:
        print(f"  [1/4] Port forward ({local_port} -> {remote_port})...")
        if not helper.forward_port(local_port, remote_port):
            return TestReport(
                name="test_physical_api_verify_status",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="iproxy failed",
            )
        time.sleep(1)

        print("  [2/4] Logging in...")
        api = APIClient(f"http://127.0.0.1:{local_port}")
        logged_in = api.login()

        if not logged_in and not api.is_first_run:
            return TestReport(
                name="test_physical_api_verify_status",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="Login failed and not in first-run state",
            )

        if not logged_in:
            print("  [INFO] First-run state — checking attestation without full auth...")

        # Try attestation endpoint (may work without auth)
        print("  [3/4] Fetching attestation status...")
        status_a, body_a = api.get("/v1/auth/attestation", timeout=15)
        attestation_info = body_a if status_a == 200 else {}

        # Try adapters endpoint (requires auth)
        adapters = []
        verify_adapter = None
        if logged_in:
            status, body = api.get("/v1/system/adapters", timeout=15)
            if status == 200:
                adapters = body if isinstance(body, list) else body.get("adapters", [])
                for adapter in adapters:
                    if isinstance(adapter, dict):
                        name = adapter.get("name", "") or adapter.get("adapter_name", "")
                        if "verify" in name.lower():
                            verify_adapter = adapter
                            break

        print("  [4/4] Building report...")
        details = {
            "attestation": attestation_info,
            "logged_in": logged_in,
            "first_run": api.is_first_run,
        }
        if verify_adapter:
            details["adapter_found"] = True
            details["adapter_info"] = verify_adapter
        if adapters:
            details["adapter_count"] = len(adapters)

        # Extract attestation level from response
        attest_data = attestation_info.get("data", {})
        attest_status = attest_data.get("attestation_status", "unknown")
        max_level = attest_data.get("max_level", "?")

        return TestReport(
            name="test_physical_api_verify_status",
            result=TestResult.PASSED if status_a == 200 else TestResult.FAILED,
            duration=time.time() - start_time,
            message=f"Attestation: status={attest_status}, level={max_level}. Details: {json.dumps(details, indent=None, default=str)[:500]}",
        )

    except Exception as e:
        return TestReport(
            name="test_physical_api_verify_status",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
        )
    finally:
        helper.stop_port_forward()


def test_physical_api_adapters(helper: IDeviceHelper, ui: PhysicalDeviceUIHelper, config: dict) -> TestReport:
    """Test: List all loaded adapters and verify expected ones are present."""
    start_time = time.time()
    local_port = config.get("local_port", 18080)
    remote_port = config.get("remote_port", 8080)

    try:
        print(f"  [1/3] Port forward ({local_port} -> {remote_port})...")
        if not helper.forward_port(local_port, remote_port):
            return TestReport(
                name="test_physical_api_adapters",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="iproxy failed",
            )
        time.sleep(1)

        print("  [2/3] Logging in...")
        api = APIClient(f"http://127.0.0.1:{local_port}")
        logged_in = api.login()

        if not logged_in:
            msg = "First-run state" if api.is_first_run else "Login failed"
            # Even without auth, some endpoints may work — try health
            status, body = api.get("/v1/system/health", timeout=5)
            return TestReport(
                name="test_physical_api_adapters",
                result=TestResult.PASSED if api.is_first_run and status == 200 else TestResult.SKIPPED,
                duration=time.time() - start_time,
                message=f"{msg}. Health: {'OK' if status == 200 else 'unreachable'}. Adapters require auth.",
            )

        print("  [3/3] Fetching adapters...")
        status, body = api.get("/v1/system/adapters", timeout=15)
        if status != 200:
            return TestReport(
                name="test_physical_api_adapters",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"Request failed: status={status}",
            )

        adapters = body if isinstance(body, list) else body.get("adapters", [])
        adapter_names = []
        for a in adapters:
            if isinstance(a, dict):
                adapter_names.append(a.get("name", "") or a.get("adapter_name", "unknown"))

        return TestReport(
            name="test_physical_api_adapters",
            result=TestResult.PASSED,
            duration=time.time() - start_time,
            message=f"Found {len(adapters)} adapters: {adapter_names}",
        )

    except Exception as e:
        return TestReport(
            name="test_physical_api_adapters",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
        )
    finally:
        helper.stop_port_forward()


def test_physical_attestation(helper: IDeviceHelper, ui: PhysicalDeviceUIHelper, config: dict) -> TestReport:
    """Test: Check attestation status via the auth endpoint (no login required)."""
    start_time = time.time()
    local_port = config.get("local_port", 18080)
    remote_port = config.get("remote_port", 8080)

    try:
        print(f"  [1/3] Port forward ({local_port} -> {remote_port})...")
        if not helper.forward_port(local_port, remote_port):
            return TestReport(
                name="test_physical_attestation",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="iproxy failed",
            )
        time.sleep(1)

        print("  [2/3] Fetching attestation...")
        api = APIClient(f"http://127.0.0.1:{local_port}")
        status, body = api.get("/v1/auth/attestation", timeout=15)

        if status != 200:
            return TestReport(
                name="test_physical_attestation",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"Attestation endpoint returned {status}: {body}",
            )

        print("  [3/3] Analyzing result...")
        data = body.get("data", {})
        attest_status = data.get("attestation_status", "unknown")
        max_level = data.get("max_level", 0)
        level_pending = data.get("level_pending", False)
        binary_ok = data.get("binary_ok", False)
        error = data.get("error")

        # If in_progress or pending, wait and retry once
        if attest_status in ("in_progress", "not_attempted") and level_pending:
            print("  [INFO] Attestation in progress, waiting 10s and retrying...")
            time.sleep(10)
            status, body = api.get("/v1/auth/attestation", timeout=15)
            if status == 200:
                data = body.get("data", {})
                attest_status = data.get("attestation_status", "unknown")
                max_level = data.get("max_level", 0)
                level_pending = data.get("level_pending", False)
                binary_ok = data.get("binary_ok", False)
                error = data.get("error")

        passed = attest_status in ("verified", "partial") or max_level > 0 or binary_ok
        message = f"Attestation: status={attest_status}, level={max_level}, binary={'OK' if binary_ok else 'FAIL'}, pending={level_pending}"
        if error:
            message += f", error={error}"

        return TestReport(
            name="test_physical_attestation",
            result=TestResult.PASSED if passed else TestResult.FAILED,
            duration=time.time() - start_time,
            message=message,
        )

    except Exception as e:
        return TestReport(
            name="test_physical_attestation",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
        )
    finally:
        helper.stop_port_forward()


def test_physical_full_check(helper: IDeviceHelper, ui: PhysicalDeviceUIHelper, config: dict) -> TestReport:
    """Test: Combined screenshot + API verification of the physical device."""
    start_time = time.time()
    all_screenshots = []
    results = []

    try:
        print("\n=== Physical Device Full Check ===\n")

        # 1. Screenshot + OCR
        print("[Step 1/6] Screenshot & App State")
        r = test_physical_app_state(helper, ui, config)
        results.append(r)
        all_screenshots.extend(r.screenshots)
        print(f"  -> {r.result.value}: {r.message}")

        # 2. API Health
        print("\n[Step 2/6] API Health Check")
        r = test_physical_api_health(helper, ui, config)
        results.append(r)
        print(f"  -> {r.result.value}: {r.message}")

        # 3. Attestation (no auth needed)
        print("\n[Step 3/6] Attestation Status")
        r = test_physical_attestation(helper, ui, config)
        results.append(r)
        print(f"  -> {r.result.value}: {r.message}")

        # 4. Telemetry
        print("\n[Step 4/6] Telemetry & Services")
        r = test_physical_api_telemetry(helper, ui, config)
        results.append(r)
        print(f"  -> {r.result.value}: {r.message}")

        # 5. Verify Status
        print("\n[Step 5/6] CIRISVerify Status")
        r = test_physical_api_verify_status(helper, ui, config)
        results.append(r)
        print(f"  -> {r.result.value}: {r.message}")

        # 6. Real UI login + navigation (relaunches with CIRIS_TEST_MODE)
        print("\n[Step 6/6] UI Login & Navigation")
        r = test_physical_ui_login(helper, ui, config)
        results.append(r)
        all_screenshots.extend(r.screenshots)
        print(f"  -> {r.result.value}: {r.message}")

        passed = sum(1 for r in results if r.result == TestResult.PASSED)
        skipped = sum(1 for r in results if r.result == TestResult.SKIPPED)
        failed = sum(1 for r in results if r.result == TestResult.FAILED)
        total = len(results)

        overall = TestResult.PASSED if failed == 0 else TestResult.FAILED

        parts = [f"{passed}/{total} passed"]
        if skipped:
            parts.append(f"{skipped} skipped")
        if failed:
            parts.append(f"{failed} failed")

        return TestReport(
            name="test_physical_full_check",
            result=overall,
            duration=time.time() - start_time,
            message=", ".join(parts),
            screenshots=all_screenshots,
        )

    except Exception as e:
        return TestReport(
            name="test_physical_full_check",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {str(e)}",
            screenshots=all_screenshots,
        )


# ========== Test-Automation HTTP Client (real UI drive) ==========


class TestAutomationClient:
    """Thin HTTP client for the in-app test-automation server (POSIX socket
    on iOS, Ktor CIO on desktop). Forwarded to the device via iproxy.

    The server is gated by the ``CIRIS_TEST_MODE`` env var on the device side
    and listens on port 9091 by default. Endpoints supported on iOS:
    ``/health``, ``/screen``, ``/tree``, ``/click``, ``/input``, ``/wait``,
    ``/element/{tag}``. (``/act`` is desktop-only — use the individual
    endpoints here.)
    """

    def __init__(self, base_url: str = "http://127.0.0.1:19091"):
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str, data: Optional[dict] = None, timeout: int = 5) -> Tuple[int, dict]:
        url = f"{self.base_url}{path}"
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"} if body else {},
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body_bytes = resp.read()
                try:
                    return resp.status, json.loads(body_bytes)
                except json.JSONDecodeError:
                    return resp.status, {"raw": body_bytes.decode("utf-8", errors="replace")}
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read())
            except Exception:
                return e.code, {"error": str(e)}
        except (urllib.error.URLError, ConnectionRefusedError, OSError) as e:
            return 0, {"error": str(e)}

    def health(self) -> Tuple[int, dict]:
        return self._request("GET", "/health")

    def screen(self) -> Optional[str]:
        status, body = self._request("GET", "/screen")
        return body.get("screen") if status == 200 else None

    def tree(self) -> List[str]:
        status, body = self._request("GET", "/tree")
        if status != 200:
            return []
        return [e.get("testTag", "") for e in body.get("elements", [])]

    def click(self, test_tag: str) -> bool:
        status, body = self._request("POST", "/click", {"testTag": test_tag})
        return status == 200 and bool(body.get("success"))

    def input(self, test_tag: str, text: str, clear_first: bool = True) -> bool:
        status, body = self._request(
            "POST",
            "/input",
            {"testTag": test_tag, "text": text, "clearFirst": clear_first},
        )
        return status == 200 and bool(body.get("success"))

    def wait_for_screen(self, expected: str, timeout: float = 10.0, interval: float = 0.5) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.screen() == expected:
                return True
            time.sleep(interval)
        return False


def _ensure_iproxy(local_port: int, remote_port: int, udid: str) -> Optional[subprocess.Popen]:
    """Start an iproxy process forwarding ``local_port`` → device ``remote_port``.

    If iproxy is missing or fails, returns None. Caller is responsible for
    terminating the returned Popen.
    """
    if not shutil.which("iproxy"):
        return None
    try:
        return subprocess.Popen(
            ["iproxy", str(local_port), str(remote_port), "-u", udid],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, FileNotFoundError):
        return None


def _resolve_udid(helper: IDeviceHelper) -> Optional[str]:
    """Resolve the libimobiledevice UDID (needed by iproxy) for the active
    device. The QA helper canonicalizes to the CoreDevice UUID, so we have to
    look up the reverse mapping it builds during get_devices()."""
    coredevice = helper.device_id or (helper.get_devices()[0].identifier if helper.get_devices() else None)
    if not coredevice:
        return None
    for udid, cd in IDeviceHelper._udid_to_coredevice.items():
        if cd == coredevice:
            return udid
    if shutil.which("idevice_id"):
        result = subprocess.run(["idevice_id", "-l"], capture_output=True, text=True, timeout=10)
        udids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if len(udids) == 1:
            return udids[0]
    return None


def test_physical_ui_login(helper: IDeviceHelper, ui: PhysicalDeviceUIHelper, config: dict) -> TestReport:
    """Drive a real UI login on the device via the in-app test-automation server.

    Flow:
      1. Relaunch the app with ``CIRIS_TEST_MODE=true``
      2. Forward port 19091 → device 9091 via iproxy
      3. Wait for the test server's /health
      4. Click ``btn_local_login`` → enter admin/qa_test_password_12345 →
         click ``btn_login_submit``
      5. Verify we land on the ``Interact`` screen
      6. Navigate to ``Telemetry`` and back, verifying screen transitions
    """
    start_time = time.time()
    screenshots = []
    bundle_id = "ai.ciris.mobile"
    test_port_local = config.get("test_port_local", 19091)
    test_port_remote = config.get("test_port_remote", 9091)
    username = config.get("username", "admin")
    password = config.get("password", "qa_test_password_12345")

    iproxy_proc: Optional[subprocess.Popen] = None
    try:
        print("  [1/6] Resolving device UDID for iproxy...")
        udid = _resolve_udid(helper)
        if not udid:
            return TestReport(
                name="test_physical_ui_login",
                result=TestResult.SKIPPED,
                duration=time.time() - start_time,
                message="Could not resolve libimobiledevice UDID (iproxy requires it)",
            )

        print("  [2/6] Relaunching app with CIRIS_TEST_MODE=true...")
        launched = helper.launch_app(
            bundle_id,
            env_vars={"CIRIS_TEST_MODE": "true"},
            terminate_existing=True,
        )
        if not launched:
            return TestReport(
                name="test_physical_ui_login",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="Failed to launch app with CIRIS_TEST_MODE",
            )

        print(f"  [3/6] Forwarding iproxy {test_port_local} -> device {test_port_remote}...")
        iproxy_proc = _ensure_iproxy(test_port_local, test_port_remote, udid)
        if not iproxy_proc:
            return TestReport(
                name="test_physical_ui_login",
                result=TestResult.SKIPPED,
                duration=time.time() - start_time,
                message="iproxy not available (install libimobiledevice)",
            )

        client = TestAutomationClient(f"http://127.0.0.1:{test_port_local}")

        print("  [4/6] Waiting for in-app test server...")
        deadline = time.time() + 30.0
        ready = False
        while time.time() < deadline:
            status, body = client.health()
            if status == 200 and body.get("testMode"):
                ready = True
                break
            time.sleep(2)
        if not ready:
            return TestReport(
                name="test_physical_ui_login",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=("Test automation server never came up. " "Is the app built with the testing module included?"),
            )

        print("  [5/6] Waiting for Login screen (Startup -> Login can take ~60s)...")
        # First app launch runs CIRISVerify attestation + spins up the Python
        # backend + boots 22 services before the Login screen renders. Give it
        # a generous window; on subsequent relaunches it's typically much faster.
        if not client.wait_for_screen("Login", timeout=120.0, interval=1.5):
            return TestReport(
                name="test_physical_ui_login",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"Did not reach Login screen (still on {client.screen()!r})",
            )

        print("  [5b/6] Driving Login → Local Login → submit...")

        if not client.click("btn_local_login"):
            return TestReport(
                name="test_physical_ui_login",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="Could not click btn_local_login",
            )
        time.sleep(2)  # StateFlow propagation

        if not client.input("input_username", username):
            return TestReport(
                name="test_physical_ui_login",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="Could not enter username",
            )
        time.sleep(2)

        if not client.input("input_password", password):
            return TestReport(
                name="test_physical_ui_login",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="Could not enter password",
            )
        time.sleep(2)

        if not client.click("btn_login_submit"):
            return TestReport(
                name="test_physical_ui_login",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="Could not click btn_login_submit",
            )

        if not client.wait_for_screen("Interact", timeout=15.0):
            return TestReport(
                name="test_physical_ui_login",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"Did not reach Interact screen (still on {client.screen()!r})",
            )

        interact_shot = ui.screenshot(f"/tmp/ciris_phys_ui_interact_{int(time.time())}.png")
        if interact_shot:
            screenshots.append(interact_shot)

        print("  [6/6] Navigating Interact → Telemetry → Interact...")
        # The nav drawer button is testable on both screens.
        client.click("btn_nav_drawer_open")
        time.sleep(2)
        if not client.click("nav_epistemic_telemetry"):
            return TestReport(
                name="test_physical_ui_login",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="Could not navigate to Telemetry",
                screenshots=screenshots,
            )
        if not client.wait_for_screen("Telemetry", timeout=8.0):
            return TestReport(
                name="test_physical_ui_login",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"Did not reach Telemetry (still on {client.screen()!r})",
                screenshots=screenshots,
            )
        telemetry_shot = ui.screenshot(f"/tmp/ciris_phys_ui_telemetry_{int(time.time())}.png")
        if telemetry_shot:
            screenshots.append(telemetry_shot)

        client.click("btn_nav_drawer_open")
        time.sleep(2)
        client.click("nav_epistemic_interact")
        client.wait_for_screen("Interact", timeout=8.0)

        return TestReport(
            name="test_physical_ui_login",
            result=TestResult.PASSED,
            duration=time.time() - start_time,
            message=(f"Logged in as {username!r} via Compose testTags; " f"navigated Interact → Telemetry → Interact"),
            screenshots=screenshots,
        )

    except Exception as e:
        return TestReport(
            name="test_physical_ui_login",
            result=TestResult.ERROR,
            duration=time.time() - start_time,
            message=f"Error: {type(e).__name__}: {e}",
            screenshots=screenshots,
        )
    finally:
        if iproxy_proc is not None:
            try:
                iproxy_proc.terminate()
                try:
                    iproxy_proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    iproxy_proc.kill()
            except Exception:
                pass
