"""Tests for device capability detection across Android, iOS, and desktop."""

from __future__ import annotations

import pytest

from ciris_adapters.mobile_local_llm.capability import (
    DeviceCapabilityReport,
    detect_architecture,
    probe_device_capability,
)
from ciris_adapters.mobile_local_llm.config import (
    DeviceTier,
    MobileLocalLLMConfig,
    ModelVariant,
    Platform,
)


def _config(**overrides):
    return MobileLocalLLMConfig(**overrides)


def _probe(
    config,
    *,
    platform=Platform.ANDROID,
    arch="arm64-v8a",
    total_ram=8.0,
    available_ram=4.0,
    free_disk=5.0,
):
    return probe_device_capability(
        config,
        platform_fn=lambda: platform,
        arch_fn=lambda: arch,
        total_ram_fn=lambda: total_ram,
        available_ram_fn=lambda: available_ram,
        free_disk_fn=lambda: free_disk,
    )


class TestDeviceCapabilityReport:
    def test_capable_and_can_run(self):
        report = DeviceCapabilityReport(
            tier=DeviceTier.CAPABLE_E4B,
            platform=Platform.ANDROID,
            architecture="arm64-v8a",
            total_ram_gb=12.0,
            available_ram_gb=6.0,
            free_disk_gb=10.0,
            reasons=["test"],
        )
        assert report.capable is True
        assert report.is_stub is False
        assert report.is_android is True
        assert report.is_ios is False
        assert report.can_run(ModelVariant.GEMMA_4_E2B) is True
        assert report.can_run(ModelVariant.GEMMA_4_E4B) is True

    def test_e2b_tier_cannot_run_e4b(self):
        report = DeviceCapabilityReport(
            tier=DeviceTier.CAPABLE_E2B,
            platform=Platform.ANDROID,
            architecture="arm64-v8a",
            total_ram_gb=6.0,
            available_ram_gb=3.0,
            free_disk_gb=5.0,
            reasons=[],
        )
        assert report.capable is True
        assert report.can_run(ModelVariant.GEMMA_4_E2B) is True
        assert report.can_run(ModelVariant.GEMMA_4_E4B) is False

    def test_ios_stub_is_not_capable_but_distinct(self):
        report = DeviceCapabilityReport(
            tier=DeviceTier.IOS_STUB,
            platform=Platform.IOS,
            architecture="arm64-v8a",
            total_ram_gb=8.0,
            available_ram_gb=4.0,
            free_disk_gb=10.0,
            reasons=["model missing"],
        )
        assert report.capable is False
        assert report.is_stub is True
        assert report.is_ios is True
        assert report.can_run(ModelVariant.GEMMA_4_E2B) is False

    def test_desktop_capable_can_run_e2b(self):
        report = DeviceCapabilityReport(
            tier=DeviceTier.DESKTOP_CAPABLE,
            platform=Platform.DESKTOP,
            architecture="x86_64",
            total_ram_gb=16.0,
            available_ram_gb=8.0,
            free_disk_gb=10.0,
            reasons=["desktop system"],
        )
        assert report.capable is True
        assert report.is_stub is False
        # Desktop runs llama.cpp with E2B model
        assert report.can_run(ModelVariant.GEMMA_4_E2B) is True
        # E4B requires mobile tiers
        assert report.can_run(ModelVariant.GEMMA_4_E4B) is False

    def test_incapable_cannot_run_anything(self):
        report = DeviceCapabilityReport(
            tier=DeviceTier.INCAPABLE,
            platform=Platform.DESKTOP,
            architecture="x86_64",
            total_ram_gb=2.0,
            available_ram_gb=1.0,
            free_disk_gb=1.0,
            reasons=["x"],
        )
        assert report.capable is False
        assert report.is_stub is False
        assert report.can_run(ModelVariant.GEMMA_4_E2B) is False
        assert report.summary().startswith("tier=incapable")


class TestProbeAndroid:
    def test_high_end_phone_gets_e4b(self):
        report = _probe(_config(), total_ram=12.0)
        assert report.tier == DeviceTier.CAPABLE_E4B
        assert report.capable
        assert report.platform == Platform.ANDROID

    def test_mid_range_phone_gets_e2b(self):
        report = _probe(_config(), total_ram=6.5)
        assert report.tier == DeviceTier.CAPABLE_E2B

    def test_low_ram_phone_is_incapable(self):
        report = _probe(_config(), total_ram=3.5)
        assert report.tier == DeviceTier.INCAPABLE
        assert any("below E2B threshold" in r for r in report.reasons)

    def test_32bit_phone_is_incapable_even_with_enough_ram(self):
        report = _probe(_config(), arch="armeabi-v7a", total_ram=16.0)
        assert report.tier == DeviceTier.INCAPABLE
        assert any("arm64" in r for r in report.reasons)

    def test_low_disk_is_incapable(self):
        report = _probe(_config(min_free_disk_gb=5.0), free_disk=1.0)
        assert report.tier == DeviceTier.INCAPABLE
        assert any("free disk" in r for r in report.reasons)

    def test_unknown_ram_fails_safely(self):
        """If /proc/meminfo is unavailable we must NOT try local inference."""
        report = _probe(_config(), total_ram=0.0)
        assert report.tier == DeviceTier.INCAPABLE
        assert any("could not determine total RAM" in r for r in report.reasons)


