"""
Tests for anonymous user handling in AdaptiveFilterService.

Validates that:
1. Trust scores persist through anonymization  
2. PII is properly removed from profiles
3. Anti-gaming measures work
4. Anonymous users can still be filtered effectively
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock

import pytest

from ciris_engine.logic.services.governance.consent import ConsentService
from ciris_engine.logic.services.governance.filter import AdaptiveFilterService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.consent.core import ConsentCategory, ConsentRequest, ConsentStream
from ciris_engine.schemas.services.filters_core import (
    AdaptiveFilterConfig,
    FilterPriority,
    UserTrustProfile,
)


class MockTimeService(TimeServiceProtocol):
    """Mock time service for testing."""
    
    def __init__(self):
        self._current_time = datetime.now(timezone.utc)
    
    def now(self) -> datetime:
        return self._current_time
    
    def advance_time(self, **kwargs):
        """Advance time for testing."""
        self._current_time += timedelta(**kwargs)
    
    def format_timestamp(self, dt: datetime) -> str:
        return dt.isoformat()
    
    def parse_timestamp(self, timestamp: str) -> datetime:
        return datetime.fromisoformat(timestamp)


class MockConfigService:
    """Mock config service."""
    
    def __init__(self):
        self._configs = {}
    
    async def get_config(self, key: str):
        return self._configs.get(key)
    
    async def set_config(self, key: str, value, metadata=None):
        self._configs[key] = value
        return Mock(success=True)


@pytest.fixture
def time_service():
    """Provide mock time service."""
    return MockTimeService()


@pytest.fixture
async def filter_service(time_service):
    """Provide filter service."""
    memory_service = Mock()
    config_service = MockConfigService()
    
    service = AdaptiveFilterService(
        memory_service=memory_service,
        time_service=time_service,
        llm_service=None,
        config_service=config_service,
    )
    await service.start()
    
    # Initialize with default config
    service._config = AdaptiveFilterConfig()
    
    yield service
    await service.stop()


@pytest.fixture
async def consent_service(time_service, filter_service):
    """Provide consent service linked to filter."""
    service = ConsentService(time_service=time_service)
    service._filter_service = filter_service
    await service.start()
    yield service
    await service.stop()


class TestAnonymousFiltering:
    """Test anonymous user filtering."""
    
    @pytest.mark.asyncio
    async def test_trust_score_persists_through_anonymization(self, filter_service):
        """Test that trust scores persist when user becomes anonymous."""
        user_id = "test_user_123"
        
        # Create profile with violations
        filter_service._config.user_profiles[user_id] = UserTrustProfile(
            user_id=user_id,
            user_hash=filter_service._hash_user_id(user_id),
            first_seen=filter_service._now(),
            last_seen=filter_service._now(),
            trust_score=0.3,
            violation_count=5,
            message_count=100,
        )
        
        original_trust = filter_service._config.user_profiles[user_id].trust_score
        original_violations = filter_service._config.user_profiles[user_id].violation_count
        
        # Anonymize user
        await filter_service.anonymize_user_profile(user_id)
        
        # Profile should be moved to anonymous ID
        anon_id = f"anon_{filter_service._hash_user_id(user_id)}"
        assert anon_id in filter_service._config.user_profiles
        assert user_id not in filter_service._config.user_profiles
        
        # Trust score and violations should persist
        anon_profile = filter_service._config.user_profiles[anon_id]
        assert anon_profile.trust_score == original_trust
        assert anon_profile.violation_count == original_violations
        assert anon_profile.is_anonymous is True
    
    @pytest.mark.asyncio
    async def test_pii_removed_from_profiles(self, filter_service):
        """Test that PII is removed from profiles."""
        user_id = "test_user_456"
        
        # Create profile with PII
        filter_service._config.user_profiles[user_id] = UserTrustProfile(
            user_id=user_id,
            user_hash=filter_service._hash_user_id(user_id),
            first_seen=filter_service._now(),
            last_seen=filter_service._now(),
            roles=["moderator", "trusted"],  # PII
            flags=["identified", "named", "suspicious"],
        )
        
        # Anonymize
        await filter_service.anonymize_user_profile(user_id)
        
        # Check anonymous profile
        anon_id = f"anon_{filter_service._hash_user_id(user_id)}"
        anon_profile = filter_service._config.user_profiles[anon_id]
        
        assert anon_profile.roles == []  # PII cleared
        assert "identified" not in anon_profile.flags
        assert "named" not in anon_profile.flags
        assert "suspicious" in anon_profile.flags  # Safety flag retained
        assert "anonymized" in anon_profile.flags
    
    @pytest.mark.asyncio
    async def test_anti_gaming_rapid_switching(self, filter_service):
        """Test detection of rapid consent switching."""
        user_id = "gamer_789"
        
        # Simulate rapid transitions
        assert await filter_service.handle_consent_transition(user_id, "temporary", "anonymous") is False
        assert await filter_service.handle_consent_transition(user_id, "anonymous", "temporary") is False
        assert await filter_service.handle_consent_transition(user_id, "temporary", "anonymous") is False
        assert await filter_service.handle_consent_transition(user_id, "anonymous", "temporary") is True  # 4th transition
        
        # Should be flagged
        profile = filter_service._config.user_profiles[user_id]
        assert profile.rapid_switching_flag is True
        assert profile.evasion_score > 0
        assert profile.consent_transitions_24h == 4
    
    @pytest.mark.asyncio
    async def test_anti_gaming_after_moderation(self, filter_service, time_service):
        """Test detection of switching to anonymous right after moderation."""
        user_id = "evader_101"
        
        # Create profile with recent moderation
        filter_service._config.user_profiles[user_id] = UserTrustProfile(
            user_id=user_id,
            user_hash=filter_service._hash_user_id(user_id),
            first_seen=filter_service._now(),
            last_seen=filter_service._now(),
            last_moderation=filter_service._now(),
        )
        
        # Try to switch to anonymous immediately
        is_gaming = await filter_service.handle_consent_transition(user_id, "temporary", "anonymous")
        
        assert is_gaming is True
        profile = filter_service._config.user_profiles[user_id]
        assert profile.evasion_score > 0
    
    @pytest.mark.asyncio
    async def test_filter_decision_for_anonymous(self, filter_service):
        """Test that filter decisions work for anonymous users."""
        user_id = "anon_user_202"
        user_hash = filter_service._hash_user_id(user_id)
        
        # Create anonymous profile with poor trust
        anon_id = f"anon_{user_hash}"
        filter_service._config.user_profiles[anon_id] = UserTrustProfile(
            user_id=anon_id,
            user_hash=user_hash,
            first_seen=filter_service._now(),
            last_seen=filter_service._now(),
            trust_score=0.15,
            is_anonymous=True,
        )
        
        # Should get high priority filtering
        priority = filter_service.get_filter_decision_for_anonymous(user_id)
        assert priority == FilterPriority.CRITICAL
    
    @pytest.mark.asyncio
    async def test_gaming_increases_filter_priority(self, filter_service):
        """Test that gaming attempts increase filter priority."""
        user_id = "gamer_606"
        
        # Create profile with gaming behavior
        filter_service._config.user_profiles[user_id] = UserTrustProfile(
            user_id=user_id,
            user_hash=filter_service._hash_user_id(user_id),
            first_seen=filter_service._now(),
            last_seen=filter_service._now(),
            rapid_switching_flag=True,
            evasion_score=0.6,
            trust_score=0.7,  # Otherwise decent trust
        )
        
        # Should still get high priority due to gaming
        priority = filter_service.get_filter_decision_for_anonymous(user_id)
        assert priority == FilterPriority.HIGH
    
    @pytest.mark.asyncio
    async def test_hash_stability(self, filter_service):
        """Test that user hashes are stable across sessions."""
        user_id = "stable_user_404"
        
        hash1 = filter_service._hash_user_id(user_id)
        hash2 = filter_service._hash_user_id(user_id)
        
        assert hash1 == hash2
        assert len(hash1) == 16  # Truncated SHA256
        assert user_id not in hash1  # No PII in hash


class TestConsentIntegration:
    """Test integration between consent and filter services."""
    
    @pytest.mark.asyncio
    async def test_consent_transition_notifies_filter(self, consent_service, filter_service):
        """Test that consent transitions notify filter service."""
        user_id = "integrated_909"
        
        # Create initial consent
        request = ConsentRequest(
            user_id=user_id,
            stream=ConsentStream.TEMPORARY,
            categories=[],
        )
        await consent_service.grant_consent(request)
        
        # Switch to anonymous
        request.stream = ConsentStream.ANONYMOUS
        await consent_service.grant_consent(request)
        
        # Filter should have been notified
        if user_id in filter_service._config.user_profiles:
            profile = filter_service._config.user_profiles[user_id]
            assert profile.consent_stream == "anonymous"
    
    @pytest.mark.asyncio
    async def test_revoke_triggers_anonymization(self, consent_service, filter_service):
        """Test that revoking consent triggers profile anonymization."""
        user_id = "decay_user_707"
        
        # Create consent and profile
        request = ConsentRequest(
            user_id=user_id,
            stream=ConsentStream.TEMPORARY,
            categories=[ConsentCategory.INTERACTION],
        )
        await consent_service.grant_consent(request)
        
        # Create filter profile
        filter_service._config.user_profiles[user_id] = UserTrustProfile(
            user_id=user_id,
            user_hash=filter_service._hash_user_id(user_id),
            first_seen=filter_service._now(),
            last_seen=filter_service._now(),
            trust_score=0.5,
        )
        
        # Revoke consent
        await consent_service.revoke_consent(user_id, "User requested deletion")
        
        # Profile should be anonymized
        anon_id = f"anon_{filter_service._hash_user_id(user_id)}"
        assert anon_id in filter_service._config.user_profiles
        assert user_id not in filter_service._config.user_profiles