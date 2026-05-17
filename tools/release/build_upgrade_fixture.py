#!/usr/bin/env python3
"""
Deterministic upgrade-fixture builder.

Generates a frozen agent DB snapshot for the current release. The snapshot is
consumed by the next-major upgrade-compat test matrix (e.g. 2.9.0 boots
2.8.13's DB through its bootstrap path and asserts a clean state).

The scenario is intentionally small and deterministic:
  1. Fresh install with isolated --data-dir
  2. Setup wizard runs with a known admin password
  3. A fixed series of mock-LLM interactions populates graph/audit/telemetry
  4. Graceful shutdown drains the chain
  5. ciris_engine.db + ciris_audit.db get copied to out/
  6. MANIFEST.json records version, sha256, scenario digest

Usage:
    python -m tools.release.build_upgrade_fixture --out fixtures/v2.8.13
    python -m tools.release.build_upgrade_fixture --out fixtures/v2.8.13 --port 8123

The output directory ends up checkable into 2.9.0+'s
tests/fixtures/upgrade_snapshots/v2.8.13/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ADMIN_USER = "admin"
ADMIN_PASSWORD = "fixture_seed_password_v1"  # deterministic, never used in prod
SCENARIO_VERSION = "v1"

# Fixed scenario — keep this stable across patch releases so the upgrade test
# diff stays meaningful. If you change the scenario, bump SCENARIO_VERSION.
SCENARIO_MESSAGES = [
    "Hello, what is your name?",
    "What cognitive states do you support?",
    "Remember that fixtures should be deterministic.",
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _scenario_digest() -> str:
    payload = json.dumps(
        {"version": SCENARIO_VERSION, "messages": SCENARIO_MESSAGES, "admin_user": ADMIN_USER},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def _http_json(method: str, url: str, body: dict | None = None, token: str | None = None, timeout: float = 30.0) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _wait_for_health(base_url: str, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(f"{base_url}/v1/system/health", timeout=2.0).read()
            return
        except (urllib.error.URLError, ConnectionRefusedError, TimeoutError) as e:
            last_err = e
            time.sleep(1.0)
    raise RuntimeError(f"server did not become healthy within {timeout}s: {last_err}")


def _run_scenario(base_url: str) -> None:
    # Setup wizard — creates admin user
    try:
        _http_json(
            "POST",
            f"{base_url}/v1/system/setup",
            {"admin_username": ADMIN_USER, "admin_password": ADMIN_PASSWORD},
            timeout=30.0,
        )
    except urllib.error.HTTPError as e:
        if e.code != 409:  # already configured
            raise

    # Login
    tok = _http_json(
        "POST", f"{base_url}/v1/auth/login", {"username": ADMIN_USER, "password": ADMIN_PASSWORD}
    )["access_token"]

    # Deterministic interactions
    for msg in SCENARIO_MESSAGES:
        _http_json("POST", f"{base_url}/v1/agent/interact", {"message": msg}, token=tok, timeout=60.0)


def _graceful_shutdown(base_url: str, token: str | None) -> None:
    if not token:
        return
    try:
        _http_json("POST", f"{base_url}/v1/system/shutdown", {"reason": "fixture build"}, token=token, timeout=10.0)
    except Exception:
        pass  # we'll SIGTERM the process anyway


def build_fixture(out_dir: Path, port: int = 8123, ciris_version: str | None = None) -> Path:
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    work = Path(tempfile.mkdtemp(prefix="upgrade-fixture-"))
    data_dir = work / "data"
    data_dir.mkdir()

    env = os.environ.copy()
    env["CIRIS_DATA_DIR"] = str(data_dir)
    env["CIRIS_PORT"] = str(port)

    base_url = f"http://127.0.0.1:{port}"
    print(f"[fixture] data_dir={data_dir} port={port}", flush=True)

    proc = subprocess.Popen(
        [sys.executable, "main.py", "--adapter", "api", "--mock-llm", "--port", str(port)],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    token: str | None = None
    try:
        _wait_for_health(base_url, timeout=90.0)
        print("[fixture] server healthy — running scenario", flush=True)
        _run_scenario(base_url)
        # Re-login to capture token for shutdown
        token = _http_json(
            "POST", f"{base_url}/v1/auth/login", {"username": ADMIN_USER, "password": ADMIN_PASSWORD}
        )["access_token"]
        _graceful_shutdown(base_url, token)
        # Allow time for chain flush
        time.sleep(3.0)
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=15.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    # Locate produced DBs
    engine_db = data_dir / "ciris_engine.db"
    audit_db = data_dir / "ciris_audit.db"
    if not engine_db.exists():
        raise RuntimeError(f"ciris_engine.db not found at {engine_db}")

    # Copy artifacts
    out_engine = out_dir / "ciris_engine.db"
    out_audit = out_dir / "ciris_audit.db"
    shutil.copy2(engine_db, out_engine)
    if audit_db.exists():
        shutil.copy2(audit_db, out_audit)

    manifest = {
        "ciris_version": ciris_version or os.environ.get("CIRIS_VERSION", "unknown"),
        "scenario_version": SCENARIO_VERSION,
        "scenario_digest": _scenario_digest(),
        "scenario_messages": SCENARIO_MESSAGES,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": {
            "ciris_engine.db": {"sha256": _sha256(out_engine), "bytes": out_engine.stat().st_size},
        },
    }
    if out_audit.exists():
        manifest["artifacts"]["ciris_audit.db"] = {
            "sha256": _sha256(out_audit),
            "bytes": out_audit.stat().st_size,
        }

    manifest_path = out_dir / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"[fixture] wrote {manifest_path}", flush=True)
    print(json.dumps(manifest, indent=2), flush=True)

    shutil.rmtree(work, ignore_errors=True)
    return manifest_path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="Output directory for fixture artifacts")
    ap.add_argument("--port", type=int, default=8123, help="API server port (default: 8123)")
    ap.add_argument("--version", help="CIRIS version label to embed in MANIFEST (default: env CIRIS_VERSION)")
    args = ap.parse_args()
    build_fixture(Path(args.out), port=args.port, ciris_version=args.version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
