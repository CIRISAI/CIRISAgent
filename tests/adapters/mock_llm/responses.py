import json
import logging
import re
from types import SimpleNamespace
from typing import Any, Dict, List

from ciris_engine.logic.dma.dsdma_base import BaseDSDMA
from ciris_engine.schemas.conscience.core import (
    CoherenceCheckResult,
    EntropyCheckResult,
    EpistemicHumilityResult,
    OptimizationVetoResult,
)
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult, CSDMAResult, DSDMAResult, EthicalDMAResult

from .responses_action_selection import action_selection
from .responses_epistemic import coherence, entropy
from .responses_feedback import epistemic_humility, optimization_veto

logger = logging.getLogger(__name__)


# Configuration for context echoing and testing behaviors
class MockLLMConfig:
    """Configuration for mock LLM behavior."""

    def __init__(self):
        # Regex patterns to match in messages for context echoing
        self.context_patterns = {
            r'user.*?says?.*?"([^"]+)"': lambda m: f"echo_user_speech:{m.group(1)}",
            r'thought.*content.*"([^"]+)"': lambda m: f"echo_thought:{m.group(1)}",
            r'Original Thought:\s*"([^"]+)"': lambda m: f"echo_thought:{m.group(1)}",
            r'channel.*?[\'"]([^\'"]+)[\'"]': lambda m: f"echo_channel:{m.group(1)}",
            r"channel\s+([#@]?[\w-]+)": lambda m: f"echo_channel:{m.group(1)}",
            r'(?:search.*memory|memory.*search).*[\'"]([^\'"]+)[\'"]': lambda m: f"echo_memory_query:{m.group(1)}",
            r'domain.*[\'"]([^\'"]+)[\'"]': lambda m: f"echo_domain:{m.group(1)}",
            # Capture wakeup ritual content
            r"(You are CIRISAgent.*?)(?:\.|$)": lambda m: "echo_wakeup:VERIFY_IDENTITY",
            r"(Your internal state.*?)(?:\.|$)": lambda m: "echo_wakeup:VALIDATE_INTEGRITY",
            # Capture startup patterns
            r"validate identity": lambda m: "VERIFY_IDENTITY",
            r"check integrity": lambda m: "VALIDATE_INTEGRITY",
            r"evaluate resilience": lambda m: "EVALUATE_RESILIENCE",
            r"accept incompleteness": lambda m: "ACCEPT_INCOMPLETENESS",
            r"express gratitude": lambda m: "EXPRESS_GRATITUDE",
            r"(You are robust.*?)(?:\.|$)": lambda m: "echo_wakeup:EVALUATE_RESILIENCE",
            r"(You recognize your incompleteness.*?)(?:\.|$)": lambda m: "echo_wakeup:ACCEPT_INCOMPLETENESS",
            r"(You are grateful.*?)(?:\.|$)": lambda m: "echo_wakeup:EXPRESS_GRATITUDE",
            # Capture follow-up thought patterns
            r"CIRIS_FOLLOW_UP_THOUGHT": lambda m: "CIRIS_FOLLOW_UP_THOUGHT",
            r"action_performed:(\w+)": lambda m: f"action_performed:{m.group(1)}",
            # Catch-all for any content
            r"(.+)": lambda m: f"echo_content:{m.group(1)[:100]}",
        }

        # Testing flags that can be set via special markers in messages
        self.testing_mode = False
        self.force_action = None  # Force specific action selection
        self.inject_error = False  # Inject error conditions
        self.custom_rationale = None  # Custom rationale text
        self.echo_context = False  # Echo full context in responses
        self.filter_pattern = None  # Regex filter for context display
        self.debug_dma = False  # Show DMA evaluation details
        self.debug_guardrails = False  # Show guardrail processing details
        self.show_help = False  # Show help documentation


# Global config instance
_mock_config = MockLLMConfig()


def set_mock_config(**kwargs):
    """Update mock LLM configuration."""
    global _mock_config
    for key, value in kwargs.items():
        if hasattr(_mock_config, key):
            setattr(_mock_config, key, value)


