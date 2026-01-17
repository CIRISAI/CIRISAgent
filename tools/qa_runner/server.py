"""
API server management for QA testing.
"""

import asyncio
import hashlib
import json
import os
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

# ============================================================================
# Mock Logshipper Server - Receives covenant traces from agents
# ============================================================================


class MockLogshipperHandler(BaseHTTPRequestHandler):
    """HTTP handler for mock logshipper that receives covenant traces."""

    # Class-level storage for received traces
    received_traces: List[Dict[str, Any]] = []
    output_dir: Optional[Path] = None

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default logging."""
        pass

    def do_POST(self) -> None:
        """Handle POST requests to /v1/covenant/events or /covenant/events."""
        if self.path in ("/v1/covenant/events", "/covenant/events"):
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
        """Save a trace to file with task-based name."""
        if not self.output_dir:
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
        filepath = self.output_dir / filename

        with open(filepath, "w") as f:
            json.dump(trace, f, indent=2, default=str)

        MockLogshipperHandler.received_traces.append(
            {
                "task_name": task_name,
                "filepath": str(filepath),
                "components": len(components),
            }
        )


class MockLogshipperServer:
    """Mock logshipper server that receives and saves covenant traces."""

    def __init__(self, port: int = 18080, output_dir: Optional[Path] = None):
        """Initialize mock server.

        Args:
            port: Port to listen on
            output_dir: Directory to save traces to
        """
        self.port = port
        self.output_dir = output_dir or Path(__file__).parent.parent.parent / "qa_reports"
        self.output_dir.mkdir(exist_ok=True)
        self.server: Optional[HTTPServer] = None
        self.thread: Optional[threading.Thread] = None

        # Configure handler
        MockLogshipperHandler.output_dir = self.output_dir
        MockLogshipperHandler.received_traces = []

    def start(self) -> bool:
        """Start the mock server in a background thread."""
        try:
            self.server = HTTPServer(("127.0.0.1", self.port), MockLogshipperHandler)
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
        """Get list of received traces."""
        return MockLogshipperHandler.received_traces.copy()

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

    def _clear_trace_files(self) -> None:
        """Clear existing trace files for fresh capture."""
        qa_reports = Path(__file__).parent.parent.parent / "qa_reports"
        if qa_reports.exists():
            # Clear both old format (real_trace_*) and new format (trace_*)
            trace_files = list(qa_reports.glob("real_trace_*.json")) + list(qa_reports.glob("trace_*.json"))
            for f in trace_files:
                f.unlink()
            if trace_files:
                self.console.print(f"[cyan]🧹 Cleared {len(trace_files)} old trace files[/cyan]")

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

        # Start mock logshipper to receive covenant traces
        self.mock_logshipper = MockLogshipperServer(port=18080)
        if self.mock_logshipper.start():
            self.console.print(f"[cyan]📡 Mock logshipper started at {self.mock_logshipper.endpoint_url}[/cyan]")
        else:
            self.console.print("[yellow]⚠️  Could not start mock logshipper[/yellow]")
            self.mock_logshipper = None

        self.console.print("[cyan]🚀 Starting API server...[/cyan]")

        # Build command - main.py is in the root directory
        main_path = Path(__file__).parent.parent.parent / "main.py"
        cmd = [sys.executable, str(main_path), "--port", str(self.config.api_port)]

        if self.config.mock_llm:
            cmd.append("--mock-llm")

        # Set environment variables
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        # Set CIRIS_ADAPTER environment variable (supports comma-separated adapters)
        # This allows loading modular services like Reddit alongside built-in adapters
        env["CIRIS_ADAPTER"] = self.config.adapter

        # Live LLM configuration (--live flag)
        if self.config.live_api_key:
            env["OPENAI_API_KEY"] = self.config.live_api_key
            self.console.print(f"[cyan]🔑 Live LLM: OPENAI_API_KEY set[/cyan]")
        if self.config.live_base_url:
            env["OPENAI_API_BASE"] = self.config.live_base_url
            self.console.print(f"[cyan]🌐 Live LLM: OPENAI_API_BASE={self.config.live_base_url}[/cyan]")
        if self.config.live_model:
            env["OPENAI_MODEL_NAME"] = self.config.live_model
            self.console.print(f"[cyan]🤖 Live LLM: OPENAI_MODEL_NAME={self.config.live_model}[/cyan]")

        # Configure covenant_metrics adapter to use mock logshipper
        if self.mock_logshipper:
            env["CIRIS_COVENANT_METRICS_ENDPOINT"] = self.mock_logshipper.endpoint_url

        # Force first-run mode for SETUP module tests
        from .config import QAModule

        if any(m == QAModule.SETUP for m in self.modules):
            env["CIRIS_FORCE_FIRST_RUN"] = "1"
            self.console.print("[dim]Setting CIRIS_FORCE_FIRST_RUN=1 for SETUP module tests[/dim]")

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

        # Enable covenant_metrics adapter with consent for trace capture tests
        if any(m == QAModule.COVENANT_METRICS for m in self.modules):
            # Load the covenant_metrics adapter alongside the main adapter
            if "ciris_covenant_metrics" not in env.get("CIRIS_ADAPTER", ""):
                current_adapter = env.get("CIRIS_ADAPTER", "api")
                env["CIRIS_ADAPTER"] = f"{current_adapter},ciris_covenant_metrics"
            # Enable consent for trace capture
            env["CIRIS_COVENANT_METRICS_CONSENT"] = "true"
            env["CIRIS_COVENANT_METRICS_CONSENT_TIMESTAMP"] = "2025-01-01T00:00:00Z"
            # Use short flush interval for QA (5 seconds instead of 60)
            env["CIRIS_COVENANT_METRICS_FLUSH_INTERVAL"] = "5"
            self.console.print("[dim]Enabling covenant_metrics adapter with consent for trace capture[/dim]")

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
            # Use backend-specific console log to avoid conflicts in parallel mode
            console_log_path = f"/tmp/qa_runner_console_{self.database_backend}_{self.config.api_port}.txt"
            console_log = open(console_log_path, "w")
            self.process = subprocess.Popen(cmd, stdout=console_log, stderr=subprocess.STDOUT, env=env, cwd=Path.cwd())
            self.pid = self.process.pid
            self._console_log_file = console_log  # Store reference to close later

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

                # Close console log file
                if hasattr(self, "_console_log_file"):
                    try:
                        self._console_log_file.close()
                    except:
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
                console_log_path = f"/tmp/qa_runner_console_{self.database_backend}_{self.config.api_port}.txt"
                try:
                    with open(console_log_path, "r") as f:
                        # Read last 1000 chars to find error
                        f.seek(0, 2)  # Seek to end
                        size = f.tell()
                        f.seek(max(0, size - 2000))
                        error_output = f.read()
                except Exception:
                    pass
                self.console.print(f"[red]Server process died (exit code: {exit_code})[/red]")
                if error_output:
                    # Show last few lines of output
                    lines = error_output.strip().split("\n")[-10:]
                    self.console.print(f"[red]Last output:[/red]")
                    for line in lines:
                        self.console.print(f"[dim]{line}[/dim]")
                return False

            # Check if server is responding
            if self._is_server_running():
                break

            time.sleep(1)
        else:
            # Timeout waiting for health check
            return False

        # SETUP module: Skip WORK state check (first-run mode doesn't reach WORK)
        if QAModule.SETUP in self.modules:
            self.console.print("[green]✅ Server ready for SETUP tests (first-run mode)[/green]")
            return True

        # Now wait for agent to reach WORK state
        self.console.print("[cyan]⏳ Waiting for agent to reach WORK state...[/cyan]")

        # Get auth token for checking cognitive state
        token = None
        try:
            auth_response = requests.post(
                f"{self.config.base_url}/v1/auth/login",
                json={"username": self.config.admin_username, "password": self.config.admin_password},
                timeout=5,
            )
            if auth_response.status_code == 200:
                token = auth_response.json()["access_token"]
            else:
                self.console.print(
                    f"[yellow]⚠️  Auth failed: {auth_response.status_code} - {auth_response.text[:100]}[/yellow]"
                )
        except Exception as e:
            self.console.print(f"[yellow]⚠️  Could not authenticate for state check: {e}[/yellow]")

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
            except Exception:
                pass

            time.sleep(1)

        self.console.print("[yellow]⚠️  Agent did not reach WORK state in time[/yellow]")
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
