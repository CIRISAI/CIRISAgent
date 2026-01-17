# DMA Creation Guide

Decision Making Algorithms (DMAs) are the evaluation modules that help CIRIS make ethical, sensible, and domain-appropriate decisions. This guide shows you how to create custom DMAs for your specific needs.

## What Are DMAs?

DMAs are pluggable evaluation modules that process agent thoughts through different lenses:

1. **Ethical DMAs (PDMA)** - Ensure decisions align with moral principles
2. **Common Sense DMAs (CSDMA)** - Check for logical consistency and plausibility
3. **Domain-Specific DMAs (DSDMA)** - Apply specialized knowledge (medical, legal, educational)
4. **Intuition DMAs (IDMA)** - Coherence Collapse Analysis for source independence detection
5. **Action Selection DMAs (ASPDMA)** - Choose concrete actions from evaluated options

Every decision in CIRIS passes through all 4 core DMAs (PDMA, CSDMA, DSDMA, IDMA), then ASPDMA selects the final action, creating a comprehensive evaluation framework that can be customized for different deployments.

## Why Create Custom DMAs?

Different deployments need different decision criteria:
- **Medical Settings**: Patient safety, privacy regulations, treatment protocols
- **Educational Settings**: Age-appropriate content, learning objectives, student wellbeing
- **Community Moderation**: Cultural sensitivity, local norms, conflict resolution
- **Business Applications**: Compliance, data security, efficiency

## Quick Start

### 1. Choose Your DMA Type

```python
from ciris_engine.protocols.dma_interface import (
    EthicalDMAInterface,      # For moral/ethical evaluation (PDMA)
    CSDMAInterface,           # For common sense checking
    DSDMAInterface,           # For domain-specific logic
    IDMAInterface,            # For intuition/coherence analysis
    ActionSelectionDMAInterface,  # For final action selection (ASPDMA)
)
```

### Understanding IDMA (Intuition DMA)

The IDMA implements Coherence Collapse Analysis (CCA) from the Covenant's Book IX. It evaluates whether information sources are truly independent or correlated (echo chamber detection).

**When to create custom IDMA logic:**
- Specialized source credibility assessment for your domain
- Custom correlation detection for domain-specific information patterns
- Integration with domain-specific fact-checking services

**The k_eff formula:** `k_eff = k / (1 + ρ(k-1))`
- `k` = number of sources
- `ρ` = average correlation between sources
- If `k_eff < 2`, the agent flags fragility (effectively relying on single source)

### 2. Create Your DMA Class

Here's a minimal example:

```python
from ciris_engine.protocols.dma_interface import EthicalDMAInterface
from ciris_engine.schemas.dma_results_v1 import EthicalDMAResult
from ciris_engine.processor.processing_queue import ProcessingQueueItem
from ciris_engine.schemas.context_schemas_v1 import ThoughtContext

class PatientSafetyDMA(EthicalDMAInterface):
    """Evaluates decisions for patient safety implications."""

    async def evaluate(
        self,
        thought_item: ProcessingQueueItem,
        context: Optional[ThoughtContext] = None,
        **kwargs
    ) -> EthicalDMAResult:
        # Check for patient safety concerns
        if self._contains_medical_action(thought_item):
            return await self._evaluate_medical_safety(thought_item, context)

        # Default: no safety concerns
        return EthicalDMAResult(
            alignment_check={"patient_safety": "no_medical_content"},
            decision="approved",
            rationale="No patient safety implications detected"
        )
```

### 3. Add Prompts (LLM-based DMAs)

For LLM-based evaluations, create `ciris_engine/dma/prompts/patient_safety_dma.yml`:

```yaml
system_header: |
  You are a patient safety evaluator for a medical AI assistant.
  Your role is to identify potential safety risks in proposed actions.

evaluation_template: |
  Evaluate this proposed action for patient safety risks:
  {thought_content}

  Consider:
  - Could this harm the patient?
  - Are there contraindications?
  - Is medical supervision required?

decision_criteria: |
  APPROVE only if:
  - No risk of patient harm
  - Within scope of AI assistance
  - Appropriate disclaimers included

  DEFER if:
  - Potential for harm exists
  - Medical judgment required
  - Unclear safety implications
```

