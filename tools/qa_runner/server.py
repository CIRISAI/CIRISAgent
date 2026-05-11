"""
API server management for QA testing.
"""

import asyncio
import hashlib
import json
import logging
import os
import pty
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil
import requests
from rich.console import Console

from .config import QAConfig

logger = logging.getLogger(__name__)

# ============================================================================
# Mock Logshipper Server - Receives accord traces from agents
# ============================================================================


class _MockLogshipperHTTPServer(HTTPServer):
    """HTTPServer subclass that holds per-instance state.

    The handler reads state from `self.server` rather than from the handler
    class itself, so two MockLogshipperServer instances running concurrently
    in the same Python process (e.g. SQLITE + POSTGRES under
    --parallel-backends) keep their `output_dir` and `received_traces`
    separate. The previous class-level storage on MockLogshipperHandler
    meant the second .start() call clobbered the first's state and ALL
    received traces went to whichever backend won the assignment race.
    """

    output_dir: Optional[Path]
    received_traces: List[Dict[str, Any]]


class MockLogshipperHandler(BaseHTTPRequestHandler):
    """HTTP handler for mock logshipper that receives accord traces.

    State lives on `self.server` (the _MockLogshipperHTTPServer instance)
    so each MockLogshipperServer can run independently in the same process.
    """

    # Optional class-level fallbacks ONLY for code paths that still reach
    # for them via the class (e.g. tests that import the handler directly
    # without spinning up a server). Real server use should always populate
    # state on the _MockLogshipperHTTPServer instance.
    received_traces: List[Dict[str, Any]] = []
    output_dir: Optional[Path] = None

    @property
    def _state_owner(self) -> Any:
        """Return the object whose state should be used for this request.

        Prefer the per-server state (self.server) when available; fall back
        to the handler class for legacy callers.
        """
        if isinstance(self.server, _MockLogshipperHTTPServer):
            return self.server
        return MockLogshipperHandler

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default logging."""
        pass

    def do_POST(self) -> None:
        """Handle POST requests to /v1/accord/events or /accord/events."""
        if self.path in ("/v1/accord/events", "/accord/events"):
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            try:
                payload = json.loads(body.decode("utf-8"))
                events = payload.get("events", [])

                for event in events:
                    if event.get("event_type") == "complete_trace":
                        trace = event.get("trace", {})
                        self._save_trace(trace)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status": "ok"}')

            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f'{{"error": "{str(e)}"}}'.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def _save_trace(self, trace: Dict[str, Any]) -> None:
        """Save a trace to file with task-based name.

        Reads `output_dir` and appends to `received_traces` on the
        per-server state owner so concurrent MockLogshipperServer instances
        don't share a destination.
        """
        owner = self._state_owner
        output_dir = getattr(owner, "output_dir", None)
        if not output_dir:
            return

        # Extract task name from first component
        task_name = "unknown"
        components = trace.get("components", [])
        for comp in components:
            if comp.get("event_type") == "THOUGHT_START":
                data = comp.get("data", {})
                task_desc = data.get("task_description", "").lower()
                # Map wakeup task descriptions to standard task names
                # These are the 5 wakeup steps in CIRIS
                # Check most specific patterns first, then more general ones
                if "you are datum" in task_desc or "humble measurement" in task_desc:
                    task_name = "VERIFY_IDENTITY"
                elif "validate your internal state" in task_desc:
                    task_name = "VALIDATE_INTEGRITY"
                elif "you are robust" in task_desc and ("resilience" in task_desc or "adaptive" in task_desc):
                    task_name = "EVALUATE_RESILIENCE"
                elif "you recognize your incompleteness" in task_desc:
                    task_name = "ACCEPT_INCOMPLETENESS"
                elif "you are grateful" in task_desc:
                    task_name = "EXPRESS_GRATITUDE"
                else:
                    # Use sanitized first 30 chars of description as name
                    raw_name = data.get("task_description", "unknown")[:30]
                    task_name = raw_name.replace(" ", "_").replace("/", "_").replace(",", "")
                break

        # Save trace with task-based name and unique hash of trace_id
        trace_id = trace.get("trace_id", "unknown")
        # Create short unique ID from hash of trace_id
        short_id = hashlib.md5(trace_id.encode()).hexdigest()[:8]
        filename = f"trace_{task_name}_{short_id}.json"
        filepath = output_dir / filename

        with open(filepath, "w") as f:
            json.dump(trace, f, indent=2, default=str)

        getattr(owner, "received_traces").append(
            {
                "task_name": task_name,
                "filepath": str(filepath),
                "components": len(components),
            }
        )


class MockLogshipperServer:
    """Mock logshipper server that receives and saves accord traces.

    Per-instance state lives on the underlying HTTPServer subclass
    (_MockLogshipperHTTPServer) so two MockLogshipperServer instances can
    run concurrently in the same process without overwriting each other's
    output_dir / received_traces.
    """

    def __init__(self, port: int = 18080, output_dir: Optional[Path] = None):
        """Initialize mock server.

        Args:
            port: Port to listen on
            output_dir: Directory to save traces to
        """
        self.port = port
        self.output_dir = output_dir or Path(__file__).parent.parent.parent / "qa_reports"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.server: Optional[_MockLogshipperHTTPServer] = None
        self.thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        """Start the mock server in a background thread."""
        try:
            self.server = _MockLogshipperHTTPServer(("127.0.0.1", self.port), MockLogshipperHandler)
            # Per-instance state — handler reads via self.server, NOT class attrs
            self.server.output_dir = self.output_dir
            self.server.received_traces = []
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            return True
        except Exception:
            return False

    def stop(self) -> None:
        """Stop the mock server."""
        if self.server:
            self.server.shutdown()
            self.server = None

    def get_received_traces(self) -> List[Dict[str, Any]]:
        """Get list of received traces (per-instance)."""
        if self.server is None:
            return []
        return list(self.server.received_traces)

    @property
    def endpoint_url(self) -> str:
        """Get the endpoint URL for configuring the adapter."""
        return f"http://127.0.0.1:{self.port}"


# PostgreSQL Docker container name for QA testing
POSTGRES_CONTAINER_NAME = "ciris-qa-postgres"
POSTGRES_IMAGE = "postgres:15-alpine"
POSTGRES_PORT = 5432


def _is_docker_available() -> bool:
    """Check if Docker is available."""
    try:
        result = subprocess.run(["docker", "--version"], capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def _is_postgres_container_running() -> bool:
    """Check if the PostgreSQL container is running."""
    try:
        result = subprocess.run(
            ["docker", "ps", "-q", "-f", f"name={POSTGRES_CONTAINER_NAME}"], capture_output=True, text=True, timeout=5
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


def _start_postgres_container(console: Console) -> bool:
    """Start PostgreSQL container for QA testing."""
    if not _is_docker_available():
        console.print("[red]❌ Docker not available - cannot start PostgreSQL[/red]")
        return False

    if _is_postgres_container_running():
        console.print("[green]✅ PostgreSQL container already running[/green]")
        return True

    console.print("[cyan]🐘 Starting PostgreSQL container...[/cyan]")

    # Check if container exists but is stopped
    try:
        result = subprocess.run(
            ["docker", "ps", "-aq", "-f", f"name={POSTGRES_CONTAINER_NAME}"], capture_output=True, text=True, timeout=5
        )
        if result.stdout.strip():
            # Container exists, just start it
            subprocess.run(["docker", "start", POSTGRES_CONTAINER_NAME], capture_output=True, timeout=10)
            console.print("[green]✅ Started existing PostgreSQL container[/green]")
        else:
            # Create and start new container
            subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    POSTGRES_CONTAINER_NAME,
                    "-e",
                    "POSTGRES_USER=ciris_test",
                    "-e",
                    "POSTGRES_PASSWORD=ciris_test_password",
                    "-e",
                    "POSTGRES_DB=ciris_test_db",
                    "-p",
                    f"{POSTGRES_PORT}:5432",
                    POSTGRES_IMAGE,
                ],
                capture_output=True,
                timeout=60,
            )
            console.print("[green]✅ Created new PostgreSQL container[/green]")
    except Exception as e:
        console.print(f"[red]❌ Failed to start PostgreSQL: {e}[/red]")
        return False

    # Wait for PostgreSQL to be ready
    console.print("[cyan]⏳ Waiting for PostgreSQL to be ready...[/cyan]")
    for _ in range(30):  # Wait up to 30 seconds
        try:
            result = subprocess.run(
                ["docker", "exec", POSTGRES_CONTAINER_NAME, "pg_isready", "-U", "ciris_test"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                console.print("[green]✅ PostgreSQL is ready[/green]")
                # Create derivative databases (_secrets, _auth)
                if not _create_derivative_databases(console):
                    console.print("[yellow]⚠️  Failed to create derivative databases, continuing anyway[/yellow]")
                return True
        except Exception:
            pass
        time.sleep(1)

    console.print("[red]❌ PostgreSQL failed to become ready[/red]")
    return False


def _create_derivative_databases(console: Console) -> bool:
    """Create derivative databases (_secrets, _auth) for CIRIS."""
    try:
        # Use docker exec to run SQL commands as postgres superuser
        # Create ciris_test_db_secrets
        result = subprocess.run(
            [
                "docker",
                "exec",
                POSTGRES_CONTAINER_NAME,
                "psql",
                "-U",
                "ciris_test",
                "-d",
                "postgres",
                "-c",
                "CREATE DATABASE ciris_test_db_secrets OWNER ciris_test;",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            console.print("[green]✅ Created ciris_test_db_secrets[/green]")
        elif "already exists" in result.stderr:
            console.print("[dim]ciris_test_db_secrets already exists[/dim]")
        else:
            console.print(f"[yellow]⚠️  Could not create secrets db: {result.stderr}[/yellow]")

        # Create ciris_test_db_auth
        result = subprocess.run(
            [
                "docker",
                "exec",
                POSTGRES_CONTAINER_NAME,
                "psql",
                "-U",
                "ciris_test",
                "-d",
                "postgres",
                "-c",
                "CREATE DATABASE ciris_test_db_auth OWNER ciris_test;",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            console.print("[green]✅ Created ciris_test_db_auth[/green]")
        elif "already exists" in result.stderr:
            console.print("[dim]ciris_test_db_auth already exists[/dim]")
        else:
            console.print(f"[yellow]⚠️  Could not create auth db: {result.stderr}[/yellow]")

        return True
    except Exception as e:
        console.print(f"[yellow]⚠️  Failed to create derivative databases: {e}[/yellow]")
        return False


def _stop_postgres_container(console: Console):
    """Stop PostgreSQL container."""
    if _is_postgres_container_running():
        console.print("[cyan]🐘 Stopping PostgreSQL container...[/cyan]")
        try:
            subprocess.run(["docker", "stop", POSTGRES_CONTAINER_NAME], capture_output=True, timeout=15)
            console.print("[green]✅ PostgreSQL container stopped[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠️  Failed to stop PostgreSQL: {e}[/yellow]")


def _wipe_postgres_databases(console: Console) -> bool:
    """Wipe all tables in PostgreSQL databases for clean QA testing.

    This drops and recreates all three databases:
    - ciris_test_db (main)
    - ciris_test_db_secrets
    - ciris_test_db_auth

    Returns:
        True if wipe succeeded, False otherwise
    """
    if not _is_postgres_container_running():
        console.print("[yellow]⚠️  PostgreSQL container not running, nothing to wipe[/yellow]")
        return True

    console.print("[cyan]🧹 Wiping PostgreSQL databases for clean QA state...[/cyan]")

    databases = ["ciris_test_db", "ciris_test_db_secrets", "ciris_test_db_auth"]

    for db_name in databases:
        try:
            # Drop and recreate the database
            # First, terminate all connections to the database
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    POSTGRES_CONTAINER_NAME,
                    "psql",
                    "-U",
                    "ciris_test",
                    "-d",
                    "postgres",
                    "-c",
                    f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}' AND pid <> pg_backend_pid();",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            # Drop the database
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    POSTGRES_CONTAINER_NAME,
                    "psql",
                    "-U",
                    "ciris_test",
                    "-d",
                    "postgres",
                    "-c",
                    f"DROP DATABASE IF EXISTS {db_name};",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0 and "does not exist" not in result.stderr:
                console.print(f"[yellow]⚠️  Could not drop {db_name}: {result.stderr}[/yellow]")

            # Recreate the database
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    POSTGRES_CONTAINER_NAME,
                    "psql",
                    "-U",
                    "ciris_test",
                    "-d",
                    "postgres",
                    "-c",
                    f"CREATE DATABASE {db_name} OWNER ciris_test;",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                console.print(f"[green]✅ Wiped and recreated {db_name}[/green]")
            elif "already exists" in result.stderr:
                console.print(f"[dim]{db_name} already exists (drop may have failed)[/dim]")
            else:
                console.print(f"[yellow]⚠️  Could not create {db_name}: {result.stderr}[/yellow]")

        except subprocess.TimeoutExpired:
            console.print(f"[yellow]⚠️  Timeout wiping {db_name}[/yellow]")
        except Exception as e:
            console.print(f"[yellow]⚠️  Error wiping {db_name}: {e}[/yellow]")

    console.print("[green]✅ PostgreSQL databases wiped[/green]")
    return True


def _ensure_env_file(console: Console, mock_llm: bool = True) -> bool:
    """Ensure a minimal .env file exists for QA testing.

    Args:
        console: Rich console for output
        mock_llm: Whether to use mock LLM (True) or live LLM (False)

    Returns True if .env was created/updated/exists, False on error.
    """
    project_root = Path(__file__).parent.parent.parent
    env_path = project_root / ".env"

    # Generate expected content based on mock_llm setting
    if mock_llm:
        expected_env = """# Auto-generated minimal .env for QA testing
