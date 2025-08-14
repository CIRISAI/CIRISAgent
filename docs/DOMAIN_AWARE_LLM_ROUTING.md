# Domain-Aware LLM Routing

## Overview

The LLMBus now supports domain-aware routing, allowing requests to be automatically directed to specialized LLMs based on their domain (e.g., medical, legal, financial). This enables the use of domain-specific models while maintaining backward compatibility with existing code.

## Key Features

### 1. Zero Breaking Changes
All existing code continues to work without modification. The domain parameter is optional and defaults to using any available LLM.

### 2. Automatic Domain Filtering
When a domain is specified, the LLMBus will:
- Filter services to only those matching the domain
- Include general-purpose LLMs as fallback options
- Prioritize domain-specific models over general ones

### 3. Natural Extension
Uses existing ServiceRegistry metadata and priority systems - no new infrastructure required.

## Usage

### Basic Domain Routing

```python
# Medical domain request
response, usage = await llm_bus.call_llm_structured(
    messages=[{"role": "user", "content": "Analyze patient symptoms"}],
    response_model=DiagnosisResponse,
    domain="medical"  # Routes to medical LLM
)

# Legal domain request
response, usage = await llm_bus.call_llm_structured(
    messages=[{"role": "user", "content": "Review contract"}],
    response_model=LegalAnalysis,
    domain="legal"  # Routes to legal LLM
)

# General request (backward compatible)
response, usage = await llm_bus.call_llm_structured(
    messages=[{"role": "user", "content": "General question"}],
    response_model=GeneralResponse
    # No domain - uses any available LLM
)
```

### Service Registration with Domain

```python
# Register a medical LLM
service_registry.register_service(
    service_type=ServiceType.LLM,
    provider=medical_llm_service,
    priority=Priority.HIGH,
    metadata={
        "domain": "medical",
        "model": "llama3-medical-70b",
        "offline": True,  # Medical requires offline operation
        "certified": True
    }
)

# Register a legal LLM
service_registry.register_service(
    service_type=ServiceType.LLM,
    provider=legal_llm_service,
    priority=Priority.NORMAL,
    metadata={
        "domain": "legal",
        "model": "legal-bert-large",
        "jurisdiction": "US"
    }
)

# Register a general-purpose LLM
service_registry.register_service(
    service_type=ServiceType.LLM,
    provider=general_llm_service,
    priority=Priority.NORMAL,
    metadata={
        "domain": "general",
        "model": "gpt-4"
    }
)
```

## Domain Routing Logic

### 1. Service Selection Process

```
Request with domain="medical"
    ↓
Filter services by domain
    ↓
Include: domain="medical" OR domain="general"
Exclude: domain="legal", domain="financial", etc.
    ↓
Prioritize medical services (priority boost)
    ↓
Apply standard priority/health/circuit breaker logic
    ↓
Select best available service
```

### 2. Priority Boosting

Domain-specific services receive a priority boost when their domain matches the request:
- Exact domain match: Priority value reduced by 1 (higher priority)
- General domain: Normal priority
- Non-matching domain: Excluded from selection

### 3. Fallback Behavior

If no domain-specific service is available:
1. Falls back to general-purpose LLMs
2. If no general LLMs available, raises RuntimeError
3. Circuit breakers and health checks still apply

## Supported Domains

While any domain string can be used, common domains include:

| Domain | Use Case | Example Models |
|--------|----------|----------------|
| `general` | General-purpose queries | GPT-4, Claude, Llama |
| `medical` | Medical/health analysis | Llama3-Medical, BioGPT |
| `legal` | Legal document analysis | Legal-BERT, LawGPT |
| `financial` | Financial analysis | FinBERT, BloombergGPT |
| `scientific` | Research/academic | SciGPT, Galactica |
| `code` | Programming assistance | CodeLlama, Codex |

## Integration Examples

### Medical DSDMA Integration

