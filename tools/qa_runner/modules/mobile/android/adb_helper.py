"""
Android Device Helper Adapter

Wraps the existing ADBHelper to implement the cross-platform DeviceHelper interface.
"""

import os
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
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


class ADBDeviceHelper(DeviceHelper):
    """Android device helper using ADB."""

    platform = Platform.ANDROID

    def __init__(
        self,
        adb_path: Optional[str] = None,
        device_serial: Optional[str] = None,
    ):
        """
        Initialize ADB helper.

        Args:
            adb_path: Path to adb binary. Auto-detected if not provided.
            device_serial: Specific device serial to target.
        """
        self.adb_path = adb_path or self._find_adb()
        self.device_serial = device_serial
        self._log_process: Optional[subprocess.Popen] = None
        self._verify_adb()

    def _find_adb(self) -> str:
        """Find ADB binary in common locations."""
        common_paths = [
            os.path.expanduser("~/Android/Sdk/platform-tools/adb"),
            "/usr/bin/adb",
            "/usr/local/bin/adb",
            os.path.expandvars("$ANDROID_HOME/platform-tools/adb"),
            os.path.expandvars("$ANDROID_SDK_ROOT/platform-tools/adb"),
        ]

        for path in common_paths:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path

        try:
            result = subprocess.run(["which", "adb"], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

        raise RuntimeError("ADB not found. Install Android SDK or set adb_path.")

    def _verify_adb(self):
        """Verify ADB is working."""
        result = self._run_adb(["version"])
        if result.returncode != 0:
            raise RuntimeError(f"ADB verification failed: {result.stderr}")

    def _run_adb(
        self,
        args: List[str],
        timeout: int = 30,
    ) -> subprocess.CompletedProcess:
        """Run an ADB command."""
        cmd = [self.adb_path]
        if self.device_serial:
            cmd.extend(["-s", self.device_serial])
        cmd.extend(args)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    # ========== Device Management ==========

    def get_devices(self) -> List[DeviceInfo]:
        """Get list of connected Android devices."""
        result = self._run_adb(["devices", "-l"])
        devices = []

        for line in result.stdout.strip().split("\n")[1:]:
            if not line.strip():
                continue

            parts = line.split()
            if len(parts) >= 2:
                serial = parts[0]
                state = parts[1]

                # Parse model from device properties
                model = None
                for part in parts[2:]:
                    if part.startswith("model:"):
                        model = part.split(":", 1)[1]
                        break

                # Get Android version
                android_version = None
                try:
                    ver_result = subprocess.run(
                        [self.adb_path, "-s", serial, "shell", "getprop", "ro.build.version.release"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if ver_result.returncode == 0:
                        android_version = ver_result.stdout.strip()
                except Exception:
                    pass

                devices.append(
                    DeviceInfo(
                        identifier=serial,
                        state=state,
                        platform=Platform.ANDROID,
                        name=model,
                        os_version=android_version,
                        model=model,
                    )
                )

        return devices

    def is_device_connected(self) -> bool:
        """Check if device is connected and ready."""
        devices = self.get_devices()
        if self.device_serial:
            return any(d.identifier == self.device_serial and d.state == "device" for d in devices)
        return any(d.state == "device" for d in devices)

    def wait_for_device(self, timeout: int = 60) -> bool:
        """Wait for device to become available."""
        try:
            self._run_adb(["wait-for-device"], timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            return False

    # ========== App Management ==========

    def install_app(self, app_path: str, reinstall: bool = True) -> bool:
        """Install APK on device."""
        args = ["install"]
        if reinstall:
            args.append("-r")
        args.append(app_path)

        result = self._run_adb(args, timeout=120)
        return "Success" in result.stdout

    def uninstall_app(self, bundle_id: str) -> bool:
        """Uninstall app from device."""
        result = self._run_adb(["uninstall", bundle_id])
        return result.returncode == 0

    def launch_app(self, bundle_id: str, activity: Optional[str] = None) -> bool:
        """Launch app on device."""
        if activity:
            component = f"{bundle_id}/{activity}"
        else:
            component = f"{bundle_id}/.MainActivity"

        result = self._run_adb([
            "shell", "am", "start",
            "-n", component,
        ])
        return result.returncode == 0

    def force_stop_app(self, bundle_id: str) -> bool:
        """Force stop app."""
        result = self._run_adb(["shell", "am", "force-stop", bundle_id])
        return result.returncode == 0

    def clear_app_data(self, bundle_id: str) -> bool:
        """Clear app data and cache."""
        result = self._run_adb(["shell", "pm", "clear", bundle_id])
        return "Success" in result.stdout

    def is_app_installed(self, bundle_id: str) -> bool:
        """Check if app is installed."""
        result = self._run_adb(["shell", "pm", "list", "packages", bundle_id])
        return f"package:{bundle_id}" in result.stdout

    def is_app_running(self, bundle_id: str) -> bool:
        """Check if app is running."""
        result = self._run_adb(["shell", "pidof", bundle_id])
        return result.returncode == 0 and result.stdout.strip()

    # ========== UI Interaction ==========

    def tap(self, x: int, y: int) -> bool:
        """Tap at coordinates."""
        result = self._run_adb(["shell", "input", "tap", str(x), str(y)])
        return result.returncode == 0

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> bool:
        """Swipe gesture."""
        result = self._run_adb([
            "shell", "input", "swipe",
            str(x1), str(y1), str(x2), str(y2), str(duration_ms),
        ])
        return result.returncode == 0

    def input_text(self, text: str) -> bool:
        """Input text."""
        # Escape special characters
        escaped = text.replace(" ", "%s").replace("'", "\\'").replace('"', '\\"')
        result = self._run_adb(["shell", "input", "text", escaped])
        return result.returncode == 0

    def press_back(self) -> bool:
        """Press back button."""
        result = self._run_adb(["shell", "input", "keyevent", "4"])
        return result.returncode == 0

    def press_home(self) -> bool:
        """Press home button."""
        result = self._run_adb(["shell", "input", "keyevent", "3"])
        return result.returncode == 0

    def press_enter(self) -> bool:
        """Press enter key."""
        result = self._run_adb(["shell", "input", "keyevent", "66"])
        return result.returncode == 0

    # ========== Screen Capture ==========

    def screenshot(self, output_path: str) -> bool:
        """Take screenshot."""
        # Capture to device then pull
        device_path = "/sdcard/screenshot.png"
        result = self._run_adb(["shell", "screencap", "-p", device_path])
        if result.returncode != 0:
            return False

        result = self._run_adb(["pull", device_path, output_path])
        self._run_adb(["shell", "rm", device_path])
        return result.returncode == 0

    def get_screen_size(self) -> Tuple[int, int]:
        """Get screen dimensions."""
        result = self._run_adb(["shell", "wm", "size"])
        match = re.search(r"(\d+)x(\d+)", result.stdout)
        if match:
            return (int(match.group(1)), int(match.group(2)))
        return (1080, 1920)  # Default

    # ========== UI Hierarchy ==========

    def dump_ui_hierarchy(self) -> str:
        """Dump UI hierarchy as XML."""
        device_path = "/sdcard/window_dump.xml"
        self._run_adb(["shell", "uiautomator", "dump", device_path])

        result = self._run_adb(["shell", "cat", device_path])
        self._run_adb(["shell", "rm", device_path])
        return result.stdout

    def _parse_ui_element(self, node: ET.Element) -> UIElement:
        """Parse XML node to UIElement."""
        bounds_str = node.get("bounds", "[0,0][0,0]")
        bounds_match = re.findall(r"\[(\d+),(\d+)\]", bounds_str)
        if len(bounds_match) >= 2:
            bounds = (
                int(bounds_match[0][0]),
                int(bounds_match[0][1]),
                int(bounds_match[1][0]),
                int(bounds_match[1][1]),
            )
        else:
            bounds = (0, 0, 0, 0)

        return UIElement(
            resource_id=node.get("resource-id", ""),
            text=node.get("text", ""),
            content_desc=node.get("content-desc", ""),
            class_name=node.get("class", ""),
            bounds=bounds,
            clickable=node.get("clickable") == "true",
            enabled=node.get("enabled") == "true",
            focused=node.get("focused") == "true",
            checkable=node.get("checkable") == "true",
            checked=node.get("checked") == "true",
            scrollable=node.get("scrollable") == "true",
            package=node.get("package", ""),
        )

    def find_element_by_text(self, text: str, exact: bool = False) -> Optional[UIElement]:
        """Find element by text."""
        xml_str = self.dump_ui_hierarchy()
        try:
            root = ET.fromstring(xml_str)
            for node in root.iter("node"):
                node_text = node.get("text", "")
                if exact:
                    if node_text == text:
                        return self._parse_ui_element(node)
                else:
                    if text.lower() in node_text.lower():
                        return self._parse_ui_element(node)
        except ET.ParseError:
            pass
        return None

    def find_element_by_id(self, resource_id: str) -> Optional[UIElement]:
        """Find element by resource ID."""
        xml_str = self.dump_ui_hierarchy()
        try:
            root = ET.fromstring(xml_str)
            for node in root.iter("node"):
                if resource_id in node.get("resource-id", ""):
                    return self._parse_ui_element(node)
        except ET.ParseError:
            pass
        return None

    def find_elements_by_class(self, class_name: str) -> List[UIElement]:
        """Find all elements by class name."""
        elements = []
        xml_str = self.dump_ui_hierarchy()
        try:
            root = ET.fromstring(xml_str)
            for node in root.iter("node"):
                if class_name in node.get("class", ""):
                    elements.append(self._parse_ui_element(node))
        except ET.ParseError:
            pass
        return elements

    # ========== Logging ==========

    def pull_logs(self, output_dir: str, bundle_id: str) -> LogCollection:
        """Pull comprehensive logs from device."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        collection = LogCollection(output_dir=output_path)

        # Get device info
        devices = self.get_devices()
        device = next((d for d in devices if d.identifier == self.device_serial or not self.device_serial), None)
        if device:
            collection.metadata["device_model"] = device.model
            collection.metadata["android_version"] = device.os_version
            collection.metadata["device_serial"] = device.identifier

        # Get app info
        pkg_info = self._run_adb(["shell", "dumpsys", "package", bundle_id])
        collection.metadata["package_info"] = pkg_info.stdout[:2000]  # Truncate

        # Pull logcat - Python logs
        python_log = output_path / "logcat_python.txt"
        result = self._run_adb([
            "logcat", "-d", "-v", "time", "-s",
            "python.stdout:V", "python.stderr:V",
        ], timeout=60)
        with open(python_log, "w") as f:
            f.write(result.stdout)
        collection.system_logs.append(python_log)

        # Pull logcat - App logs
        app_log = output_path / "logcat_app.txt"
        result = self._run_adb([
            "logcat", "-d", "-v", "time", "-s",
            "CIRISApp:V", "MainActivity:V", "PythonRuntime:V",
            "EnvFileUpdater:V", "TokenManager:V", "BillingViewModel:V",
        ], timeout=60)
        with open(app_log, "w") as f:
            f.write(result.stdout)
        collection.system_logs.append(app_log)

        # Pull logcat - Crashes
        crash_log = output_path / "logcat_crashes.txt"
        result = self._run_adb([
            "logcat", "-d", "-v", "time", "-s", "AndroidRuntime:E",
        ], timeout=60)
        with open(crash_log, "w") as f:
            f.write(result.stdout)
        if result.stdout.strip():
            collection.crash_logs.append(crash_log)

        # Try to pull app files (debug builds only)
        self._pull_debug_files(bundle_id, output_path, collection)

        # Save metadata
        metadata_path = output_path / "device_info.json"
        import json
        with open(metadata_path, "w") as f:
            json.dump(collection.metadata, f, indent=2, default=str)

        return collection

    def _pull_debug_files(self, bundle_id: str, output_path: Path, collection: LogCollection):
        """Pull files from debug build app directory."""
        # Get app files directory
        result = self._run_adb(["shell", "run-as", bundle_id, "ls", "files/"])
        if result.returncode != 0:
            collection.metadata["debug_access"] = "denied"
            return

        collection.metadata["debug_access"] = "granted"

        # Pull log files
        logs_dir = output_path / "logs"
        logs_dir.mkdir(exist_ok=True)

        log_files = ["latest.log", "incidents_latest.log", "ciris.log"]
        for log_name in log_files:
            result = self._run_adb([
                "shell", "run-as", bundle_id,
                "cat", f"files/logs/{log_name}",
            ], timeout=30)
            if result.returncode == 0 and result.stdout.strip():
                log_path = logs_dir / log_name
                with open(log_path, "w") as f:
                    f.write(result.stdout)
                collection.app_logs.append(log_path)

        # Pull databases
        db_dir = output_path / "databases"
        db_dir.mkdir(exist_ok=True)

        db_list = self._run_adb([
            "shell", "run-as", bundle_id,
            "find", "files/", "-name", "*.db",
        ])
        for db_path in db_list.stdout.strip().split("\n"):
            if db_path.strip():
                db_name = Path(db_path).name
                # Copy to temp then pull
                temp_path = f"/sdcard/{db_name}"
                self._run_adb(["shell", "run-as", bundle_id, "cp", db_path, temp_path])
                result = self._run_adb(["pull", temp_path, str(db_dir / db_name)])
                self._run_adb(["shell", "rm", temp_path])
                if result.returncode == 0:
                    collection.databases.append(db_dir / db_name)

        # Pull preferences
        prefs_dir = output_path / "prefs"
        prefs_dir.mkdir(exist_ok=True)

        prefs_list = self._run_adb([
            "shell", "run-as", bundle_id,
            "ls", "shared_prefs/",
        ])
        for pref_name in prefs_list.stdout.strip().split("\n"):
            if pref_name.strip() and pref_name.endswith(".xml"):
                result = self._run_adb([
                    "shell", "run-as", bundle_id,
                    "cat", f"shared_prefs/{pref_name}",
                ])
                if result.returncode == 0:
                    pref_path = prefs_dir / pref_name
                    with open(pref_path, "w") as f:
                        f.write(result.stdout)
                    collection.preferences.append(pref_path)

        # Pull .env file (redact tokens)
        result = self._run_adb([
            "shell", "run-as", bundle_id,
            "cat", "files/.env",
        ])
        if result.returncode == 0 and result.stdout.strip():
            env_path = output_path / "env_file.txt"
            # Redact sensitive values
            env_content = result.stdout
            env_content = re.sub(
                r'(OPENAI_API_KEY|GOOGLE_ID_TOKEN|ACCESS_TOKEN)=.*',
                r'\1=[REDACTED]',
                env_content,
            )
            with open(env_path, "w") as f:
                f.write(env_content)

    def clear_logs(self) -> bool:
        """Clear logcat."""
        result = self._run_adb(["logcat", "-c"])
        return result.returncode == 0

    def start_log_capture(self, output_path: str, bundle_id: str) -> bool:
        """Start continuous logcat capture."""
        try:
            self._log_process = subprocess.Popen(
                [
                    self.adb_path, "-s", self.device_serial or "",
                    "logcat", "-v", "time",
                ],
                stdout=open(output_path, "w"),
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            return False

    def stop_log_capture(self) -> bool:
        """Stop logcat capture."""
        if self._log_process:
            self._log_process.terminate()
            self._log_process = None
            return True
        return False

    # ========== Utilities ==========

    def grant_permission(self, bundle_id: str, permission: str) -> bool:
        """Grant permission to app."""
        result = self._run_adb([
            "shell", "pm", "grant", bundle_id, permission,
        ])
        return result.returncode == 0

    def set_property(self, key: str, value: str) -> bool:
        """Set system property."""
        result = self._run_adb(["shell", "setprop", key, value])
        return result.returncode == 0

    def get_property(self, key: str) -> Optional[str]:
        """Get system property."""
        result = self._run_adb(["shell", "getprop", key])
        return result.stdout.strip() if result.returncode == 0 else None

    def forward_port(self, local_port: int, remote_port: int) -> bool:
        """Forward local port to device."""
        result = self._run_adb([
            "forward", f"tcp:{local_port}", f"tcp:{remote_port}",
        ])
        return result.returncode == 0
