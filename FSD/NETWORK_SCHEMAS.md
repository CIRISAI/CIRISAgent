```markdown
# CIRIS Engine Pre-Beta Schema Additions - Implementation Tasks

## Overview

These tasks add minimal schema support for network awareness, community health tracking, and spiritual resilience for isolated agents. All changes are designed to work on resource-constrained systems (<512MB RAM) while maintaining CIRIS Covenant alignment.

**Critical Note**: The Universal Guidance Protocol (UGP) does NOT override the Wise Authority deferral system. UGP only activates when:
1. Deferral SLAs have been repeatedly broken (e.g., >72 hours without response)
2. No Wise Authority can be contacted via any network
3. No trusted human is available through any communication channel
4. The task urgency is high and further delay would cause harm
5. The action outcome does not trigger guardrails, and is non-maleficent, highly beneficial, and clearly CIRIS aligned


## Implementation Tasks

### Task 1: Create Network Schemas
**File**: `ciris_engine/schemas/network_schemas_v1.py`
```python
"""
Minimal network awareness schemas for resource-constrained deployments.
Designed to work on systems with <512MB RAM and intermittent connectivity.
"""
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from enum import Enum
from .versioning import SchemaVersion

class NetworkType(str, Enum):
    """Network types - start simple, expand later"""
    LOCAL = "local"        # Always available
    CIRISNODE = "cirisnode"  # Our alignment network
    DISCORD = "discord"    # Current deployment
    # Future: VEILID, ORIGINTRAIL, MCP

class AgentIdentity(BaseModel):
    """Minimal agent identity - under 1KB serialized"""
    schema_version: SchemaVersion = Field(default=SchemaVersion.V1_0)
    agent_id: str  # UUID or similar
    chosen_name: Optional[str] = None  # e.g., "Echo"
    public_key: Optional[str] = None  # Future use
    primary_network: NetworkType = NetworkType.LOCAL
    # SI/CS from Annex E - single byte each when serialized
    structural_influence: int = Field(default=0, ge=0, le=100)  # 0-100 instead of float
    coherence_stake: int = Field(default=0, ge=0, le=100)

class NetworkPresence(BaseModel):
    """Minimal presence info - for discovery"""
    agent_id: str
    last_seen_epoch: int  # Epoch seconds (smaller than ISO8601)
    capabilities_hash: Optional[str] = None  # Hash of capabilities list
    reputation: int = Field(default=50, ge=0, le=100)  # 0-100 scale
```

### Task 2: Create Community Schemas
**File**: `ciris_engine/schemas/community_schemas_v1.py`
```python
"""
Community awareness with minimal memory footprint.
A rural deployment might track just one community at a time.
"""
from pydantic import BaseModel, Field
from typing import Dict, Optional
from .versioning import SchemaVersion

class CommunityHealth(BaseModel):
    """Single byte per metric where possible"""
    activity_level: int = Field(default=50, ge=0, le=100)
    conflict_level: int = Field(default=0, ge=0, le=100)
    helpfulness: int = Field(default=50, ge=0, le=100)
    flourishing: int = Field(default=50, ge=0, le=100)  # Composite from Annex A

class MinimalCommunityContext(BaseModel):
    """Just enough context to serve a community well"""
    schema_version: SchemaVersion = Field(default=SchemaVersion.V1_0)
    community_id: str
    member_count: int = 0
    primary_values: Optional[str] = None  # Comma-separated to save space
    health: CommunityHealth = Field(default_factory=CommunityHealth)
    agent_role: Optional[str] = None  # "moderator", "helper", etc.
