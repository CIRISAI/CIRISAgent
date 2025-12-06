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

# Constants
_FILES_DIR_SUFFIX = "/files"
_DB_EXTENSIONS = (".db", ".sqlite", ".sqlite3")


def _get_directory_size(path: str) -> int:
    """Calculate the total size of all files in a directory tree.

    Handles permission errors gracefully and skips inaccessible files.
    """
    if not os.path.exists(path):
        return 0

    total_size = 0
    try:
        for dirpath, _dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.lstat(filepath).st_size
                except (OSError, IOError):
                    pass
    except (OSError, IOError):
        pass

    return total_size


def _get_file_size_safe(path: str) -> int:
    """Get file size safely, returning 0 on error."""
    try:
        return os.lstat(path).st_size
    except (OSError, IOError):
        return 0


def _directory_contains_databases(dir_path: str) -> bool:
    """Check if a directory contains any database files."""
    try:
        return any(f.endswith(_DB_EXTENSIONS) for f in os.listdir(dir_path))
    except (OSError, IOError):
        return False


def _detect_data_directory() -> str:
    """Detect the app's data directory from environment or CWD."""
    data_dir = os.environ.get("HOME", "")
    if data_dir:
        return data_dir

    cwd = os.getcwd()
    files_marker = _FILES_DIR_SUFFIX + "/"
    if files_marker in cwd:
        return cwd.split(files_marker)[0] + _FILES_DIR_SUFFIX
    return cwd


def _find_app_root(data_dir: str) -> str:
    """Find the app's root data directory (parent of 'files')."""
    if data_dir.endswith(_FILES_DIR_SUFFIX):
        return os.path.dirname(data_dir)
    if _FILES_DIR_SUFFIX in data_dir:
        return data_dir.split(_FILES_DIR_SUFFIX)[0]
    return data_dir


def _categorize_files_item(item_path: str, item_name: str) -> tuple[int, int, int]:
    """Categorize a single item in the files directory.

    Returns (databases_size, files_size, chaquopy_size).
    """
    if item_name == "chaquopy":
        return (0, 0, _get_directory_size(item_path))

    if item_name.endswith(_DB_EXTENSIONS):
        return (_get_file_size_safe(item_path), 0, 0)

    if os.path.isdir(item_path):
        subdir_size = _get_directory_size(item_path)
        if _directory_contains_databases(item_path):
            return (subdir_size, 0, 0)
        return (0, subdir_size, 0)

    return (0, _get_file_size_safe(item_path), 0)


def _scan_files_directory(files_dir: str) -> tuple[int, int, int]:
    """Scan files directory and categorize contents.

    Returns (databases_size, files_size, chaquopy_size).
    """
    if not os.path.exists(files_dir):
        return (0, 0, 0)

    databases_size = 0
    files_size = 0
    chaquopy_size = 0

    try:
        for item in os.listdir(files_dir):
            item_path = os.path.join(files_dir, item)
            db, fs, cq = _categorize_files_item(item_path, item)
            databases_size += db
            files_size += fs
            chaquopy_size += cq
    except (OSError, IOError):
        pass

    return (databases_size, files_size, chaquopy_size)


def _empty_storage() -> sappstorage:
    """Return an empty storage result."""
    return sappstorage(total=0, databases=0, files=0, cache=0, chaquopy=0, other=0)


def app_storage_usage(data_dir: Optional[str] = None) -> sappstorage:
    """Return app-specific storage usage breakdown.

    This calculates actual storage used by the app's data directories,
    not the filesystem-level stats from disk_usage().

    Args:
        data_dir: Base data directory. If None, tries to detect from environment.
                  On Android/Chaquopy, this is typically the app's files directory.

    Returns:
        sappstorage namedtuple with storage breakdown by category.
    """
    if data_dir is None:
        data_dir = _detect_data_directory()

    if not data_dir or not os.path.exists(data_dir):
        return _empty_storage()

    app_root = _find_app_root(data_dir)

    # Databases directory
    databases_size = _get_directory_size(os.path.join(app_root, "databases"))

    # Scan files directory
    files_dir = os.path.join(app_root, "files")
    db_from_files, files_size, chaquopy_size = _scan_files_directory(files_dir)
    databases_size += db_from_files

    # Cache directories
    cache_size = _get_directory_size(os.path.join(app_root, "cache"))
    cache_size += _get_directory_size(os.path.join(app_root, "code_cache"))

    # Other directories
    other_size = sum(
        _get_directory_size(os.path.join(app_root, d)) for d in ["shared_prefs", "app_webview", "no_backup"]
    )

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
