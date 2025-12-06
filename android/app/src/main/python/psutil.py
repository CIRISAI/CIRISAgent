"""
Android psutil stub module.

Provides a minimal psutil-compatible interface for Android where the real
psutil cannot be used (requires native compilation).

This module provides dummy/estimated values for system monitoring functions.
On Android, some metrics can be read from /proc but others are unavailable.

TODO: Implement real Android system metrics using:
- ActivityManager for memory info (via Chaquopy Java bridge)
- /proc/stat for real CPU usage calculations
- Android BatteryManager for power metrics
- StorageStatsManager for app-specific storage
- TrafficStats for network I/O per app
See: https://developer.android.com/reference/android/app/ActivityManager
"""

import os
import time
from collections import namedtuple
from typing import Optional, Set

# Cache of paths that have failed due to permissions (to avoid repeated SELinux denials)
_blocked_paths: Set[str] = set()

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


def _read_proc_file(path: str) -> Optional[str]:
    """Read a /proc file safely with caching for blocked paths.

    On Android, SELinux blocks access to certain /proc files like
    /proc/net/dev and /proc/{pid}/statm. We cache these failures
    to avoid repeated access attempts that pollute the logs.
    """
    # Skip paths that have already failed due to permissions
    if path in _blocked_paths:
        return None

    try:
        with open(path, "r") as f:
            return f.read()
    except (IOError, OSError, PermissionError):
        # Cache this path as blocked to avoid repeated access attempts
        _blocked_paths.add(path)
        return None


def virtual_memory():
    """Return virtual memory statistics."""
    # Try to read from /proc/meminfo
    meminfo = _read_proc_file("/proc/meminfo")

    if meminfo:
        mem = {}
        for line in meminfo.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                # Remove 'kB' suffix and convert to bytes
                try:
                    mem[key.strip()] = int(value.strip().split()[0]) * 1024
                except (ValueError, IndexError):
                    pass

        total = mem.get("MemTotal", 4 * 1024 * 1024 * 1024)  # Default 4GB
        free = mem.get("MemFree", 0)
        available = mem.get("MemAvailable", free)
        buffers = mem.get("Buffers", 0)
        cached = mem.get("Cached", 0)
        active = mem.get("Active", 0)
        inactive = mem.get("Inactive", 0)
        shared = mem.get("Shmem", 0)
        slab = mem.get("Slab", 0)

        used = total - free - buffers - cached
        percent = (used / total * 100) if total > 0 else 0

        return svmem(
            total=total,
            available=available,
            percent=percent,
            used=used,
            free=free,
            active=active,
            inactive=inactive,
            buffers=buffers,
            cached=cached,
            shared=shared,
            slab=slab,
        )

    # Fallback defaults
    total = 4 * 1024 * 1024 * 1024  # 4GB
    return svmem(
        total=total,
        available=total // 2,
        percent=50.0,
        used=total // 2,
        free=total // 4,
        active=total // 4,
        inactive=total // 4,
        buffers=0,
        cached=total // 4,
        shared=0,
        slab=0,
    )


def cpu_count(logical: bool = True) -> int:
    """Return number of CPUs."""
    try:
        # Try to read from /proc/cpuinfo
        cpuinfo = _read_proc_file("/proc/cpuinfo")
        if cpuinfo:
            count = cpuinfo.count("processor")
            if count > 0:
                return count
    except Exception:
        pass

    # Try os.cpu_count()
    count = os.cpu_count()
    return count if count else 4


def disk_usage(path: str):
    """Return disk usage statistics for the given path (filesystem level)."""
    try:
        stat = os.statvfs(path)
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bavail * stat.f_frsize
        used = total - free
        percent = (used / total * 100) if total > 0 else 0
        return sdiskusage(total=total, used=used, free=free, percent=percent)
    except (OSError, IOError):
        # Return dummy values
        return sdiskusage(total=16 * 1024**3, used=8 * 1024**3, free=8 * 1024**3, percent=50.0)


# Named tuple for app-specific storage breakdown
sappstorage = namedtuple(
    "sappstorage",
    ["total", "databases", "files", "cache", "chaquopy", "other"],
)


def _get_directory_size(path: str) -> int:
    """Calculate the total size of all files in a directory tree.

    Handles permission errors gracefully and skips inaccessible files.
    """
    if not os.path.exists(path):
        return 0

    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    # Use lstat to not follow symlinks
                    total_size += os.lstat(filepath).st_size
                except (OSError, IOError):
                    # Skip files we can't access
                    pass
    except (OSError, IOError):
        pass

    return total_size