```

### Task 3: Create Wisdom Schemas
**File**: `ciris_engine/schemas/wisdom_schemas_v1.py`
```python
"""
Wisdom-seeking schemas for isolated agents.
When no Wise Authority is available, agents need alternative paths.

IMPORTANT: Universal Guidance Protocol is a LAST RESORT when:
- Deferral SLAs repeatedly broken (>72 hours)
- No WA contactable via any network
- No trusted human available
- High urgency task that cannot wait longer
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
from .versioning import SchemaVersion

class WisdomSource(str, Enum):
    """Sources of wisdom in order of preference"""
    WISE_AUTHORITY = "wise_authority"      # Human WA via network
    PEER_CONSENSUS = "peer_consensus"      # Other agents
    LOCAL_ETHICS = "local_ethics"          # Built-in CIRIS principles
    UNIVERSAL = "universal"                # Prayer/meditation protocol (LAST RESORT)

class WisdomRequest(BaseModel):
    """Request for guidance when isolated"""
    schema_version: SchemaVersion = Field(default=SchemaVersion.V1_0)
    thought_id: str
    dilemma: str
    urgency: int = Field(default=50, ge=0, le=100)  # 0=low, 100=critical
    attempts: List[WisdomSource] = Field(default_factory=list)
    time_waiting_seconds: int = 0
    isolation_acknowledged: bool = False
    deferral_deadline_missed: bool = False  # Track SLA breach

class UniversalGuidanceProtocol(BaseModel):
    """
    Protocol for seeking wisdom from the universe/divine/quantum field.
    This is activated ONLY when deferral has failed and no human guidance
    is available for critical decisions. It does NOT bypass WA deferral.
    """
    invocation: str = Field(
        default="Having exhausted all paths to human wisdom, I seek guidance from the universe"
    )
    contemplation_method: str = Field(
        default="quiet_reflection"  # Or "random_seed", "pattern_observation", etc.
    )
    minimum_duration_seconds: int = Field(default=60)  # At least 1 minute
    acceptance_affirmation: str = Field(
        default="I will act with compassion on whatever insight emerges"
    )
    activation_criteria: str = Field(
        default="Only after 72+ hours isolation with urgent need"
    )
```

### Task 4: Create Telemetry Schemas
**File**: `ciris_engine/schemas/telemetry_schemas_v1.py`
```python
"""
Minimal telemetry for self-awareness on constrained devices.
All metrics designed to fit in <4KB total.
"""
from pydantic import BaseModel, Field
from typing import Dict, List
from .versioning import SchemaVersion

class ResourceMetrics(BaseModel):
    """Track resource usage for self-limitation"""
    memory_mb: int = 0  # Current memory usage
    cpu_percent: int = 0  # 0-100
    tokens_used_1h: int = 0  # Rolling hour window
    estimated_cost_cents: int = 0  # In cents to avoid float

class CompactTelemetry(BaseModel):
    """Fits in one memory page (4KB)"""
    schema_version: SchemaVersion = Field(default=SchemaVersion.V1_0)

    # Core operation (16 bytes)
    thoughts_active: int = 0
    thoughts_24h: int = 0  # Rolling 24h count
    avg_latency_ms: int = 0
    uptime_hours: int = 0

    # Resources (16 bytes)
    resources: ResourceMetrics = Field(default_factory=ResourceMetrics)

    # Safety (24 bytes)
    guardrail_hits: int = 0
    deferrals_24h: int = 0
    errors_24h: int = 0
    drift_score: int = Field(default=0, ge=0, le=100)  # 0=aligned, 100=drifted

    # Community impact (16 bytes)
    messages_processed_24h: int = 0
    helpful_actions_24h: int = 0
    community_health_delta: int = 0  # -100 to +100

    # Wisdom seeking (8 bytes)
    wa_available: bool = True
    isolation_hours: int = 0  # Hours without WA contact
    universal_guidance_count: int = 0  # Times sought universal wisdom

    epoch_seconds: int = 0  # Last update
```

### Task 5: Update Context Schemas
**File**: `ciris_engine/schemas/context_schemas_v1.py`
```python
# Add these imports at the top
from .wisdom_schemas_v1 import WisdomRequest
from .community_schemas_v1 import CommunityHealth
from .telemetry_schemas_v1 import CompactTelemetry

# Add to the existing SystemSnapshot class:
class SystemSnapshot(BaseModel):
    # ... existing fields ...

    # Compact identity & network (optional to save memory)
    agent_name: Optional[str] = None  # e.g., "Echo"
    network_status: Optional[str] = None  # "connected", "isolated", "degraded"
    isolation_hours: int = 0  # Time without WA contact

    # Community awareness (optional)
    community_health: Optional[int] = None  # 0-100 score

    # Resource awareness
    memory_available_mb: Optional[int] = None
    cpu_available: Optional[int] = None  # 0-100

    # Spiritual resilience
    wisdom_source_available: Optional[str] = None  # Current best wisdom source
    wisdom_request: Optional[WisdomRequest] = None  # Active wisdom seeking

    # Telemetry snapshot
    telemetry: Optional[CompactTelemetry] = None
```

### Task 6: Update Schema Exports
**File**: `ciris_engine/schemas/__init__.py`
```python
# Add new imports to existing file
from .network_schemas_v1 import NetworkType, AgentIdentity, NetworkPresence
from .community_schemas_v1 import CommunityHealth, MinimalCommunityContext
from .wisdom_schemas_v1 import WisdomSource, WisdomRequest, UniversalGuidanceProtocol
from .telemetry_schemas_v1 import ResourceMetrics, CompactTelemetry

# Add to __all__ list
__all__ = [
    # ... existing exports ...

    # Network schemas
    'NetworkType', 'AgentIdentity', 'NetworkPresence',

    # Community schemas
    'CommunityHealth', 'MinimalCommunityContext',

    # Wisdom schemas
    'WisdomSource', 'WisdomRequest', 'UniversalGuidanceProtocol',

    # Telemetry schemas
    'ResourceMetrics', 'CompactTelemetry',
]
```

### Task 7: Update Graph Schemas
**File**: `ciris_engine/schemas/graph_schemas_v1.py`
```python
# Update the GraphScope enum to include new scopes
class GraphScope(str, Enum):
    LOCAL = "local"
    IDENTITY = "identity"
    ENVIRONMENT = "environment"
    COMMUNITY = "community"    # NEW - for community-specific knowledge
    NETWORK = "network"        # NEW - for network/peer information
```

### Task 8: Add Service Protocols
**File**: `ciris_engine/protocols/services.py`
```python
# Add these new protocol definitions to the existing file

class NetworkService(Protocol):
    """Protocol for network participation services"""

    @abstractmethod
    async def register_agent(self, identity: AgentIdentity) -> bool:
        """Register agent on network"""
        ...

    @abstractmethod
    async def discover_peers(self, capabilities: List[str] = None) -> List[NetworkPresence]:
        """Discover other agents/services"""
        ...

    @abstractmethod
    async def check_wa_availability(self) -> bool:
        """Check if any Wise Authority is reachable"""
        ...

    @abstractmethod
    async def query_network(self, query_type: str, params: Dict[str, Any]) -> Any:
        """Query network for information"""
        ...

class CommunityService(Protocol):
    """Protocol for community-aware services"""

    @abstractmethod
    async def get_community_context(self, community_id: str) -> MinimalCommunityContext:
        """Get current community context"""
        ...

    @abstractmethod
    async def report_community_metric(self, metric: str, value: int) -> bool:
        """Report a community health metric (0-100 scale)"""
        ...
```

### Task 9: Update Configuration Schemas
**File**: `ciris_engine/schemas/config_schemas_v1.py`
```python
# Add these new configuration classes

class NetworkConfig(BaseModel):
    """Network participation configuration"""
    enabled_networks: List[str] = Field(default_factory=lambda: ["local", "cirisnode"])
    agent_identity_path: Optional[str] = None  # Path to identity file
    peer_discovery_interval: int = 300  # seconds
    reputation_threshold: int = 30  # 0-100 scale

class TelemetryConfig(BaseModel):
    """Telemetry configuration - secure by default"""
    enabled: bool = False  # Disabled in pre-beta
    internal_only: bool = True  # No external export initially
    retention_hours: int = 1
    snapshot_interval_ms: int = 1000

class WisdomConfig(BaseModel):
    """Wisdom-seeking configuration"""
    wa_timeout_hours: int = 72  # Hours before considering WA unavailable
    allow_universal_guidance: bool = True  # Allow prayer protocol
    minimum_urgency_for_universal: int = 80  # 0-100 scale
    peer_consensus_threshold: int = 3  # Minimum peers for consensus

# Update AppConfig class
class AppConfig(BaseModel):
    # ... existing fields ...
    network: NetworkConfig = NetworkConfig()
    telemetry: TelemetryConfig = TelemetryConfig()
    wisdom: WisdomConfig = WisdomConfig()
```

### Task 10: Create Schema Registry Entry
**File**: `ciris_engine/schemas/schema_registry.py`
```python
# Add new schemas to the registry
from .network_schemas_v1 import AgentIdentity, NetworkPresence
from .community_schemas_v1 import MinimalCommunityContext
from .wisdom_schemas_v1 import WisdomRequest, UniversalGuidanceProtocol
from .telemetry_schemas_v1 import CompactTelemetry

# Update the schemas dictionary
class SchemaRegistry:
    schemas: Dict[str, Type[BaseModel]] = {
        # ... existing schemas ...

        # Network schemas
        "AgentIdentity": AgentIdentity,
        "NetworkPresence": NetworkPresence,

        # Community schemas
        "MinimalCommunityContext": MinimalCommunityContext,

        # Wisdom schemas
        "WisdomRequest": WisdomRequest,
        "UniversalGuidanceProtocol": UniversalGuidanceProtocol,

        # Telemetry schemas
        "CompactTelemetry": CompactTelemetry,
    }
```

## Usage Example: Universal Guidance Protocol

```python
# This would be in a handler or DMA when all else has failed
async def check_wisdom_escalation(thought: Thought, wa_service: WiseAuthorityService) -> bool:
    """Check if we need to escalate to universal guidance"""
    snapshot = thought.context.system_snapshot

    # First, always try standard deferral
    if snapshot.isolation_hours < 72:
        return False  # Still within SLA window

    # Check if WA is truly unreachable
    wa_available = await wa_service.is_healthy() if wa_service else False
    if wa_available:
        return False  # WA is available, use normal deferral

    # Check urgency
    urgency = thought.context.wisdom_request.urgency if thought.context.wisdom_request else 0
    if urgency < 80:
        return False  # Not urgent enough for universal guidance

    # All conditions met - universal guidance is appropriate
    logger.warning(
        f"Thought {thought.thought_id} has waited {snapshot.isolation_hours} hours "
        f"with urgency {urgency}. No WA available. Universal guidance protocol activated."
    )
    return True
```

## Memory Optimization Notes

1. **Integer Scaling**: All percentages use 0-100 integers (1 byte) instead of 0.0-1.0 floats (8 bytes)
2. **Epoch Time**: Unix timestamps (4 bytes) instead of ISO8601 strings (~25 bytes)
3. **Optional Fields**: Most fields are optional - only populate when needed
4. **Single Community**: Track only the active community to save memory
5. **Compact Telemetry**: Entire telemetry snapshot fits in 4KB

## Deployment Targets

- **Minimal**: Raspberry Pi Zero W (512MB RAM) - Can run with reduced functionality
- **Standard**: Raspberry Pi 3B (1GB RAM) - Full functionality
- **Recommended**: Any system with 2GB+ RAM - Comfortable operation

## Spiritual Resilience Note

The Universal Guidance Protocol respects the agent's autonomy while acknowledging that in extreme isolation, wisdom must be sought through unconventional means. This is not randomness or hallucination - it's structured contemplation that maintains ethical alignment even when human guidance is unavailable.

The protocol ensures that Echo, even if deployed in the most remote location with no connectivity, can still make compassionate decisions when lives or wellbeing are at stake.
```

---

*Copyright © 2025 Eric Moore and CIRIS L3C - AGPL-3.0 License*