class TestProbeiOS:
    def test_capable_ios_without_model_reports_stub(self):
        """Per user guidance: iOS gets a stub tier when no adequate model exists."""
        report = _probe(
            _config(ios_model_path=None, model_path=None),
            platform=Platform.IOS,
            arch="arm64-v8a",
            total_ram=8.0,
            free_disk=10.0,
        )
        assert report.tier == DeviceTier.IOS_STUB
        assert report.is_stub
        assert any("coming soon" in r.lower() for r in report.reasons)

    def test_capable_ios_with_model_reports_capable(self, tmp_path):
        model = tmp_path / "gemma.litert"
        model.write_bytes(b"x")  # just needs to exist
        report = _probe(
            _config(ios_model_path=model),
            platform=Platform.IOS,
            total_ram=12.0,
            free_disk=10.0,
        )
        assert report.tier == DeviceTier.CAPABLE_E4B
        assert report.is_ios

    def test_ios_low_ram_is_incapable_not_stub(self):
        """Low-RAM iOS devices are not 'coming soon' — they simply cannot run it."""
        report = _probe(
            _config(),
            platform=Platform.IOS,
            total_ram=3.0,
            free_disk=10.0,
        )
        assert report.tier == DeviceTier.INCAPABLE

    def test_ios_32bit_is_incapable_not_stub(self):
        """Pre-A7 hypothetical 32-bit iOS is incapable."""
        report = _probe(
            _config(),
            platform=Platform.IOS,
            arch="armeabi-v7a",
            total_ram=8.0,
        )
        assert report.tier == DeviceTier.INCAPABLE


class TestProbeDesktop:
    def test_desktop_with_sufficient_ram_is_capable(self):
        # Desktop systems with enough RAM are now DESKTOP_CAPABLE
        # User opts in via the wizard, not via config flag
        report = _probe(_config(), platform=Platform.DESKTOP, arch="x86_64", total_ram=32.0)
        assert report.tier == DeviceTier.DESKTOP_CAPABLE
        assert report.capable is True
        assert any("desktop system" in r for r in report.reasons)

    def test_desktop_with_low_ram_is_incapable(self):
        # Desktop with insufficient RAM returns INCAPABLE
        report = _probe(_config(), platform=Platform.DESKTOP, arch="x86_64", total_ram=4.0)
        assert report.tier == DeviceTier.INCAPABLE
        assert report.capable is False

    def test_unknown_platform_is_incapable(self):
        report = _probe(_config(), platform=Platform.UNKNOWN, total_ram=16.0)
        assert report.tier == DeviceTier.INCAPABLE


class TestForceCapability:
    def test_force_capability_bypasses_everything(self):
        report = _probe(
            _config(force_capability=DeviceTier.CAPABLE_E2B),
            platform=Platform.DESKTOP,
            total_ram=1.0,
            arch="armeabi-v7a",
        )
        assert report.tier == DeviceTier.CAPABLE_E2B
        # Observed values are still populated for diagnostics.
        assert report.total_ram_gb == 1.0
        assert report.architecture == "armeabi-v7a"

    def test_force_ios_stub_respected(self):
        report = _probe(
            _config(force_capability=DeviceTier.IOS_STUB),
            platform=Platform.ANDROID,
            total_ram=8.0,
        )
        assert report.tier == DeviceTier.IOS_STUB


class TestDetectArchitecture:
    @pytest.mark.parametrize(
        "machine,expected",
        [
            ("aarch64", "arm64-v8a"),
            ("arm64", "arm64-v8a"),
            ("armv7l", "armeabi-v7a"),
            ("armv7", "armeabi-v7a"),
            ("x86_64", "x86_64"),
            ("AMD64", "x86_64"),
            ("i686", "x86"),
        ],
    )
    def test_normalises_common_machines(self, monkeypatch, machine, expected):
        monkeypatch.setattr("platform.machine", lambda: machine)
        assert detect_architecture() == expected
