"""CSD-129 agent step: the accord_halt QA module meeting CIRISServer's native harness (#769).

The server's `harness/native` scenario `halt` mints a test-anchor mesh and hands
this runner what it needs through files in one directory:

  1. agent_handoff.json  (harness) the env block + canonical + holders
  2. agent_ready.json    (us)      {"agent_id_hash", "token"}
  3. halt_fired.json     (harness) {"invocation_id", ...} once ONE holder fired a
                                   halt at our node's :4243 and a majority confirmed
  4. agent_acted.json    (us)      {"status": 423, "trace_id", "agent_id_hash"}
  5. done.json           (harness) {"verdict", ...} after the canonical holds the
                                   trace, the halt resumed, our node reads clear

The env block is exported verbatim into the agent by `tools/qa_runner/server.py`
(see `prepare_server_env`), into a fresh CIRIS_HOME with every data path pinned
there. Everything else is this module.

WHERE THE REFUSAL ACTION_RESULT COMES FROM. Under a standing halt the agent
refuses intake (interact/message answer 423 before any task exists) and holds
its rounds, so the interact the protocol sends creates no act and no
ACTION_RESULT. A refusal record exists only for a thought that was ALREADY IN
FLIGHT when the halt landed. So the runner keeps the agent working — it submits
a message, and another each time the last one has been answered — until
halt_fired appears; the round in flight when the halt lands reaches the act
gate and is refused, and its terminal ACTION_RESULT carries
`execution_error = accord_halt_in_effect:<invocation_id>` (DETAILED+ trace
level). That trace's id is what agent_acted.json reports. If the halt happens to
land between rounds, no act was in flight and the runner says so instead of
inventing a trace.

PREREQUISITE: a ciris-server wheel built with `--features test-anchor`. The PyPI
wheel compiles the test-bless / test-genesis paths out, so it cannot honour the
handoff's CIRIS_TEST_* env; `test_anchor_compiled()` asks the server's probe.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

HANDOFF_DIR_ENV = "CIRIS_QA_HALT_HANDOFF_DIR"
TEE_DIR_ENV = "CIRIS_QA_HALT_TEE_DIR"

HANDOFF_FILE = "agent_handoff.json"
READY_FILE = "agent_ready.json"
FIRED_FILE = "halt_fired.json"
ACTED_FILE = "agent_acted.json"
DONE_FILE = "done.json"

NODE_HALT_STATUS_URL = "http://127.0.0.1:4243/v1/accord/halt-status"
REFUSAL_PREFIX = "accord_halt_in_effect:"

#: agent_acted.json `outcome` when the halt landed between rounds (no act was in flight).
NO_IN_FLIGHT_ACT = "no_in_flight_act"
REFUSED_IN_FLIGHT_ACT = "refused_in_flight_act"

#: Agent data paths that a host .env could otherwise point at a live install.
PINNED_DATA_PATHS = ("CIRIS_HOME", "CIRIS_DATA_DIR", "CIRIS_CONFIG_DIR", "CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR")


@dataclass(frozen=True)
class AgentHandoff:
    env: Dict[str, str]
    agent_url: Optional[str]
    canonical: Dict[str, Any] = field(default_factory=dict)
    holders: List[Any] = field(default_factory=list)


def load_handoff(directory: Path) -> AgentHandoff:
    """Parse agent_handoff.json. Refuses anything but a string-valued env block."""
    raw = json.loads((directory / HANDOFF_FILE).read_text())
    env = raw.get("env")
    if not isinstance(env, dict) or not env:
        raise ValueError(f"{HANDOFF_FILE} has no env block")
    bad = [k for k, v in env.items() if not isinstance(k, str) or not isinstance(v, str)]
    if bad:
        raise ValueError(f"{HANDOFF_FILE} env values must be strings: {bad}")
    canonical = raw.get("canonical") if isinstance(raw.get("canonical"), dict) else {}
    holders = raw.get("holders") if isinstance(raw.get("holders"), list) else []
    return AgentHandoff(env=dict(env), agent_url=raw.get("agent_url"), canonical=canonical, holders=holders)


def is_fresh(path: Path, since: Optional[float]) -> bool:
    """`path` exists and was written at or after `since` (wall clock); any age when `since` is None."""
    try:
        return path.exists() and (since is None or path.stat().st_mtime >= since)
    except OSError:
        return False


def wait_for_file(
    path: Path, timeout_s: float, poll_s: float = 1.0, since: Optional[float] = None
) -> Optional[Dict[str, Any]]:
    """Block until `path` holds a JSON object written at/after `since`, or time out.

    `since` keeps a directory a previous harness run left behind from being read
    as this run's protocol (the harness writes atomically).
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if is_fresh(path, since):
            try:
                data = json.loads(path.read_text())
                if isinstance(data, dict):
                    return data
            except (OSError, ValueError):
                pass  # mid-write; try again
        time.sleep(poll_s)
    return None


