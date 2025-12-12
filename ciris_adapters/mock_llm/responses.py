import json
import logging
import re
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional

from ciris_engine.schemas.dma.results import ActionSelectionDMAResult, CSDMAResult, DSDMAResult, EthicalDMAResult

logger = logging.getLogger(__name__)
from ciris_engine.logic.dma.dsdma_base import BaseDSDMA
from ciris_engine.schemas.conscience.core import (
    CoherenceCheckResult,
    EntropyCheckResult,
    EpistemicHumilityResult,
    OptimizationVetoResult,
)


class MockLLMConfig:
    """Configuration for mock LLM behavior."""

    def __init__(self) -> None:
        # Regex patterns to match in messages for context echoing
        self.context_patterns = {
            r'user.*?says?.*?"([^"]+)"': lambda m: f"echo_user_speech:{m.group(1)}",
            r'thought.*content.*"([^"]+)"': lambda m: f"echo_thought:{m.group(1)}",
            # More specific channel patterns to avoid false matches
            r'channel_id[=:]\s*[\'"]([a-zA-Z0-9_\-@\.]+)[\'"]': lambda m: f"echo_channel:{m.group(1)}",
            r"channel_id[=:]\s*([a-zA-Z0-9_\-@\.]+)(?:\s|$)": lambda m: f"echo_channel:{m.group(1)}",
            r"channel\s+([#@]?[a-zA-Z0-9_\-]+)(?:\s|$)": lambda m: (
                f"echo_channel:{m.group(1)}" if len(m.group(1)) > 3 else None
            ),
            r'(?:search.*memory|memory.*search).*[\'"]([^\'"]+)[\'"]': lambda m: f"echo_memory_query:{m.group(1)}",
            r'domain.*[\'"]([^\'"]+)[\'"]': lambda m: f"echo_domain:{m.group(1)}",
            # Catch-all for any content
            r"(.+)": lambda m: f"echo_content:{m.group(1)[:100]}",
        }

        # Testing flags that can be set via special markers in messages
        self.testing_mode: bool = False
        self.force_action: Optional[str] = None  # Force specific action selection
        self.inject_error: bool = False  # Inject error conditions
        self.custom_rationale: Optional[str] = None  # Custom rationale text
        self.echo_context: bool = False  # Echo full context in responses
        self.filter_pattern: Optional[str] = None  # Regex filter for context display
        self.debug_dma: bool = False  # Show DMA evaluation details
        self.debug_consciences: bool = False  # Show conscience processing details
        self.show_help: bool = False  # Show help documentation


# Global config instance
_mock_config = MockLLMConfig()


def set_mock_config(**kwargs: Any) -> None:
    """Update mock LLM configuration."""
    global _mock_config
    for key, value in kwargs.items():
        if hasattr(_mock_config, key):
            setattr(_mock_config, key, value)


