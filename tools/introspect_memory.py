#!/usr/bin/env python3
"""Introspect Python memory usage of running CIRIS agent.

Usage:
    python3 tools/introspect_memory.py --adapters api --duration 30
    python3 tools/introspect_memory.py --adapters api --messages 1000 --concurrency 8
"""

import argparse
import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path


def format_size(size: float) -> str:
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


async def _wait_for_server(base_url: str, timeout_seconds: int = 90) -> bool:
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


async def _get_auth_token(base_url: str, retries: int = 30) -> str:
    import httpx

    async with httpx.AsyncClient(timeout=10.0) as client:
        for _ in range(retries):
            try:
                for username in ["admin", "owner"]:
                    response = await client.post(
                        f"{base_url}/v1/auth/login",
                        json={"username": username, "password": "qa_test_password_12345"},
                    )
                    if response.status_code == 200:
                        return response.json().get("access_token", "")
            except Exception:
                pass
            await asyncio.sleep(0.5)
    return ""


async def _complete_setup(base_url: str, port: int) -> bool:
    """Complete first-run setup for local benchmark environments."""
    import httpx

    payload = {
        "llm_provider": "openai",
        "llm_api_key": "test-key-for-introspection",
        "llm_model": "gpt-4",
        "template_id": "default",
        "enabled_adapters": ["api"],
        "adapter_config": {},
        "admin_username": "owner",
        "admin_password": "qa_test_password_12345",
        "agent_port": port,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{base_url}/v1/setup/complete", json=payload)
        return response.status_code == 200
    except Exception:
        return False


async def _wait_for_runtime_ready(base_url: str, token: str, timeout_seconds: int = 120) -> bool:
    import httpx

    deadline = time.time() + timeout_seconds
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=5.0) as client:
        while time.time() < deadline:
            try:
                response = await client.get(f"{base_url}/v1/agent/status", headers=headers)
                if response.status_code == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(1.0)
    return False


async def _run_message_load(base_url: str, token: str, messages: int, concurrency: int) -> tuple[int, int, float]:
    import httpx

    queue: asyncio.Queue[int] = asyncio.Queue()
    for i in range(messages):
        queue.put_nowait(i)

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    success = 0
    failed = 0
    lock = asyncio.Lock()
    start = time.time()
    client_timeout = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=10.0)

    async def worker(worker_id: int) -> None:
        nonlocal success, failed
        async with httpx.AsyncClient(timeout=client_timeout) as client:
            while True:
                try:
                    idx = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return

                payload = {
                    "message": f"Introspection benchmark message {idx + 1}/{messages}",
                    "context": {"channel_id": f"introspection_w{worker_id}_m{idx}"},
                }
                try:
                    accepted = False
                    for attempt in range(3):
                        response = await client.post(f"{base_url}/v1/agent/message", headers=headers, json=payload)
                        if response.status_code == 200:
                            response_json = response.json()
                            accepted = bool(
                                response_json.get("task_id")
                                or response_json.get("data", {}).get("task_id")
                            )
                            if accepted:
                                break
                        await asyncio.sleep(0.15 * (attempt + 1))

                    async with lock:
                        if accepted:
                            success += 1
                        else:
                            failed += 1
                except Exception:
                    async with lock:
                        failed += 1

                queue.task_done()

    workers = [asyncio.create_task(worker(i)) for i in range(max(1, concurrency))]
    await asyncio.gather(*workers)
    return success, failed, time.time() - start


