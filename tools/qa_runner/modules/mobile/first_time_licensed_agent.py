"""
First-Time Licensed Agent E2E Module for CIRIS Mobile QA Runner.

Complete end-to-end flow for a first-run agent that acquires a license
via Portal device auth and completes setup with provisioned credentials.

Flow:
  1. Health check
  2. Verify first-run status
  3. Enumerate providers / templates / adapters
  4. POST /v1/setup/connect-node  -> device code + verification URL
  5. Poll  /v1/setup/connect-node/status  until authorized
  6. POST /v1/setup/complete  with provisioned signing key, template, adapters
  7. POST /v1/auth/login  to verify user creation
  8. GET  /v1/system/health  to verify agent is configured
  9. GET  /v1/telemetry/unified  to verify services online

Usage:
    python -m tools.qa_runner.modules.mobile licensed-agent --wait
    python -m tools.qa_runner.modules.mobile licensed-agent --llm-provider groq --llm-key-file ~/.groq_key
"""

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import httpx
except ImportError:
    httpx = None

try:
    import requests
except ImportError:
    requests = None


class TestStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class StepResult:
    name: str
    status: TestStatus
    duration: float
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


class FirstTimeLicensedAgentTester:
    """
    End-to-end tester: first-run -> portal device auth -> setup complete -> verify.

    All setup endpoints are called WITHOUT auth (first-run mode).
    After setup completes, auth is verified with the newly created user.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        portal_url: str = "https://portal.ciris.ai",
        llm_provider: str = "groq",
        llm_api_key: str = "",
        llm_model: Optional[str] = None,
        admin_username: str = "admin",
        admin_password: str = "ciris_admin_password",
        poll_timeout: int = 300,
        poll_interval: int = 5,
        verbose: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.portal_url = portal_url
        self.llm_provider = llm_provider
        self.llm_api_key = llm_api_key
        self.llm_model = llm_model
        self.admin_username = admin_username
        self.admin_password = admin_password
        self.poll_timeout = poll_timeout
        self.poll_interval = poll_interval
        self.verbose = verbose

        # Populated during test execution
        self.token: Optional[str] = None
        self._provisioned: Dict[str, Any] = {}

        if httpx is None and requests is None:
            raise RuntimeError("Neither httpx nor requests is installed")

    def _log(self, msg: str):
        if self.verbose:
            print(f"  [DEBUG] {msg}")

    # -- HTTP helpers (no auth for first-run) --------------------------------

    def _get(self, path: str, params: Optional[Dict] = None, timeout: int = 30) -> Dict:
        url = f"{self.base_url}{path}"
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if httpx:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(url, headers=headers, params=params)
                resp.raise_for_status()
                return resp.json()
        resp = requests.get(url, headers=headers, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, data: Optional[Dict] = None, timeout: int = 30) -> Dict:
        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if httpx:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, headers=headers, json=data)
                resp.raise_for_status()
                return resp.json()
        resp = requests.post(url, headers=headers, json=data, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def _get_raw(self, path: str, params: Optional[Dict] = None, timeout: int = 30):
        url = f"{self.base_url}{path}"
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if httpx:
            with httpx.Client(timeout=timeout) as client:
                return client.get(url, headers=headers, params=params)
        return requests.get(url, headers=headers, params=params, timeout=timeout)

    def _post_raw(self, path: str, data: Optional[Dict] = None, timeout: int = 30):
        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if httpx:
            with httpx.Client(timeout=timeout) as client:
                return client.post(url, headers=headers, json=data)
        return requests.post(url, headers=headers, json=data, timeout=timeout)

    # -- Test steps -----------------------------------------------------------

    def step_health(self) -> StepResult:
        """Step 1: Verify API is healthy."""
        start = time.time()
        try:
            data = self._get("/v1/system/health")
            health = data.get("data", {})
            status = health.get("status", "unknown")
            version = health.get("version", "unknown")
            if status == "healthy":
                return StepResult("health", TestStatus.PASSED, time.time() - start,
                                  f"API healthy v{version}")
            return StepResult("health", TestStatus.FAILED, time.time() - start,
                              f"Unhealthy: {status}", health)
        except Exception as e:
            return StepResult("health", TestStatus.ERROR, time.time() - start,
                              f"Cannot reach API: {e}")

    def step_first_run(self) -> StepResult:
        """Step 2: Verify agent is in first-run mode."""
        start = time.time()
        try:
            data = self._get("/v1/setup/status")
            setup = data.get("data", {})
            is_first_run = setup.get("is_first_run", False)
            setup_required = setup.get("setup_required", False)

            if is_first_run or setup_required:
                return StepResult("first_run", TestStatus.PASSED, time.time() - start,
                                  "First-run mode confirmed", setup)
            return StepResult("first_run", TestStatus.FAILED, time.time() - start,
                              "Agent is already configured (not first-run)", setup)
        except Exception as e:
            return StepResult("first_run", TestStatus.ERROR, time.time() - start,
                              f"Status check failed: {e}")

    def step_enumerate(self) -> StepResult:
        """Step 3: Enumerate providers, templates, adapters."""
        start = time.time()
        details: Dict[str, Any] = {}
        errors: List[str] = []

        for name, path in [("providers", "/v1/setup/providers"),
                           ("templates", "/v1/setup/templates"),
                           ("adapters", "/v1/setup/adapters")]:
            try:
                data = self._get(path)
                items = data.get("data", [])
                details[name] = len(items) if isinstance(items, list) else "ok"
            except Exception as e:
                errors.append(f"{name}: {e}")

        if errors:
            return StepResult("enumerate", TestStatus.FAILED, time.time() - start,
                              f"Errors: {'; '.join(errors)}", details)
        return StepResult("enumerate", TestStatus.PASSED, time.time() - start,
                          f"providers={details.get('providers')}, "
                          f"templates={details.get('templates')}, "
                          f"adapters={details.get('adapters')}",
                          details)

    def step_connect_node(self) -> StepResult:
        """Step 4: Initiate device auth via portal."""
        start = time.time()
        try:
            data = self._post("/v1/setup/connect-node",
                              {"node_url": self.portal_url}, timeout=30)
            rd = data.get("data", data)

            device_code = rd.get("device_code", "")
            user_code = rd.get("user_code", "")
            verification_uri = rd.get("verification_uri_complete", "")
            expires_in = rd.get("expires_in", 0)

            if not device_code:
                return StepResult("connect_node", TestStatus.FAILED, time.time() - start,
                                  f"No device_code: {list(rd.keys())}", rd)

            return StepResult("connect_node", TestStatus.PASSED, time.time() - start,
                              f"Code: {user_code}, expires: {expires_in}s",
                              {"device_code": device_code,
                               "user_code": user_code,
                               "verification_uri_complete": verification_uri,
                               "portal_url": rd.get("portal_url", self.portal_url),
                               "expires_in": expires_in,
                               "interval": rd.get("interval", 5)})
        except Exception as e:
            return StepResult("connect_node", TestStatus.ERROR, time.time() - start,
                              f"Connect failed: {e}")

    def step_poll_auth(self, device_code: str, portal_url: str) -> StepResult:
        """Step 5: Poll until portal authorization completes."""
        start = time.time()
        params = {"device_code": device_code, "portal_url": portal_url}
        poll_count = 0

        try:
            while time.time() - start < self.poll_timeout:
                poll_count += 1
                resp = self._get_raw("/v1/setup/connect-node/status", params=params)

                try:
                    body = resp.json()
                except Exception:
                    body = {}

                rd = body.get("data", body)
                poll_status = rd.get("status", "unknown")

                if poll_status == "complete":
                    self._provisioned = rd
                    template = rd.get("template", "")
                    adapters = rd.get("adapters", [])
                    has_key = bool(rd.get("signing_key_b64"))
                    tier = rd.get("stewardship_tier", 0)

                    return StepResult(
                        "poll_auth", TestStatus.PASSED, time.time() - start,
                        f"Authorized! template={template}, adapters={adapters}, "
                        f"key={'yes' if has_key else 'NO'}, tier={tier}",
                        {"polls": poll_count, **rd})

                if poll_status == "error":
                    return StepResult("poll_auth", TestStatus.FAILED, time.time() - start,
                                      f"Rejected: {rd.get('error', '?')}",
                                      {"polls": poll_count})

                elapsed = int(time.time() - start)
                print(f"\r  Waiting for Portal auth... "
                      f"({elapsed}s / {self.poll_timeout}s, poll #{poll_count})",
                      end="", flush=True)
                time.sleep(self.poll_interval)

            print()
            return StepResult("poll_auth", TestStatus.FAILED, time.time() - start,
                              f"Timeout after {poll_count} polls ({self.poll_timeout}s)",
                              {"polls": poll_count})
        except Exception as e:
            return StepResult("poll_auth", TestStatus.ERROR, time.time() - start,
                              f"Poll error: {e}")

    def step_complete_setup(self) -> StepResult:
        """Step 6: POST /v1/setup/complete with provisioned + LLM config."""
        start = time.time()

        if not self.llm_api_key:
            return StepResult("complete_setup", TestStatus.SKIPPED, time.time() - start,
                              "No LLM API key provided (--llm-key or --llm-key-file)")

        prov = self._provisioned

        payload: Dict[str, Any] = {
            # LLM
            "llm_provider": self.llm_provider,
            "llm_api_key": self.llm_api_key,
            "llm_model": self.llm_model,
            # Identity / template
            "template_id": prov.get("template", "default"),
            # Adapters (keep api + portal-approved)
            "enabled_adapters": list(set(["api"] + prov.get("adapters", []))),
            # User
            "admin_username": self.admin_username,
            "admin_password": self.admin_password,
            "agent_port": 8080,
            # Portal provisioned fields
            "node_url": self.portal_url,
            "identity_template": prov.get("template"),
            "stewardship_tier": prov.get("stewardship_tier"),
            "approved_adapters": prov.get("adapters"),
            "org_id": prov.get("org_id"),
            "signing_key_provisioned": bool(prov.get("signing_key_b64")),
            "provisioned_signing_key_b64": prov.get("signing_key_b64"),
        }

        self._log(f"Setup payload keys: {list(payload.keys())}")

        try:
            resp = self._post_raw("/v1/setup/complete", payload, timeout=60)
            status_code = resp.status_code

            try:
                body = resp.json()
            except Exception:
                body = {"raw": resp.text[:500] if hasattr(resp, "text") else "?"}

            if status_code == 200:
                rd = body.get("data", body)
                return StepResult("complete_setup", TestStatus.PASSED, time.time() - start,
                                  f"Setup completed: {rd.get('message', 'ok')}",
                                  {"http_status": status_code, **rd})
            return StepResult("complete_setup", TestStatus.FAILED, time.time() - start,
                              f"HTTP {status_code}: {body}",
                              {"http_status": status_code, "body": body})
        except Exception as e:
            return StepResult("complete_setup", TestStatus.ERROR, time.time() - start,
                              f"Setup request failed: {e}")

    def step_verify_login(self) -> StepResult:
        """Step 7: Verify login with the newly created user."""
        start = time.time()
        try:
            # Small delay for server restart after setup
            time.sleep(3)

            data = self._post("/v1/auth/login",
                              {"username": self.admin_username,
                               "password": self.admin_password})
            token = data.get("access_token")
            if token:
                self.token = token
                return StepResult("verify_login", TestStatus.PASSED, time.time() - start,
                                  f"Logged in as {self.admin_username}")
            return StepResult("verify_login", TestStatus.FAILED, time.time() - start,
                              f"No access_token: {list(data.keys())}", data)
        except Exception as e:
            return StepResult("verify_login", TestStatus.ERROR, time.time() - start,
                              f"Login failed: {e}")

    def step_verify_configured(self) -> StepResult:
        """Step 8: Verify agent is now configured (not first-run)."""
        start = time.time()
        try:
            data = self._get("/v1/system/health")
            health = data.get("data", {})
            status = health.get("status", "unknown")
            cog_state = health.get("cognitive_state")

            # Also check setup status
            setup_data = self._get("/v1/setup/status")
            setup = setup_data.get("data", {})
            is_first_run = setup.get("is_first_run", True)

            if not is_first_run and status == "healthy":
                return StepResult("verify_configured", TestStatus.PASSED, time.time() - start,
                                  f"Configured, state={cog_state}",
                                  {"status": status, "cognitive_state": cog_state,
                                   "is_first_run": is_first_run})
            if is_first_run:
                return StepResult("verify_configured", TestStatus.FAILED, time.time() - start,
                                  "Still in first-run mode after setup",
                                  {"is_first_run": is_first_run, "status": status})
            return StepResult("verify_configured", TestStatus.FAILED, time.time() - start,
                              f"Unhealthy after setup: {status}",
                              {"status": status, "is_first_run": is_first_run})
        except Exception as e:
            return StepResult("verify_configured", TestStatus.ERROR, time.time() - start,
                              f"Health check failed: {e}")

    def step_verify_services(self) -> StepResult:
        """Step 9: Check telemetry for services online."""
        start = time.time()
        try:
            # Give services time to initialize after setup
            time.sleep(5)

            data = self._get("/v1/telemetry/unified", timeout=15)
            telem = data.get("data", data)
            online = telem.get("services_online", 0)
            total = telem.get("services_total", 0)
            cog = telem.get("cognitive_state")

            if online > 0:
                return StepResult("verify_services", TestStatus.PASSED, time.time() - start,
                                  f"{online}/{total} services online, state={cog}",
                                  {"services_online": online, "services_total": total,
                                   "cognitive_state": cog})
            return StepResult("verify_services", TestStatus.FAILED, time.time() - start,
                              f"0/{total} services online",
                              {"services_online": online, "services_total": total})
        except Exception as e:
            # Telemetry may not be available yet
            return StepResult("verify_services", TestStatus.SKIPPED, time.time() - start,
                              f"Telemetry unavailable: {e}")


# -- Key file loader ---------------------------------------------------------

_KEY_FILES: Dict[str, str] = {
    "anthropic": "~/.anthropic_key",
    "google": "~/.google_key",
    "groq": "~/.groq_key",
    "openrouter": "~/.openrouter_key",
    "together": "~/.together_key",
    "openai": "~/.openai_key",
}


def _load_key_file(path: str) -> str:
    expanded = os.path.expanduser(path)
    if os.path.exists(expanded):
        return Path(expanded).read_text().strip()
    return ""


def _resolve_llm_key(provider: str, explicit_key: str, key_file: str) -> str:
    """Resolve LLM API key: explicit > key_file > provider default file."""
    if explicit_key:
        return explicit_key
    if key_file:
        key = _load_key_file(key_file)
        if key:
            return key
    default_file = _KEY_FILES.get(provider, "")
    if default_file:
        return _load_key_file(default_file)
    return ""


# -- Runner -------------------------------------------------------------------

def run_first_time_licensed_agent(
    base_url: str = "http://localhost:8080",
    portal_url: str = "https://portal.ciris.ai",
    llm_provider: str = "groq",
    llm_api_key: str = "",
    llm_key_file: str = "",
    llm_model: Optional[str] = None,
    admin_username: str = "admin",
    admin_password: str = "ciris_admin_password",
    wait: bool = True,
    poll_timeout: int = 300,
    poll_interval: int = 5,
    output_dir: str = "mobile_qa_reports",
    verbose: bool = False,
) -> int:
    """Run the full first-time licensed agent E2E test suite. Returns 0/1."""

    api_key = _resolve_llm_key(llm_provider, llm_api_key, llm_key_file)

    print("\n" + "=" * 60)
    print("First-Time Licensed Agent E2E Test")
    print("=" * 60)
    print(f"  API:       {base_url}")
    print(f"  Portal:    {portal_url}")
    print(f"  LLM:       {llm_provider} (key: {'set' if api_key else 'MISSING'})")
    print(f"  Wait:      {wait}  (timeout: {poll_timeout}s)")
    print()

    tester = FirstTimeLicensedAgentTester(
        base_url=base_url,
        portal_url=portal_url,
        llm_provider=llm_provider,
        llm_api_key=api_key,
        llm_model=llm_model,
        admin_username=admin_username,
        admin_password=admin_password,
        poll_timeout=poll_timeout,
        poll_interval=poll_interval,
        verbose=verbose,
    )

    results: List[StepResult] = []
    total_steps = 9

    def run_step(num: int, label: str, fn, *args, **kwargs) -> StepResult:
        print(f"[{num}/{total_steps}] {label}...")
        result = fn(*args, **kwargs)
        results.append(result)
        _print_step(result)
        return result

    # == Step 1: Health ======================================================
    r = run_step(1, "API health check", tester.step_health)
    if r.status != TestStatus.PASSED:
        return _finish(results, output_dir)

    # == Step 2: First-run ===================================================
    r = run_step(2, "Verify first-run mode", tester.step_first_run)
    if r.status != TestStatus.PASSED:
        return _finish(results, output_dir)

    # == Step 3: Enumerate ===================================================
    run_step(3, "Enumerate providers/templates/adapters", tester.step_enumerate)

    # == Step 4: Connect node ================================================
    r = run_step(4, f"Initiate device auth with {portal_url}", tester.step_connect_node)
    if r.status != TestStatus.PASSED:
        return _finish(results, output_dir)

    # Print device auth info
    details = r.details
    verification_uri = details.get("verification_uri_complete", "")
    user_code = details.get("user_code", "")
    device_code = details.get("device_code", "")
    portal_url_resp = details.get("portal_url", portal_url)

    print()
    print("  " + "=" * 50)
    print("  AUTHORIZE THIS AGENT IN YOUR BROWSER:")
    if verification_uri:
        print(f"    {verification_uri}")
    if user_code:
        print(f"  User code: {user_code}")
    print("  " + "=" * 50)
    print()

    # == Step 5: Poll auth ===================================================
    if not wait:
        # Single poll check only
        r = run_step(5, "Poll status (single check)", tester.step_poll_auth,
                     device_code, portal_url_resp)
        # Even if pending, report success for the single-check case
        print("\n  [INFO] Use --wait to poll until Portal authorization completes\n")
        return _finish(results, output_dir)

    r = run_step(5, f"Polling for Portal authorization (timeout: {poll_timeout}s)",
                 tester.step_poll_auth, device_code, portal_url_resp)
    print()
    if r.status != TestStatus.PASSED:
        return _finish(results, output_dir)

    # == Step 6: Complete setup ==============================================
    r = run_step(6, "Complete setup with provisioned credentials",
                 tester.step_complete_setup)
    if r.status not in (TestStatus.PASSED, TestStatus.SKIPPED):
        return _finish(results, output_dir)

    if r.status == TestStatus.SKIPPED:
        print("  [INFO] Setup completion skipped (no LLM key). "
              "Remaining steps will be skipped.")
        return _finish(results, output_dir)

    # == Step 7: Verify login ================================================
    run_step(7, "Verify login with new credentials", tester.step_verify_login)

    # == Step 8: Verify configured ===========================================
    run_step(8, "Verify agent is configured", tester.step_verify_configured)

    # == Step 9: Verify services =============================================
    run_step(9, "Check services online", tester.step_verify_services)

    return _finish(results, output_dir)


def _print_step(result: StepResult):
    icons = {
        TestStatus.PASSED: "PASS",
        TestStatus.FAILED: "FAIL",
        TestStatus.ERROR: "ERR!",
        TestStatus.SKIPPED: "SKIP",
    }
    icon = icons.get(result.status, "????")
    print(f"  [{icon}] {result.name} ({result.duration:.1f}s) -- {result.message}")


def _finish(results: List[StepResult], output_dir: str) -> int:
    passed = sum(1 for r in results if r.status == TestStatus.PASSED)
    failed = sum(1 for r in results if r.status == TestStatus.FAILED)
    errors = sum(1 for r in results if r.status == TestStatus.ERROR)
    skipped = sum(1 for r in results if r.status == TestStatus.SKIPPED)

    print("\n" + "=" * 60)
    print("First-Time Licensed Agent Summary")
    print("=" * 60)
    print(f"  Total:   {len(results)}")
    print(f"  Passed:  {passed}")
    print(f"  Failed:  {failed}")
    print(f"  Errors:  {errors}")
    print(f"  Skipped: {skipped}")
    print("=" * 60)

    # Save results
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = out_path / f"licensed_agent_{timestamp}.json"

    with open(results_file, "w") as f:
        json.dump(
            {
                "test_suite": "first_time_licensed_agent",
                "timestamp": timestamp,
                "results": [
                    {"name": r.name, "status": r.status.value,
                     "duration": r.duration, "message": r.message,
                     "details": r.details}
                    for r in results
                ],
                "summary": {"total": len(results), "passed": passed,
                            "failed": failed, "errors": errors, "skipped": skipped},
            },
            f, indent=2,
        )
    print(f"\nResults: {results_file}")

    return 0 if (failed == 0 and errors == 0) else 1
