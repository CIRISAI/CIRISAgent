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

        # Build command
        cmd = [sys.executable, "main.py", "--adapter", self.config.adapter, "--port", str(self.config.api_port)]

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

                # Wait up to 5 seconds for graceful shutdown
                try:
                    self.process.wait(timeout=5)
                    self.console.print("[green]✅ Server stopped gracefully[/green]")
                except subprocess.TimeoutExpired:
                    # Force kill if needed
                    self.process.kill()
                    self.console.print("[yellow]⚠️  Server force killed[/yellow]")

                self.process = None
                self.pid = None

            except Exception as e:
                self.console.print(f"[red]Error stopping server: {e}[/red]")

        # Also try to kill by port if process tracking failed
        self._kill_by_port()

    def _is_server_running(self) -> bool:
        """Check if server is running on the configured port."""
        try:
            response = requests.get(f"{self.config.base_url}/health", timeout=2)
            return response.status_code == 200
        except:
            return False

    def _wait_for_server(self) -> bool:
        """Wait for server to be ready."""
        start_time = time.time()

        while time.time() - start_time < self.config.server_startup_timeout:
            # Check if process is still alive
            if self.process and self.process.poll() is not None:
                # Process died
                stderr = self.process.stderr.read().decode() if self.process.stderr else ""
                self.console.print(f"[red]Server process died: {stderr[:500]}[/red]")
                return False

            # Check if server is responding
            if self._is_server_running():
                return True

            time.sleep(1)

        return False

    def _kill_by_port(self):
        """Kill any process using the configured port."""
        try:
            for conn in psutil.net_connections():
                if conn.laddr.port == self.config.api_port and conn.status == "LISTEN":
                    try:
                        process = psutil.Process(conn.pid)
                        process.terminate()
                        self.console.print(f"[yellow]Killed process {conn.pid} on port {self.config.api_port}[/yellow]")
                    except:
                        pass
        except:
            pass
