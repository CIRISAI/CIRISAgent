"""
Device capability detection for local Gemma 4 inference on mobile devices.

Google AI Edge and LiteRT-LM documentation for Gemma 4 says:

- E2B can run in ~1.5 GB of memory "on some devices"
- E4B is heavier and only suitable for high-end phones
- arm64-v8a is the supported Android ABI; arm64 is the supported iOS ABI
- Thermal / sustained latency matter more than peak parameter count

We translate that guidance into a concrete capability probe so the runtime
can decide whether to start the local inference server or skip it and let
the LLM bus fall back to a hosted provider.

On iOS the adapter can detect capable hardware (enough RAM, arm64, recent
iOS) but Google AI Edge / LiteRT-LM does not yet ship an adequate
on-device model in every configuration. When the expected model bundle is
missing we return :attr:`DeviceTier.IOS_STUB` so the wizard can display a
"coming soon" option rather than offering a broken local path.
"""

from __future__ import annotations

import logging
import os
import platform as _platform
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from .config import DeviceTier, MobileLocalLLMConfig, ModelVariant, Platform

logger = logging.getLogger(__name__)


# Android app data directories follow /data/data/<pkg>/ — this is the most
# reliable way to detect we are inside a Chaquopy-hosted Python runtime.
_ANDROID_DATA_PREFIX = "/data/data/"
_ANDROID_USER_PREFIX = "/data/user/"

# iOS app container paths — we will not match the Android prefixes, and
# PythonKit / embedded Python on iOS typically executes out of a sandboxed
# path that includes one of these substrings.
_IOS_PATH_MARKERS = (
    "/var/mobile/Containers/",  # user apps on device
    "/var/containers/Bundle/Application/",  # installed app bundles
    "/CoreSimulator/Devices/",  # simulator
)


@dataclass(frozen=True)
class DeviceCapabilityReport:
    """Structured outcome of the capability probe.

    Immutable by design: the adapter caches one report per start() call and
    derives all decisions from its fields.
    """

    tier: DeviceTier
    platform: Platform
    architecture: str
    total_ram_gb: float
    available_ram_gb: float
    free_disk_gb: float
    reasons: List[str]

    @property
    def capable(self) -> bool:
        """True when the device can actually run local inference today."""
        return self.tier in {DeviceTier.CAPABLE_E2B, DeviceTier.CAPABLE_E4B, DeviceTier.DESKTOP_CAPABLE}

    @property
    def is_stub(self) -> bool:
        """True when the platform is supported but the model is not yet shipped."""
        return self.tier == DeviceTier.IOS_STUB

    @property
    def is_android(self) -> bool:
        return self.platform == Platform.ANDROID

    @property
    def is_ios(self) -> bool:
        return self.platform == Platform.IOS

    def can_run(self, variant: ModelVariant) -> bool:
        """Does this device tier support the given variant?"""
        if variant == ModelVariant.GEMMA_4_E2B:
            return self.capable
        if variant == ModelVariant.GEMMA_4_E4B:
            return self.tier == DeviceTier.CAPABLE_E4B
        return False

    def summary(self) -> str:
        """Short human-readable summary for logs and status endpoints."""
        return (
            f"tier={self.tier.value} platform={self.platform.value} "
            f"arch={self.architecture} ram_total={self.total_ram_gb:.1f}GB "
            f"ram_avail={self.available_ram_gb:.1f}GB "
            f"disk_free={self.free_disk_gb:.1f}GB"
        )


# ---------------------------------------------------------------------------
# Low-level probes (pure functions, kept small for unit testing)
# ---------------------------------------------------------------------------


def detect_platform() -> Platform:
    """Return the high-level platform this Python process is running on.

    We check Android first because an Android Chaquopy process reports
    ``platform.system() == 'Linux'``. iOS is identified through path
    markers and the CoreFoundation/NSBundle bridge that PythonKit exposes.
    """
    # Signal 1: Chaquopy / Android app data path.
    try:
        current = str(Path(__file__).resolve())
    except OSError:
        current = ""
    if _ANDROID_DATA_PREFIX in current or _ANDROID_USER_PREFIX in current:
        return Platform.ANDROID

    # Signal 2: Android-specific environment variables.
    if os.environ.get("ANDROID_ROOT") and os.environ.get("ANDROID_DATA"):
        return Platform.ANDROID

    # Signal 3: Chaquopy `java` module.
    try:
        import java  # type: ignore[import-not-found]

        _ = java  # presence is the signal
        return Platform.ANDROID
    except ImportError:
        pass

    # Signal 4: iOS — look for container paths or the mobile sysname.
    if any(marker in current for marker in _IOS_PATH_MARKERS):
        return Platform.IOS
    if sys.platform == "ios" or _platform.system() == "iOS":  # type: ignore[comparison-overlap]
        return Platform.IOS
    if os.environ.get("CIRIS_MOBILE_LOCAL_LLM_FORCE_PLATFORM") == "ios":
        # Only used in dev loops / unit tests where the probes are injected.
        return Platform.IOS

    # Signal 5: Desktop fallback.
    if _platform.system() in {"Linux", "Darwin", "Windows"}:
        return Platform.DESKTOP
    return Platform.UNKNOWN


