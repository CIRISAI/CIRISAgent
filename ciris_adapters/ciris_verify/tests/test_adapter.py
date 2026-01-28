"""Tests for CIRISVerify adapter integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_adapters.ciris_verify.adapter import CIRISVerifyAdapter
from ciris_adapters.ciris_verify.service import CIRISVerifyService, VerificationConfig, _FallbackMockClient


class TestCIRISVerifyAdapter:
    """Tests for CIRISVerifyAdapter."""

    @pytest.fixture
    def adapter(self):
        return CIRISVerifyAdapter(config={"use_mock": True})

    @pytest.fixture
    def adapter_with_config(self):
        return CIRISVerifyAdapter(
            config={
                "use_mock": True,
                "cache_ttl_seconds": 60,
                "timeout_seconds": 5.0,
            }
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
    async def test_start_stop_lifecycle(self, adapter):
        await adapter.start()
        assert adapter._started
        assert adapter._service is not None

        await adapter.stop()
        assert not adapter._started
        assert adapter._service is None

    @pytest.mark.asyncio
    async def test_get_license_status(self, adapter):
        await adapter.start()

        status = await adapter.get_license_status()
        assert status is not None

        # Mock returns community mode by default
        if isinstance(status, dict):
            assert status.get("status") == 200  # UNLICENSED_COMMUNITY
        else:
            assert status.status == 200

        await adapter.stop()

    @pytest.mark.asyncio
    async def test_check_capability(self, adapter):
        await adapter.start()

        # Professional capabilities denied in community mode
        result = await adapter.check_capability("medical:diagnosis")
        if isinstance(result, dict):
            assert not result.get("allowed")
        else:
            assert not result.allowed

        # Standard operations allowed
        result = await adapter.check_capability("standard:telemetry")
        if isinstance(result, dict):
            assert result.get("allowed")
        else:
            assert result.allowed

        await adapter.stop()

    @pytest.mark.asyncio
    async def test_get_mandatory_disclosure(self, adapter):
        await adapter.start()

        disclosure = await adapter.get_mandatory_disclosure()
        assert disclosure is not None

        if isinstance(disclosure, dict):
            assert "text" in disclosure
        else:
            assert hasattr(disclosure, "text")

        await adapter.stop()

    def test_get_agent_tier_community(self, adapter):
        # Before start, should return 1 (community)
        assert adapter.get_agent_tier() == 1

    def test_is_licensed_false_before_start(self, adapter):
        assert not adapter.is_licensed()

    @pytest.mark.asyncio
    async def test_is_licensed_community(self, adapter):
        await adapter.start()
        # Mock returns community mode
        assert not adapter.is_licensed()
        await adapter.stop()

    @pytest.mark.asyncio
    async def test_services_registered(self, adapter):
        await adapter.start()

        services = adapter.get_services_to_register()
        assert len(services) == 1
        assert services[0].service_type.value == "verification"

        await adapter.stop()

    @pytest.mark.asyncio
    async def test_double_start_idempotent(self, adapter):
        await adapter.start()
        service1 = adapter._service

        await adapter.start()
        service2 = adapter._service

        # Should be the same service instance
        assert service1 is service2

        await adapter.stop()


class TestCIRISVerifyService:
    """Tests for CIRISVerifyService."""

    @pytest.fixture
    def service(self):
        config = VerificationConfig(use_mock=True)
        return CIRISVerifyService(config)

    @pytest.mark.asyncio
    async def test_initialize(self, service):
        result = await service.initialize()
        assert result is True
        assert service._initialized

    @pytest.mark.asyncio
    async def test_get_license_status_caches(self, service):
        await service.initialize()

        # First call
        status1 = await service.get_license_status()
        assert status1 is not None

        # Second call should use cache
        status2 = await service.get_license_status()
        assert status2 is not None

        # Cache should be populated
        assert service._cache is not None
        assert service._cache.is_valid()

    @pytest.mark.asyncio
    async def test_force_refresh_bypasses_cache(self, service):
        await service.initialize()

        # Populate cache
        await service.get_license_status()
        old_cache = service._cache

        # Force refresh
        await service.get_license_status(force_refresh=True)
        new_cache = service._cache

        # Cache should be updated (different timestamp)
        assert new_cache.cached_at >= old_cache.cached_at

    @pytest.mark.asyncio
    async def test_shutdown(self, service):
        await service.initialize()
        await service.shutdown()

        assert not service._initialized
        assert service._cache is None


class TestFallbackMockClient:
    """Tests for fallback mock when ciris-verify package not installed."""

    @pytest.fixture
    def client(self):
        return _FallbackMockClient()

    @pytest.mark.asyncio
    async def test_returns_community_mode(self, client):
        status = await client.get_license_status(b"x" * 32)
        assert status["status"] == 200  # UNLICENSED_COMMUNITY

    @pytest.mark.asyncio
    async def test_denies_professional_capabilities(self, client):
        result = await client.check_capability("medical:diagnosis")
        assert not result["allowed"]

    @pytest.mark.asyncio
    async def test_allows_standard_operations(self, client):
        result = await client.check_capability("standard:telemetry")
        assert result["allowed"]

        result = await client.check_capability("tool:search")
        assert result["allowed"]
