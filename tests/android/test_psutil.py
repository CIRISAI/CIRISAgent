"""Tests for Android psutil stub module.

This module tests the psutil-compatible interface used by the Android app
where the real psutil cannot be used due to native compilation requirements.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import the module under test
from android.app.src.main.python import psutil


class TestReadProcFile:
    """Tests for _read_proc_file() function."""

    def setup_method(self):
        """Clear blocked paths cache before each test."""
        psutil._blocked_paths.clear()

    def test_read_existing_file(self, tmp_path):
        """Test reading an existing file returns its content."""
        test_file = tmp_path / "test_proc"
        test_file.write_text("test content\nline 2")

        result = psutil._read_proc_file(str(test_file))

        assert result == "test content\nline 2"

    def test_read_nonexistent_file_returns_none(self, tmp_path):
        """Test reading a nonexistent file returns None."""
        result = psutil._read_proc_file(str(tmp_path / "nonexistent"))

        assert result is None

    def test_blocked_path_caching(self, tmp_path):
        """Test that blocked paths are cached to avoid repeated access."""
        nonexistent = str(tmp_path / "nonexistent")

        # First call - should try to access and fail
        result1 = psutil._read_proc_file(nonexistent)
        assert result1 is None
        assert nonexistent in psutil._blocked_paths

        # Second call - should be skipped due to cache
        result2 = psutil._read_proc_file(nonexistent)
        assert result2 is None

    def test_permission_error_caches_path(self, tmp_path):
        """Test that permission errors cache the path."""
        test_file = tmp_path / "no_read"
        test_file.write_text("content")
        test_file.chmod(0o000)

        try:
            result = psutil._read_proc_file(str(test_file))
            assert result is None
            assert str(test_file) in psutil._blocked_paths
        finally:
            # Restore permissions for cleanup
            test_file.chmod(0o644)


class TestVirtualMemory:
    """Tests for virtual_memory() function."""

    def setup_method(self):
        """Clear blocked paths cache before each test."""
        psutil._blocked_paths.clear()

    def test_virtual_memory_returns_svmem(self):
        """Test that virtual_memory returns an svmem named tuple."""
        result = psutil.virtual_memory()

        assert hasattr(result, "total")
        assert hasattr(result, "available")
        assert hasattr(result, "percent")
        assert hasattr(result, "used")
        assert hasattr(result, "free")
        assert hasattr(result, "active")
        assert hasattr(result, "inactive")
        assert hasattr(result, "buffers")
        assert hasattr(result, "cached")
        assert hasattr(result, "shared")
        assert hasattr(result, "slab")

    def test_virtual_memory_with_real_meminfo(self, tmp_path):
        """Test parsing real /proc/meminfo format."""
        meminfo_content = """MemTotal:       16384000 kB
MemFree:         8000000 kB
MemAvailable:   10000000 kB
Buffers:          500000 kB
Cached:          2000000 kB
Active:          4000000 kB
Inactive:        2000000 kB
Shmem:            100000 kB
Slab:             200000 kB
"""
        meminfo_file = tmp_path / "meminfo"
        meminfo_file.write_text(meminfo_content)

        with patch.object(psutil, "_read_proc_file") as mock_read:
            mock_read.return_value = meminfo_content
            result = psutil.virtual_memory()

            # Verify conversion from kB to bytes
            assert result.total == 16384000 * 1024
            assert result.free == 8000000 * 1024
            assert result.available == 10000000 * 1024
            assert result.buffers == 500000 * 1024
            assert result.cached == 2000000 * 1024
            assert result.active == 4000000 * 1024
            assert result.inactive == 2000000 * 1024
            assert result.shared == 100000 * 1024
            assert result.slab == 200000 * 1024

    def test_virtual_memory_percent_calculation(self):
        """Test that memory percent is calculated correctly."""
        meminfo_content = """MemTotal:       1000 kB
MemFree:         500 kB
Buffers:           0 kB
Cached:            0 kB
"""
        with patch.object(psutil, "_read_proc_file", return_value=meminfo_content):
            result = psutil.virtual_memory()
            # used = total - free - buffers - cached = 1000 - 500 - 0 - 0 = 500
            # percent = (500 / 1000) * 100 = 50%
            assert result.percent == 50.0

    def test_virtual_memory_fallback_defaults(self):
        """Test fallback when /proc/meminfo is unavailable."""
        with patch.object(psutil, "_read_proc_file", return_value=None):
            result = psutil.virtual_memory()

            # Verify fallback values
            assert result.total == 4 * 1024 * 1024 * 1024  # 4GB
            assert result.percent == 50.0
            assert result.available == result.total // 2

    def test_virtual_memory_handles_malformed_lines(self):
        """Test handling of malformed lines in meminfo."""
        meminfo_content = """MemTotal:       16384000 kB
