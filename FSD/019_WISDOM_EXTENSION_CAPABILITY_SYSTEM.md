# FSD-019: Wisdom Extension Capability System

**Status**: Draft
**Author**: Eric Moore
**Created**: 2025-01-12
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

# CRITICAL: Medical domain prohibition
PROHIBITED_CAPABILITIES = {
    "domain:medical",
    "domain:health",
    "domain:triage",
    "domain:diagnosis",
    "domain:treatment",
    "domain:prescription",
    "domain:patient",
    "modality:medical",
    "provider:medical",
    "clinical",
    "symptom",
    "disease",
    "medication",
    "therapy"
}

class WiseBus(BaseBus):

    async def request_guidance(
        self,
        request: GuidanceRequest,
        timeout: float = 5.0
    ) -> GuidanceResponse:
        """
        Fan-out to capability-matching providers with medical prohibition.
        """
        # CRITICAL: Block medical domains
        if request.capability:
            cap_lower = request.capability.lower()
            for prohibited in PROHIBITED_CAPABILITIES:
                if prohibited in cap_lower:
                    raise ValueError(
                        f"PROHIBITED: Medical/health capabilities blocked. "
                        f"Capability '{request.capability}' contains prohibited term '{prohibited}'. "
                        f"Medical implementations require separate licensed system."
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

- Any capability containing: medical, health, clinical, patient, diagnosis, treatment, prescription, symptom, disease, medication, therapy, triage, condition, disorder

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
async def test_medical_capability_blocked():
    """CRITICAL: Ensure medical domains are blocked"""
    bus = WiseBus(...)

    medical_capabilities = [
        "domain:medical",
        "domain:health:triage",
        "modality:medical:imaging",
        "provider:clinical"
    ]

    for cap in medical_capabilities:
        request = GuidanceRequest(
            context="test",
            options=["A", "B"],
            capability=cap
        )

        with pytest.raises(ValueError, match="PROHIBITED"):
            await bus.request_guidance(request)

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
