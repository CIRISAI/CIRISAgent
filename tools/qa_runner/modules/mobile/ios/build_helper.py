"""
iOS Build and Deploy Helper.

Provides utilities for building, installing, and launching iOS apps
on both simulators and physical devices.
"""

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..device_helper import DeviceInfo, Platform


class iOSTarget(Enum):
    """iOS build target type."""
    SIMULATOR = "simulator"
    DEVICE = "device"


@dataclass
class iOSBuildConfig:
    """Configuration for iOS builds."""
    project_path: Path
    scheme: str = "iosApp"
    configuration: str = "Debug"
    bundle_id: str = "ai.ciris.mobile"

    # Auto-detected paths
    ciris_root: Optional[Path] = None
    derived_data_path: Optional[Path] = None

    # Build options
    prepare_bundle: bool = True
    clean_build: bool = False
    verbose: bool = False

    def __post_init__(self):
        if self.ciris_root is None:
            # Derive CIRIS root from project path
            # project_path = .../mobile/iosApp
            self.ciris_root = self.project_path.parent.parent

        if self.derived_data_path is None:
            # Standard Xcode DerivedData location
            self.derived_data_path = Path.home() / "Library/Developer/Xcode/DerivedData"


@dataclass
class iOSBuildResult:
    """Result of an iOS build operation."""
    success: bool
    app_path: Optional[Path] = None
    target: Optional[iOSTarget] = None
    build_time: float = 0.0
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