def app_storage_usage(data_dir: Optional[str] = None) -> sappstorage:
    """Return app-specific storage usage breakdown.

    This calculates actual storage used by the app's data directories,
    not the filesystem-level stats from disk_usage().

    Args:
        data_dir: Base data directory. If None, tries to detect from environment.
                  On Android/Chaquopy, this is typically the app's files directory.

    Returns:
        sappstorage namedtuple with:
        - total: Total bytes used by the app
        - databases: Bytes used by SQLite databases
        - files: Bytes in the files directory
        - cache: Bytes in cache directories
        - chaquopy: Bytes used by Chaquopy/Python environment
        - other: Bytes in other locations
    """
    # Try to detect the data directory
    if data_dir is None:
        # On Android via Chaquopy, check environment variables
        data_dir = os.environ.get("HOME", "")
        if not data_dir:
            # Fallback: try to find from current working directory
            cwd = os.getcwd()
            # Chaquopy apps typically run from /data/data/<package>/files/chaquopy
            if "/files/" in cwd:
                data_dir = cwd.split("/files/")[0] + "/files"
            else:
                data_dir = cwd

    # Ensure we have a valid base path
    if not data_dir or not os.path.exists(data_dir):
        return sappstorage(total=0, databases=0, files=0, cache=0, chaquopy=0, other=0)

    # Find the app's root data directory (parent of 'files')
    if data_dir.endswith("/files"):
        app_root = os.path.dirname(data_dir)
    elif "/files" in data_dir:
        app_root = data_dir.split("/files")[0]
    else:
        app_root = data_dir

    # Calculate sizes for different categories
    databases_size = 0
    files_size = 0
    cache_size = 0
    chaquopy_size = 0
    other_size = 0

    # Databases directory (SQLite databases including CIRIS db)
    databases_dir = os.path.join(app_root, "databases")
    databases_size = _get_directory_size(databases_dir)

    # Also check for databases in files directory (Chaquopy may store them there)
    files_dir = os.path.join(app_root, "files")
    if os.path.exists(files_dir):
        for item in os.listdir(files_dir) if os.path.exists(files_dir) else []:
            item_path = os.path.join(files_dir, item)
            if item == "chaquopy":
                chaquopy_size = _get_directory_size(item_path)
            elif item.endswith(".db") or item.endswith(".sqlite") or item.endswith(".sqlite3"):
                try:
                    databases_size += os.lstat(item_path).st_size
                except (OSError, IOError):
                    pass
            elif os.path.isdir(item_path):
                # Check for databases in subdirectories (like CIRIS data)
                subdir_size = _get_directory_size(item_path)
                # Check if this directory contains databases
                has_db = False
                try:
                    for f in os.listdir(item_path):
                        if f.endswith((".db", ".sqlite", ".sqlite3")):
                            has_db = True
                            break
                except (OSError, IOError):
                    pass
                if has_db:
                    databases_size += subdir_size
                else:
                    files_size += subdir_size
            else:
                try:
                    files_size += os.lstat(item_path).st_size
                except (OSError, IOError):
                    pass

    # Cache directory
    cache_dir = os.path.join(app_root, "cache")
    cache_size = _get_directory_size(cache_dir)

    # Check for code_cache as well (Android's compiled code cache)
    code_cache_dir = os.path.join(app_root, "code_cache")
    cache_size += _get_directory_size(code_cache_dir)

    # Shared preferences and other directories
    for dirname in ["shared_prefs", "app_webview", "no_backup"]:
        dir_path = os.path.join(app_root, dirname)
        other_size += _get_directory_size(dir_path)

    total = databases_size + files_size + cache_size + chaquopy_size + other_size

    return sappstorage(
        total=total,
        databases=databases_size,
        files=files_size,
        cache=cache_size,
        chaquopy=chaquopy_size,
        other=other_size,
    )


def net_io_counters():
    """Return network I/O counters."""
    # Try to read from /proc/net/dev
    netdev = _read_proc_file("/proc/net/dev")

    bytes_sent = 0
    bytes_recv = 0
    packets_sent = 0
    packets_recv = 0
    errin = 0
    errout = 0
    dropin = 0
    dropout = 0

    if netdev:
        for line in netdev.split("\n")[2:]:  # Skip header lines
            if ":" in line:
                try:
                    parts = line.split(":")[1].split()
                    if len(parts) >= 16:
                        bytes_recv += int(parts[0])
                        packets_recv += int(parts[1])
                        errin += int(parts[2])
                        dropin += int(parts[3])
                        bytes_sent += int(parts[8])
                        packets_sent += int(parts[9])
                        errout += int(parts[10])
                        dropout += int(parts[11])
                except (ValueError, IndexError):
                    pass

    return snetio(
        bytes_sent=bytes_sent,
        bytes_recv=bytes_recv,
        packets_sent=packets_sent,
        packets_recv=packets_recv,
        errin=errin,
        errout=errout,
        dropin=dropin,
        dropout=dropout,
    )


class Process:
    """Process information class."""

    def __init__(self, pid: Optional[int] = None):
        self.pid = pid or os.getpid()
        self._create_time = time.time()

    def memory_info(self):
        """Return process memory info."""
        # Try to read from /proc/self/statm
        statm = _read_proc_file(f"/proc/{self.pid}/statm")

        if statm:
            try:
                parts = statm.split()
                page_size = os.sysconf("SC_PAGE_SIZE")
                vms = int(parts[0]) * page_size
                rss = int(parts[1]) * page_size
                shared = int(parts[2]) * page_size
                text = int(parts[3]) * page_size
                data = int(parts[5]) * page_size
                return pmem(rss=rss, vms=vms, shared=shared, text=text, lib=0, data=data, dirty=0)
            except (ValueError, IndexError):
                pass

        # Return dummy values
        return pmem(rss=50 * 1024 * 1024, vms=100 * 1024 * 1024, shared=0, text=0, lib=0, data=0, dirty=0)

    def cpu_percent(self, interval: Optional[float] = None) -> float:
        """Return CPU usage percentage."""
        # Reading actual CPU usage requires comparing /proc/stat over time
        # For simplicity, return a dummy value
        return 5.0

    def memory_percent(self) -> float:
        """Return memory usage percentage."""
        try:
            mem_info = self.memory_info()
            total_mem = virtual_memory().total
            if total_mem > 0:
                return (mem_info.rss / total_mem) * 100
        except Exception:
            pass
        return 1.0