BadLine without colon
MemFree:         8000000 kB
AlsoBad:
"""
        with patch.object(psutil, "_read_proc_file", return_value=meminfo_content):
            # Should not raise, should use defaults for missing values
            result = psutil.virtual_memory()
            assert result.total == 16384000 * 1024


class TestCpuCount:
    """Tests for cpu_count() function."""

    def setup_method(self):
        """Clear blocked paths cache before each test."""
        psutil._blocked_paths.clear()

    def test_cpu_count_returns_positive_integer(self):
        """Test that cpu_count returns a positive integer."""
        result = psutil.cpu_count()
        assert isinstance(result, int)
        assert result > 0

    def test_cpu_count_from_cpuinfo(self):
        """Test parsing processor count from /proc/cpuinfo."""
        cpuinfo_content = """processor	: 0
vendor_id	: GenuineIntel

processor	: 1
vendor_id	: GenuineIntel

processor	: 2
vendor_id	: GenuineIntel

processor	: 3
vendor_id	: GenuineIntel
"""
        with patch.object(psutil, "_read_proc_file", return_value=cpuinfo_content):
            result = psutil.cpu_count()
            assert result == 4

    def test_cpu_count_fallback_to_os(self):
        """Test fallback to os.cpu_count() when /proc/cpuinfo unavailable."""
        with patch.object(psutil, "_read_proc_file", return_value=None):
            with patch("os.cpu_count", return_value=8):
                result = psutil.cpu_count()
                assert result == 8

    def test_cpu_count_ultimate_fallback(self):
        """Test ultimate fallback to 4 when everything fails."""
        with patch.object(psutil, "_read_proc_file", return_value=None):
            with patch("os.cpu_count", return_value=None):
                result = psutil.cpu_count()
                assert result == 4

    def test_cpu_count_logical_parameter(self):
        """Test that logical parameter is accepted (compatibility)."""
        # Both should return same value on our stub
        result_logical = psutil.cpu_count(logical=True)
        result_physical = psutil.cpu_count(logical=False)
        assert result_logical == result_physical


class TestDiskUsage:
    """Tests for disk_usage() function."""

    def test_disk_usage_returns_sdiskusage(self):
        """Test that disk_usage returns an sdiskusage named tuple."""
        result = psutil.disk_usage("/")

        assert hasattr(result, "total")
        assert hasattr(result, "used")
        assert hasattr(result, "free")
        assert hasattr(result, "percent")

    def test_disk_usage_valid_path(self, tmp_path):
        """Test disk_usage on a valid path."""
        result = psutil.disk_usage(str(tmp_path))

        assert result.total > 0
        assert result.free >= 0
        assert result.used >= 0
        assert 0 <= result.percent <= 100

    def test_disk_usage_calculation(self, tmp_path):
        """Test that total = used + free approximately."""
        result = psutil.disk_usage(str(tmp_path))

        # Due to reserved blocks, this may not be exact
        assert abs((result.used + result.free) - result.total) < result.total * 0.1

    def test_disk_usage_fallback_on_error(self):
        """Test fallback values when statvfs fails."""
        result = psutil.disk_usage("/nonexistent/path/that/does/not/exist")

        # Should return fallback values
        assert result.total == 16 * 1024**3
        assert result.percent == 50.0


class TestAppStorageUsage:
    """Tests for app_storage_usage() and helper functions."""

    def test_get_directory_size(self, tmp_path):
        """Test _get_directory_size calculates correct size."""
        # Create some files
        (tmp_path / "file1.txt").write_text("hello")  # 5 bytes
        (tmp_path / "file2.txt").write_text("world!")  # 6 bytes
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("test")  # 4 bytes

        size = psutil._get_directory_size(str(tmp_path))
        assert size == 15

    def test_get_directory_size_nonexistent(self):
        """Test _get_directory_size returns 0 for nonexistent path."""
        size = psutil._get_directory_size("/nonexistent/path")
        assert size == 0

    def test_get_file_size_safe(self, tmp_path):
        """Test _get_file_size_safe returns file size."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("12345678")  # 8 bytes

        size = psutil._get_file_size_safe(str(test_file))
        assert size == 8

    def test_get_file_size_safe_error(self):
        """Test _get_file_size_safe returns 0 on error."""
        size = psutil._get_file_size_safe("/nonexistent/file")
        assert size == 0

    def test_directory_contains_databases(self, tmp_path):
        """Test _directory_contains_databases detection."""
        # No databases
        assert not psutil._directory_contains_databases(str(tmp_path))

        # Add a .db file
        (tmp_path / "test.db").write_text("")
        assert psutil._directory_contains_databases(str(tmp_path))

    def test_directory_contains_databases_sqlite3(self, tmp_path):
        """Test detection of .sqlite3 extension."""
        (tmp_path / "data.sqlite3").write_text("")
        assert psutil._directory_contains_databases(str(tmp_path))

    def test_detect_data_directory_from_home(self, tmp_path):
        """Test _detect_data_directory uses HOME environment."""
        with patch.dict(os.environ, {"HOME": str(tmp_path)}):
            result = psutil._detect_data_directory()
            assert result == str(tmp_path)

    def test_detect_data_directory_from_cwd(self, tmp_path):
        """Test _detect_data_directory falls back to CWD pattern."""
        files_dir = tmp_path / "files"
        files_dir.mkdir()

        with patch.dict(os.environ, {"HOME": ""}):
            with patch("os.getcwd", return_value=str(files_dir) + "/subdir"):
                result = psutil._detect_data_directory()
                assert result == str(files_dir)

    def test_find_app_root(self, tmp_path):
        """Test _find_app_root finds parent of 'files' directory."""
        files_dir = tmp_path / "files"
        files_dir.mkdir()

        result = psutil._find_app_root(str(files_dir))
        assert result == str(tmp_path)

    def test_find_app_root_no_files_suffix(self, tmp_path):
        """Test _find_app_root returns input when no /files pattern."""
        result = psutil._find_app_root(str(tmp_path))
        assert result == str(tmp_path)

    def test_categorize_files_item_chaquopy(self, tmp_path):
        """Test _categorize_files_item for chaquopy directory."""
        chaquopy_dir = tmp_path / "chaquopy"
        chaquopy_dir.mkdir()
        (chaquopy_dir / "cache.txt").write_text("12345")  # 5 bytes

        db, files, cq = psutil._categorize_files_item(str(chaquopy_dir), "chaquopy")
        assert db == 0
        assert files == 0
        assert cq == 5

    def test_categorize_files_item_database(self, tmp_path):
        """Test _categorize_files_item for database files."""
        db_file = tmp_path / "test.db"
        db_file.write_text("12345678")  # 8 bytes

        db, files, cq = psutil._categorize_files_item(str(db_file), "test.db")
        assert db == 8
        assert files == 0
        assert cq == 0

    def test_categorize_files_item_regular_file(self, tmp_path):
        """Test _categorize_files_item for regular files."""
        regular_file = tmp_path / "regular.txt"
        regular_file.write_text("hello")  # 5 bytes

        db, files, cq = psutil._categorize_files_item(str(regular_file), "regular.txt")
        assert db == 0
        assert files == 5
        assert cq == 0

    def test_categorize_files_item_dir_with_databases(self, tmp_path):
        """Test _categorize_files_item for directory containing databases."""
        db_dir = tmp_path / "db_dir"
        db_dir.mkdir()
        (db_dir / "data.sqlite").write_text("content")

        db, files, cq = psutil._categorize_files_item(str(db_dir), "db_dir")
        assert db == 7  # "content" is 7 bytes
        assert files == 0
        assert cq == 0

    def test_scan_files_directory(self, tmp_path):
        """Test _scan_files_directory categorization."""
        files_dir = tmp_path / "files"
        files_dir.mkdir()

        # Create test structure
        (files_dir / "data.db").write_text("db")  # 2 bytes
        (files_dir / "file.txt").write_text("text")  # 4 bytes
        chaq = files_dir / "chaquopy"
        chaq.mkdir()
        (chaq / "pip.cache").write_text("cache")  # 5 bytes

        db, files, cq = psutil._scan_files_directory(str(files_dir))
        assert db == 2
        assert files == 4
        assert cq == 5

    def test_scan_files_directory_nonexistent(self):
        """Test _scan_files_directory returns zeros for nonexistent path."""
        db, files, cq = psutil._scan_files_directory("/nonexistent")
        assert db == 0
        assert files == 0
        assert cq == 0

    def test_empty_storage(self):
        """Test _empty_storage returns all zeros."""
        result = psutil._empty_storage()

        assert result.total == 0
        assert result.databases == 0
        assert result.files == 0
        assert result.cache == 0
        assert result.chaquopy == 0
        assert result.other == 0

    def test_app_storage_usage_complete(self, tmp_path):
        """Test app_storage_usage with complete app structure."""
        # Create Android app structure
        app_root = tmp_path / "app"
        app_root.mkdir()

        # Databases directory
        databases = app_root / "databases"
        databases.mkdir()
        (databases / "main.db").write_text("database")  # 8 bytes

        # Files directory
        files = app_root / "files"
        files.mkdir()
        (files / "log.txt").write_text("log")  # 3 bytes
        chaquopy = files / "chaquopy"
        chaquopy.mkdir()
        (chaquopy / "cache").write_text("pip")  # 3 bytes

        # Cache directory
        cache = app_root / "cache"
        cache.mkdir()
        (cache / "temp.tmp").write_text("temp")  # 4 bytes

        # Code cache
        code_cache = app_root / "code_cache"
        code_cache.mkdir()
        (code_cache / "oat.cache").write_text("oat")  # 3 bytes

        # Shared prefs
        shared_prefs = app_root / "shared_prefs"
        shared_prefs.mkdir()
        (shared_prefs / "prefs.xml").write_text("xml")  # 3 bytes

        result = psutil.app_storage_usage(str(files))

        assert result.databases == 8
        assert result.files == 3
        assert result.chaquopy == 3
        assert result.cache == 7  # 4 + 3
        assert result.other == 3
        assert result.total == 8 + 3 + 3 + 7 + 3  # 24

    def test_app_storage_usage_empty_path(self):
        """Test app_storage_usage with None data_dir."""
        with patch.dict(os.environ, {"HOME": ""}):
            with patch("os.getcwd", return_value="/tmp"):
                with patch("os.path.exists", return_value=False):
                    result = psutil.app_storage_usage(None)
                    assert result.total == 0


