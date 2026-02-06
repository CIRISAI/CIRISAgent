"""
iOS Physical Device Helper using xcrun devicectl and libimobiledevice tools.

Provides utilities for interacting with physical iOS devices.
"""

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..device_helper import DeviceHelper, DeviceInfo, LogCollection, Platform, UIElement


class IDeviceHelper(DeviceHelper):
    """Helper class for physical iOS device operations using xcrun devicectl."""

    platform = Platform.IOS

    def __init__(
        self,
        device_id: Optional[str] = None,
    ):
        """
        Initialize iOS physical device helper.

        Args:
            device_id: Specific device UDID. If None, uses first connected device.
        """
        self.device_id = device_id
        self._log_process: Optional[subprocess.Popen] = None
        self._verify_tools()

    def _verify_tools(self):
        """Verify required tools are available."""
        try:
            result = subprocess.run(
                ["xcrun", "devicectl", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self._has_devicectl = result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self._has_devicectl = False

        # Check for idevice tools (libimobiledevice)
        try:
            result = subprocess.run(
                ["idevice_id", "-l"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self._has_idevice = result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self._has_idevice = False

        if not self._has_devicectl and not self._has_idevice:
            raise RuntimeError(
                "Neither xcrun devicectl nor libimobiledevice tools available. "
                "Install Xcode 15+ or libimobiledevice."
            )

    def _run_devicectl(
        self,
        args: List[str],
        timeout: int = 60,
    ) -> subprocess.CompletedProcess:
        """Run an xcrun devicectl command."""
        cmd = ["xcrun", "devicectl"] + args
        if self.device_id:
            # Insert device flag after subcommand
            if len(args) >= 2:
                cmd = ["xcrun", "devicectl", args[0], args[1], "--device", self.device_id] + args[2:]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def _get_device_target(self) -> str:
        """Get the device target identifier."""
        if self.device_id:
            return self.device_id
        # Get first connected device
        devices = self.get_devices()
        if devices:
            self.device_id = devices[0].identifier
            return self.device_id
        raise RuntimeError("No physical iOS device connected")

    # ========== Device Management ==========

    def get_devices(self) -> List[DeviceInfo]:
        """Get list of connected physical iOS devices."""
        devices = []

        if self._has_devicectl:
            try:
                result = subprocess.run(
                    ["xcrun", "devicectl", "list", "devices", "--json-output", "/dev/stdout"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    data = json.loads(result.stdout)
                    for device in data.get("result", {}).get("devices", []):
                        devices.append(
                            DeviceInfo(
                                identifier=device.get("identifier", ""),
                                state=(
                                    "device"
                                    if device.get("connectionProperties", {}).get("tunnelState") == "connected"
                                    else "offline"
                                ),
                                platform=Platform.IOS,
                                name=device.get("deviceProperties", {}).get("name"),
                                os_version=device.get("deviceProperties", {}).get("osVersionNumber"),
                                model=device.get("hardwareProperties", {}).get("marketingName"),
                            )
                        )
            except (json.JSONDecodeError, subprocess.TimeoutExpired, Exception):
                pass

        # Fallback to idevice_id
        if not devices and self._has_idevice:
            try:
                result = subprocess.run(
                    ["idevice_id", "-l"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                for line in result.stdout.strip().split("\n"):
                    if line:
                        devices.append(
                            DeviceInfo(
                                identifier=line.strip(),
                                state="device",
                                platform=Platform.IOS,
                            )
                        )
            except Exception:
                pass

        return devices

    def is_device_connected(self) -> bool:
        """Check if target device is connected."""
        devices = self.get_devices()
        if self.device_id:
            return any(d.identifier == self.device_id and d.state == "device" for d in devices)
        return len(devices) > 0

    def wait_for_device(self, timeout: int = 60) -> bool:
        """Wait for device to become available."""
        start = time.time()
        while time.time() - start < timeout:
            if self.is_device_connected():
                return True
            time.sleep(1)
        return False

    # ========== App Management ==========

    def install_app(self, app_path: str, reinstall: bool = True) -> bool:
        """Install app on device."""
        device = self._get_device_target()

        if self._has_devicectl:
            result = subprocess.run(
                ["xcrun", "devicectl", "device", "install", "app", "--device", device, app_path],
                capture_output=True,
                text=True,
                timeout=300,
            )
            return result.returncode == 0

        # Fallback to ideviceinstaller
        if self._has_idevice:
            result = subprocess.run(
                ["ideviceinstaller", "-u", device, "-i", app_path],
                capture_output=True,
                text=True,
                timeout=300,
            )
            return result.returncode == 0

        return False

    def uninstall_app(self, bundle_id: str) -> bool:
        """Uninstall app from device."""
        device = self._get_device_target()

        if self._has_devicectl:
            result = subprocess.run(
                ["xcrun", "devicectl", "device", "uninstall", "app", "--device", device, bundle_id],
                capture_output=True,
                text=True,
                timeout=60,
            )
            return result.returncode == 0

        if self._has_idevice:
            result = subprocess.run(
                ["ideviceinstaller", "-u", device, "-U", bundle_id],
                capture_output=True,
                text=True,
                timeout=60,
            )
            return result.returncode == 0

        return False

    def launch_app(self, bundle_id: str, activity: Optional[str] = None) -> bool:
        """Launch app on device."""
        device = self._get_device_target()

        if self._has_devicectl:
            result = subprocess.run(
                ["xcrun", "devicectl", "device", "process", "launch", "--device", device, bundle_id],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode == 0

        return False

    def force_stop_app(self, bundle_id: str) -> bool:
        """Terminate app on device."""
        # devicectl doesn't have a direct terminate command
        # Would need to find PID and kill
        return False

    def clear_app_data(self, bundle_id: str) -> bool:
        """Clear app data - not directly supported on physical devices."""
        return False

    def is_app_installed(self, bundle_id: str) -> bool:
        """Check if app is installed."""
        device = self._get_device_target()

        if self._has_idevice:
            result = subprocess.run(
                ["ideviceinstaller", "-u", device, "-l"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return bundle_id in result.stdout

        return False

    def is_app_running(self, bundle_id: str) -> bool:
        """Check if app is running."""
        device = self._get_device_target()

        if self._has_devicectl:
            result = subprocess.run(
                ["xcrun", "devicectl", "device", "info", "processes", "--device", device],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return bundle_id in result.stdout

        return False

    # ========== UI Interaction ==========

    def tap(self, x: int, y: int) -> bool:
        """Tap - not supported without additional tools."""
        return False

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> bool:
        """Swipe - not supported without additional tools."""
        return False

    def input_text(self, text: str) -> bool:
        """Input text - not supported without additional tools."""
        return False

    def press_back(self) -> bool:
        """Press back - not supported."""
        return False

    def press_home(self) -> bool:
        """Press home - not supported."""
        return False

    def press_enter(self) -> bool:
        """Press enter - not supported."""
        return False

    # ========== Screen Capture ==========

    def screenshot(self, output_path: str) -> bool:
        """Take screenshot."""
        device = self._get_device_target()

        if self._has_devicectl:
            result = subprocess.run(
                ["xcrun", "devicectl", "device", "info", "screenshot", "--device", device, "--output", output_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode == 0

        if self._has_idevice:
            result = subprocess.run(
                ["idevicescreenshot", "-u", device, output_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode == 0

        return False

    def get_screen_size(self) -> Tuple[int, int]:
        """Get screen dimensions."""
        # Default iPhone size
        return (1170, 2532)

    # ========== UI Hierarchy ==========

    def dump_ui_hierarchy(self) -> str:
        """Dump UI hierarchy - not supported without WebDriverAgent."""
        return ""

    def find_element_by_text(self, text: str, exact: bool = False) -> Optional[UIElement]:
        """Find element - not supported."""
        return None

    def find_element_by_id(self, resource_id: str) -> Optional[UIElement]:
        """Find element - not supported."""
        return None

    def find_elements_by_class(self, class_name: str) -> List[UIElement]:
        """Find elements - not supported."""
        return []

    # ========== Logging ==========

    def pull_logs(self, output_dir: str, bundle_id: str) -> LogCollection:
        """Pull comprehensive logs from physical device."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        collection = LogCollection(output_dir=output_path)
        device = self._get_device_target()

        # Get device info
        devices = self.get_devices()
        device_info = next((d for d in devices if d.identifier == device), None)

        if device_info:
            collection.metadata["device_name"] = device_info.name
            collection.metadata["os_version"] = device_info.os_version
            collection.metadata["device_id"] = device_info.identifier
            collection.metadata["model"] = device_info.model

        # Pull Documents directory using devicectl
        if self._has_devicectl:
            self._pull_app_data_devicectl(device, bundle_id, output_path, collection)

        # Pull system logs
        self._pull_system_logs(device, output_path, bundle_id, collection)

        # Pull crash logs
        self._pull_crash_logs(device, output_path, bundle_id, collection)

        # Save metadata
        metadata_path = output_path / "device_info.json"
        with open(metadata_path, "w") as f:
            json.dump(collection.metadata, f, indent=2, default=str)

        return collection

    def _pull_app_data_devicectl(self, device: str, bundle_id: str, output_path: Path, collection: LogCollection):
        """Pull app data using xcrun devicectl."""
        # Create temp directory for downloaded files
        docs_dir = output_path / "Documents"
        docs_dir.mkdir(exist_ok=True)

        # Pull entire Documents directory
        result = subprocess.run(
            [
                "xcrun",
                "devicectl",
                "device",
                "copy",
                "from",
                "--device",
                device,
                "--domain-type",
                "appDataContainer",
                "--domain-identifier",
                bundle_id,
                "--source",
                "Documents",
                "--destination",
                str(docs_dir),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0:
            # Find and categorize files
            logs_dir = output_path / "logs"
            logs_dir.mkdir(exist_ok=True)

            # Python error log
            error_log = docs_dir / "python_error.log"
            if error_log.exists():
                dest = logs_dir / "python_error.log"
                error_log.rename(dest)
                collection.app_logs.append(dest)

            # CIRIS logs
            ciris_logs = docs_dir / "ciris" / "logs"
            if ciris_logs.exists():
                for log_file in ciris_logs.glob("*.log"):
                    dest = logs_dir / log_file.name
                    log_file.rename(dest)
                    collection.app_logs.append(dest)

            # Databases
            db_dir = output_path / "databases"
            db_dir.mkdir(exist_ok=True)
            ciris_dbs = docs_dir / "ciris" / "databases"
            if ciris_dbs.exists():
                for db_file in ciris_dbs.glob("*.db"):
                    dest = db_dir / db_file.name
                    db_file.rename(dest)
                    collection.databases.append(dest)

            # PythonResources info
            python_res = docs_dir / "PythonResources"
            if python_res.exists():
                collection.metadata["python_resources_exists"] = True
                collection.metadata["python_resources_contents"] = [p.name for p in python_res.iterdir() if p.is_dir()]

    def _pull_system_logs(self, device: str, output_path: Path, bundle_id: str, collection: LogCollection):
        """Pull system logs using idevicesyslog."""
        if not self._has_idevice:
            return

        try:
            # Capture recent logs (run for 5 seconds)
            log_path = output_path / "system_log.txt"
            process = subprocess.Popen(
                ["idevicesyslog", "-u", device],
                stdout=open(log_path, "w"),
                stderr=subprocess.DEVNULL,
            )
            time.sleep(5)
            process.terminate()
            process.wait(timeout=5)

            if log_path.exists() and log_path.stat().st_size > 0:
                collection.system_logs.append(log_path)
        except Exception as e:
            collection.metadata["system_log_error"] = str(e)

    def _pull_crash_logs(self, device: str, output_path: Path, bundle_id: str, collection: LogCollection):
        """Pull crash logs from device."""
        crash_dir = output_path / "crashes"
        crash_dir.mkdir(exist_ok=True)

        if self._has_idevice:
            try:
                result = subprocess.run(
                    ["idevicecrashreport", "-u", device, "-e", str(crash_dir)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode == 0:
                    for crash_file in crash_dir.glob("*.crash"):
                        collection.crash_logs.append(crash_file)
                    for ips_file in crash_dir.glob("*.ips"):
                        collection.crash_logs.append(ips_file)
            except Exception as e:
                collection.metadata["crash_log_error"] = str(e)

    def clear_logs(self) -> bool:
        """Clear logs - not supported."""
        return False

    def start_log_capture(self, output_path: str, bundle_id: str) -> bool:
        """Start continuous log capture using idevicesyslog."""
        if not self._has_idevice:
            return False

        device = self._get_device_target()
        try:
            self._log_process = subprocess.Popen(
                ["idevicesyslog", "-u", device],
                stdout=open(output_path, "w"),
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            return False

    def stop_log_capture(self) -> bool:
        """Stop continuous log capture."""
        if self._log_process:
            self._log_process.terminate()
            self._log_process = None
            return True
        return False

    # ========== Utilities ==========

    def grant_permission(self, bundle_id: str, permission: str) -> bool:
        """Grant permission - not supported on physical devices."""
        return False

    def set_property(self, key: str, value: str) -> bool:
        """Set property - not supported."""
        return False

    def get_property(self, key: str) -> Optional[str]:
        """Get property - not supported."""
        return None

    def forward_port(self, local_port: int, remote_port: int) -> bool:
        """Forward port using iproxy."""
        if self._has_idevice:
            device = self._get_device_target()
            try:
                subprocess.Popen(
                    ["iproxy", str(local_port), str(remote_port), "-u", device],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            except Exception:
                pass
        return False
