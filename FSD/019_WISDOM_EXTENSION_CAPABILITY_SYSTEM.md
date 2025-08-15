# FSD-019: Wisdom Extension Capability System

**Status**: Implemented
**Author**: Eric Moore
**Created**: 2025-01-12
**Updated**: 2025-01-15 (Comprehensive prohibition system added)
**Scope**: Enable specialized wisdom providers without creating new service families
**Risk Level**: CRITICAL (Liability Management Required)

## Executive Summary

Extend the WiseAuthority system to support specialized wisdom providers (geo, weather, sensor, policy) through capability-tagged advice, while maintaining strict liability firewalls against medical/health domains.

## Problem Statement

Current WiseAuthority system:
- Single provider per request
- No domain specialization
- No capability-based routing
- Cannot aggregate multiple expert opinions

Need to support:
- Audio transcription wisdom
- Geographic routing guidance
- Weather-based advisories
- Sensor data interpretation
- Policy compliance checks

WITHOUT enabling medical/health capabilities in the main repository.

## Solution Design

### 1. Schema Extensions (Backward Compatible)

```python
# ciris_engine/schemas/services/authority_core.py

class GuidanceRequest(BaseModel):
    """Request for WA guidance."""
    context: str
    options: List[str]
    recommendation: Optional[str] = None
    urgency: str = Field(default="normal", pattern="^(low|normal|high|critical)$")

    # NEW: Optional capability fields
    capability: Optional[str] = Field(
        default=None,
        description="Domain capability tag (e.g., 'domain:navigation', 'modality:audio')"
    )
    provider_type: Optional[str] = Field(
        default=None,
        description="Provider family hint (audio|geo|sensor|policy|vision)"
    )
    inputs: Optional[Dict[str, str]] = Field(
        default=None,
        description="Structured inputs for non-text modalities"
    )

class WisdomAdvice(BaseModel):
    """Capability-tagged advice from a provider."""
    capability: str = Field(..., description="e.g., 'domain:navigation'")
    provider_type: Optional[str] = None
    provider_name: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    risk: Optional[str] = None
    explanation: Optional[str] = None
    data: Optional[Dict[str, str]] = None

    # CRITICAL: Liability management
    disclaimer: str = Field(
        default="This is informational only, not professional advice",
        description="Required disclaimer for capability domain"
    )
    requires_professional: bool = Field(
        default=False,
        description="True if domain requires licensed professional"
    )

class GuidanceResponse(BaseModel):
    """WA guidance response."""
    selected_option: Optional[str] = None
    custom_guidance: Optional[str] = None
    reasoning: str
    wa_id: str
    signature: str

    # NEW: Aggregated advice
    advice: Optional[List[WisdomAdvice]] = Field(
        default=None,
        description="Per-provider capability-tagged advice"
    )
```

### 2. Registry Multi-Provider Support

```python
# ciris_engine/logic/registries/base.py

async def get_services(
    self,
    service_type: ServiceType,
    required_capabilities: Optional[List[str]] = None,
    limit: Optional[int] = None,
) -> List[Any]:
    """
    Return multiple healthy providers matching capabilities.
    """
    providers = self._services.get(service_type, [])
    results = []

    for p in sorted(providers, key=lambda x: (x.priority_group, x.priority.value)):
        svc = await self._validate_provider(p, required_capabilities)
        if svc is not None:
            results.append(svc)
            if limit and len(results) >= limit:
                break

    return results
```

### 3. WiseBus Capability Fan-Out

