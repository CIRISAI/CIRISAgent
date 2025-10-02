"""
API server management for QA testing.
"""

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import psutil
import requests
from rich.console import Console

from .config import QAConfig


class APIServerManager:
    """Manages the API server lifecycle for testing."""

    def __init__(self, config: QAConfig):
        """Initialize server manager."""
        self.config = config
        self.console = Console()
        self.process: Optional[subprocess.Popen] = None
        self.pid: Optional[int] = None

    def start(self) -> bool:
        """Start the API server."""
        # Check if server is already running
        if self._is_server_running():
            self.console.print("[yellow]⚠️  Server already running[/yellow]")
            return True

        self.console.print("[cyan]🚀 Starting API server...[/cyan]")

        # Build command - main.py is in the root directory
        main_path = Path(__file__).parent.parent.parent / "main.py"
        cmd = [sys.executable, str(main_path), "--adapter", self.config.adapter, "--port", str(self.config.api_port)]

        if self.config.mock_llm:
            cmd.append("--mock-llm")

        # Set environment variables
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        # Start server process
        try:
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=Path.cwd()
            )
            self.pid = self.process.pid

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

            except Exception as e:
                self.console.print(f"[red]Error stopping server: {e}[/red]")

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
        start_time = time.time()

        # First, wait for server to respond to health checks
        while time.time() - start_time < self.config.server_startup_timeout:
            # Check if process is still alive
            if self.process and self.process.poll() is not None:
                # Process died
                stderr = self.process.stderr.read().decode() if self.process.stderr else ""
                self.console.print(f"[red]Server process died: {stderr[:500]}[/red]")
                return False

            # Check if server is responding
            if self._is_server_running():
                break

            time.sleep(1)
        else:
            # Timeout waiting for health check
            return False

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
        except:
            self.console.print("[yellow]⚠️  Could not authenticate for state check[/yellow]")

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
                    state_lower = cognitive_state.lower()
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
            except Exception as e:
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