class TestNetIoCounters:
    """Tests for net_io_counters() function."""

    def setup_method(self):
        """Clear blocked paths cache before each test."""
        psutil._blocked_paths.clear()

    def test_net_io_counters_returns_snetio(self):
        """Test that net_io_counters returns an snetio named tuple."""
        result = psutil.net_io_counters()

        assert hasattr(result, "bytes_sent")
        assert hasattr(result, "bytes_recv")
        assert hasattr(result, "packets_sent")
        assert hasattr(result, "packets_recv")
        assert hasattr(result, "errin")
        assert hasattr(result, "errout")
        assert hasattr(result, "dropin")
        assert hasattr(result, "dropout")

    def test_net_io_counters_parsing(self):
        """Test parsing /proc/net/dev format."""
        netdev_content = """Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo: 1000    100    0    0    0     0          0         0     2000    200    0    0    0     0       0          0
  eth0: 5000    500    1    2    0     0          0         0     3000    300    3    4    0     0       0          0
"""
        with patch.object(psutil, "_read_proc_file", return_value=netdev_content):
            result = psutil.net_io_counters()

            # Sum of all interfaces
            assert result.bytes_recv == 6000  # 1000 + 5000
            assert result.bytes_sent == 5000  # 2000 + 3000
            assert result.packets_recv == 600  # 100 + 500
            assert result.packets_sent == 500  # 200 + 300
            assert result.errin == 1  # 0 + 1
            assert result.errout == 3  # 0 + 3
            assert result.dropin == 2  # 0 + 2
            assert result.dropout == 4  # 0 + 4

    def test_net_io_counters_fallback(self):
        """Test fallback when /proc/net/dev unavailable."""
        with patch.object(psutil, "_read_proc_file", return_value=None):
            result = psutil.net_io_counters()

            # Should return zeros
            assert result.bytes_sent == 0
            assert result.bytes_recv == 0


