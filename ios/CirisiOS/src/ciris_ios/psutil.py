"""
iOS psutil stub module.

Provides a minimal psutil-compatible interface for iOS where the real
psutil cannot be used (requires native compilation).

This module provides dummy/estimated values for system monitoring functions.
On iOS, some metrics are available but most system APIs are sandboxed.
"""

import os
import time
from collections import namedtuple
from typing import Optional, Set

# Named tuples to match psutil's interface
svmem = namedtuple(
    "svmem",
    ["total", "available", "percent", "used", "free", "active", "inactive", "buffers", "cached", "shared", "slab"],
)
sdiskusage = namedtuple("sdiskusage", ["total", "used", "free", "percent"])
snetio = namedtuple(
    "snetio", ["bytes_sent", "bytes_recv", "packets_sent", "packets_recv", "errin", "errout", "dropin", "dropout"]
)
pmem = namedtuple("pmem", ["rss", "vms", "shared", "text", "lib", "data", "dirty"])
scputimes = namedtuple(
    "scputimes", ["user", "system", "idle", "nice", "iowait", "irq", "softirq", "steal", "guest", "guest_nice"]
)


def virtual_memory():
    """Return virtual memory statistics (estimated for iOS)."""
    # iOS devices typically have 2-8GB RAM
    # Return conservative estimates
    total = 4 * 1024 * 1024 * 1024  # Assume 4GB
    available = 2 * 1024 * 1024 * 1024  # Assume 2GB available
    used = total - available
    percent = (used / total) * 100

    return svmem(
        total=total,
        available=available,
        percent=percent,
        used=used,
        free=available,
        active=used // 2,
        inactive=used // 2,
        buffers=0,
        cached=0,
        shared=0,
        slab=0,
    )


def disk_usage(path="/"):
    """Return disk usage statistics for the given path."""
    try:
        st = os.statvfs(path)
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        used = total - free
        percent = (used / total) * 100 if total > 0 else 0
        return sdiskusage(total=total, used=used, free=free, percent=percent)
    except (OSError, AttributeError):
        # Fallback for sandboxed environments
        total = 64 * 1024 * 1024 * 1024  # Assume 64GB
        used = 32 * 1024 * 1024 * 1024  # Assume 50% used
        free = total - used
        return sdiskusage(total=total, used=used, free=free, percent=50.0)


def cpu_percent(interval=None, percpu=False):
    """Return CPU usage percentage (dummy value for iOS)."""
    if interval:
        time.sleep(interval)
    if percpu:
        # Assume 6-core device
        return [15.0] * 6
    return 15.0


def cpu_count(logical=True):
    """Return number of CPUs (estimated for iOS)."""
    # Modern iOS devices have 6-8 cores
    return 6


def cpu_times():
    """Return CPU times (dummy values for iOS)."""
    return scputimes(
        user=1000.0,
        system=500.0,
        idle=8500.0,
        nice=0.0,
        iowait=0.0,
        irq=0.0,
        softirq=0.0,
        steal=0.0,
        guest=0.0,
        guest_nice=0.0,
    )


def net_io_counters():
    """Return network I/O counters (dummy values for iOS)."""
    return snetio(
        bytes_sent=0,
        bytes_recv=0,
        packets_sent=0,
        packets_recv=0,
        errin=0,
        errout=0,
        dropin=0,
        dropout=0,
    )


def boot_time():
    """Return system boot time (approximate)."""
    # Return a time from about 1 hour ago as a reasonable estimate
    return time.time() - 3600


class Process:
    """Minimal Process class for compatibility."""

    def __init__(self, pid=None):
        self.pid = pid or os.getpid()
        self._create_time = time.time()

    def memory_info(self):
        """Return memory info for this process."""
        # Return reasonable estimates for a Python app
        rss = 100 * 1024 * 1024  # 100MB RSS
        vms = 500 * 1024 * 1024  # 500MB VMS
        return pmem(
            rss=rss,
            vms=vms,
            shared=0,
            text=0,
            lib=0,
            data=0,
            dirty=0,
        )

    def cpu_percent(self, interval=None):
        """Return CPU usage for this process."""
        if interval:
            time.sleep(interval)
        return 5.0

    def memory_percent(self):
        """Return memory usage percentage for this process."""
        return 2.5

    def create_time(self):
        """Return process creation time."""
        return self._create_time

    def name(self):
        """Return process name."""
        return "python"

    def status(self):
        """Return process status."""
        return "running"

    def is_running(self):
        """Check if process is running."""
        return True


def process_iter(attrs=None):
    """Iterate over running processes (returns only current process on iOS)."""
    yield Process()


def pids():
    """Return list of PIDs (returns only current PID on iOS)."""
    return [os.getpid()]


# Compatibility aliases
CONN_ESTABLISHED = "ESTABLISHED"
CONN_SYN_SENT = "SYN_SENT"
CONN_SYN_RECV = "SYN_RECV"
CONN_FIN_WAIT1 = "FIN_WAIT1"
CONN_FIN_WAIT2 = "FIN_WAIT2"
CONN_TIME_WAIT = "TIME_WAIT"
CONN_CLOSE = "CLOSE"
CONN_CLOSE_WAIT = "CLOSE_WAIT"
CONN_LAST_ACK = "LAST_ACK"
CONN_LISTEN = "LISTEN"
CONN_CLOSING = "CLOSING"


class NoSuchProcess(Exception):
    """Exception raised when a process doesn't exist."""

    pass


class AccessDenied(Exception):
    """Exception raised when access is denied."""

    pass


# =============================================================================
# REGISTER AS 'psutil' IN sys.modules
# =============================================================================

import sys

print("[iOS] Using psutil stub (pure Python)", flush=True)
sys.modules["psutil"] = sys.modules[__name__]
