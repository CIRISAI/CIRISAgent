"""scripts/verify_install.sh claims the node before /v1/setup/complete, fail-closed."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_install.sh"

pytestmark = pytest.mark.skipif(not shutil.which("curl") or not shutil.which("bash"), reason="needs bash + curl")


class FakeAgent(ThreadingHTTPServer):
    """Brain and node on one port: records every call in order."""

    def __init__(self, booting_502s: int = 0) -> None:
        self.calls: List[str] = []
        self.bodies: Dict[str, Any] = {}
        self.booting_502s = booting_502s
        super().__init__(("127.0.0.1", 0), Handler)


class Handler(BaseHTTPRequestHandler):
    server: FakeAgent

    def log_message(self, *args: Any) -> None:
        pass

    def _send(self, status: int, body: Any) -> None:
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        self.server.calls.append(f"GET {self.path}")
        if self.path == "/v1/federation/node-code":
            return self._send(200, {"data": {"node_code": "NODECODE-123"}})
        self._send(404, {})

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        self.server.calls.append(f"POST {self.path}")
        self.server.bodies[self.path] = body
        if self.path == "/v1/self/identity":
            if self.server.booting_502s:
                self.server.booting_502s -= 1
                return self._send(502, {"detail": "The folded node did not answer POST /v1/self/identity."})
            return self._send(200, {"key_id": "fed-qa"})
        if self.path in ("/v1/setup/claim-remote", "/v1/setup/complete"):
            return self._send(200, {"data": {"message": "ok"}})
        self._send(404, {})


def _run(tmp_path: Path, agent: FakeAgent, claim_wait: int = 4) -> subprocess.CompletedProcess:
    # The script's functions without its trailing `main "$@"`, then the one check.
    lib = tmp_path / "verify_lib.sh"
    lines = SCRIPT.read_text().splitlines()
    assert lines[-1].strip() == 'main "$@"'
    lib.write_text("\n".join(lines[:-1]) + "\n")
    url = f"http://127.0.0.1:{agent.server_address[1]}"
    driver = (
        f'source "{lib}"; BASE_URL="{url}"; TIMEOUT=5; CLAIM_HOME="{tmp_path}"; NODE_URL="{url}"; '
        f"CLAIM_WAIT={claim_wait}; ADMIN_USER=qa_verify_user; check_setup_complete"
    )
    return subprocess.run(["bash", "-c", driver], capture_output=True, text=True, timeout=120)


@pytest.fixture
def agent():
    server = FakeAgent()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()


def test_the_install_check_claims_before_setup(tmp_path, agent):
    (tmp_path / "claim_pin").write_text("Q4YC-AZQA\n")
    result = _run(tmp_path, agent)
    assert result.returncode == 0, result.stdout + result.stderr
    assert agent.calls == [
        "POST /v1/self/identity",
        "GET /v1/federation/node-code",
        "POST /v1/setup/claim-remote",
        "POST /v1/setup/complete",
    ]
    claim = agent.bodies["/v1/setup/claim-remote"]
    assert claim["claim_pin"] == "Q4YC-AZQA" and claim["node_code"] == "NODECODE-123"
    assert claim["owner_username"] == "qa_verify_user"


def test_no_pin_fails_closed_and_setup_is_never_posted(tmp_path, agent):
    result = _run(tmp_path, agent, claim_wait=1)
    assert result.returncode == 3
    assert "No claim PIN" in result.stdout + result.stderr
    assert agent.calls == []


def test_the_boot_window_is_waited_out(tmp_path, agent):
    (tmp_path / "claim_pin").write_text('{"pin": "QCKE-AY69"}')
    agent.booting_502s = 2
    result = _run(tmp_path, agent, claim_wait=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert agent.calls.count("POST /v1/self/identity") == 3
    assert agent.bodies["/v1/setup/claim-remote"]["claim_pin"] == "QCKE-AY69"
