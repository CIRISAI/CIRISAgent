"""Optimized Mock LLM Action Selection - Reduced from 980 to ~450 lines."""
from typing import Optional, Any, List, Union, Dict, Callable, Tuple
import re
import json
import logging
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.actions import *
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.services.graph_core import GraphNode, NodeType, GraphScope, GraphNodeAttributes
from ciris_engine.logic.utils.channel_utils import create_channel_context

logger = logging.getLogger(__name__)

# Constants
VALID_NODE_TYPES = ["AGENT", "USER", "CHANNEL", "CONCEPT", "CONFIG"]
VALID_SCOPES = ["LOCAL", "IDENTITY", "ENVIRONMENT", "COMMUNITY", "NETWORK"]

HELP_TEXT = """📋 CIRIS Mock LLM Commands Help

🎛️ **Action Commands:**
• $speak <message> - Send a message
• $speak @channel:<id> <message> - Cross-channel message
• $recall <query> OR <node_id> [type] [scope] - Query memory
• $memorize <content> - Store in memory
• $tool <name> [params] - Execute a tool
• $observe [channel] [active] - Monitor channel
• $ponder <q1>; <q2> - Ask questions
• $defer <reason> - Postpone task
• $reject <reason> - Decline request
• $forget <node_id> <reason> - Remove memory
• $task_complete - Complete current task
• $help - Show this help

📝 **Formats:**
• NodeType: {types}
• GraphScope: {scopes}

💡 **Examples:**
• $speak Hello world!
• $recall weather
• $tool read_file {{"path": "/tmp/test.txt"}}
""".format(types=", ".join(VALID_NODE_TYPES), scopes=", ".join(VALID_SCOPES))

# Error templates
ERRORS = {
    'no_content': "❌ {} requires content. Example: {}",
    'invalid_type': "❌ Invalid node type '{}'. Valid: {}",
    'invalid_scope': "❌ Invalid scope '{}'. Valid: {}",
    'no_params': "❌ {} requires parameters. Example: {}"
}

def parse_channel(content: str) -> Tuple[Optional[str], str]:
    """Extract @channel: from content."""
    match = re.search(r'@channel:(\S+)', content)
    if match:
        channel = match.group(1)
        cleaned = content.replace(match.group(0), '').strip() or "[MOCK LLM] Cross-channel message"
        return channel, cleaned
    return None, content

def create_node(node_id: str, node_type: str = "CONCEPT", scope: str = "LOCAL", 
                content: str = None, tags: List[str] = None) -> GraphNode:
    """Create a GraphNode."""
    # GraphNodeAttributes doesn't have content field - use tags/metadata instead
    attrs = GraphNodeAttributes(created_by="mock_llm")
    if tags:
        attrs.tags = tags
    return GraphNode(
        id=node_id,
        type=getattr(NodeType, node_type.upper()),
        scope=getattr(GraphScope, scope.upper()),
        attributes=attrs
    )

def parse_tool_params(params_str: str) -> Dict[str, Any]:
    """Parse tool parameters."""
    if not params_str:
        return {}
    try:
        return json.loads(params_str)
    except:
        # Key=value parsing
        result = {}
        for pair in params_str.split():
            if '=' in pair:
                k, v = pair.split('=', 1)
                result[k] = v.strip().rstrip('\\')
        return result

# Command handlers - compact format
def cmd_speak(args: str, ctx: List, msgs: List) -> Tuple[HandlerActionType, Any, str]:
    if not args:
        # Empty command defaults to hello
        return HandlerActionType.SPEAK, SpeakParams(content="[MOCK LLM] Hello!"), "Speaking"
    
    if args == "$context":
        content = "📋 **Full Context Display**\n\n**Context:**\n"
        content += "\n".join(f"• {item}" for item in ctx)
        content += "\n\n**Messages:**\n"
        for i, msg in enumerate(msgs):
            content += f"\n[{i}] {msg.get('role', '?')}: {msg.get('content', '')[:100]}...\n"
        return HandlerActionType.SPEAK, SpeakParams(content=content), "Showing context"
    
    channel, content = parse_channel(args)
    params = SpeakParams(content=content, channel_context=create_channel_context(channel) if channel else None)
    return HandlerActionType.SPEAK, params, f"Speaking{' to ' + channel if channel else ''}"