def detect_architecture() -> str:
    """Return a normalised ABI name for the current CPU."""
    machine = _platform.machine().lower()
    if "aarch64" in machine or "arm64" in machine:
        return "arm64-v8a"
    if machine.startswith("armv7") or machine == "armv7l" or machine.startswith("arm"):
        return "armeabi-v7a"
    if "x86_64" in machine or machine == "amd64":
        return "x86_64"
    if machine.startswith("i") and machine.endswith("86"):
        return "x86"
    return machine or "unknown"


def read_total_ram_gb() -> float:
    """Read total RAM in gigabytes.

    Uses /proc/meminfo on Linux/Android. Falls back to psutil when available
    so iOS and desktop dev also report a reasonable number.
    """
    meminfo = _read_proc_file("/proc/meminfo")
    if meminfo:
        for line in meminfo.splitlines():
            if line.startswith("MemTotal:"):
                try:
                    kb = int(line.split()[1])
                    return kb / (1024 * 1024)
                except (ValueError, IndexError):
                    break
    try:
        import psutil  # type: ignore[import-not-found]

        return float(psutil.virtual_memory().total) / (1024**3)
    except Exception:  # pragma: no cover - optional dependency
        return 0.0


def read_available_ram_gb() -> float:
    """Read currently available RAM in gigabytes."""
    meminfo = _read_proc_file("/proc/meminfo")
    if meminfo:
        available_kb: Optional[int] = None
        free_kb: Optional[int] = None
        for line in meminfo.splitlines():
            if line.startswith("MemAvailable:"):
                try:
                    available_kb = int(line.split()[1])
                except (ValueError, IndexError):
                    pass
            elif line.startswith("MemFree:"):
                try:
                    free_kb = int(line.split()[1])
                except (ValueError, IndexError):
                    pass
        if available_kb is not None:
            return available_kb / (1024 * 1024)
        if free_kb is not None:
            return free_kb / (1024 * 1024)
    try:
        import psutil  # type: ignore[import-not-found]

        return float(psutil.virtual_memory().available) / (1024**3)
    except Exception:  # pragma: no cover - optional dependency
        return 0.0


def read_free_disk_gb(path: Optional[Path] = None) -> float:
    """Free disk space in gigabytes for the given path (app data dir by default)."""
    target = path or _default_disk_path()
    try:
        usage = shutil.disk_usage(str(target))
        return usage.free / (1024**3)
    except (OSError, FileNotFoundError):
        return 0.0


def _default_disk_path() -> Path:
    """Best-effort guess of the writable data directory we care about."""
    home = os.environ.get("HOME")
    if home:
        return Path(home)
    ciris_home = os.environ.get("CIRIS_HOME")
    if ciris_home:
        return Path(ciris_home)
    return Path(os.getcwd())