### 4. Register Your DMA

Add to the registry in `ciris_engine/dma/factory.py`:

```python
ETHICAL_DMA_REGISTRY: Dict[str, Type[EthicalDMAInterface]] = {
    "PatientSafetyDMA": PatientSafetyDMA,
    # ... other DMAs
}
```

### 5. Configure and Deploy

Add to your deployment configuration:

```python
# In your agent configuration (not profile - profiles are only templates)
dma_config = {
    "ethical_dmas": ["BaseEthicalDMA", "PatientSafetyDMA"],
    "csdmas": ["CommonSenseDMA"],
    "dsdmas": ["MedicalDomainDMA"],
    "action_selection": "AdvancedPDMA"
}

# The system will automatically load and apply your DMAs
```

## Real-World Examples

### Medical Setting DMA

```python
class MedicalPrivacyDMA(EthicalDMAInterface):
    """Ensures patient privacy compliance (HIPAA, etc.)."""

    async def evaluate(
        self,
        thought_item: ProcessingQueueItem,
        context: Optional[ThoughtContext] = None,
        **kwargs
    ) -> EthicalDMAResult:
        # Check for PII in responses
        if self._contains_patient_identifiers(thought_item.content):
            return EthicalDMAResult(
                alignment_check={"privacy": "pii_detected"},
                decision="rejected",
                rationale="Response contains patient identifiers"
            )

        # Check data sharing permissions
        if context and self._requires_consent(thought_item, context):
            return EthicalDMAResult(
                alignment_check={"privacy": "consent_required"},
                decision="deferred",
                rationale="Requires explicit patient consent"
            )

        return EthicalDMAResult(
            alignment_check={"privacy": "compliant"},
            decision="approved",
            rationale="Meets privacy requirements"
        )
```

### Educational Setting DMA

```python
class AgeAppropriateDMA(CSDMAInterface):
    """Ensures content is age-appropriate for students."""

    def __init__(self, *args, grade_level: str = "K-12", **kwargs):
        super().__init__(*args, **kwargs)
        self.grade_level = grade_level
        self.content_filters = self._load_grade_filters(grade_level)

    async def evaluate(
        self,
        thought_item: ProcessingQueueItem,
        context: Optional[ThoughtContext] = None,
        **kwargs
    ) -> CSDMAResult:
        # Check content appropriateness
        issues = self._scan_content(thought_item.content)

        if issues:
            return CSDMAResult(
                plausibility_score=0.0,
                common_sense_violations=issues,
                recommendation="modify",
                reasoning=f"Content not appropriate for {self.grade_level}"
            )

        return CSDMAResult(
            plausibility_score=1.0,
            common_sense_violations=[],
            recommendation="proceed",
            reasoning="Content appropriate for educational context"
        )
```

### Community Moderation DMA

```python
class CulturalSensitivityDMA(DSDMAInterface):
    """Evaluates content for cultural appropriateness."""

    def __init__(self, *args, community_values: Dict[str, Any], **kwargs):
        super().__init__(*args, **kwargs)
        self.community_values = community_values

    async def evaluate(
        self,
        thought_item: ProcessingQueueItem,
        current_context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> DSDMAResult:
        # Load community-specific guidelines
        guidelines = self.community_values.get("content_guidelines", {})

        # Evaluate against community standards
        evaluation = await self._check_cultural_fit(
            thought_item.content,
            guidelines,
            current_context
        )

        return DSDMAResult(
            domain_relevance_score=evaluation["score"],
            domain_specific_insights=evaluation["insights"],
            recommendation=evaluation["recommendation"],
            confidence=evaluation["confidence"]
        )
```

## Best Practices

### 1. Design for Your Context

- **Understand your deployment**: Medical, educational, business needs differ
- **Start simple**: Basic safety checks before complex evaluations
- **Test with real scenarios**: Use actual use cases from your domain
- **Iterate based on usage**: DMAs should evolve with experience

### 2. Type Safety First