def cmd_memorize(args: str, ctx: List, msgs: List) -> Tuple[HandlerActionType, Any, str]:
    if not args:
        return HandlerActionType.SPEAK, SpeakParams(content=ERRORS['no_params'].format("$memorize", "$memorize important fact")), "Error"
    
    parts = args.split()
    # If 3+ parts, check if it's structured format
    if len(parts) >= 3:
        # Check if it looks like structured format (second part could be a node type)
        potential_node_type = parts[1].upper()
        potential_scope = parts[2].upper()
        
        # Validate node type if it looks like structured format
        if potential_node_type in VALID_NODE_TYPES:
            # Valid structured format
            node_id = parts[0]
            if potential_scope not in VALID_SCOPES:
                return HandlerActionType.SPEAK, SpeakParams(content=ERRORS['invalid_scope'].format(potential_scope, ', '.join(VALID_SCOPES))), "Error"
            node = create_node(node_id, potential_node_type, potential_scope)
        else:
            # Could be invalid structured format - check if scope is valid
            if potential_scope in VALID_SCOPES:
                # Looks like structured format but invalid node type
                return HandlerActionType.SPEAK, SpeakParams(content=ERRORS['invalid_type'].format(potential_node_type, ', '.join(VALID_NODE_TYPES))), "Error"
            else:
                # Not structured format, treat as content
                node_id = "_".join(args.split()[:3]).lower().replace(",", "").replace(".", "") or "memory"
                node = create_node(node_id, tags=[f"content:{args[:50]}", "source:mock_llm"])
    else:
        # Treat as content
        node_id = "_".join(args.split()[:3]).lower().replace(",", "").replace(".", "") or "memory"
        node = create_node(node_id, tags=[f"content:{args[:50]}", "source:mock_llm"])
    
    return HandlerActionType.MEMORIZE, MemorizeParams(node=node), f"Memorizing {node_id}"

def cmd_recall(args: str, ctx: List, msgs: List) -> Tuple[HandlerActionType, Any, str]:
    if not args:
        args = "memories"
    
    parts = args.split()
    # Structured format: node_id TYPE SCOPE
    if len(parts) >= 3 and parts[1].upper() in VALID_NODE_TYPES:
        params = RecallParams(
            node_id=parts[0],
            node_type=getattr(NodeType, parts[1].upper()),
            scope=getattr(GraphScope, parts[2].upper()) if len(parts) > 2 else None,
            limit=10
        )
        return HandlerActionType.RECALL, params, f"Recalling node {parts[0]}"
    
    # Simple query - for user commands, use string node_type
    params = RecallParams(query=args, node_type="CONCEPT", limit=10)
    return HandlerActionType.RECALL, params, f"Recalling: {args}"

def cmd_ponder(args: str, ctx: List, msgs: List) -> Tuple[HandlerActionType, Any, str]:
    if not args:
        return HandlerActionType.SPEAK, SpeakParams(content=ERRORS['no_params'].format("$ponder", "$ponder What now?; How to help?")), "Error"
    questions = [q.strip() for q in args.split(';') if q.strip()]
    return HandlerActionType.PONDER, PonderParams(questions=questions), "Pondering"

def cmd_observe(args: str, ctx: List, msgs: List) -> Tuple[HandlerActionType, Any, str]:
    parts = args.split() if args else []
    channel = parts[0] if parts else "cli"
    active = len(parts) > 1 and parts[1].lower() == 'true'
    return HandlerActionType.OBSERVE, ObserveParams(channel_context=create_channel_context(channel), active=active), f"Observing {channel}"

def cmd_tool(args: str, ctx: List, msgs: List) -> Tuple[HandlerActionType, Any, str]:
    if not args:
        return HandlerActionType.SPEAK, SpeakParams(content=ERRORS['no_params'].format("$tool", "$tool list_files")), "Error"
    
    parts = args.split(None, 1)
    name = parts[0]
    params = {}
    if len(parts) > 1:
        if name == "curl":
            params = {"url": parts[1].strip()}
        else:
            params = parse_tool_params(parts[1])
    
    return HandlerActionType.TOOL, ToolParams(name=name, parameters=params), f"Tool: {name}"

def cmd_defer(args: str, ctx: List, msgs: List) -> Tuple[HandlerActionType, Any, str]:
    reason = args or "Need more information"
    return HandlerActionType.DEFER, DeferParams(reason=reason), "Deferring"

def cmd_reject(args: str, ctx: List, msgs: List) -> Tuple[HandlerActionType, Any, str]:
    reason = args or "Cannot process request"
    return HandlerActionType.REJECT, RejectParams(reason=reason), "Rejecting"

