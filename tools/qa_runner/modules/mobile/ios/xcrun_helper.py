"""
iOS Device Helper using xcrun simctl

Provides utilities for interacting with iOS simulators via xcrun simctl.
Also supports physical devices via libimobiledevice tools when available.
"""

import json
import os
import plistlib
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..device_helper import (
    DeviceHelper,
    DeviceInfo,
    LogCollection,
    Platform,
    UIElement,
)


class XCRunHelper(DeviceHelper):
    """Helper class for iOS simulator operations using xcrun simctl."""

    platform = Platform.IOS

    def __init__(
        self,
        device_id: Optional[str] = None,
        use_booted: bool = True,
    ):
        """
        Initialize iOS helper.

        Args:
            device_id: Specific simulator UDID. If None, uses booted simulator.
            use_booted: If True and no device_id, target the booted simulator.
        """
        self.device_id = device_id
        self.use_booted = use_booted
        self._log_process: Optional[subprocess.Popen] = None
        self._verify_xcrun()

    def _verify_xcrun(self):
        """Verify xcrun is available."""
        try:
            result = subprocess.run(
                ["xcrun", "simctl", "help"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                raise RuntimeError("xcrun simctl not available")
        except FileNotFoundError:
            raise RuntimeError("Xcode command line tools not installed")

    def _get_device_target(self) -> str:
        """Get the device target identifier."""
        if self.device_id:
            return self.device_id
        if self.use_booted:
            return "booted"
        raise RuntimeError("No device specified and use_booted is False")

    def _run_simctl(
        self,
        args: List[str],
        timeout: int = 60,
        check: bool = False,
    ) -> subprocess.CompletedProcess:
        """Run an xcrun simctl command."""
        cmd = ["xcrun", "simctl"] + args
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    # ========== Device Management ==========

    def get_devices(self) -> List[DeviceInfo]:
        """Get list of available iOS simulators."""
        result = self._run_simctl(["list", "devices", "--json"])
        if result.returncode != 0:
            return []

        try:
            data = json.loads(result.stdout)
            devices = []

            for runtime, device_list in data.get("devices", {}).items():
                # Extract iOS version from runtime string
                # e.g., "com.apple.CoreSimulator.SimRuntime.iOS-17-0" -> "17.0"
                version_match = re.search(r"iOS[.-](\d+)[.-](\d+)", runtime)
                os_version = (
                    f"{version_match.group(1)}.{version_match.group(2)}"
                    if version_match
                    else None
                )

                for device in device_list:
                    if device.get("isAvailable", False):
                        devices.append(
                            DeviceInfo(
                                identifier=device["udid"],
                                state=device["state"].lower(),
                                platform=Platform.IOS,
                                name=device.get("name"),
                                os_version=os_version,
                                model=device.get("deviceTypeIdentifier", "").split(".")[-1],
                            )
                        )

            return devices
        except (json.JSONDecodeError, KeyError):
            return []

    def is_device_connected(self) -> bool:
        """Check if target simulator is booted."""
        target = self._get_device_target()
        if target == "booted":
            # Check if any simulator is booted
            devices = self.get_devices()
            return any(d.state == "booted" for d in devices)
        else:
            devices = self.get_devices()
            return any(d.identifier == target and d.state == "booted" for d in devices)

    def wait_for_device(self, timeout: int = 60) -> bool:
        """Wait for simulator to boot."""
        target = self._get_device_target()

        # If targeting specific device, boot it
        if target != "booted":
            self._run_simctl(["boot", target])

        start = time.time()
        while time.time() - start < timeout:
            if self.is_device_connected():
                return True
            time.sleep(1)
        return False

    def boot_device(self, device_id: Optional[str] = None) -> bool:
        """Boot a specific simulator."""
        target = device_id or self.device_id
        if not target:
            # Boot first available device
            devices = self.get_devices()
            available = [d for d in devices if d.state == "shutdown"]
            if not available:
                return False
            target = available[0].identifier

        result = self._run_simctl(["boot", target])
        return result.returncode == 0

    def shutdown_device(self, device_id: Optional[str] = None) -> bool:
        """Shutdown a simulator."""
        target = device_id or self._get_device_target()
        result = self._run_simctl(["shutdown", target])
        return result.returncode == 0

    # ========== App Management ==========

    def install_app(self, app_path: str, reinstall: bool = True) -> bool:
        """Install app on simulator."""
        target = self._get_device_target()

        if reinstall:
            # Get bundle ID and uninstall first
            bundle_id = self._get_bundle_id_from_app(app_path)
            if bundle_id:
                self.uninstall_app(bundle_id)

        result = self._run_simctl(["install", target, app_path])
        return result.returncode == 0

    def _get_bundle_id_from_app(self, app_path: str) -> Optional[str]:
        """Extract bundle ID from .app bundle."""
        info_plist = Path(app_path) / "Info.plist"
        if info_plist.exists():
            try:
                with open(info_plist, "rb") as f:
                    plist = plistlib.load(f)
                    return plist.get("CFBundleIdentifier")
            except Exception:
                pass
        return None

    def uninstall_app(self, bundle_id: str) -> bool:
        """Uninstall app from simulator."""
        target = self._get_device_target()
        result = self._run_simctl(["uninstall", target, bundle_id])
        return result.returncode == 0

    def launch_app(self, bundle_id: str, activity: Optional[str] = None) -> bool:
        """Launch app on simulator."""
        target = self._get_device_target()
        result = self._run_simctl(["launch", target, bundle_id])
        return result.returncode == 0

    def force_stop_app(self, bundle_id: str) -> bool:
        """Terminate app on simulator."""
        target = self._get_device_target()
        result = self._run_simctl(["terminate", target, bundle_id])
        return result.returncode == 0

    def clear_app_data(self, bundle_id: str) -> bool:
        """Clear app data by uninstalling and reinstalling."""
        # Simulators don't have a direct "clear data" command
        # This is a placeholder - would need to reinstall the app
        return False

    def is_app_installed(self, bundle_id: str) -> bool:
        """Check if app is installed."""
        target = self._get_device_target()
        result = self._run_simctl(["get_app_container", target, bundle_id])
        return result.returncode == 0

    def is_app_running(self, bundle_id: str) -> bool:
        """Check if app is currently running."""
        target = self._get_device_target()
        # Use spawn to run 'launchctl list' to check running apps
        result = self._run_simctl(
            ["spawn", target, "launchctl", "list"],
            timeout=10,
        )
        return bundle_id in result.stdout

    # ========== UI Interaction ==========

    def tap(self, x: int, y: int) -> bool:
        """Tap at coordinates using simctl io."""
        target = self._get_device_target()
        # Note: simctl io tap was added in later Xcode versions
        result = subprocess.run(
            ["xcrun", "simctl", "io", target, "tap", str(x), str(y)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> bool:
        """Swipe from (x1,y1) to (x2,y2)."""
        target = self._get_device_target()
        # simctl io swipe format: simctl io <device> swipe <x1> <y1> <x2> <y2>
        result = subprocess.run(
            ["xcrun", "simctl", "io", target, "swipe", str(x1), str(y1), str(x2), str(y2)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0

    def input_text(self, text: str) -> bool:
        """Input text using simctl keychain or pbcopy+paste."""
        target = self._get_device_target()
        # Use simctl keychain to send text
        result = subprocess.run(
            ["xcrun", "simctl", "io", target, "sendText", text],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return True

        # Fallback: use pbcopy and paste
        try:
            subprocess.run(["pbcopy"], input=text, text=True, timeout=5)
            # Simulate Cmd+V
            return self._send_key_event("v", command=True)
        except Exception:
            return False

    def _send_key_event(self, key: str, command: bool = False) -> bool:
        """Send a key event to the simulator."""
        # This would require AppleScript or similar
        # For now, return False as it's complex to implement
        return False

    def press_back(self) -> bool:
        """Swipe from left edge to go back (iOS gesture)."""
        # Get screen size and swipe from left edge
        width, height = self.get_screen_size()
        return self.swipe(10, height // 2, width // 2, height // 2)

    def press_home(self) -> bool:
        """Press home button."""
        target = self._get_device_target()
        # Use simctl keychain to send home button
        result = subprocess.run(
            ["xcrun", "simctl", "io", target, "home"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0

    def press_enter(self) -> bool:
        """Press return key."""
        target = self._get_device_target()
        result = subprocess.run(
            ["xcrun", "simctl", "io", target, "sendKeyCode", "40"],  # Return key
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0

    # ========== Screen Capture ==========

    def screenshot(self, output_path: str) -> bool:
        """Take screenshot."""
        target = self._get_device_target()
        result = self._run_simctl(["io", target, "screenshot", output_path])
        return result.returncode == 0

    def get_screen_size(self) -> Tuple[int, int]:
        """Get screen dimensions."""
        # Default iPhone screen size - could be improved by querying device type
        target = self._get_device_target()
        devices = self.get_devices()

        for device in devices:
            if device.identifier == target or (target == "booted" and device.state == "booted"):
                model = device.model or ""
                # Common iPhone sizes
                if "Pro-Max" in model:
                    return (1290, 2796)
                elif "Pro" in model:
                    return (1179, 2556)
                elif "Plus" in model:
                    return (1284, 2778)
                else:
                    return (1170, 2532)  # Standard iPhone

        return (1170, 2532)  # Default

    # ========== UI Hierarchy ==========

    def dump_ui_hierarchy(self) -> str:
        """
        Dump UI hierarchy.

        Note: iOS doesn't have direct equivalent to Android's uiautomator.
        This returns the accessibility hierarchy via simctl.
        """
        target = self._get_device_target()
        # recordState returns JSON with UI info
        result = self._run_simctl(["io", target, "recordState"], timeout=30)
        return result.stdout if result.returncode == 0 else ""

    def find_element_by_text(self, text: str, exact: bool = False) -> Optional[UIElement]:
        """Find UI element by text content."""
        # iOS doesn't have easy UI introspection without XCUITest
        # This is a placeholder - would need WebDriverAgent or similar
        return None

    def find_element_by_id(self, resource_id: str) -> Optional[UIElement]:
        """Find UI element by accessibility ID."""
        # Placeholder - requires XCUITest/WebDriverAgent
        return None

    def find_elements_by_class(self, class_name: str) -> List[UIElement]:
        """Find all UI elements by class name."""
        # Placeholder - requires XCUITest/WebDriverAgent
        return []

    # ========== Logging ==========

    def pull_logs(self, output_dir: str, bundle_id: str) -> LogCollection:
        """Pull comprehensive logs from simulator."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        collection = LogCollection(output_dir=output_path)

        # Get device info
        target = self._get_device_target()
        devices = self.get_devices()
        device_info = next(
            (d for d in devices if d.identifier == target or (target == "booted" and d.state == "booted")),
            None,
        )

        if device_info:
            collection.metadata["device_name"] = device_info.name
            collection.metadata["os_version"] = device_info.os_version
            collection.metadata["device_id"] = device_info.identifier

        # Find simulator data directory
        sim_data_dir = self._get_simulator_data_dir(device_info.identifier if device_info else None)

        if sim_data_dir:
            # Find app container
            app_container = self._find_app_container(sim_data_dir, bundle_id)

            if app_container:
                # Pull app logs
                self._pull_app_logs(app_container, output_path, collection)

                # Pull databases
                self._pull_databases(app_container, output_path, collection)

                # Pull preferences
                self._pull_preferences(app_container, output_path, collection)

        # Pull system logs
        self._pull_system_logs(output_path, bundle_id, collection)

        # Pull crash logs
        self._pull_crash_logs(output_path, bundle_id, collection)

        # Save metadata
        metadata_path = output_path / "device_info.json"
        with open(metadata_path, "w") as f:
            json.dump(collection.metadata, f, indent=2, default=str)

        return collection

    def _get_simulator_data_dir(self, device_id: Optional[str] = None) -> Optional[Path]:
        """Get the simulator's data directory."""
        if device_id:
            data_dir = Path.home() / "Library/Developer/CoreSimulator/Devices" / device_id / "data"
            if data_dir.exists():
                return data_dir

        # Find booted simulator
        devices = self.get_devices()
        for device in devices:
            if device.state == "booted":
                data_dir = Path.home() / "Library/Developer/CoreSimulator/Devices" / device.identifier / "data"
                if data_dir.exists():
                    return data_dir

        return None

    def _find_app_container(self, sim_data_dir: Path, bundle_id: str) -> Optional[Path]:
        """Find app's data container in simulator."""
        containers_dir = sim_data_dir / "Containers/Data/Application"
        if not containers_dir.exists():
            return None

        for app_dir in containers_dir.iterdir():
            metadata_plist = app_dir / ".com.apple.mobile_container_manager.metadata.plist"
            if metadata_plist.exists():
                try:
                    with open(metadata_plist, "rb") as f:
                        plist = plistlib.load(f)
                        if plist.get("MCMMetadataIdentifier") == bundle_id:
                            return app_dir
                except Exception:
                    continue

        return None

    def _pull_app_logs(self, app_container: Path, output_dir: Path, collection: LogCollection):
        """Pull application log files."""
        logs_dir = output_dir / "logs"
        logs_dir.mkdir(exist_ok=True)

        # Check Documents/ciris/logs for CIRIS-specific logs
        ciris_logs = app_container / "Documents/ciris/logs"
        if ciris_logs.exists():
            for log_file in ciris_logs.glob("*.log"):
                dest = logs_dir / log_file.name
                shutil.copy2(log_file, dest)
                collection.app_logs.append(dest)

        # Also check Library/Logs
        lib_logs = app_container / "Library/Logs"
        if lib_logs.exists():
            for log_file in lib_logs.glob("*.log"):
                dest = logs_dir / log_file.name
                shutil.copy2(log_file, dest)
                collection.app_logs.append(dest)

    def _pull_databases(self, app_container: Path, output_dir: Path, collection: LogCollection):
        """Pull SQLite database files."""
        db_dir = output_dir / "databases"
        db_dir.mkdir(exist_ok=True)

        # Check Documents/ciris/databases
        ciris_dbs = app_container / "Documents/ciris/databases"
        if ciris_dbs.exists():
            for db_file in ciris_dbs.glob("*.db"):
                dest = db_dir / db_file.name
                shutil.copy2(db_file, dest)
                collection.databases.append(dest)

        # Also check Library/Application Support
        app_support = app_container / "Library/Application Support"
        if app_support.exists():
            for db_file in app_support.rglob("*.db"):
                dest = db_dir / db_file.name
                if not dest.exists():  # Avoid duplicates
                    shutil.copy2(db_file, dest)
                    collection.databases.append(dest)

    def _pull_preferences(self, app_container: Path, output_dir: Path, collection: LogCollection):
        """Pull preferences/settings files."""
        prefs_dir = output_dir / "preferences"
        prefs_dir.mkdir(exist_ok=True)

        # UserDefaults plist
        lib_prefs = app_container / "Library/Preferences"
        if lib_prefs.exists():
            for plist_file in lib_prefs.glob("*.plist"):
                dest = prefs_dir / plist_file.name
                shutil.copy2(plist_file, dest)
                collection.preferences.append(dest)

    def _pull_system_logs(self, output_dir: Path, bundle_id: str, collection: LogCollection):
        """Pull filtered system logs."""
        # Use log show to get recent logs for the app
        try:
            result = subprocess.run(
                [
                    "log",
                    "show",
                    "--predicate",
                    f'process == "{bundle_id.split(".")[-1]}" OR subsystem == "{bundle_id}"',
                    "--last",
                    "1h",
                    "--style",
                    "compact",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.stdout:
                log_path = output_dir / "system_log.txt"
                with open(log_path, "w") as f:
                    f.write(result.stdout)
                collection.system_logs.append(log_path)

        except (subprocess.TimeoutExpired, Exception) as e:
            collection.metadata["system_log_error"] = str(e)

    def _pull_crash_logs(self, output_dir: Path, bundle_id: str, collection: LogCollection):
        """Pull crash logs."""
        crash_dir = output_dir / "crashes"
        crash_dir.mkdir(exist_ok=True)

        # Check for crash logs in ~/Library/Logs/DiagnosticReports
        diag_reports = Path.home() / "Library/Logs/DiagnosticReports"
        if diag_reports.exists():
            app_name = bundle_id.split(".")[-1]
            for crash_file in diag_reports.glob(f"{app_name}*.crash"):
                dest = crash_dir / crash_file.name
                shutil.copy2(crash_file, dest)
                collection.crash_logs.append(dest)

            for crash_file in diag_reports.glob(f"{app_name}*.ips"):
                dest = crash_dir / crash_file.name
                shutil.copy2(crash_file, dest)
                collection.crash_logs.append(dest)

    def clear_logs(self) -> bool:
        """Clear is not directly supported for iOS logs."""
        return False

    def start_log_capture(self, output_path: str, bundle_id: str) -> bool:
        """Start continuous log capture."""
        try:
            app_name = bundle_id.split(".")[-1]
            self._log_process = subprocess.Popen(
                [
                    "log",
                    "stream",
                    "--predicate",
                    f'process == "{app_name}" OR subsystem == "{bundle_id}"',
                    "--style",
                    "compact",
                ],
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
        """Grant permission (limited support on simulator)."""
        target = self._get_device_target()
        # simctl privacy command
        result = self._run_simctl(["privacy", target, "grant", permission, bundle_id])
        return result.returncode == 0

    def set_property(self, key: str, value: str) -> bool:
        """Set property - not directly supported on iOS simulator."""
        return False

    def get_property(self, key: str) -> Optional[str]:
        """Get property - not directly supported on iOS simulator."""
        return None

    def forward_port(self, local_port: int, remote_port: int) -> bool:
        """Port forwarding - not needed for simulator (shares network with host)."""
        # Simulator uses localhost directly, no forwarding needed
        return True

    # ========== Simulator-Specific ==========

    def open_url(self, url: str) -> bool:
        """Open URL in simulator."""
        target = self._get_device_target()
        result = self._run_simctl(["openurl", target, url])
        return result.returncode == 0

    def set_location(self, latitude: float, longitude: float) -> bool:
        """Set simulated location."""
        target = self._get_device_target()
        result = self._run_simctl(
            ["location", target, "set", f"{latitude},{longitude}"]
        )
        return result.returncode == 0

    def push_notification(self, bundle_id: str, payload: dict) -> bool:
        """Send push notification to app."""
        target = self._get_device_target()
        payload_str = json.dumps(payload)
        result = self._run_simctl(
            ["push", target, bundle_id, "-"],
            timeout=10,
        )
        # Would need to pipe payload_str to stdin
        return result.returncode == 0
