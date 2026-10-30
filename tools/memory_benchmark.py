#!/usr/bin/env python3
"""Memory benchmark for CIRIS agent under message load.

Measures RSS memory growth while submitting N async messages to the API.
Designed for fast, reliable mock LLM profiling up to 1k+ messages.
"""

import argparse
import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import random
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional


def format_size(size: float) -> str:
    """Format bytes as human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(size) < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def get_process_memory(pid: int) -> int:
    """Get RSS memory for a process in bytes."""
    try:
        import psutil

        process = psutil.Process(pid)
        return process.memory_info().rss
    except ImportError:
        try:
            with open(f"/proc/{pid}/statm") as f:
                pages = int(f.read().split()[1])
                return pages * os.sysconf("SC_PAGE_SIZE")
        except Exception:
            return 0
    except Exception:
        return 0


def get_children_memory(pid: int) -> int:
    """Get total RSS memory for a process and all its children."""
    try:
        import psutil

        parent = psutil.Process(pid)
        total = parent.memory_info().rss
        for child in parent.children(recursive=True):
            try:
                total += child.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return total
    except ImportError:
        return get_process_memory(pid)
    except Exception:
        return 0


async def wait_for_server(base_url: str, timeout_seconds: int = 90) -> bool:
    """Wait for API server to become healthy."""
    import httpx

    deadline = time.time() + timeout_seconds
    async with httpx.AsyncClient(timeout=3.0) as client:
        while time.time() < deadline:
            try:
                response = await client.get(f"{base_url}/v1/system/health")
                if response.status_code == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(1.0)
    return False


async def wait_for_runtime_ready(base_url: str, token: str, timeout_seconds: int = 120) -> bool:
    """Wait for agent runtime endpoints to accept authenticated traffic."""
    import httpx

    deadline = time.time() + timeout_seconds
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=5.0) as client:
        while time.time() < deadline:
            try:
                response = await client.get(f"{base_url}/v1/agent/status", headers=headers)
                if response.status_code == 200:
                    try:
                        data = response.json()
                    except Exception:
                        data = {}
                    cognitive_state = data.get("data", {}).get("cognitive_state")
                    if cognitive_state:
                        print(f"  Runtime state poll: {cognitive_state}")
                    return True
            except Exception:
                pass
            await asyncio.sleep(1.0)
    return False


async def get_auth_token(base_url: str, retries: int = 30) -> str:
    """Get auth token from API with retries."""
    import httpx

    last_status = 0
    async with httpx.AsyncClient(timeout=10.0) as client:
        for attempt in range(retries):
            try:
                for username in ["admin", "owner"]:
                    response = await client.post(
                        f"{base_url}/v1/auth/login",
                        json={"username": username, "password": "qa_test_password_12345"},
                    )
                    last_status = response.status_code
                    if response.status_code == 200:
                        return response.json().get("access_token", "")
            except Exception:
                pass
            await asyncio.sleep(0.5)
    if last_status:
        print(f"  Login failed after {retries} attempts (last status: {last_status})")
    return ""


async def complete_setup(base_url: str, port: int, homes: Optional[List[Optional[str]]] = None, since: Optional[float] = None) -> bool:
    """Complete first-run setup for benchmark environments."""
    import httpx

    payload: Dict[str, Any] = {
        "llm_provider": "openai",
        "llm_api_key": "test-key-for-benchmark",
        "llm_model": "gpt-4",
        "template_id": "default",
        "enabled_adapters": ["api"],
        "adapter_config": {},
        "admin_username": "owner",
        "admin_password": "qa_test_password_12345",
        "agent_port": port,
    }

    # Every node is always claimed: claim with the node's PIN first, as the
    # wizard does (tools/qa_runner/node_claim.py), or setup is not attempted.
    project_root = Path(__file__).parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))  # run as a script: tools/ is on the path, the repo is not
    from tools.qa_runner.node_claim import claim_like_the_wizard

    homes = homes or [os.environ.get("CIRIS_HOME"), str(project_root), os.path.expanduser("~/ciris")]
    async with httpx.AsyncClient(timeout=60.0) as client:
        claim = await claim_like_the_wizard(
            client, base_url, homes, str(payload["admin_username"]), str(payload["admin_password"]), since=since
        )
    if not claim.ok:
        print(f"  Node claim ({claim.step}) failed, setup not attempted: {claim.detail}")
        return False

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{base_url}/v1/setup/complete", json=payload)
        print(f"  Setup response status: {response.status_code}")
        print(f"  Setup response body: {response.text[:300]}")
        return response.status_code == 200
    except Exception as exc:
        print(f"  Setup request failed: {exc}")
        return False


#: Back-pressure defaults. The workflow's 20-minute job budget has to hold two
#: agent boots, a 100-message and a 1000-message run, an idle window and the
#: composition probe, so the workflow passes tighter overall deadlines; these
#: defaults are for a local run.
DEFAULT_PER_MESSAGE_DEADLINE_S = 180.0  # six 30 s SHED windows for one message
DEFAULT_OVERALL_DEADLINE_S = 900.0
#: 423 (node unclaimed / constitutional halt) is retried this long after the
#: burst starts — the claim or halt latch can lag the boot — then it is fatal.
DEFAULT_LOCKED_GRACE_S = 30.0
DEFAULT_MIN_SUCCESS_RATE = 0.99
#: Wait used for a 503/429 that names no Retry-After anywhere.
DEFAULT_RETRY_AFTER_S = 2.0
#: Wait between 423 retries inside the startup grace window.
LOCKED_RETRY_S = 2.0
#: Attempts for any other failure (5xx without Retry-After semantics, 4xx,
#: transport exceptions, 200 without a task id).
OTHER_FAILURE_ATTEMPTS = 3

BACKPRESSURE_STATUSES = (429, 503)


@dataclass
class SendResult:
    """What one burst did: outcomes per message plus why the agent pushed back."""

    success: int = 0
    failed: int = 0
    elapsed: float = 0.0
    task_ids: List[str] = field(default_factory=list)
    #: Final reason for each message that was NOT accepted → count.
    failure_reasons: Counter[str] = field(default_factory=Counter)
    #: Every non-accepted response or exception seen, retried or not → count.
    response_reasons: Counter[str] = field(default_factory=Counter)
    #: 503 resource_shed refusals seen (each attempt counts once).
    shed_refusals: int = 0
    #: Resource names the agent cited in its SHED refusals → count.
    shed_resources: Counter[str] = field(default_factory=Counter)
    #: Seconds spent sleeping on Retry-After (header, body or default), summed over workers.
    retry_after_wait_total: float = 0.0
    retries: int = 0
    #: Set when a non-retryable condition (423 past the grace window) stopped the burst.
    aborted: Optional[str] = None


def _detail(body: Any) -> Dict[str, Any]:
    """The refusal detail: FastAPI nests HTTPException dicts under "detail"; middleware does not."""
    if not isinstance(body, dict):
        return {}
    nested = body.get("detail")
    return nested if isinstance(nested, dict) else body


def _response_body(response: Any) -> Any:
    try:
        return response.json()
    except Exception:
        return None


def parse_retry_after(response: Any, body: Any, now_epoch: Optional[float] = None) -> Optional[float]:
    """Seconds the agent asked us to wait: Retry-After header, else the body, else None.

    The header may be delta-seconds or an HTTP-date (RFC 9110 §10.2.3). In the
    body, SHED refusals say ``retry_after_seconds`` and the rate limiter says
    ``retry_after``.
    """
    header = response.headers.get("Retry-After")
    if header:
        header = header.strip()
        try:
            return max(0.0, float(header))
        except ValueError:
            try:
                when = parsedate_to_datetime(header)
                now = now_epoch if now_epoch is not None else time.time()
                return max(0.0, float(when.timestamp()) - now)
            except (TypeError, ValueError, IndexError):
                pass
    for source in (_detail(body), body if isinstance(body, dict) else {}):
        for key in ("retry_after_seconds", "retry_after"):
            value = source.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return max(0.0, float(value))
    return None


def _refusal_reason(status: int, body: Any) -> str:
    detail = _detail(body)
    error = detail.get("error")
    reason = f"http_{status}_{error}" if isinstance(error, str) and error else f"http_{status}"
    # A 423 can be a real halt or claim, or a fail-closed READ of either: the
    # halt latch and the ownership read both refuse when the local node does not
    # answer in time. The reading says which, so a timeout under load is not
    # reported as a halt.
    halt = detail.get("halt")
    reading = halt.get("reading") if isinstance(halt, dict) else None
    if not reading and status == 423 and isinstance(detail.get("message"), str):
        message = detail["message"]
        if "no owner (" in message:
            reading = message.split("no owner (", 1)[1].split(":", 1)[0].split(")", 1)[0]
    return f"{reason}[{reading}]" if isinstance(reading, str) and reading else reason


async def send_messages(
    base_url: str,
    messages: int,
    token: str,
    concurrency: int,
    process_tasks: bool,
    *,
    per_message_deadline: float = DEFAULT_PER_MESSAGE_DEADLINE_S,
    overall_deadline: float = DEFAULT_OVERALL_DEADLINE_S,
    locked_grace: float = DEFAULT_LOCKED_GRACE_S,
    transport: Optional[Any] = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    clock: Callable[[], float] = time.monotonic,
    rng: Callable[[], float] = random.random,
) -> SendResult:
    """Submit messages concurrently, yielding to the agent's back-pressure.

    503 (SHED) and 429 (rate limit) are the agent saying "not now": the worker
    waits out Retry-After plus jitter and resubmits the SAME message until it
    is accepted or its per-message deadline, or the overall deadline, passes.
    423 (node unclaimed / halt) is retried for ``locked_grace`` seconds after
    the burst starts, then stops the burst. Anything else gets a small bounded
    retry. ``transport``/``sleep``/``clock``/``rng`` exist so tests can drive
    this without a server or real time.
    """
    import httpx

    queue: asyncio.Queue[int] = asyncio.Queue()
    for i in range(messages):
        queue.put_nowait(i)

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    result = SendResult()
    counter_lock = asyncio.Lock()
    start = clock()
    overall_end = start + overall_deadline
    endpoint = "/v1/agent/interact" if process_tasks else "/v1/agent/message"

    limits = httpx.Limits(max_keepalive_connections=max(20, concurrency * 2), max_connections=max(40, concurrency * 4))
    # Read budget: process_tasks=True waits for a full DMA pipeline + SPEAK
    # (~minutes under live LLM load); process_tasks=False is the fast queue
    # path (just task acceptance), but 10s was too tight on GitHub Actions
    # runners under 20-way concurrent burst — auth/rate-limit middleware +
    # SQLite write contention on the audit + tasks tables added enough
    # tail-latency to push 21% of /v1/agent/message calls past 10s, all
    # surfacing as `exc_ReadTimeout`. 30s gives breathing room for the
    # acceptance path while still catching genuine hangs.
    client_timeout = (
        httpx.Timeout(connect=5.0, read=60.0, write=30.0, pool=10.0)
        if process_tasks
        else httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=10.0)
    )

    async def wait(seconds: float, honour: bool) -> None:
        if seconds <= 0:
            return
        await sleep(seconds)
        async with counter_lock:
            result.retries += 1
            if honour:
                result.retry_after_wait_total += seconds

    async def submit_one(client: Any, idx: int, worker_id: int) -> tuple[bool, str]:
        payload = {
            "message": f"Memory benchmark message {idx + 1} of {messages}",
            "context": {"channel_id": f"memory_benchmark_w{worker_id}_m{idx}"},
        }
        message_end = min(clock() + per_message_deadline, overall_end)
        other_failures = 0
        reason = "no_attempts"
        while True:
            if result.aborted:
                return False, f"aborted:{result.aborted}"
            honour = False
            try:
                response = await client.post(f"{base_url}{endpoint}", json=payload, headers=headers)
            except Exception as e:
                reason = f"exc_{type(e).__name__}"
                response = None

            if response is not None and response.status_code == 200:
                response_json = _response_body(response)
                if process_tasks:
                    return True, "ok"
                data = response_json if isinstance(response_json, dict) else {}
                inner = data.get("data")
                task_id = data.get("task_id") or (inner.get("task_id") if isinstance(inner, dict) else None)
                if isinstance(task_id, str) and task_id:
                    async with counter_lock:
                        result.task_ids.append(task_id)
                    return True, "ok"
                reason = "200_no_task_id"

            delay: float
            if response is not None and response.status_code in BACKPRESSURE_STATUSES:
                body = _response_body(response)
                reason = _refusal_reason(response.status_code, body)
                detail = _detail(body)
                if response.status_code == 503 and detail.get("error") == "resource_shed":
                    shed = detail.get("resources")
                    async with counter_lock:
                        result.shed_refusals += 1
                        for name in shed if isinstance(shed, list) else []:
                            result.shed_resources[str(name)] += 1
                retry_after = parse_retry_after(response, body)
                base = DEFAULT_RETRY_AFTER_S if retry_after is None else retry_after
                # Jitter keeps 20 workers that were refused together from all
                # coming back in the same instant.
                delay = base + rng() * max(0.5, 0.2 * base)
                honour = True
            elif response is not None and response.status_code == 423:
                reason = _refusal_reason(423, _response_body(response))
                if clock() - start > locked_grace:
                    async with counter_lock:
                        result.response_reasons[reason] += 1
                        if not result.aborted:
                            result.aborted = reason
                    return False, reason
                delay = LOCKED_RETRY_S
            else:
                if response is not None and reason != "200_no_task_id":
                    reason = _refusal_reason(response.status_code, _response_body(response))
                other_failures += 1
                if other_failures >= OTHER_FAILURE_ATTEMPTS:
                    async with counter_lock:
                        result.response_reasons[reason] += 1
                    return False, reason
                delay = 0.15 * other_failures

            async with counter_lock:
                result.response_reasons[reason] += 1
            # Honouring Retry-After means not coming back early: a wait that
            # would end past the deadline is a give-up, not a shortened wait.
            if clock() + delay > message_end:
                which = "overall" if message_end >= overall_end else "message"
                return False, f"deadline_{which}:{reason}"
            await wait(delay, honour)

    async def worker(worker_id: int) -> None:
        async with httpx.AsyncClient(timeout=client_timeout, limits=limits, transport=transport) as client:
            while True:
                try:
                    idx = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                if result.aborted:
                    accepted, reason = False, f"aborted:{result.aborted}"
                elif clock() >= overall_end:
                    accepted, reason = False, "deadline_overall:not_started"
                else:
                    accepted, reason = await submit_one(client, idx, worker_id)

                async with counter_lock:
                    if accepted:
                        result.success += 1
                    else:
                        result.failed += 1
                        result.failure_reasons[reason] += 1
                    done = result.success + result.failed

                if done % 100 == 0:
                    print(f"  Submitted {done}/{messages} messages ({result.success} accepted)...")

                queue.task_done()

    workers = [asyncio.create_task(worker(i)) for i in range(max(1, concurrency))]
    await asyncio.gather(*workers)
    result.elapsed = clock() - start
    return result


def _extract_task_ids_from_payload(payload_text: str) -> set[str]:
    """Extract all task_id values from a serialized payload."""
    found: set[str] = set()
    try:
        payload = json.loads(payload_text)
    except Exception:
        return found

    def walk(value: object) -> None:
        if isinstance(value, dict):
            maybe_task_id = value.get("task_id")
            if isinstance(maybe_task_id, str):
                found.add(maybe_task_id)
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(payload)
    return found


def verify_task_processing(
    task_ids: list[str],
    expected_count: int,
    start_time_iso: str,
    timeout_seconds: int = 180,
) -> tuple[bool, int, int]:
    """Verify submitted tasks reached SPEAK and TASK_COMPLETE in local audit DB."""
    submitted = set(task_ids)

    deadline = time.time() + timeout_seconds
    speak_count = 0
    task_complete_count = 0
    while time.time() < deadline:
        speak_ids: set[str] = set()
        complete_ids: set[str] = set()
        try:
            conn = sqlite3.connect("data/ciris_audit.db")
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT event_type, event_payload
                FROM audit_log
                WHERE event_timestamp >= ?
                AND event_type IN ('speak', 'task_complete')
                """,
                (start_time_iso,),
            )
            rows = cursor.fetchall()
            conn.close()

            speak_count = 0
            task_complete_count = 0
            for event_type, event_payload in rows:
                if event_type == "speak":
                    speak_count += 1
                elif event_type == "task_complete":
                    task_complete_count += 1

                if isinstance(event_payload, str):
                    ids = _extract_task_ids_from_payload(event_payload)
                    if event_type == "speak":
                        speak_ids.update(ids)
                    elif event_type == "task_complete":
                        complete_ids.update(ids)

            if submitted and submitted.issubset(speak_ids) and submitted.issubset(complete_ids):
                return True, task_complete_count, speak_count

            required = expected_count if expected_count > 0 else len(submitted)
            if speak_count >= required and task_complete_count >= required:
                return True, task_complete_count, speak_count
        except Exception:
            pass

        time.sleep(2.0)

    return False, task_complete_count, speak_count


