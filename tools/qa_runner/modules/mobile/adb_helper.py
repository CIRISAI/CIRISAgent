"""
ADB Helper for Mobile QA Testing

Provides utilities for interacting with Android devices via ADB.
"""

import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class DeviceInfo:
    """Information about a connected Android device."""

    serial: str
    state: str
    model: Optional[str] = None
    android_version: Optional[str] = None


@dataclass
class UINode:
    """Represents a UI node from UI Automator dump."""

    resource_id: str
    text: str
    content_desc: str
    class_name: str
    bounds: Tuple[int, int, int, int]  # left, top, right, bottom
    clickable: bool
    enabled: bool


class ADBHelper:
    """Helper class for ADB operations."""

    def __init__(self, adb_path: Optional[str] = None, device_serial: Optional[str] = None):
        """
        Initialize ADB helper.

        Args:
            adb_path: Path to adb binary. Auto-detected if not provided.
            device_serial: Specific device serial to target. Uses default if not provided.
        """
        self.adb_path = adb_path or self._find_adb()
        self.device_serial = device_serial
        self._verify_adb()

    def _find_adb(self) -> str:
        """Find ADB binary in common locations."""
        # Check common locations
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

        # Try to find in PATH
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

    def _run_adb(self, args: List[str], timeout: int = 30) -> subprocess.CompletedProcess:
        """Run an ADB command."""
        cmd = [self.adb_path]
        if self.device_serial:
            cmd.extend(["-s", self.device_serial])
        cmd.extend(args)

        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def get_devices(self) -> List[DeviceInfo]:
        """Get list of connected devices."""
        result = self._run_adb(["devices", "-l"])
        devices = []

        for line in result.stdout.strip().split("\n")[1:]:
            if not line.strip():
                continue

            parts = line.split()
            if len(parts) >= 2:
                serial = parts[0]
                state = parts[1]

                # Extract model if available
                model = None
                for part in parts[2:]:
                    if part.startswith("model:"):
                        model = part.split(":")[1]
                        break

                devices.append(DeviceInfo(serial=serial, state=state, model=model))

        return devices

    def is_device_connected(self) -> bool:
        """Check if a device is connected and ready."""
        devices = self.get_devices()
        if self.device_serial:
            return any(d.serial == self.device_serial and d.state == "device" for d in devices)
        return any(d.state == "device" for d in devices)

    def wait_for_device(self, timeout: int = 60) -> bool:
        """Wait for a device to be connected."""
        start = time.time()
        while time.time() - start < timeout:
            if self.is_device_connected():
                return True
            time.sleep(1)
        return False

    def install_apk(self, apk_path: str, reinstall: bool = True) -> bool:
        """Install an APK on the device."""
        args = ["install"]
        if reinstall:
            args.append("-r")
        args.append(apk_path)

        result = self._run_adb(args, timeout=120)
        return "Success" in result.stdout

    def uninstall_app(self, package: str) -> bool:
        """Uninstall an app."""
        result = self._run_adb(["uninstall", package])
        return result.returncode == 0

    def launch_app(self, package: str, activity: str) -> bool:
        """Launch an app activity."""
        result = self._run_adb(["shell", "am", "start", "-n", f"{package}/{activity}"])
        return result.returncode == 0

    def force_stop_app(self, package: str) -> bool:
        """Force stop an app."""
        result = self._run_adb(["shell", "am", "force-stop", package])
        return result.returncode == 0

    def clear_app_data(self, package: str) -> bool:
        """Clear app data."""
        result = self._run_adb(["shell", "pm", "clear", package])
        return "Success" in result.stdout

    def is_app_running(self, package: str) -> bool:
        """Check if an app is currently running."""
        result = self._run_adb(["shell", "pidof", package])
        return result.returncode == 0 and result.stdout.strip()

    def get_current_activity(self) -> Optional[str]:
        """Get the currently focused activity."""
        result = self._run_adb(["shell", "dumpsys", "activity", "activities", "|", "grep", "mResumedActivity"])
        # Parse output like: mResumedActivity: ActivityRecord{...package/.Activity...}
        match = re.search(r"(\w+\.\w+)/(\.\w+|\w+)", result.stdout)
        if match:
            return f"{match.group(1)}/{match.group(2)}"
        return None

    def tap(self, x: int, y: int) -> bool:
        """Tap at coordinates."""
        result = self._run_adb(["shell", "input", "tap", str(x), str(y)])
        return result.returncode == 0

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> bool:
        """Swipe from one point to another."""
        result = self._run_adb(["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms)])
        return result.returncode == 0

    def input_text(self, text: str) -> bool:
        """Input text (escapes special characters)."""
        # Escape special characters for shell
        escaped = text.replace(" ", "%s").replace("'", "\\'").replace('"', '\\"')
        result = self._run_adb(["shell", "input", "text", escaped])
        return result.returncode == 0

    def press_key(self, keycode: str) -> bool:
        """Press a key by keycode name or number."""
        result = self._run_adb(["shell", "input", "keyevent", keycode])
        return result.returncode == 0

    def press_back(self) -> bool:
        """Press the back button."""
        return self.press_key("KEYCODE_BACK")

    def press_home(self) -> bool:
        """Press the home button."""
        return self.press_key("KEYCODE_HOME")

    def press_enter(self) -> bool:
        """Press the enter key."""
        return self.press_key("KEYCODE_ENTER")

    def get_screen_size(self) -> Tuple[int, int]:
        """Get screen width and height."""
        result = self._run_adb(["shell", "wm", "size"])
        match = re.search(r"(\d+)x(\d+)", result.stdout)
        if match:
            return int(match.group(1)), int(match.group(2))
        return 1080, 1920  # Default

    def screenshot(self, output_path: str) -> bool:
        """Take a screenshot."""
        # Capture on device
        result = self._run_adb(["shell", "screencap", "-p", "/sdcard/screenshot.png"])
        if result.returncode != 0:
            return False

        # Pull to local
        result = self._run_adb(["pull", "/sdcard/screenshot.png", output_path])
        if result.returncode != 0:
            return False

        # Clean up
        self._run_adb(["shell", "rm", "/sdcard/screenshot.png"])
        return True

    def dump_ui_hierarchy(self, output_path: Optional[str] = None) -> str:
        """Dump UI hierarchy to XML."""
        device_path = "/sdcard/window_dump.xml"

        # Dump on device
        result = self._run_adb(["shell", "uiautomator", "dump", device_path])
        if result.returncode != 0:
            raise RuntimeError(f"UI dump failed: {result.stderr}")

        # Read content
        result = self._run_adb(["shell", "cat", device_path])
        xml_content = result.stdout

        # Clean up
        self._run_adb(["shell", "rm", device_path])

        # Optionally save to file
        if output_path:
            with open(output_path, "w") as f:
                f.write(xml_content)

        return xml_content

    def get_logcat(self, filter_tag: Optional[str] = None, lines: int = 100) -> str:
        """Get logcat output."""
        args = ["logcat", "-d", "-t", str(lines)]
        if filter_tag:
            args.extend(["-s", filter_tag])
        result = self._run_adb(args)
        return result.stdout

    def clear_logcat(self) -> bool:
        """Clear logcat buffer."""
        result = self._run_adb(["logcat", "-c"])
        return result.returncode == 0

    def start_logcat_capture(self, output_path: str, filter_tags: Optional[List[str]] = None):
        """Start capturing logcat to a file in background."""
        args = [self.adb_path]
        if self.device_serial:
            args.extend(["-s", self.device_serial])
        args.extend(["logcat"])
        if filter_tags:
            args.extend(["-s"] + filter_tags)

        with open(output_path, "w") as f:
            return subprocess.Popen(args, stdout=f, stderr=subprocess.STDOUT)

    def grant_permission(self, package: str, permission: str) -> bool:
        """Grant a permission to an app."""
        result = self._run_adb(["shell", "pm", "grant", package, permission])
        return result.returncode == 0

    def set_prop(self, prop: str, value: str) -> bool:
        """Set a system property."""
        result = self._run_adb(["shell", "setprop", prop, value])
        return result.returncode == 0

    def forward_port(self, local_port: int, remote_port: int) -> bool:
        """Forward a local port to device port."""
        result = self._run_adb(["forward", f"tcp:{local_port}", f"tcp:{remote_port}"])
        return result.returncode == 0

    def can_run_as(self, package: str) -> bool:
        """Check if run-as works for this package (debug build)."""
        result = self._run_adb(["shell", "run-as", package, "ls"])
        return result.returncode == 0

    def pull_device_logs(self, output_dir: str, package: str = "ai.ciris.mobile", verbose: bool = True) -> dict:
        """
        Pull comprehensive logs and files from device.

        Collects:
        - Python logs (latest.log, incidents_latest.log)
        - Database files (.db)
        - Shared preferences (.xml)
        - Logcat output (python, crashes, app logs)
        - App info and storage usage

        Args:
            output_dir: Base directory for output (timestamp subfolder created)
            package: Android package name
            verbose: Print progress messages

        Returns:
            Dict with collected file paths and metadata
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path(output_dir) / timestamp
        output_path.mkdir(parents=True, exist_ok=True)

        results = {
            "timestamp": timestamp,
            "output_dir": str(output_path),
            "files": [],
            "errors": [],
        }

        def log(msg: str):
            if verbose:
                print(f"  {msg}")

        # Paths
        app_data = f"/data/data/{package}"
        app_files = f"{app_data}/files"
        logs_dir = f"{app_files}/ciris/logs"
        prefs_dir = f"{app_data}/shared_prefs"

        # Check if debug build (run-as available)
        can_run_as = self.can_run_as(package)
        if verbose:
            if can_run_as:
                print("[INFO] Debug build detected - full file access available")
            else:
                print("[WARN] Release build detected - limited file access (logcat only)")

        # 1. App Info
        log("Collecting app info...")
        app_info_path = output_path / "app_info.txt"
        with open(app_info_path, "w") as f:
            f.write("=== Device Info ===\n")
            result = self._run_adb(["shell", "getprop", "ro.product.model"])
            f.write(f"Model: {result.stdout.strip()}\n")
            result = self._run_adb(["shell", "getprop", "ro.build.version.release"])
            f.write(f"Android: {result.stdout.strip()}\n\n")

            f.write("=== Package Info ===\n")
            result = self._run_adb(["shell", "dumpsys", "package", package])
            for line in result.stdout.split("\n"):
                if any(k in line for k in ["versionName", "versionCode", "firstInstallTime", "lastUpdateTime"]):
                    f.write(f"{line.strip()}\n")
            f.write("\n")

            f.write("=== Process Info ===\n")
            result = self._run_adb(["shell", "ps", "-A"])
            for line in result.stdout.split("\n"):
                if "python" in line.lower() or "ciris" in line.lower():
                    f.write(f"{line}\n")
        results["files"].append(str(app_info_path))
        log(f"app_info.txt")

        # 2. Logcat - Python output
        log("Collecting logcat...")
        logcat_python = output_path / "logcat_python.txt"
        result = self._run_adb(["logcat", "-d", "-v", "time", "python.stdout:*", "python.stderr:*", "*:S"])
        with open(logcat_python, "w") as f:
            f.write(result.stdout)
        results["files"].append(str(logcat_python))
        log("logcat_python.txt")

        # Logcat - Crashes
        logcat_crashes = output_path / "logcat_crashes.txt"
        result = self._run_adb(["logcat", "-d", "-v", "time", "AndroidRuntime:E", "*:S"])
        with open(logcat_crashes, "w") as f:
            f.write(result.stdout)
        results["files"].append(str(logcat_crashes))
        log("logcat_crashes.txt")

        # Logcat - App logs (CIRISApp, MainActivity, EnvFileUpdater, etc.)
        logcat_app = output_path / "logcat_app.txt"
        result = self._run_adb(
            [
                "logcat",
                "-d",
                "-v",
                "time",
                "CIRISApp:*",
                "MainActivity:*",
                "EnvFileUpdater:*",
                "TokenManager:*",
                "FirstRunDetector:*",
                "BillingViewModel:*",
                "PythonRuntime:*",
                "*:S",
            ]
        )
        with open(logcat_app, "w") as f:
            f.write(result.stdout)
        results["files"].append(str(logcat_app))
        log("logcat_app.txt")

        # Logcat - Combined
        logcat_combined = output_path / "logcat_combined.txt"
        result = self._run_adb(
            [
                "logcat",
                "-d",
                "-v",
                "time",
                "CIRISApp:*",
                "MainActivity:*",
                "EnvFileUpdater:*",
                "python.stdout:*",
                "python.stderr:*",
                "chromium:*",
                "WebViewFactory:*",
                "*:S",
            ]
        )
        with open(logcat_combined, "w") as f:
            f.write(result.stdout)
        results["files"].append(str(logcat_combined))
        log("logcat_combined.txt")

        # If we have run-as access, get more files
        if can_run_as:
            # 3. Python log files
            log("Collecting Python logs...")
            logs_path = output_path / "logs"
            logs_path.mkdir(exist_ok=True)

            for log_file in ["latest.log", "incidents_latest.log", "ciris.log"]:
                result = self._run_adb(["shell", "run-as", package, "cat", f"{logs_dir}/{log_file}"])
                if result.returncode == 0 and result.stdout.strip():
                    file_path = logs_path / log_file
                    with open(file_path, "w") as f:
                        f.write(result.stdout)
                    results["files"].append(str(file_path))
                    log(f"logs/{log_file}")

            # 4. Database files
            log("Collecting database files...")
            db_path = output_path / "databases"
            db_path.mkdir(exist_ok=True)

            result = self._run_adb(["shell", "run-as", package, "find", app_files, "-name", "*.db"])
            if result.returncode == 0:
                for db_file in result.stdout.strip().split("\n"):
                    db_file = db_file.strip()
                    if db_file:
                        basename = os.path.basename(db_file)
                        # Use binary mode for database files
                        cmd = [self.adb_path]
                        if self.device_serial:
                            cmd.extend(["-s", self.device_serial])
                        cmd.extend(["shell", "run-as", package, "cat", db_file])
                        db_result = subprocess.run(cmd, capture_output=True, timeout=30)
                        if db_result.returncode == 0:
                            file_path = db_path / basename
                            with open(file_path, "wb") as f:
                                f.write(db_result.stdout)
                            results["files"].append(str(file_path))
                            log(f"databases/{basename}")

            # 5. Shared preferences
            log("Collecting shared preferences...")
            prefs_path = output_path / "prefs"
            prefs_path.mkdir(exist_ok=True)

            result = self._run_adb(["shell", "run-as", package, "ls", prefs_dir])
            if result.returncode == 0:
                for pref_file in result.stdout.strip().split("\n"):
                    pref_file = pref_file.strip()
                    if pref_file.endswith(".xml"):
                        pref_result = self._run_adb(["shell", "run-as", package, "cat", f"{prefs_dir}/{pref_file}"])
                        if pref_result.returncode == 0:
                            file_path = prefs_path / pref_file
                            with open(file_path, "w") as f:
                                f.write(pref_result.stdout)
                            results["files"].append(str(file_path))
                            log(f"prefs/{pref_file}")

            # 6. .env file (for debugging token issues)
            log("Collecting .env file...")
            env_result = self._run_adb(["shell", "run-as", package, "cat", f"{app_files}/ciris/.env"])
            if env_result.returncode == 0 and env_result.stdout.strip():
                env_path = output_path / "env_file.txt"
                with open(env_path, "w") as f:
                    # Redact sensitive tokens but show their presence
                    content = env_result.stdout
                    import re

                    # Redact long token values but show they exist
                    content = re.sub(r'(CIRIS_BILLING_GOOGLE_ID_TOKEN=")[^"]{20,}(")', r"\1[REDACTED]\2", content)
                    content = re.sub(r'(OPENAI_API_KEY=")[^"]{20,}(")', r"\1[REDACTED]\2", content)
                    f.write(content)
                results["files"].append(str(env_path))
                log("env_file.txt (tokens redacted)")

            # 7. File listing
            log("Collecting file listing...")
            result = self._run_adb(["shell", "run-as", package, "find", app_files, "-type", "f"])
            if result.returncode == 0:
                file_list_path = output_path / "file_listing.txt"
                with open(file_list_path, "w") as f:
                    f.write(result.stdout)
                results["files"].append(str(file_list_path))
                log("file_listing.txt")

        if verbose:
            print(f"\n[SUCCESS] Logs saved to: {output_path}")
            print(f"  Total files: {len(results['files'])}")

        return results