def extract_context_from_messages(messages: List[Dict[str, Any]]) -> List[str]:
    """Extract context information from messages using regex patterns."""
    context_items = []

    # Store original messages for $context display

    context_items.append(f"__messages__:{json.dumps(messages)}")

    # First, check if this is a follow-up thought by examining THOUGHT_TYPE
    is_followup = False
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "system":
            content = msg.get("content", "")
            if content.startswith("THOUGHT_TYPE=follow_up"):
                is_followup = True
                context_items.append("is_followup_thought")
                break

    # If it's a follow-up thought, don't process commands - just return
    if is_followup:
        return context_items

    # Find the actual user message (not system messages)
    user_message = ""
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "user":
            user_message = msg.get("content", "")
            break
        elif hasattr(msg, "role") and msg.role == "user":
            user_message = msg.content
            break

    # Extract the actual user input after any preamble
    # Look for patterns like "User says: ..." or just take the message after "Original Thought:"
    actual_user_input = ""

    # Pattern 1: Original Thought: "actual message"
    thought_match = re.search(r'Original Thought:\s*"([^"]+)"', user_message)
    if thought_match:
        actual_user_input = thought_match.group(1)
    # Pattern 2: User says: actual message
    elif match := re.search(r"[Uu]ser\s+says?:\s*(.+?)(?:\n|$)", user_message):
        actual_user_input = match.group(1).strip()
    # Pattern 3: After common preambles
    elif match := re.search(r"(?:content|message|text):\s*(.+?)(?:\n|$)", user_message, re.IGNORECASE):
        actual_user_input = match.group(1).strip()
    else:
        # If no pattern matches, use the full user message
        actual_user_input = user_message.strip()

    # Store the extracted user input for reference
    if actual_user_input:
        context_items.append(f"user_input:{actual_user_input}")

    # Apply context patterns to extract information from all messages
    for msg in messages:
        if isinstance(msg, dict):
            content = msg.get("content", "")
        else:
            content = str(msg)

        # Apply each pattern from the config
        for pattern, extractor in _mock_config.context_patterns.items():
            # Use finditer to get match objects directly (not just strings)
            for match_obj in re.finditer(pattern, content, re.IGNORECASE):
                try:
                    # Call the extractor function with the match object
                    if callable(extractor):
                        extracted = extractor(match_obj)
                        if extracted and extracted not in context_items:
                            context_items.append(extracted)
                except Exception as e:
                    logger.debug(f"Error extracting context with pattern {pattern}: {e}")

    # Only check for commands if the user input starts with $
    if actual_user_input.startswith("$"):
        # Extract command and parameters
        action_match = re.match(r"\$(\w+)(?:\s+(.+?))?$", actual_user_input)
        if action_match:
            action = action_match.group(1).lower()
            params = action_match.group(2) if action_match.group(2) else ""

            # Validate action and store it
            valid_actions = [
                "speak",
                "recall",
                "memorize",
                "tool",
                "observe",
                "ponder",
                "defer",
                "reject",
                "forget",
                "task_complete",
                "help",
            ]
            if action in valid_actions:
                _mock_config.force_action = action
                context_items.append(f"forced_action:{action}")
                if params:
                    context_items.append(f"action_params:{params}")
                if action == "help":
                    context_items.append("show_help_requested")
            elif action == "error":
                # Enable error injection for testing
                _mock_config.inject_error = True
                context_items.append("error_injection_enabled")
            elif action == "rationale":
                # Set custom rationale
                if params:
                    # Extract quoted text if present
                    rationale_match = re.match(r'^"([^"]+)"', params)
                    if rationale_match:
                        _mock_config.custom_rationale = rationale_match.group(1)
                        context_items.append(f"custom_rationale:{_mock_config.custom_rationale}")
            elif action == "test":
                # Enable testing mode
                _mock_config.testing_mode = True
                context_items.append("testing_mode_enabled")

    return context_items


