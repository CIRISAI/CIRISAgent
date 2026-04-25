"""
Global test configuration for pytest.

This file is automatically loaded by pytest and contains setup that applies to all tests.
"""

# CRITICAL: Set import protection BEFORE any other imports
import os
import tempfile

os.environ["CIRIS_IMPORT_MODE"] = "true"
os.environ["CIRIS_MOCK_LLM"] = "true"
os.environ["CIRIS_TESTING_MODE"] = "true"  # Enable fallback admin credentials for tests
# Pin language to English so handler-content assertions stay stable regardless
# of the developer's local CIRIS_PREFERRED_LANGUAGE in .env. Tests that
# intentionally exercise localization can override via monkeypatch.
os.environ["CIRIS_PREFERRED_LANGUAGE"] = "en"

# CRITICAL: Override log directory for tests to prevent container interference
# Tests should NEVER write to the main logs directory that containers use
os.environ["CIRIS_LOG_DIR"] = "test_logs"
os.environ["CIRIS_DATA_DIR"] = "test_data"

# PERFORMANCE: Use tmpfs for all temp files to reduce disk I/O during tests
# /dev/shm is a RAM-based tmpfs available on most Linux systems
_TMPFS_DIR = "/dev/shm/ciris_tests"
if os.path.isdir("/dev/shm"):
    # Clean up stale temp files from previous test runs to prevent /dev/shm from filling up
    # Only do this for the main process (not xdist workers) to avoid race conditions
    import shutil

    is_xdist_worker = os.environ.get("PYTEST_XDIST_WORKER") is not None
    if not is_xdist_worker and os.path.isdir(_TMPFS_DIR):
        try:
            shutil.rmtree(_TMPFS_DIR)
        except OSError:
            pass  # May fail if files are in use by another test run
    os.makedirs(_TMPFS_DIR, exist_ok=True)
    os.environ["TMPDIR"] = _TMPFS_DIR
    tempfile.tempdir = _TMPFS_DIR

# PERFORMANCE: Disable network-dependent services in tests
# This prevents NTP checks, billing API calls, etc.
os.environ["CIRIS_DISABLE_NETWORK"] = "true"

# NOTE: Network calls are disabled via CIRIS_IMPORT_MODE and CIRIS_MOCK_LLM
# Code should check these flags and skip network operations entirely

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

# Load environment variables from .env file for all tests
try:
    from dotenv import load_dotenv

    # Find the .env file in the project root
    project_root = Path(__file__).parent.parent
    env_file = project_root / ".env"
    if env_file.exists():
        load_dotenv(env_file)

    # Also load test-specific config if available
    test_env_file = Path(__file__).parent / "test_config.env"
    if test_env_file.exists():
        load_dotenv(test_env_file, override=True)
        # Also set as environment variables for non-dotenv aware code
        import subprocess

        result = subprocess.run(["bash", "-c", f"source {test_env_file} && env"], capture_output=True, text=True)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "=" in line and line.startswith("CIRIS_"):
                    key, value = line.split("=", 1)
                    os.environ[key] = value
except ImportError:
    # If python-dotenv is not installed, silently continue
    pass

import gc  # noqa: E402
import time  # noqa: E402

# Import database fixtures and API fixtures - must be imported after os.environ setup
from tests.fixtures.api import random_api_port  # noqa: E402
from tests.fixtures.database import clean_db, test_db  # noqa: E402
from tests.fixtures.mocks import MockRuntime  # noqa: E402
from tests.fixtures.runtime_control import (  # noqa: E402
    mock_api_runtime_control_service,
    mock_step_result_gather_context,
    mock_step_result_perform_dmas,
    single_step_control_response,
)


@pytest.fixture
def mock_runtime(mock_step_result_perform_dmas):
    """Create a centralized MockRuntime with step result data."""
    runtime = MockRuntime()
    # Connect the centralized step result fixture
    runtime.pipeline_controller.get_latest_step_result.return_value = mock_step_result_perform_dmas
    return runtime


# Make fixtures available to all tests by explicitly referencing them
__all__ = [
    "test_db",
    "clean_db",
    "random_api_port",
    "single_step_control_response",
    "mock_step_result_perform_dmas",
    "mock_step_result_gather_context",
    "mock_api_runtime_control_service",
    "mock_runtime",
]


@pytest.fixture(scope="session", autouse=True)
def manage_import_protection():
    """Manage import protection for the entire test session."""
    # Import protection is already set at module level
    # But we ensure it stays set during test collection
    os.environ["CIRIS_IMPORT_MODE"] = "true"
    os.environ["CIRIS_MOCK_LLM"] = "true"

    yield

    # After all tests are done, we can clear the protection
    # (though it doesn't really matter since process is ending)
    os.environ.pop("CIRIS_IMPORT_MODE", None)


