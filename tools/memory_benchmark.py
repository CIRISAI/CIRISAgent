#!/usr/bin/env python3
"""Memory benchmark for CIRIS agent under message load.

Measures RSS memory growth while submitting N async messages to the API.
Designed for fast, reliable mock LLM profiling up to 1k+ messages.
"""

import argparse
import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path


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
                    return True
            except Exception:
                pass
            await asyncio.sleep(1.0)
    return False


async def get_auth_token(base_url: str, retries: int = 30) -> str:
    """Get auth token from API with retries."""
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


async def complete_setup(base_url: str, port: int) -> bool:
    """Complete first-run setup for benchmark environments."""
    import httpx

    payload = {
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

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{base_url}/v1/setup/complete", json=payload)
        return response.status_code == 200
    except Exception:
        return False


async def send_messages(base_url: str, messages: int, token: str, concurrency: int) -> tuple[int, int, float]:
    """Submit messages concurrently using unique channel_id values."""
    import httpx

    queue: asyncio.Queue[int] = asyncio.Queue()
    for i in range(messages):
        queue.put_nowait(i)

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    success = 0
    failed = 0
    counter_lock = asyncio.Lock()
    start = time.time()

    limits = httpx.Limits(max_keepalive_connections=max(20, concurrency * 2), max_connections=max(40, concurrency * 4))
    client_timeout = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=10.0)

    async def worker(worker_id: int) -> None:
        nonlocal success, failed
        async with httpx.AsyncClient(timeout=client_timeout, limits=limits) as client:
            while True:
                try:
                    idx = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return

                payload = {
                    "message": f"Memory benchmark message {idx + 1} of {messages}",
                    "context": {"channel_id": f"memory_benchmark_w{worker_id}_m{idx}"},
                }

                try:
                    accepted = False
                    for attempt in range(3):
                        response = await client.post(f"{base_url}/v1/agent/message", json=payload, headers=headers)
                        if response.status_code == 200:
                            response_json = response.json()
                            accepted = bool(
                                response_json.get("task_id")
                                or response_json.get("data", {}).get("task_id")
                            )
                            if accepted:
                                break
                        await asyncio.sleep(0.15 * (attempt + 1))

                    async with counter_lock:
                        if accepted:
                            success += 1
                        else:
                            failed += 1
                except Exception:
                    async with counter_lock:
                        failed += 1

                if (idx + 1) % 100 == 0:
                    print(f"  Submitted {idx + 1}/{messages} messages...")

                queue.task_done()

    workers = [asyncio.create_task(worker(i)) for i in range(max(1, concurrency))]
    await asyncio.gather(*workers)
    elapsed = time.time() - start
    return success, failed, elapsed


def main(messages: int = 100, adapter: str = "api", port: int = 8080, concurrency: int = 8) -> int:
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

    cmd = [
        sys.executable,
        str(main_py),
        "--adapter",
        adapter,
        "--mock-llm",
        "--port",
        str(port),
    ]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(project_root),
        env=env,
        text=True,
    )
    pid = process.pid
    print(f"  PID: {pid}")

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
        setup_ok = asyncio.run(complete_setup(base_url, port))
        if setup_ok:
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

    print(f"\n[4/4] Sending {messages} messages (concurrency={concurrency})...")
    samples = []
    success = 0
    failed = 0
    try:
        success, failed, elapsed = asyncio.run(send_messages(base_url, messages, token, concurrency))
        print(f"  Submitted {success}/{messages} messages in {elapsed:.1f}s")

        for _ in range(5):
            mem = get_children_memory(pid)
            if mem > 0:
                samples.append(mem)
            time.sleep(0.5)

    except Exception as e:
        print(f"  ERROR: {e}")
    finally:
        print("\nShutting down server...")
        shutdown_process()

    print("\n" + "=" * 70)
    print("MEMORY BENCHMARK RESULTS")
    print("=" * 70)
    final_mem = samples[-1] if samples else 0
    peak_mem = max(samples) if samples else 0

    print(f"  Messages:       {messages}")
    print(f"  Initial:        {format_size(initial_mem)}")
    print(f"  Final:          {format_size(final_mem)}")
    print(f"  Peak:           {format_size(peak_mem)}")
    print(f"  Growth:         {format_size(final_mem - initial_mem)}")
    if messages > 0 and final_mem > initial_mem:
        per_msg = (final_mem - initial_mem) / messages
        print(f"  Per Message:    {format_size(per_msg)}")

    print(f"\n  Adapter:        {adapter}")
    print("  Mock LLM:       True")
    print(f"  Concurrency:    {concurrency}")
    print(f"  Success Rate:   {success}/{messages} ({100 * success / messages:.1f}%)")
    print(f"  Failures:       {failed}")
    print("=" * 70)

    return 0 if success == messages else 1


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
        default=8,
        help="Number of concurrent submit workers (default: 8)",
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
        )
    )
