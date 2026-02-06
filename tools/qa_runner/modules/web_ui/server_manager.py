"""
Server Manager for Web UI Testing

Manages CIRIS API server lifecycle including:
- Data wipe (clean slate)
- Wheel installation
- Server startup/shutdown
- Health monitoring
"""

import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests


@dataclass
class ServerConfig:
    """Configuration for CIRIS server management."""

    # Server settings
    host: str = "127.0.0.1"
    port: int = 8080
    mock_llm: bool = False  # Use mock LLM for testing

    # Paths
    project_root: Optional[str] = None  # Auto-detect if not set
    data_dir: Optional[str] = None  # Data directory to wipe
    log_dir: str = "logs"

    # Timeouts
    startup_timeout: int = 60  # Seconds to wait for server startup
    health_check_interval: float = 1.0  # Seconds between health checks

    # Build settings
    install_wheel: bool = False  # Install fresh wheel before starting
    wipe_data: bool = True  # Wipe data for clean slate


@dataclass
class ServerStatus:
    """Current server status."""

    running: bool = False
    healthy: bool = False
    url: Optional[str] = None
    pid: Optional[int] = None
    agent_state: Optional[str] = None
    services_online: int = 0
    error: Optional[str] = None


class ServerManager:
    """
    Manages CIRIS API server for web UI testing.

    Handles:
    - Data cleanup for fresh tests
    - Wheel building and installation
    - Server process management
    - Health monitoring
    """

    def __init__(self, config: Optional[ServerConfig] = None):
        self.config = config or ServerConfig()
        self._process: Optional[subprocess.Popen] = None
        self._log_file = None

        # Auto-detect project root
        if not self.config.project_root:
            self.config.project_root = self._find_project_root()

        # Set data directory
        if not self.config.data_dir:
            self.config.data_dir = os.path.join(self.config.project_root, "data")

    def _find_project_root(self) -> str:
        """Find CIRIS project root directory."""
        # Try current working directory
        cwd = os.getcwd()
        if os.path.exists(os.path.join(cwd, "main.py")):
            return cwd

        # Try relative paths
        for path in ["..", "../..", "../../.."]:
            full_path = os.path.abspath(os.path.join(cwd, path))
            if os.path.exists(os.path.join(full_path, "main.py")):
                return full_path

        # Default to CIRISAgent in home directory
        home_path = os.path.expanduser("~/CIRISAgent")
        if os.path.exists(os.path.join(home_path, "main.py")):
            return home_path

        raise RuntimeError("Could not find CIRIS project root. Set project_root in config.")

    @property
    def base_url(self) -> str:
        """Get the base URL for the server."""
        return f"http://{self.config.host}:{self.config.port}"

    def wipe_data(self) -> bool:
        """
        Wipe all data for a clean slate test.

        Removes:
        - SQLite databases
        - Log files
        - Cache files

        Returns:
            True if successful
        """
        print("🗑️  Wiping data for clean slate...")

        data_paths = [
            self.config.data_dir,
            os.path.join(self.config.project_root, "ciris_engine.db"),
            os.path.join(self.config.project_root, "ciris_engine.db-wal"),
            os.path.join(self.config.project_root, "ciris_engine.db-shm"),
            os.path.join(self.config.project_root, "audit.db"),
            os.path.join(self.config.project_root, "secrets.db"),
            # Also remove .env to reset first-run state (both locations checked in dev mode)
            os.path.join(self.config.project_root, ".env"),
            os.path.join(self.config.project_root, "ciris", ".env"),  # Dev mode first-priority path
        ]

        for path in data_paths:
            if path and os.path.exists(path):
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path)
                        print(f"   Removed directory: {path}")
                    else:
                        os.remove(path)
                        print(f"   Removed file: {path}")
                except Exception as e:
                    print(f"   ⚠️  Could not remove {path}: {e}")

        # Clear logs but keep directory
        log_dir = os.path.join(self.config.project_root, self.config.log_dir)
        if os.path.exists(log_dir):
            for f in os.listdir(log_dir):
                try:
                    fp = os.path.join(log_dir, f)
                    if os.path.isfile(fp):
                        os.remove(fp)
                except Exception:
                    pass
            print(f"   Cleared logs in: {log_dir}")

        print("✅ Data wiped successfully")
        return True

    def build_wheel(self) -> bool:
        """
        Build and install the CIRIS wheel.

        Returns:
            True if successful
        """
        print("📦 Building wheel...")

        try:
            # Build wheel
            result = subprocess.run(
                [sys.executable, "-m", "pip", "wheel", ".", "-w", "dist", "--no-deps"],
                cwd=self.config.project_root,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                print(f"   ⚠️  Wheel build failed: {result.stderr}")
                return False

            # Find and install the wheel
            dist_dir = os.path.join(self.config.project_root, "dist")
            wheels = sorted(Path(dist_dir).glob("ciris_engine-*.whl"), reverse=True)

            if not wheels:
                print("   ⚠️  No wheel found after build")
                return False

            wheel_path = str(wheels[0])
            print(f"   Installing: {wheel_path}")

            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--force-reinstall", wheel_path],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                print(f"   ⚠️  Wheel install failed: {result.stderr}")
                return False

            print("✅ Wheel built and installed")
            return True

        except Exception as e:
            print(f"   ⚠️  Build error: {e}")
            return False

    def start(self) -> ServerStatus:
        """
        Start the CIRIS API server.

        Returns:
            ServerStatus with startup result
        """
        status = ServerStatus(url=self.base_url)

        # Check if already running
        if self.is_running():
            print("⚠️  Server already running, stopping first...")
            self.stop()
            time.sleep(2)

        # Wipe data if requested
        if self.config.wipe_data:
            self.wipe_data()

        # Build wheel if requested
        if self.config.install_wheel:
            if not self.build_wheel():
                status.error = "Failed to build/install wheel"
                return status

        print(f"🚀 Starting CIRIS API server on port {self.config.port}...")

        # Build command
        cmd = [
            sys.executable,
            "main.py",
            "--adapter",
            "api",
            "--port",
            str(self.config.port),
        ]

        if self.config.mock_llm:
            cmd.append("--mock-llm")

        # Open log file
        log_path = os.path.join(self.config.project_root, self.config.log_dir, "web_ui_qa_server.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        self._log_file = open(log_path, "w")

        # Start server process
        try:
            self._process = subprocess.Popen(
                cmd,
                cwd=self.config.project_root,
                stdout=self._log_file,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid if hasattr(os, "setsid") else None,
            )
            status.pid = self._process.pid
            print(f"   Server PID: {self._process.pid}")

        except Exception as e:
            status.error = f"Failed to start server: {e}"
            return status

        # Wait for server to be ready
        print("   Waiting for server to be ready...")
        start_time = time.time()

        while time.time() - start_time < self.config.startup_timeout:
            time.sleep(self.config.health_check_interval)

            # Check if process died
            if self._process.poll() is not None:
                status.error = "Server process exited unexpectedly"
                return status

            # Check health endpoint
            try:
                response = requests.get(f"{self.base_url}/v1/system/health", timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    # Response format: {"data": {"cognitive_state": "work"|null, ...}}
                    health_data = data.get("data", data)
                    agent_state = health_data.get("cognitive_state")

                    # In first-run mode, cognitive_state is null - that's OK
                    # Check for healthy status or normal operation states
                    is_healthy = health_data.get("status") == "healthy"
                    is_ready = agent_state and agent_state.lower() in ["work", "ready"]
                    is_first_run = agent_state is None and is_healthy

                    if is_ready or is_first_run:
                        status.running = True
                        status.healthy = True
                        status.agent_state = agent_state or "first-run"
                        state_msg = agent_state or "first-run (setup required)"
                        print(f"✅ Server ready (state: {state_msg})")
                        return status
                    else:
                        print(f"   Agent state: {agent_state}, healthy: {is_healthy}")

            except requests.exceptions.ConnectionError:
                pass  # Server not ready yet
            except Exception as e:
                print(f"   Health check error: {e}")

        status.error = f"Server startup timeout ({self.config.startup_timeout}s)"
        return status

    def stop(self) -> bool:
        """
        Stop the CIRIS API server.

        Returns:
            True if stopped successfully
        """
        if not self._process:
            return True

        print("🛑 Stopping CIRIS API server...")

        try:
            # Try graceful shutdown first
            if hasattr(os, "killpg"):
                os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
            else:
                self._process.terminate()

            # Wait for graceful shutdown
            try:
                self._process.wait(timeout=10)
                print("   Server stopped gracefully")
            except subprocess.TimeoutExpired:
                # Force kill
                print("   Force killing server...")
                if hasattr(os, "killpg"):
                    os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
                else:
                    self._process.kill()
                self._process.wait()

            self._process = None

        except Exception as e:
            print(f"   ⚠️  Error stopping server: {e}")
            return False

        finally:
            if self._log_file:
                self._log_file.close()
                self._log_file = None

        return True

    def is_running(self) -> bool:
        """Check if server is running."""
        if self._process and self._process.poll() is None:
            return True

        # Also check by port
        try:
            response = requests.get(f"{self.base_url}/v1/system/health", timeout=2)
            return response.status_code == 200
        except Exception:
            return False

    def get_status(self) -> ServerStatus:
        """Get current server status."""
        status = ServerStatus(url=self.base_url)

        if self._process:
            status.pid = self._process.pid
            status.running = self._process.poll() is None

        if status.running or self.is_running():
            try:
                response = requests.get(f"{self.base_url}/v1/system/health", timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    health_data = data.get("data", data)
                    status.healthy = True
                    status.agent_state = health_data.get("cognitive_state")
            except Exception as e:
                status.error = str(e)

        return status

    def kill_existing_servers(self) -> None:
        """Kill any existing CIRIS servers on the configured port."""
        import subprocess

        try:
            # Find processes using the port
            result = subprocess.run(
                ["lsof", "-t", f"-i:{self.config.port}"],
                capture_output=True,
                text=True,
            )

            if result.stdout.strip():
                pids = result.stdout.strip().split("\n")
                for pid in pids:
                    try:
                        os.kill(int(pid), signal.SIGKILL)
                        print(f"   Killed existing process: {pid}")
                    except Exception:
                        pass
                time.sleep(1)

        except FileNotFoundError:
            # lsof not available, try pkill
            subprocess.run(
                ["pkill", "-f", f"python.*main.py.*{self.config.port}"],
                capture_output=True,
            )

    def __enter__(self) -> "ServerManager":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - stop server."""
        self.stop()