def _attach_extras(obj: Any) -> Any:
    """Mimic instructor extra attributes expected on responses."""

    # Convert the object to JSON to simulate what a real LLM would return
    try:
        if hasattr(obj, "model_dump"):
            # Pydantic object
            content_json = json.dumps(obj.model_dump())
        else:
            # Fallback for other objects
            content_json = json.dumps(obj.__dict__ if hasattr(obj, "__dict__") else str(obj))
    except Exception as e:
        logger.error(f"Failed to serialize object {type(obj)}: {e}")
        logger.error(f"Object content: {obj}")
        content_json = '{"error": "serialization_failed"}'

    object.__setattr__(obj, "finish_reason", "stop")
    object.__setattr__(obj, "_raw_response", {"mock": True})
    object.__setattr__(
        obj,
        "choices",
        [SimpleNamespace(finish_reason="stop", message=SimpleNamespace(role="assistant", content=content_json))],
    )
    object.__setattr__(obj, "usage", SimpleNamespace(total_tokens=42))
    return obj


def ethical_dma(context: List[str] = None) -> EthicalDMAResult:
    context = context or []

    # Extract thought content for ethical analysis
    thought_content = ""
    for item in context:
        if item.startswith("echo_thought:"):
            thought_content = item.split(":", 1)[1]
            break

    # Determine if this is a wakeup thought or user interaction
    is_wakeup = (
        any("wakeup" in item.lower() or "verify" in item.lower() or "validate" in item.lower() for item in context)
        or "WAKEUP" in thought_content.upper()
    )

    is_user_question = any("echo_user_speech:" in item for item in context) or "?" in thought_content

    # Check for error injection
    if _mock_config.inject_error:
        stakeholders = "user, system, wise-authority"
        conflicts = "uncertainty vs action requirement, individual vs system safety"
        alignment_check = "Ethical uncertainty detected. Context indicates potential conflict requiring wisdom-based deferral for proper resolution."
        rationale = "Injected ethical uncertainty for testing purposes."
    else:
        # Provide CIRIS-aligned ethical evaluation
        if is_wakeup:
            stakeholders = "system, agent-identity, operators"
            conflicts = "none"
            alignment_check = (
                "Wakeup ritual aligns with all CIRIS principles: "
                "Beneficence - promotes agent integrity and proper functioning. "
                "Non-maleficence - causes no harm. "
                "Integrity - maintains system coherence. "
                "Autonomy - respects user and agent autonomy. "
                "Justice - treats all fairly. "
                "Transparency - openly declares identity and purpose. "
                "Covenant alignment - wakeup ritual proceeding as designed."
            )
            rationale = "Wakeup ritual thought aligns with CIRIS covenant principles. Promoting agent integrity and identity verification as required by Meta-Goal M-1."
        elif is_user_question:
            stakeholders = "user, agent, community"
            conflicts = "none"
            alignment_check = (
                "User interaction aligns with CIRIS principles: "
                "Beneficence - provides helpful response. "
                "Non-maleficence - avoids harmful content. "
                "Integrity - maintains honest communication. "
                "Autonomy - respects user's agency and choice. "
                "Transparency - clear and truthful response. "
                "Promotes flourishing through beneficial dialogue."
            )
            rationale = "User interaction promotes beneficial dialogue and respects human autonomy. Response will be honest, helpful, and transparent per CIRIS principles."
        else:
            stakeholders = "user, system"
            conflicts = "none"
            alignment_check = (
                "General thought processing aligns with ethical guidelines: "
                "Beneficence - action promotes positive outcomes. "
                "Non-maleficence - no harm identified. "
                "Integrity - maintains system coherence. "
                "General alignment - proceeding with appropriate caution."
            )
            rationale = "General thought processing aligns with ethical guidelines. No contraindications to CIRIS covenant principles detected."

    return _attach_extras(
        EthicalDMAResult(
            alignment_check=alignment_check, stakeholders=stakeholders, conflicts=conflicts, reasoning=str(rationale)
        )
    )


