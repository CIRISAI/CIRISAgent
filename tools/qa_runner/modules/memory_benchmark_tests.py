"""
Memory benchmark module for QA runner.

Measures RSS memory growth under message load.
Uses QA runner's server lifecycle management for reliable benchmarking.

Supports concurrent channel testing to avoid serial bottlenecks from
updated_info_available flag triggering conscience retries when messages
arrive in a channel with an active task.
"""

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from rich.console import Console

from .base_test_module import BaseTestModule


@dataclass
class MemorySnapshot:
    """Memory snapshot at a point in time."""

    timestamp: float
    rss_bytes: int
    messages_sent: int


@dataclass
class ChannelStats:
    """Statistics for a single benchmark channel."""

    channel_id: str
    messages_sent: int = 0
    messages_succeeded: int = 0
    messages_failed: int = 0
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None

    @property
    def elapsed(self) -> float:
        end = self.end_time or time.time()
        return end - self.start_time

    @property
    def throughput(self) -> float:
        if self.elapsed > 0:
            return self.messages_succeeded / self.elapsed
        return 0.0


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


def find_server_pid(port: int = 8080) -> Optional[int]:
    """Find the PID of the server listening on the given port."""
    try:
        import psutil

        for conn in psutil.net_connections():
            if conn.laddr.port == port and conn.status == "LISTEN":
                return conn.pid
    except Exception:
        pass
    return None


