"""
Emulator Bridge - ADB port forwarding and device management.

This module handles the connection between the host machine and the
Android emulator running CIRIS. It provides:
- ADB port forwarding (emulator:8080 → localhost:8080)
- Device status checking
- .env file management on device
- Server health monitoring
- Bridge to main QA runner
"""

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import requests

from .config import MobileQAConfig


@dataclass
class DeviceInfo:
    """Information about a connected Android device."""
    serial: str
    state: str
    is_emulator: bool
    api_level: Optional[int] = None
    model: Optional[str] = None


@dataclass
class ServerStatus:
    """Status of CIRIS server on device."""
    reachable: bool
    healthy: bool
    services_online: int = 0
    total_services: int = 22
    is_first_run: bool = False
    error: Optional[str] = None


class EmulatorBridge:
    """
    Bridge for communicating with CIRIS running on Android emulator.
    """
    
    # Path to main project's venv
    MAIN_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
    VENV_PYTHON = MAIN_PROJECT_ROOT / ".venv" / "bin" / "python"
    
    def __init__(self, config: Optional[MobileQAConfig] = None):
        self.config = config or MobileQAConfig()
        self._port_forward_active = False
    
    def _run_adb(self, *args, check: bool = True) -> subprocess.CompletedProcess:
        """Run an ADB command."""
        cmd = [self.config.adb_executable]
        if self.config.device_serial:
            cmd.extend(["-s", self.config.device_serial])
        cmd.extend(args)
        
        if self.config.verbose:
            print(f"[ADB] {' '.join(cmd)}")
        
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=check
        )
    
    def get_devices(self) -> list[DeviceInfo]:
        """Get list of connected Android devices."""
        result = self._run_adb("devices", "-l", check=False)
        if result.returncode != 0:
            raise RuntimeError(f"ADB not available: {result.stderr}")
        
        devices = []
        for line in result.stdout.strip().split("\n")[1:]:
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 2:
                serial = parts[0]
                state = parts[1]
                is_emulator = serial.startswith("emulator-")
                
                model = None
                for part in parts[2:]:
                    if part.startswith("model:"):
                        model = part.split(":")[1]
                
                devices.append(DeviceInfo(
                    serial=serial,
                    state=state,
                    is_emulator=is_emulator,
                    model=model
                ))
        
        return devices
    
    def get_device(self) -> DeviceInfo:
        """Get the target device (first emulator or specified device)."""
        devices = self.get_devices()
        
        if not devices:
            raise RuntimeError("No Android devices connected")
        
        if self.config.device_serial:
            for device in devices:
                if device.serial == self.config.device_serial:
                    return device
            raise RuntimeError(f"Device {self.config.device_serial} not found")
        
        for device in devices:
            if device.is_emulator and device.state == "device":
                return device
        
        for device in devices:
            if device.state == "device":
                return device
        
        raise RuntimeError("No ready devices found")
    
    def start_port_forward(self) -> bool:
        """Start ADB port forwarding from device to host."""
        try:
            self._run_adb(
                "forward", "--remove",
                f"tcp:{self.config.local_port}",
                check=False
            )
            
            result = self._run_adb(
                "forward",
                f"tcp:{self.config.local_port}",
                f"tcp:{self.config.device_port}"
            )
            
            if result.returncode == 0:
                self._port_forward_active = True
                print(f"✓ Port forward: localhost:{self.config.local_port} → device:{self.config.device_port}")
                return True
            else:
                print(f"✗ Port forward failed: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"✗ Port forward error: {e}")
            return False
    
    def stop_port_forward(self) -> bool:
        """Stop ADB port forwarding."""
        try:
            result = self._run_adb(
                "forward", "--remove",
                f"tcp:{self.config.local_port}",
                check=False
            )
            self._port_forward_active = False
            return result.returncode == 0
        except Exception:
            return False
    
    def check_server_status(self) -> ServerStatus:
        """Check CIRIS server status on device."""
        if not self._port_forward_active:
            self.start_port_forward()
        
        try:
            response = requests.get(
                f"{self.config.base_url}/v1/system/health",
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                return ServerStatus(
                    reachable=True,
                    healthy=data.get("healthy", False),
                    services_online=data.get("services_online", 0),
                    total_services=data.get("services_total", 22)
                )
            else:
                return ServerStatus(
                    reachable=True,
                    healthy=False,
                    error=f"HTTP {response.status_code}"
                )
                
        except requests.exceptions.ConnectionError:
            return ServerStatus(
                reachable=False,
                healthy=False,
                error="Connection refused - server not running"
            )
        except Exception as e:
            return ServerStatus(
                reachable=False,
                healthy=False,
                error=str(e)
            )
    
    def check_first_run(self) -> bool:
        """Check if device is in first-run state (no .env file)."""
        try:
            result = self._run_adb(
                "shell", f"test -f {self.config.device_env_path} && echo exists",
                check=False
            )
            return "exists" not in result.stdout
        except Exception:
            return True
    
    def create_env_file(
        self,
        llm_api_key: str,
        llm_provider: str = "openai",
        llm_model: str = "gpt-4o",
        admin_password: Optional[str] = None
    ) -> bool:
        """Create .env file on device to complete first-run setup."""
        if not admin_password:
            import secrets
            admin_password = secrets.token_urlsafe(24)
        
        env_content = f"""# CIRIS Mobile Configuration
OPENAI_API_KEY={llm_api_key}
LLM_PROVIDER={llm_provider}
LLM_MODEL={llm_model}
ADMIN_PASSWORD={admin_password}
CIRIS_CONFIGURED=true
CIRIS_MODE=installed
"""
        
        try:
            self._run_adb("shell", "mkdir", "-p", self.config.device_ciris_home, check=False)
            
            escaped = env_content.replace("'", "'\\''")
            result = self._run_adb(
                "shell", f"echo '{escaped}' > {self.config.device_env_path}"
            )
            
            if result.returncode == 0:
                print(f"✓ Created .env at {self.config.device_env_path}")
                return True
            else:
                print(f"✗ Failed to create .env: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"✗ Error creating .env: {e}")
            return False
    
    def delete_env_file(self) -> bool:
        """Delete .env file to reset to first-run state."""
        try:
            result = self._run_adb("shell", "rm", "-f", self.config.device_env_path)
            if result.returncode == 0:
                print(f"✓ Deleted {self.config.device_env_path}")
                return True
            return False
        except Exception as e:
            print(f"✗ Error deleting .env: {e}")
            return False
    
    def restart_app(self) -> bool:
        """Force stop and restart the CIRIS app."""
        package = "ai.ciris.mobile"
        activity = "ai.ciris.mobile.MainActivity"
        
        try:
            self._run_adb("shell", "am", "force-stop", package)
            time.sleep(1)
            
            result = self._run_adb("shell", "am", "start", "-n", f"{package}/{activity}")
            
            if "Starting:" in result.stdout or result.returncode == 0:
                print(f"✓ Restarted {package}")
                return True
            else:
                print(f"✗ Failed to restart: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"✗ Error restarting app: {e}")
            return False
    
    def wait_for_server(self, timeout: Optional[float] = None) -> ServerStatus:
        """Wait for server to become healthy."""
        timeout = timeout or self.config.server_startup_timeout
        start = time.time()
        
        while time.time() - start < timeout:
            status = self.check_server_status()
            
            if status.healthy:
                return status
            
            if status.reachable:
                print(f"  Server reachable, {status.services_online}/{status.total_services} services...")
            else:
                print(f"  Waiting for server... ({status.error})")
            
            time.sleep(self.config.health_check_interval)
        
        return ServerStatus(
            reachable=False,
            healthy=False,
            error=f"Timeout after {timeout}s"
        )
    
    def get_logcat(self, lines: int = 100, filter_tag: str = "python") -> str:
        """Get recent logcat output."""
        try:
            result = self._run_adb(
                "logcat", "-d", "-t", str(lines),
                f"{filter_tag}.stdout:I", f"{filter_tag}.stderr:W", "*:S"
            )
            return result.stdout
        except Exception as e:
            return f"Error getting logcat: {e}"
    
    def run_qa_module(self, *modules, force: bool = False) -> Tuple[bool, str]:
        """
        Run QA modules via the main QA runner using the project's venv.
        
        Args:
            modules: Test modules to run (e.g., "setup", "auth", "telemetry")
            force: Run even if server not fully healthy
            
        Returns:
            (success, message) tuple
        """
        if not self._port_forward_active:
            self.start_port_forward()
        
        # Use the main project's venv Python
        venv_python = str(self.VENV_PYTHON)
        if not Path(venv_python).exists():
            return False, f"Venv not found at {venv_python}"
        
        # Build command
        cmd = [
            venv_python, "-m", "tools.qa_runner",
            *modules,
            "--no-auto-start",
            "--url", self.config.base_url,
        ]
        
        if self.config.verbose:
            cmd.append("--verbose")
        
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.MAIN_PROJECT_ROOT),
                capture_output=False,  # Let output go to terminal
                timeout=self.config.timeout * len(modules),
            )
            
            success = result.returncode == 0
            return success, "Tests completed" if success else f"Exit code {result.returncode}"
            
        except subprocess.TimeoutExpired:
            return False, "Timeout"
        except Exception as e:
            return False, f"Error: {e}"