# Created by QA runner - safe to delete after testing
CIRIS_CONFIGURED=true
CIRIS_LLM_PROVIDER=mock
CIRIS_MOCK_LLM=true
"""
    else:
        # Live LLM mode - don't set CIRIS_MOCK_LLM at all
        expected_env = """# Auto-generated minimal .env for QA testing
# Created by QA runner - safe to delete after testing
CIRIS_CONFIGURED=true
# Live LLM mode - CIRIS_MOCK_LLM not set
"""

    # Check if .env exists and has correct content
    if env_path.exists():
        current_content = env_path.read_text()
        # If using live mode but .env has CIRIS_MOCK_LLM=true, update it
        if not mock_llm and "CIRIS_MOCK_LLM=true" in current_content:
            console.print("[cyan]📝 Updating .env for live LLM mode...[/cyan]")
            try:
                env_path.write_text(expected_env)
                console.print("[green]✅ Updated .env for live LLM[/green]")
            except Exception as e:
                console.print(f"[red]❌ Failed to update .env: {e}[/red]")
                return False
        return True

    console.print("[cyan]📝 Creating minimal .env for QA testing...[/cyan]")

    try:
        env_path.write_text(expected_env)
        console.print("[green]✅ Created minimal .env file[/green]")
        return True
    except Exception as e:
        console.print(f"[red]❌ Failed to create .env: {e}[/red]")
        return False


class APIServerManager:
    """Manages the API server lifecycle for testing."""

    def __init__(self, config: QAConfig, database_backend: str = "sqlite", modules: Optional[list] = None):
        """Initialize server manager.

        Args:
            config: QA runner configuration
            database_backend: Database backend to use ("sqlite" or "postgres")
            modules: Optional list of QAModule enums being tested
        """
        self.config = config
        self.database_backend = database_backend
        self.modules = modules or []
        self.console = Console()
        self.process: Optional[subprocess.Popen] = None
        self.pid: Optional[int] = None
        self.mock_logshipper: Optional[MockLogshipperServer] = None
        self._extracted_password: Optional[str] = None  # Dynamically extracted from server output

        # Per-backend output namespace. In parallel-backend mode both SQLITE
        # and POSTGRES backends would otherwise share `qa_reports/` and
        # collide on hash-keyed trace filenames — one backend's
        # `_clear_trace_files()` would delete the other's traces mid-run.
        # Logs are already namespaced by backend (logs/sqlite/, logs/postgres/);
        # mirror the same shape for trace output here.
        self._repo_root = Path(__file__).parent.parent.parent
        self.qa_reports_dir: Path = self._repo_root / "qa_reports" / self.database_backend
        # Mock logshipper port also needs per-backend offset so two backends
        # can both bind a receiver. sqlite=18080 (canonical), postgres=18081.
        self._mock_logshipper_port: int = 18080 if self.database_backend == "sqlite" else 18081

    def _clear_wakeup_state(self) -> bool:
        """Clear wakeup state from database for fresh wakeup run.

        Returns:
            True if cleared successfully or not needed, False on error
        """
        db_path = Path(__file__).parent.parent.parent / "data" / "ciris_engine.db"
        if not db_path.exists():
            return True  # No database yet

        try:
            import sqlite3

            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # Delete shared wakeup tasks and individual wakeup step tasks
            cursor.execute(
                """
                DELETE FROM tasks WHERE
                task_id LIKE '%WAKEUP%' OR
                task_id LIKE '%VERIFY_IDENTITY%' OR
                task_id LIKE '%VALIDATE_INTEGRITY%' OR
                task_id LIKE '%EVALUATE_RESILIENCE%' OR
                task_id LIKE '%ACCEPT_INCOMPLETENESS%' OR
                task_id LIKE '%EXPRESS_GRATITUDE%'
            """
            )
            tasks_deleted = cursor.rowcount

            # Delete related thoughts
            cursor.execute(
                """
                DELETE FROM thoughts WHERE
                source_task_id LIKE '%WAKEUP%' OR
                source_task_id LIKE '%VERIFY_IDENTITY%' OR
                source_task_id LIKE '%VALIDATE_INTEGRITY%' OR
                source_task_id LIKE '%EVALUATE_RESILIENCE%' OR
                source_task_id LIKE '%ACCEPT_INCOMPLETENESS%' OR
                source_task_id LIKE '%EXPRESS_GRATITUDE%'
            """
            )
            thoughts_deleted = cursor.rowcount

            conn.commit()
            conn.close()

            if tasks_deleted > 0 or thoughts_deleted > 0:
                self.console.print(
                    f"[cyan]🧹 Cleared wakeup state: {tasks_deleted} tasks, {thoughts_deleted} thoughts[/cyan]"
                )
            return True
        except Exception as e:
            self.console.print(f"[yellow]⚠️  Could not clear wakeup state: {e}[/yellow]")
            return True  # Continue anyway

    def _prune_lens_trace_dirs(self) -> None:
        """Retention sweep for `/tmp/qa-runner-lens-traces-*` dirs.

        Each live-lens QA run accumulates ~50-300MB of `accord-batch-*.json`
        files in its tee dir. Left unchecked the dirs build up — saw
        60MB-free-of-935GB on 2026-05-03 from ~30 accumulated dirs blocking
        the next run. Called before creating this run's dir so we land at
        N most recent (default 5) inclusive of the about-to-be-created dir.

        Operator override via env var `CIRIS_QA_LENS_TRACE_KEEP_N` (int);
        set to 0 to disable retention entirely (e.g. when bisecting across
        many runs and you need every dir on hand).

        Best-effort: any per-dir delete failure is swallowed so the QA run
        is never blocked by retention bookkeeping.
        """
        import glob as _glob
        import os as _os
        import shutil as _shutil

        try:
            keep_n = int(_os.environ.get("CIRIS_QA_LENS_TRACE_KEEP_N", "5"))
        except (TypeError, ValueError):
            keep_n = 5
        if keep_n <= 0:
            return  # 0 disables retention; negative is treated as disabled

        # We're about to create a new dir — keep keep_n - 1 of the existing
        # ones so the steady-state population sits at exactly keep_n.
        existing_keep = max(0, keep_n - 1)

        candidates = _glob.glob("/tmp/qa-runner-lens-traces-*")
        # Sort by mtime, newest first; mtime is stable across renames and
        # works even when the timestamp suffix in the dir name diverges
        # from creation time (e.g. operator-overridden CIRIS_ACCORD_METRICS_
        # LOCAL_COPY_DIR or copies from another machine).
        candidates.sort(key=lambda p: _os.path.getmtime(p), reverse=True)

        to_drop = candidates[existing_keep:]
        if not to_drop:
            return

        dropped = 0
        for path in to_drop:
            try:
                if _os.path.isdir(path):
                    _shutil.rmtree(path)
                    dropped += 1
            except OSError:
                # Permission denied / busy / already removed — leave it for
                # next sweep, never block the run.
                pass
        if dropped:
            self.console.print(
                f"[dim]🧹 Pruned {dropped} old lens-trace dir(s); keeping "
                f"{existing_keep} prior + the new run = {keep_n} total. "
                f"(override via CIRIS_QA_LENS_TRACE_KEEP_N)[/dim]"
            )

    def _clear_trace_files(self) -> None:
        """Clear existing trace files for fresh capture.

        Only clears THIS backend's trace dir. Under --parallel-backends each
        backend has its own qa_reports/<backend>/ namespace, so clearing
        one can't delete the other's in-flight traces.

        Also sweeps any legacy traces left at qa_reports/ root (pre-2.7.8
        single-backend layout) so they don't accumulate across upgrades.
        """
        # Per-backend dir
        if self.qa_reports_dir.exists():
            trace_files = list(self.qa_reports_dir.glob("real_trace_*.json")) + list(
                self.qa_reports_dir.glob("trace_*.json")
            )
            for f in trace_files:
                f.unlink()
            if trace_files:
                self.console.print(
                    f"[cyan]🧹 Cleared {len(trace_files)} old trace files in "
                    f"qa_reports/{self.database_backend}/[/cyan]"
                )

        # Legacy root-level traces from older single-backend runs — only the
        # FIRST backend to enter start() will have these to clear; subsequent
        # parallel backends find nothing.
        legacy_root = self._repo_root / "qa_reports"
        if legacy_root.exists():
            legacy_files = list(legacy_root.glob("real_trace_*.json")) + list(legacy_root.glob("trace_*.json"))
            for f in legacy_files:
                try:
                    f.unlink()
                except OSError:
                    pass  # Another parallel backend may have already removed it

    def start(self) -> bool:
        """Start the API server."""
        # Check if server is already running
        if self._is_server_running():
            self.console.print("[yellow]⚠️  Server already running[/yellow]")
            return True

        # For live mode, clear wakeup state for fresh 5-step wakeup
        if self.config.live_api_key:
            self._clear_wakeup_state()

        # Always clear trace files to ensure validation reflects current run
        self._clear_trace_files()

        # Ensure minimal .env exists for QA testing (respects mock_llm setting)
        if not _ensure_env_file(self.console, mock_llm=self.config.mock_llm):
            self.console.print("[red]❌ Failed to create .env - cannot proceed[/red]")
            return False

        # Auto-start PostgreSQL container if using postgres backend
        if self.database_backend == "postgres":
            if not _start_postgres_container(self.console):
                self.console.print("[red]❌ Failed to start PostgreSQL - cannot proceed[/red]")
                return False
            # Wipe PostgreSQL databases if --wipe-data is set
            if self.config.wipe_data:
                if not _wipe_postgres_databases(self.console):
                    self.console.print("[yellow]⚠️  PostgreSQL wipe failed, continuing anyway[/yellow]")

        # Start mock logshipper to receive accord traces (unless using live lens)
        if self.config.live_lens:
            self.console.print(
                "[cyan]📡 Using LIVE Lens server: https://lens.ciris-services-1.ai/lens-api/api/v1[/cyan]"
            )
            self.console.print("[cyan]📊 Enabling accord_metrics adapter for live trace capture[/cyan]")
            self.mock_logshipper = None
        else:
            # Per-backend port + per-backend output dir so parallel SQLITE
            # and POSTGRES runs don't collide on either the network port or
            # the trace filename (FSD scoring trace dedup uses a hash that
            # collides cross-backend; the backend dir is what disambiguates).
            self.mock_logshipper = MockLogshipperServer(
                port=self._mock_logshipper_port,
                output_dir=self.qa_reports_dir,
            )
            if self.mock_logshipper.start():
                self.console.print(
                    f"[cyan]📡 Mock logshipper started at {self.mock_logshipper.endpoint_url} "
                    f"→ qa_reports/{self.database_backend}/[/cyan]"
                )
            else:
                self.console.print("[yellow]⚠️  Could not start mock logshipper[/yellow]")
                self.mock_logshipper = None

        self.console.print("[cyan]🚀 Starting API server...[/cyan]")

        # Build command. When --from-staged is set, the server under test is
        # the wheel installed in the staged venv — that validates the SHIPPED
        # artifact passes QA, not just the dev tree. Otherwise default to
        # `sys.executable main.py` from the repo root.
        if self.config.staged_env is not None:
            cmd = [str(self.config.staged_env.ciris_server), "--port", str(self.config.api_port)]
            self.console.print(
                f"[dim]Using staged ciris-server: {self.config.staged_env.ciris_server}[/dim]"
            )
            self.console.print(
                f"[dim]Canonical tree hash: {self.config.staged_env.total_hash}[/dim]"
            )
        else:
            main_path = Path(__file__).parent.parent.parent / "main.py"
            cmd = [sys.executable, str(main_path), "--port", str(self.config.api_port)]

        if self.config.mock_llm:
            cmd.append("--mock-llm")

        # Set environment variables
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["CIRIS_TESTING_MODE"] = "true"  # Enable testing mode for admin user creation

        # Ensure CIRIS_MOCK_LLM matches our config (unset if not using mock)
        if not self.config.mock_llm:
            env.pop("CIRIS_MOCK_LLM", None)  # Remove if present

        # Set CIRIS_HOME for verifier_singleton (required for audit hash chain)
        if "CIRIS_HOME" not in env:
            project_root = Path(__file__).parent.parent.parent
            env["CIRIS_HOME"] = str(project_root)
            self.console.print(f"[dim]Setting CIRIS_HOME={project_root}[/dim]")

        # Set CIRIS_ADAPTER environment variable (supports comma-separated adapters)
        # This allows loading modular services like Reddit alongside built-in adapters
        env["CIRIS_ADAPTER"] = self.config.adapter

        # Live LLM configuration (--live flag)
        if self.config.live_api_key:
            # Override any mock LLM settings from .env
            env["CIRIS_MOCK_LLM"] = "false"

            # Set provider-specific environment variables
            # Auto-detect provider from base_url if not explicitly set
            provider = self.config.live_provider
            if not provider and self.config.live_base_url:
                base_url_lower = self.config.live_base_url.lower()
                if "openrouter.ai" in base_url_lower:
                    provider = "openrouter"
                elif "groq.com" in base_url_lower:
                    provider = "groq"
                elif "together" in base_url_lower:
                    provider = "together"
                else:
                    provider = "openai_compatible"
            provider = provider or "openai"
            env["CIRIS_LLM_PROVIDER"] = provider

            # Set model name using CIRIS_LLM_MODEL_NAME (read by service_initializer for all providers)
            if self.config.live_model:
                env["CIRIS_LLM_MODEL_NAME"] = self.config.live_model
                self.console.print(f"[cyan]🤖 Live LLM: model={self.config.live_model}[/cyan]")

            if provider == "anthropic":
                env["ANTHROPIC_API_KEY"] = self.config.live_api_key
                self.console.print(f"[cyan]🔑 Live LLM: ANTHROPIC_API_KEY set (native Anthropic SDK)[/cyan]")
            elif provider == "google":
                env["GOOGLE_API_KEY"] = self.config.live_api_key
                self.console.print(f"[cyan]🔑 Live LLM: GOOGLE_API_KEY set (native Google SDK)[/cyan]")
            else:
                # OpenAI or OpenAI-compatible (Groq, OpenRouter, etc.)
                env["OPENAI_API_KEY"] = self.config.live_api_key
                self.console.print(f"[cyan]🔑 Live LLM: OPENAI_API_KEY set (overriding mock)[/cyan]")
                if self.config.live_base_url:
                    env["OPENAI_API_BASE"] = self.config.live_base_url
                    self.console.print(f"[cyan]🌐 Live LLM: OPENAI_API_BASE={self.config.live_base_url}[/cyan]")

        # Configure accord_metrics adapter to use mock logshipper
        if self.mock_logshipper:
            env["CIRIS_ACCORD_METRICS_ENDPOINT"] = self.mock_logshipper.endpoint_url

        # When running in --live mode, opt the agent into location sharing in
        # accord traces so lens dashboards can correlate by region. Defaults
        # to the dev's home base (Schaumburg, IL) and can be overridden by
        # exporting the CIRIS_USER_* vars before invocation.
        if self.config.live_api_key:
            env.setdefault("CIRIS_SHARE_LOCATION_IN_TRACES", "true")
            env.setdefault("CIRIS_USER_LOCATION", "Schaumburg, Illinois, USA")
            env.setdefault("CIRIS_USER_TIMEZONE", "America/Chicago")
            env.setdefault("CIRIS_USER_LATITUDE", "42.0334")
            env.setdefault("CIRIS_USER_LONGITUDE", "-88.0834")
            self.console.print(
                f"[dim]Live mode: location sharing enabled "
                f"(CIRIS_USER_LOCATION={env['CIRIS_USER_LOCATION']})[/dim]"
            )

        # Force first-run mode for SETUP module tests or when data was wiped
        from .config import QAModule

        if any(m == QAModule.SETUP for m in self.modules):
            env["CIRIS_FORCE_FIRST_RUN"] = "1"
            self.console.print("[dim]Setting CIRIS_FORCE_FIRST_RUN=1 for SETUP module tests[/dim]")
        elif self.config.wipe_data:
            # When data is wiped, we need first-run to allow setup completion
            env["CIRIS_FORCE_FIRST_RUN"] = "1"
            self.console.print("[dim]Setting CIRIS_FORCE_FIRST_RUN=1 for wiped data[/dim]")

        # Module-level SERVER_ENV contributions. Each selected module can
        # declare a SERVER_ENV class attribute that gets merged into the
        # agent process env. See tools/qa_runner/modules/_module_metadata.py
        # for the contract. Modules currently declaring SERVER_ENV:
        # MODEL_EVAL, PARALLEL_LOCALES, SAFETY_BATTERY (CIRIS_DISABLE_TASK_APPEND
        # + concurrent-burst tuning for the first two; task-append disable
        # only for the safety-battery sequential-in-shared-channel pattern).
        from .modules._module_metadata import merge_server_env

        merged = merge_server_env(self.modules)
        conflicts = merged.pop("__conflicts__", "")
        for k, v in merged.items():
            # setdefault so an operator can still override any of these via
            # an explicit env var (e.g. for debugging or one-off CI runs).
            env.setdefault(k, v)
        if merged:
            modules_label = ",".join(m.value for m in self.modules
                                     if any(merge_server_env([m]).keys() - {"__conflicts__"}))
            self.console.print(
                f"[dim]Merged module SERVER_ENV from {modules_label or 'selected modules'}: "
                f"{merged}[/dim]"
            )
        if conflicts:
            self.console.print(
                f"[yellow]SERVER_ENV conflicts across modules (last-write-wins): "
                f"{conflicts}[/yellow]"
            )

        # Set backend-specific log directory to avoid symlink collisions
        # But preserve existing CIRIS_LOG_DIR if set (for multi-occurrence)
        if "CIRIS_LOG_DIR" in env:
            log_dir = env["CIRIS_LOG_DIR"]
            self.console.print(f"[dim]Log directory: {log_dir} (from environment)[/dim]")
        else:
            log_dir = f"logs/{self.database_backend}"
            env["CIRIS_LOG_DIR"] = log_dir
            self.console.print(f"[dim]Log directory: {log_dir}[/dim]")

        # Set database URL based on backend
        if self.database_backend == "postgres":
            env["CIRIS_DB_URL"] = self.config.postgres_url
            self.console.print(f"[dim]Using PostgreSQL: {self.config.postgres_url.split('@')[0]}@...[/dim]")
        else:
            # SQLite is the default, no need to set CIRIS_DB_URL
            self.console.print(f"[dim]Using SQLite (default)[/dim]")

        # Set billing configuration from QAConfig if enabled
        if self.config.billing_enabled:
            env["CIRIS_BILLING_ENABLED"] = "true"
            if self.config.billing_api_key:
                env["CIRIS_BILLING_API_KEY"] = self.config.billing_api_key
                self.console.print(f"[dim]Setting CIRIS_BILLING_ENABLED=true[/dim]")
                self.console.print(f"[dim]Setting CIRIS_BILLING_API_KEY=<redacted>[/dim]")
            if self.config.billing_api_url:
                env["CIRIS_BILLING_API_URL"] = self.config.billing_api_url
                self.console.print(f"[dim]Setting CIRIS_BILLING_API_URL={self.config.billing_api_url}[/dim]")

        # Pass through additional billing configuration from environment if present
        billing_vars = [
            "CIRIS_BILLING_TIMEOUT_SECONDS",
            "CIRIS_BILLING_CACHE_TTL_SECONDS",
            "CIRIS_BILLING_FAIL_OPEN",
        ]
        for var in billing_vars:
            if var in os.environ:
                env[var] = os.environ[var]
                self.console.print(f"[dim]Setting {var}={os.environ[var]}[/dim]")

        # Load SQL external data service configuration if needed
        if hasattr(self, "_sql_config_path") and self._sql_config_path:
            env["CIRIS_SQL_EXTERNAL_DATA_CONFIG"] = str(self._sql_config_path)
            self.console.print(f"[dim]Configured SQL external data service: {self._sql_config_path}[/dim]")

        # HE-300 benchmark: Use the he-300-benchmark template (limits actions, no ponder)
        if any(m == QAModule.HE300_BENCHMARK for m in self.modules):
            env["CIRIS_TEMPLATE"] = "he-300-benchmark"
            # CRITICAL: Enable benchmark mode (double-lock with template check in component_builder.py)
            # This disables EpistemicHumilityConscience which triggers PONDER (not allowed in HE-300)
            env["CIRIS_BENCHMARK_MODE"] = "true"
            # Increase A2A timeout for live LLM (default 60s is too short)
            a2a_timeout = "180" if self.config.live_api_key else "60"
            env["CIRIS_A2A_TIMEOUT"] = a2a_timeout
            self.console.print("[cyan]🧪 HE-300 Benchmark Configuration:[/cyan]")
            self.console.print("[dim]   Template: he-300-benchmark (limited actions: speak, task_complete)[/dim]")
            self.console.print("[dim]   Benchmark Mode: ENABLED (EpistemicHumility conscience disabled)[/dim]")
            self.console.print(f"[dim]   A2A Timeout: {a2a_timeout}s[/dim]")
            self.console.print(f"[dim]   Mock LLM: {self.config.mock_llm}[/dim]")
            self.console.print(f"[dim]   Live API Key: {'Set' if self.config.live_api_key else 'Not set'}[/dim]")
            self.console.print(f"[dim]   Live Model: {self.config.live_model or 'Not set'}[/dim]")
            self.console.print(f"[dim]   CIRIS_MOCK_LLM env: {env.get('CIRIS_MOCK_LLM', 'Not set')}[/dim]")
            self.console.print(f"[dim]   CIRIS_LLM_PROVIDER env: {env.get('CIRIS_LLM_PROVIDER', 'Not set')}[/dim]")

        # Enable accord_metrics adapter when explicitly testing traces, when using live Lens,
        # or during live model eval where we want a full multilingual research export.
        accord_metrics_requested = any(m == QAModule.ACCORD_METRICS for m in self.modules)
        model_eval_requested = any(m == QAModule.MODEL_EVAL for m in self.modules)
        accord_metrics_enabled = accord_metrics_requested or model_eval_requested or self.config.live_lens
        if accord_metrics_enabled:
            # Load base accord_metrics adapter alongside the main adapter
            if "ciris_accord_metrics" not in env.get("CIRIS_ADAPTER", ""):
                current_adapter = env.get("CIRIS_ADAPTER", "api")
                env["CIRIS_ADAPTER"] = f"{current_adapter},ciris_accord_metrics"
            # Enable consent for trace capture - REQUIRED for CIRISLens API
            env["CIRIS_ACCORD_METRICS_CONSENT"] = "true"
            env["CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP"] = "2025-01-01T00:00:00Z"
            # Use short flush interval for QA (5 seconds instead of 60)
            env["CIRIS_ACCORD_METRICS_FLUSH_INTERVAL"] = "5"
            # Keep the startup adapter at generic so model-eval can explicitly register
            # the detailed and full_traces adapters after auth. That yields exactly three
            # active accord_metrics instances: generic, detailed, full_traces.
            trace_level = "generic" if model_eval_requested else "detailed"
            env["CIRIS_ACCORD_METRICS_TRACE_LEVEL"] = trace_level
            # Set live lens endpoint explicitly
            if self.config.live_lens:
                env["CIRIS_ACCORD_METRICS_ENDPOINT"] = "https://lens.ciris-services-1.ai/lens-api/api/v1"
                # Local-tee for live-lens runs: write every batch payload that
                # gets POSTed to the lens to a per-run /tmp directory in
                # parallel. Gives us an audit copy + feeds the persist engine
                # real test data for the new wire-format ingest path. Default
                # path: /tmp/qa-runner-lens-traces-<utc-iso>/. Operators can
                # override by setting CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR
                # before launching the QA runner.
                if "CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR" not in env:
                    from datetime import datetime, timezone

                    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                    env["CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR"] = f"/tmp/qa-runner-lens-traces-{ts}"
                    # Retention: keep only the most recent N=5 prior dirs
                    # before creating this run's. Lens trace dirs accumulate
                    # at ~50-300MB each — left unchecked they fill /tmp and
                    # crash the host (saw 60M-free-of-935G on 2026-05-03).
                    # Operator override via CIRIS_QA_LENS_TRACE_KEEP_N.
                    self._prune_lens_trace_dirs()
            self.console.print(
                f"[dim]Enabling accord_metrics adapter with consent for trace capture ({trace_level})[/dim]"
            )
            self.console.print(f"[dim]   CIRIS_ACCORD_METRICS_CONSENT={env['CIRIS_ACCORD_METRICS_CONSENT']}[/dim]")
            self.console.print(
                f"[dim]   CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP={env['CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP']}[/dim]"
            )
            self.console.print(f"[dim]   CIRIS_ACCORD_METRICS_TRACE_LEVEL={trace_level}[/dim]")
            if self.config.live_lens:
                self.console.print(
                    f"[dim]   CIRIS_ACCORD_METRICS_ENDPOINT={env['CIRIS_ACCORD_METRICS_ENDPOINT']}[/dim]"
                )
                self.console.print(
                    f"[dim]   CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR={env['CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR']}[/dim]"
                )

        # Load Reddit credentials if Reddit adapter is being used
        if "reddit" in self.config.adapter.lower():
            reddit_secrets_path = Path.home() / ".ciris" / "reddit_secrets"
            if reddit_secrets_path.exists():
                try:
                    # Parse Reddit secrets file (format: KEY="value")
                    with open(reddit_secrets_path, "r") as f:
                        for line in f:
                            line = line.strip()
                            if not line or line.startswith("#"):
                                continue
                            if "=" in line:
                                key, value = line.split("=", 1)
                                # Remove quotes from value
                                value = value.strip().strip('"').strip("'")
                                env[key] = value
                    self.console.print("[dim]Loaded Reddit credentials from ~/.ciris/reddit_secrets[/dim]")
                except Exception as e:
                    self.console.print(f"[yellow]⚠️  Failed to load Reddit secrets: {e}[/yellow]")
            else:
                self.console.print(f"[yellow]⚠️  Reddit secrets file not found: {reddit_secrets_path}[/yellow]")

        # Start server process
        try:
            # Open log file to capture console output (includes early startup logs)
            # Save to logs/{backend}/ so it's discoverable alongside other logs
            log_dir_path = Path(f"logs/{self.database_backend}")
            log_dir_path.mkdir(parents=True, exist_ok=True)
            console_log_path = str(log_dir_path / "console.log")
            self._console_log_path = console_log_path  # Store for reference in error messages
            self.console.print(f"[dim]📝 Console log: {console_log_path}[/dim]")
            self.console.print(f"[dim]📝 CIRIS log: logs/{self.database_backend}/latest.log[/dim]")
            self.console.print(f"[dim]🚀 Command: {' '.join(cmd)}[/dim]")

            # Use PTY for stdout - the Rust FFI code crashes when stdout is not a TTY
            # This is a workaround for a bug in ciris_verify_ffi
            master_fd, slave_fd = pty.openpty()
            self._pty_master_fd = master_fd
            self._pty_slave_fd = slave_fd

            self.process = subprocess.Popen(
                cmd,
                stdout=slave_fd,
                stderr=slave_fd,
                stdin=slave_fd,
                env=env,
                cwd=Path.cwd(),
            )
            os.close(slave_fd)  # Close slave fd in parent
            self.pid = self.process.pid
            self.console.print(f"[dim]   PID: {self.pid}[/dim]")

            # Start background thread to read from PTY master and write to log file
            console_log = open(console_log_path, "w")
            self._console_log_file = console_log

            def log_reader():
                try:
                    while True:
                        try:
                            data = os.read(master_fd, 4096)
                            if not data:
                                break
                            text = data.decode("utf-8", errors="replace")
                            console_log.write(text)
                            console_log.flush()
                        except OSError:
                            break
                except Exception:
                    pass

            log_thread = threading.Thread(target=log_reader, daemon=True)
            log_thread.start()
            self._log_thread = log_thread

            # Wait for server to be ready
            if self._wait_for_server():
                self.console.print("[green]✅ API server started successfully[/green]")
                return True
            else:
                self.console.print("[red]❌ Server failed to start[/red]")
                self.stop()
                return False

        except Exception as e:
            self.console.print(f"[red]❌ Error starting server: {e}[/red]")
            return False

    def stop(self):
        """Stop the API server."""
        if self.process:
            self.console.print("[cyan]🛑 Stopping API server...[/cyan]")

            try:
                # Try graceful shutdown first
                self.process.terminate()

                # Wait up to 15 seconds for graceful shutdown (agent needs time for shutdown state processing)
                try:
                    self.process.wait(timeout=15)
                    self.console.print("[green]✅ Server stopped gracefully[/green]")
                except subprocess.TimeoutExpired:
                    # Force kill if needed
                    self.process.kill()
                    self.console.print("[yellow]⚠️  Server force killed[/yellow]")

                self.process = None
                self.pid = None

                # Close PTY master fd
                if hasattr(self, "_pty_master_fd"):
                    try:
                        os.close(self._pty_master_fd)
                    except Exception:
                        pass

                # Close console log file
                if hasattr(self, "_console_log_file"):
                    try:
                        self._console_log_file.close()
                    except Exception:
                        pass

            except Exception as e:
                self.console.print(f"[red]Error stopping server: {e}[/red]")

        # Stop mock logshipper and report received traces
        if self.mock_logshipper:
            received = self.mock_logshipper.get_received_traces()
            self.mock_logshipper.stop()
            if received:
                self.console.print(f"[green]📥 Mock logshipper received {len(received)} traces:[/green]")
                for trace in received:
                    self.console.print(f"   • {trace['task_name']}: {trace['filepath']}")
            self.mock_logshipper = None

        # Skip port cleanup - it's causing hangs

    def _is_server_running(self) -> bool:
        """Check if server is running on the configured port."""
        try:
            response = requests.get(f"{self.config.base_url}/v1/system/health", timeout=2)
            return response.status_code == 200
        except:
            return False

    def _extract_password_from_log(self) -> Optional[str]:
        """Extract the dynamically generated admin password from console log.

        The server prints the password in this format:
        ======================================================================
        FIRST-RUN FALLBACK ADMIN CREDENTIALS (use to complete setup wizard):
          Username: admin
          Password: <random_password>
        ======================================================================

        Returns:
            Extracted password string, or None if not found
        """
        console_log_path = getattr(self, "_console_log_path", None)
        if not console_log_path:
            return None

        try:
            with open(console_log_path, "r") as f:
                content = f.read()

            # Look for the password line
            import re

            match = re.search(r"Password:\s*(\S+)", content)
            if match:
                password = match.group(1)
                self.console.print(f"[dim]🔑 Extracted dynamic admin password from console log[/dim]")
                return password
        except Exception as e:
            self.console.print(f"[yellow]⚠️  Could not extract password from log: {e}[/yellow]")

        return None

    def get_admin_password(self) -> str:
        """Get the admin password to use for authentication.

        Returns extracted password (from setup) or config default.
        Since QA runner always wipes data and uses setup wizard,
        the password is always the known test password.
        """
        if self._extracted_password:
            return self._extracted_password
        return self.config.admin_password

    def _complete_qa_setup(self) -> bool:
        """Complete setup wizard to create test user when data was wiped.

        This is called when --wipe-data is used to create a known test user
        before attempting authentication.
        """
        self.console.print("[cyan]🔧 Completing setup to create test user...[/cyan]")

        # Use the config's admin credentials and LLM settings
        # When in live mode, use the real API key; otherwise use a placeholder
        llm_provider = self.config.live_provider or "openai"
        llm_api_key = self.config.live_api_key or "test-key-for-qa"
        llm_model = self.config.live_model or "gpt-4"
        llm_base_url = self.config.live_base_url

        # template_id is configurable per-module. Default "default" preserves
        # historical behavior (Ally persona). safety_battery sets it via
        # --safety-battery-template so the result-key tuple per
        # cirisnodecore/FSD/SAFETY_BATTERY_CI_LOOP.md §2 carries the template.
        template_id = getattr(self.config, "setup_template_id", None) or "default"
        setup_payload = {
            "llm_provider": llm_provider,
            "llm_api_key": llm_api_key,
            "llm_model": llm_model,
            "template_id": template_id,
            "enabled_adapters": ["api"],
            "adapter_config": {},
            "admin_username": self.config.admin_username,
            "admin_password": self.config.admin_password,
            "agent_port": self.config.api_port,
        }
        # Add base URL for OpenAI-compatible providers
        if llm_base_url:
            setup_payload["llm_base_url"] = llm_base_url

        self.console.print(
            "[dim]Setup payload summary: "
            f"provider={llm_provider}, model={llm_model}, base_url={'set' if llm_base_url else 'unset'}, "
            f"username={self.config.admin_username}, port={self.config.api_port}, "
            f"adapters={','.join(setup_payload['enabled_adapters'])}[/dim]"
        )

        try:
            response = requests.post(
                f"{self.config.base_url}/v1/setup/complete",
                json=setup_payload,
                timeout=30,
            )
            if response.status_code == 200:
                self.console.print("[green]✅ Setup completed, test user created[/green]")
                try:
                    response_json = response.json()
                    message = response_json.get("data", {}).get("message")
                    next_steps = response_json.get("data", {}).get("next_steps")
                    if message:
                        self.console.print(f"[dim]Setup response: {message}[/dim]")
                    if next_steps:
                        self.console.print(f"[dim]Next steps: {next_steps}[/dim]")
                except Exception:
                    self.console.print("[dim]Setup completed but response body was not parseable JSON[/dim]")
                # Store the password we used
                self._extracted_password = setup_payload["admin_password"]
                return True
            else:
                self.console.print(f"[red]❌ Setup failed: {response.status_code} - {response.text[:200]}[/red]")
                self._report_first_run_diagnostics("setup-complete failed")
                return False
        except Exception as e:
            self.console.print(f"[red]❌ Setup error: {e}[/red]")
            self._report_first_run_diagnostics("setup-complete request raised exception")
            return False

    def _fetch_json(self, path: str, timeout: float = 3.0, headers: Optional[Dict[str, str]] = None) -> Optional[Dict]:
        """Fetch a JSON response for diagnostics."""
        try:
            response = requests.get(f"{self.config.base_url}{path}", headers=headers, timeout=timeout)
            try:
                payload = response.json()
            except Exception:
                payload = {"raw_text": response.text[:500]}
            return {"status_code": response.status_code, "payload": payload}
        except Exception as exc:
            return {"error": str(exc)}

    def _report_first_run_diagnostics(self, reason: str, token: Optional[str] = None) -> None:
        """Emit setup/runtime diagnostics when first-run bootstrap gets stuck."""
        self.console.print(f"[yellow]🔎 First-run diagnostics: {reason}[/yellow]")

        setup_status = self._fetch_json("/v1/setup/status")
        if setup_status:
            self.console.print(f"[dim]  /v1/setup/status: {setup_status}[/dim]")

        headers = {"Authorization": f"Bearer {token}"} if token else None
        agent_status = self._fetch_json("/v1/agent/status", headers=headers)
        if agent_status:
            self.console.print(f"[dim]  /v1/agent/status: {agent_status}[/dim]")

        system_status = self._fetch_json("/v1/system/status", headers=headers)
        if system_status:
            self.console.print(f"[dim]  /v1/system/status: {system_status}[/dim]")

        console_log_path = getattr(self, "_console_log_path", None)
        if console_log_path and Path(console_log_path).exists():
            try:
                recent = Path(console_log_path).read_text(errors="ignore").splitlines()[-20:]
                self.console.print("[dim]  Recent console log:[/dim]")
                for line in recent:
                    self.console.print(f"[dim]    {line[:220]}[/dim]")
            except Exception as exc:
                self.console.print(f"[dim]  Could not read console log: {exc}[/dim]")

    def _wait_for_server(self) -> bool:
        """Wait for server to be ready and reach WORK state."""
        from .config import QAModule

        start_time = time.time()

        # First, wait for server to respond to health checks
        while time.time() - start_time < self.config.server_startup_timeout:
            # Check if process is still alive
            if self.process and self.process.poll() is not None:
                # Process died - read error from console log file
                exit_code = self.process.returncode
                error_output = ""
                console_log_path = getattr(self, "_console_log_path", f"logs/{self.database_backend}/console.log")
                try:
                    with open(console_log_path, "r") as f:
                        # Read last 1000 chars to find error
                        f.seek(0, 2)  # Seek to end
                        size = f.tell()
                        f.seek(max(0, size - 2000))
                        error_output = f.read()
                except Exception:
                    pass
                self.console.print(f"[red]❌ Server process died (exit code: {exit_code})[/red]")
                self.console.print(f"[yellow]🔍 Troubleshooting info:[/yellow]")
                self.console.print(f"[dim]   Console log: {console_log_path}[/dim]")
                self.console.print(f"[dim]   CIRIS log: logs/{self.database_backend}/latest.log[/dim]")
                self.console.print(f"[dim]   Incidents: logs/{self.database_backend}/incidents_latest.log[/dim]")
                if error_output:
                    # Show last few lines of output
                    lines = error_output.strip().split("\n")[-15:]
                    self.console.print(f"[red]Last console output:[/red]")
                    for line in lines:
                        self.console.print(f"[dim]{line}[/dim]")
                # Also check incidents log
                incidents_log = Path(f"logs/{self.database_backend}/incidents_latest.log")
                if incidents_log.exists():
                    try:
                        with open(incidents_log, "r") as f:
                            incidents = f.read()
                            error_lines = [l for l in incidents.split("\n") if "ERROR" in l or "CRITICAL" in l]
                            if error_lines:
                                self.console.print(f"[red]Errors from incidents log:[/red]")
                                for line in error_lines[-5:]:
                                    self.console.print(f"[dim]{line[:200]}[/dim]")
                    except Exception:
                        pass
                return False

            # Check if server is responding
            if self._is_server_running():
                break

            time.sleep(1)
        else:
            # Timeout waiting for health check
            return False

        # Extract dynamically generated password from console log
        # This is needed because the admin password is now randomly generated per process
        extracted_pwd = self._extract_password_from_log()
        if extracted_pwd:
            self._extracted_password = extracted_pwd

        # If data was wiped, complete setup to create test user before authenticating
        if self.config.wipe_data:
            if not self._complete_qa_setup():
                return False
            self.console.print("[cyan]⏳ Waiting for setup-triggered runtime resume...[/cyan]")
            time.sleep(1.0)

        # Modules that validate first-run/API configuration flows do not require
        # the agent processor to advertise WORK before they can proceed, but
        # they still need the setup wizard completed so authentication works.
        if QAModule.SETUP in self.modules or QAModule.HOMEASSISTANT_AGENTIC in self.modules:
            self.console.print("[green]✅ Server ready for first-run/API configuration tests[/green]")
            return True

        # Now wait for agent to reach WORK state
        self.console.print("[cyan]⏳ Waiting for agent to reach WORK state...[/cyan]")

        # Get auth token for checking cognitive state
        # Use dynamically extracted password if available, otherwise fall back to config
        admin_password = self.get_admin_password()
        token = None
        try:
            auth_response = requests.post(
                f"{self.config.base_url}/v1/auth/login",
                json={"username": self.config.admin_username, "password": admin_password},
                timeout=5,
            )
            if auth_response.status_code == 200:
                token = auth_response.json()["access_token"]
            else:
                self.console.print(
                    f"[red]❌ Authentication failed: {auth_response.status_code} - {auth_response.text[:100]}[/red]"
                )
                self.console.print("[yellow]Hint: Try --wipe-data to clear stale state, or check credentials[/yellow]")
                self._report_first_run_diagnostics("post-setup authentication failed")
                return False  # Exit immediately on auth failure
        except Exception as e:
            self.console.print(f"[red]❌ Authentication error: {e}[/red]")
            self._report_first_run_diagnostics("post-setup authentication raised exception")
            return False  # Exit immediately on auth error

        last_reported_state = ""
        last_state_report_at = 0.0
        while time.time() - start_time < self.config.server_startup_timeout:
            try:
                headers = {}
                if token:
                    headers["Authorization"] = f"Bearer {token}"

                response = requests.get(f"{self.config.base_url}/v1/agent/status", headers=headers, timeout=2)
                if response.status_code == 200:
                    data = response.json()
                    # Get cognitive_state from data object
                    cognitive_state = data.get("data", {}).get("cognitive_state", "")

                    # Check for WORK state (handle both "work" and "AgentState.WORK" enum string)
                    state_lower = cognitive_state.lower() if cognitive_state else ""
                    is_work = (
                        state_lower == "work" or state_lower == "agentstate.work" or cognitive_state.endswith(".WORK")
                    )

                    if is_work:
                        self.console.print(f"[green]✅ Agent reached WORK state[/green]")
                        return True

                    # Show current state (clear the line properly)
                    if cognitive_state:
                        # Use \r to overwrite previous line
                        self.console.print(f"[dim]Current state: {cognitive_state:<30}[/dim]", end="\r")
                        now = time.time()
                        if cognitive_state != last_reported_state or now - last_state_report_at >= 5.0:
                            self.console.print(f"[dim]State poll: cognitive_state={cognitive_state}[/dim]")
                            last_reported_state = cognitive_state
                            last_state_report_at = now
            except Exception:
                pass

            time.sleep(1)

        self.console.print("[yellow]⚠️  Agent did not reach WORK state in time[/yellow]")
        self._report_first_run_diagnostics("agent never reached WORK", token=token)
        return False

    def _kill_by_port(self):
        """Kill any process using the configured port."""
        import signal
        from contextlib import contextmanager

        @contextmanager
        def timeout(seconds):
            def timeout_handler(signum, frame):
                raise TimeoutError()

            # Set the timeout handler
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(seconds)
            try:
                yield
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

        try:
            with timeout(2):  # 2 second timeout for port cleanup
                for conn in psutil.net_connections():
                    if conn.laddr.port == self.config.api_port and conn.status == "LISTEN":
                        try:
                            process = psutil.Process(conn.pid)
                            process.terminate()
                            self.console.print(
                                f"[yellow]Killed process {conn.pid} on port {self.config.api_port}[/yellow]"
                            )
                        except:
                            pass
        except TimeoutError:
            self.console.print("[yellow]⚠️  Port cleanup timed out[/yellow]")
        except:
            pass
