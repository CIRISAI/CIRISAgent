"""One node of the local mesh, brought up the way the first-run wizard does it.

Runs INSIDE a mesh container (tools/qa_runner/local_mesh/Dockerfile). On a fresh
home it boots the agent in first-run mode and then, in the wizard's order:

  1. mint the owner's federation ID     POST <brain>/v1/self/identity
  2. claim the node with its PIN         POST <node>/v1/setup/claim-remote
  3. complete setup                      POST <brain>/v1/setup/complete
  4. log in as the owner, and announce   POST <node>/v1/federation/announce

then writes `<home>/mesh_ready.json` and keeps the backend running. On a home
that is already set up it only starts the backend, so a container restart is a
restart of the same node (same owner, same fedID, same keys), which is what the
CI chat stage does to the linux leg.

Steps 1-2 are tools/qa_runner/node_claim.py and step 4 is
tools/qa_runner/announce_bundle.py: the same code the QA runner and the gate
use, so the mesh cannot drift from them.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from tools.qa_runner.announce_bundle import check_announce_bundle
from tools.qa_runner.node_claim import claim_node, mint_federation_id, wait_for_claim_pin

BRAIN = "http://127.0.0.1:8080"
NODE = "http://127.0.0.1:4243"
READY_MARKER = "mesh_ready.json"


def _home() -> Path:
    return Path(os.environ["CIRIS_HOME"])


def _log(msg: str) -> None:
    print(f"[mesh-bootstrap] {msg}", flush=True)


def _backend_cmd() -> List[str]:
    # --mock-llm is requested explicitly: the mesh exercises person-to-person
    # chat between nodes, which never reaches the agent's LLM.
    return [sys.executable, "main.py", "--adapter", "api", "--port", "8080", "--mock-llm"]


def _backend_env() -> Dict[str, str]:
    env = os.environ.copy()
    env.setdefault("CIRIS_AGENT_ID", "qa-runner-ciris-agent")
    # Reachable through the container's published port, not only its loopback.
    env.setdefault("CIRIS_API_HOST", "0.0.0.0")
    env.setdefault("CIRIS_TESTING_MODE", "true")
    env.setdefault("CIRIS_API_RATE_LIMIT_ENABLED", "false")
    env.setdefault("CIRIS_TRACE_RUN_KIND", "qa")
    return env


#: The backend process, so a wait can stop the moment it exits.
_BACKEND: Optional[subprocess.Popen] = None


async def _wait_health(client: httpx.AsyncClient, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _BACKEND is not None and _BACKEND.poll() is not None:
            raise RuntimeError(f"the backend exited (rc={_BACKEND.returncode}) before it answered; see its log")
        try:
            if (await client.get(f"{BRAIN}/v1/system/health", timeout=5.0)).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        await asyncio.sleep(1.0)
    return False


async def _login(client: httpx.AsyncClient, username: str, password: str, timeout_s: float) -> Optional[str]:
    """The owner's token. Retried: setup/complete resumes the runtime before auth answers."""
    deadline = time.monotonic() + timeout_s
    last = ""
    while time.monotonic() < deadline:
        try:
            r = await client.post(
                f"{BRAIN}/v1/auth/login", json={"username": username, "password": password}, timeout=10.0
            )
            if r.status_code == 200:
                return str(r.json()["access_token"])
            last = f"{r.status_code} {r.text[:160]}"
        except httpx.HTTPError as exc:
            last = f"{type(exc).__name__}: {exc}"
        await asyncio.sleep(2.0)
    _log(f"login never succeeded: {last}")
    return None


async def first_run(username: str, password: str, label: str, launched_at: float) -> Dict[str, Any]:
    """Wizard steps 1-4 against this container's own backend. Raises on any failure."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        if not await _wait_health(client, 300.0):
            raise RuntimeError("the agent never answered /v1/system/health within 300s")
        pin, pin_file = await wait_for_claim_pin([str(_home())], 180.0, launched_at)
        if pin is None:
            raise RuntimeError(f"the node wrote no claim PIN under {_home()}")
        minted, data, error = await mint_federation_id(client, BRAIN, label)
        if not minted:
            raise RuntimeError(f"mint failed: {error}")
        claimed = await claim_node(client, BRAIN, pin, username, password, NODE)
        if not claimed.ok:
            raise RuntimeError(f"claim failed: {claimed.detail}")
        _log(f"claimed: owner={claimed.owner} fedID={claimed.federation_key_id}")

        r = await client.post(
            f"{BRAIN}/v1/setup/complete",
            json={
                "llm_provider": "openai",
                "llm_api_key": "test-key-for-qa",
                "llm_model": "gpt-4",
                "template_id": "default",
                "enabled_adapters": ["api"],
                "adapter_config": {},
                "admin_username": username,
                "admin_password": password,
                "agent_port": 8080,
            },
            timeout=60.0,
        )
        if r.status_code != 200:
            raise RuntimeError(f"setup/complete {r.status_code}: {r.text[:300]}")

        token = await _login(client, username, password, 180.0)
        if token is None:
            raise RuntimeError("could not log in as the owner after setup")
        announce = await check_announce_bundle(client, NODE, {"Authorization": f"Bearer {token}"})
        _log(f"announce: {announce.status} {getattr(announce, 'message', '')}")
        return {
            "owner": claimed.owner,
            "federation_key_id": claimed.federation_key_id,
            "label": label,
            "announce": announce.details(),
        }


async def _restarted() -> bool:
    async with httpx.AsyncClient(timeout=10.0) as client:
        return await _wait_health(client, 300.0)


def main() -> int:
    home = _home()
    home.mkdir(parents=True, exist_ok=True)
    username = os.environ.get("MESH_USERNAME", "qaadmin")
    password = os.environ.get("MESH_PASSWORD", "qa_test_password_12345")
    label = os.environ.get("MESH_LABEL") or f"qa-node-{int(time.time())}"
    marker = home / READY_MARKER
    fresh = not marker.exists()

    launched_at = time.time()
    global _BACKEND
    backend = _BACKEND = subprocess.Popen(_backend_cmd(), env=_backend_env(), cwd="/app")
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: backend.terminate())

    if fresh:
        try:
            info = asyncio.run(first_run(username, password, label, launched_at))
        except Exception as exc:  # noqa: BLE001 - reported, then the container exits non-zero
            _log(f"FIRST RUN FAILED: {exc}")
            (home / "mesh_failed.txt").write_text(f"{exc}\n")
            backend.terminate()
            backend.wait(timeout=60)
            return 1
        marker.write_text(json.dumps(info, indent=2, sort_keys=True) + "\n")
        _log(f"ready: {json.dumps({k: info[k] for k in ('owner', 'federation_key_id')})}")
    else:
        _log("home already set up: restarting the same node")
        if asyncio.run(_restarted()):
            (home / "mesh_restarted.txt").write_text(f"{time.time()}\n")
    return backend.wait()


if __name__ == "__main__":
    sys.exit(main())
