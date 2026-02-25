"""
iOS Physical Device Test Cases for CIRIS App

Test cases for physical iOS devices using:
- pymobiledevice3 screenshots + Vision OCR for UI verification
- iproxy port forwarding + HTTP API calls for backend verification

These tests work without UI interaction (no tap/swipe/input on physical devices).
They verify the running app state via screenshots and API endpoints.
"""

import json
import time
import urllib.request
import urllib.error
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

    def login(self, username: str = "admin", password: str = "ciris_admin_password") -> bool:
        """Login and store token."""
        status, body = self.post("/v1/auth/login", {"username": username, "password": password})
        if status == 200 and "access_token" in body:
            self.token = body["access_token"]
            return True
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
        if not api.login():
            # Check if app is in first-run state (no credentials set up yet)
            status, body = api.get("/v1/system/health", timeout=5)
            if status == 200:
                return TestReport(
                    name="test_physical_api_telemetry",
                    result=TestResult.SKIPPED,
                    duration=time.time() - start_time,
                    message="Login failed — app may be in first-run state (setup not completed). Health OK.",
                )
            return TestReport(
                name="test_physical_api_telemetry",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message="Login failed and health check unreachable",
            )

        print("  [3/4] Fetching telemetry...")
        status, body = api.get("/v1/telemetry/unified", timeout=15)

        if status != 200:
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
        if not api.login():
            return TestReport(
                name="test_physical_api_verify_status",
                result=TestResult.SKIPPED,
                duration=time.time() - start_time,
                message="Login failed — app may be in first-run state (setup not completed)",
            )

        print("  [3/4] Fetching verify status...")
        status, body = api.get("/v1/system/adapters", timeout=15)
        if status != 200:
            return TestReport(
                name="test_physical_api_verify_status",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"Adapters request failed: status={status}",
            )

        # Find ciris_verify adapter
        adapters = body if isinstance(body, list) else body.get("adapters", [])
        verify_adapter = None
        for adapter in adapters:
            if isinstance(adapter, dict):
                name = adapter.get("name", "") or adapter.get("adapter_name", "")
                if "verify" in name.lower():
                    verify_adapter = adapter
                    break

        if not verify_adapter:
            return TestReport(
                name="test_physical_api_verify_status",
                result=TestResult.FAILED,
                duration=time.time() - start_time,
                message=f"CIRISVerify adapter not found in {len(adapters)} adapters",
            )

        print("  [4/4] Checking verify tool results...")
        # Try getting verify status via tool endpoint
        status2, body2 = api.post("/v1/tools/execute", {
            "tool_name": "ciris_verify_status",
            "parameters": {},
        }, timeout=15)

        verify_info = {}
        if status2 == 200:
            verify_info = body2

        # Also try the dedicated verify endpoint if available
        status3, body3 = api.get("/v1/system/verify-status", timeout=10)
        if status3 == 200:
            verify_info = body3

        # Build report
        details = {
            "adapter_found": True,
            "adapter_info": verify_adapter,
        }
        if verify_info:
            details["verify_status"] = verify_info

        return TestReport(
            name="test_physical_api_verify_status",
            result=TestResult.PASSED,
            duration=time.time() - start_time,
            message=f"CIRISVerify adapter loaded. Details: {json.dumps(details, indent=None, default=str)[:500]}",
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
        if not api.login():
            return TestReport(
                name="test_physical_api_adapters",
                result=TestResult.SKIPPED,
                duration=time.time() - start_time,
                message="Login failed — app may be in first-run state (setup not completed)",
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


def test_physical_full_check(helper: IDeviceHelper, ui: PhysicalDeviceUIHelper, config: dict) -> TestReport:
    """Test: Combined screenshot + API verification of the physical device."""
    start_time = time.time()
    all_screenshots = []
    results = []

    try:
        print("\n=== Physical Device Full Check ===\n")

        # 1. Screenshot + OCR
        print("[Step 1/4] Screenshot & App State")
        r = test_physical_app_state(helper, ui, config)
        results.append(r)
        all_screenshots.extend(r.screenshots)
        print(f"  -> {r.result.value}: {r.message}")

        # 2. API Health
        print("\n[Step 2/4] API Health Check")
        r = test_physical_api_health(helper, ui, config)
        results.append(r)
        print(f"  -> {r.result.value}: {r.message}")

        # 3. Telemetry
        print("\n[Step 3/4] Telemetry & Services")
        r = test_physical_api_telemetry(helper, ui, config)
        results.append(r)
        print(f"  -> {r.result.value}: {r.message}")

        # 4. Verify Status
        print("\n[Step 4/4] CIRISVerify Status")
        r = test_physical_api_verify_status(helper, ui, config)
        results.append(r)
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
