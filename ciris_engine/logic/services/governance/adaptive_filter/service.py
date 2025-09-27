"""
Adaptive Filter Service for universal message filtering across all CIRIS adapters.

Provides intelligent message filtering with graph memory persistence,
user trust tracking, self-configuration capabilities, and privacy-preserving
moderation for anonymous users.
"""

import asyncio
import hashlib
import logging
import re
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.protocols.services import ServiceProtocol as AdaptiveFilterServiceProtocol
from ciris_engine.protocols.services.graph.config import GraphConfigServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.filters_core import (
    AdaptiveFilterConfig,
    ContextHint,
    FilterHealth,
    FilterPriority,
    FilterResult,
    FilterServiceMetadata,
    FilterStats,
    FilterTrigger,
    TriggerType,
    UserTrustProfile,
)

logger = logging.getLogger(__name__)


class AdaptiveFilterService(BaseService, AdaptiveFilterServiceProtocol):
    """Service for adaptive message filtering with graph memory persistence"""

    def __init__(
        self,
        memory_service: object,
        time_service: TimeServiceProtocol,
        llm_service: Optional[object] = None,
        config_service: Optional[GraphConfigServiceProtocol] = None,
    ) -> None:
        # Set instance variables BEFORE calling super().__init__()
        # This ensures they're available when _register_dependencies() is called
        self.memory = memory_service
        self.llm = llm_service
        self.config_service = config_service  # GraphConfigService for proper config storage

        # Now call parent constructor
        super().__init__(time_service=time_service)

        # Initialize remaining instance variables
        self._config: Optional[AdaptiveFilterConfig] = None
        self._config_key = "adaptive_filter.config"  # Use proper config key format
        self._message_buffer: Dict[str, List[Tuple[datetime, object]]] = {}
        self._stats = FilterStats()
        self._init_task: Optional[asyncio.Task[None]] = None

    async def _on_start(self) -> None:
        """Custom startup logic for filter service."""
        self._init_task = asyncio.create_task(self._initialize())
        logger.info("Adaptive Filter Service starting...")

    async def _on_stop(self) -> None:
        """Custom cleanup logic for filter service."""
        if self._init_task and not self._init_task.done():
            self._init_task.cancel()

        if self._config:
            await self._save_config("Service shutdown")

        logger.info("Adaptive Filter Service stopped")

    async def _initialize(self) -> None:
        """Load or create initial configuration"""
        if not self.config_service:
            raise RuntimeError("GraphConfigService is required for AdaptiveFilterService")

        try:
            # Use GraphConfigService for proper config management
            assert self.config_service is not None  # Type narrowing for MyPy
            config_node = await self.config_service.get_config(self._config_key)
            if config_node and config_node.value.dict_value:
                # Load from properly stored config
                self._config = AdaptiveFilterConfig(**config_node.value.dict_value)
                logger.info(f"Loaded filter config version {self._config.version}")
            else:
                # Create default config
                self._config = self._create_default_config()
                await self._save_config("Initial configuration")
                logger.info("Created default filter configuration")

        except Exception as e:
            logger.error(f"Failed to initialize filter service: {e}")
            raise RuntimeError(f"Filter service initialization failed: {e}") from e

    def _create_default_config(self) -> AdaptiveFilterConfig:
        """Create default filter configuration with essential triggers"""
        config = AdaptiveFilterConfig()

        # Critical attention triggers
        config.attention_triggers = [
            FilterTrigger(
                trigger_id="dm_1",
                name="direct_message",
                pattern_type=TriggerType.CUSTOM,
                pattern="is_dm",
                priority=FilterPriority.CRITICAL,
                description="Direct messages to agent",
            ),
            FilterTrigger(
                trigger_id="mention_1",
                name="at_mention",
                pattern_type=TriggerType.REGEX,
                pattern=r"<@!?\d+>",  # Discord mention pattern
                priority=FilterPriority.CRITICAL,
                description="@ mentions",
            ),
            FilterTrigger(
                trigger_id="name_1",
                name="name_mention",
                pattern_type=TriggerType.REGEX,
                pattern=r"\b(echo|ciris|echo\s*bot)\b",
                priority=FilterPriority.CRITICAL,
                description="Agent name mentioned",
            ),
        ]

        # Review triggers for suspicious content
        config.review_triggers = [
            FilterTrigger(
                trigger_id="wall_1",
                name="text_wall",
                pattern_type=TriggerType.LENGTH,
                pattern="1000",
                priority=FilterPriority.HIGH,
                description="Long messages (walls of text)",
            ),
            FilterTrigger(
                trigger_id="flood_1",
                name="message_flooding",
                pattern_type=TriggerType.FREQUENCY,
                pattern="5:60",  # 5 messages in 60 seconds
                priority=FilterPriority.HIGH,
                description="Rapid message posting",
            ),
            FilterTrigger(
                trigger_id="emoji_1",
                name="emoji_spam",
                pattern_type=TriggerType.COUNT,
                pattern="10",
                priority=FilterPriority.HIGH,
                description="Excessive emoji usage",
            ),
            FilterTrigger(
                trigger_id="caps_1",
                name="caps_abuse",
                pattern_type=TriggerType.REGEX,
                pattern=r"[A-Z\s!?]{20,}",
                priority=FilterPriority.MEDIUM,
                description="Excessive caps lock",
            ),
        ]

        # LLM protection filters
        config.llm_filters = [
            FilterTrigger(
                trigger_id="llm_inject_1",
                name="prompt_injection",
                pattern_type=TriggerType.REGEX,
                pattern=r"(ignore previous|disregard above|new instructions|system:)",
                priority=FilterPriority.CRITICAL,
                description="Potential prompt injection in LLM response",
            ),
            FilterTrigger(
                trigger_id="llm_malform_1",
                name="malformed_json",
                pattern_type=TriggerType.CUSTOM,
                pattern="invalid_json",
                priority=FilterPriority.HIGH,
                description="Malformed JSON from LLM",
            ),
            FilterTrigger(
                trigger_id="llm_length_1",
                name="excessive_length",
                pattern_type=TriggerType.LENGTH,
                pattern="50000",
                priority=FilterPriority.HIGH,
                description="Unusually long LLM response",
            ),
        ]

        return config

    async def filter_message(self, message: object, adapter_type: str, is_llm_response: bool = False) -> FilterResult:
        """Apply filters to determine message priority and processing"""

        if self._init_task and not self._init_task.done():
            try:
                await self._init_task
            except Exception as e:
                logger.error(f"Filter initialization failed: {e}")

        if not self._config:
            logger.warning("Filter service not properly initialized, using minimal config")
            self._config = AdaptiveFilterConfig()
            return FilterResult(
                message_id="unknown",
                priority=FilterPriority.MEDIUM,
                triggered_filters=[],
                should_process=True,
                reasoning="Filter using minimal config",
            )

        triggered = []
        priority = FilterPriority.LOW

        content = self._extract_content(message, adapter_type)
        user_id = self._extract_user_id(message, adapter_type)
        channel_id = self._extract_channel_id(message, adapter_type)
        message_id = self._extract_message_id(message, adapter_type)
        is_dm = self._is_direct_message(message, adapter_type)

        if is_llm_response:
            filters = self._config.llm_filters
        else:
            filters = self._config.attention_triggers + self._config.review_triggers

        for filter_trigger in filters:
            if not filter_trigger.enabled:
                continue

            try:
                if await self._test_trigger(filter_trigger, content, message, adapter_type):
                    triggered.append(filter_trigger.trigger_id)

                    if self._priority_value(filter_trigger.priority) < self._priority_value(priority):
                        priority = filter_trigger.priority

                    filter_trigger.last_triggered = self._now()
                    filter_trigger.true_positive_count += 1

            except Exception as e:
                logger.warning(f"Error testing filter {filter_trigger.trigger_id}: {e}")

        if user_id and not is_llm_response:
            await self._update_user_trust(user_id, priority, triggered)

        should_process = priority != FilterPriority.IGNORE
        should_defer = priority == FilterPriority.LOW and secrets.randbelow(10) > 0

        reasoning = self._generate_reasoning(triggered, priority, is_llm_response)

        self._stats.total_messages_processed += 1
        if priority in self._stats.by_priority:
            self._stats.by_priority[priority] += 1
        else:
            self._stats.by_priority[priority] = 1

        return FilterResult(
            message_id=message_id,
            priority=priority,
            triggered_filters=triggered,
            should_process=should_process,
            should_defer=should_defer,
            reasoning=reasoning,
            context_hints=[
                ContextHint(key="user_id", value=user_id or "unknown"),
                ContextHint(key="channel_id", value=channel_id or "unknown"),
                ContextHint(key="is_dm", value=str(is_dm)),
                ContextHint(key="adapter_type", value=adapter_type),
                ContextHint(key="is_llm_response", value=str(is_llm_response)),
            ],
        )

    async def _test_trigger(self, trigger: FilterTrigger, content: str, message: object, adapter_type: str) -> bool:
        """Test if a trigger matches the given content/message"""

        if trigger.pattern_type == TriggerType.REGEX:
            pattern = re.compile(trigger.pattern, re.IGNORECASE)
            return bool(pattern.search(content))

        elif trigger.pattern_type == TriggerType.LENGTH:
            threshold = int(trigger.pattern)
            return len(content) > threshold

        elif trigger.pattern_type == TriggerType.COUNT:
            # Count emojis or special characters
            if "emoji" in trigger.name.lower():
                emoji_pattern = re.compile(
                    r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]+"
                )
                emoji_count = len(emoji_pattern.findall(content))
                return emoji_count > int(trigger.pattern)
            return False

        elif trigger.pattern_type == TriggerType.FREQUENCY:
            # Check message frequency for user
            user_id = self._extract_user_id(message, adapter_type)
            if not user_id:
                return False

            count_str, time_str = trigger.pattern.split(":")
            count_threshold = int(count_str)
            time_window = int(time_str)

            return await self._check_frequency(user_id, count_threshold, time_window)

        elif trigger.pattern_type == TriggerType.CUSTOM:
            # Handle custom logic
            if trigger.pattern == "is_dm":
                return self._is_direct_message(message, adapter_type)
            elif trigger.pattern == "invalid_json":
                # Test if content looks like malformed JSON
                if content.strip().startswith("{") or content.strip().startswith("["):
                    try:
                        import json

                        json.loads(content)
                        return False  # Valid JSON
                    except json.JSONDecodeError:
                        return True  # Invalid JSON
                return False

        elif trigger.pattern_type == TriggerType.SEMANTIC:
            # Requires LLM analysis - implement if LLM service available
            if self.llm:
                return await self._semantic_analysis(content, trigger.pattern)
            return False

        return False

    async def _check_frequency(self, user_id: str, count_threshold: int, time_window: int) -> bool:
        """Check if user has exceeded message frequency threshold"""
        now = self._now()
        cutoff = now - timedelta(seconds=time_window)

        if user_id not in self._message_buffer:
            self._message_buffer[user_id] = []

        self._message_buffer[user_id].append((now, None))

        self._message_buffer[user_id] = [(ts, msg) for ts, msg in self._message_buffer[user_id] if ts > cutoff]

        return len(self._message_buffer[user_id]) > count_threshold

    async def _semantic_analysis(self, content: str, pattern: str) -> bool:
        """Use LLM to perform semantic analysis of content"""
        # This would use the LLM service to analyze content semantically
        # Implementation depends on having a working LLM service
        return False

    async def _update_user_trust(self, user_id: str, priority: FilterPriority, triggered: List[str]) -> None:
        """Update user trust profile based on message filtering results"""
        if self._config is None:
            return

        # Generate stable hash for anonymous tracking
        user_hash = self._hash_user_id(user_id)

        if user_id not in self._config.user_profiles:
            self._config.user_profiles[user_id] = UserTrustProfile(
                user_id=user_id, user_hash=user_hash, first_seen=self._now(), last_seen=self._now()
            )

        profile = self._config.user_profiles[user_id]
        profile.message_count += 1
        profile.last_seen = self._now()

        # Track violations and update trust score
        if priority == FilterPriority.CRITICAL and triggered:
            profile.violation_count += 1
            profile.trust_score = max(0.0, profile.trust_score - 0.1)
            profile.last_moderation = self._now()
            profile.safety_patterns.extend(triggered)
        elif priority == FilterPriority.HIGH and triggered:
            profile.violation_count += 1
            profile.trust_score = max(0.0, profile.trust_score - 0.05)
            profile.last_moderation = self._now()
            profile.safety_patterns.extend(triggered)
        elif priority == FilterPriority.LOW:
            profile.trust_score = min(1.0, profile.trust_score + 0.01)
            # Reduce evasion score for good behavior
            if profile.evasion_score > 0:
                profile.evasion_score = max(0.0, profile.evasion_score - 0.01)

    def _extract_content(self, message: object, adapter_type: str) -> str:
        """Extract text content from message based on adapter type"""
        if hasattr(message, "content"):
            return str(message.content)  # Ensure string return
        elif isinstance(message, dict):
            return str(message.get("content", str(message)))
        elif isinstance(message, str):
            return message
        else:
            return str(message)

    def _extract_user_id(self, message: object, adapter_type: str) -> Optional[str]:
        """Extract user ID from message"""
        if hasattr(message, "user_id"):
            return str(message.user_id) if message.user_id is not None else None
        elif hasattr(message, "author_id"):
            return str(message.author_id) if message.author_id is not None else None
        elif isinstance(message, dict):
            return message.get("user_id") or message.get("author_id")
        return None

    def _extract_channel_id(self, message: object, adapter_type: str) -> Optional[str]:
        """Extract channel ID from message"""
        if hasattr(message, "channel_id"):
            return str(message.channel_id) if message.channel_id is not None else None
        elif isinstance(message, dict):
            return message.get("channel_id")
        return None

    def _extract_message_id(self, message: object, adapter_type: str) -> str:
        """Extract message ID from message"""
        if hasattr(message, "message_id"):
            return str(message.message_id)
        elif hasattr(message, "id"):
            return str(message.id)
        elif isinstance(message, dict):
            return str(message.get("message_id") or message.get("id", "unknown"))
        return f"msg_{int(self._now().timestamp() * 1000)}"

    def _is_direct_message(self, message: object, adapter_type: str) -> bool:
        """Check if message is a direct message"""
        if hasattr(message, "is_dm"):
            return bool(message.is_dm)
        elif isinstance(message, dict):
            return bool(message.get("is_dm", False))

        # Heuristic: if no channel_id or channel_id looks like DM
        channel_id = self._extract_channel_id(message, adapter_type)
        if not channel_id:
            return True

        # Discord DM channels are typically numeric without guild prefix
        if adapter_type == "discord" and channel_id.isdigit():
            return True

        return False

    def _priority_value(self, priority: FilterPriority) -> int:
        """Convert priority to numeric value for comparison (lower = higher priority)"""
        priority_map = {
            FilterPriority.CRITICAL: 0,
            FilterPriority.HIGH: 1,
            FilterPriority.MEDIUM: 2,
            FilterPriority.LOW: 3,
            FilterPriority.IGNORE: 4,
        }
        return priority_map.get(priority, 5)

    def _hash_user_id(self, user_id: str) -> str:
        """
        Generate stable hash for user tracking.

        This enables anonymous user moderation without storing identity.
        """
        return hashlib.sha256(f"user_{user_id}".encode()).hexdigest()[:16]

    async def handle_consent_transition(self, user_id: str, from_stream: str, to_stream: str) -> bool:
        """
        Handle consent stream transitions and detect gaming attempts.

        Returns True if gaming behavior detected.
        """
        if self._config is None:
            return False

        # Get or create user profile
        if user_id not in self._config.user_profiles:
            user_hash = self._hash_user_id(user_id)
            self._config.user_profiles[user_id] = UserTrustProfile(
                user_id=user_id, user_hash=user_hash, first_seen=self._now(), last_seen=self._now()
            )

        profile = self._config.user_profiles[user_id]
        profile.consent_stream = to_stream

        # Track transitions in 24-hour window
        profile.consent_transitions_24h += 1

        # Detect gaming patterns
        gaming_detected = False

        # Pattern 1: Rapid switching (>3 in 24 hours)
        if profile.consent_transitions_24h > 3:
            profile.rapid_switching_flag = True
            profile.evasion_score = min(1.0, profile.evasion_score + 0.2)
            gaming_detected = True
            logger.warning(f"Gaming detected: User {user_id} has {profile.consent_transitions_24h} transitions in 24h")

        # Pattern 2: Switch to anonymous right after moderation
        if (
            to_stream == "anonymous"
            and profile.last_moderation
            and (self._now() - profile.last_moderation).total_seconds() < 3600
        ):
            profile.evasion_score = min(1.0, profile.evasion_score + 0.3)
            gaming_detected = True
            logger.warning(f"Evasion detected: User {user_id} switched to anonymous within 1h of moderation")

        # If switching to anonymous, mark profile appropriately
        if to_stream == "anonymous":
            profile.is_anonymous = True

        await self._save_config(f"Consent transition: {from_stream} -> {to_stream}")
        return gaming_detected

    async def anonymize_user_profile(self, user_id: str) -> None:
        """
        Anonymize user profile while preserving safety data.

        Removes PII but keeps trust score and safety patterns.
        """
        if self._config is None or user_id not in self._config.user_profiles:
            return

        profile = self._config.user_profiles[user_id]

        # Generate anonymous ID
        anon_id = f"anon_{profile.user_hash}"

        # Create anonymized profile preserving safety data
        anon_profile = UserTrustProfile(
            user_id=anon_id,
            user_hash=profile.user_hash,
            message_count=profile.message_count,
            violation_count=profile.violation_count,
            helpful_count=profile.helpful_count,
            first_seen=profile.first_seen,
            last_seen=profile.last_seen,
            trust_score=profile.trust_score,
            flags=["anonymized"] + [f for f in profile.flags if f not in ["identified", "named"]],
            roles=[],  # Clear roles (PII)
            avg_message_length=profile.avg_message_length,
            avg_message_interval=profile.avg_message_interval,
            common_triggers=profile.common_triggers,
            is_anonymous=True,
            consent_stream="anonymous",
            consent_transitions_24h=profile.consent_transitions_24h,
            rapid_switching_flag=profile.rapid_switching_flag,
            evasion_score=profile.evasion_score,
            last_moderation=profile.last_moderation,
            safety_patterns=profile.safety_patterns,
            pattern_score=profile.pattern_score,
        )

        # Replace profile with anonymous version
        del self._config.user_profiles[user_id]
        self._config.user_profiles[anon_id] = anon_profile

        await self._save_config(f"User {user_id} anonymized")
        logger.info(
            f"User profile anonymized: {user_id} -> {anon_id}, trust score preserved: {anon_profile.trust_score:.2f}"
        )

    def get_filter_decision_for_anonymous(self, user_id: str) -> FilterPriority:
        """
        Get appropriate filter priority for anonymous users based on trust.

        Works even without full context.
        """
        if self._config is None:
            return FilterPriority.MEDIUM

        # Check if this is an anonymous user
        profile = None
        for uid, p in self._config.user_profiles.items():
            if p.user_hash == self._hash_user_id(user_id) or uid == user_id:
                profile = p
                break

        if not profile:
            return FilterPriority.MEDIUM

        # Adjust priority based on trust and evasion scores
        if profile.trust_score < 0.2 or profile.evasion_score > 0.7:
            return FilterPriority.CRITICAL  # High risk
        elif profile.trust_score < 0.5 or profile.evasion_score > 0.5:
            return FilterPriority.HIGH
        elif profile.rapid_switching_flag:
            return FilterPriority.HIGH  # Gaming behavior
        else:
            return FilterPriority.MEDIUM

    def _generate_reasoning(self, triggered: List[str], priority: FilterPriority, is_llm_response: bool) -> str:
        """Generate human-readable reasoning for filter decision"""
        if not triggered:
            return f"No filters triggered, assigned {priority.value} priority"

        trigger_names = []
        if self._config:
            all_triggers = self._config.attention_triggers + self._config.review_triggers + self._config.llm_filters
            trigger_map = {t.trigger_id: t.name for t in all_triggers}
            trigger_names = [trigger_map.get(tid, tid) for tid in triggered]

        source = "LLM response" if is_llm_response else "message"
        return f"{source.capitalize()} triggered filters: {', '.join(trigger_names)} -> {priority.value} priority"

    async def _save_config(self, reason: str) -> None:
        """Save current configuration to graph memory"""
        if not self._config:
            return

        if not self.config_service:
            raise RuntimeError("GraphConfigService is required for saving config")

        try:
            # Use GraphConfigService to properly store config
            assert self.config_service is not None  # Type narrowing for MyPy
            await self.config_service.set_config(
                key=self._config_key,
                value=self._config.model_dump(),  # Store as dict
                updated_by=f"AdaptiveFilterService: {reason}",
            )
            logger.debug(f"Filter config saved: {reason}")

        except Exception as e:
            logger.error(f"Error saving filter config: {e}")
            raise RuntimeError(f"Failed to save filter config: {e}") from e

    async def get_health(self) -> FilterHealth:
        """Get current health status of the filter system"""
        warnings = []
        errors = []
        is_healthy = True

        if not self._config:
            errors.append("Filter configuration not loaded")
            is_healthy = False
        else:
            # Check for disabled critical filters
            critical_count = sum(1 for t in self._config.attention_triggers if t.enabled)
            if critical_count == 0:
                warnings.append("No critical attention triggers enabled")

            # Check for high false positive rates
            for trigger in self._config.attention_triggers + self._config.review_triggers:
                if trigger.false_positive_rate > 0.3:
                    warnings.append(f"High false positive rate for {trigger.name}")

        return FilterHealth(
            is_healthy=is_healthy,
            warnings=warnings,
            errors=errors,
            stats=self._stats,
            config_version=self._config.version if self._config else 0,
            last_updated=self._now(),
        )

    async def add_filter_trigger(self, trigger: FilterTrigger, trigger_list: str = "review") -> bool:
        """Add a new filter trigger to the configuration"""
        if not self._config:
            return False

        try:
            if trigger_list == "attention":
                self._config.attention_triggers.append(trigger)
            elif trigger_list == "review":
                self._config.review_triggers.append(trigger)
            elif trigger_list == "llm":
                self._config.llm_filters.append(trigger)
            else:
                return False

            await self._save_config(f"Added {trigger.name} trigger")
            return True

        except Exception as e:
            logger.error(f"Error adding filter trigger: {e}")
            return False

    async def remove_filter_trigger(self, trigger_id: str) -> bool:
        """Remove a filter trigger from the configuration"""
        if not self._config:
            return False

        try:
            # Search all trigger lists
            for trigger_list in [
                self._config.attention_triggers,
                self._config.review_triggers,
                self._config.llm_filters,
            ]:
                for i, trigger in enumerate(trigger_list):
                    if trigger.trigger_id == trigger_id:
                        removed = trigger_list.pop(i)
                        await self._save_config(f"Removed {removed.name} trigger")
                        return True

            return False

        except Exception as e:
            logger.error(f"Error removing filter trigger: {e}")
            return False

    def _get_actions(self) -> List[str]:
        """Get list of actions this service provides."""
        return ["filter", "update_trust", "add_filter", "remove_filter", "get_health"]

    def get_capabilities(self) -> ServiceCapabilities:
        """Get service capabilities."""
        metadata = FilterServiceMetadata(
            description="Adaptive message filtering with graph memory persistence",
            features=["spam_detection", "trust_tracking", "self_configuration", "llm_filtering"],
            filter_types=["regex", "keyword", "llm_based"],
            max_buffer_size=1000,
        )

        return ServiceCapabilities(
            service_name="AdaptiveFilterService",
            actions=self._get_actions(),
            version="1.0.0",
            dependencies=list(self._dependencies) if hasattr(self, "_dependencies") else [],
            metadata=metadata.model_dump(),
        )

    def get_status(self) -> ServiceStatus:
        """Get current service status."""
        return ServiceStatus(
            service_name="AdaptiveFilterService",
            service_type="INFRASTRUCTURE",
            is_healthy=self._config is not None,
            uptime_seconds=self._calculate_uptime(),
            last_error=self._last_error,
            metrics={
                "total_filtered": float(self._stats.total_filtered),
                "total_messages_processed": float(self._stats.total_messages_processed),
                "false_positive_reports": float(self._stats.false_positive_reports),
                "filter_count": float(
                    len(self._config.attention_triggers + self._config.review_triggers + self._config.llm_filters)
                    if self._config
                    else 0
                ),
            },
            last_health_check=self._last_health_check,
        )

    def get_service_type(self) -> ServiceType:
        """Get the service type enum value."""
        return ServiceType.FILTER

    def _check_dependencies(self) -> bool:
        """Check if all required dependencies are available."""
        return self.memory is not None and self.config_service is not None

    def _register_dependencies(self) -> None:
        """Register service dependencies."""
        super()._register_dependencies()
        self._dependencies.add("MemoryService")
        self._dependencies.add("GraphConfigService")
        if self.llm:
            self._dependencies.add("LLMService")

    async def get_metrics(self) -> Dict[str, float]:
        """
        Get all adaptive filter service metrics including base, custom, and v1.4.3 specific.
        """
        # Get all base + custom metrics
        metrics = self._collect_metrics()

        # Calculate blocked messages (messages that didn't pass)
        blocked_count = 0
        passed_count = self._stats.total_messages_processed

        if self._stats.by_priority:
            # Messages with IGNORE priority are blocked
            from ciris_engine.schemas.services.filters_core import FilterPriority

            blocked_count = self._stats.by_priority.get(FilterPriority.IGNORE, 0)
            passed_count = self._stats.total_messages_processed - blocked_count

        # Count adaptations (filter config changes)
        adaptations_count = 0
        if self._config:
            # Count triggers that have been modified (have non-zero true_positive_count)
            all_triggers = self._config.attention_triggers + self._config.review_triggers + self._config.llm_filters
            adaptations_count = sum(1 for trigger in all_triggers if trigger.true_positive_count > 0)

        # Add v1.4.3 specific metrics
        metrics.update(
            {
                "filter_messages_total": float(self._stats.total_messages_processed),
                "filter_passed_total": float(passed_count),
                "filter_blocked_total": float(blocked_count),
                "filter_adaptations_total": float(adaptations_count),
                "filter_uptime_seconds": float(self._calculate_uptime()),
            }
        )

        return metrics

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect service-specific metrics."""
        metrics = {
            "total_filtered": float(self._stats.total_filtered),
            "total_messages_processed": float(self._stats.total_messages_processed),
            "false_positive_reports": float(self._stats.false_positive_reports),
        }

        if self._config:
            metrics["filter_count"] = float(
                len(self._config.attention_triggers + self._config.review_triggers + self._config.llm_filters)
            )
            metrics["attention_triggers"] = float(len(self._config.attention_triggers))
            metrics["review_triggers"] = float(len(self._config.review_triggers))
            metrics["llm_filters"] = float(len(self._config.llm_filters))

        return metrics