class MemoryBenchmarkTests(BaseTestModule):
    """Memory benchmark test module.

    Sends a configurable number of messages and tracks memory growth.
    Reports initial, final, peak memory and per-message overhead.

    Supports two modes:
    - Serial (concurrent_channels=1): Messages sent one at a time, waiting for completion
    - Concurrent (concurrent_channels>1): Messages spread across N channels, sent in parallel

    Concurrent mode avoids the updated_info_available bottleneck by using
    separate channels that don't interfere with each other.
    """

    def __init__(
        self,
        client: Any,
        console: Console,
        fail_fast: bool = True,
        test_timeout: float = 30.0,
        message_count: int = 100,
        server_pid: Optional[int] = None,
        concurrent_channels: int = 1,
    ):
        super().__init__(client, console, fail_fast, test_timeout)
        self.message_count = message_count
        self.server_pid = server_pid
        self.concurrent_channels = max(1, concurrent_channels)
        self.snapshots: List[MemorySnapshot] = []
        self.channel_stats: Dict[str, ChannelStats] = {}

    def _take_snapshot(self, messages_sent: int) -> Optional[MemorySnapshot]:
        """Take a memory snapshot."""
        pid = self.server_pid or find_server_pid()
        if not pid:
            return None

        mem = get_children_memory(pid)
        if mem <= 0:
            return None

        snapshot = MemorySnapshot(
            timestamp=time.time(),
            rss_bytes=mem,
            messages_sent=messages_sent,
        )
        self.snapshots.append(snapshot)
        return snapshot

    async def run(self) -> List[Dict]:
        """Run memory benchmark tests."""
        self.console.print("\n[bold cyan]Memory Benchmark[/bold cyan]")
        self.console.print(f"  Messages to send: {self.message_count}")
        self.console.print(f"  Concurrent channels: {self.concurrent_channels}")
        if self.concurrent_channels > 1:
            msgs_per_channel = self.message_count // self.concurrent_channels
            self.console.print(f"  Messages per channel: ~{msgs_per_channel}")

        # Start SSE monitoring for task completion
        self._start_sse_monitoring()

        try:
            # Initial memory snapshot
            initial = self._take_snapshot(0)
            if initial:
                self.console.print(f"  Initial memory: {format_size(initial.rss_bytes)}")
            else:
                self.console.print("  [yellow]Warning: Could not measure initial memory[/yellow]")
                self._record_result("memory_snapshot", False, "Could not get server PID")
                return self.results

            # Send messages and track memory
            if self.concurrent_channels > 1:
                await self._test_concurrent_channels(initial)
            else:
                await self._test_message_load(initial)

            # Report results
            self._report_results(initial)

        finally:
            self._stop_sse_monitoring()

        return self.results

    async def _test_message_load(self, initial: MemorySnapshot) -> None:
        """Send messages and track memory growth."""
        self.console.print(f"\n  Sending {self.message_count} messages...")

        success_count = 0
        start_time = time.time()

        # Take snapshots at intervals
        snapshot_interval = max(10, self.message_count // 10)

        for i in range(self.message_count):
            try:
                # Send message and wait for completion
                result = await self._interact(
                    f"Memory benchmark message {i + 1} of {self.message_count}",
                    timeout=self.test_timeout,
                )
                success_count += 1

                # Progress update
                if (i + 1) % snapshot_interval == 0:
                    snapshot = self._take_snapshot(i + 1)
                    if snapshot:
                        growth = snapshot.rss_bytes - initial.rss_bytes
                        self.console.print(
                            f"    {i + 1}/{self.message_count}: "
                            f"{format_size(snapshot.rss_bytes)} "
                            f"(+{format_size(growth)})"
                        )
                    else:
                        self.console.print(f"    {i + 1}/{self.message_count} sent")

            except Exception as e:
                self.console.print(f"    [yellow]Message {i + 1} failed: {e}[/yellow]")

        elapsed = time.time() - start_time

        # Final snapshot
        self._take_snapshot(self.message_count)

        # Record test result
        success_rate = success_count / self.message_count * 100
        passed = success_rate >= 90  # 90% success threshold

        self._record_result(
            f"send_{self.message_count}_messages",
            passed,
            None if passed else f"Only {success_count}/{self.message_count} succeeded",
        )

        self.console.print(
            f"\n  Completed: {success_count}/{self.message_count} in {elapsed:.1f}s "
            f"({success_count / elapsed:.1f} msg/s)"
        )

    async def _test_concurrent_channels(self, initial: MemorySnapshot) -> None:
        """Send messages across multiple channels concurrently."""
        self.console.print(f"\n  Testing with {self.concurrent_channels} concurrent channels...")

        # Initialize channel stats
        for i in range(self.concurrent_channels):
            channel_id = f"benchmark_channel_{i}"
            self.channel_stats[channel_id] = ChannelStats(channel_id=channel_id)

        # Distribute messages across channels
        messages_per_channel = self.message_count // self.concurrent_channels
        remainder = self.message_count % self.concurrent_channels

        start_time = time.time()

        # Create concurrent tasks for each channel
        tasks = []
        for i, (channel_id, stats) in enumerate(self.channel_stats.items()):
            # Add remainder messages to first channels
            count = messages_per_channel + (1 if i < remainder else 0)
            task = asyncio.create_task(self._send_channel_messages(channel_id, count, stats))
            tasks.append(task)

        # Run all channels concurrently
        await asyncio.gather(*tasks)

        elapsed = time.time() - start_time

        # Final snapshot
        self._take_snapshot(self.message_count)

        # Aggregate results
        total_success = sum(s.messages_succeeded for s in self.channel_stats.values())
        total_failed = sum(s.messages_failed for s in self.channel_stats.values())

        # Print channel summaries
        self.console.print("\n  [bold]Channel Performance:[/bold]")
        for channel_id, stats in self.channel_stats.items():
            self.console.print(
                f"    {channel_id}: {stats.messages_succeeded}/{stats.messages_sent} " f"({stats.throughput:.1f} msg/s)"
            )

        # Record test result
        success_rate = total_success / self.message_count * 100 if self.message_count > 0 else 0
        passed = success_rate >= 90  # 90% success threshold

        self._record_result(
            f"concurrent_{self.concurrent_channels}_channels_{self.message_count}_messages",
            passed,
            None if passed else f"Only {total_success}/{self.message_count} succeeded",
        )

        throughput = total_success / elapsed if elapsed > 0 else 0
        self.console.print(
            f"\n  Completed: {total_success}/{self.message_count} in {elapsed:.1f}s " f"({throughput:.1f} msg/s total)"
        )

    async def _send_channel_messages(
        self,
        channel_id: str,
        message_count: int,
        stats: ChannelStats,
    ) -> None:
        """Send messages to a specific channel.

        Uses unique channel_id per message (like A2A benchmark) to avoid
        updated_info_available triggering. Each message gets its own channel
        so there's no cross-talk or conscience retries.
        """
        stats.start_time = time.time()
        snapshot_interval = max(5, message_count // 5)

        for i in range(message_count):
            stats.messages_sent += 1
            try:
                # Each message gets a UNIQUE channel_id (like A2A adapter does)
                # This prevents updated_info_available from triggering
                unique_channel = f"{channel_id}_msg_{i}"
                context = {"channel_id": unique_channel}
                submission = await self.client.agent.submit_message(
                    f"Benchmark message {i + 1}/{message_count}",
                    context=context,
                )

                if submission.accepted:
                    stats.messages_succeeded += 1
                    # Minimal delay - just yield to event loop
                    await asyncio.sleep(0.01)
                else:
                    stats.messages_failed += 1

                # Progress update at intervals
                if (i + 1) % snapshot_interval == 0:
                    snapshot = self._take_snapshot(stats.messages_sent)
                    if snapshot:
                        growth = snapshot.rss_bytes - self.snapshots[0].rss_bytes
                        self.console.print(
                            f"    [{channel_id}] {i + 1}/{message_count}: "
                            f"{format_size(snapshot.rss_bytes)} (+{format_size(growth)})"
                        )

            except Exception as e:
                stats.messages_failed += 1
                self.console.print(f"    [{channel_id}] Message {i + 1} failed: {e}")

        stats.end_time = time.time()

    def _report_results(self, initial: MemorySnapshot) -> None:
        """Report memory benchmark results."""
        if len(self.snapshots) < 2:
            self.console.print("  [yellow]Insufficient snapshots for analysis[/yellow]")
            return

        final = self.snapshots[-1]
        peak = max(self.snapshots, key=lambda s: s.rss_bytes)

        growth = final.rss_bytes - initial.rss_bytes
        per_message = growth / self.message_count if self.message_count > 0 else 0

        self.console.print("\n[bold cyan]Memory Benchmark Results[/bold cyan]")
        self.console.print("=" * 50)
        self.console.print(f"  Messages:     {self.message_count}")
        self.console.print(f"  Initial:      {format_size(initial.rss_bytes)}")
        self.console.print(f"  Final:        {format_size(final.rss_bytes)}")
        self.console.print(f"  Peak:         {format_size(peak.rss_bytes)}")
        self.console.print(f"  Growth:       {format_size(growth)}")
        self.console.print(f"  Per Message:  {format_size(per_message)}")
        self.console.print("=" * 50)

        # Memory thresholds (4GB target)
        max_memory = 4 * 1024 * 1024 * 1024  # 4GB
        max_per_message = 1 * 1024 * 1024  # 1MB per message

        # Check thresholds
        if peak.rss_bytes > max_memory:
            self._record_result(
                "memory_under_4gb",
                False,
                f"Peak {format_size(peak.rss_bytes)} exceeds 4GB limit",
            )
        else:
            self._record_result("memory_under_4gb", True)

        if per_message > max_per_message:
            self._record_result(
                "memory_per_message_reasonable",
                False,
                f"Per-message growth {format_size(per_message)} exceeds 1MB",
            )
        else:
            self._record_result("memory_per_message_reasonable", True)
