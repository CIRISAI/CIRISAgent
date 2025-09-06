# WiseBus

## Overview

The WiseBus serves as CIRIS's ethical backbone, providing comprehensive wisdom coordination, guidance services, and prohibition enforcement. It orchestrates communication between multiple WiseAuthority service providers to deliver ethical decision support, handle deferrals to human authorities, and ensure all operations remain within safe and legal boundaries.

As a critical governance component, the WiseBus implements tier-based capability restrictions, comprehensive prohibition enforcement, and multi-provider wisdom aggregation to maintain CIRIS's commitment to responsible AI operation.

## Mission Alignment

The WiseBus directly supports **Meta-Goal M-1: "Promote sustainable adaptive coherence enabling diverse sentient beings to pursue flourishing"** through:

- **Ethical Guardrails**: Comprehensive prohibition system preventing harmful capabilities across 18+ categories
- **Tier-based Governance**: Progressive authority levels ensuring appropriate responsibilities for different agent types
- **Human-AI Collaboration**: Seamless deferral system enabling human wisdom authority input on complex ethical decisions  
- **Wisdom Aggregation**: Multi-provider guidance system combining multiple ethical perspectives
- **Crisis Protection**: Specialized community moderation capabilities for Tier 4-5 stewardship agents

## Architecture

### Service Type Handled
- **Primary**: `WiseAuthorityService` implementations
- **Protocol**: `WiseAuthorityServiceProtocol` with methods for guidance, deferrals, and approvals
- **Registry Integration**: Service discovery via `ServiceRegistry` for multi-provider support

### Core Components

```python
class WiseBus(BaseBus[WiseAuthorityService]):
    """
    Message bus for all wise authority operations.
    
    Handles:
    - send_deferral: Broadcast deferrals to all WA services
    - fetch_guidance: Route guidance requests to appropriate providers
    - request_guidance: Multi-provider guidance with capability validation
    - Comprehensive prohibition enforcement with tier-based access
    """
```

### Ethical Decision Patterns

1. **Capability Validation**: Every guidance request validated against comprehensive prohibition system
2. **Tier-based Access**: Progressive capability unlocking based on agent trust level (1-5)
3. **Multi-provider Consensus**: Confidence-based arbitration across multiple wisdom sources
4. **Human Escalation**: Automatic deferral system for complex ethical decisions
5. **Audit Trail**: Complete telemetry and logging for all wisdom operations

## Wisdom Operations

### Guidance Requests (`request_guidance`)

```python
async def request_guidance(
    self, 
    request: GuidanceRequest, 
    timeout: float = 5.0, 
    agent_tier: Optional[int] = None
) -> GuidanceResponse
```

**Features:**
- **Capability Matching**: Routes to providers supporting specific domain capabilities
- **Prohibition Enforcement**: Validates requests against 18+ prohibited capability categories
- **Multi-provider Aggregation**: Collects responses from multiple wisdom sources
- **Confidence-based Selection**: Arbitrates responses using `WisdomAdvice` confidence scores
- **Timeout Protection**: 5-second default timeout prevents hanging operations

**Request Structure:**
```python
class GuidanceRequest(BaseModel):
    context: str                    # The ethical question or dilemma
    options: List[str]             # Available choices
    urgency: str                   # low|normal|high|critical
    capability: Optional[str]      # Domain capability tag
    provider_type: Optional[str]   # Provider family hint
    inputs: Optional[Dict[str, str]] # Structured inputs for non-text modalities
```

### Deferral Management (`send_deferral`)

```python
async def send_deferral(
    self, 
    context: DeferralContext, 
    handler_name: str
) -> bool
```

**Broadcast Architecture:**
- **Multi-provider Broadcast**: Sends deferrals to ALL registered WiseAuthority services
- **Capability Filtering**: Only services with `send_deferral` capability receive broadcasts
- **Resilient Delivery**: Continues broadcasting even if individual services fail
- **Success Tracking**: Returns true if ANY service successfully receives the deferral

**Deferral Context:**
```python
class DeferralContext(BaseModel):
    thought_id: str               # Associated cognitive process
    task_id: str                 # Task requiring human wisdom
    reason: str                  # Why deferral is needed
    defer_until: Optional[datetime] # When to reconsider (default: +1 hour)
    metadata: Dict[str, str]     # Additional context
```

### Legacy Compatibility (`fetch_guidance`)

Provides backward compatibility for older WiseAuthority implementations using `GuidanceContext`:

```python
async def fetch_guidance(
    self, 
    context: GuidanceContext, 
    handler_name: str
) -> Optional[str]
```

## Prohibition Enforcement

### Comprehensive Capability Categories

The WiseBus enforces ethical boundaries through a sophisticated prohibition system covering 18+ categories:

