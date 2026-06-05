"""
AgentMode QA tests for ``GET/PUT /v1/system/agent-mode``.

Validates the global agent mode endpoints introduced for 2.9.4 federation:
- GET returns current mode + disk facts (OBSERVER+)
- PUT switches mode (SYSTEM_ADMIN only)
- PUT to SERVER without 256 GiB free returns 400 ``INSUFFICIENT_DISK``
- PUT with an invalid mode returns 422

Schema reference: ``ciris_engine/schemas/runtime/agent_mode.py``.
Endpoint reference: ``ciris_engine/logic/adapters/api/routes/system/agent_mode.py``.
"""

from __future__ import annotations

import traceback
from typing import Any, Dict, List, Optional

import requests
from rich.console import Console

from ciris_sdk.client import CIRISClient

# 256 GiB — must match SERVER_MINIMUM_DISK_BYTES in ciris_engine/constants.py
SERVER_MINIMUM_DISK_BYTES = 256 * 1024 * 1024 * 1024

VALID_MODES = {"client", "proxy", "server"}


class AgentModeTests:
    """Test the global AgentMode endpoints."""

    def __init__(self, client: CIRISClient, console: Console):
        self.client = client
        self.console = console
        self.results: List[Dict[str, Any]] = []
        self._original_mode: Optional[str] = None

    # ------------------------------------------------------------------
    # Transport helpers
    # ------------------------------------------------------------------
    def _resolve_base_url(self) -> str:
        base_url = getattr(self.client, "_base_url", None)
        if not base_url:
            transport = getattr(self.client, "_transport", None)
            if transport:
                base_url = getattr(transport, "base_url", None) or getattr(transport, "_base_url", None)
        return base_url or "http://localhost:8000"

    def _resolve_token(self) -> Optional[str]:
        transport = getattr(self.client, "_transport", None)
        if transport is None:
            return None
        return getattr(transport, "_api_key", None) or getattr(transport, "api_key", None)

    def _headers(self, token: Optional[str]) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _get_mode(self, token: Optional[str]) -> Dict[str, Any]:
        url = f"{self._resolve_base_url()}/v1/system/agent-mode"
        resp = requests.get(url, headers=self._headers(token), timeout=10)
        return {"status_code": resp.status_code, "body": _safe_json(resp)}

    def _put_mode(self, token: Optional[str], mode: str) -> Dict[str, Any]:
        url = f"{self._resolve_base_url()}/v1/system/agent-mode"
        resp = requests.put(
            url, headers=self._headers(token), json={"mode": mode}, timeout=15
        )
        return {"status_code": resp.status_code, "body": _safe_json(resp)}

    # ------------------------------------------------------------------
    # Test orchestrator
    # ------------------------------------------------------------------
    async def run(self) -> List[Dict[str, Any]]:
        self.console.print("\n[cyan]🎛️  Testing AgentMode endpoints[/cyan]")

        tests = [
            ("GET requires auth (401 when missing)", self.test_get_requires_auth),
            ("GET returns valid AgentModeStatus shape", self.test_get_status_shape),
            ("GET reports SERVER eligibility matches disk facts", self.test_server_eligibility_consistent),
            ("PUT no-op to current mode succeeds", self.test_put_noop_current_mode),
            ("PUT invalid mode returns 422", self.test_put_invalid_mode),
            ("PUT SERVER honors 256 GiB disk gate", self.test_put_server_disk_gate),
            ("PUT requires auth (401 when missing)", self.test_put_requires_auth),
        ]

        for name, test_func in tests:
            try:
                await test_func()
                self.results.append({"test": name, "status": "✅ PASS", "error": None})
                self.console.print(f"  ✅ {name}")
            except Exception as exc:  # noqa: BLE001 — we want to record every failure
                self.results.append({"test": name, "status": "❌ FAIL", "error": str(exc)})
                self.console.print(f"  ❌ {name}: {str(exc)[:200]}")
                if self.console.is_terminal:
                    self.console.print(f"     [dim]{traceback.format_exc()[:600]}[/dim]")

        # Best-effort restore: if we mutated the mode, put it back.
        if self._original_mode is not None:
            try:
                self._put_mode(self._resolve_token(), self._original_mode)
            except Exception:
                pass

        self._print_summary()
        return self.results

    # ------------------------------------------------------------------
    # Individual tests
    # ------------------------------------------------------------------
    async def test_get_requires_auth(self) -> None:
        result = self._get_mode(token=None)
        if result["status_code"] not in (401, 403):
            raise AssertionError(
                f"GET without auth should be 401/403, got {result['status_code']}: {result['body']}"
            )

    async def test_get_status_shape(self) -> None:
        token = self._resolve_token()
        result = self._get_mode(token=token)
        if result["status_code"] != 200:
            raise AssertionError(f"GET expected 200, got {result['status_code']}: {result['body']}")

        body = result["body"]
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            raise AssertionError(f"GET response missing 'data' object, got: {body}")

        required = {
            "mode",
            "available_disk_bytes",
            "server_minimum_disk_bytes",
            "server_eligible",
            "data_dir",
        }
        missing = required - data.keys()
        if missing:
            raise AssertionError(f"GET response missing fields: {missing} (got keys {sorted(data.keys())})")

        if data["mode"] not in VALID_MODES:
            raise AssertionError(f"GET returned invalid mode: {data['mode']!r}")
        if not isinstance(data["available_disk_bytes"], int) or data["available_disk_bytes"] < 0:
            raise AssertionError(f"available_disk_bytes invalid: {data['available_disk_bytes']!r}")
        if data["server_minimum_disk_bytes"] != SERVER_MINIMUM_DISK_BYTES:
            raise AssertionError(
                f"server_minimum_disk_bytes drift: got {data['server_minimum_disk_bytes']}, "
                f"expected {SERVER_MINIMUM_DISK_BYTES}"
            )
        if not isinstance(data["server_eligible"], bool):
            raise AssertionError(f"server_eligible not bool: {data['server_eligible']!r}")
        if not isinstance(data["data_dir"], str) or not data["data_dir"]:
            raise AssertionError(f"data_dir empty/non-string: {data['data_dir']!r}")

        # Stash the live mode so later tests can restore.
        self._original_mode = data["mode"]

    async def test_server_eligibility_consistent(self) -> None:
        token = self._resolve_token()
        result = self._get_mode(token=token)
        data = result["body"]["data"]
        expected = data["available_disk_bytes"] >= data["server_minimum_disk_bytes"]
        if data["server_eligible"] is not expected:
            raise AssertionError(
                f"server_eligible={data['server_eligible']} contradicts disk facts "
                f"(available={data['available_disk_bytes']}, minimum={data['server_minimum_disk_bytes']})"
            )

    async def test_put_noop_current_mode(self) -> None:
        token = self._resolve_token()
        snapshot = self._get_mode(token=token)
        current_mode = snapshot["body"]["data"]["mode"]
        result = self._put_mode(token=token, mode=current_mode)
        if result["status_code"] != 200:
            raise AssertionError(
                f"PUT to current mode {current_mode!r} should be 200, "
                f"got {result['status_code']}: {result['body']}"
            )
        body = result["body"]
        if not isinstance(body, dict):
            raise AssertionError(f"PUT response not a JSON object: {body!r}")
        if "data" not in body or "requires_restart" not in body:
            raise AssertionError(f"PUT response missing data/requires_restart: {body!r}")
        if body["requires_restart"] is not True:
            raise AssertionError(f"requires_restart should be True, got {body['requires_restart']!r}")

    async def test_put_invalid_mode(self) -> None:
        token = self._resolve_token()
        result = self._put_mode(token=token, mode="banana")
        if result["status_code"] != 422:
            raise AssertionError(
                f"PUT invalid mode should be 422, got {result['status_code']}: {result['body']}"
            )

    async def test_put_server_disk_gate(self) -> None:
        token = self._resolve_token()
        snapshot = self._get_mode(token=token)
        data = snapshot["body"]["data"]
        eligible = data["server_eligible"]
        available = data["available_disk_bytes"]

        result = self._put_mode(token=token, mode="server")
        if eligible:
            # Box has the 256 GiB headroom — the switch should succeed.
            if result["status_code"] != 200:
                raise AssertionError(
                    f"PUT SERVER expected 200 on eligible host (free={available}), "
                    f"got {result['status_code']}: {result['body']}"
                )
        else:
            # Disk-gate must fire with the documented structured error.
            if result["status_code"] != 400:
                raise AssertionError(
                    f"PUT SERVER expected 400 on ineligible host (free={available}), "
                    f"got {result['status_code']}: {result['body']}"
                )
            body = result["body"]
            if not isinstance(body, dict) or body.get("error") != "INSUFFICIENT_DISK":
                raise AssertionError(f"Expected INSUFFICIENT_DISK error envelope, got: {body!r}")
            if not isinstance(body.get("available_bytes"), int):
                raise AssertionError(f"available_bytes missing/non-int: {body!r}")
            if body.get("required_bytes") != SERVER_MINIMUM_DISK_BYTES:
                raise AssertionError(
                    f"required_bytes drift: got {body.get('required_bytes')}, "
                    f"expected {SERVER_MINIMUM_DISK_BYTES}"
                )

    async def test_put_requires_auth(self) -> None:
        result = self._put_mode(token=None, mode="proxy")
        if result["status_code"] not in (401, 403):
            raise AssertionError(
                f"PUT without auth should be 401/403, got {result['status_code']}: {result['body']}"
            )

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------
    def _print_summary(self) -> None:
        passed = sum(1 for r in self.results if r["status"].startswith("✅"))
        total = len(self.results)
        self.console.print(f"\n[bold]AgentMode: {passed}/{total} passed[/bold]")


def _safe_json(resp: requests.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return resp.text