def dump_composition(pid: int, json_path: Optional[str] = None) -> None:
    """Print what the resident set is actually made of.

    Imported lazily so the benchmark keeps working if the tool is absent, and
    never fatal: a failed introspection must not fail a memory run.
    """
    print("\n[composition] attributing resident memory...")
    try:
        # This file is usually run as a script, so `tools` is not importable as
        # a package -- load the sibling module by path instead of by name.
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "memory_composition", Path(__file__).parent / "memory_composition.py"
        )
        if spec is None or spec.loader is None:
            raise ImportError("cannot locate tools/memory_composition.py")
        memory_composition = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(memory_composition)

        report = memory_composition.collect(pid, probe=True, trim=True)
        print(memory_composition.render(report))
        if json_path:
            with open(json_path, "w", encoding="utf-8") as handle:
                json.dump(report, handle, indent=2, sort_keys=True)
            print(f"  wrote {json_path}")
    except Exception as exc:
        print(f"  composition failed: {exc}")


def report_results(
    *,
    messages: int,
    adapter: str,
    concurrency: int,
    initial_mem: int,
    final_mem: int,
    peak_mem: int,
    send: SendResult,
    processed: int,
    min_success_rate: float = DEFAULT_MIN_SUCCESS_RATE,
) -> int:
    """Print the results banner; return the exit code (non-zero below ``min_success_rate``).

    ``processed`` is what the run actually got the agent to do: accepted
    submissions, or with --verify-audit the ones the audit trail shows done.
    Growth is reported per processed message, because growth divided by
    messages *submitted* reads as a tiny per-message cost exactly when the
    agent refused most of them.
    """
    print("\n" + "=" * 70)
    print("MEMORY BENCHMARK RESULTS")
    print("=" * 70)
    growth = final_mem - initial_mem

    print(f"  Messages:       {messages}")
    print(f"  Processed:      {processed}")
    print(f"  Initial:        {format_size(initial_mem)}")
    print(f"  Final:          {format_size(final_mem)}")
    print(f"  Peak:           {format_size(peak_mem)}")
    print(f"  Growth:         {format_size(growth)}")
    if growth > 0:
        if processed > 0:
            print(f"  Per Processed:  {format_size(growth / processed)}  (growth / {processed} processed)")
        else:
            print("  Per Processed:  n/a (nothing processed)")
        if messages > 0:
            print(f"  Per Submitted:  {format_size(growth / messages)}  (growth / {messages} submitted)")

    rate = processed / messages if messages > 0 else 0.0
    print(f"\n  Adapter:        {adapter}")
    print("  Mock LLM:       True")
    print(f"  Concurrency:    {concurrency}")
    print(f"  Success Rate:   {processed}/{messages} ({100 * rate:.1f}%, gate >= {100 * min_success_rate:.1f}%)")
    print(f"  Failures:       {messages - processed}")
    shed_names = ", ".join(f"{name}×{count}" for name, count in send.shed_resources.most_common())
    print(f"  Shed refusals:  {send.shed_refusals}" + (f" ({shed_names})" if shed_names else ""))
    print(f"  Retry-After waits (total s): {send.retry_after_wait_total:.1f}")
    print(f"  Retries:        {send.retries}")
    if send.aborted:
        print(f"  Aborted:        {send.aborted}")
    passed = messages > 0 and rate >= min_success_rate
    print(f"  Result:         {'PASS' if passed else 'FAIL'}")
    print("=" * 70)
    return 0 if passed else 1