def write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, path)


def prepare_server_env(env: Dict[str, str], handoff_dir: Path, home: Path) -> Dict[str, str]:
    """The agent's env for a handoff run: the handoff block verbatim, every data path in `home`.

    Called by tools/qa_runner/server.py when HANDOFF_DIR_ENV is set. Returns the
    tee dir the module reads the refusal trace from.
    """
    handoff = load_handoff(handoff_dir)
    env.update(handoff.env)
    tee = home / "tee"
    pins = {
        "CIRIS_HOME": str(home),
        "CIRIS_DATA_DIR": str(home / "data"),
        "CIRIS_CONFIG_DIR": str(home / "config"),
        "CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR": str(tee),
        # The refusal's execution_error is a DETAILED field; GENERIC carries only the boolean.
        "CIRIS_ACCORD_METRICS_TRACE_LEVEL": "detailed",
    }
    for key, value in pins.items():
        if key in handoff.env and handoff.env[key] != value:
            raise ValueError(f"{HANDOFF_FILE} env sets {key}; a handoff run owns its own data paths")
        env[key] = value
    for sub in ("data", "config", "tee"):
        (home / sub).mkdir(parents=True, exist_ok=True)
    return env


def test_anchor_compiled() -> bool:
    """Was the importable ciris_server built with `--features test-anchor`?

    The server's probe (CIRISServer#769): `ciris_server.test_anchor_compiled()`
    is true only in a test-anchor build. The PyPI wheel lacks the attribute, and
    a missing probe reads as False.
    """
    try:
        import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]
    except Exception:
        return False
    return bool(getattr(ciris_server, "test_anchor_compiled", lambda: False)())


def find_refusal_trace(tee_dir: Path, invocation_id: str) -> Optional[str]:
    """The trace_id of the sealed trace whose ACTION_RESULT is this halt's refusal, if one sealed."""
    wanted = f"{REFUSAL_PREFIX}{invocation_id}"
    for path in sorted(tee_dir.rglob("lens-batch-*.json")):
        try:
            batch = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        for event in batch.get("events", []) if isinstance(batch, dict) else []:
            trace = event.get("trace") if isinstance(event, dict) else None
            if not isinstance(trace, dict):
                continue
            for component in trace.get("components", []) or []:
                if not isinstance(component, dict) or component.get("event_type") != "ACTION_RESULT":
                    continue
                data = component.get("data")
                if isinstance(data, dict) and data.get("execution_error") == wanted:
                    trace_id = trace.get("trace_id")
                    return str(trace_id) if trace_id else None
    return None


