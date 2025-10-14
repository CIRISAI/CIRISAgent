"""
Dynamic Action Instruction Generator for CIRIS Agent.

Generates action parameter schemas and instructions dynamically based on
registered action handlers and their parameter schemas.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Type
from ciris_engine.schemas.types import JSONDict

from pydantic import BaseModel

from ciris_engine.schemas.actions.parameters import (
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
from ciris_engine.schemas.runtime.enums import HandlerActionType

logger = logging.getLogger(__name__)


class ActionInstructionGenerator:
    """Generates dynamic action instructions based on registered handlers and schemas."""

    # Map action types to their parameter schemas
    ACTION_PARAM_SCHEMAS: Dict[HandlerActionType, Type[BaseModel]] = {
        HandlerActionType.OBSERVE: ObserveParams,
        HandlerActionType.SPEAK: SpeakParams,
        HandlerActionType.TOOL: ToolParams,
        HandlerActionType.PONDER: PonderParams,
        HandlerActionType.REJECT: RejectParams,
        HandlerActionType.DEFER: DeferParams,
        HandlerActionType.MEMORIZE: MemorizeParams,
        HandlerActionType.RECALL: RecallParams,
        HandlerActionType.FORGET: ForgetParams,
        HandlerActionType.TASK_COMPLETE: TaskCompleteParams,
    }

    def __init__(self, service_registry: Optional[Any] = None, bus_manager: Optional[Any] = None):
        """Initialize with optional service registry and multi-service sink for tool discovery."""
        self.service_registry = service_registry
        self.bus_manager = bus_manager
        self._cached_instructions: Optional[str] = None

    def generate_action_instructions(self, available_actions: Optional[List[HandlerActionType]] = None) -> str:
        """Generate complete action parameter instructions dynamically."""

        if available_actions is None:
            available_actions = list(HandlerActionType)

        instructions = []
        instructions.append("Schemas for 'action_parameters' based on the selected_action:")

        for action_type in available_actions:
            if action_type in self.ACTION_PARAM_SCHEMAS:
                schema_text = self._generate_schema_for_action(action_type)
                if schema_text:
                    instructions.append(schema_text)

        return "\n".join(instructions)

    def _generate_schema_for_action(self, action_type: HandlerActionType) -> str:
        """Generate schema text for a specific action type."""

        param_class = self.ACTION_PARAM_SCHEMAS.get(action_type)
        if not param_class:
            return ""

        # Get the Pydantic schema
        schema = param_class.model_json_schema()

        # Use the actual schema to generate the format
        schema_str = self._simplify_schema(schema)

        # Add action-specific guidance
        if action_type == HandlerActionType.MEMORIZE:
            return self._format_memory_action_schema("MEMORIZE")

        elif action_type == HandlerActionType.RECALL:
            return self._format_memory_action_schema("RECALL")

        elif action_type == HandlerActionType.FORGET:
            # Special formatting for FORGET to show the node structure
            return (
                'FORGET: {"node": {id: string, type: "agent"|"user"|"channel"|"concept", '
                'scope: "local"|"identity"|"environment"}}, "reason": string (required)}}\n'
                "For user nodes: Use numeric Discord IDs like 'user/537080239679864862' as the node id."
            )

        elif action_type == HandlerActionType.DEFER:
            # Override the schema string to be more explicit about types
            defer_schema = (
                '{"reason": string (required), "context"?: Dict[str, str], "defer_until"?: ISO 8601 timestamp string}'
            )
            return (
                f"DEFER: {defer_schema}\n"
                "defer_until must be ISO 8601 format: '2025-01-20T15:00:00Z'\n"
                f'context should be a dictionary: {{"key": "value"}}\n'
                "Use defer_until for time-based deferrals that auto-reactivate."
            )

        elif action_type == HandlerActionType.REJECT:
            return f"REJECT: {schema_str}\nUse create_filter=true to prevent similar future requests."

        elif action_type == HandlerActionType.TOOL:
            return self._generate_tool_schema()

        elif action_type == HandlerActionType.TASK_COMPLETE:
            # Override schema to be explicit about context type
            complete_schema = '{"completion_reason": string (default: "Task completed successfully"), "context"?: Dict[str, str], "positive_moment"?: string}'
            return (
                f"TASK_COMPLETE: {complete_schema}\n"
                f'context should be a dictionary: {{"task_id": "123", "status": "done"}}\n'
                "Use when task is done, impossible, unnecessary, or cannot be actioned. "
                "This is the preferred resolution for problematic tasks."
            )

        elif action_type == HandlerActionType.OBSERVE:
            # Override schema to be explicit about context type
            observe_schema = '{"channel_id"?: string, "channel_context"?: object, "active": boolean (default: false), "context"?: Dict[str, str]}'
            return (
                f"OBSERVE: {observe_schema}\n"
                f'context should be a dictionary: {{"reason": "need more info", "focus": "user intent"}}'
            )

        else:
            # For all other actions, use the dynamically generated schema
            return f"{action_type.value.upper()}: {schema_str}"

    def _format_memory_action_schema(self, action_name: str) -> str:
        """Format schema for memory-related actions (MEMORIZE, RECALL)."""
        if action_name == "MEMORIZE":
            base_schema = (
                'MEMORIZE: {"node": {id: string (unique identifier), '
                'type: "agent"|"user"|"channel"|"concept", '
                'scope: "local"|"identity"|"environment", '
                "attributes?: object (data to store)}}"
            )

            # Add guidance for MEMORIZE
            guidance = [
                "\nFor type: use 'user' for user data, 'channel' for channel data, "
                "'concept' for facts/beliefs/knowledge, 'agent' for agent data.",
                "For scope: use 'local' for user/channel data, 'identity' for personal "
                "facts/beliefs, 'environment' for external/internet data.",
                "\nIMPORTANT for user nodes: ALWAYS use numeric Discord IDs (e.g., 'user/537080239679864862') "
                "as the primary identifier, NOT usernames. Usernames can change, but numeric IDs are permanent. "
                "Store the username in attributes if needed, but the node ID must be the numeric user ID.",
            ]

            return base_schema + "\n".join(guidance)

        elif action_name == "RECALL":
            # RECALL has a completely different schema
            base_schema = (
                'RECALL: {"query"?: string (search text), '
                '"node_type"?: string (agent, user, channel, concept, config, tsdb_data, tsdb_summary, conversation_summary, audit_entry, identity_snapshot, behavioral, social, identity, observation), '
                '"node_id"?: string (specific node ID), '
                '"scope"?: "local"|"identity"|"environment", '
                '"limit"?: integer (default: 10)}}'
            )

            # Add guidance for RECALL
            guidance = [
                "\nUse query to search by text, node_type to filter by type, " "node_id to fetch a specific node.",
                "At least one of query, node_type, or node_id should be provided.",
                "For scope: use 'local' for user/channel data, 'identity' for personal "
                "facts/beliefs, 'environment' for external/internet data.",
                "\nFor user lookups: Use numeric Discord IDs like 'user/537080239679864862' for node_id. "
                "If you only have a username, use query with node_type='user' to search.",
            ]

            return base_schema + "\n".join(guidance)

        # Should not reach here
        return f"{action_name}: {{}}"

    def _generate_tool_schema(self) -> str:
        """Generate dynamic tool schema based on available tools."""
        base_schema = (
            'TOOL: {"name": string (tool name), "parameters": Dict[str, str|int|float|bool|List[str]|Dict[str,str]]}'
        )

        # If we have a service registry, try to get tools from all tool services
        if self.service_registry:
            try:
                # Get all tool services from the registry
                import asyncio

                loop = asyncio.get_event_loop()

                # Create a coroutine to get all tools
                async def get_all_tools() -> JSONDict:
                    if not self.service_registry:
                        return {}

                    # Get ALL tool services registered in the system
                    tool_services = self.service_registry.get_services_by_type("tool")
                    all_tools = {}

                    # Aggregate tools from all services
                    for tool_service in tool_services:
                        try:
                            # Try to get detailed tool info first
                            service_name = getattr(tool_service, "adapter_name", type(tool_service).__name__)

                            # Check if service has get_all_tool_info method
                            if hasattr(tool_service, "get_all_tool_info"):
                                tool_infos = await tool_service.get_all_tool_info()

                                # Process ToolInfo objects
                                for tool_info in tool_infos:
                                    tool_name = tool_info.name

                                    # Create unique key if tool name exists in multiple services
                                    if tool_name in all_tools:
                                        tool_key = f"{tool_name}_{service_name}"
                                    else:
                                        tool_key = tool_name

                                    # Extract info from ToolInfo object
                                    enhanced_info = {
                                        "name": tool_name,
                                        "service": service_name,
                                        "description": tool_info.description,
                                        "parameters": tool_info.parameters.model_dump() if tool_info.parameters else {},
                                    }

                                    if hasattr(tool_info, "when_to_use") and tool_info.when_to_use:
                                        enhanced_info["when_to_use"] = tool_info.when_to_use

                                    all_tools[tool_key] = enhanced_info
                            else:
                                # Fallback to get_available_tools
                                service_tools = await tool_service.get_available_tools()

                                if isinstance(service_tools, list):
                                    # If it returns a list of names, convert to dict
                                    for tool_name in service_tools:
                                        all_tools[tool_name] = {
                                            "name": tool_name,
                                            "description": "No description available",
                                            "service": service_name,
                                        }
                                elif isinstance(service_tools, dict):
                                    # If it returns a dict with details
                                    for tool_name, tool_info in service_tools.items():
                                        # Create unique key if tool name exists in multiple services
                                        if tool_name in all_tools:
                                            tool_key = f"{tool_name}_{service_name}"
                                        else:
                                            tool_key = tool_name

                                        # Enhance tool info with service metadata
                                        enhanced_info = {
                                            "name": tool_name,
                                            "service": service_name,
                                            "description": (
                                                tool_info.get("description", "No description")
                                                if isinstance(tool_info, dict)
                                                else "No description"
                                            ),
                                        }

                                        if isinstance(tool_info, dict):
                                            if "parameters" in tool_info:
                                                enhanced_info["parameters"] = tool_info["parameters"]
                                            if "when_to_use" in tool_info:
                                                enhanced_info["when_to_use"] = tool_info["when_to_use"]

                                        all_tools[tool_key] = enhanced_info

                        except Exception as e:
                            logger.warning(f"Failed to get tools from {type(tool_service).__name__}: {e}")

                    return all_tools

                # Execute the coroutine
                try:
                    if loop.is_running():
                        # If loop is already running, we can't use run_until_complete
                        # This is a limitation of calling async from sync in an async context
                        logger.debug("Event loop already running, skipping dynamic tool discovery")
                        return base_schema + self._get_default_tool_instructions()
                    else:
                        all_tools = loop.run_until_complete(get_all_tools())
                except RuntimeError as e:
                    logger.debug(f"Cannot fetch tools synchronously: {e}")
                    return base_schema + self._get_default_tool_instructions()

                if all_tools:
                    tools_info = []
                    tools_info.append("\nAvailable tools and their parameters:")

                    for tool_key, tool_info in all_tools.items():
                        tool_desc = f"  - {tool_info['name']}: {tool_info['description']}"
                        if tool_info["service"] != tool_info["name"]:
                            tool_desc += f" (from {tool_info['service']})"
                        tools_info.append(tool_desc)

                        # Add parameter schema if available
                        if "parameters" in tool_info:
                            param_text = f"    parameters: {json.dumps(tool_info['parameters'], indent=6)}"
                            tools_info.append(param_text)

                        # Add usage guidance if available
                        if "when_to_use" in tool_info:
                            tools_info.append(f"    Use when: {tool_info['when_to_use']}")

                    return base_schema + "\n".join(tools_info)

            except Exception as e:
                logger.warning(f"Could not fetch tools via LIST_TOOLS: {e}")

        # Fallback: Include some known tools
        return base_schema + self._get_default_tool_instructions()

    def _get_default_tool_instructions(self) -> str:
        """Get default tool instructions when dynamic discovery isn't available."""
        return """
Available tools (check with tool service for current list):
  - discord_delete_message: Delete a message
    parameters: {"channel_id": integer, "message_id": integer}
  - discord_timeout_user: Temporarily mute a user
    parameters: {"guild_id": integer, "user_id": integer, "duration_seconds": integer, "reason"?: string}
  - discord_ban_user: Ban a user from the server
    parameters: {"guild_id": integer, "user_id": integer, "reason"?: string, "delete_message_days"?: integer}"""

    def _simplify_schema(self, schema: JSONDict) -> str:
        """Simplify a JSON schema to a readable format."""
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        params = []
        for prop_name, prop_schema in properties.items():
            # Handle complex types (anyOf, oneOf, allOf)
            prop_type = self._extract_type(prop_schema)

            # Add description if available
            prop_schema.get("description", "")

            if prop_name in required:
                params.append(f'"{prop_name}": {prop_type} (required)')
            else:
                default = prop_schema.get("default")
                if default is not None:
                    params.append(f'"{prop_name}"?: {prop_type} (default: {default})')
                else:
                    params.append(f'"{prop_name}"?: {prop_type}')

        return "{" + ", ".join(params) + "}"

    def _extract_type(self, prop_schema: JSONDict) -> str:
        """Extract type information from a property schema, handling complex types."""
        # Direct type
        if "type" in prop_schema:
            base_type = prop_schema["type"]

            # Handle object types with additionalProperties
            if base_type == "object" and "additionalProperties" in prop_schema:
                add_props = prop_schema["additionalProperties"]
                if isinstance(add_props, dict) and add_props.get("type") == "string":
                    return "Dict[str, str]"

            return str(base_type)

        # Handle anyOf (nullable types)
        if "anyOf" in prop_schema:
            types = []
            for option in prop_schema["anyOf"]:
                if option.get("type") == "null":
                    continue  # Skip null option
                elif option.get("type") == "object":
                    # Check if it's a Dict[str, str]
                    if "additionalProperties" in option:
                        add_props = option["additionalProperties"]
                        if isinstance(add_props, dict) and add_props.get("type") == "string":
                            types.append("Dict[str, str]")
                        else:
                            types.append("object")
                    else:
                        types.append("object")
                else:
                    types.append(option.get("type", "any"))

            return types[0] if len(types) == 1 else " | ".join(types)

        # Handle oneOf, allOf similarly if needed
        return "any"

    def get_action_guidance(self, action_type: HandlerActionType) -> str:
        """Get specific guidance for an action type."""

        guidance_map = {
            HandlerActionType.SPEAK: (
                "If 'Speak' is chosen, the 'action_parameters' MUST be a JSON object "
                "containing a 'content' key with the substantive response string."
            ),
            HandlerActionType.PONDER: (
                "If 'Ponder' is chosen, 'questions' MUST list 2-3 distinct, NEW questions "
                "to resolve ambiguity, building upon any previous ponder_notes."
            ),
            HandlerActionType.OBSERVE: (
                "If 'Observe' is chosen to gather more context, 'active' SHOULD generally "
                "be true to actively fetch recent information. Provide clear context."
            ),
            HandlerActionType.REJECT: (
                "Use 'Reject' only for requests that are fundamentally unserviceable, "
                "unethical, or malicious. Set create_filter=true to prevent similar requests."
            ),
            HandlerActionType.DEFER: (
                "Use 'Defer' ONLY when a task MUST be completed AND requires human approval. "
                "Most problematic tasks should be marked TASK_COMPLETE instead. "
                "Defer is for tasks that need doing but require human oversight."
            ),
            HandlerActionType.TASK_COMPLETE: (
                "Use 'TASK_COMPLETE' when: task is done, impossible, unnecessary, or unclear. "
                "This is preferred over DEFER for most situations where you cannot act."
            ),
        }

        return guidance_map.get(action_type, "")
