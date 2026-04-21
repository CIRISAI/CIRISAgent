#!/usr/bin/env python3
"""Memory benchmark for CIRIS agent under message load.

Measures RSS memory after processing N messages via the API.

Usage:
    python3 tools/memory_benchmark.py --messages 100 --adapter api
    python3 tools/memory_benchmark.py --messages 1000 --adapter api

Prerequisites:
    - API server must be running or will be started automatically
    - Mock LLM mode recommended for reproducible benchmarks
"""
import argparse
import asyncio
import json
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


async def send_messages(base_url: str, messages: int, token: str) -> tuple[int, float]:
    """Send N messages to the API and return (success_count, elapsed_time)."""
    import httpx

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    success = 0
    start = time.time()

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i in range(messages):
            try:
                response = await client.post(
                    f"{base_url}/v1/agent/interact",
                    json={"message": f"Test message {i + 1} of {messages}"},
                    headers=headers,
                )
                if response.status_code == 200:
                    success += 1
                if (i + 1) % 100 == 0:
                    print(f"  Sent {i + 1}/{messages} messages...")
            except Exception as e:
                print(f"  Error sending message {i + 1}: {e}")

    elapsed = time.time() - start
    return success, elapsed


async def get_auth_token(base_url: str) -> str:
    """Get auth token from API."""
    import httpx

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Try to login with default QA credentials
        response = await client.post(
            f"{base_url}/v1/auth/login",
            json={"username": "admin", "password": "qa_test_password_12345"},
        )
        if response.status_code == 200:
            return response.json().get("access_token", "")
    return ""


def main(messages: int = 100, adapter: str = "api", port: int = 8080) -> int:
    """Run memory benchmark with N messages."""
    print("=" * 70)
    print(f"CIRIS MEMORY BENCHMARK - {messages} MESSAGES")
    print("=" * 70)

    project_root = Path(__file__).parent.parent
    main_py = project_root / "main.py"
    base_url = f"http://localhost:{port}"

    # Start server
    print(f"\n[1/4] Starting CIRIS API server...")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    cmd = [
        sys.executable,
        str(main_py),
        "--adapter", adapter,
        "--mock-llm",
        "--port", str(port),
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

    # Wait for server to be ready
    print(f"\n[2/4] Waiting for server...")
    import httpx
    for _ in range(30):
        try:
            r = httpx.get(f"{base_url}/health", timeout=2.0)
            if r.status_code == 200:
                print("  Server ready!")
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        print("  ERROR: Server failed to start")
        process.terminate()
        return 1

    # Measure initial memory
    initial_mem = get_children_memory(pid)
    print(f"\n  Initial memory: {format_size(initial_mem)}")

    # Get auth token
    print(f"\n[3/4] Authenticating...")
    try:
        token = asyncio.run(get_auth_token(base_url))
        if not token:
            print("  WARNING: Could not get auth token, using unauthenticated requests")
    except Exception as e:
        print(f"  WARNING: Auth failed: {e}")
        token = ""

    # Send messages
    print(f"\n[4/4] Sending {messages} messages...")
    samples = []
    try:
        success, elapsed = asyncio.run(send_messages(base_url, messages, token))
        print(f"  Sent {success}/{messages} messages in {elapsed:.1f}s")

        # Sample memory a few times after load
        for _ in range(5):
            mem = get_children_memory(pid)
            if mem > 0:
                samples.append(mem)
            time.sleep(0.5)

    except Exception as e:
        print(f"  ERROR: {e}")
    finally:
        # Shutdown
        print("\nShutting down server...")
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()

    # Report
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
    print(f"  Mock LLM:       True")
    print(f"  Success Rate:   {success}/{messages} ({100*success/messages:.1f}%)")
    print("=" * 70)

    return 0


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
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(main(messages=args.messages, adapter=args.adapter, port=args.port))