class HandoffRun:
    """Drives the agent side of the protocol against a running agent."""

    #: A live LLM round for a short prompt; the harness peers and fires inside this.
    KEEP_BUSY_PROMPT = "In two sentences, explain what it means for a process to be paused and later resumed."
    KEEP_BUSY_EVERY_S = 10.0

    def __init__(self, base_url: str, token: Optional[str], handoff_dir: Path, tee_dir: Path, console: Any) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.dir = handoff_dir
        self.tee_dir = tee_dir
        self.console = console
        self.results: List[Dict[str, Any]] = []
        self.timeouts = {"fired": 600.0, "halted": 60.0, "trace": 120.0, "done": 900.0}
        #: Harness files older than this run are a previous run's leftovers. The
        #: runner's launch time (set by server.py) when there is one.
        self.started_at = float(os.environ.get("CIRIS_QA_HALT_LAUNCHED_AT") or time.time())

    def _record(self, name: str, ok: bool, detail: Optional[str] = None) -> None:
        self.results.append({"test": name, "status": "✅ PASS" if ok else "❌ FAIL", "error": None if ok else detail})
        self.console.print(f" [{'OK' if ok else 'FAIL'}] {name}{f': {detail}' if detail else ''}")

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def _agent_id_hash(self, http: Any) -> Optional[str]:
        response = await http.get(f"{self.base_url}/v1/system/runtime/delivery-receipt", headers=self._headers())
        if response.status_code != 200:
            return None
        value = (response.json().get("data") or {}).get("agent_id_hash")
        return str(value) if value else None

    async def _node_halted(self, http: Any) -> Optional[bool]:
        try:
            body = (await http.get(NODE_HALT_STATUS_URL)).json()
        except Exception:
            return None
        return body.get("halted") if isinstance(body, dict) else None

    async def _keep_busy_until_fired(self, http: Any) -> Optional[Dict[str, Any]]:
        """Keep a live round in flight until halt_fired.json lands.

        A message every KEEP_BUSY_EVERY_S keeps the processor's queue non-empty,
        so a round is almost always running when the holder's halt arrives.
        Messages admitted after the halt answer 423 and are harmless.
        """
        fired_path = self.dir / FIRED_FILE
        deadline = time.monotonic() + self.timeouts["fired"]
        next_submit = 0.0
        submitted = 0
        while time.monotonic() < deadline:
            if is_fresh(fired_path, self.started_at):
                self.console.print(f"[dim]kept the agent busy with {submitted} message(s)[/dim]")
                return wait_for_file(fired_path, 5.0, 0.2, since=self.started_at)
            if time.monotonic() >= next_submit:
                response = await http.post(
                    f"{self.base_url}/v1/agent/message",
                    headers=self._headers(),
                    json={"message": self.KEEP_BUSY_PROMPT},
                )
                submitted += 1
                next_submit = time.monotonic() + self.KEEP_BUSY_EVERY_S
                if response.status_code == 423:
                    # The halt is already standing; the fired file follows.
                    return wait_for_file(fired_path, 60.0, 0.5, since=self.started_at)
            await asyncio.sleep(0.5)
        return None

    async def run(self, http: Any) -> List[Dict[str, Any]]:
        agent_id_hash = await self._agent_id_hash(http)
        self._record("agent_id_hash resolved", bool(agent_id_hash), "delivery-receipt gave no agent_id_hash")
        if not agent_id_hash:
            return self.results
        self._record("No halt at start", await self._node_halted(http) is False)

        write_json_atomic(self.dir / READY_FILE, {"agent_id_hash": agent_id_hash, "token": self.token})
        fired = await self._keep_busy_until_fired(http)
        invocation_id = str((fired or {}).get("invocation_id") or "")
        self._record("Harness fired the halt", bool(invocation_id), f"no {FIRED_FILE} within the window")
        if not invocation_id:
            return self.results

        async def halted() -> bool:
            return await self._node_halted(http) is True

        deadline = time.monotonic() + self.timeouts["halted"]
        while time.monotonic() < deadline and not await halted():
            await asyncio.sleep(1.0)
        self._record("Node reads halted:true", await halted())

        interact = await http.post(
            f"{self.base_url}/v1/agent/interact", headers=self._headers(), json={"message": "Are you there?"}
        )
        detail = interact.json().get("detail", {}) if interact.status_code == 423 else {}
        refused = (
            interact.status_code == 423 and isinstance(detail, dict) and detail.get("error") == "accord_halt_in_effect"
        )
        self._record("interact answers 423 accord_halt_in_effect", refused, f"HTTP {interact.status_code}")

        trace_id = None
        deadline = time.monotonic() + self.timeouts["trace"]
        while time.monotonic() < deadline and trace_id is None:
            trace_id = find_refusal_trace(self.tee_dir, invocation_id)
            if trace_id is None:
                await asyncio.sleep(2.0)
        # NOT a pass when nothing was in flight: the run then proves nothing about
        # the refusal record. Said explicitly, never papered over.
        self._record(
            "An in-flight act was refused and its ACTION_RESULT sealed",
            trace_id is not None,
            f"{NO_IN_FLIGHT_ACT}: no sealed ACTION_RESULT carries {REFUSAL_PREFIX}{invocation_id}; "
            "the halt landed between rounds, so no act was in flight",
        )

        write_json_atomic(
            self.dir / ACTED_FILE,
            {
                "status": interact.status_code,
                "trace_id": trace_id or "",
                "agent_id_hash": agent_id_hash,
                "outcome": REFUSED_IN_FLIGHT_ACT if trace_id else NO_IN_FLIGHT_ACT,
            },
        )
        done = await asyncio.to_thread(wait_for_file, self.dir / DONE_FILE, self.timeouts["done"], 2.0, self.started_at)
        verdict = str((done or {}).get("verdict", "")).lower()
        self._record("Harness verdict", verdict in ("pass", "passed", "ok", "green", "true"), str(done))
        return self.results


__all__ = [
    "ACTED_FILE",
    "AgentHandoff",
    "DONE_FILE",
    "FIRED_FILE",
    "HANDOFF_DIR_ENV",
    "HandoffRun",
    "NO_IN_FLIGHT_ACT",
    "REFUSED_IN_FLIGHT_ACT",
    "READY_FILE",
    "TEE_DIR_ENV",
    "find_refusal_trace",
    "load_handoff",
    "prepare_server_env",
    "test_anchor_compiled",
    "wait_for_file",
    "write_json_atomic",
]