class iOSBuildHelper:
    """Helper class for iOS build and deploy operations."""

    def __init__(self, config: Optional[iOSBuildConfig] = None):
        """Initialize with optional config, auto-detecting paths if not provided."""
        if config is None:
            # Try to find the iOS project
            config = self._auto_detect_config()
        self.config = config
        self._verify_tools()

    def _auto_detect_config(self) -> iOSBuildConfig:
        """Auto-detect iOS project configuration."""
        # Try common locations
        candidates = [
            Path.cwd() / "mobile" / "iosApp",
            Path.cwd().parent / "mobile" / "iosApp",
            Path(__file__).parent.parent.parent.parent.parent.parent / "mobile" / "iosApp",
        ]

        for candidate in candidates:
            if (candidate / "iosApp.xcodeproj").exists():
                return iOSBuildConfig(project_path=candidate)

        raise RuntimeError(
            "Could not auto-detect iOS project. "
            "Please run from CIRISAgent directory or provide explicit config."
        )

    def _verify_tools(self) -> None:
        """Verify required build tools are available."""
        required = ["xcodebuild", "xcrun"]
        for tool in required:
            result = subprocess.run(
                ["which", tool],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Required tool not found: {tool}")

    def _run_command(
        self,
        cmd: List[str],
        cwd: Optional[Path] = None,
        timeout: int = 600,
        capture: bool = True,
    ) -> subprocess.CompletedProcess:
        """Run a command with optional output capture."""
        if self.config.verbose:
            print(f"[CMD] {' '.join(cmd)}")

        return subprocess.run(
            cmd,
            cwd=cwd or self.config.project_path,
            capture_output=capture,
            text=True,
            timeout=timeout,
        )

    # ========== Device Discovery ==========

    def get_simulators(self) -> List[DeviceInfo]:
        """Get available iOS simulators."""
        result = self._run_command(
            ["xcrun", "simctl", "list", "devices", "--json"],
        )
        if result.returncode != 0:
            return []

        devices = []
        try:
            data = json.loads(result.stdout)
            for runtime, device_list in data.get("devices", {}).items():
                # Extract iOS version from runtime
                # e.g., "com.apple.CoreSimulator.SimRuntime.iOS-17-0"
                ios_version = None
                if "iOS" in runtime:
                    parts = runtime.split("iOS-")
                    if len(parts) > 1:
                        ios_version = parts[1].replace("-", ".")

                for device in device_list:
                    if device.get("isAvailable", False):
                        devices.append(DeviceInfo(
                            identifier=device["udid"],
                            state="booted" if device["state"] == "Booted" else "available",
                            platform=Platform.IOS,
                            name=device["name"],
                            os_version=ios_version,
                            model=device.get("deviceTypeIdentifier", "").split(".")[-1],
                        ))
        except (json.JSONDecodeError, KeyError):
            pass

        return devices

    def get_physical_devices(self) -> List[DeviceInfo]:
        """Get connected physical iOS devices."""
        result = self._run_command(
            ["xcrun", "devicectl", "list", "devices", "--json-output", "/dev/stdout"],
        )
        if result.returncode != 0:
            return []

        devices = []
        try:
            data = json.loads(result.stdout)
            for device in data.get("result", {}).get("devices", []):
                conn_props = device.get("connectionProperties", {})
                dev_props = device.get("deviceProperties", {})
                hw_props = device.get("hardwareProperties", {})

                is_connected = conn_props.get("tunnelState") == "connected"

                devices.append(DeviceInfo(
                    identifier=device.get("identifier", ""),
                    state="device" if is_connected else "offline",
                    platform=Platform.IOS,
                    name=dev_props.get("name"),
                    os_version=dev_props.get("osVersionNumber"),
                    model=hw_props.get("marketingName"),
                ))
        except (json.JSONDecodeError, KeyError):
            pass

        return devices

    def get_all_devices(self) -> Tuple[List[DeviceInfo], List[DeviceInfo]]:
        """Get all available devices (physical and simulators)."""
        physical = self.get_physical_devices()
        simulators = self.get_simulators()
        return physical, simulators

    def select_device(
        self,
        device_id: Optional[str] = None,
        prefer_physical: bool = True,
    ) -> Tuple[Optional[DeviceInfo], iOSTarget]:
        """Select a device to target, with optional preference."""
        physical, simulators = self.get_all_devices()

        # Filter to available/booted devices
        connected_physical = [d for d in physical if d.state == "device"]
        booted_simulators = [d for d in simulators if d.state == "booted"]

        # If specific device requested, find it
        if device_id:
            for d in connected_physical:
                if d.identifier == device_id or (d.name and device_id in d.name):
                    return d, iOSTarget.DEVICE
            for d in simulators:
                if d.identifier == device_id or (d.name and device_id in d.name):
                    return d, iOSTarget.SIMULATOR
            return None, iOSTarget.SIMULATOR

        # Auto-select based on preference
        if prefer_physical and connected_physical:
            return connected_physical[0], iOSTarget.DEVICE

        if booted_simulators:
            return booted_simulators[0], iOSTarget.SIMULATOR

        # Try to find any available simulator
        available_sims = [d for d in simulators if d.state == "available"]
        if available_sims:
            # Prefer iPhone Pro models
            for sim in available_sims:
                if sim.name and "Pro" in sim.name and "iPhone" in sim.name:
                    return sim, iOSTarget.SIMULATOR
            return available_sims[0], iOSTarget.SIMULATOR

        return None, iOSTarget.SIMULATOR

    # ========== Bundle Preparation ==========

    def prepare_python_bundle(self, target: iOSTarget = iOSTarget.SIMULATOR) -> bool:
        """Prepare the Python bundle for iOS."""
        script_path = self.config.project_path / "scripts" / "prepare_python_bundle.sh"

        if not script_path.exists():
            print(f"[ERROR] Bundle script not found: {script_path}")
            return False

        target_arg = "device" if target == iOSTarget.DEVICE else "simulator"
        print(f"[INFO] Preparing Python bundle for {target_arg}...")

        result = self._run_command(
            ["bash", str(script_path), target_arg],
            timeout=300,
        )

        if result.returncode != 0:
            print(f"[ERROR] Bundle preparation failed:\n{result.stderr}")
            return False

        # Create Resources.zip
        resources_dir = self.config.project_path / "Resources"
        resources_zip = self.config.project_path / "Resources.zip"

        if resources_dir.exists():
            print("[INFO] Creating Resources.zip...")
            # Remove old zip
            if resources_zip.exists():
                resources_zip.unlink()

            result = self._run_command(
                ["zip", "-q", "-r", str(resources_zip), "."],
                cwd=resources_dir,
                timeout=120,
            )

            if result.returncode != 0:
                print(f"[ERROR] Failed to create Resources.zip")
                return False

            print(f"[INFO] Resources.zip created ({resources_zip.stat().st_size // 1024 // 1024}MB)")

        return True

    # ========== Building ==========

    def build(
        self,
        target: iOSTarget = iOSTarget.SIMULATOR,
        device: Optional[DeviceInfo] = None,
    ) -> iOSBuildResult:
        """Build the iOS app for the specified target."""
        start_time = time.time()

        # Prepare bundle if requested
        if self.config.prepare_bundle:
            if not self.prepare_python_bundle(target):
                return iOSBuildResult(
                    success=False,
                    error_message="Failed to prepare Python bundle",
                )

        # Build command
        sdk = "iphoneos" if target == iOSTarget.DEVICE else "iphonesimulator"

        cmd = [
            "xcodebuild",
            "-project", f"{self.config.scheme}.xcodeproj",
            "-scheme", self.config.scheme,
            "-configuration", self.config.configuration,
            "-sdk", sdk,
        ]

        if target == iOSTarget.DEVICE:
            cmd.extend([
                "-destination", "generic/platform=iOS",
                "CODE_SIGN_IDENTITY=Apple Development",
                "CODE_SIGNING_REQUIRED=YES",
            ])
        else:
            # For simulator, use specific device if provided
            if device:
                cmd.extend([
                    "-destination", f"platform=iOS Simulator,id={device.identifier}",
                ])
            else:
                cmd.extend([
                    "-destination", "generic/platform=iOS Simulator",
                ])

        if self.config.clean_build:
            cmd.append("clean")
        cmd.append("build")

        print(f"[INFO] Building for {target.value}...")
        if self.config.verbose:
            print(f"[CMD] {' '.join(cmd)}")

        result = self._run_command(cmd, timeout=600)

        build_time = time.time() - start_time
        warnings = []

        # Parse output for warnings and errors
        if result.stdout:
            for line in result.stdout.split("\n"):
                if "warning:" in line.lower():
                    warnings.append(line.strip())

        if result.returncode != 0:
            error_msg = "Build failed"
            if result.stderr:
                # Extract relevant error
                for line in result.stderr.split("\n"):
                    if "error:" in line.lower():
                        error_msg = line.strip()
                        break

            return iOSBuildResult(
                success=False,
                target=target,
                build_time=build_time,
                error_message=error_msg,
                warnings=warnings,
            )

        # Find built app
        app_path = self._find_built_app(target)

        print(f"[INFO] Build succeeded in {build_time:.1f}s")
        if app_path:
            print(f"[INFO] App: {app_path}")

        return iOSBuildResult(
            success=True,
            app_path=app_path,
            target=target,
            build_time=build_time,
            warnings=warnings,
        )

    def _find_built_app(self, target: iOSTarget) -> Optional[Path]:
        """Find the built .app bundle in DerivedData."""
        config_suffix = "iphoneos" if target == iOSTarget.DEVICE else "iphonesimulator"
        products_dir = f"{self.config.configuration}-{config_suffix}"

        # Search in DerivedData
        derived_data = self.config.derived_data_path
        if not derived_data.exists():
            return None

        # Find project-specific derived data folder
        for folder in derived_data.iterdir():
            if folder.name.startswith("iosApp-"):
                app_path = folder / "Build" / "Products" / products_dir / "iosApp.app"
                if app_path.exists():
                    return app_path

        return None

    # ========== Installation ==========

    def install(
        self,
        app_path: Path,
        device: DeviceInfo,
        target: iOSTarget,
    ) -> bool:
        """Install app to device or simulator."""
        print(f"[INFO] Installing to {device.name or device.identifier}...")

        if target == iOSTarget.DEVICE:
            return self._install_to_device(app_path, device)
        else:
            return self._install_to_simulator(app_path, device)

    def _install_to_device(self, app_path: Path, device: DeviceInfo) -> bool:
        """Install to physical device using devicectl."""
        result = self._run_command([
            "xcrun", "devicectl", "device", "install", "app",
            "--device", device.identifier,
            str(app_path),
        ])

        if result.returncode != 0:
            print(f"[ERROR] Install failed: {result.stderr}")
            return False

        return True

    def _install_to_simulator(self, app_path: Path, device: DeviceInfo) -> bool:
        """Install to simulator using simctl."""
        # Boot simulator if not booted
        if device.state != "booted":
            print(f"[INFO] Booting simulator {device.name}...")
            result = self._run_command([
                "xcrun", "simctl", "boot", device.identifier,
            ])
            if result.returncode != 0:
                print(f"[ERROR] Failed to boot simulator: {result.stderr}")
                return False
            time.sleep(2)

        result = self._run_command([
            "xcrun", "simctl", "install", device.identifier, str(app_path),
        ])

        if result.returncode != 0:
            print(f"[ERROR] Install failed: {result.stderr}")
            return False

        return True

    # ========== Launch ==========

    def launch(
        self,
        device: DeviceInfo,
        target: iOSTarget,
        wait_for_debugger: bool = False,
    ) -> bool:
        """Launch the app on device or simulator."""
        print(f"[INFO] Launching {self.config.bundle_id}...")

        if target == iOSTarget.DEVICE:
            return self._launch_on_device(device, wait_for_debugger)
        else:
            return self._launch_on_simulator(device)

    def _launch_on_device(self, device: DeviceInfo, wait: bool = False) -> bool:
        """Launch on physical device using devicectl."""
        cmd = [
            "xcrun", "devicectl", "device", "process", "launch",
            "--device", device.identifier,
            self.config.bundle_id,
        ]

        result = self._run_command(cmd)

        if result.returncode != 0:
            print(f"[ERROR] Launch failed: {result.stderr}")
            return False

        return True

    def _launch_on_simulator(self, device: DeviceInfo) -> bool:
        """Launch on simulator using simctl."""
        result = self._run_command([
            "xcrun", "simctl", "launch", device.identifier, self.config.bundle_id,
        ])

        if result.returncode != 0:
            print(f"[ERROR] Launch failed: {result.stderr}")
            return False

        return True

    # ========== Convenience Methods ==========

    def build_and_run(
        self,
        device_id: Optional[str] = None,
        prefer_physical: bool = True,
        prepare_bundle: bool = True,
    ) -> Tuple[bool, Optional[DeviceInfo]]:
        """Build, install, and launch in one step."""
        self.config.prepare_bundle = prepare_bundle

        # Select device
        device, target = self.select_device(device_id, prefer_physical)

        if device is None:
            # For simulators, we might need to boot one
            sims = self.get_simulators()
            available = [s for s in sims if s.state == "available"]
            if available:
                device = available[0]
                target = iOSTarget.SIMULATOR
                print(f"[INFO] Will boot simulator: {device.name}")
            else:
                print("[ERROR] No devices available")
                return False, None

        print(f"[INFO] Target: {target.value} - {device.name or device.identifier}")

        # Build
        result = self.build(target, device)
        if not result.success:
            print(f"[ERROR] Build failed: {result.error_message}")
            return False, device

        # Install
        if result.app_path:
            if not self.install(result.app_path, device, target):
                return False, device

        # Launch
        if not self.launch(device, target):
            return False, device

        print(f"\n[SUCCESS] App running on {device.name or device.identifier}")
        return True, device

    def increment_build_number(self) -> Optional[int]:
        """Increment the build number in Info.plist."""
        plist_path = self.config.project_path / "iosApp" / "Info.plist"

        if not plist_path.exists():
            return None

        content = plist_path.read_text()

        # Find current build number
        import re
        match = re.search(r'<key>CFBundleVersion</key>\s*<string>(\d+)</string>', content)

        if match:
            current = int(match.group(1))
            new_version = current + 1

            new_content = re.sub(
                r'(<key>CFBundleVersion</key>\s*<string>)\d+(</string>)',
                f'\\g<1>{new_version}\\g<2>',
                content,
            )

            plist_path.write_text(new_content)
            print(f"[INFO] Build number: {current} -> {new_version}")
            return new_version

        return None


def build_ios_app(
    device_id: Optional[str] = None,
    prefer_physical: bool = True,
    prepare_bundle: bool = True,
    increment_version: bool = True,
    verbose: bool = False,
) -> Tuple[bool, Optional[DeviceInfo]]:
    """
    Convenience function to build and deploy iOS app.

    Args:
        device_id: Specific device/simulator ID to target
        prefer_physical: Prefer physical devices over simulators
        prepare_bundle: Regenerate Python bundle before build
        increment_version: Increment build number
        verbose: Show detailed output

    Returns:
        Tuple of (success, device_info)
    """
    try:
        helper = iOSBuildHelper()
        helper.config.verbose = verbose

        if increment_version:
            helper.increment_build_number()

        return helper.build_and_run(
            device_id=device_id,
            prefer_physical=prefer_physical,
            prepare_bundle=prepare_bundle,
        )
    except Exception as e:
        print(f"[ERROR] {e}")
        return False, None