@pytest.fixture(autouse=True)
def _isolate_process_global_env(monkeypatch):
    """Restore global, process-wide env vars to known values for every test.

    Some tests intentionally flip `CIRIS_PREFERRED_LANGUAGE` or
    `CIRIS_LLM_REPLICAS` via raw `os.environ[...] = ...` to exercise
    behavior that depends on those globals. Those env vars work fine for
    personal-agent deployments (one process, one operator) but they are
    the wrong shape for a test harness: under `pytest -n`, xdist workers
    run tests serially per worker, so a leaked mutation from test A can
    change the behavior of unrelated test B and produce flaky CI
    failures (e.g. a handler follow-up rendered in Amharic, or a second
    LLM replica being initialized when the test expects one).

    Using monkeypatch here captures the current values before each test
    and restores them at teardown — even if a test mutates them with raw
    `os.environ[...]` and forgets to restore, or crashes mid-test. Tests
    that want a different value should still prefer `monkeypatch.setenv`
    inside the test so the change is scoped and obvious.
    """
    monkeypatch.setenv("CIRIS_PREFERRED_LANGUAGE", "en")
    monkeypatch.delenv("CIRIS_LLM_REPLICAS", raising=False)


@pytest.fixture(autouse=True, scope="function")
def cleanup_after_test(request):
    """
    Ensure proper cleanup after each test.
    This helps prevent interference between tests, especially when Discord is involved.
    """
    yield

    # Force garbage collection to clean up any lingering objects
    gc.collect()

    # Only add socket cleanup delay for tests that actually use network/Discord
    # This saves ~0.1s per test for the majority of tests that don't need it
    test_path = str(request.fspath) if hasattr(request, "fspath") else ""
    needs_socket_cleanup = (
        "discord" in test_path.lower()
        or request.node.get_closest_marker("requires_discord_token")
        or request.node.get_closest_marker("needs_socket_cleanup")
    )
    if needs_socket_cleanup:
        time.sleep(0.1)


@pytest.fixture(autouse=True, scope="function")
def clear_asyncio_module_state():
    """
    Clear module-level asyncio state to prevent cross-test contamination.

    This fixes the "asyncio.Event/Queue object is bound to a different event loop" error
    that occurs when pytest-xdist runs tests in parallel with different event loops.

    Affected modules:
    1. step_decorators:
       - _paused_thoughts: Dict[str, asyncio.Event] - Events bound to specific event loops
       - _single_step_mode: bool - Global flag for single-step debugging

    2. step_streaming:
       - reasoning_event_stream._subscribers: set[asyncio.Queue] - Queues bound to event loops
       - reasoning_event_stream._sequence_number: int - Counter that should reset
       - reasoning_event_stream._recent_events: list - Buffer that should clear

    Without this cleanup, asyncio primitives created in one test's event loop persist
    and cause RuntimeError when accessed from a different test's event loop.
    """

    def _clear_state():
        # Clear step_decorators state
        try:
            from ciris_engine.logic.processors.core import step_decorators

            step_decorators._paused_thoughts.clear()
            step_decorators._single_step_mode = False
        except ImportError:
            pass  # Module not yet available during collection

        # Clear step_streaming singleton state
        try:
            from ciris_engine.logic.infrastructure.step_streaming import reasoning_event_stream

            reasoning_event_stream._subscribers.clear()
            reasoning_event_stream._sequence_number = 0
            reasoning_event_stream._recent_events.clear()
        except ImportError:
            pass  # Module not yet available during collection

    # Clear before test
    _clear_state()

    yield

    # Clear after test to ensure clean state for next test
    _clear_state()


@pytest.fixture(autouse=True, scope="function")
def isolate_test_env_vars():
    """
    Isolate environment variables that can cause test pollution.

    This fixture saves any existing env vars before the test and restores
    them after, ensuring parallel test runs don't interfere with each other.
    """
    # Env vars that need isolation
    env_vars = [
        # Accord metrics (current names)
        "CIRIS_ACCORD_METRICS_CONSENT",
        "CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP",
        "CIRIS_ACCORD_METRICS_TRACE_LEVEL",
        "CIRIS_ACCORD_METRICS_FLUSH_INTERVAL",
        "CIRIS_ACCORD_METRICS_ENDPOINT",
        # Legacy covenant metrics (for backward compat)
        "CIRIS_COVENANT_METRICS_CONSENT",
        "CIRIS_COVENANT_METRICS_CONSENT_TIMESTAMP",
        "CIRIS_COVENANT_METRICS_TRACE_LEVEL",
        "CIRIS_COVENANT_METRICS_FLUSH_INTERVAL",
        "CIRIS_COVENANT_METRICS_ENDPOINT",
        # LLM provider detection (affects which provider is selected)
        "CIRIS_LLM_PROVIDER",
        "LLM_PROVIDER",
        "OPENAI_API_KEY",
        "OPENAI_API_BASE",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        # Dual LLM service
        "CIRIS_OPENAI_API_KEY_2",
        "CIRIS_OPENAI_API_BASE_2",
        "CIRIS_OPENAI_MODEL_NAME_2",
    ]

    # Save existing values
    saved = {var: os.environ.get(var) for var in env_vars}

    # Clear them before test
    for var in env_vars:
        os.environ.pop(var, None)

    yield

    # Restore original values after test
    for var, value in saved.items():
        if value is not None:
            os.environ[var] = value
        else:
            os.environ.pop(var, None)


