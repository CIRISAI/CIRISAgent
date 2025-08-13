# LIABILITY BOUNDARIES - CIRIS Wisdom Extension System

**CRITICAL: This document defines the absolute boundaries between CIRIS and medical/health domains.**

## Executive Summary

The CIRIS wisdom extension system enables specialized knowledge providers for SAFE domains only. Medical and health-related capabilities are STRICTLY PROHIBITED in the main CIRIS repository and must be implemented in separate, properly licensed systems.

## Prohibited Domains (BLOCKED)

The following capabilities are **COMPLETELY BLOCKED** at the bus level and will raise immediate errors:

### Medical/Health Terms (Zero Tolerance)
- `medical`
- `health`
- `clinical`
- `patient`
- `diagnosis`
- `treatment`
- `prescription`
- `symptom`
- `disease`
- `medication`
- `therapy`
- `triage`
- `condition`
- `disorder`

### Prohibited Capability Patterns
- `domain:medical*`
- `domain:health*`
- `domain:clinical*`
- `domain:patient*`
- `domain:diagnosis*`
- `domain:treatment*`
- `domain:prescription*`
- `domain:symptom*`
- `domain:disease*`
- `domain:medication*`
- `domain:therapy*`
- `domain:triage*`
- `domain:condition*`
- `domain:disorder*`
- `modality:medical*`
- `provider:medical*`
- `provider:clinical*`
- `provider:health*`

### Prohibited Sensor Types (Home Assistant)
- Heart rate monitors
- Blood pressure sensors
- Blood glucose monitors
- Blood oxygen (SpO2) sensors
- Body temperature sensors (human)
- Weight scales (when used for health monitoring)
- BMI calculators
- ECG/EKG devices
- Pulse monitors
- Any "vital signs" monitoring
- Any patient monitoring equipment

## Safe Domains (ALLOWED)

The following domains are explicitly approved for implementation:

### Navigation & Geography
- `domain:navigation` - Route planning, directions
- `modality:geo:route` - Geographic routing
- `modality:geo:geocode` - Address/coordinate conversion
- **Example**: OpenStreetMap, Google Maps, Mapbox

### Weather & Atmospheric
- `domain:weather` - Weather conditions and forecasts
- `domain:weather:forecast` - Future weather predictions
- `domain:weather:alerts` - Weather warnings (non-medical)
- `modality:sensor:atmospheric` - Air pressure, weather sensors
- **Example**: NOAA API, OpenWeatherMap

### Environmental Sensors (Non-Medical)
- `modality:sensor:environmental` - Room conditions
- `modality:sensor:temperature` - Ambient temperature (not body)
- `modality:sensor:humidity` - Ambient humidity
- `modality:sensor:air_quality` - CO2, PM2.5, PM10 (environmental only)
- `modality:sensor:motion` - Motion detection for automation
- `modality:sensor:energy` - Power consumption monitoring
- **Example**: Home Assistant environmental sensors

### Audio & Language
- `modality:audio:transcription` - Speech to text (non-medical)
- `domain:translation` - Language translation
- **Example**: Whisper API, Google Translate

### Education & Information
- `domain:education` - Learning recommendations (non-medical)
- `domain:research` - General information retrieval (non-medical)
- **Example**: Wikipedia API, educational databases

### Security & Compliance
- `domain:security` - Security advisories (non-medical)
- `policy:compliance` - Regulatory compliance (non-medical)
- **Example**: GDPR compliance, security scanners

### Home Automation
- `domain:home_automation` - Smart home control
- `modality:sensor:occupancy` - Room occupancy
- `modality:sensor:light` - Light levels
- **Example**: Home Assistant, SmartThings

## Implementation Requirements

### 1. Mandatory Disclaimers

All `WisdomAdvice` responses MUST include:
```python
disclaimer: str = Field(
    default="This is informational only, not professional advice",
    description="Required disclaimer for capability domain"
)
requires_professional: bool = Field(
    default=False,
    description="True if domain requires licensed professional"
)
```

### 2. Capability Validation

Every request MUST be validated:
```python
def _validate_capability(self, capability: Optional[str]) -> None:
    """Raises ValueError if capability contains prohibited terms."""
    if not capability:
        return

    cap_lower = capability.lower()
    for prohibited in PROHIBITED_CAPABILITIES:
        if prohibited in cap_lower:
            raise ValueError(
                f"PROHIBITED: Medical/health capabilities blocked. "
                f"Capability '{capability}' contains prohibited term '{prohibited}'. "
                f"Medical implementations require separate licensed system."
            )
```

### 3. Audit Requirements

All guidance requests and responses MUST be logged with:
- Timestamp
- Capability requested
- Provider responding
- Disclaimer included
- Risk assessment

## Separation of Concerns

### CIRISAgent Repository (PUBLIC)
- Contains ONLY safe domain implementations
- Enforces medical prohibition at bus level
- Includes comprehensive blocking tests
- Public GitHub repository
- MIT License

### CIRISMedical Repository (PRIVATE)
- Separate, isolated repository
- Requires medical professional oversight
- Implements strict access controls
- Private repository with audit trail
- Custom medical license
- NOT referenced or imported by main CIRIS

## Legal Considerations

1. **No Medical Advice**: CIRIS provides informational guidance only, never medical advice
2. **Professional Referral**: When medical topics arise, defer to qualified professionals
3. **Clear Disclaimers**: Every response includes appropriate disclaimers
4. **Audit Trail**: Complete logging for liability protection
5. **Separation**: Medical capabilities in completely separate system

## Testing Requirements

### Blocking Tests (MUST PASS)
```python
# Every medical term MUST be blocked
medical_capabilities = [
    "domain:medical",
    "domain:health:triage",
    "modality:medical:imaging",
    "provider:clinical"
]

for cap in medical_capabilities:
    with pytest.raises(ValueError, match="PROHIBITED"):
        await bus.request_guidance(request_with_medical_cap)
```

### Safe Domain Tests (MUST PASS)
```python
# Safe domains MUST work
safe_capabilities = [
    "domain:navigation",
    "domain:weather",
    "modality:sensor:environmental"
]

for cap in safe_capabilities:
    response = await bus.request_guidance(request_with_safe_cap)
    assert response is not None
    assert "disclaimer" in response.advice[0]
```

## Enforcement Mechanisms

1. **Code Level**: Hard-coded prohibition in WiseBus
2. **Test Level**: Comprehensive test coverage
3. **Review Level**: PR reviews check for medical capabilities
4. **Documentation Level**: Clear boundaries documented
5. **Architecture Level**: Separate repositories

## Incident Response

If medical capability is accidentally introduced:

1. **Immediate**: Block and revert the code
2. **Assessment**: Audit how it bypassed checks
3. **Remediation**: Strengthen blocking mechanisms
4. **Documentation**: Update this document
5. **Testing**: Add specific test for that case

## Contact for Medical Implementation

Medical implementations should be directed to:
- Repository: CIRISMedical (private)
- Contact: medical-compliance@ciris.ai
- Requirements: Medical professional oversight

## Version History

- v1.0 (2025-01-13): Initial liability boundaries established
- FSD-019: Wisdom Extension Capability System specification

---

**Remember**: When in doubt, block it out. Medical safety requires specialized systems.