def main(adapters: str = "cli", duration: int = 30, messages: int = 0, concurrency: int = 8, port: int = 8080) -> int:
    print("=" * 70)
    print("CIRIS 2.0 MEMORY INTROSPECTION")
    print("=" * 70)
    print(f"Adapters: {adapters}")
    print(f"Duration: {duration}s")
    if messages > 0:
        print(f"Message load: {messages} (concurrency={concurrency})")

    project_root = Path(__file__).parent.parent
    main_py = project_root / "main.py"

    if not main_py.exists():
        print(f"ERROR: main.py not found at {main_py}")
        return 1

    cmd = [sys.executable, str(main_py), "--adapter", adapters, "--mock-llm"]
    if adapters == "api":
        cmd.extend(["--port", str(port)])
    else:
        cmd.extend(["--timeout", str(duration)])

    print(f"\nCommand: {' '.join(cmd)}")
    print("\n[1/3] Starting CIRIS agent...")

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(project_root),
        env=env,
        text=True,
    )

    pid = process.pid
    print(f"PID: {pid}")

    def shutdown_process() -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    samples = []
    start_time = time.time()

    try:
        if adapters == "api" and messages > 0:
            base_url = f"http://localhost:{port}"
            if not asyncio.run(_wait_for_server(base_url)):
                print("ERROR: API server did not become healthy")
                shutdown_process()
                return 1

            token = asyncio.run(_get_auth_token(base_url))
            if not token:
                print("No auth token yet, attempting first-run setup...")
                setup_ok = asyncio.run(_complete_setup(base_url, port))
                if setup_ok:
                    token = asyncio.run(_get_auth_token(base_url))
            if not token:
                print("ERROR: Could not authenticate with QA credentials")
                shutdown_process()
                return 1
            runtime_ready = asyncio.run(_wait_for_runtime_ready(base_url, token))
            if not runtime_ready:
                print("ERROR: Agent runtime did not become ready for authenticated traffic")
                shutdown_process()
                return 1

            print("\n[2/3] Running message load...")
            success, failed, elapsed = asyncio.run(_run_message_load(base_url, token, messages, concurrency))
            print(f"  Message load complete: {success}/{messages} in {elapsed:.1f}s (failed={failed})")

            immediate_mem = get_children_memory(pid)
            if immediate_mem > 0:
                samples.append(immediate_mem)

            settle_deadline = time.time() + min(10, duration)
            while time.time() < settle_deadline and process.poll() is None:
                mem = get_children_memory(pid)
                if mem > 0:
                    samples.append(mem)
                time.sleep(0.2)
        else:
            print(f"\n[2/3] Monitoring memory for ~{duration}s...")
            end_time = start_time + duration
            while time.time() < end_time and process.poll() is None:
                mem = get_children_memory(pid)
                if mem > 0:
                    samples.append(mem)
                    elapsed = time.time() - start_time
                    print(f"  {elapsed:5.1f}s: {format_size(mem)}", end="\r")
                time.sleep(0.1)
            print()

        print("\n[3/3] Shutting down process...")
        shutdown_process()

        print("\n" + "=" * 70)
        print("MEMORY SUMMARY")
        print("=" * 70)
        if samples:
            initial = samples[0]
            peak = max(samples)
            final = samples[-1]
            avg = sum(samples) / len(samples)
            print(f"  Initial:    {format_size(initial)}")
            print(f"  Peak:       {format_size(peak)}")
            print(f"  Final:      {format_size(final)}")
            print(f"  Average:    {format_size(avg)}")
            print(f"  Samples:    {len(samples)}")
        else:
            print("  No memory samples collected")
        print(f"\n  Adapters:   {adapters}")
        print("  Mock LLM:   True")
        if messages > 0:
            print(f"  Messages:   {messages}")
        print("\n" + "=" * 70)
        print("INTROSPECTION COMPLETE")
        print("=" * 70)
        return 0

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        process.terminate()
        process.wait(timeout=5)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CIRIS memory introspection tool")
    parser.add_argument(
        "--adapters",
        default="cli",
        help="Adapter to use (default: cli)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=30,
        help="Seconds to run before shutdown (default: 30)",
    )
    parser.add_argument(
        "--messages",
        type=int,
        default=0,
        help="Optional message-load count (API adapter only)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=8,
        help="Message-load concurrency (default: 8)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="API port when adapters=api (default: 8080)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(
        main(
            adapters=args.adapters,
            duration=args.duration,
            messages=max(0, args.messages),
            concurrency=max(1, args.concurrency),
            port=args.port,
        )
    )
