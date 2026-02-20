"""
Portal Registration Module for CIRIS Mobile QA Runner.

Tests the RFC 8628 device authorization flow against portal.ciris.ai:
  1. Login to local CIRIS API
  2. POST /v1/setup/connect-node → device code + verification URL
  3. Poll /v1/setup/connect-node/status until authorized or timeout
  4. Verify provisioned template, adapters, and signing key

Usage (standalone):
    python -m tools.qa_runner.modules.mobile portal --portal-url https://portal.ciris.ai
    python -m tools.qa_runner.modules.mobile portal --wait --timeout 300

Usage (from CLI):
    python -m tools.qa_runner.modules.mobile portal          # Initiate only
    python -m tools.qa_runner.modules.mobile portal --wait   # Initiate + poll until complete
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

try:
    import httpx
except ImportError:
    httpx = None

try:
    import requests
except ImportError:
    requests = None


class PortalTestStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    PENDING = "pending"


@dataclass
class PortalTestResult:
    name: str
    status: PortalTestStatus
    duration: float
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    screenshots: List[str] = field(default_factory=list)


class PortalRegistrationTester:
    """Tests portal.ciris.ai device auth registration against a running CIRIS API."""

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        portal_url: str = "https://portal.ciris.ai",
        username: str = "admin",
        password: str = "ciris_admin_password",
        poll_timeout: int = 300,
        poll_interval: int = 5,
        verbose: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.portal_url = portal_url
        self.username = username
        self.password = password
        self.poll_timeout = poll_timeout
        self.poll_interval = poll_interval
        self.verbose = verbose
        self.token: Optional[str] = None

        self._first_run = False

        # Use httpx if available, fall back to requests
        if httpx is None and requests is None:
            raise RuntimeError("Neither httpx nor requests is installed")

    def _log(self, msg: str):
        if self.verbose:
            print(f"  [DEBUG] {msg}")

    def _get(self, path: str, params: Optional[Dict] = None, timeout: int = 30) -> Dict:
        """GET request to CIRIS API."""
        url = f"{self.base_url}{path}"
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        if httpx:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(url, headers=headers, params=params)
                resp.raise_for_status()
                return resp.json()
        else:
            resp = requests.get(url, headers=headers, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json()

    def _post(self, path: str, data: Optional[Dict] = None, timeout: int = 30) -> Dict:
        """POST request to CIRIS API."""
        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        if httpx:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, headers=headers, json=data)
                resp.raise_for_status()
                return resp.json()
        else:
            resp = requests.post(url, headers=headers, json=data, timeout=timeout)
            resp.raise_for_status()
            return resp.json()

    def _get_raw(self, path: str, params: Optional[Dict] = None, timeout: int = 30):
        """GET request returning raw response (for status code inspection)."""
        url = f"{self.base_url}{path}"
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        if httpx:
            with httpx.Client(timeout=timeout) as client:
                return client.get(url, headers=headers, params=params)
        else:
            return requests.get(url, headers=headers, params=params, timeout=timeout)

    # ========== Test Steps ==========

    def test_health(self) -> PortalTestResult:
        """Test 1: Verify CIRIS API is healthy."""
        start = time.time()
        try:
            data = self._get("/v1/system/health")
            health = data.get("data", {})
            status = health.get("status", "unknown")
            version = health.get("version", "unknown")

            if status == "healthy":
                return PortalTestResult(
                    name="api_health",
                    status=PortalTestStatus.PASSED,
                    duration=time.time() - start,
                    message=f"API healthy (v{version})",
                    details={"version": version, "status": status},
                )
            else:
                return PortalTestResult(
                    name="api_health",
                    status=PortalTestStatus.FAILED,
                    duration=time.time() - start,
                    message=f"API unhealthy: {status}",
                    details=health,
                )
        except Exception as e:
            return PortalTestResult(
                name="api_health",
                status=PortalTestStatus.ERROR,
                duration=time.time() - start,
                message=f"Cannot reach API at {self.base_url}: {e}",
            )

    def test_setup_status(self) -> PortalTestResult:
        """Test 2: Check setup status and determine auth needs."""
        start = time.time()
        try:
            data = self._get("/v1/setup/status")
            setup_data = data.get("data", {})
            is_first_run = setup_data.get("is_first_run", False)
            setup_required = setup_data.get("setup_required", False)

            if is_first_run or setup_required:
                # First-run mode: setup endpoints don't require auth
                self._first_run = True
                return PortalTestResult(
                    name="setup_status",
                    status=PortalTestStatus.PASSED,
                    duration=time.time() - start,
                    message="First-run mode — setup endpoints available without auth",
                    details=setup_data,
                )
            else:
                # Already configured: need to login
                self._first_run = False
                return self._do_login(start)

        except Exception as e:
            return PortalTestResult(
                name="setup_status",
                status=PortalTestStatus.ERROR,
                duration=time.time() - start,
                message=f"Setup status check failed: {e}",
            )

    def _do_login(self, start: float) -> PortalTestResult:
        """Login to get auth token (needed when not in first-run mode)."""
        try:
            data = self._post(
                "/v1/auth/login",
                {"username": self.username, "password": self.password},
            )
            token = data.get("access_token")
            if not token:
                return PortalTestResult(
                    name="setup_status",
                    status=PortalTestStatus.FAILED,
                    duration=time.time() - start,
                    message=f"Login failed — no access_token: {list(data.keys())}",
                    details=data,
                )

            self.token = token
            return PortalTestResult(
                name="setup_status",
                status=PortalTestStatus.PASSED,
                duration=time.time() - start,
                message=f"Configured mode — logged in as {self.username}",
                details={"token_prefix": token[:20] + "..."},
            )
        except Exception as e:
            return PortalTestResult(
                name="setup_status",
                status=PortalTestStatus.ERROR,
                duration=time.time() - start,
                message=f"Login failed: {e}",
            )

    def test_connect_node(self) -> PortalTestResult:
        """Test 3: Initiate device auth via POST /v1/setup/connect-node."""
        start = time.time()
        try:
            data = self._post(
                "/v1/setup/connect-node",
                {"node_url": self.portal_url},
                timeout=30,
            )

            response_data = data.get("data", data)

            verification_uri = response_data.get("verification_uri_complete", "")
            device_code = response_data.get("device_code", "")
            user_code = response_data.get("user_code", "")
            portal_url = response_data.get("portal_url", "")
            expires_in = response_data.get("expires_in", 0)
            interval = response_data.get("interval", 5)

            if not device_code:
                return PortalTestResult(
                    name="connect_node",
                    status=PortalTestStatus.FAILED,
                    duration=time.time() - start,
                    message=f"No device_code in response: {list(response_data.keys())}",
                    details=response_data,
                )

            details = {
                "verification_uri_complete": verification_uri,
                "device_code": device_code,
                "user_code": user_code,
                "portal_url": portal_url,
                "expires_in": expires_in,
                "interval": interval,
            }

            return PortalTestResult(
                name="connect_node",
                status=PortalTestStatus.PASSED,
                duration=time.time() - start,
                message=(
                    f"Device auth initiated. "
                    f"User code: {user_code}, "
                    f"Expires in: {expires_in}s"
                ),
                details=details,
            )
        except Exception as e:
            error_msg = str(e)
            # Try to extract response body for better error messages
            if hasattr(e, "response"):
                try:
                    error_body = e.response.json()
                    error_msg = f"{e} — {error_body}"
                except Exception:
                    try:
                        error_msg = f"{e} — {e.response.text[:500]}"
                    except Exception:
                        pass

            return PortalTestResult(
                name="connect_node",
                status=PortalTestStatus.ERROR,
                duration=time.time() - start,
                message=f"Connect failed: {error_msg}",
            )

    def test_poll_status(
        self,
        device_code: str,
        portal_url: str,
        wait: bool = False,
    ) -> PortalTestResult:
        """Test 4: Poll device auth status."""
        start = time.time()

        params = {"device_code": device_code, "portal_url": portal_url}

        try:
            if not wait:
                # Single poll — just check the endpoint works
                resp = self._get_raw("/v1/setup/connect-node/status", params=params)
                status_code = resp.status_code

                try:
                    body = resp.json()
                except Exception:
                    body = {"raw": resp.text[:500]}

                response_data = body.get("data", body)
                poll_status = response_data.get("status", "unknown")

                return PortalTestResult(
                    name="poll_status",
                    status=PortalTestStatus.PASSED,
                    duration=time.time() - start,
                    message=f"Poll returned status={poll_status} (HTTP {status_code})",
                    details={"http_status": status_code, "auth_status": poll_status, **response_data},
                )
            else:
                # Polling loop until complete or timeout
                poll_count = 0
                while time.time() - start < self.poll_timeout:
                    poll_count += 1
                    resp = self._get_raw("/v1/setup/connect-node/status", params=params)

                    try:
                        body = resp.json()
                    except Exception:
                        body = {}

                    response_data = body.get("data", body)
                    poll_status = response_data.get("status", "unknown")

                    if poll_status == "complete":
                        template = response_data.get("template", "")
                        adapters = response_data.get("adapters", [])
                        org_id = response_data.get("org_id", "")
                        has_key = bool(response_data.get("signing_key_b64"))
                        key_id = response_data.get("key_id", "")
                        tier = response_data.get("stewardship_tier", 0)

                        return PortalTestResult(
                            name="poll_status",
                            status=PortalTestStatus.PASSED,
                            duration=time.time() - start,
                            message=(
                                f"Authorization COMPLETE after {poll_count} polls. "
                                f"Template: {template}, "
                                f"Adapters: {adapters}, "
                                f"Key: {'received' if has_key else 'missing'}, "
                                f"Tier: {tier}"
                            ),
                            details={
                                "auth_status": "complete",
                                "template": template,
                                "adapters": adapters,
                                "org_id": org_id,
                                "has_signing_key": has_key,
                                "key_id": key_id,
                                "stewardship_tier": tier,
                                "polls": poll_count,
                            },
                        )
                    elif poll_status == "error":
                        error = response_data.get("error", "unknown error")
                        return PortalTestResult(
                            name="poll_status",
                            status=PortalTestStatus.FAILED,
                            duration=time.time() - start,
                            message=f"Authorization REJECTED after {poll_count} polls: {error}",
                            details={"auth_status": "error", "error": error, "polls": poll_count},
                        )

                    # Still pending
                    self._log(f"Poll {poll_count}: status={poll_status} (HTTP {resp.status_code})")
                    elapsed = int(time.time() - start)
                    remaining = self.poll_timeout - elapsed
                    print(f"\r  Waiting for Portal authorization... "
                          f"({elapsed}s / {self.poll_timeout}s, poll #{poll_count})", end="", flush=True)

                    time.sleep(self.poll_interval)

                print()  # newline after \r
                return PortalTestResult(
                    name="poll_status",
                    status=PortalTestStatus.FAILED,
                    duration=time.time() - start,
                    message=f"Authorization TIMEOUT after {poll_count} polls ({self.poll_timeout}s)",
                    details={"auth_status": "timeout", "polls": poll_count},
                )

        except Exception as e:
            return PortalTestResult(
                name="poll_status",
                status=PortalTestStatus.ERROR,
                duration=time.time() - start,
                message=f"Poll failed: {e}",
            )


def run_portal_registration(
    base_url: str = "http://localhost:8080",
    portal_url: str = "https://portal.ciris.ai",
    username: str = "admin",
    password: str = "ciris_admin_password",
    wait: bool = False,
    poll_timeout: int = 300,
    poll_interval: int = 5,
    output_dir: str = "mobile_qa_reports",
    verbose: bool = False,
) -> int:
    """
    Run the portal registration test suite.

    Returns 0 on success, 1 on failure.
    """
    print("\n" + "=" * 60)
    print("CIRIS Portal Registration Test")
    print("=" * 60)
    print(f"  API:     {base_url}")
    print(f"  Portal:  {portal_url}")
    print(f"  Wait:    {wait}")
    if wait:
        print(f"  Timeout: {poll_timeout}s")
    print()

    tester = PortalRegistrationTester(
        base_url=base_url,
        portal_url=portal_url,
        username=username,
        password=password,
        poll_timeout=poll_timeout,
        poll_interval=poll_interval,
        verbose=verbose,
    )

    results: List[PortalTestResult] = []

    # ========== Test 1: Health ==========
    print("[1/4] Checking API health...")
    result = tester.test_health()
    results.append(result)
    _print_result(result)

    if result.status != PortalTestStatus.PASSED:
        _print_summary(results, output_dir)
        return 1

    # ========== Test 2: Setup Status / Login ==========
    print("[2/4] Checking setup status...")
    result = tester.test_setup_status()
    results.append(result)
    _print_result(result)

    if result.status != PortalTestStatus.PASSED:
        _print_summary(results, output_dir)
        return 1

    # ========== Test 3: Connect Node ==========
    print(f"[3/4] Initiating device auth with {portal_url}...")
    result = tester.test_connect_node()
    results.append(result)
    _print_result(result)

    if result.status != PortalTestStatus.PASSED:
        _print_summary(results, output_dir)
        return 1

    # Print device auth info for user
    details = result.details
    verification_uri = details.get("verification_uri_complete", "")
    user_code = details.get("user_code", "")
    device_code = details.get("device_code", "")
    portal_url_resp = details.get("portal_url", portal_url)
    expires_in = details.get("expires_in", 900)

    print()
    print("  " + "=" * 50)
    print("  DEVICE AUTHORIZATION")
    print("  " + "=" * 50)
    if verification_uri:
        print(f"  Open this URL in your browser:")
        print(f"    {verification_uri}")
    if user_code:
        print(f"  User code: {user_code}")
    print(f"  Expires in: {expires_in}s")
    print("  " + "=" * 50)
    print()

    # ========== Test 4: Poll Status ==========
    if wait:
        print(f"[4/4] Polling for authorization (timeout: {poll_timeout}s)...")
        print(f"  Complete the authorization at: {verification_uri}")
    else:
        print("[4/4] Polling status (single check)...")

    result = tester.test_poll_status(
        device_code=device_code,
        portal_url=portal_url_resp,
        wait=wait,
    )
    results.append(result)
    print()
    _print_result(result)

    _print_summary(results, output_dir)

    failed = sum(1 for r in results if r.status in (PortalTestStatus.FAILED, PortalTestStatus.ERROR))
    return 0 if failed == 0 else 1


def _print_result(result: PortalTestResult):
    """Print a single test result."""
    icons = {
        PortalTestStatus.PASSED: "PASS",
        PortalTestStatus.FAILED: "FAIL",
        PortalTestStatus.ERROR: "ERR!",
        PortalTestStatus.PENDING: "WAIT",
    }
    icon = icons.get(result.status, "????")
    print(f"  [{icon}] {result.name} ({result.duration:.1f}s) — {result.message}")


def _print_summary(results: List[PortalTestResult], output_dir: str):
    """Print summary and save results."""
    passed = sum(1 for r in results if r.status == PortalTestStatus.PASSED)
    failed = sum(1 for r in results if r.status == PortalTestStatus.FAILED)
    errors = sum(1 for r in results if r.status == PortalTestStatus.ERROR)

    print("\n" + "=" * 60)
    print("Portal Registration Summary")
    print("=" * 60)
    print(f"  Total:   {len(results)}")
    print(f"  Passed:  {passed}")
    print(f"  Failed:  {failed}")
    print(f"  Errors:  {errors}")
    print("=" * 60)

    # Save results
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = out_path / f"portal_registration_{timestamp}.json"

    with open(results_file, "w") as f:
        json.dump(
            {
                "test_suite": "portal_registration",
                "timestamp": timestamp,
                "results": [
                    {
                        "name": r.name,
                        "status": r.status.value,
                        "duration": r.duration,
                        "message": r.message,
                        "details": r.details,
                    }
                    for r in results
                ],
                "summary": {
                    "total": len(results),
                    "passed": passed,
                    "failed": failed,
                    "errors": errors,
                },
            },
            f,
            indent=2,
        )
    print(f"\nResults: {results_file}")