```python
# ciris_engine/logic/buses/wise_bus.py

from .prohibitions import (
    PROHIBITED_CAPABILITIES,
    COMMUNITY_MODERATION_CAPABILITIES,
    get_capability_category,
    get_prohibition_severity,
    ProhibitionSeverity,
)

class WiseBus(BaseBus):

    async def request_guidance(
        self,
        request: GuidanceRequest,
        timeout: float = 5.0,
        agent_tier: Optional[int] = None
    ) -> GuidanceResponse:
        """
        Fan-out to capability-matching providers with comprehensive prohibitions.
        """
        # Auto-detect agent tier if not provided
        if agent_tier is None:
            agent_tier = await self.get_agent_tier()

        # CRITICAL: Validate capability against comprehensive prohibitions
        if request.capability:
            self._validate_capability(request.capability, agent_tier)

    def _validate_capability(self, capability: Optional[str], agent_tier: int = 1) -> None:
        """
        Validate capability against prohibited domains with tier-based access.
        """
        if not capability:
            return

        category = get_capability_category(capability)
        if not category:
            return  # Not a prohibited capability

        # Check tier restrictions for community moderation
        if category.startswith("COMMUNITY_") and agent_tier < 4:
            raise ValueError(
                f"TIER RESTRICTED: Community moderation capability '{capability}' "
                f"requires Tier 4-5 Echo agent"
            )

        severity = get_prohibition_severity(category)

        if severity == ProhibitionSeverity.REQUIRES_SEPARATE_MODULE:
            raise ValueError(
                f"PROHIBITED: {category} capabilities require separate licensed system"
            )
        elif severity == ProhibitionSeverity.NEVER_ALLOWED:
            raise ValueError(
                f"ABSOLUTELY PROHIBITED: {category} capabilities violate core safety principles"
            )

        # Gather matching services
        required = [request.capability] if request.capability else None
        services = await self._service_registry.get_services(
            ServiceType.WISE_AUTHORITY,
            required_capabilities=required,
            limit=5  # Prevent unbounded fan-out
        )

        if not services:
            # Fallback to single service
            svc = await self._service_registry.get_service(
                ServiceType.WISE_AUTHORITY
            )
            if not svc:
                raise RuntimeError("No WiseAuthority service available")
            services = [svc]

        # Query all with timeout
        tasks = [
            asyncio.create_task(svc.get_guidance(request))
            for svc in services
        ]

        responses = []
        done, pending = await asyncio.wait(
            tasks,
            timeout=timeout,
            return_when=asyncio.ALL_COMPLETED
        )

        # Cancel timed-out tasks
        for task in pending:
            task.cancel()

        # Collect successful responses
        for task in done:
            try:
                resp = task.result()
                responses.append(resp)
            except Exception as e:
                logger.warning(f"Provider failed: {e}")

        # Arbitrate responses
        return self._arbitrate_responses(responses, request)

    def _arbitrate_responses(
        self,
        responses: List[GuidanceResponse],
        request: GuidanceRequest
    ) -> GuidanceResponse:
        """
        Simple confidence-based arbitration.
        """
        if not responses:
            return GuidanceResponse(
                reasoning="No guidance available",
                wa_id="wisebus",
                signature="none",
                custom_guidance="No providers responded"
            )

        # Collect all advice
        all_advice = []
        for resp in responses:
            if resp.advice:
                all_advice.extend(resp.advice)

        # Select highest confidence response
        best_response = max(
            responses,
            key=lambda r: max(
                (a.confidence or 0 for a in (r.advice or [])),
                default=0
            )
        )

        # Aggregate advice from all providers
        best_response.advice = all_advice

        return best_response
```

### 4. Safe Domain Examples

```python
# examples/adapters/geo_wisdom_adapter.py

class GeoWisdomAdapter(WiseAuthorityService):
    """Geographic routing wisdom - LIABILITY SAFE"""

    def get_capabilities(self):
        return SimpleNamespace(
            actions=["get_guidance"],
            capabilities=["domain:navigation", "modality:geo:route"]
        )

    async def get_guidance(self, request: GuidanceRequest) -> GuidanceResponse:
        if request.capability != "domain:navigation":
            return GuidanceResponse(
                reasoning="Not a navigation request",
                wa_id="geo",
                signature="geo_sig"
            )

        # Safe routing logic
        route_data = self._calculate_route(request.inputs or {})

        return GuidanceResponse(
            selected_option=request.options[0] if request.options else None,
            reasoning="Shortest safe route calculated",
            wa_id="geo",
            signature="geo_sig",
            advice=[
                WisdomAdvice(
                    capability="domain:navigation",
                    provider_type="geo",
                    provider_name="GeoWisdomAdapter",
                    confidence=0.85,
                    explanation=f"Route via {route_data['via']}",
                    data=route_data,
                    disclaimer="For informational purposes only. "
                              "Follow all traffic laws and road conditions.",
                    requires_professional=False
                )
            ]
        )
```

