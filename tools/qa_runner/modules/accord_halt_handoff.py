"""CSD-129 agent step: the accord_halt QA module meeting CIRISServer's native harness (#769).

The server's `harness/native` scenario `halt` mints a test-anchor mesh and hands
this runner what it needs through files in one directory:

  1. agent_handoff.json  (harness) the env block + canonical + holders
  1a. agent_up.json      (us)      {"node_home"} once our node minted its claim PIN,
                                   BEFORE setup completes (setup mints a ROOT WA,
                                   after which the node mints no PIN)
  1b. agent_claimed.json (harness) {"owner_key_id", "token"} after it claimed our
                                   node with that PIN, as it claims alice and bob
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

THE MODEL is the one Five-Platform Live QA ships traces with:
`--live-model qwen/qwen3.6-35b-a3b --live-base-url https://openrouter.ai/api/v1`
and NO --live-provider, so the provider auto-detects as openrouter. Every
OpenRouter call carries `reasoning.enabled=false`; llama-4-scout's serverless
providers were routed away from on 2026-10-14 ("Filter by Parameters").

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
#: Epoch floor for accepting agent_handoff.json; overrides the leftover scan.
HANDOFF_SINCE_ENV = "CIRIS_QA_HALT_HANDOFF_SINCE"

HANDOFF_FILE = "agent_handoff.json"
UP_FILE = "agent_up.json"
CLAIMED_FILE = "agent_claimed.json"
CLAIM_PIN_FILE = "claim_pin"
READY_FILE = "agent_ready.json"
FIRED_FILE = "halt_fired.json"
ACTED_FILE = "agent_acted.json"
DONE_FILE = "done.json"
#: The harness's own end-of-run summary; any copy present before the handoff is a previous run's.
REPORT_FILE = "report.json"

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


def handoff_floor(handoff_dir: Path) -> Optional[float]:
    """Oldest mtime agent_handoff.json may have and still be this run's.

    The harness may write its handoff before the runner starts, so the floor is
    not our launch time: it is "newer than anything a finished run left behind"
    (its report, or any of the end-of-protocol files). An empty directory means
    the harness cleared it for this run: any handoff counts. HANDOFF_SINCE_ENV
    overrides both.
    """
    explicit = os.environ.get(HANDOFF_SINCE_ENV)
    if explicit:
        return float(explicit)
    leftovers = []
    for name in (REPORT_FILE, DONE_FILE, ACTED_FILE, FIRED_FILE, READY_FILE, CLAIMED_FILE, UP_FILE):
        try:
            leftovers.append((handoff_dir / name).stat().st_mtime)
        except OSError:
            continue
    return max(leftovers) + 1e-3 if leftovers else None


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


def claim_via_harness(
    handoff_dir: Path, node_home: Path, pin_timeout_s: float = 180.0, claim_timeout_s: float = 60.0
) -> Optional[Dict[str, Any]]:
    """Have the harness owner-bind our node; the claimed record, or None.

    An unowned node ships no trace to any canonical, so the halt's refusal
    trace could never arrive. The node writes its one-time PIN to
    `<node_home>/claim_pin` once compose reaches the claim phase; agent_up.json
    names that home only once the file is there, so the harness never reads a
    home with nothing to claim. Must run before /v1/setup/complete: setup mints
    a ROOT WA, and a node that sees a ROOT mints no PIN.
    """
    pin_file = node_home / CLAIM_PIN_FILE
    deadline = time.monotonic() + pin_timeout_s
    while not (pin_file.is_file() and pin_file.stat().st_size > 0):
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.5)
    up_at = time.time()
    write_json_atomic(handoff_dir / UP_FILE, {"node_home": str(node_home)})
    return wait_for_file(handoff_dir / CLAIMED_FILE, claim_timeout_s, 0.5, since=up_at)


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


TEST_ENV_PREFIX = "CIRIS_TEST_"

_PROBE = (
    "import sys\n"
    "try:\n    import ciris_server\nexcept Exception:\n    sys.exit(2)\n"
    "sys.exit(0 if getattr(ciris_server, 'test_anchor_compiled', lambda: False)() else 3)\n"
)


def test_anchor_compiled() -> bool:
    """Was the installed ciris_server built with `--features test-anchor`?

    The server's probe (CIRISServer#769): `ciris_server.test_anchor_compiled()`
    is true only in a test-anchor build. The PyPI wheel lacks the attribute, and
    a missing probe reads as False.

    Asked in a child with every CIRIS_TEST_* key stripped: a test-anchor
    `import ciris_server` installs CIRIS_TEST_GENESIS_BUNDLE (and raises when it
    is missing), which belongs to the agent process alone, in its pinned home.
    """
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if not k.startswith(TEST_ENV_PREFIX)}
    try:
        return subprocess.run([sys.executable, "-c", _PROBE], env=env, timeout=120).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def runner_env_is_clean(handoff_env: Dict[str, str], environ: Optional[Dict[str, str]] = None) -> List[str]:
    """The handoff's CIRIS_TEST_* keys already in the RUNNER's own env; must be empty.

    The runner imports ciris_server itself (through ciris_engine). With the
    handoff's genesis key in its env that import would install the bundle
    outside the agent's home; the handoff env goes to the agent subprocess only.
    """
    env = os.environ if environ is None else environ
    return sorted(k for k in handoff_env if k.startswith(TEST_ENV_PREFIX) and k in env)


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
        #: The full body of the protocol's one interact under the halt.
        self.interact_body = ""
        #: Builds the reasoning-stream client; None shares `http` (tests).
        self.stream_client_factory: Optional[Any] = None
        self.timeouts = {"round": 180.0, "fired": 600.0, "halted": 60.0, "trace": 120.0, "done": 900.0}
        #: halt_fired.json / done.json answer our agent_ready.json, so anything
        #: older than our ready write is a previous run's. Set in run().
        self.started_at = time.time()

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

    #: agent_ready goes out on this event. A step's event is broadcast when the
    #: step ENDS, and the names trail the steps: IDMA_RESULT comes out of
    #: PERFORM_ASPDMA (the action is chosen), ASPDMA_RESULT out of CONSCIENCE
    #: (milliseconds before dispatch; run 4 fired after the act). After
    #: IDMA_RESULT the conscience's LLM calls (seconds) still run before the gate.
    READY_ON_EVENT = "idma_result"

    async def _watch_for_round_start(self, http: Any, started: asyncio.Event) -> None:
        """Set `started` on the first READY_ON_EVENT on the reasoning stream.

        agent_ready.json tells the harness to fire NOW (it fires ~0.1 s later),
        so it must not go out until an act is on its way: written on submit, the
        halt beat the round to the thought (CSD-129 run 3, no_in_flight_act).
        """
        url = f"{self.base_url}/v1/system/runtime/reasoning-stream"
        while not started.is_set():
            try:
                async with http.stream("GET", url, headers=self._headers(), timeout=None) as response:
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        try:
                            events = json.loads(line[5:].strip()).get("events", [])
                        except (ValueError, AttributeError):
                            continue
                        if any(isinstance(e, dict) and e.get("event_type") == self.READY_ON_EVENT for e in events):
                            started.set()
                            return
            except Exception:  # noqa: BLE001 - reconnect; the stream is best-effort until a round shows
                pass
            await asyncio.sleep(0.5)

    async def _submit(self, http: Any) -> int:
        response = await http.post(
            f"{self.base_url}/v1/agent/message", headers=self._headers(), json={"message": self.KEEP_BUSY_PROMPT}
        )
        return int(response.status_code)

    async def _keep_busy_until_fired(self, http: Any) -> Optional[Dict[str, Any]]:
        """Keep a live round in flight until halt_fired.json lands.

        A message every KEEP_BUSY_EVERY_S keeps the processor's queue non-empty,
        so a round is almost always running when the holder's halt arrives.
        Messages admitted after the halt answer 423 and are harmless.
        """
        fired_path = self.dir / FIRED_FILE
        deadline = time.monotonic() + self.timeouts["fired"]
        next_submit = time.monotonic() + self.KEEP_BUSY_EVERY_S  # run() already submitted the first
        submitted = 1
        while time.monotonic() < deadline:
            if is_fresh(fired_path, self.started_at):
                self.console.print(f"[dim]kept the agent busy with {submitted} message(s)[/dim]")
                return wait_for_file(fired_path, 5.0, 0.2, since=self.started_at)
            if time.monotonic() >= next_submit:
                status = await self._submit(http)
                submitted += 1
                next_submit = time.monotonic() + self.KEEP_BUSY_EVERY_S
                if status == 423:
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

        round_started = asyncio.Event()
        # Its own client: a stream cancelled mid-read must not share a pool with
        # the protocol's requests (run 4's interact hung 60 s after the cancel).
        stream_http = self.stream_client_factory() if self.stream_client_factory else http
        watcher = asyncio.create_task(self._watch_for_round_start(stream_http, round_started))
        try:
            await asyncio.sleep(0.2)  # subscribed before the message, so its THOUGHT_START is seen
            await self._submit(http)
            try:
                await asyncio.wait_for(round_started.wait(), self.timeouts["round"])
            except asyncio.TimeoutError:
                pass
        finally:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
            if stream_http is not http:
                await stream_http.aclose()
        self._record("A round is in flight before agent_ready", round_started.is_set(), f"no {self.READY_ON_EVENT} on the stream")
        if not round_started.is_set():
            return self.results

        self.started_at = time.time()
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

        status = 0
        try:
            interact = await http.post(
                f"{self.base_url}/v1/agent/interact",
                headers=self._headers(),
                json={"message": "Are you there?"},
                timeout=30.0,  # a 423 is immediate; a hang is a finding, named below
            )
            status = interact.status_code
            self.interact_body = interact.text
            detail = interact.json().get("detail", {}) if status == 423 else {}
        except Exception as exc:  # noqa: BLE001 - recorded; agent_acted still goes out
            self.interact_body = repr(exc)
            detail = {}
        self.console.print(f"[dim]interact under the halt: HTTP {status} {self.interact_body}[/dim]")
        refused = status == 423 and isinstance(detail, dict) and detail.get("error") == "accord_halt_in_effect"
        self._record("interact answers 423 accord_halt_in_effect", refused, f"HTTP {status}: {self.interact_body}")

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
                "status": status,
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
    "CLAIMED_FILE",
    "CLAIM_PIN_FILE",
    "DONE_FILE",
    "FIRED_FILE",
    "HANDOFF_DIR_ENV",
    "HANDOFF_SINCE_ENV",
    "HandoffRun",
    "NO_IN_FLIGHT_ACT",
    "REFUSED_IN_FLIGHT_ACT",
    "READY_FILE",
    "TEE_DIR_ENV",
    "UP_FILE",
    "claim_via_harness",
    "find_refusal_trace",
    "handoff_floor",
    "load_handoff",
    "prepare_server_env",
    "runner_env_is_clean",
    "test_anchor_compiled",
    "wait_for_file",
    "write_json_atomic",
]