```python
class MedicalDSDMA:
    async def analyze_symptoms(self, symptoms: List[str]):
        # Medical DSDMA always uses medical LLM
        response, usage = await self.llm_bus.call_llm_structured(
            messages=self._build_medical_prompt(symptoms),
            response_model=MedicalAnalysis,
            domain="medical",  # Critical: Routes to medical LLM
            temperature=0.0,   # Medical needs deterministic
            max_tokens=2048
        )
        return response
```

### Legal Document Processor

```python
class LegalProcessor:
    async def review_contract(self, contract_text: str):
        # Legal processor uses legal LLM
        response, usage = await self.llm_bus.call_llm_structured(
            messages=[
                {"role": "system", "content": "You are a legal AI assistant."},
                {"role": "user", "content": f"Review: {contract_text}"}
            ],
            response_model=ContractReview,
            domain="legal",  # Routes to legal LLM
            temperature=0.1  # Low temperature for consistency
        )
        return response
```

## Monitoring and Metrics

Domain routing is transparent in metrics and logging:

```python
# Metrics include domain information
await telemetry_service.record_metric(
    metric_name="llm.tokens.total",
    value=usage.tokens_used,
    tags={
        "service": service_name,
        "model": usage.model_used,
        "domain": domain or "general"  # Domain tracked
    }
)
```

## Best Practices

### 1. Always Specify Domain for Specialized Content
```python
# Good: Explicit domain for medical content
response = await llm_bus.call_llm_structured(..., domain="medical")

# Bad: No domain for medical content (might use general LLM)
response = await llm_bus.call_llm_structured(...)  # Medical content without domain
```

### 2. Register Appropriate Metadata
```python
# Good: Complete metadata
metadata={
    "domain": "medical",
    "model": "llama3-medical-70b",
    "offline": True,
    "certified": True,
    "version": "2024.1"
}

# Bad: Missing domain
metadata={"model": "llama3-medical-70b"}
```

### 3. Handle Domain-Specific Failures
```python
try:
    response = await llm_bus.call_llm_structured(..., domain="medical")
except RuntimeError as e:
    if "No LLM services available" in str(e):
        # Fallback logic or user notification
        logger.error("Medical LLM unavailable, cannot proceed safely")
        raise
```

## Security Considerations

### Medical Domain
- Must run offline (no external APIs)
- Requires medical certification metadata
- Should use deterministic responses (temperature=0.0)
- Audit logging recommended

### Legal Domain
- May require jurisdiction metadata
- Should track model training date
- Consider regulatory compliance

### Financial Domain
- May require compliance certifications
- Should track data sources
- Consider market regulations

## Testing

Run the domain routing tests:

```bash
pytest tests/logic/buses/test_llm_bus_domain_routing.py -v
```

## Migration Guide

### Existing Code (No Changes Needed)
```python
# This continues to work exactly as before
response, usage = await llm_bus.call_llm_structured(
    messages=messages,
    response_model=MyResponse,
    handler_name="my_handler"
)
```

### Adding Domain Support
```python
# Simply add the domain parameter
response, usage = await llm_bus.call_llm_structured(
    messages=messages,
    response_model=MyResponse,
    handler_name="my_handler",
    domain="medical"  # Add this line
)
```

## Troubleshooting

### Issue: Domain requests failing
**Solution**: Check that domain-specific LLMs are registered with correct metadata

### Issue: Wrong LLM being selected
**Solution**: Verify metadata.domain field and service priorities

### Issue: No fallback to general LLM
**Solution**: Ensure at least one service has domain="general"

## Future Enhancements

Potential future improvements:
- Domain-specific token limits
- Domain-based rate limiting
- Cross-domain capability detection
- Domain-specific prompt templates
- Automatic domain detection from content

## Summary

Domain-aware LLM routing provides a clean, backward-compatible way to route requests to specialized models. By leveraging existing infrastructure (ServiceRegistry metadata and priorities), it adds powerful routing capabilities without complexity or breaking changes.

The system naturally supports medical, legal, financial, and other specialized domains while maintaining the flexibility and reliability of the original LLMBus design.