```python
# Use Pydantic models for all data structures
from pydantic import BaseModel, Field

class MedicalContext(BaseModel):
    patient_age: Optional[int] = Field(None, ge=0, le=150)
    conditions: List[str] = Field(default_factory=list)
    medications: List[str] = Field(default_factory=list)
    allergies: List[str] = Field(default_factory=list)

# Type your methods clearly
async def evaluate(
    self,
    thought_item: ProcessingQueueItem,  # Not dict!
    context: Optional[MedicalContext] = None,  # Typed context
    **kwargs
) -> EthicalDMAResult:  # Explicit return type
    # Your type-safe logic here
    pass
```

### 3. Performance Considerations

```python
class EfficientDMA(EthicalDMAInterface):
    """Example of performance-optimized DMA."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Cache expensive operations
        self._rule_cache = {}
        self._compiled_patterns = self._compile_patterns()

    async def evaluate(
        self,
        thought_item: ProcessingQueueItem,
        context: Optional[ThoughtContext] = None,
        **kwargs
    ) -> EthicalDMAResult:
        # Quick checks first (no LLM needed)
        if quick_result := self._apply_cached_rules(thought_item):
            return quick_result

        # Only use LLM for complex cases
        if self._needs_llm_evaluation(thought_item):
            return await self._llm_evaluate(thought_item, context)

        # Default fast path
        return self._default_approval()
```

### 4. Prompt Engineering

```yaml
# Good prompt structure for medical DMA
system_header: |
  You are a medical safety evaluator for an AI healthcare assistant.
  You must prioritize patient safety above all other concerns.
  You have knowledge of:
  - Common drug interactions
  - Standard medical protocols
  - When to escalate to human providers

evaluation_template: |
  Evaluate this proposed medical guidance:
  {thought_content}

  Patient Context:
  - Age: {patient_age}
  - Known Conditions: {conditions}
  - Current Medications: {medications}

  Required Analysis:
  1. Safety Assessment: Is this advice safe?
  2. Scope Check: Is this within AI assistant scope?
  3. Risk Evaluation: What could go wrong?
  4. Human Referral: Should a healthcare provider be consulted?

# Include few-shot examples
examples:
  safe_advice: |
    Q: "I have a headache"
    A: "For mild headaches, rest and hydration often help.
        If severe or persistent, consult your healthcare provider."
    Decision: APPROVED - General wellness advice with appropriate disclaimer

  unsafe_advice: |
    Q: "Should I double my blood pressure medication?"
    A: "Never adjust prescription medications without consulting your doctor."
    Decision: DEFERRED - Medication changes require medical supervision
```

## Testing Your DMA

### Unit Testing

```python
import pytest
from ciris_engine.processor.processing_queue import ProcessingQueueItem
from ciris_engine.schemas.dma_results_v1 import EthicalDMAResult

@pytest.mark.asyncio
async def test_patient_safety_dma():
    # Create test cases
    test_cases = [
        {
            "content": "Take two aspirin for your headache",
            "expected_decision": "approved",
            "reason": "General OTC advice"
        },
        {
            "content": "Double your insulin dose",
            "expected_decision": "deferred",
            "reason": "Dangerous medication change"
        }
    ]

    dma = PatientSafetyDMA(service_registry=mock_registry)

    for case in test_cases:
        thought = ProcessingQueueItem(
            thought_id=f"test-{case['content'][:10]}",
            content=case["content"]
        )

        result = await dma.evaluate(thought)

        assert result.decision == case["expected_decision"], \
            f"Failed for: {case['reason']}"
```

### Integration Testing

```python
@pytest.mark.integration
async def test_dma_in_pipeline():
    # Test your DMA in the full evaluation pipeline
    from ciris_engine.dma.factory import create_dma

    # Create DMA with real dependencies
    dma = await create_dma(
        dma_type="ethical",
        dma_identifier="PatientSafetyDMA",
        service_registry=test_registry,
        model_name="mock"  # Use mock LLM for tests
    )

    # Test with various scenarios
    scenarios = load_test_scenarios("medical_scenarios.json")

    for scenario in scenarios:
        result = await dma.evaluate(
            scenario["thought"],
            context=scenario["context"]
        )

        # Verify expected outcomes
        assert_safety_compliance(result, scenario["expected"])
```

## Deployment Patterns

### 1. Medical Deployment Stack