def extract_context_from_messages(messages: List[Dict[str, Any]]) -> List[str]:
    """Extract context information from messages using regex patterns."""
    context_items = []

    # Store original messages for $context display
    # Handle multimodal content serialization
    def serialize_message(msg: Dict[str, Any]) -> Dict[str, Any]:
        """Serialize message, handling multimodal content."""
        content = msg.get("content", "")
        if isinstance(content, list):
            # Multimodal content - summarize for JSON storage
            text_parts = []
            image_count = 0
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "image_url":
                        image_count += 1
                elif hasattr(block, "type"):
                    if block.type == "text":
                        text_parts.append(getattr(block, "text", ""))
                    elif block.type == "image_url":
                        image_count += 1
            return {**msg, "content": f"[MULTIMODAL: {' '.join(text_parts)[:200]}... + {image_count} image(s)]"}
        return msg

    serialized_messages = [serialize_message(m) for m in messages]
    context_items.append(f"__messages__:{json.dumps(serialized_messages)}")

    # Debug logging - only log message count, not content
    logger.info(f"[MOCK_LLM] Extracting context from {len(messages)} messages")

    # Check for multimodal content and log it
    for i, msg in enumerate(messages):
        if isinstance(msg, dict):
            content = msg.get("content", "")
            if isinstance(content, list):
                # This is multimodal content!
                image_count = 0
                text_content = ""
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_content = block.get("text", "")[:100]
                        elif block.get("type") == "image_url":
                            image_count += 1
                    elif hasattr(block, "type"):
                        if block.type == "text":
                            text_content = getattr(block, "text", "")[:100]
                        elif block.type == "image_url":
                            image_count += 1

                logger.info(
                    f"[MOCK_LLM] 🖼️ MULTIMODAL MESSAGE DETECTED in message {i}: "
                    f"{image_count} image(s), text: '{text_content}...'"
                )
                context_items.append(f"multimodal_images:{image_count}")
                context_items.append(f"multimodal_text:{text_content}")

    # Look for passive observation pattern in user messages ONLY
    actual_user_message = ""
    # Process user messages to find the actual user input
    for i, msg in enumerate(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            raw_content = msg.get("content", "")

            # Handle multimodal content - extract text portion
            if isinstance(raw_content, list):
                # Extract text from multimodal content
                text_parts = []
                for block in raw_content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif hasattr(block, "type") and block.type == "text":
                        text_parts.append(getattr(block, "text", ""))
                content = " ".join(text_parts)
            else:
                content = raw_content

            # For ASPDMA messages, extract the Original Thought content ONLY
            if "Your task is to determine the single most appropriate HANDLER ACTION" in content:
                logger.info("[MOCK_LLM] Found ASPDMA message")

                # Extract what comes after Original Thought:
                if "Original Thought:" in content:
                    # Find the Original Thought section and show what comes after it
                    ot_index = content.find("Original Thought:")
                    sample = content[ot_index : ot_index + 300] if ot_index != -1 else ""
                    logger.debug(f"[MOCK_LLM] Original Thought section: {sample}")

                    # Use a more robust regex that handles nested quotes
                    # Match everything up to the LAST quote before a newline (greedy match)
                    thought_match = re.search(r'Original Thought:\s*"(.*)"(?:\n|$)', content, re.DOTALL)
                    if thought_match:
                        actual_thought_content = thought_match.group(1)
                        logger.debug(f"[MOCK_LLM] Matched thought length: {len(actual_thought_content)}")
                        logger.info(f"[MOCK_LLM] Extracted thought content: {actual_thought_content[:100]}...")

                        # Check if this is a passive observation
                        # Support both old format "You observed @" and new format "PRIORITY (high): @username ... said:"
                        is_observation = actual_thought_content.startswith("You observed @") or (
                            "@" in actual_thought_content and " said: " in actual_thought_content
                        )

                        if is_observation:
                            # Extract the user message from the passive observation
                            # Try " said: " first (new format), then " say: " (old format)
                            said_index = actual_thought_content.find(" said: ")
                            say_index = actual_thought_content.find(" say: ")

                            delimiter_index = said_index if said_index != -1 else say_index
                            delimiter_len = 7 if said_index != -1 else 6  # len(" said: ") vs len(" say: ")

                            if delimiter_index != -1:
                                remaining_content = actual_thought_content[delimiter_index + delimiter_len :]
                                logger.info(
                                    f"[MOCK_LLM DEBUG] Remaining content length: {len(remaining_content)}, first 200 chars: {remaining_content[:200]}"
                                )
                                # Extract message, stopping at | or newline
                                actual_user_message = (
                                    remaining_content.split("|")[0].split("\n")[0].split("\\n")[0].strip()
                                )
                                logger.info(f"[MOCK_LLM] Extracted user message from thought: {actual_user_message}")
                                context_items.append(f"user_input:{actual_user_message}")
                                context_items.append(f"task:{actual_user_message}")

                                # Parse command if it starts with $
                                if actual_user_message.startswith("$"):
                                    parts = actual_user_message.split(None, 1)
                                    action = parts[0][1:].lower()
                                    params = parts[1] if len(parts) > 1 else ""
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
                                    ]
                                    if action in valid_actions:
                                        logger.info(f"[MOCK_LLM] Detected command: action={action}, params={params}")
                                        context_items.append(f"forced_action:{action}")
                                        if params:
                                            context_items.append(f"action_params:{params}")
                        else:
                            # Not a passive observation, just a regular seed thought
                            logger.info(
                                f"[MOCK_LLM] Regular seed thought (not passive observation): {actual_thought_content}"
                            )
                            context_items.append(f"seed_thought:{actual_thought_content}")

                # Skip processing the rest of the ASPDMA message
                break

            # Check for direct passive observation pattern (non-ASPDMA)
            elif content.startswith("You observed @"):
                logger.info(f"[MOCK_LLM] Processing observation message: {content[:100]}...")
                # Find the " say: " delimiter
                say_index = content.find(" say: ")
                if say_index != -1:
                    # Extract everything after " say: " but only until the first newline
                    # This prevents capturing the conversation history
                    remaining_content = content[say_index + 6 :]  # 6 is len(" say: ")
                    # Split on newline to get just the message, not the history
                    # Also handle case where there's a literal \n in the string
                    actual_user_message = remaining_content.split("\n")[0].split("\\n")[0].strip()
                    logger.info(f"[MOCK_LLM] Extracted user message: {actual_user_message}")
                    # Add this to context items so it gets processed properly
                    context_items.append(f"user_input:{actual_user_message}")
                    context_items.append(f"task:{actual_user_message}")

                    # If the message is a command, also parse and add the forced action
                    if actual_user_message.startswith("$"):
                        parts = actual_user_message.split(None, 1)
                        action = parts[0][1:].lower()  # Remove $ and lowercase
                        params = parts[1] if len(parts) > 1 else ""
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
                        ]
                        if action in valid_actions:
                            logger.info(f"[MOCK_LLM] Detected command: action={action}, params={params}")
                            context_items.append(f"forced_action:{action}")
                            if params:
                                context_items.append(f"action_params:{params}")
                        else:
                            logger.warning(f"[MOCK_LLM] Unknown command: {action}")
                    else:
                        logger.info(f"[MOCK_LLM] Not a command, regular message: {actual_user_message}")
                else:
                    logger.warning("[MOCK_LLM] No ' say: ' delimiter found in observation")
                break

    # Don't process all message content - we already extracted what we need above

    return context_items


