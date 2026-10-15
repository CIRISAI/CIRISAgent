"""Prove an upgraded, pre-claim deployment can be claimed: brain ROOT, no node owner.

EVERY NODE IS ALWAYS CLAIMED, and an agent holds on an unowned node. A
deployment set up before that rule has a brain ROOT WA and no node owner; the
node then mints NO claim PIN ("node already has a ROOT owner — no first-run
claim PIN minted (setup/root is closed)"). This checks that such a node can
still be claimed, the deployer's way, and that the agent then runs.

  Phase A  boot --old-tree (code without the ownership gate) on a fresh
           CIRIS_HOME and complete setup WITHOUT claiming: the brain mints a ROOT.
  Phase B  boot --new-tree on the same home and assert, failing loudly:
             - /v1/system/health is 200 and carries `node_unclaimed`;
             - the processor is held (cognitive_state is not work/wakeup);
             - the ROOT signs in, POST /v1/self/identity, POST /v1/self/upgrade-owner -> 200;
             - the processor starts (state work/wakeup) and `node_unclaimed` clears.

Real wheel, real node, a scratch CIRIS_HOME with every data-path key pinned to it.
It binds :4243 (fixed by the node fold) and --port, and REFUSES to start if either
is already in use, so it never clashes with a node already running on the host.
Never prints the PIN.

  python tools/release/check_upgrade_owner_path.py --old-tree <dir> --new-tree . --home <scratch>
"""

from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import httpx

NODE_PORT = 4243
USER, PASSWORD = "deployer-owner", "Upgrade-Path-12345"
RUNNING = ("work", "wakeup")


def _busy(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def _env(home: Path) -> Dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("CIRIS_")}
    data = home / "data"
    env.update(
        CIRIS_HOME=str(home),
        CIRIS_DB_PATH=str(data / "ciris_engine.db"),
        CIRIS_DATA_DIR=str(data),
        SECRETS_DB_PATH=str(data / "secrets.db"),
        AUDIT_LOG_PATH=str(data / "audit_logs.jsonl"),
        PYTHONUNBUFFERED="1",
    )
    return env


class Agent:
    def __init__(self, python: str, tree: Path, home: Path, port: int, log: Path) -> None:
        self.base = f"http://127.0.0.1:{port}"
        for p in (NODE_PORT, port):
            if _busy(p):
                sys.exit(f"ABORT: :{p} is in use; refusing to clash with another process")
        self.log = log
        self.proc = subprocess.Popen(
            [python, "main.py", "--adapter", "api", "--mock-llm", "--port", str(port)],
            cwd=tree,
            env=_env(home),
            stdout=open(log, "w"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self.port = port
        deadline = time.time() + 180
        while time.time() < deadline:
            if self.proc.poll() is not None:
                sys.exit(f"FAIL: agent exited rc={self.proc.returncode}; see {log}")
            try:
                if httpx.get(f"{self.base}/v1/system/health", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(2)
        else:
            self.stop()
            sys.exit(f"FAIL: never healthy; see {log}")
        db = [line for line in log.read_text(errors="replace").splitlines() if "Database parent dir ready" in line]
        if not db or str(home) not in db[0]:
            self.stop()
            sys.exit(f"ABORT: the agent is not on the scratch database: {db[:1]}")

    def health(self) -> Tuple[int, str, List[str]]:
        r = httpx.get(f"{self.base}/v1/system/health", timeout=10)
        data = r.json().get("data", {})
        return r.status_code, str(data.get("cognitive_state")), [str(w.get("code")) for w in data.get("warnings", [])]

    def stop(self) -> None:
        try:
            os.killpg(self.proc.pid, signal.SIGINT)
            self.proc.wait(60)
        except Exception:  # noqa: BLE001
            os.killpg(self.proc.pid, signal.SIGKILL)
            self.proc.wait(30)
        for _ in range(30):
            if not _busy(NODE_PORT) and not _busy(self.port):
                return
            time.sleep(1)


def _check(ok: bool, what: str) -> None:
    print(("PASS " if ok else "FAIL ") + what, flush=True)
    if not ok:
        raise SystemExit(1)


def phase_a(args: argparse.Namespace) -> None:
    args.home.mkdir(parents=True, exist_ok=True)
    agent = Agent(args.python, args.old_tree, args.home, args.port, args.home / "phaseA.out")
    try:
        r = httpx.post(
            f"{agent.base}/v1/setup/complete",
            json={
                "llm_provider": "openai",
                "llm_api_key": "test-key",
                "llm_model": "gpt-4",
                "template_id": "default",
                "enabled_adapters": ["api"],
                "adapter_config": {},
                "admin_username": USER,
                "admin_password": PASSWORD,
                "agent_port": args.port,
            },
            timeout=120,
        )
        _check(r.status_code == 200, f"phase A: old code completes setup without a claim (HTTP {r.status_code})")
        time.sleep(15)
    finally:
        agent.stop()


def phase_b(args: argparse.Namespace) -> None:
    agent = Agent(args.python, args.new_tree, args.home, args.port, args.home / "phaseB.out")
    try:
        time.sleep(15)
        status, state, codes = agent.health()
        _check(status == 200, f"upgrade boot: health is 200 while held (HTTP {status})")
        _check("node_unclaimed" in codes, f"upgrade boot: health carries node_unclaimed ({codes})")
        _check(state not in RUNNING, f"upgrade boot: the processor is held (cognitive_state={state})")

        login = httpx.post(f"{agent.base}/v1/auth/login", json={"username": USER, "password": PASSWORD}, timeout=60)
        _check(login.status_code == 200, f"the existing ROOT signs in (HTTP {login.status_code})")
        hdr = {"Authorization": f"Bearer {login.json()['access_token']}"}
        ident = httpx.post(f"{agent.base}/v1/self/identity", json={"label": USER}, headers=hdr, timeout=120)
        _check(ident.status_code == 200, f"POST /v1/self/identity (HTTP {ident.status_code})")
        up = httpx.post(f"{agent.base}/v1/self/upgrade-owner", json={}, headers=hdr, timeout=120)
        _check(up.status_code == 200, f"POST /v1/self/upgrade-owner (HTTP {up.status_code}: {up.text[:300]})")
        print(f"     owner-binding: {up.json()}", flush=True)

        deadline = time.time() + 120
        while time.time() < deadline:
            status, state, codes = agent.health()
            if state in RUNNING and "node_unclaimed" not in codes:
                break
            time.sleep(3)
        _check(state in RUNNING, f"after the claim: the processor starts (cognitive_state={state})")
        _check("node_unclaimed" not in codes, f"after the claim: node_unclaimed clears ({codes})")
    finally:
        agent.stop()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--old-tree", type=Path, required=True, help="code WITHOUT the ownership gate")
    p.add_argument("--new-tree", type=Path, required=True, help="code under test")
    p.add_argument("--home", type=Path, required=True, help="a fresh scratch CIRIS_HOME")
    p.add_argument("--python", default=sys.executable)
    p.add_argument("--port", type=int, default=18080)
    p.add_argument("--phase", choices=["A", "B", "AB"], default="AB")
    args = p.parse_args()
    if "A" in args.phase:
        phase_a(args)
    if "B" in args.phase:
        phase_b(args)
    print("OK: an upgraded pre-claim deployment is held, then claimed via upgrade-owner, then runs")


if __name__ == "__main__":
    main()