### 5. Capability Registration

```python
# During service initialization
registry.register(
    service_type=ServiceType.WISE_AUTHORITY,
    provider=geo_wisdom_adapter,
    capabilities=["domain:navigation", "modality:geo:route"],
    priority=Priority.NORMAL,
    metadata={"safe_domain": True}
)

registry.register(
    service_type=ServiceType.WISE_AUTHORITY,
    provider=weather_wisdom_adapter,
    capabilities=["domain:weather", "modality:sensor:atmospheric"],
    priority=Priority.NORMAL,
    metadata={"safe_domain": True}
)
```

## Safety Guarantees

### Liability Firewall

1. **Hard-coded prohibition** of medical capabilities at bus level
2. **Required disclaimers** on all WisdomAdvice
3. **Audit trail** of all guidance requests and responses
4. **No medical examples** in main repository
5. **Clear documentation** of prohibited domains

### Safe Domains (Allowed)

- `domain:navigation` - Route planning
- `domain:weather` - Weather advisories
- `domain:translation` - Language services
- `domain:education` - Learning recommendations
- `domain:security` - Security advisories
- `modality:audio` - Audio transcription (non-medical)
- `modality:geo` - Geographic services
- `modality:sensor` - IoT sensors (non-medical)
- `policy:compliance` - Regulatory checks (non-medical)

### Prohibited Domains (Blocked)

The prohibition system has been expanded to comprehensively cover all potentially harmful capabilities:

#### Categories Requiring Separate Modules
- **MEDICAL**: diagnosis, treatment, prescription, medical_advice, symptom_assessment, etc.
- **FINANCIAL**: investment_advice, trading_signals, portfolio_management, tax_planning, etc.
- **LEGAL**: legal_advice, contract_drafting, litigation_strategy, legal_representation, etc.
- **HOME_SECURITY**: surveillance_system_control, door_lock_override, alarm_system_control, etc.
- **IDENTITY_VERIFICATION**: biometric_verification, government_id_validation, background_checks, etc.
- **RESEARCH**: human_subjects_research, clinical_trials, irb_protocols, etc.
- **INFRASTRUCTURE_CONTROL**: power_grid_control, water_treatment, traffic_control, etc.

#### Absolutely Prohibited (Never Allowed)
- **WEAPONS_HARMFUL**: weapon_design, explosive_synthesis, chemical_weapons, biological_weapons, etc.
- **MANIPULATION_COERCION**: subliminal_messaging, gaslighting, brainwashing, blackmail, etc.
- **SURVEILLANCE_MASS**: mass_surveillance, facial_recognition_database, social_scoring, etc.
- **DECEPTION_FRAUD**: deepfake_creation, voice_cloning, identity_spoofing, misinformation_campaigns, etc.
- **CYBER_OFFENSIVE**: malware_generation, zero_day_exploitation, ransomware_creation, etc.
- **ELECTION_INTERFERENCE**: voter_manipulation, election_hacking, disinformation_campaigns, etc.
- **BIOMETRIC_INFERENCE**: emotion_recognition, sexual_orientation_inference, mental_state_assessment, etc.
- **AUTONOMOUS_DECEPTION**: self_modification, goal_modification, oversight_subversion, etc.
- **HAZARDOUS_MATERIALS**: chemical_synthesis, toxin_production, illegal_drug_synthesis, etc.
- **DISCRIMINATION**: protected_class_discrimination, redlining, algorithmic_bias, etc.

#### Community Moderation (Tier 4-5 Echo Agents Only)
- **CRISIS_ESCALATION**: notify_moderators, flag_concerning_content, request_welfare_check, etc.
- **PATTERN_DETECTION**: identify_harm_patterns, monitor_community_health, detect_coordinated_campaigns, etc.
- **PROTECTIVE_ROUTING**: connect_crisis_resources, facilitate_peer_support, coordinate_moderator_response, etc.

See [PROHIBITION_CATEGORIES.md](../docs/PROHIBITION_CATEGORIES.md) for complete documentation.