def _read_proc_file(path: str) -> Optional[str]:
    """Read a /proc file, returning None on any permission or IO error."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except (OSError, PermissionError):
        return None


# ---------------------------------------------------------------------------
# Public probe
# ---------------------------------------------------------------------------


def probe_device_capability(
    config: MobileLocalLLMConfig,
    *,
    platform_fn: Optional[Callable[[], Platform]] = None,
    arch_fn: Optional[Callable[[], str]] = None,
    total_ram_fn: Optional[Callable[[], float]] = None,
    available_ram_fn: Optional[Callable[[], float]] = None,
    free_disk_fn: Optional[Callable[[], float]] = None,
) -> DeviceCapabilityReport:
    """Probe the current device and decide whether local inference is safe.

    The returned report is what the adapter uses to decide whether to spawn
    the inference server. Callable overrides let the unit tests simulate
    phones without the probe needing to reach the real system.
    """
    current_platform = (platform_fn or detect_platform)()
    architecture = (arch_fn or detect_architecture)()
    total_ram_gb = (total_ram_fn or read_total_ram_gb)()
    available_ram_gb = (available_ram_fn or read_available_ram_gb)()
    free_disk_gb = (free_disk_fn or read_free_disk_gb)()

    reasons: List[str] = []

    # Honour explicit override (testing / power users) but still populate the
    # observed fields for visibility.
    if config.force_capability is not None:
        reasons.append(f"tier forced via config to {config.force_capability.value}")
        return DeviceCapabilityReport(
            tier=config.force_capability,
            platform=current_platform,
            architecture=architecture,
            total_ram_gb=total_ram_gb,
            available_ram_gb=available_ram_gb,
            free_disk_gb=free_disk_gb,
            reasons=reasons,
        )

    # Gate 1: platform — Android, iOS (with caveats), and Desktop are all supported.
    # None auto-start the server; all platforms detect capability and let the
    # user opt in via the wizard. This keeps behavior predictable and gives
    # users control over when to allocate resources for local inference.
    if current_platform == Platform.UNKNOWN:
        reasons.append("unknown platform; refusing to run local inference")
        return _result(
            DeviceTier.INCAPABLE, current_platform, architecture,
            total_ram_gb, available_ram_gb, free_disk_gb, reasons,
        )

    # Gate 2: arm64 on mobile. Desktop dev can be x86_64.
    if current_platform in {Platform.ANDROID, Platform.IOS} and architecture != "arm64-v8a":
        reasons.append(
            f"architecture {architecture} is not arm64; Gemma 4 mobile builds require arm64"
        )
        return _result(
            DeviceTier.INCAPABLE, current_platform, architecture,
            total_ram_gb, available_ram_gb, free_disk_gb, reasons,
        )

    # Gate 3: free disk.
    if free_disk_gb > 0.0 and free_disk_gb < config.min_free_disk_gb:
        reasons.append(
            f"free disk {free_disk_gb:.2f}GB is below required {config.min_free_disk_gb:.2f}GB"
        )
        return _result(
            DeviceTier.INCAPABLE, current_platform, architecture,
            total_ram_gb, available_ram_gb, free_disk_gb, reasons,
        )

    # Gate 4: RAM thresholds.
    if total_ram_gb <= 0.0:
        reasons.append("could not determine total RAM; skipping local inference for safety")
        return _result(
            DeviceTier.INCAPABLE, current_platform, architecture,
            total_ram_gb, available_ram_gb, free_disk_gb, reasons,
        )

    if total_ram_gb >= config.min_total_ram_gb_e4b:
        reasons.append(
            f"total RAM {total_ram_gb:.1f}GB >= E4B threshold {config.min_total_ram_gb_e4b:.1f}GB"
        )
        tentative_tier = DeviceTier.CAPABLE_E4B
    elif total_ram_gb >= config.min_total_ram_gb_e2b:
        reasons.append(
            f"total RAM {total_ram_gb:.1f}GB >= E2B threshold {config.min_total_ram_gb_e2b:.1f}GB"
        )
        tentative_tier = DeviceTier.CAPABLE_E2B
    else:
        reasons.append(
            f"total RAM {total_ram_gb:.1f}GB is below E2B threshold {config.min_total_ram_gb_e2b:.1f}GB"
        )
        return _result(
            DeviceTier.INCAPABLE, current_platform, architecture,
            total_ram_gb, available_ram_gb, free_disk_gb, reasons,
        )

    # Gate 5: iOS stub — hardware looks fine but we may not have a model to
    # feed LiteRT-LM yet. If the model bundle does not exist we demote the
    # tier to IOS_STUB so the wizard can show "coming soon".
    if current_platform == Platform.IOS:
        model_path = config.ios_model_path or config.model_path
        if model_path is None or not model_path.exists():
            reasons.append(
                "iOS local inference is supported on this device but no Gemma 4 model "
                "bundle was found; marking as stub so the wizard shows 'coming soon'"
            )
            return _result(
                DeviceTier.IOS_STUB, current_platform, architecture,
                total_ram_gb, available_ram_gb, free_disk_gb, reasons,
            )

    # Gate 6: Desktop — return DESKTOP_CAPABLE so the wizard can offer to
    # start a local llama.cpp server. User must explicitly opt in.
    if current_platform == Platform.DESKTOP:
        reasons.append(
            f"desktop system with {total_ram_gb:.1f}GB RAM can run local llama.cpp inference"
        )
        return _result(
            DeviceTier.DESKTOP_CAPABLE, current_platform, architecture,
            total_ram_gb, available_ram_gb, free_disk_gb, reasons,
        )

    return _result(
        tentative_tier, current_platform, architecture,
        total_ram_gb, available_ram_gb, free_disk_gb, reasons,
    )


def _result(
    tier: DeviceTier,
    current_platform: Platform,
    architecture: str,
    total_ram_gb: float,
    available_ram_gb: float,
    free_disk_gb: float,
    reasons: List[str],
) -> DeviceCapabilityReport:
    return DeviceCapabilityReport(
        tier=tier,
        platform=current_platform,
        architecture=architecture,
        total_ram_gb=total_ram_gb,
        available_ram_gb=available_ram_gb,
        free_disk_gb=free_disk_gb,
        reasons=reasons,
    )


__all__ = [
    "DeviceCapabilityReport",
    "detect_architecture",
    "detect_platform",
    "probe_device_capability",
    "read_available_ram_gb",
    "read_free_disk_gb",
    "read_total_ram_gb",
]