def main(
    messages: int = 100,
    adapter: str = "api",
    port: int = 8080,
    concurrency: int = 20,
    verify_audit: bool = False,
    idle_seconds: int = 0,
    composition: bool = False,
    composition_json: Optional[str] = None,
    per_message_deadline: float = DEFAULT_PER_MESSAGE_DEADLINE_S,
    overall_deadline: float = DEFAULT_OVERALL_DEADLINE_S,
    locked_grace: float = DEFAULT_LOCKED_GRACE_S,
    min_success_rate: float = DEFAULT_MIN_SUCCESS_RATE,
    pid_file: Optional[str] = None,
) -> int:
    """Run memory benchmark with N messages."""
    print("=" * 70)
    print(f"CIRIS MEMORY BENCHMARK - {messages} MESSAGES")
    print("=" * 70)

    project_root = Path(__file__).parent.parent
    main_py = project_root / "main.py"
    base_url = f"http://localhost:{port}"

    print("\n[1/4] Starting CIRIS API server...")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    # Benchmarks measure per-task throughput, so bypass the channel-level task-append
    # coalescing in BaseObserver. See ciris_engine/logic/adapters/base_observer.py.
    env.setdefault("CIRIS_DISABLE_TASK_APPEND", "1")

    if composition:
        # Arming is purely a launch-time concern: putting tools/memprobe on
        # PYTHONPATH makes `site` import its sitecustomize, which registers a
        # SIGUSR1 handler.  No engine code is involved and nothing changes when
        # the flag is off.
        probe_dir = project_root / "tools" / "memprobe"
        env["CIRIS_MEMPROBE"] = "1"
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(probe_dir), env.get("PYTHONPATH", "")]))

    cmd = [
        sys.executable,
        str(main_py),
        "--adapter",
        adapter,
        "--mock-llm",
        "--port",
        str(port),
    ]

    launched_at = time.time()
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(project_root),
        env=env,
    )
    pid = process.pid
    print(f"  PID: {pid}")
    if pid_file:
        # Lets a profiler outside this script (the workflow's opt-in py-spy
        # recorder) attach to the agent without guessing which python it is.
        Path(pid_file).write_text(f"{pid}\n")

    def shutdown_process() -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    print("\n[2/4] Waiting for server...")
    if not asyncio.run(wait_for_server(base_url)):
        print("  ERROR: Server failed to start")
        shutdown_process()
        return 1
    print("  Server ready!")

    initial_mem = get_children_memory(pid)
    print(f"\n  Initial memory: {format_size(initial_mem)}")

    print("\n[3/4] Authenticating...")
    token = asyncio.run(get_auth_token(base_url))
    if not token:
        print("  No auth token yet, attempting first-run setup...")
        setup_ok = asyncio.run(complete_setup(base_url, port, since=launched_at))
        if setup_ok:
            print("  Setup completed; retrying authentication...")
            token = asyncio.run(get_auth_token(base_url))
    if not token:
        print("  ERROR: Could not get auth token with QA credentials")
        shutdown_process()
        return 1
    runtime_ready = asyncio.run(wait_for_runtime_ready(base_url, token))
    if not runtime_ready:
        print("  ERROR: Agent runtime did not become ready for authenticated traffic")
        shutdown_process()
        return 1

    benchmark_start_time = datetime.now(timezone.utc).isoformat()
    print(f"\n[4/4] Sending {messages} messages (concurrency={concurrency})...")
    samples = []
    send = SendResult()
    processed = 0
    try:
        send = asyncio.run(
            send_messages(
                base_url,
                messages,
                token,
                concurrency,
                process_tasks=verify_audit,
                per_message_deadline=per_message_deadline,
                overall_deadline=overall_deadline,
                locked_grace=locked_grace,
            )
        )
        success = send.success
        processed = success
        print(f"  Submitted {success}/{messages} messages in {send.elapsed:.1f}s")
        if send.failure_reasons:
            print(f"  Failure breakdown ({send.failed} total):")
            for reason, count in send.failure_reasons.most_common():
                print(f"    {count:>4}× {reason}")
        if send.response_reasons:
            print("  Refusals/errors seen (every attempt, incl. retried):")
            for reason, count in send.response_reasons.most_common():
                print(f"    {count:>4}× {reason}")

        if verify_audit and success > 0:
            verified, task_complete_count, speak_count = verify_task_processing(
                send.task_ids, success, benchmark_start_time
            )
            if verified:
                print(
                    f"  Audit verification: TASK_COMPLETE={task_complete_count}, SPEAK={speak_count} "
                    f"(expected >= {success})"
                )
            else:
                print(
                    "  ERROR: Not all submitted tasks reached SPEAK/TASK_COMPLETE in audit trail "
                    f"(TASK_COMPLETE={task_complete_count}, SPEAK={speak_count}, expected={success})"
                )
                processed = min(success, task_complete_count, speak_count)

        for _ in range(5):
            mem = get_children_memory(pid)
            if mem > 0:
                samples.append(mem)
            time.sleep(0.5)

        # Optional idle window: hold the server alive after the burst and
        # sample memory periodically so we can observe whether async task
        # processing eventually drains and memory plateaus. Without this,
        # the headline "Final" memory in CI is taken 2.5s after submission
        # — well before the queued thoughts have actually finished
        # processing — and underrepresents steady-state RSS.
        if idle_seconds > 0:
            print(f"\n  Idle settling window: {idle_seconds}s, sampling every 2s...")
            idle_samples: list[tuple[float, float]] = []
            t0 = time.time()
            while time.time() - t0 < idle_seconds:
                t = time.time() - t0
                mem = get_children_memory(pid)
                if mem > 0:
                    samples.append(mem)
                    idle_samples.append((t, mem / 1024 / 1024))
                time.sleep(2.0)
            if idle_samples:
                first = idle_samples[0][1]
                last = idle_samples[-1][1]
                peak = max(s[1] for s in idle_samples)
                # Plateau = last 10% of samples agree within 1 MB
                tail = idle_samples[-max(1, len(idle_samples) // 10) :]
                stable = (max(s[1] for s in tail) - min(s[1] for s in tail)) < 1.0
                print(
                    f"  Idle: first={first:.1f}MB peak={peak:.1f}MB final={last:.1f}MB "
                    f"delta={last - first:+.1f}MB plateau={'yes' if stable else 'no'}"
                )

        # Composition is taken last, at the plateau, because that is the number
        # the resource budget is judged against.
        if composition:
            dump_composition(pid, composition_json)

    except Exception as e:
        print(f"  ERROR: {e}")
    finally:
        print("\nShutting down server...")
        shutdown_process()

    final_mem = samples[-1] if samples else 0
    peak_mem = max(samples) if samples else 0
    return report_results(
        messages=messages,
        adapter=adapter,
        concurrency=concurrency,
        initial_mem=initial_mem,
        final_mem=final_mem,
        peak_mem=peak_mem,
        send=send,
        processed=processed,
        min_success_rate=min_success_rate,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CIRIS memory benchmark")
    parser.add_argument(
        "--messages",
        type=int,
        default=100,
        help="Number of messages to send (default: 100)",
    )
    parser.add_argument(
        "--adapter",
        default="api",
        help="Adapter to use (default: api)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for API server (default: 8080)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=20,
        help="Number of concurrent submit workers (default: 20)",
    )
    parser.add_argument("--verify-audit", action="store_true", help="Verify SPEAK/TASK_COMPLETE entries in audit log")
    parser.add_argument(
        "--idle-seconds",
        type=int,
        default=0,
        help=(
            "After submitting all messages, hold the server alive for N seconds "
            "and sample memory every 2s. Reveals whether async task processing "
            "drains and RAM plateaus. Default 0 (matches old behavior)."
        ),
    )
    parser.add_argument(
        "--composition",
        action="store_true",
        help=(
            "At the end of the run, attribute resident memory to allocators and "
            "mappings (see tools/memory_composition.py). Arms the in-process probe."
        ),
    )
    parser.add_argument(
        "--composition-json",
        default=None,
        help="Write the composition report here as JSON",
    )
    parser.add_argument(
        "--per-message-deadline",
        type=float,
        default=DEFAULT_PER_MESSAGE_DEADLINE_S,
        help=(
            "Seconds one message may keep being resubmitted under 503/429 back-pressure "
            f"before it counts as failed (default: {DEFAULT_PER_MESSAGE_DEADLINE_S:g})"
        ),
    )
    parser.add_argument(
        "--overall-deadline",
        type=float,
        default=DEFAULT_OVERALL_DEADLINE_S,
        help=(
            "Seconds the whole submission burst may take; messages not accepted by then "
            f"count as failed (default: {DEFAULT_OVERALL_DEADLINE_S:g})"
        ),
    )
    parser.add_argument(
        "--locked-grace",
        type=float,
        default=DEFAULT_LOCKED_GRACE_S,
        help=(
            "Seconds after the burst starts during which 423 (node unclaimed / halt) is "
            f"retried; after that it stops the run (default: {DEFAULT_LOCKED_GRACE_S:g})"
        ),
    )
    parser.add_argument(
        "--min-success-rate",
        type=float,
        default=DEFAULT_MIN_SUCCESS_RATE,
        help=(
            "Exit non-zero when processed/messages is below this fraction "
            f"(default: {DEFAULT_MIN_SUCCESS_RATE:g})"
        ),
    )
    parser.add_argument(
        "--pid-file",
        default=None,
        help="Write the agent's PID here once it is launched (for an external profiler)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(
        main(
            messages=args.messages,
            adapter=args.adapter,
            port=args.port,
            concurrency=max(1, args.concurrency),
            verify_audit=args.verify_audit,
            idle_seconds=max(0, args.idle_seconds),
            composition=args.composition,
            composition_json=args.composition_json,
            per_message_deadline=max(0.0, args.per_message_deadline),
            overall_deadline=max(0.0, args.overall_deadline),
            locked_grace=max(0.0, args.locked_grace),
            min_success_rate=min(1.0, max(0.0, args.min_success_rate)),
            pid_file=args.pid_file,
        )
    )
