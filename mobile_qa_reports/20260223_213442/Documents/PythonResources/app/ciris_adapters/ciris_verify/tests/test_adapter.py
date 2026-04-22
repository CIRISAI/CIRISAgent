"""Tests for CIRISVerify adapter integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_adapters.ciris_verify.adapter import CIRISVerifyAdapter
from ciris_adapters.ciris_verify.service import CIRISVerifyService, VerificationConfig


def _make_mock_license_response():
    """Create a mock LicenseStatusResponse."""
    mock_status = MagicMock()
    mock_status.allows_licensed_operation.return_value = False
    mock_status.value = 200  # UNLICENSED_COMMUNITY

    mock_disclosure = MagicMock()
    mock_disclosure.text = "COMMUNITY MODE: Unlicensed community agent."
    mock_disclosure.severity = "warning"

    mock_response = MagicMock()
    mock_response.status = mock_status
    mock_response.license = None
    mock_response.mandatory_disclosure = mock_disclosure
    mock_response.allows_licensed_operation.return_value = False
    mock_response.model_dump.return_value = {
        "status": 200,
        "license": None,
        "mandatory_disclosure": {"text": mock_disclosure.text, "severity": "warning"},
        "hardware_type": "software_only",
        "cached": False,
    }
    return mock_response


def _make_mock_capability_result(capability, allowed, reason=""):
    """Create a mock CapabilityCheckResult."""
    result = MagicMock()
    result.capability = capability
    result.allowed = allowed
    result.reason = reason
    return result


class TestCIRISVerifyAdapter:
    """Tests for CIRISVerifyAdapter."""

    @pytest.fixture
    def adapter(self) -> CIRISVerifyAdapter:
        mock_runtime = MagicMock()
        return CIRISVerifyAdapter(runtime=mock_runtime, adapter_config={})

    @pytest.fixture
    def adapter_with_config(self) -> CIRISVerifyAdapter:
        mock_runtime = MagicMock()
        return CIRISVerifyAdapter(
            runtime=mock_runtime,
            adapter_config={
                "cache_ttl_seconds": 60,
                "timeout_seconds": 5.0,
            },
        )

    def test_adapter_name(self, adapter):
        assert adapter.name == "ciris_verify"

    def test_adapter_version(self, adapter):
        assert adapter.version == "0.1.0"

    def test_get_metadata(self, adapter):
        metadata = adapter.get_metadata()
        assert metadata.name == "ciris_verify"
        assert "license:verify" in metadata.capabilities

    @pytest.mark.asyncio
    @patch("ciris_adapters.ciris_verify.service.CIRISVerify")
    async def test_start_stop_lifecycle(self, mock_ciris_verify_cls, adapter):
        mock_client = AsyncMock()
        mock_client.get_license_status = AsyncMock(return_value=_make_mock_license_response())
        mock_ciris_verify_cls.return_value = mock_client

        await adapter.start()
        assert adapter._started
        assert adapter._service is not None

        await adapter.stop()
        assert not adapter._started
        assert adapter._service is None

    @pytest.mark.asyncio
    @patch("ciris_adapters.ciris_verify.service.CIRISVerify")
    async def test_get_license_status(self, mock_ciris_verify_cls, adapter):
        mock_client = AsyncMock()
        mock_client.get_license_status = AsyncMock(return_value=_make_mock_license_response())
        mock_ciris_verify_cls.return_value = mock_client

        await adapter.start()
        status = await adapter.get_license_status()
        assert status is not None
        await adapter.stop()

    @pytest.mark.asyncio
    @patch("ciris_adapters.ciris_verify.service.CIRISVerify")
    async def test_check_capability(self, mock_ciris_verify_cls, adapter):
        mock_client = AsyncMock()
        mock_client.get_license_status = AsyncMock(return_value=_make_mock_license_response())
        mock_client.check_capability = AsyncMock(
            side_effect=lambda cap: _make_mock_capability_result(
                cap, cap.startswith("standard:") or cap.startswith("tool:")
            )
        )
        mock_ciris_verify_cls.return_value = mock_client

        await adapter.start()

        result = await adapter.check_capability("medical:diagnosis")
        assert not result.allowed

        result = await adapter.check_capability("standard:telemetry")
        assert result.allowed

        await adapter.stop()

    @pytest.mark.asyncio
    @patch("ciris_adapters.ciris_verify.service.CIRISVerify")
    async def test_get_mandatory_disclosure(self, mock_ciris_verify_cls, adapter):
        mock_client = AsyncMock()
        mock_client.get_license_status = AsyncMock(return_value=_make_mock_license_response())
        mock_ciris_verify_cls.return_value = mock_client

        await adapter.start()
        disclosure = await adapter.get_mandatory_disclosure()
        assert disclosure is not None
        assert hasattr(disclosure, "text")
        await adapter.stop()

    def test_get_agent_tier_community(self, adapter):
        assert adapter.get_agent_tier() == 1

    def test_is_licensed_false_before_start(self, adapter):
        assert not adapter.is_licensed()

    @pytest.mark.asyncio
    @patch("ciris_adapters.ciris_verify.service.CIRISVerify")
    async def test_is_licensed_community(self, mock_ciris_verify_cls, adapter):
        mock_client = AsyncMock()
        mock_client.get_license_status = AsyncMock(return_value=_make_mock_license_response())
        mock_ciris_verify_cls.return_value = mock_client

        await adapter.start()
        assert not adapter.is_licensed()
        await adapter.stop()

    @pytest.mark.asyncio
    @patch("ciris_adapters.ciris_verify.service.CIRISVerify")
    async def test_services_registered(self, mock_ciris_verify_cls, adapter):
        mock_client = AsyncMock()
        mock_client.get_license_status = AsyncMock(return_value=_make_mock_license_response())
        mock_ciris_verify_cls.return_value = mock_client

        await adapter.start()
        services = adapter.get_services_to_register()
        assert len(services) == 1
        assert services[0].service_type.value == "tool"
        await adapter.stop()

    @pytest.mark.asyncio
    @patch("ciris_adapters.ciris_verify.service.CIRISVerify")
    async def test_double_start_idempotent(self, mock_ciris_verify_cls, adapter):
        mock_client = AsyncMock()
        mock_client.get_license_status = AsyncMock(return_value=_make_mock_license_response())
        mock_ciris_verify_cls.return_value = mock_client

        await adapter.start()
        service1 = adapter._service

        await adapter.start()
        service2 = adapter._service

        assert service1 is service2
        await adapter.stop()


class TestCIRISVerifyService:
    """Tests for CIRISVerifyService."""

    @pytest.fixture
    def service(self):
        return CIRISVerifyService(VerificationConfig())

    @pytest.mark.asyncio
    @patch("ciris_adapters.ciris_verify.service.CIRISVerify")
    async def test_initialize(self, mock_ciris_verify_cls, service):
        mock_ciris_verify_cls.return_value = AsyncMock()
        result = await service.initialize()
        assert result is True
        assert service._initialized

    @pytest.mark.asyncio
    @patch("ciris_adapters.ciris_verify.service.CIRISVerify")
    async def test_get_license_status_caches(self, mock_ciris_verify_cls, service):
        mock_client = AsyncMock()
        mock_client.get_license_status = AsyncMock(return_value=_make_mock_license_response())
        mock_ciris_verify_cls.return_value = mock_client

        await service.initialize()

        status1 = await service.get_license_status()
        assert status1 is not None

        status2 = await service.get_license_status()
        assert status2 is not None

        assert service._cache is not None
        assert service._cache.is_valid()

    @pytest.mark.asyncio
    @patch("ciris_adapters.ciris_verify.service.CIRISVerify")
    async def test_force_refresh_bypasses_cache(self, mock_ciris_verify_cls, service):
        mock_client = AsyncMock()
        mock_client.get_license_status = AsyncMock(return_value=_make_mock_license_response())
        mock_ciris_verify_cls.return_value = mock_client

        await service.initialize()

        await service.get_license_status()
        old_cache = service._cache

        await service.get_license_status(force_refresh=True)
        new_cache = service._cache

        assert new_cache.cached_at >= old_cache.cached_at

    @pytest.mark.asyncio
    @patch("ciris_adapters.ciris_verify.service.CIRISVerify")
    async def test_shutdown(self, mock_ciris_verify_cls, service):
        mock_ciris_verify_cls.return_value = AsyncMock()
        await service.initialize()
        await service.shutdown()

        assert not service._initialized
        assert service._cache is None