def cmd_forget(args: str, ctx: List, msgs: List) -> Tuple[HandlerActionType, Any, str]:
    if not args:
        return HandlerActionType.SPEAK, SpeakParams(content=ERRORS['no_params'].format("$forget", "$forget node123 Privacy request")), "Error"
    
    parts = args.split(None, 1)
    if len(parts) >= 2:
        node_id = parts[0]
        reason = parts[1]
    else:
        # If only one part, treat as node_id with default reason
        node_id = parts[0]
        reason = "User requested deletion"
    
    node = create_node(node_id)
    return HandlerActionType.FORGET, ForgetParams(node=node, reason=reason), f"Forgetting {node_id}"

def cmd_task_complete(args: str, ctx: List, msgs: List) -> Tuple[HandlerActionType, Any, str]:
    return HandlerActionType.TASK_COMPLETE, TaskCompleteParams(completion_reason=args or "[MOCK LLM] Task completed"), "Completing"

def cmd_help(args: str, ctx: List, msgs: List) -> Tuple[HandlerActionType, Any, str]:
    return HandlerActionType.SPEAK, SpeakParams(content=HELP_TEXT), "Showing help"

# Command registry
COMMANDS = {
    '$speak': cmd_speak,
    '$memorize': cmd_memorize,
    '$recall': cmd_recall,
    '$ponder': cmd_ponder,
    '$observe': cmd_observe,
    '$tool': cmd_tool,
    '$defer': cmd_defer,
    '$reject': cmd_reject,
    '$forget': cmd_forget,
    '$task_complete': cmd_task_complete,
    '$help': cmd_help
}

def extract_command(text: str) -> Optional[Tuple[str, str]]:
    """Extract command and args from text."""
    if text and text.startswith('$'):
        parts = text.split(None, 1)
        return parts[0].lower(), parts[1] if len(parts) > 1 else ""
    return None