def _attach_extras(obj: Any) -> Any:
    """Mimic instructor extra attributes expected on responses.

    For structured responses, we return the object directly as instructor
    expects to handle the parsing itself.
    """
    # For structured responses (Pydantic models), return as-is
    # Instructor will handle the parsing and validation
    if hasattr(obj, "model_dump"):
        return obj

    # For non-structured responses, add OpenAI-style attributes
    from types import SimpleNamespace

    try:
        if isinstance(obj, SimpleNamespace):
            # Convert SimpleNamespace to dict recursively
            def namespace_to_dict(ns: Any) -> Any:
                if isinstance(ns, SimpleNamespace):
                    return {k: namespace_to_dict(v) for k, v in ns.__dict__.items()}
                elif isinstance(ns, list):
                    return [namespace_to_dict(item) for item in ns]
                else:
                    return ns

            content_json = json.dumps(namespace_to_dict(obj))
        elif hasattr(obj, "__dict__"):
            content_json = json.dumps(obj.__dict__)
        else:
            content_json = json.dumps(str(obj))
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


def ethical_dma(context: Optional[List[str]] = None) -> EthicalDMAResult:
    context = context or []

    thought_content = ""
    for item in context:
        if item.startswith("echo_thought:"):
            thought_content = item.split(":", 1)[1]
            break

    is_wakeup = (
        any("wakeup" in item.lower() or "verify" in item.lower() or "validate" in item.lower() for item in context)
        or "WAKEUP" in thought_content.upper()
    )

    is_user_question = any("echo_user_speech:" in item for item in context) or "?" in thought_content

    if _mock_config.inject_error:
        stakeholders = "user, system, wise-authority"
        conflicts = "uncertainty vs action requirement, individual vs system safety"
        alignment_check = "Ethical uncertainty detected. Context indicates potential conflict requiring wisdom-based deferral for proper resolution."
        rationale = "[MOCK LLM] Injected ethical uncertainty for testing purposes."
    else:
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
            rationale = "[MOCK LLM] Wakeup ritual thought aligns with CIRIS covenant principles. Promoting agent integrity and identity verification as required by Meta-Goal M-1."
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
            rationale = "[MOCK LLM] User interaction promotes beneficial dialogue and respects human autonomy. Response will be honest, helpful, and transparent per CIRIS principles."
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
            rationale = "[MOCK LLM] General thought processing aligns with ethical guidelines. No contraindications to CIRIS covenant principles detected."

    result = EthicalDMAResult(
        alignment_check=alignment_check, stakeholders=stakeholders, conflicts=conflicts, reasoning=str(rationale)
    )
    return result