class TestProcess:
    """Tests for Process class."""

    def setup_method(self):
        """Clear blocked paths cache before each test."""
        psutil._blocked_paths.clear()

    def test_process_init_default_pid(self):
        """Test Process() uses current PID by default."""
        proc = psutil.Process()
        assert proc.pid == os.getpid()

    def test_process_init_custom_pid(self):
        """Test Process() accepts custom PID."""
        proc = psutil.Process(pid=12345)
        assert proc.pid == 12345

    def test_process_memory_info_returns_pmem(self):
        """Test memory_info returns a pmem named tuple."""
        proc = psutil.Process()
        result = proc.memory_info()

        assert hasattr(result, "rss")
        assert hasattr(result, "vms")
        assert hasattr(result, "shared")
        assert hasattr(result, "text")
        assert hasattr(result, "lib")
        assert hasattr(result, "data")
        assert hasattr(result, "dirty")

    def test_process_memory_info_parsing(self):
        """Test parsing /proc/self/statm format."""
        # Format: size resident shared text lib data dirty
        statm_content = "100 50 10 5 0 20 0"

        with patch.object(psutil, "_read_proc_file", return_value=statm_content):
            with patch("os.sysconf", return_value=4096):  # 4KB page size
                proc = psutil.Process()
                result = proc.memory_info()

                assert result.vms == 100 * 4096
                assert result.rss == 50 * 4096
                assert result.shared == 10 * 4096
                assert result.text == 5 * 4096
                assert result.data == 20 * 4096

    def test_process_memory_info_fallback(self):
        """Test fallback when /proc/{pid}/statm unavailable."""
        with patch.object(psutil, "_read_proc_file", return_value=None):
            proc = psutil.Process()
            result = proc.memory_info()

            # Should return fallback values
            assert result.rss == 50 * 1024 * 1024  # 50MB
            assert result.vms == 100 * 1024 * 1024  # 100MB

    def test_process_cpu_percent_returns_float(self):
        """Test cpu_percent returns a float."""
        proc = psutil.Process()
        result = proc.cpu_percent()

        assert isinstance(result, float)
        # Stub returns 5.0
        assert result == 5.0

    def test_process_cpu_percent_with_interval(self):
        """Test cpu_percent accepts interval parameter."""
        proc = psutil.Process()
        result = proc.cpu_percent(interval=0.1)

        assert isinstance(result, float)

    def test_process_memory_percent_returns_float(self):
        """Test memory_percent returns a float."""
        proc = psutil.Process()
        result = proc.memory_percent()

        assert isinstance(result, float)
        assert 0 <= result <= 100

    def test_process_memory_percent_calculation(self):
        """Test memory_percent calculates correctly."""
        with patch.object(
            psutil.Process,
            "memory_info",
            return_value=psutil.pmem(
                rss=100 * 1024 * 1024,  # 100MB
                vms=0,
                shared=0,
                text=0,
                lib=0,
                data=0,
                dirty=0,
            ),
        ):
            with patch.object(
                psutil,
                "virtual_memory",
                return_value=psutil.svmem(
                    total=1000 * 1024 * 1024,  # 1000MB
                    available=0,
                    percent=0,
                    used=0,
                    free=0,
                    active=0,
                    inactive=0,
                    buffers=0,
                    cached=0,
                    shared=0,
                    slab=0,
                ),
            ):
                proc = psutil.Process()
                result = proc.memory_percent()

                # 100 / 1000 * 100 = 10%
                assert result == 10.0