def extract_user_input(msg_content: str) -> str:
    """Extract user input from various message formats."""
    # @USERNAME (ID: ID): content
    match = re.search(r'@\w+\s*\([^)]+\):\s*(.+)', msg_content, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    
    # User said: content
    match = re.search(r'(?:User|@\w+)\s+(?:said|says?):\s*(.+)', msg_content, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    
    return msg_content.strip()

def process_forced_action(action: str, params: str, ctx: List, msgs: List) -> Tuple[HandlerActionType, Any, str]:
    """Process forced action for testing."""
    try:
        action_type = getattr(HandlerActionType, action.upper())
        
        # Special handling for SPEAK with no params in forced action context
        if action_type == HandlerActionType.SPEAK and not params:
            return HandlerActionType.SPEAK, SpeakParams(content=ERRORS['no_content'].format("$speak", "$speak Hello")), "Error"
        
        # Map to command handlers
        handler_map = {
            HandlerActionType.SPEAK: cmd_speak,
            HandlerActionType.MEMORIZE: cmd_memorize,
            HandlerActionType.RECALL: cmd_recall,
            HandlerActionType.PONDER: cmd_ponder,
            HandlerActionType.OBSERVE: cmd_observe,
            HandlerActionType.TOOL: cmd_tool,
            HandlerActionType.DEFER: cmd_defer,
            HandlerActionType.REJECT: cmd_reject,
            HandlerActionType.FORGET: cmd_forget,
            HandlerActionType.TASK_COMPLETE: lambda p, c, m: (HandlerActionType.TASK_COMPLETE, TaskCompleteParams(completion_reason="Forced task completion via testing"), "Completing")
        }
        
        if action_type in handler_map:
            result = handler_map[action_type](params, ctx, msgs)
            return result[0], result[1], f"[MOCK LLM] Executing {action} action from mock command"
            
    except AttributeError:
        valid_actions = ['speak', 'recall', 'memorize', 'tool', 'observe', 'ponder', 
                        'defer', 'reject', 'forget', 'task_complete']
        return HandlerActionType.SPEAK, SpeakParams(content=f"❌ Invalid action '{action}'. Valid actions: {', '.join(valid_actions)}"), "[MOCK LLM] Invalid action"
    
    return HandlerActionType.SPEAK, SpeakParams(content=f"❌ Invalid action '{action}'"), "[MOCK LLM] Invalid action"

def action_selection(context: Optional[List[Any]] = None, messages: Optional[List[dict]] = None) -> ActionSelectionDMAResult:
    """Mock LLM action selection - optimized version."""
    context = context or []
    messages = messages or []
    
    logger.debug(f"[MOCK_LLM] Context: {len(context)}, Messages: {len(messages)}")
    
    # Extract context elements
    user_input = ""
    forced_action = None
    action_params = ""
    custom_rationale = None
    show_help = False
    
    for item in context:
        if isinstance(item, str):
            if item.startswith(("user_input:", "task:", "content:")):
                user_input = item.split(":", 1)[1].strip()
                break
            elif item.startswith("forced_action:"):
                forced_action = item.split(":", 1)[1]
            elif item.startswith("action_params:"):
                action_params = item.split(":", 1)[1]
            elif item.startswith("custom_rationale:"):
                custom_rationale = item.split(":", 1)[1]
            elif item == "show_help_requested":
                show_help = True
    
    # Process in priority order
    action, params, rationale = None, None, None
    
    # 1. Forced action
    if forced_action:
        action, params, rationale = process_forced_action(forced_action, action_params, context, messages)
    
    # 2. Help request
    elif show_help:
        action, params, rationale = cmd_help("", context, messages)
    
    # 3. User command
    elif user_input:
        cmd_info = extract_command(user_input)
        if cmd_info and cmd_info[0] in COMMANDS:
            action, params, rationale = COMMANDS[cmd_info[0]](cmd_info[1], context, messages)
        elif not user_input.startswith('$'):
            # Non-command speech
            action = HandlerActionType.SPEAK
            params = SpeakParams(content="[MOCKLLM DISCLAIMER] SPEAK IN RESPONSE TO TASK WITHOUT COMMAND")
            rationale = f"Responding to: {user_input[:50]}"
    
    # 4. Check messages
    else:
        # Check for follow-up thought
        is_followup = False
        if messages and messages[0].get('role') == 'system' and messages[0].get('content', '').startswith('THOUGHT_TYPE=follow_up'):
            is_followup = True
            
            # Extract thought content
            for msg in messages:
                if msg.get('role') == 'user' and "Original Thought:" in msg.get('content', ''):
                    match = re.search(r'Original Thought:\s*"(.*?)"', msg['content'], re.DOTALL)
                    if match:
                        thought = match.group(1)
                        if any(p in thought for p in ["Message sent successfully", "TASK COMPLETE", "spoke in channel"]):
                            action = HandlerActionType.TASK_COMPLETE
                            params = TaskCompleteParams(completion_reason="[MOCK LLM] SPEAK operation completed")
                            rationale = "[MOCK LLM] Completing follow-up"
                        else:
                            content = thought.replace("CIRIS_FOLLOW_UP_THOUGHT:", "").strip()
                            action = HandlerActionType.SPEAK
                            params = SpeakParams(content=f"[MOCK LLM] {content}")
                            rationale = "[MOCK LLM] Speaking follow-up result"
                        break
        
        # Check for commands in messages
        if not action:
            for msg in messages:
                if msg.get('role') == 'user':
                    user_input = extract_user_input(msg.get('content', ''))
                    cmd_info = extract_command(user_input)
                    if cmd_info and cmd_info[0] in COMMANDS:
                        action, params, rationale = COMMANDS[cmd_info[0]](cmd_info[1], context, messages)
                        break
                    
                    # Check conversation history
                    if "=== CONVERSATION HISTORY" in msg.get('content', ''):
                        for line in msg['content'].split('\n'):
                            match = re.search(r'^\d+\.\s*@\w+\s*\([^)]+\):\s*(\$\w+.*?)$', line.strip())
                            if match:
                                cmd_text = match.group(1).strip()
                                cmd_info = extract_command(cmd_text)
                                if cmd_info and cmd_info[0] in COMMANDS:
                                    # Special handling for memorize from history
                                    if cmd_info[0] == '$memorize':
                                        # Treat args as content for user commands
                                        action = HandlerActionType.MEMORIZE
                                        node_id = "_".join(cmd_info[1].split()[:3]).lower().replace(",", "").replace(".", "") or "memory"
                                        node = create_node(node_id, tags=[f"content:{cmd_info[1][:50]}", "source:mock_llm"])
                                        params = MemorizeParams(node=node)
                                        rationale = f"Memorizing: {cmd_info[1][:50]}..."
                                    else:
                                        action, params, rationale = COMMANDS[cmd_info[0]](cmd_info[1], context, messages)
                                    break
    
    # Default
    if not action:
        action = HandlerActionType.SPEAK
        params = SpeakParams(content="[MOCKLLM DISCLAIMER] SPEAK IN RESPONSE TO TASK WITHOUT COMMAND")
        rationale = "[MOCK LLM] Default speak action"
    
    return ActionSelectionDMAResult(
        selected_action=action,
        action_parameters=params,
        rationale=custom_rationale or f"[MOCK LLM] {rationale}"
    )