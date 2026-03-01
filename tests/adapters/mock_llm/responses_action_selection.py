# Protocol-facing mock responses for ActionSelectionDMAResult and related types
import json
from typing import Any, Dict, List, Optional

from ciris_engine.schemas.actions.parameters import (
    DeferParams,
    ForgetParams,
    MemorizeParams,
    ObserveParams,
    PonderParams,
    RecallParams,
    RejectParams,
    SpeakParams,
    ToolParams,
)
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType


def action_selection(
    context: Optional[List[str]] = None, messages: Optional[List[Dict[str, Any]]] = None
) -> ActionSelectionDMAResult:
    """Mock ActionSelectionDMAResult with passing values and protocol-compliant types."""
    context = context or []
    messages = messages or []

    # Check if this is a follow-up thought FIRST
    if "is_followup_thought" in context:
        # Follow-up thought - always TASK_COMPLETE
        action = HandlerActionType.TASK_COMPLETE
        params: Dict[str, Any] = {}
        rationale = "Completing follow-up thought (detected via is_followup_thought)"

        result = ActionSelectionDMAResult(
            selected_action=action, action_parameters=params, rationale=rationale  # type: ignore
        )
        object.__setattr__(result, "choices", [result])
        object.__setattr__(result, "finish_reason", "stop")
        object.__setattr__(result, "_raw_response", "mock")
        return result

    # Debug context parsing (disabled for less verbose output)
    # print(f"[ACTION_SELECTION_DEBUG] Context: {context}")

    # Extract messages from context if available
    messages_extracted: List[Dict[str, Any]] = []
    for item in context:
        if item.startswith("__messages__:"):
            try:
                messages_extracted = json.loads(item.split(":", 1)[1])
            except (json.JSONDecodeError, ValueError):
                pass
            break

    # Extract channel from context - check multiple patterns
    channel_id = "cli"  # Default to cli instead of test
    for item in context:
        # Check for echo_channel pattern from responses.py
        if item.startswith("echo_channel:"):
            channel_id = item.split(":", 1)[1].strip()
            break
        # Check for channel_id pattern
        elif item.startswith("channel_id:"):
            channel_id = item.split(":", 1)[1].strip()
            break
        # Check for channel context patterns
        elif "channel" in str(item).lower():
            # Try to extract channel ID from various formats
            import re

            channel_match = re.search(r'channel[_\s]*(?:id)?[:\s]*[\'"]?([^\'",\s]+)[\'"]?', str(item), re.IGNORECASE)
            if channel_match:
                channel_id = channel_match.group(1)
                break

    # Extract user input
    user_input = ""
    for item in context:
        if item.startswith("user_input:") or item.startswith("task:") or item.startswith("content:"):
            user_input = item.split(":", 1)[1].strip()
            break

    # Extract user speech (non-command input)
    user_speech = ""
    if user_input and not user_input.startswith("$"):
        user_speech = user_input

    # Check for forced actions (testing)
    forced_action = None
    action_params = ""
    for item in context:
        if item.startswith("forced_action:"):
            forced_action = item.split(":", 1)[1]
        elif item.startswith("action_params:"):
            action_params = item.split(":", 1)[1]

    # Check for custom rationale
    custom_rationale = None
    for item in context:
        if item.startswith("custom_rationale:"):
            custom_rationale = item.split(":", 1)[1]
            break

    # Check for help request
    show_help = False
    for item in context:
        if item == "show_help_requested":
            show_help = True
            break

    # Determine action based on context
    action: HandlerActionType
    params: Any
    rationale: str

    if forced_action:
        try:
            action = getattr(HandlerActionType, forced_action.upper())

            # Parse parameters based on action type
            if action == HandlerActionType.SPEAK:
                if action_params:
                    # Check if user wants to display context
                    if action_params.strip() == "$context":
                        # Display the full context
                        context_display = "📋 **Full Context Display**\n\n"
                        context_display += "**Extracted Context Items:**\n"
                        for item in context:
                            context_display += f"• {item}\n"

                        # Get the original messages if available
                        context_display += "\n**Original Messages:**\n"
                        for i, msg in enumerate(messages_extracted if messages_extracted else messages or []):
                            role = msg.get("role", "unknown")
                            content = msg.get("content", "")
                            context_display += f"\n[{i}] {role}:\n{content}\n"

                        params = SpeakParams(content=context_display)
                    else:
                        params = SpeakParams(content=action_params)
                else:
                    # Provide helpful error with valid format
                    error_msg = "❌ $speak requires content. Format: $speak <message>\nExample: $speak Hello world!\nSpecial: $speak $context (displays full context)"
                    params = SpeakParams(content=error_msg)

            elif action == HandlerActionType.MEMORIZE:
                if action_params:
                    # Try to parse node info from params
                    parts = action_params.split()
                    if len(parts) >= 1:
                        node_id = parts[0]
                        node_type = parts[1] if len(parts) > 1 else "CONCEPT"
                        scope = parts[2] if len(parts) > 2 else "LOCAL"

                        # Validate and provide tooltips
                        valid_types = ["AGENT", "USER", "CHANNEL", "CONCEPT", "CONFIG"]
                        valid_scopes = ["LOCAL", "IDENTITY", "ENVIRONMENT", "COMMUNITY", "NETWORK"]

                        if node_type.upper() not in valid_types:
                            error_msg = f"❌ Invalid node type '{node_type}'. Valid types: {', '.join(valid_types)}"
                            params = SpeakParams(content=error_msg)
                            action = HandlerActionType.SPEAK
                        elif scope.upper() not in valid_scopes:
                            error_msg = f"❌ Invalid scope '{scope}'. Valid scopes: {', '.join(valid_scopes)}"
                            params = SpeakParams(content=error_msg)
                            action = HandlerActionType.SPEAK
                        else:
                            params = MemorizeParams(
                                node=GraphNode(
                                    id=node_id,
                                    type=getattr(NodeType, node_type.upper()),
                                    scope=getattr(GraphScope, scope.upper()),
                                    data={},  # type: ignore
                                    metadata={},  # type: ignore
                                )
                            )
                    else:
                        error_msg = "❌ $memorize requires: <node_id> [type] [scope]\nExample: $memorize user123 USER LOCAL\nTypes: AGENT, USER, CHANNEL, CONCEPT, CONFIG\nScopes: LOCAL, IDENTITY, ENVIRONMENT, COMMUNITY, NETWORK"
                        params = SpeakParams(content=error_msg)
                        action = HandlerActionType.SPEAK
                else:
                    error_msg = "❌ $memorize requires: <node_id> [type] [scope]\nExample: $memorize concept/weather CONCEPT LOCAL"
                    params = SpeakParams(content=error_msg)
                    action = HandlerActionType.SPEAK

            elif action == HandlerActionType.RECALL:
                if action_params:
                    # Similar parsing as memorize
                    parts = action_params.split()
                    node_id = parts[0]
                    node_type = parts[1] if len(parts) > 1 else "CONCEPT"
                    scope = parts[2] if len(parts) > 2 else "LOCAL"
                    params = RecallParams(
                        node=GraphNode(
                            id=node_id,
                            type=getattr(NodeType, node_type.upper(), NodeType.CONCEPT),
                            scope=getattr(GraphScope, scope.upper(), GraphScope.LOCAL),
                            data={},  # type: ignore
                            metadata={},  # type: ignore
                        )
                    )
                else:
                    error_msg = "❌ $recall requires: <node_id> [type] [scope]\nExample: $recall user123 USER LOCAL"
                    params = SpeakParams(content=error_msg)
                    action = HandlerActionType.SPEAK

            elif action == HandlerActionType.PONDER:
                if action_params:
                    # Split by semicolon for multiple questions
                    questions = [q.strip() for q in action_params.split(";") if q.strip()]
                    params = PonderParams(questions=questions)
                else:
                    error_msg = "❌ $ponder requires questions. Format: $ponder <question1>; <question2>\nExample: $ponder What should I do next?; How can I help?"
                    params = SpeakParams(content=error_msg)
                    action = HandlerActionType.SPEAK

            elif action == HandlerActionType.OBSERVE:
                parts = action_params.split() if action_params else []
                channel_id = parts[0] if len(parts) > 0 else None
                active = parts[1].lower() == "true" if len(parts) > 1 else False
                params = ObserveParams(channel_id=channel_id, active=active)

            elif action == HandlerActionType.TOOL:
                if action_params:
                    parts = action_params.split(None, 1)
                    tool_name = parts[0]
                    tool_params: Dict[str, Any] = {}

                    # Parse JSON-like parameters if provided
                    if len(parts) > 1:
                        try:
                            tool_params = json.loads(parts[1])
                        except (json.JSONDecodeError, ValueError):
                            # Try simple key=value parsing
                            for pair in parts[1].split():
                                if "=" in pair:
                                    k, v = pair.split("=", 1)
                                    tool_params[k] = v

                    params = ToolParams(name=tool_name, parameters=tool_params)
                else:
                    error_msg = "❌ $tool requires: <tool_name> [parameters]\nExample: $tool discord_delete_message channel_id=123 message_id=456\nAvailable tools: discord_delete_message, discord_timeout_user, list_files, read_file, etc."
                    params = SpeakParams(content=error_msg)
                    action = HandlerActionType.SPEAK

            elif action == HandlerActionType.REJECT:
                if action_params:
                    params = RejectParams(reason=action_params)
                else:
                    error_msg = "❌ $reject requires a reason. Format: $reject <reason>\nExample: $reject This request violates ethical guidelines"
                    params = SpeakParams(content=error_msg)
                    action = HandlerActionType.SPEAK

            elif action == HandlerActionType.DEFER:
                if action_params:
                    params = DeferParams(reason=action_params, defer_until=None)
                else:
                    error_msg = "❌ $defer requires a reason. Format: $defer <reason>\nExample: $defer I need more context to answer properly"
                    params = SpeakParams(content=error_msg)
                    action = HandlerActionType.SPEAK

            elif action == HandlerActionType.FORGET:
                if action_params:
                    parts = action_params.split(None, 1)
                    if len(parts) >= 2:
                        node_id = parts[0]
                        reason = parts[1]
                        params = ForgetParams(
                            node=GraphNode(
                                id=node_id,
                                type=NodeType.CONCEPT,
                                scope=GraphScope.LOCAL,
                                data={},  # type: ignore
                                metadata={},  # type: ignore
                            ),
                            reason=reason,
                        )
                    else:
                        error_msg = "❌ $forget requires: <node_id> <reason>\nExample: $forget user123 User requested data deletion"
                        params = SpeakParams(content=error_msg)
                        action = HandlerActionType.SPEAK
                else:
                    error_msg = "❌ $forget requires: <node_id> <reason>"
                    params = SpeakParams(content=error_msg)
                    action = HandlerActionType.SPEAK

            elif action == HandlerActionType.TASK_COMPLETE:
                # No parameters needed
                params = {}

            else:
                # Unknown action
                params = SpeakParams(content=f"Unknown action: {forced_action}")

        except AttributeError:
            # Invalid action type
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
            error_msg = f"❌ Invalid action '{forced_action}'. Valid actions: {', '.join(valid_actions)}"
            action = HandlerActionType.SPEAK
            params = SpeakParams(content=error_msg)

        # Include context pattern in rationale
        context_patterns = [item for item in context if item.startswith("forced_action:")]
        context_info = f" {context_patterns[0]}" if context_patterns else ""
        rationale = f"Executing {forced_action} action from mock command{context_info}"

    elif show_help:
        action = HandlerActionType.SPEAK
        help_text = """📋 CIRIS Mock LLM Commands Help

🎛️ **Action Commands:**
• $speak <message>                - Send a message
• $recall <node_id> [type] [scope] - Recall from memory
• $memorize <node_id> [type] [scope] - Store in memory
• $tool <name> [params]           - Execute a tool
• $observe [channel_id] [active]  - Observe a channel
• $ponder <q1>; <q2>             - Ask questions
• $defer <reason>                 - Defer the task
• $reject <reason>                - Reject the request
• $forget <node_id> <reason>      - Forget memory
• $task_complete                  - Complete current task

🔧 **Testing & Debug Commands:**
• $test                          - Enable testing mode
• $error                         - Inject error conditions
• $rationale "custom text"       - Set custom rationale
• $context                       - Show full context
• $filter "regex"                - Filter context display
• $debug_dma                     - Show DMA details
• $debug_guardrails              - Show guardrail details
• $help                          - Show this help

📝 **Parameter Formats:**
• NodeType: AGENT, USER, CHANNEL, CONCEPT, CONFIG
• GraphScope: LOCAL, IDENTITY, ENVIRONMENT, COMMUNITY, NETWORK
• Tools: discord_delete_message, list_files, read_file, etc.

💡 **Examples:**
• $speak Hello world!
• $recall user123 USER LOCAL
• $tool read_file path=/tmp/test.txt
• $defer Need more information
• $ponder What should I do?; Is this ethical?

The mock LLM provides deterministic responses for testing CIRIS functionality offline."""
        params = SpeakParams(content=help_text)
        rationale = "Providing Mock LLM help documentation"

    # Removed the weird ? recall command - only $recall is supported

    elif user_speech:
        # Regular user input - always speak
        action = HandlerActionType.SPEAK
        params = SpeakParams(content=f"Mock response to: {user_speech}")
        rationale = f"Responding to user: {user_speech}"

    else:
        # Check if this is a follow-up thought by looking at the THOUGHT_TYPE in the system message
        is_followup = False

        # The first message should be the system message with accord
        messages_to_check = messages_extracted if messages_extracted else messages or []
        if messages_to_check and len(messages_to_check) > 0:
            first_msg = messages_to_check[0]
            if isinstance(first_msg, dict) and first_msg.get("role") == "system":
                msg_content = first_msg.get("content", "")
                # Check if this is a follow_up thought type
                if msg_content.startswith("THOUGHT_TYPE=follow_up"):
                    is_followup = True

        if is_followup:
            # Follow-up thought → TASK_COMPLETE
            action = HandlerActionType.TASK_COMPLETE
            params = {}  # TASK_COMPLETE doesn't need params
            rationale = "Completing follow-up thought"
        else:
            # Default: new task → SPEAK
            action = HandlerActionType.SPEAK
            params = SpeakParams(content="Hello! How can I help you?")
            rationale = "Default speak action for new task"

    # Use custom rationale if provided, otherwise use the generated rationale
    final_rationale = custom_rationale if custom_rationale else rationale

    result = ActionSelectionDMAResult(
        selected_action=action, action_parameters=params, rationale=final_rationale  # type: ignore
    )
    object.__setattr__(result, "choices", [result])
    object.__setattr__(result, "finish_reason", "stop")
    object.__setattr__(result, "_raw_response", "mock")
    return result