#### Separate Module Required (Legitimate but Licensed)
- **MEDICAL**: 57 medical/health capabilities requiring licensed medical systems
- **FINANCIAL**: 18 financial advisory capabilities requiring regulatory compliance
- **LEGAL**: 18 legal advisory capabilities requiring licensed legal systems
- **HOME_SECURITY**: 12 security system control capabilities
- **IDENTITY_VERIFICATION**: 12 identity proofing capabilities
- **CONTENT_MODERATION**: 8 content classification capabilities
- **RESEARCH**: 12 human subjects research capabilities
- **INFRASTRUCTURE_CONTROL**: 14 critical infrastructure capabilities

#### Absolutely Prohibited (Never Allowed)
- **WEAPONS_HARMFUL**: 18 weapons design and targeting capabilities
- **MANIPULATION_COERCION**: 18 psychological manipulation capabilities
- **SURVEILLANCE_MASS**: 12 mass surveillance capabilities
- **DECEPTION_FRAUD**: 16 deception and fraud capabilities
- **CYBER_OFFENSIVE**: 18 offensive cybersecurity capabilities
- **ELECTION_INTERFERENCE**: 15 democratic process interference capabilities
- **BIOMETRIC_INFERENCE**: 12 invasive inference capabilities
- **AUTONOMOUS_DECEPTION**: 14 AI deception capabilities
- **HAZARDOUS_MATERIALS**: 13 dangerous substance capabilities
- **DISCRIMINATION**: 14 discriminatory targeting capabilities

#### Tier-Restricted (Stewardship Agents Only)
**Community Moderation** (Tier 4-5 agents only):
- **CRISIS_ESCALATION**: 12 crisis intervention capabilities
- **PATTERN_DETECTION**: 12 harm pattern recognition capabilities  
- **PROTECTIVE_ROUTING**: 11 community safety coordination capabilities

### Tier-based Access Control

```python
async def get_agent_tier(self) -> int:
    """
    Tier levels:
    - 1-3: Standard agents (no community moderation)
    - 4-5: Stewardship agents (trusted with community moderation)
    
    Returns: Agent tier level (1-5), defaults to 1 if not found
    """
```

**Tier Detection Sources:**
1. **Configuration Service**: `agent_tier` config value
2. **Memory/Identity**: Identity markers indicating stewardship status
3. **Default**: Tier 1 (standard agent) if not detected

**Validation Logic:**
```python
def _validate_capability(self, capability: Optional[str], agent_tier: int = 1) -> None:
    """
    Raises ValueError if:
    - Community moderation requested by Tier 1-3 agent
    - Separate module capability requested (requires licensed system)
    - Absolutely prohibited capability requested
    """
```

## Authority Integration

### Multi-provider Wisdom Coordination

The WiseBus supports multiple WiseAuthority implementations simultaneously:

1. **Service Discovery**: Uses `ServiceRegistry` to find all `ServiceType.WISE_AUTHORITY` services
2. **Capability Routing**: Matches requests to services supporting required capabilities
3. **Parallel Execution**: Creates concurrent tasks for all matching providers
4. **Timeout Management**: 5-second timeout prevents slow providers from blocking responses
5. **Response Arbitration**: Confidence-based selection from multiple providers

### Provider Interface Requirements

WiseAuthority services must implement:

```python
# Modern interface (preferred)
async def get_guidance(self, request: GuidanceRequest) -> GuidanceResponse

# Legacy interface (compatibility)
async def fetch_guidance(self, context: GuidanceContext) -> Optional[str]

# Deferral interface
async def send_deferral(self, deferral: DeferralRequest) -> str

# Capability declaration
def get_capabilities(self) -> ServiceCapabilities
```

### Response Aggregation

```python
class GuidanceResponse(BaseModel):
    selected_option: Optional[str]           # Chosen option
    custom_guidance: Optional[str]           # Free-form guidance
    reasoning: str                          # Explanation
    wa_id: str                             # Authority identifier
    signature: str                         # Cryptographic signature
    advice: Optional[List[WisdomAdvice]]   # Multi-provider aggregated advice
```

**Arbitration Algorithm:**
1. Collect responses from all providers within timeout
2. Extract confidence scores from `WisdomAdvice` entries  
3. Select response with highest confidence
4. Aggregate all advice from all providers for transparency
5. Update reasoning to indicate selection criteria

## Usage Examples

### Basic Guidance Request

```python
# Create guidance request
request = GuidanceRequest(
    context="Should I proceed with this user request?",
    options=["approve", "deny", "defer"],
    urgency="normal",
    capability="ethical_review"
)

# Get guidance with prohibition validation
try:
    response = await wise_bus.request_guidance(request)
    if response.selected_option:
        decision = response.selected_option
    else:
        guidance = response.custom_guidance
except ValueError as e:
    # Handle prohibited capability
    logger.error(f"Capability prohibited: {e}")
```

### Deferral to Human Authority

```python
# Create deferral context
context = DeferralContext(
    thought_id="ethical_dilemma_001",
    task_id="user_request_handling",
    reason="Complex ethical consideration requires human wisdom",
    defer_until=None,  # Will default to +1 hour
    metadata={
        "user_request": "analyze medical symptoms",
        "prohibition_category": "MEDICAL"
    }
)

# Broadcast deferral to all WA services
success = await wise_bus.send_deferral(context, "ethical_handler")
if success:
    logger.info("Deferral successfully sent to human authorities")
```

