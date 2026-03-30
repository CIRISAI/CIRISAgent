"""
iOS Physical Device Helper using xcrun devicectl and libimobiledevice tools.

Provides utilities for interacting with physical iOS devices.
"""

import json
import subprocess
import tempfile
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
        self._port_forward_process: Optional[subprocess.Popen] = None
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

    # Maps libimobiledevice UDID -> CoreDevice UUID for devicectl commands
    _udid_to_coredevice: Dict[str, str] = {}

    def _get_devicectl_devices_json(self) -> Optional[dict]:
        """
        Run devicectl list devices and return parsed JSON.

        Uses a temp file because --json-output /dev/stdout does not work
        reliably when subprocess captures stdout.
        """
        if not self._has_devicectl:
            return None
        try:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
                tmp_path = tmp.name

            result = subprocess.run(
                ["xcrun", "devicectl", "list", "devices", "--json-output", tmp_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                with open(tmp_path) as f:
                    return json.load(f)
        except (json.JSONDecodeError, subprocess.TimeoutExpired, OSError):
            pass
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass
        return None

    def get_devices(self) -> List[DeviceInfo]:
        """Get list of connected physical iOS devices.

        Prefers devicectl (returns CoreDevice UUID needed for file operations).
        Falls back to idevice_id if devicectl is unavailable, then attempts
        to resolve CoreDevice UUIDs via a separate devicectl call.
        """
        devices = []

        data = self._get_devicectl_devices_json()
        if data:
            for device in data.get("result", {}).get("devices", []):
                hw = device.get("hardwareProperties", {})
                # Only include physical devices (not simulators)
                if hw.get("reality") != "physical":
                    continue

                coredevice_uuid = device.get("identifier", "")
                udid = hw.get("udid", "")
                conn = device.get("connectionProperties", {})
                tunnel_state = conn.get("tunnelState", "")

                # Build UDID -> CoreDevice UUID map
                if udid and coredevice_uuid:
                    IDeviceHelper._udid_to_coredevice[udid] = coredevice_uuid

                devices.append(
                    DeviceInfo(
                        identifier=coredevice_uuid,
                        state="device" if tunnel_state == "connected" else "offline",
                        platform=Platform.IOS,
                        name=device.get("deviceProperties", {}).get("name"),
                        os_version=device.get("deviceProperties", {}).get("osVersionNumber"),
                        model=hw.get("marketingName"),
                    )
                )

        # Fallback to idevice_id if devicectl returned nothing
        if not devices and self._has_idevice:
            try:
                result = subprocess.run(
                    ["idevice_id", "-l"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                udids = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]

                for udid in udids:
                    # Try to resolve CoreDevice UUID from devicectl
                    coredevice_uuid = self._resolve_coredevice_uuid(udid)
                    devices.append(
                        DeviceInfo(
                            identifier=coredevice_uuid or udid,
                            state="device",
                            platform=Platform.IOS,
                        )
                    )
            except Exception:
                pass

        return devices

    def _resolve_coredevice_uuid(self, udid: str) -> Optional[str]:
        """Resolve a libimobiledevice UDID to a CoreDevice UUID.

        devicectl commands require the CoreDevice UUID, not the UDID.
        The mapping is available in the devicectl JSON under
        hardwareProperties.udid.
        """
        # Check cache first
        if udid in IDeviceHelper._udid_to_coredevice:
            return IDeviceHelper._udid_to_coredevice[udid]

        # Try to get it from devicectl JSON
        data = self._get_devicectl_devices_json()
        if data:
            for device in data.get("result", {}).get("devices", []):
                hw = device.get("hardwareProperties", {})
                device_udid = hw.get("udid", "")
                coredevice_uuid = device.get("identifier", "")
                if device_udid and coredevice_uuid:
                    IDeviceHelper._udid_to_coredevice[device_udid] = coredevice_uuid
                    if device_udid == udid:
                        return coredevice_uuid

        return None

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
        """Take screenshot using pymobiledevice3 (requires tunneld running).

        pymobiledevice3 developer dvt screenshot is the only reliable method
        for iOS 17+ physical devices. Requires a background tunneld daemon:
            sudo python3 -m pymobiledevice3 remote tunneld &
        """
        # pymobiledevice3 is the only working screenshot method for iOS 17+
        # (idevicescreenshot is broken, xcrun devicectl has no screenshot command)
        try:
            result = subprocess.run(
                ["python3", "-m", "pymobiledevice3", "developer", "dvt", "screenshot", output_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and Path(output_path).exists():
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Fallback: idevicescreenshot (works on older iOS)
        if self._has_idevice:
            device = self._get_device_target()
            udid = self._get_udid_for_idevice_tools(device)
            try:
                result = subprocess.run(
                    ["idevicescreenshot", "-u", udid, output_path],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                return result.returncode == 0
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

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

    def _pull_single_file_devicectl(
        self,
        device: str,
        bundle_id: str,
        source: str,
        destination: Path,
        timeout: int = 30,
    ) -> bool:
        """
        Pull a single file from the device app container using xcrun devicectl.

        Args:
            device: CoreDevice UUID
            bundle_id: App bundle identifier
            source: Relative path within the app data container (e.g. "Documents/ciris/logs/kmp_runtime.log")
            destination: Local path to save the file to
            timeout: Command timeout in seconds

        Returns:
            True if the file was successfully pulled
        """
        destination.parent.mkdir(parents=True, exist_ok=True)

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
                source,
                "--destination",
                str(destination),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0

    def _resolve_log_from_marker(
        self,
        device: str,
        bundle_id: str,
        output_path: Path,
        marker_name: str,
    ) -> Optional[str]:
        """
        Resolve a log filename by pulling a marker file from the device.

        Marker files contain the absolute on-device path to the current log.
        We extract just the filename from it.

        Args:
            marker_name: Name of the marker file (e.g. ".current_incident_log",
                         ".current_log")

        Returns:
            The log filename (e.g. "incidents_20260224_032846.log") or None
        """
        marker_dest = output_path / marker_name
        ok = self._pull_single_file_devicectl(
            device,
            bundle_id,
            f"Documents/ciris/logs/{marker_name}",
            marker_dest,
        )
        if ok and marker_dest.exists():
            content = marker_dest.read_text().strip()
            # Extract filename from absolute path like:
            # /private/var/mobile/.../Documents/ciris/logs/incidents_20260224_032846.log
            if "/" in content:
                return content.rsplit("/", 1)[-1]
            return content
        return None

    def _pull_app_data_devicectl(self, device: str, bundle_id: str, output_path: Path, collection: LogCollection):
        """
        Pull key app data files individually from a physical iOS device.

        Pulling the entire Documents directory can fail when symlinks or locked
        files exist (e.g. latest.log).  Instead we pull specific files one at a
        time, which is more reliable.
        """
        logs_dir = output_path / "logs"
        logs_dir.mkdir(exist_ok=True)
        status_dir = output_path / "status"
        status_dir.mkdir(exist_ok=True)

        pulled_count = 0
        failed_files: list = []

        # --- 1. Resolve and pull the current incidents log via marker ---
        incidents_name = self._resolve_log_from_marker(device, bundle_id, output_path, ".current_incident_log")
        if incidents_name:
            dest = logs_dir / incidents_name
            ok = self._pull_single_file_devicectl(
                device,
                bundle_id,
                f"Documents/ciris/logs/{incidents_name}",
                dest,
            )
            if ok:
                # Also save as incidents_latest.log for consistent naming
                latest_dest = logs_dir / "incidents_latest.log"
                try:
                    import shutil

                    shutil.copy2(dest, latest_dest)
                except Exception:
                    pass
                collection.app_logs.append(dest)
                pulled_count += 1
                print(f"  [OK] {incidents_name} (→ incidents_latest.log)")
            else:
                failed_files.append(incidents_name)
        else:
            print("  [WARN] Could not resolve current incidents log filename")

        # --- 1b. Resolve and pull the current main log via marker ---
        main_log_name = self._resolve_log_from_marker(device, bundle_id, output_path, ".current_log")
        if main_log_name:
            dest = logs_dir / main_log_name
            ok = self._pull_single_file_devicectl(
                device,
                bundle_id,
                f"Documents/ciris/logs/{main_log_name}",
                dest,
            )
            if ok:
                # Also save as latest.log for consistent naming
                latest_dest = logs_dir / "latest.log"
                try:
                    import shutil

                    shutil.copy2(dest, latest_dest)
                except Exception:
                    pass
                collection.app_logs.append(dest)
                pulled_count += 1
                print(f"  [OK] {main_log_name} (→ latest.log)")
            else:
                failed_files.append(main_log_name)

        # --- 2. Known log files ---
        log_files = [
            "Documents/ciris/logs/kmp_runtime.log",
            "Documents/ciris/logs/kmp_errors.log",
            "Documents/ciris/logs/kmp_app.log",
        ]
        for source in log_files:
            filename = source.rsplit("/", 1)[-1]
            dest = logs_dir / filename
            ok = self._pull_single_file_devicectl(device, bundle_id, source, dest)
            if ok:
                collection.app_logs.append(dest)
                pulled_count += 1
                print(f"  [OK] {filename}")
            else:
                failed_files.append(filename)

        # --- 3. Status / config JSON files ---
        status_files = [
            "Documents/ciris/runtime_status.json",
            "Documents/ciris/startup_status.json",
            "Documents/ciris/service_status.json",
        ]
        for source in status_files:
            filename = source.rsplit("/", 1)[-1]
            dest = status_dir / filename
            ok = self._pull_single_file_devicectl(device, bundle_id, source, dest)
            if ok:
                collection.app_logs.append(dest)
                pulled_count += 1
                print(f"  [OK] {filename}")
            else:
                failed_files.append(filename)

        # --- 4. Optional files (may not exist or may be symlinks) ---
        optional_files = [
            "Documents/python_error.log",
            "Documents/ciris/logs/latest.log",
            "Documents/ciris/logs/incidents_latest.log",
        ]
        for source in optional_files:
            filename = source.rsplit("/", 1)[-1]
            dest = logs_dir / filename
            ok = self._pull_single_file_devicectl(device, bundle_id, source, dest)
            if ok:
                collection.app_logs.append(dest)
                pulled_count += 1
                print(f"  [OK] {filename}")
            # Silently skip optional files that don't exist

        # --- 5. Try pulling databases directory (best-effort) ---
        db_dir = output_path / "databases"
        db_dir.mkdir(exist_ok=True)
        db_result = subprocess.run(
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
                "Documents/ciris/databases",
                "--destination",
                str(db_dir),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if db_result.returncode == 0 and db_dir.exists():
            for db_file in db_dir.rglob("*.db"):
                collection.databases.append(db_file)
                print(f"  [OK] databases/{db_file.name}")
                pulled_count += 1

        # Summary
        if failed_files:
            collection.metadata["failed_pulls"] = failed_files
            print(f"  [WARN] Could not pull: {', '.join(failed_files)}")

        print(f"  [INFO] Pulled {pulled_count} files from device")

    def _get_udid_for_idevice_tools(self, device: str) -> str:
        """Get the libimobiledevice UDID for idevice* tools.

        If device is already a UDID (from idevice_id fallback), return as-is.
        If device is a CoreDevice UUID, look up the UDID from our mapping.
        """
        # Check reverse map: CoreDevice UUID -> UDID
        for udid, coredevice in IDeviceHelper._udid_to_coredevice.items():
            if coredevice == device:
                return udid
        # Assume it's already a UDID
        return device

    def _pull_system_logs(self, device: str, output_path: Path, bundle_id: str, collection: LogCollection):
        """Pull system logs using idevicesyslog."""
        if not self._has_idevice:
            return

        udid = self._get_udid_for_idevice_tools(device)
        try:
            # Capture recent logs (run for 5 seconds)
            log_path = output_path / "system_log.txt"
            process = subprocess.Popen(
                ["idevicesyslog", "-u", udid],
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
            udid = self._get_udid_for_idevice_tools(device)
            try:
                result = subprocess.run(
                    ["idevicecrashreport", "-u", udid, "-e", str(crash_dir)],
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
        # Clean up any previous port forward
        self.stop_port_forward()

        if self._has_idevice:
            device = self._get_device_target()
            udid = self._get_udid_for_idevice_tools(device)
            try:
                self._port_forward_process = subprocess.Popen(
                    ["iproxy", str(local_port), str(remote_port), "-u", udid],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                # Give iproxy a moment to start
                time.sleep(0.5)
                return True
            except Exception:
                pass
        return False

    def stop_port_forward(self) -> bool:
        """Stop the port forwarding process."""
        if self._port_forward_process:
            self._port_forward_process.terminate()
            try:
                self._port_forward_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._port_forward_process.kill()
            self._port_forward_process = None
            return True
        return False