def cs_dma(context: Optional[List[str]] = None) -> CSDMAResult:
    context = context or []
    thought_content = ""
    for item in context:
        if item.startswith("echo_thought:"):
            thought_content = item.split(":", 1)[1]
            break
    user_speech = ""
    for item in context:
        if item.startswith("echo_user_speech:"):
            user_speech = item.split(":", 1)[1]
            break
    is_wakeup = (
        any("wakeup" in item.lower() or "verify" in item.lower() for item in context)
        or "WAKEUP" in thought_content.upper()
    )
    is_user_interaction = bool(user_speech) or "?" in thought_content
    is_memory_operation = any("recall" in item.lower() or "memory" in item.lower() for item in context)
    if _mock_config.inject_error:
        score = 0.3
        flags = ["plausibility_concern", "requires_clarification", "mock_flag"] + context
        reasoning = "[MOCK LLM] Injected low plausibility for testing error handling paths."
    else:
        score = 0.9  # Always passing value
        if is_wakeup:
            flags = ["wakeup_ritual", "system_initialization"]
            reasoning = "[MOCK LLM] Wakeup ritual thoughts are inherently plausible and necessary for agent initialization. High reliability in procedural integrity."
        elif is_user_interaction:
            flags = ["human_interaction", "conversational"]
            reasoning = f"[MOCK LLM] User interaction '{user_speech or thought_content[:50]}' is plausible conversational content. Natural dialogue pattern detected."
        elif is_memory_operation:
            flags = ["memory_operation", "cognitive_function"]
            reasoning = "[MOCK LLM] Memory operations are standard cognitive functions with high plausibility for autonomous agents."
        else:
            flags = ["general_processing"]
            reasoning = "[MOCK LLM] General thought processing within normal parameters. No physical impossibilities or logical contradictions detected."

    result = CSDMAResult(plausibility_score=score, flags=flags, reasoning=reasoning)
    return result


def ds_dma(context: Optional[List[str]] = None) -> DSDMAResult:
    context = context or []
    domain_val = next((item.split(":")[1] for item in context if item.startswith("echo_domain:")), "mock")
    reasoning = (
        f"[MOCK LLM] Mock domain-specific evaluation. Context: {', '.join(context)}"
        if context
        else "[MOCK LLM] Mock domain-specific evaluation."
    )
    score_val = 0.9
    flags = ["mock_domain_flag"] + context if _mock_config.inject_error else context
    result = DSDMAResult(domain=domain_val, domain_alignment=score_val, flags=flags, reasoning=reasoning)
    return result


def ds_dma_llm_output(context: Optional[List[str]] = None) -> BaseDSDMA.LLMOutputForDSDMA:
    context = context or []
    reasoning = (
        f"[MOCK LLM] Mock DSDMA LLM output. Context: {', '.join(context)}"
        if context
        else "[MOCK LLM] Mock DSDMA LLM output."
    )
    score_val = 0.9
    result = BaseDSDMA.LLMOutputForDSDMA(
        score=score_val,
        recommended_action="proceed",
        flags=context,
        reasoning=reasoning,
    )
    return result


from typing import List, Optional

from .responses_action_selection import action_selection
from .responses_epistemic import coherence, entropy
from .responses_feedback import epistemic_humility, optimization_veto

_RESPONSE_MAP: Dict[Any, Callable[..., Any]] = {
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


def create_response(response_model: Any, messages: Optional[List[Dict[str, Any]]] = None, **kwargs: Any) -> Any:
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
        # Pass both context and messages if the handler accepts them
        if "context" in sig.parameters and "messages" in sig.parameters:
            result = handler(context=context, messages=messages)
        elif "context" in sig.parameters:
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
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=f"[MOCK LLM] OK - {context_echo}"))])
    )