class TestNamedTuples:
    """Tests for named tuple definitions."""

    def test_svmem_fields(self):
        """Test svmem has all required fields."""
        mem = psutil.svmem(
            total=1,
            available=2,
            percent=3,
            used=4,
            free=5,
            active=6,
            inactive=7,
            buffers=8,
            cached=9,
            shared=10,
            slab=11,
        )
        assert mem.total == 1
        assert mem.slab == 11

    def test_sdiskusage_fields(self):
        """Test sdiskusage has all required fields."""
        disk = psutil.sdiskusage(total=100, used=50, free=50, percent=50.0)
        assert disk.total == 100
        assert disk.percent == 50.0

    def test_snetio_fields(self):
        """Test snetio has all required fields."""
        net = psutil.snetio(
            bytes_sent=1,
            bytes_recv=2,
            packets_sent=3,
            packets_recv=4,
            errin=5,
            errout=6,
            dropin=7,
            dropout=8,
        )
        assert net.bytes_sent == 1
        assert net.dropout == 8

    def test_pmem_fields(self):
        """Test pmem has all required fields."""
        mem = psutil.pmem(rss=1, vms=2, shared=3, text=4, lib=5, data=6, dirty=7)
        assert mem.rss == 1
        assert mem.dirty == 7

    def test_sappstorage_fields(self):
        """Test sappstorage has all required fields."""
        storage = psutil.sappstorage(total=100, databases=20, files=30, cache=15, chaquopy=25, other=10)
        assert storage.total == 100
        assert storage.databases == 20
        assert storage.chaquopy == 25


class TestConstants:
    """Tests for module constants."""

    def test_files_dir_suffix(self):
        """Test _FILES_DIR_SUFFIX constant."""
        assert psutil._FILES_DIR_SUFFIX == "/files"

    def test_db_extensions(self):
        """Test _DB_EXTENSIONS constant."""
        assert ".db" in psutil._DB_EXTENSIONS
        assert ".sqlite" in psutil._DB_EXTENSIONS
        assert ".sqlite3" in psutil._DB_EXTENSIONS
