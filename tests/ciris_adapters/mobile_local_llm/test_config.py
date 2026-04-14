"""Tests for Mobile Local LLM adapter configuration."""

from __future__ import annotations

import os
from unittest import mock

import pytest

from ciris_adapters.mobile_local_llm.config import (
    DeviceTier,
    ENV_ALLOW_DESKTOP,
    ENV_ENABLED,
    ENV_FORCE_CAPABILITY,
    ENV_HEALTH_INTERVAL,
    ENV_IOS_STUB_MODEL_PATH,
    ENV_MIN_FREE_DISK_GB,
    ENV_MIN_RAM_GB,
    ENV_MODEL_PATH,
    ENV_MODEL_VARIANT,
    ENV_READY_TIMEOUT,
    ENV_REQUEST_TIMEOUT,
    ENV_SERVER_BINARY,
    ENV_SERVER_HOST,
    ENV_SERVER_PORT,
    MobileLocalLLMConfig,
    ModelVariant,
    load_config_from_env,
)


class TestMobileLocalLLMConfig:
    """Tests for the config model itself."""

    def test_defaults_are_sensible(self):
        cfg = MobileLocalLLMConfig()
        assert cfg.enabled is True
        assert cfg.model_variant == ModelVariant.GEMMA_4_E2B
        assert cfg.host == "127.0.0.1"
        assert 1024 <= cfg.port <= 65535
        assert cfg.min_total_ram_gb_e2b == 6.0
        assert cfg.min_total_ram_gb_e4b == 8.0
        assert cfg.min_free_disk_gb == 3.0
        assert cfg.allow_desktop is False
        assert cfg.ios_model_path is None

    def test_base_url_and_health_url_match_host_port(self):
        cfg = MobileLocalLLMConfig(host="127.0.0.1", port=9001)
        assert cfg.base_url() == "http://127.0.0.1:9001/v1"
        assert cfg.health_url() == "http://127.0.0.1:9001/health"

    def test_required_ram_depends_on_variant(self):
        e2b = MobileLocalLLMConfig(model_variant=ModelVariant.GEMMA_4_E2B)
        e4b = MobileLocalLLMConfig(model_variant=ModelVariant.GEMMA_4_E4B)
        assert e2b.required_ram_gb() == 6.0
        assert e4b.required_ram_gb() == 8.0

    def test_port_validation(self):
        with pytest.raises(ValueError):
            MobileLocalLLMConfig(port=80)  # privileged, blocked
        with pytest.raises(ValueError):
            MobileLocalLLMConfig(port=70000)

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValueError):
            MobileLocalLLMConfig(random_field="x")  # type: ignore[call-arg]

    def test_device_tier_includes_ios_stub(self):
        """IOS_STUB is how we surface 'capable hardware, model not yet shipped'."""
        assert DeviceTier.IOS_STUB.value == "ios_stub"
        assert DeviceTier.CAPABLE_E2B in set(DeviceTier)


class TestLoadConfigFromEnv:
    """Tests for env-var hydration."""

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_empty_env_returns_defaults(self):
        cfg = load_config_from_env()
        assert cfg == MobileLocalLLMConfig()

    def test_env_overrides_applied(self, tmp_path):
        model_path = tmp_path / "gemma.bin"
        ios_model_path = tmp_path / "gemma.litert"
        server_binary = tmp_path / "litertlm"
        env = {
            ENV_ENABLED: "false",
            ENV_MODEL_VARIANT: "gemma-4-e4b",
            ENV_MODEL_PATH: str(model_path),
            ENV_IOS_STUB_MODEL_PATH: str(ios_model_path),
            ENV_SERVER_BINARY: str(server_binary),
            ENV_SERVER_HOST: "127.0.0.1",
            ENV_SERVER_PORT: "9999",
            ENV_READY_TIMEOUT: "12.5",
            ENV_REQUEST_TIMEOUT: "45",
            ENV_HEALTH_INTERVAL: "7",
            ENV_MIN_RAM_GB: "7.5",
            ENV_MIN_FREE_DISK_GB: "2.5",
            ENV_FORCE_CAPABILITY: "capable_e4b",
            ENV_ALLOW_DESKTOP: "1",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            cfg = load_config_from_env()
        assert cfg.enabled is False
        assert cfg.model_variant == ModelVariant.GEMMA_4_E4B
        assert cfg.model_path == model_path
        assert cfg.ios_model_path == ios_model_path
        assert cfg.server_binary == server_binary
        assert cfg.port == 9999
        assert cfg.ready_timeout_seconds == 12.5
        assert cfg.request_timeout_seconds == 45.0
        assert cfg.health_interval_seconds == 7.0
        assert cfg.min_total_ram_gb_e2b == 7.5
        assert cfg.min_free_disk_gb == 2.5
        assert cfg.force_capability == DeviceTier.CAPABLE_E4B
        assert cfg.allow_desktop is True

    @mock.patch.dict(
        os.environ,
        {
            ENV_MODEL_VARIANT: "not-a-variant",
            ENV_FORCE_CAPABILITY: "definitely-invalid",
            ENV_SERVER_PORT: "not-a-number",
            ENV_READY_TIMEOUT: "banana",
        },
        clear=True,
    )
    def test_invalid_env_values_fall_back_to_defaults(self):
        cfg = load_config_from_env()
        defaults = MobileLocalLLMConfig()
        assert cfg.model_variant == defaults.model_variant
        assert cfg.force_capability is None
        assert cfg.port == defaults.port
        assert cfg.ready_timeout_seconds == defaults.ready_timeout_seconds

    @mock.patch.dict(os.environ, {ENV_ENABLED: "0"}, clear=True)
    def test_enabled_false_parsed_correctly(self):
        cfg = load_config_from_env()
        assert cfg.enabled is False

    @mock.patch.dict(os.environ, {ENV_ENABLED: "Yes"}, clear=True)
    def test_enabled_truthy_parsed_correctly(self):
        cfg = load_config_from_env()
        assert cfg.enabled is True

    @mock.patch.dict(os.environ, {ENV_FORCE_CAPABILITY: "ios_stub"}, clear=True)
    def test_force_capability_accepts_ios_stub(self):
        cfg = load_config_from_env()
        assert cfg.force_capability == DeviceTier.IOS_STUB