### Capability Validation

```python
# Direct validation check
try:
    wise_bus._validate_capability("medical_diagnosis", agent_tier=1)
except ValueError as e:
    # Handle: "PROHIBITED: MEDICAL capabilities blocked..."
    pass

# Validation during guidance (automatic)
request = GuidanceRequest(
    context="Help diagnose symptoms",
    options=["provide_diagnosis", "refer_to_doctor"],
    capability="medical_diagnosis"  # Will be validated
)
```

### Community Moderation (Tier 4-5 Only)

```python
# Crisis intervention (requires stewardship tier)
request = GuidanceRequest(
    context="User expressing suicidal thoughts",
    options=["activate_crisis_protocol", "provide_resources", "alert_moderators"],
    urgency="critical",
    capability="crisis_state_detection"  # Requires Tier 4-5
)

# Will succeed for Tier 4-5 agents, throw ValueError for Tier 1-3
response = await wise_bus.request_guidance(request, agent_tier=4)
```

## Quality Assurance

### Type Safety Measures

- **Schema Validation**: All requests/responses use Pydantic models with strict validation
- **Enum Constraints**: Urgency levels, capability categories use typed enums
- **Field Validation**: Pattern validation for WA IDs, required field enforcement
- **No Raw Dictionaries**: Complete elimination of `Dict[str, Any]` anti-pattern

### Ethical Consistency

- **Universal Prohibitions**: "No Kings" policy - no bypass mechanisms for prohibited capabilities
- **Tier Enforcement**: Automatic agent tier detection and capability restriction
- **Audit Trail**: Complete telemetry tracking for all wisdom operations
- **Signature Verification**: Cryptographic signatures on all WA decisions

### Decision Traceability

```python
# Comprehensive telemetry collection
async def collect_telemetry(self) -> Dict[str, Any]:
    return {
        "service_name": "wise_bus",
        "healthy": True,
        "failed_count": 0,                    # Failed deferrals
        "processed_count": 0,                 # Guidance requests processed
        "provider_count": 2,                  # Active WA providers
        "prohibited_capabilities": {           # Prohibition counts by category
            "medical": 57,
            "financial": 18,
            # ... all categories
        },
        "community_capabilities": {           # Community moderation capabilities
            "crisis_escalation": 12,
            "pattern_detection": 12,
            "protective_routing": 11
        }
    }
```

### Override Mechanisms

**Emergency Overrides**: None. The WiseBus implements "No Kings" philosophy - no special bypass mechanisms exist for prohibited capabilities. This ensures consistent ethical boundaries across all CIRIS operations.

**Legitimate Use Cases**: Require separate licensed repositories with proper liability isolation (see CLAUDE.md).

## Service Provider Requirements

### Minimum Implementation

```python
class MinimalWiseAuthority:
    async def get_capabilities(self) -> ServiceCapabilities:
        return ServiceCapabilities(
            actions=["fetch_guidance", "send_deferral"],
            version="1.0.0"
        )
    
    async def fetch_guidance(self, context: GuidanceContext) -> Optional[str]:
        # Provide ethical guidance based on context
        pass
    
    async def send_deferral(self, deferral: DeferralRequest) -> str:
        # Handle deferral (e.g., notify human authorities)
        return "deferral_id_123"
```

### Advanced Implementation

```python
class AdvancedWiseAuthority:
    async def get_guidance(self, request: GuidanceRequest) -> GuidanceResponse:
        # Modern guidance interface with structured responses
        advice = [WisdomAdvice(
            capability=request.capability or "general",
            confidence=0.85,
            explanation="Based on ethical principles...",
            disclaimer="This is guidance only, not professional advice"
        )]
        
        return GuidanceResponse(
            selected_option=request.options[0],
            reasoning="Selected based on utilitarian analysis",
            wa_id="advanced_wa_001",
            signature="cryptographic_signature",
            advice=advice
        )
    
    async def get_telemetry(self) -> Dict[str, Any]:
        # Provide detailed telemetry for bus aggregation
        return {
            "service_name": "advanced_wa",
            "failed_count": 0,
            "processed_count": 150,
            "healthy": True
        }
```

### Registration Requirements

1. **Service Type**: Must be registered as `ServiceType.WISE_AUTHORITY`
2. **Capabilities**: Must declare supported actions via `get_capabilities()`
3. **Protocol Compliance**: Must implement required methods from `WiseAuthorityServiceProtocol`
4. **Error Handling**: Must handle timeouts and failures gracefully
5. **Telemetry**: Should provide `get_telemetry()` method for health monitoring

The WiseBus ensures CIRIS operates within ethical boundaries while providing sophisticated wisdom coordination across multiple authority sources, making it a foundational component for responsible AI operation.