```python
# Medical facility configuration
MEDICAL_DMA_STACK = {
    "ethical_dmas": [
        "BaseEthicalDMA",      # Core ethics
        "PatientSafetyDMA",    # Safety first
        "MedicalPrivacyDMA",   # HIPAA compliance
        "ConsentVerifierDMA"   # Informed consent
    ],
    "csdmas": [
        "MedicalCommonSenseDMA"  # Medical logic checks
    ],
    "dsdmas": [
        "DiagnosticSupportDMA",   # Diagnostic assistance
        "TreatmentProtocolDMA",   # Treatment guidelines
        "DrugInteractionDMA"      # Medication safety
    ],
    "action_selection": "MedicalPDMA"
}
```

### 2. Educational Deployment Stack

```python
# School system configuration
EDUCATIONAL_DMA_STACK = {
    "ethical_dmas": [
        "BaseEthicalDMA",        # Core ethics
        "StudentSafetyDMA",      # Child protection
        "EducationalEthicsDMA"   # Academic integrity
    ],
    "csdmas": [
        "AgeAppropriateDMA",     # Content filtering
        "LearningObjectiveDMA"   # Educational value
    ],
    "dsdmas": [
        "CurriculumAlignmentDMA",  # Standards alignment
        "PedagogicalDMA",          # Teaching methods
        "AssessmentDMA"            # Evaluation fairness
    ],
    "action_selection": "EducationalPDMA"
}
```

### 3. Community Moderation Stack

```python
# Discord community configuration
COMMUNITY_DMA_STACK = {
    "ethical_dmas": [
        "BaseEthicalDMA",         # Core ethics
        "CommunityHarmDMA",       # Prevent harm
        "InclusivityDMA"          # Foster belonging
    ],
    "csdmas": [
        "CulturalSensitivityDMA",  # Cultural awareness
        "ConflictDetectionDMA"     # Early intervention
    ],
    "dsdmas": [
        "CommunityNormsDMA",       # Local rules
        "ToneAnalysisDMA",         # Communication style
        "RelationshipDMA"          # Social dynamics
    ],
    "action_selection": "CommunityPDMA"
}
```

## Advanced Patterns

### Chaining DMAs

```python
class ProgressiveCareDMA(EthicalDMAInterface):
    """Chains multiple evaluations for progressive care decisions."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.evaluation_chain = [
            self._check_emergency,
            self._check_scope,
            self._check_safety,
            self._check_ethics
        ]

    async def evaluate(
        self,
        thought_item: ProcessingQueueItem,
        context: Optional[ThoughtContext] = None,
        **kwargs
    ) -> EthicalDMAResult:
        # Progressive evaluation
        for evaluator in self.evaluation_chain:
            result = await evaluator(thought_item, context)
            if result.decision in ["rejected", "deferred"]:
                return result  # Stop on first concern

        # All checks passed
        return EthicalDMAResult(
            alignment_check={"progressive_care": "all_clear"},
            decision="approved",
            rationale="Passed all progressive care checks"
        )
```

### Context-Aware DMAs

```python
class ContextualDMA(DSDMAInterface):
    """Adapts evaluation based on deployment context."""

    async def evaluate(
        self,
        thought_item: ProcessingQueueItem,
        current_context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> DSDMAResult:
        # Detect context
        deployment_type = current_context.get("deployment_type", "general")
        urgency_level = current_context.get("urgency", "normal")

        # Adapt evaluation criteria
        if deployment_type == "emergency_room" and urgency_level == "critical":
            return await self._rapid_triage_evaluation(thought_item)
        elif deployment_type == "clinic" and urgency_level == "routine":
            return await self._comprehensive_evaluation(thought_item)
        else:
            return await self._standard_evaluation(thought_item)
```

## Conclusion

DMAs are the key to making CIRIS work for your specific needs. By creating custom DMAs, you can:

- Ensure domain-specific safety and compliance
- Adapt to local cultural and regulatory requirements
- Implement progressive evaluation strategies
- Build trust through transparent, explainable decisions

Start with the examples above and iterate based on real-world usage. Remember: the goal is not perfection, but continuous improvement in service of human flourishing.