# Import WA test harness fixtures (when available)
try:
    from ciris_engine.logic.services.test_wa_auth_harness import wa_test_env, wa_test_harness, wa_test_keys
except ImportError:
    # WA test harness not available yet
    wa_test_harness = None
    wa_test_env = None
    wa_test_keys = None


# Skip Discord tests if no token is set
def pytest_configure(config):
    config.addinivalue_line("markers", "requires_discord_token: mark test as requiring Discord token")
    config.addinivalue_line("markers", "needs_socket_cleanup: mark test as needing socket cleanup delay")


# =============================================================================
# Test Start/End Markers for Debugging Hanging Tests
# =============================================================================
# These hooks print markers that can be grep'd to find tests that started but
# never finished (hanging tests). Look for [TEST_START] without matching [TEST_END].


def pytest_runtest_logstart(nodeid, location):
    """Print marker when test starts - helps identify hanging tests in CI logs."""
    import sys

    # Flush to ensure marker appears immediately in CI logs
    print(f"\n[TEST_START] {nodeid}", file=sys.stderr, flush=True)


def pytest_runtest_logfinish(nodeid, location):
    """Print marker when test finishes - pair with TEST_START to find hangs."""
    import sys

    print(f"[TEST_END] {nodeid}", file=sys.stderr, flush=True)


# ============================================================================
# CASCADING FAILURE PROTECTION
# ============================================================================
# These hooks and fixtures prevent a single test crash from causing
# cascading failures (e.g., 18-minute hangs due to orphan processes).


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_teardown(item, nextitem):
    """Clean up any orphan async tasks after each test.

    This prevents tests from leaving behind background tasks that can
    cause worker crashes or hangs in pytest-xdist.
    """
    import asyncio

    try:
        # Only cancel tasks if there's a running event loop
        # get_event_loop() without a running loop is deprecated in Python 3.10+
        # and there are no tasks to cancel anyway if there's no loop
        try:
            loop = asyncio.get_running_loop()
            # Cancel any pending tasks from this test
            pending = asyncio.all_tasks(loop)
            for task in pending:
                if not task.done():
                    task.cancel()
        except RuntimeError:
            # No running loop - nothing to clean up
            pass
    except Exception:
        pass  # Best effort cleanup


@pytest.fixture(autouse=True, scope="function")
def prevent_subprocess_orphans():
    """Track and clean up any subprocesses spawned during tests.

    This prevents tests from leaving orphan processes that can cause
    pytest-xdist workers to hang during shutdown.
    """
    import subprocess
    import weakref

    # Track any Popen objects created during the test
    original_popen = subprocess.Popen
    spawned_processes = []

    class TrackedPopen(original_popen):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            spawned_processes.append(weakref.ref(self))

    subprocess.Popen = TrackedPopen

    yield

    # Restore original Popen
    subprocess.Popen = original_popen

    # Kill any processes that are still running
    for proc_ref in spawned_processes:
        proc = proc_ref()
        if proc is not None:
            try:
                if proc.poll() is None:  # Still running
                    proc.kill()
                    proc.wait(timeout=1)
            except Exception:
                pass  # Best effort cleanup


@pytest.fixture(autouse=True)
def skip_without_discord_token(request):
    """Skip tests that require Discord token if not available."""
    if request.node.get_closest_marker("requires_discord_token"):
        if not os.environ.get("DISCORD_BOT_TOKEN"):
            pytest.skip("Test requires DISCORD_BOT_TOKEN environment variable")


# SDK client fixture removed - ciris_sdk no longer exists


# Remove the event_loop fixture - let pytest-asyncio handle it
# The asyncio_mode = auto in pytest.ini will create event loops as needed

# Import centralized fixtures to make them available to all tests
pytest_plugins = [
    "tests.fixtures.auth",  # Centralized auth fixtures (SECURITY: uses dynamic passwords)
    "tests.fixtures.telemetry_api",
    "tests.fixtures.system_snapshot_fixtures",
    "tests.fixtures.audit",
    "tests.fixtures.database_maintenance",
]


@pytest.fixture
def api_required():
    """Mark test as requiring running API."""
    import socket

    # Check if API is accessible
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("localhost", 8080))
        sock.close()

        if result != 0:
            pytest.skip("API not running on localhost:8080")
    except Exception:
        pytest.skip("Cannot check API availability")
