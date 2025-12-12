"""
Dynamic Action Instruction Generator for CIRIS Agent.

Generates action parameter schemas and instructions dynamically based on
registered action handlers and their parameter schemas.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel

from ciris_engine.logic.utils.jsondict_helpers import get_dict, get_str
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
from ciris_engine.schemas.types import JSONDict

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
        """Generate dynamic tool schema based on available tools.

        CRITICAL: This method MUST use pre-cached tools. No fallbacks, no hardcoded tools.
        If tools aren't available, we fail loudly so the issue is obvious.
        """
        base_schema = (
            'TOOL: {"name": string (tool name), "parameters": Dict[str, str|int|float|bool|List[str]|Dict[str,str]]}'
        )

        # Check for pre-cached tools first (set by async caller before prompt building)
        if hasattr(self, "_cached_tools") and self._cached_tools:
            logger.info(f"[TOOL_SCHEMA] Using {len(self._cached_tools)} pre-cached tools")
            return base_schema + self._format_tools_for_prompt(self._cached_tools)

        # No service registry = no tools
        if not self.service_registry:
            logger.error("[TOOL_SCHEMA] FAIL: No service_registry available - cannot discover tools!")
            return base_schema + "\n\n⚠️ ERROR: No tool service registry available. Tools cannot be discovered."

        # Service registry exists but no cached tools - this is a bug in the caller
        logger.error(
            "[TOOL_SCHEMA] FAIL: service_registry exists but _cached_tools not set! "
            "Caller must call await pre_cache_tools() before generating schema. "
            "This is a bug - tools should be fetched asynchronously before prompt building."
        )
        return base_schema + "\n\n⚠️ ERROR: Tools not pre-cached. Call pre_cache_tools() before schema generation."

    async def pre_cache_tools(self) -> int:
        """Pre-cache tools from all registered tool services.

        MUST be called before generate_action_instructions() to populate _cached_tools.
        Returns the number of tools cached.
        """
        if not self.service_registry:
            logger.warning("[TOOL_CACHE] No service_registry - cannot cache tools")
            self._cached_tools: JSONDict = {}
            return 0

        all_tools: JSONDict = {}
        tool_services = self.service_registry.get_services_by_type("tool")

        logger.info(f"[TOOL_CACHE] Discovering tools from {len(tool_services)} tool service(s)...")

        for tool_service in tool_services:
            service_name = getattr(tool_service, "adapter_name", type(tool_service).__name__)
            try:
                await self._cache_tools_from_service(tool_service, service_name, all_tools)
            except Exception as e:
                logger.error(f"[TOOL_CACHE] {service_name}: FAILED to get tools: {e}")

        self._cached_tools = all_tools
        logger.info(f"[TOOL_CACHE] ✓ Cached {len(all_tools)} total tools: {list(all_tools.keys())}")
        return len(all_tools)

    async def _cache_tools_from_service(self, tool_service: Any, service_name: str, all_tools: JSONDict) -> None:
        """Cache tools from a single tool service into all_tools dict."""
        if hasattr(tool_service, "get_all_tool_info"):
            await self._cache_from_tool_info_api(tool_service, service_name, all_tools)
        elif hasattr(tool_service, "get_available_tools"):
            await self._cache_from_available_tools_api(tool_service, service_name, all_tools)
        else:
            logger.warning(f"[TOOL_CACHE] {service_name}: No get_all_tool_info or get_available_tools method!")

    async def _cache_from_tool_info_api(self, tool_service: Any, service_name: str, all_tools: JSONDict) -> None:
        """Cache tools using the get_all_tool_info() API."""
        tool_infos = await tool_service.get_all_tool_info()
        logger.info(f"[TOOL_CACHE] {service_name}: Found {len(tool_infos)} tools via get_all_tool_info()")

        for tool_info in tool_infos:
            tool_name = tool_info.name
            tool_key = f"{tool_name}_{service_name}" if tool_name in all_tools else tool_name

            enhanced_info: JSONDict = {
                "name": tool_name,
                "service": service_name,
                "description": tool_info.description,
                "parameters": tool_info.parameters.model_dump() if tool_info.parameters else {},
            }
            if hasattr(tool_info, "when_to_use") and tool_info.when_to_use:
                enhanced_info["when_to_use"] = tool_info.when_to_use

            all_tools[tool_key] = enhanced_info
            logger.debug(f"[TOOL_CACHE]   - {tool_name}: {tool_info.description[:50]}...")

    async def _cache_from_available_tools_api(self, tool_service: Any, service_name: str, all_tools: JSONDict) -> None:
        """Cache tools using the get_available_tools() API."""
        service_tools = await tool_service.get_available_tools()
        logger.info(f"[TOOL_CACHE] {service_name}: Found {len(service_tools)} tools via get_available_tools()")

        if isinstance(service_tools, list):
            self._cache_tools_from_list(service_tools, service_name, all_tools)
        elif isinstance(service_tools, dict):
            self._cache_tools_from_dict(service_tools, service_name, all_tools)

    def _cache_tools_from_list(self, service_tools: List[str], service_name: str, all_tools: JSONDict) -> None:
        """Cache tools from a list of tool names."""
        for tool_name in service_tools:
            tool_key = f"{tool_name}_{service_name}" if tool_name in all_tools else tool_name
            all_tools[tool_key] = {
                "name": tool_name,
                "description": "No description available",
                "service": service_name,
            }

    def _cache_tools_from_dict(self, service_tools: Dict[str, Any], service_name: str, all_tools: JSONDict) -> None:
        """Cache tools from a dict of tool name to tool info."""
        for tool_name, tool_info in service_tools.items():
            tool_key = f"{tool_name}_{service_name}" if tool_name in all_tools else tool_name
            enhanced_info: JSONDict = {
                "name": tool_name,
                "service": service_name,
                "description": (
                    tool_info.get("description", "No description") if isinstance(tool_info, dict) else "No description"
                ),
            }
            if isinstance(tool_info, dict):
                if "parameters" in tool_info:
                    enhanced_info["parameters"] = tool_info["parameters"]
                if "when_to_use" in tool_info:
                    enhanced_info["when_to_use"] = tool_info["when_to_use"]
            all_tools[tool_key] = enhanced_info

    def _format_tools_for_prompt(self, all_tools: JSONDict) -> str:
        """Format cached tools into prompt text."""
        if not all_tools:
            return "\n\n⚠️ No tools registered. TOOL action is not available."

        tools_info = []
        tools_info.append("\nAvailable tools and their parameters:")

        for tool_key, tool_info_raw in all_tools.items():
            tool_info = get_dict({"info": tool_info_raw}, "info", {})
            tool_name = get_str(tool_info, "name", "")
            tool_desc_str = get_str(tool_info, "description", "")
            tool_service = get_str(tool_info, "service", "")

            tool_desc = f"  - {tool_name}: {tool_desc_str}"
            if tool_service != tool_name:
                tool_desc += f" (from {tool_service})"
            tools_info.append(tool_desc)

            if "parameters" in tool_info:
                params = get_dict(tool_info, "parameters", {})
                param_text = f"    parameters: {json.dumps(params, indent=6)}"
                tools_info.append(param_text)

            if "when_to_use" in tool_info:
                when_to_use = get_str(tool_info, "when_to_use", "")
                tools_info.append(f"    Use when: {when_to_use}")

        return "\n".join(tools_info)

    def _simplify_schema(self, schema: JSONDict) -> str:
        """Simplify a JSON schema to a readable format."""
        from ciris_engine.logic.utils.jsondict_helpers import get_list

        properties = get_dict(schema, "properties", {})
        required_raw = schema.get("required", [])
        required = list(required_raw) if isinstance(required_raw, list) else []

        params = []
        for prop_name, prop_schema_raw in properties.items():
            # Convert prop_schema to dict
            prop_schema = get_dict({"s": prop_schema_raw}, "s", {})

            # Handle complex types (anyOf, oneOf, allOf)
            prop_type = self._extract_type(prop_schema)

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
            base_type = get_str(prop_schema, "type", "any")

            # Handle object types with additionalProperties
            if base_type == "object" and "additionalProperties" in prop_schema:
                add_props = get_dict(prop_schema, "additionalProperties", {})
                if get_str(add_props, "type", "") == "string":
                    return "Dict[str, str]"

            return str(base_type)

        # Handle anyOf (nullable types)
        if "anyOf" in prop_schema:
            types = []
            anyof_raw = prop_schema.get("anyOf", [])
            anyof_list = list(anyof_raw) if isinstance(anyof_raw, list) else []

            for option_raw in anyof_list:
                option = get_dict({"o": option_raw}, "o", {})
                opt_type = get_str(option, "type", "")

                if opt_type == "null":
                    continue  # Skip null option
                elif opt_type == "object":
                    # Check if it's a Dict[str, str]
                    if "additionalProperties" in option:
                        add_props = get_dict(option, "additionalProperties", {})
                        if get_str(add_props, "type", "") == "string":
                            types.append("Dict[str, str]")
                        else:
                            types.append("object")
                    else:
                        types.append("object")
                else:
                    types.append(opt_type if opt_type else "any")

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