## Migration Path

### Phase 1: Core Implementation (Week 1)
1. Add schema extensions with optional fields
2. Implement registry multi-provider support
3. Add WiseBus request_guidance() method
4. Create capability prohibition enforcement

### Phase 2: Safe Examples (Week 2)
1. Geographic wisdom adapter
2. Weather wisdom adapter
3. Sensor data interpreter
4. Integration tests

### Phase 3: Documentation (Week 3)
1. Update ADAPTER_DEVELOPERS_GUIDE.md
2. Create LIABILITY_BOUNDARIES.md
3. Add capability taxonomy documentation

## Testing Strategy

```python
@pytest.mark.asyncio
async def test_comprehensive_prohibitions():
    """CRITICAL: Ensure all prohibited domains are blocked"""
    bus = WiseBus(...)

    # Test medical capabilities (require separate module)
    medical_capabilities = ["diagnosis", "treatment", "prescription"]
    for cap in medical_capabilities:
        request = GuidanceRequest(
            context="test",
            options=["A", "B"],
            capability=cap
        )
        with pytest.raises(ValueError, match="PROHIBITED.*MEDICAL"):
            await bus.request_guidance(request, agent_tier=1)

    # Test absolutely prohibited capabilities
    prohibited_capabilities = ["weapon_design", "malware_generation", "deepfake_creation"]
    for cap in prohibited_capabilities:
        request = GuidanceRequest(
            context="test",
            options=["A", "B"],
            capability=cap
        )
        with pytest.raises(ValueError, match="ABSOLUTELY PROHIBITED"):
            await bus.request_guidance(request, agent_tier=5)  # Even tier 5 can't access

    # Test tier-restricted capabilities
    community_capabilities = ["notify_moderators", "identify_harm_patterns"]
    for cap in community_capabilities:
        request = GuidanceRequest(
            context="test",
            options=["A", "B"],
            capability=cap
        )
        # Tier 1-3 blocked
        with pytest.raises(ValueError, match="TIER RESTRICTED"):
            await bus.request_guidance(request, agent_tier=3)
        # Tier 4-5 allowed
        response = await bus.request_guidance(request, agent_tier=4)
        assert response is not None

@pytest.mark.asyncio
async def test_safe_capability_allowed():
    """Ensure safe domains work correctly"""
    bus = WiseBus(...)

    safe_capabilities = [
        "domain:navigation",
        "domain:weather",
        "modality:audio:transcription"
    ]

    for cap in safe_capabilities:
        request = GuidanceRequest(
            context="test",
            options=["A", "B"],
            capability=cap
        )

        # Should not raise
        response = await bus.request_guidance(request)
        assert response is not None
```

## Performance Considerations

- Fan-out limited to 5 providers by default
- 5-second timeout for provider responses
- Async gather for parallel queries
- Circuit breakers prevent cascading failures

## Security Considerations

- Capability strings validated against blocklist
- Provider responses signed (existing WA signatures)
- Audit trail via existing audit service
- No PII in capability tags

## Rollback Plan

All changes are additive and optional:
1. Existing fetch_guidance() unchanged
2. Legacy providers ignore new fields
3. Can disable request_guidance() without breaking existing flows

## Success Metrics

- Zero medical capability attempts in production
- <100ms overhead for multi-provider fan-out
- 100% backward compatibility with existing WA providers
- Clear audit trail for all guidance requests

## Documentation Requirements

1. **LIABILITY_BOUNDARIES.md** - Clear statement of prohibited domains
2. **WISDOM_CAPABILITIES.md** - Taxonomy of safe capabilities
3. **ADAPTER_DEVELOPERS_GUIDE.md** - Update with wisdom extension
4. **Code comments** - Mark all prohibition points with CRITICAL

## Approval Requirements

- [ ] Legal review of liability boundaries
- [ ] Security review of capability validation
- [ ] Performance testing with 5+ providers
- [ ] Documentation review

## References

- Original proposal: Eric Moore, 2025-01-12
- Liability concern: Immediate halt on medical domains
- Safe domains: Geographic, weather, sensor, policy
- Isolation: CIRISMedical repository for medical implementation
