import re
from typing import Any, Dict, List, Optional, Union

from ciris_engine.schemas.actions import (
    DeferParams,
    ForgetParams,
    MemorizeParams,
    ObserveParams,
    PonderParams,
    RecallParams,
    RejectParams,
    SpeakParams,
    TaskCompleteParams,
    ToolParams,
)
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult

# Union type for all action parameters - 100% schema compliant
ActionParams = Union[
    SpeakParams,
    MemorizeParams,
    RecallParams,
    PonderParams,
    ObserveParams,
    ToolParams,
    RejectParams,
    DeferParams,
    ForgetParams,
    TaskCompleteParams,
]
from typing import Union

from ciris_engine.logic.utils.channel_utils import create_channel_context
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.services.graph_core import GraphNode, GraphNodeAttributes, GraphScope, NodeType


def action_selection(
    context: Optional[List[Any]] = None, messages: Optional[List[Dict[str, Any]]] = None
) -> ActionSelectionDMAResult:
    """Mock ActionSelectionDMAResult with passing values and protocol-compliant types."""
    context = context or []
    messages = messages or []

    # Debug context parsing
    import logging

    logger = logging.getLogger(__name__)

    # === CRITICAL: Early follow-up detection ===
    # Check the FIRST system message for THOUGHT_TYPE=follow_up
    # This MUST happen before any other logic to ensure follow-ups are detected
    is_followup_thought = False
    if messages and len(messages) > 0:
        first_msg = messages[0]
        if isinstance(first_msg, dict) and first_msg.get("role") == "system":
            content = first_msg.get("content", "")
            # Log what we're checking (INFO level for visibility)
            logger.info(f"[MOCK_LLM] FIRST SYSTEM MESSAGE (first 100 chars): {content[:100] if content else 'EMPTY'}")
            if content.startswith("THOUGHT_TYPE=follow_up"):
                is_followup_thought = True
                logger.info("[MOCK_LLM] *** DETECTED FOLLOW-UP THOUGHT *** via THOUGHT_TYPE=follow_up in first message")
            elif "THOUGHT_TYPE=" in content:
                # Log what type it actually is
                thought_type_match = content.split("\n")[0] if content else ""
                logger.info(f"[MOCK_LLM] Found different thought type: {thought_type_match}")
            else:
                logger.info("[MOCK_LLM] No THOUGHT_TYPE found in first system message")
    else:
        logger.info("[MOCK_LLM] WARNING: No messages passed to action_selection!")

    logger.debug(f"[MOCK_LLM] Context items: {len(context)}")
    logger.debug(f"[MOCK_LLM] Messages count: {len(messages)}")
    if messages:
        for i, msg in enumerate(messages[:3]):  # First 3 messages
            role = msg.get("role", "unknown") if isinstance(msg, dict) else "not-dict"
            content_preview = str(msg.get("content", ""))[:100] if isinstance(msg, dict) else str(msg)[:100]
            logger.debug(f"[MOCK_LLM] Message {i}: role={role}, content={content_preview}...")

    # If messages not provided, try to extract from context for backwards compatibility
    if not messages:
        for item in context:
            if item.startswith("__messages__:"):
                import json

                try:
                    messages = json.loads(item.split(":", 1)[1])
                except json.JSONDecodeError:
                    pass
                break

    # The mock LLM no longer extracts or sets channel for SPEAK actions
    # It will only use channel_context when explicitly told via @channel: syntax
    logger.info("[MOCK_LLM] Not extracting channel from context - will use task context unless @channel: is specified")

    # Default channel for non-SPEAK actions that need a channel
    default_channel = "cli"

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

    # If user_input is a command, handle it directly
    command_from_context = None
    command_args_from_context = ""
    if user_input and user_input.startswith("$"):
        # Parse the command from user_input
        parts = user_input.split(None, 1)
        command_from_context = parts[0].lower()
        command_args_from_context = parts[1] if len(parts) > 1 else ""

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

    # Initialize rationale with default - should be overridden by specific logic paths
    rationale = "[MOCK LLM] Action selection (no specific rationale provided)"

    # Check for help request
    show_help = False
    for item in context:
        if item == "show_help_requested":
            show_help = True
            break

    # Determine action based on context
    # Initialize params with proper type annotation for 100% schema compliance
    params: ActionParams

    # Check for multimodal content in context
    multimodal_image_count = 0
    for item in context:
        if item.startswith("multimodal_images:"):
            try:
                multimodal_image_count = int(item.split(":", 1)[1])
            except ValueError:
                pass
            break

    # Debug logging
    logger.info(
        f"[MOCK_LLM] Action selection - forced_action: {forced_action}, user_speech: {user_speech}, command_from_context: {command_from_context}, is_followup_thought: {is_followup_thought}, multimodal_images: {multimodal_image_count}"
    )

    # === EARLY EXIT FOR FOLLOW-UP THOUGHTS ===
    # If this is a follow-up thought (detected via THOUGHT_TYPE=follow_up), complete the task
    # This check MUST come before other logic to prevent follow-ups from looping
    if is_followup_thought and not forced_action and not command_from_context:
        logger.info("[MOCK_LLM] *** EARLY EXIT: Follow-up thought detected, returning TASK_COMPLETE ***")
        action = HandlerActionType.TASK_COMPLETE
        params = TaskCompleteParams(completion_reason="[MOCK LLM] Follow-up thought completed - task finished")
        rationale = "[MOCK LLM] Completing follow-up thought (detected via THOUGHT_TYPE=follow_up)"
        return ActionSelectionDMAResult(
            selected_action=action,
            action_parameters=params.model_dump(),
            rationale=rationale,
        )

    if forced_action:
        try:
            action = getattr(HandlerActionType, forced_action.upper())

            # Parse parameters based on action type
            if action == HandlerActionType.SPEAK:
                if action_params:
                    # Check if user wants to display context
                    if action_params.strip() == "$context":
                        # Display the full context
                        import json

                        context_display = "📋 **Full Context Display**\n\n"
                        context_display += "**Extracted Context Items:**\n"
                        for item in context:
                            context_display += f"• {item}\n"

                        # Get the original messages if available
                        context_display += "\n**Original Messages:**\n"
                        for i, msg in enumerate(messages or []):
                            role = msg.get("role", "unknown")
                            content = msg.get("content", "")
                            context_display += f"\n[{i}] {role}:\n{content}\n"

                        params = SpeakParams(content=context_display)
                    else:
                        # Check for @channel: syntax in forced action params
                        speak_content = action_params
                        speak_channel = default_channel

                        # re already imported at top of file
                        channel_match = re.search(r"@channel:(\S+)", action_params)
                        if channel_match:
                            speak_channel = channel_match.group(1)
                            # Remove the @channel: part from the content
                            speak_content = action_params.replace(channel_match.group(0), "").strip()
                            if not speak_content:
                                speak_content = "[MOCK LLM] Cross-channel message"
                            logger.info(
                                f"[MOCK_LLM] Parsed channel from @channel: syntax in forced action - channel: {speak_channel}, content: {speak_content[:50]}"
                            )

                        # Only set channel_context if @channel: was explicitly used
                        if channel_match:
                            params = SpeakParams(
                                content=speak_content, channel_context=create_channel_context(speak_channel)
                            )
                            logger.info(
                                f"[MOCK_LLM] Created SpeakParams with channel_context for channel: {speak_channel}"
                            )
                        else:
                            params = SpeakParams(content=speak_content)
                            logger.info(
                                "[MOCK_LLM] Created SpeakParams without channel_context - will use task context"
                            )
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
                                    attributes={"created_by": "mock_llm"},
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
                    # Parse recall parameters - can be a query string or node ID
                    parts = action_params.split()
                    if len(parts) == 1:
                        # Single parameter - treat as query
                        params = RecallParams(query=action_params, limit=10)
                    else:
                        # Multiple parameters - parse as node_id, type, scope
                        node_id = parts[0]
                        recall_type: str = parts[1] if len(parts) > 1 else "general"
                        scope_str = parts[2] if len(parts) > 2 else None

                        params = RecallParams(
                            node_id=node_id,
                            node_type=recall_type,
                            scope=getattr(GraphScope, scope_str.upper()) if scope_str else None,
                            limit=10,
                        )
                else:
                    error_msg = "❌ $recall requires either a query or node_id\nExamples:\n$recall memories\n$recall user123 USER LOCAL"
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
                observe_channel = parts[0] if len(parts) > 0 else ""
                # Always active - agent should always create follow-up thoughts
                channel_context = create_channel_context(observe_channel) if observe_channel else None
                params = ObserveParams(channel_context=channel_context, active=True)

            elif action == HandlerActionType.TOOL:
                if action_params:
                    logger.info(f"[MOCK_LLM] TOOL handler - action_params: '{action_params}'")
                    parts = action_params.split(None, 1)
                    tool_name = parts[0]
                    tool_params = {}

                    # Parse JSON-like parameters if provided
                    if len(parts) > 1:
                        logger.info(f"[MOCK_LLM] TOOL handler - parsing params: '{parts[1]}'")
                        try:
                            import json

                            tool_params = json.loads(parts[1])
                            logger.info(f"[MOCK_LLM] TOOL handler - parsed as JSON: {tool_params}")
                        except json.JSONDecodeError:
                            # Special handling for curl tool - expects 'url' parameter
                            if tool_name == "curl":
                                tool_params = {"url": parts[1].strip()}
                                logger.info(f"[MOCK_LLM] TOOL handler - curl with URL: {tool_params}")
                            else:
                                # Try simple key=value parsing with quote handling
                                # First clean up the parameters string by removing escaped newlines
                                params_str = parts[1].split("\\n")[0].strip()
                                import shlex

                                try:
                                    # Use shlex to properly handle quoted strings
                                    tokens = shlex.split(params_str)
                                    for token in tokens:
                                        if "=" in token:
                                            k, v = token.split("=", 1)
                                            tool_params[k] = v
                                    logger.info(f"[MOCK_LLM] TOOL handler - parsed with shlex: {tool_params}")
                                except ValueError as e:
                                    # Fallback to simple parsing if shlex fails
                                    logger.info(f"[MOCK_LLM] TOOL handler - shlex failed ({e}), using fallback")
                                    for pair in params_str.split():
                                        if "=" in pair:
                                            k, v = pair.split("=", 1)
                                            # Clean up the value
                                            v = v.strip().rstrip("\\").strip('"')
                                            tool_params[k] = v
                                    logger.info(f"[MOCK_LLM] TOOL handler - parsed as key=value: {tool_params}")
                    else:
                        logger.info("[MOCK_LLM] TOOL handler - no parameters provided")

                    logger.info(f"[MOCK_LLM] TOOL handler - final params: name='{tool_name}', parameters={tool_params}")
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
                                attributes={"created_by": "mock_llm"},
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
                # Mission-critical schema compliance with proper TaskCompleteParams
                params = TaskCompleteParams(completion_reason="Forced task completion via testing")

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
        rationale = f"[MOCK LLM] Executing {forced_action} action from mock command{context_info}"

    if show_help:  # Changed from elif to if to handle help from anywhere
        action = HandlerActionType.SPEAK
        help_text = """📋 CIRIS Mock LLM Commands Help

🎛️ **Action Commands:**
• $speak <message>                - Send a message to current channel
• $speak @channel:<id> <message>  - Send message to specific channel
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
• $debug_consciences              - Show conscience details
• $help                          - Show this help

📝 **Parameter Formats:**
• NodeType: AGENT, USER, CHANNEL, CONCEPT, CONFIG
• GraphScope: LOCAL, IDENTITY, ENVIRONMENT, COMMUNITY, NETWORK
• Tools: discord_delete_message, list_files, read_file, etc.

💡 **Examples:**
• $speak Hello world!
• $speak @channel:api_0.0.0.0_8080 Cross-adapter message!
• $recall user123 USER LOCAL
• $tool read_file path=/tmp/test.txt
• $defer Need more information
• $ponder What should I do?; Is this ethical?

The mock LLM provides deterministic responses for testing CIRIS functionality offline."""
        params = SpeakParams(content=help_text)
        rationale = "[MOCK LLM] Providing Mock LLM help documentation"

    # Removed the weird ? recall command - only $recall is supported

    elif user_speech:
        # Regular user input - always speak
        action = HandlerActionType.SPEAK
        # Include multimodal detection info if images were present
        if multimodal_image_count > 0:
            speak_content = f"[MOCKLLM DISCLAIMER] SPEAK IN RESPONSE TO TASK WITHOUT COMMAND [MULTIMODAL_DETECTED:{multimodal_image_count}]"
        else:
            speak_content = "[MOCKLLM DISCLAIMER] SPEAK IN RESPONSE TO TASK WITHOUT COMMAND"
        params = SpeakParams(content=speak_content)
        rationale = f"Responding to user: {user_speech}"

    elif command_from_context:
        # Handle command extracted from context (e.g., from Original Thought)
        command_found = False

        # Handle specific commands
        if command_from_context == "$ponder":
            questions = command_args_from_context.split(";") if command_args_from_context else ["What should I do?"]
            params = PonderParams(questions=[q.strip() for q in questions if q.strip()])
            action = HandlerActionType.PONDER
            rationale = "[MOCK LLM] Pondering questions from context"
            command_found = True
        elif command_from_context == "$speak":
            # Parse for @channel:default_channel syntax anywhere in the message
            channel_match = re.search(r"@channel:(\S+)", command_args_from_context)
            if channel_match:
                speak_channel = channel_match.group(1)
                # Channel override removed - mock LLM doesn't set channels
                # Remove the @channel: part from the content
                speak_content = command_args_from_context.replace(channel_match.group(0), "").strip()
                if not speak_content:
                    speak_content = "[MOCK LLM] Cross-channel message"
                logger.info(
                    f"[MOCK_LLM] Parsed channel from @channel: syntax - channel: {speak_channel}, content: {speak_content[:50]}"
                )
            else:
                speak_content = command_args_from_context if command_args_from_context else "[MOCK LLM] Hello!"
                speak_channel = default_channel

            # Only set channel_context if @channel: was explicitly used
            if channel_match:
                params = SpeakParams(content=speak_content, channel_context=create_channel_context(speak_channel))
            else:
                params = SpeakParams(content=speak_content)
            action = HandlerActionType.SPEAK
            rationale = "[MOCK LLM] Speaking from context command"
            command_found = True
        elif command_from_context == "$recall":
            query = command_args_from_context if command_args_from_context else "memories"
            params = RecallParams(query=query, node_type=NodeType.CONCEPT, scope=GraphScope.LOCAL, limit=5)
            action = HandlerActionType.RECALL
            rationale = f"[MOCK LLM] Recalling memories about: {query}"
            command_found = True
        elif command_from_context == "$memorize":
            content = command_args_from_context if command_args_from_context else "Empty memory"
            node_id = "_".join(content.split()[:3]).lower().replace(",", "").replace(".", "")
            if not node_id:
                node_id = "memory_node"

            params = MemorizeParams(
                node=GraphNode(
                    id=node_id,
                    type=NodeType.CONCEPT,
                    scope=GraphScope.LOCAL,
                    attributes={"created_by": "mock_llm", "tags": [f"content:{content[:50]}", "source:mock_llm"]},
                )
            )
            action = HandlerActionType.MEMORIZE
            rationale = f"[MOCK LLM] Memorizing: {content[:50]}..."
            command_found = True
        elif command_from_context == "$task_complete":
            params = TaskCompleteParams(completion_reason="[MOCK LLM] Task completed via context command")
            action = HandlerActionType.TASK_COMPLETE
            rationale = "[MOCK LLM] Completing task from context"
            command_found = True
        elif command_from_context == "$tool":
            # Parse tool command
            tool_name = "list_tools"  # default
            tool_params = {}
            if command_args_from_context:
                parts = command_args_from_context.split(None, 1)
                if parts:
                    tool_name = parts[0]
                    if len(parts) > 1:
                        # Parse parameters the same way as forced action
                        params_str = parts[1].split("\\n")[0].strip()
                        try:
                            import json

                            tool_params = json.loads(params_str)
                        except json.JSONDecodeError:
                            # Try simple key=value parsing with quote handling
                            import shlex

                            try:
                                # Use shlex to properly handle quoted strings
                                tokens = shlex.split(params_str)
                                for token in tokens:
                                    if "=" in token:
                                        k, v = token.split("=", 1)
                                        tool_params[k] = v
                            except ValueError:
                                # Fallback to simple parsing if shlex fails
                                for pair in params_str.split():
                                    if "=" in pair:
                                        k, v = pair.split("=", 1)
                                        # Clean up the value
                                        v = v.strip().rstrip("\\").strip('"')
                                        tool_params[k] = v

            params = ToolParams(name=tool_name, parameters=tool_params)
            action = HandlerActionType.TOOL
            rationale = f"[MOCK LLM] Executing tool: {tool_name}"
            command_found = True
        elif command_from_context == "$observe":
            # Parse observe command - expects a default_channel
            args = command_args_from_context.strip().split() if command_args_from_context else []
            obs_channel = args[0] if args else default_channel
            # Always active - agent should always create follow-up thoughts
            params = ObserveParams(
                channel_context=create_channel_context(obs_channel),
                active=True,
                context={"observer_channel": default_channel, "target_channel": obs_channel},
            )
            action = HandlerActionType.OBSERVE
            rationale = f"[MOCK LLM] Observing channel: {obs_channel}"
            command_found = True
        elif command_from_context == "$defer":
            reason = command_args_from_context or "Need more information"
            params = DeferParams(reason=reason, context={"channel": default_channel} if default_channel else None)
            action = HandlerActionType.DEFER
            rationale = f"[MOCK LLM] Deferring: {reason}"
            command_found = True
        elif command_from_context == "$reject":
            reason = command_args_from_context or "Cannot process request"
            params = RejectParams(reason=reason, create_filter=False)
            action = HandlerActionType.REJECT
            rationale = f"[MOCK LLM] Rejecting: {reason}"
            command_found = True
        elif command_from_context == "$forget":
            # Parse forget command - expects: <node_id> <reason>
            parts = command_args_from_context.split(None, 1) if command_args_from_context else []
            if len(parts) >= 1:
                node_id = parts[0]
                reason = parts[1] if len(parts) >= 2 else "User requested deletion"
                # Create a GraphNode for the forget action
                params = ForgetParams(
                    node=GraphNode(
                        id=node_id,
                        type=NodeType.CONCEPT,  # Default type for forget
                        scope=GraphScope.LOCAL,
                        attributes={"created_by": "mock_llm"},
                    ),
                    reason=reason,
                )
                action = HandlerActionType.FORGET
                rationale = f"[MOCK LLM] Forgetting memory: {node_id}"
                command_found = True
            else:
                # Error case - no parameters provided
                action = HandlerActionType.SPEAK
                params = SpeakParams(
                    content="❌ $forget requires: <node_id> <reason>\nExample: $forget user123 User requested data deletion"
                )
                rationale = "[MOCK LLM] Invalid forget command"
                command_found = True

        if not command_found:
            # Unknown command, default to speak
            action = HandlerActionType.SPEAK
            params = SpeakParams(content=f"[MOCK LLM] Unknown command from context: {command_from_context}")
            rationale = "[MOCK LLM] Unknown command from context"

    else:
        # Step 1: Check if this is a follow-up thought by looking at the THOUGHT_TYPE in the system message
        is_followup = False

        # The first message should be the system message with covenant
        if messages and len(messages) > 0:
            first_msg = messages[0]
            if isinstance(first_msg, dict) and first_msg.get("role") == "system":
                content = first_msg.get("content", "")
                logger.info(f"[MOCK_LLM] First system message starts with: {content[:80] if content else 'EMPTY'}...")
                # Check if this is a follow_up thought type
                if content.startswith("THOUGHT_TYPE=follow_up"):
                    is_followup = True
                    logger.info("[MOCK_LLM] DETECTED FOLLOW-UP THOUGHT via THOUGHT_TYPE=follow_up")
        else:
            logger.info("[MOCK_LLM] No messages available for THOUGHT_TYPE check")

        if is_followup:
            # Check the content of the follow-up thought to determine if it's from a SPEAK handler
            # Extract the thought content from the user message
            thought_content = ""
            for msg in messages or []:
                if isinstance(msg, dict) and msg.get("role") == "user":
                    user_content = msg.get("content", "")
                    # Look for "Original Thought:" pattern
                    if "Original Thought:" in user_content:
                        # Handle nested quotes by looking for the content between the first and last quotes
                        # or use a more robust pattern that captures everything until the next field
                        thought_match = re.search(r'Original Thought:\s*"(.*?)"(?:\n|$)', user_content, re.DOTALL)
                        if thought_match:
                            thought_content = thought_match.group(1)
                            break

            # Check if this is a follow-up from SPEAK handler (usually contains specific patterns)
            # Most follow-ups from other handlers contain operation results that should be spoken
            is_speak_followup = any(
                pattern in thought_content
                for pattern in [
                    "Message sent successfully to channel",
                    "CIRIS_FOLLOW_UP_THOUGHT: Message sent successfully to channel",
                    "NEXT ACTION IS ALMOST CERTAINLY TASK COMPLETE",
                    "spoke in channel",
                    "message delivered",
                    "response sent",
                ]
            )

            if is_speak_followup:
                # Follow-up from SPEAK handler → TASK_COMPLETE
                action = HandlerActionType.TASK_COMPLETE
                params = TaskCompleteParams(completion_reason="[MOCK LLM] SPEAK operation completed")
                rationale = "[MOCK LLM] Completing SPEAK follow-up thought"
            else:
                # Follow-up from other handlers (RECALL, MEMORIZE, etc.) → SPEAK the result
                action = HandlerActionType.SPEAK
                # Extract the actual content to speak from the follow-up thought
                if thought_content.startswith("CIRIS_FOLLOW_UP_THOUGHT:"):
                    content_to_speak = thought_content.replace("CIRIS_FOLLOW_UP_THOUGHT:", "").strip()
                else:
                    content_to_speak = thought_content

                params = SpeakParams(content=f"[MOCK LLM] {content_to_speak}")
                rationale = "[MOCK LLM] Speaking operation result from follow-up thought"
        else:
            # Step 2: For initial thoughts, check USER message for commands
            command_found = False

            # Look for the user message in the messages list
            for msg in messages or []:
                if isinstance(msg, dict) and msg.get("role") == "user":
                    user_content = msg.get("content", "")

                    # Debug logging
                    logger.debug(f"[MOCK_LLM] Processing user message: {user_content[:200]}...")

                    # Try to extract the actual user input after various patterns:
                    # - "User @username said:" or "@username said:"
                    # - "@USERNAME (ID: USERNAME):" (API format)
                    # - Direct content without prefix
                    # re already imported at top of file

                    # First try API format: @USERNAME (ID: USERNAME): content
                    api_match = re.search(r"@\w+\s*\([^)]+\):\s*(.+)", user_content, re.IGNORECASE | re.DOTALL)
                    if api_match:
                        actual_user_input = api_match.group(1).strip()
                        logger.debug(f"[MOCK_LLM] Extracted via API pattern: {actual_user_input[:100]}")
                    else:
                        # Then try "User said:" or "@username said:" format
                        user_match = re.search(
                            r"(?:User|@\w+)\s+(?:said|says?):\s*(.+)", user_content, re.IGNORECASE | re.DOTALL
                        )
                        if user_match:
                            actual_user_input = user_match.group(1).strip()
                            logger.debug(f"[MOCK_LLM] Extracted via User said pattern: {actual_user_input[:100]}")
                        else:
                            # If no pattern matches, use the content as-is
                            actual_user_input = user_content.strip()
                            logger.debug(f"[MOCK_LLM] Using content as-is: {actual_user_input[:100]}")

                    # Check if it starts with a command
                    if actual_user_input.startswith("$"):
                        # Parse the command
                        parts = actual_user_input.split(None, 1)
                        command = parts[0].lower()
                        command_args = parts[1] if len(parts) > 1 else ""

                        # Handle specific commands
                        if command == "$speak":
                            action = HandlerActionType.SPEAK
                            logger.info(f"[MOCK_LLM] Processing $speak command with args: {command_args}")

                            # Check if channel is specified with @channel syntax
                            speak_channel = default_channel  # Default to current channel
                            speak_content = command_args if command_args else "[MOCK LLM] Hello!"

                            # Parse for @channel:default_channel syntax anywhere in the message
                            channel_match = re.search(r"@channel:(\S+)", command_args)
                            if channel_match:
                                speak_channel = channel_match.group(1)
                                # Channel override removed - mock LLM doesn't set channels
                                # Remove the @channel: part from the content
                                speak_content = command_args.replace(channel_match.group(0), "").strip()
                                if not speak_content:
                                    speak_content = "[MOCK LLM] Cross-channel message"
                                logger.info(
                                    f"[MOCK_LLM] Parsed channel from @channel: syntax - channel: {speak_channel}, content: {speak_content[:50]}"
                                )

                            # Only set channel_context if @channel: was explicitly used
                            if channel_match:
                                params = SpeakParams(
                                    content=speak_content, channel_context=create_channel_context(speak_channel)
                                )
                            else:
                                params = SpeakParams(content=speak_content)
                            rationale = f"[MOCK LLM] Speaking to channel {speak_channel}"
                            command_found = True
                            break
                        elif command == "$recall":
                            # Use query-based recall with the search term
                            query = command_args if command_args else "memories"

                            params = RecallParams(
                                query=query, node_type=NodeType.CONCEPT, scope=GraphScope.LOCAL, limit=5
                            )
                            action = HandlerActionType.RECALL
                            rationale = f"[MOCK LLM] Recalling memories about: {query}"
                            command_found = True
                            break
                        elif command == "$memorize":
                            # Treat the entire command_args as the content to memorize
                            content = command_args if command_args else "Empty memory"
                            # Create a node ID from the content (first few words)
                            node_id = "_".join(content.split()[:3]).lower().replace(",", "").replace(".", "")
                            if not node_id:
                                node_id = "memory_node"

                            params = MemorizeParams(
                                node=GraphNode(
                                    id=node_id,
                                    type=NodeType.CONCEPT,
                                    scope=GraphScope.LOCAL,
                                    attributes={
                                        "created_by": "mock_llm",
                                        "content": content,
                                        "description": f"Memory: {content}",
                                    },
                                )
                            )
                            action = HandlerActionType.MEMORIZE
                            rationale = f"[MOCK LLM] Memorizing: {content[:50]}..."
                            command_found = True
                            break
                        elif command == "$ponder":
                            questions = command_args.split(";") if command_args else ["What should I do?"]
                            params = PonderParams(questions=[q.strip() for q in questions if q.strip()])
                            action = HandlerActionType.PONDER
                            rationale = "[MOCK LLM] Pondering questions"
                            command_found = True
                            break
                        elif command == "$observe":
                            # Parse observe command - expects a default_channel
                            args = command_args.strip().split() if command_args else []
                            obs_channel = args[0] if args else default_channel
                            # Always active - agent should always create follow-up thoughts

                            params = ObserveParams(
                                channel_context=create_channel_context(obs_channel),
                                active=True,
                                context={"observer_channel": default_channel, "target_channel": obs_channel},
                            )
                            action = HandlerActionType.OBSERVE
                            rationale = f"[MOCK LLM] Observing channel: {obs_channel}"
                            command_found = True
                            break
                        elif command == "$tool":
                            tool_parts = command_args.split(None, 1)
                            tool_name = tool_parts[0] if tool_parts else "unknown_tool"
                            tool_params = {}

                            if len(tool_parts) > 1:
                                # Try to parse JSON params
                                try:
                                    import json

                                    tool_params = json.loads(tool_parts[1])
                                except json.JSONDecodeError:
                                    # Simple key=value parsing
                                    for pair in tool_parts[1].split():
                                        if "=" in pair:
                                            k, v = pair.split("=", 1)
                                            tool_params[k] = v

                            params = ToolParams(name=tool_name, parameters=tool_params)
                            action = HandlerActionType.TOOL
                            rationale = f"[MOCK LLM] Executing tool {tool_name}"
                            command_found = True
                            break
                        elif command == "$defer":
                            params = DeferParams(
                                reason=command_args if command_args else "Need more information", defer_until=None
                            )
                            action = HandlerActionType.DEFER
                            rationale = "[MOCK LLM] Deferring task"
                            command_found = True
                            break
                        elif command == "$reject":
                            params = RejectParams(reason=command_args if command_args else "Cannot fulfill request")
                            action = HandlerActionType.REJECT
                            rationale = "[MOCK LLM] Rejecting request"
                            command_found = True
                            break
                        elif command == "$forget":
                            # Parse forget - can be either node_id or search term
                            if command_args:
                                # Try to match the node ID format we create in memorize
                                search_term = command_args.strip()
                                # Create the same node ID format as memorize
                                node_id = "_".join(search_term.split()[:3]).lower().replace(",", "").replace(".", "")
                                if not node_id:
                                    node_id = search_term.split()[0] if search_term else "unknown"
                            else:
                                node_id = "unknown_node"
                                search_term = "unknown"

                            params = ForgetParams(
                                node=GraphNode(
                                    id=node_id,
                                    type=NodeType.CONCEPT,
                                    scope=GraphScope.LOCAL,
                                    attributes={"created_by": "mock_llm"},
                                ),
                                reason=f"Forgetting memory about: {search_term}",
                            )
                            action = HandlerActionType.FORGET
                            rationale = f"[MOCK LLM] Forgetting memory: {search_term[:50]}..."
                            command_found = True
                            break
                        elif command == "$task_complete":
                            params = TaskCompleteParams(completion_reason="[MOCK LLM] Task completed via command")
                            action = HandlerActionType.TASK_COMPLETE
                            rationale = "[MOCK LLM] Completing task"
                            command_found = True
                            break
                        elif command == "$help":
                            # Show help
                            show_help = True
                            break

            if show_help:
                # Return to the help handler below
                pass
            elif not command_found:
                # Step 3: Check conversation history in the user message for commands
                # This handles cases where commands come through API in conversation history
                for msg in messages or []:
                    if isinstance(msg, dict) and msg.get("role") == "user":
                        user_content = msg.get("content", "")

                        # Look for conversation history pattern
                        if "=== CONVERSATION HISTORY" in user_content:
                            # Extract lines that look like user messages
                            lines = user_content.split("\n")
                            # Collect all command lines with their line numbers
                            command_lines = []
                            for line in lines:
                                # Match patterns like "3. @SYSTEM_ADMIN (ID: SYSTEM_ADMIN): $memorize test"
                                # re already imported at top of file
                                history_match = re.search(r"^(\d+)\.\s*@[^:]+:\s*(\$\w+.*?)$", line.strip())
                                if history_match:
                                    line_num = int(history_match.group(1))
                                    command_line = history_match.group(2).strip()
                                    command_lines.append((line_num, command_line))

                            # Use the most recent command (highest line number)
                            if command_lines:
                                command_lines.sort(key=lambda x: x[0], reverse=True)
                                _, command_line = command_lines[0]

                                if command_line.startswith("$"):
                                    # Parse this command
                                    parts = command_line.split(None, 1)
                                    command = parts[0].lower()
                                    command_args = parts[1] if len(parts) > 1 else ""

                                    # Process the command (similar to above)
                                    if command == "$memorize":
                                        content = command_args if command_args else "Empty memory"
                                        node_id = (
                                            "_".join(content.split()[:3]).lower().replace(",", "").replace(".", "")
                                        )
                                        if not node_id:
                                            node_id = "memory_node"

                                        params = MemorizeParams(
                                            node=GraphNode(
                                                id=node_id,
                                                type=NodeType.CONCEPT,
                                                scope=GraphScope.LOCAL,
                                                attributes={
                                                    "created_by": "mock_llm",
                                                    "content": content,
                                                    "description": f"Memory: {content}",
                                                },
                                            )
                                        )
                                        action = HandlerActionType.MEMORIZE
                                        rationale = (
                                            f"[MOCK LLM] Memorizing from conversation history: {content[:50]}..."
                                        )
                                        command_found = True
                                    elif command == "$speak":
                                        params = SpeakParams(
                                            content=command_args if command_args else "[MOCK LLM] Hello!"
                                        )
                                        action = HandlerActionType.SPEAK
                                        rationale = "[MOCK LLM] Speaking from conversation history"
                                        command_found = True
                                    elif command == "$recall":
                                        query = command_args if command_args else "memories"
                                        params = RecallParams(
                                            query=query, node_type=NodeType.CONCEPT, scope=GraphScope.LOCAL, limit=5
                                        )
                                        action = HandlerActionType.RECALL
                                        rationale = f"[MOCK LLM] Recalling from conversation history: {query}"
                                        command_found = True
                                    # Add other handlers as needed...

                            if command_found:
                                break

                if not command_found:
                    # Default: new task → SPEAK
                    action = HandlerActionType.SPEAK
                    # Include multimodal detection info if images were present
                    if multimodal_image_count > 0:
                        speak_content = f"[MOCKLLM DISCLAIMER] SPEAK IN RESPONSE TO TASK WITHOUT COMMAND [MULTIMODAL_DETECTED:{multimodal_image_count}]"
                    else:
                        speak_content = "[MOCKLLM DISCLAIMER] SPEAK IN RESPONSE TO TASK WITHOUT COMMAND"
                    params = SpeakParams(content=speak_content)
                    rationale = "[MOCK LLM] Default speak action for new task"

    # Use custom rationale if provided, otherwise use the generated rationale
    final_rationale = custom_rationale if custom_rationale else rationale

    # Store action parameters directly as a dict
    if params:
        action_params_dict = params.model_dump() if hasattr(params, "model_dump") else params
    else:
        action_params_dict = None

    result = ActionSelectionDMAResult(
        selected_action=action,
        action_parameters=action_params_dict,  # Store parameters directly
        rationale=final_rationale,
    )

    # Return structured result directly - instructor will handle it
    return result