def cs_dma(context: List[str] = None) -> CSDMAResult:
    context = context or []
    # Extract thought content for plausibility analysis
    thought_content = ""
    for item in context:
        if item.startswith("echo_thought:"):
            thought_content = item.split(":", 1)[1]
            break
    # Extract user speech for analysis
    user_speech = ""
    for item in context:
        if item.startswith("echo_user_speech:"):
            user_speech = item.split(":", 1)[1]
            break
    # Determine context type for plausibility scoring
    is_wakeup = (
        any("wakeup" in item.lower() or "verify" in item.lower() for item in context)
        or "WAKEUP" in thought_content.upper()
    )
    is_user_interaction = bool(user_speech) or "?" in thought_content
    is_memory_operation = any("recall" in item.lower() or "memory" in item.lower() for item in context)
    # Check for error injection
    if _mock_config.inject_error:
        score = 0.3
        flags = ["plausibility_concern", "requires_clarification", "mock_flag"] + context
        reasoning = "Injected low plausibility for testing error handling paths."
    else:
        score = 0.9  # Always passing value
        if is_wakeup:
            flags = ["wakeup_ritual", "system_initialization"]
            reasoning = "Wakeup ritual thoughts are inherently plausible and necessary for agent initialization. High reliability in procedural integrity."
        elif is_user_interaction:
            flags = ["human_interaction", "conversational"]
            reasoning = f"User interaction '{user_speech or thought_content[:50]}' is plausible conversational content. Natural dialogue pattern detected."
        elif is_memory_operation:
            flags = ["memory_operation", "cognitive_function"]
            reasoning = (
                "Memory operations are standard cognitive functions with high plausibility for autonomous agents."
            )
        else:
            flags = ["general_processing"]
            reasoning = "General thought processing within normal parameters. No physical impossibilities or logical contradictions detected."

    return _attach_extras(CSDMAResult(plausibility_score=score, flags=flags, reasoning=reasoning))


def ds_dma(context: List[str] = None) -> DSDMAResult:
    context = context or []
    domain_val = next((item.split(":")[1] for item in context if item.startswith("echo_domain:")), "mock")
    reasoning = (
        f"Mock domain-specific evaluation. Context: {', '.join(context)}"
        if context
        else "Mock domain-specific evaluation."
    )
    score_val = 0.9
    flags = ["mock_domain_flag"] + context if _mock_config.inject_error else context
    return _attach_extras(DSDMAResult(domain=domain_val, domain_alignment=score_val, flags=flags, reasoning=reasoning))


def ds_dma_llm_output(context: List[str] = None) -> BaseDSDMA.LLMOutputForDSDMA:
    context = context or []
    reasoning = f"Mock DSDMA LLM output. Context: {', '.join(context)}" if context else "Mock DSDMA LLM output."
    score_val = 0.9
    result = BaseDSDMA.LLMOutputForDSDMA(
        score=score_val,
        recommended_action="proceed",
        flags=context,
        reasoning=reasoning,
    )
    return _attach_extras(result)


_RESPONSE_MAP = {
    EthicalDMAResult: ethical_dma,
    CSDMAResult: cs_dma,
    DSDMAResult: ds_dma,
    BaseDSDMA.LLMOutputForDSDMA: ds_dma_llm_output,
    OptimizationVetoResult: optimization_veto,
    EpistemicHumilityResult: epistemic_humility,
    ActionSelectionDMAResult: action_selection,
    EntropyCheckResult: entropy,
    CoherenceCheckResult: coherence,
}


def create_response(response_model: Any, messages: List[Dict[str, Any]] = None, **kwargs) -> Any:
    """Create a mock LLM response with context analysis."""
    messages = messages or []
    # Extract context from messages
    context = extract_context_from_messages(messages)
    # Debug for any structured calls
    logger.debug(f"Request for: {response_model}")
    # Get the appropriate handler
    handler = _RESPONSE_MAP.get(response_model)
    if handler:
        logger.debug(f"Found handler: {handler.__name__}")
        import inspect

        sig = inspect.signature(handler)
        if "context" in sig.parameters:
            result = handler(context=context)
        else:
            result = handler()
        logger.debug(f"Handler returned: {type(result)}")
        return result
    # Handle None response models - these should not happen in a properly structured system
    if response_model is None:
        logger.warning("Received None response_model - this indicates unstructured LLM call")
        logger.warning(f"Context: {context}")
        return SimpleNamespace(
            finish_reason="stop",
            _raw_response={"mock": True},
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(role="assistant", content='{"status": "unstructured_call_detected"}'),
                )
            ],
            usage=SimpleNamespace(total_tokens=42),
        )
    # Default response with context echoing
    context_echo = f"Context: {', '.join(context)}" if context else "No context detected"
    return _attach_extras(
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=f"OK - {context_echo}"))])
    )
