"""Generated tool disclosure for the first-run setup wizard.

The setup wizard asks the operator to accept a set of adapters. Historically it
disclosed at *adapter* granularity -- "api", "discord", "cli" -- and never said
what those choices actually grant. This module produces the missing half.

**Wide tool access is intended.** Nothing here restricts, gates, or defaults
anything off. This module only makes the grant legible at the moment of consent.

The one hard rule: **the tool list is never hand-maintained.** Every tool name,
description, category and parameter set is read from a live tool service's
``get_all_tool_info()``. The cautionary case is in-repo -- ``moderation_tools``
in ``ciris_templates/echo.yaml`` names ``discord_slowmode``, a tool that does not
exist in the Discord tool service, and has drifted there unnoticed. A disclosure
that has drifted is worse than none: it is a false assurance shown at the exact
moment the operator is deciding.

Three groups are disclosed:

1. **Built-in adapters** (``api``, ``cli``, ``discord``) -- their tool services
   live under ``ciris_engine/logic/adapters/`` and are NOT visible to
   ``AdapterDiscoveryService`` (which only scans ``ciris_adapters/``). Their
   ``get_all_tool_info()`` is pure metadata, so it can be read before the
   adapter is configured. Disclosed as :attr:`ToolDisclosureSource.PROSPECTIVE`.

2. **Discovered adapters** under ``ciris_adapters/`` -- read via the existing
   :class:`AdapterDiscoveryService`, which already instantiates each adapter's
   tool service and calls ``get_all_tool_info()``.

3. **Always-on services** -- ``CoreToolService`` and ``ConsentService`` are
   registered as ``ServiceType.TOOL`` providers by ``ServiceInitializer``
   regardless of every adapter choice. They appear in no wizard list today and
   cannot be declined, so the disclosure says exactly that rather than omitting
   them.

The only hand-written mappings are the *pointers* to those tool service classes
(:data:`BUILTIN_TOOL_SERVICES`, :data:`ALWAYS_ON_TOOL_SERVICES`), never their
contents. ``tests/ciris_engine/logic/services/tool/test_tool_disclosure.py``
asserts both pointer sets are complete against the source tree and against
``ServiceInitializer``'s registrations, so adding a tool service without
disclosing it fails the build.
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from ciris_engine.schemas.adapters.tools import (
    AdapterToolDisclosure,
    ToolCapabilityFlag,
    ToolDisclosure,
    ToolDisclosureReport,
    ToolDisclosureSource,
    ToolInfo,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Capability derivation
#
# Derived from the tool's DECLARED PARAMETER SHAPE, not from its name. A tool is
# flagged because of what the model gets to fill in when calling it, so a new
# tool with the same shape is flagged automatically. Name-keyed classification
# is exactly the pattern that rotted `moderation_tools`.
# ============================================================================

_URL_PARAMS = frozenset({"url", "urls", "uri", "endpoint", "base_url", "target_url", "webhook_url"})
_HEADER_PARAMS = frozenset({"headers", "header", "auth_headers", "extra_headers"})
_BODY_PARAMS = frozenset({"data", "body", "payload", "json", "form", "files"})
_COMMAND_PARAMS = frozenset({"command", "cmd", "script", "shell", "shell_command", "args", "argv"})
_PATH_PARAMS = frozenset(
    {"path", "file_path", "filename", "file", "filepath", "target_path", "dest", "destination", "directory"}
)
_WRITE_PARAMS = frozenset({"content", "contents", "text", "data", "body", "bytes"})
_PLAINTEXT_PARAMS = frozenset({"decrypt", "reveal", "plaintext", "unmask", "show_value"})
_OTHER_PERSON_PARAMS = frozenset(
    {"user_id", "member_id", "guild_id", "recipient", "recipient_id", "target_user", "target_user_id", "to"}
)


def _parameter_names(tool: ToolInfo) -> List[str]:
    """Parameter names the model authors when calling this tool."""
    properties = tool.parameters.properties or {}
    return sorted(str(name) for name in properties)


def derive_capability_flags(tool: ToolInfo) -> List[ToolCapabilityFlag]:
    """Derive the consequential capabilities a tool grants from its live ToolInfo.

    Structural only -- parameter names plus ``dma_guidance``. No tool-name table.
    """
    params: Set[str] = {name.lower() for name in _parameter_names(tool)}
    flags: List[ToolCapabilityFlag] = []

    fetches = bool(params & _URL_PARAMS)
    if fetches:
        flags.append(ToolCapabilityFlag.NETWORK_FETCH)
    if params & _HEADER_PARAMS:
        flags.append(ToolCapabilityFlag.CUSTOM_HEADERS)
    if fetches and (params & _BODY_PARAMS):
        flags.append(ToolCapabilityFlag.REQUEST_BODY)
    if params & _COMMAND_PARAMS:
        flags.append(ToolCapabilityFlag.SHELL_EXECUTION)

    if params & _PATH_PARAMS:
        # A path plus a payload parameter means the tool puts bytes on disk.
        # A path alone means it reads them.
        if params & _WRITE_PARAMS and not fetches:
            flags.append(ToolCapabilityFlag.FILE_WRITE)
        else:
            flags.append(ToolCapabilityFlag.FILE_READ)

    if params & _PLAINTEXT_PARAMS:
        flags.append(ToolCapabilityFlag.SECRET_PLAINTEXT)
    if params & _OTHER_PERSON_PARAMS:
        flags.append(ToolCapabilityFlag.AFFECTS_OTHER_PEOPLE)
    if tool.dma_guidance is not None and tool.dma_guidance.requires_approval:
        flags.append(ToolCapabilityFlag.REQUIRES_APPROVAL)

    return flags


def disclose_tool(tool: ToolInfo) -> ToolDisclosure:
    """Project a live ToolInfo onto the wire shape the wizard renders."""
    return ToolDisclosure(
        name=tool.name,
        description=tool.description,
        category=tool.category,
        model_authored_parameters=_parameter_names(tool),
        capability_flags=derive_capability_flags(tool),
    )


# ============================================================================
# Tool service pointers
#
# Hand-written POINTERS to tool service classes -- never their contents. Guarded
# by tests that scan the source tree and ServiceInitializer for anything missing.
# ============================================================================

# Built-in adapters live under ciris_engine/logic/adapters/ and are invisible to
# AdapterDiscoveryService, which only scans ciris_adapters/. adapter_id here
# matches the id the setup wizard uses in its adapter list.
BUILTIN_TOOL_SERVICES: Dict[str, Tuple[str, str, str]] = {
    "api": (
        "ciris_engine.logic.adapters.api.api_tools",
        "APIToolService",
        "Web API",
    ),
    # NOTE: the CLI platform registers CLIAdapter itself as its ServiceType.TOOL
    # provider (ciris_engine/logic/adapters/cli/adapter.py:110-116), NOT the
    # CLIToolService in cli_tools.py. CLIToolService defines shell_command /
    # write_file / search_text but has no registration path, so enabling "cli"
    # does not grant them and the disclosure must not claim it does. The
    # provider-registration test below is what keeps this pointer honest.
    "cli": (
        "ciris_engine.logic.adapters.cli.cli_adapter",
        "CLIAdapter",
        "Command Line",
    ),
    "discord": (
        "ciris_engine.logic.adapters.discord.discord_tool_service",
        "DiscordToolService",
        "Discord",
    ),
}

# Registered as ServiceType.TOOL providers by ServiceInitializer regardless of
# every adapter choice. The wizard offers no way to decline these.
ALWAYS_ON_TOOL_SERVICES: Dict[str, Tuple[str, str, str]] = {
    "core_tools": (
        "ciris_engine.logic.services.tools.core_tool_service.service",
        "CoreToolService",
        "Core agent tools",
    ),
    "consent": (
        "ciris_engine.logic.services.governance.consent.service",
        "ConsentService",
        "Consent tools",
    ),
}

# The always-on services take live collaborators, but get_all_tool_info() on both
# is pure metadata and touches none of them. Passing None keeps enumeration
# side-effect-free at setup time, when those services may not exist yet.
_ENUMERATION_KWARGS: Dict[str, Dict[str, Any]] = {
    "CoreToolService": {"secrets_service": None, "time_service": None},
    "ConsentService": {"time_service": None},
}

_UNAVAILABLE_NOTE = (
    "This adapter's tool list can only be read after it loads with live credentials. "
    "Enabling it grants whatever tools it registers at that point."
)


async def _tools_from_service_class(
    module_path: str, class_name: str
) -> Tuple[ToolDisclosureSource, List[ToolInfo], Optional[str]]:
    """Read a tool service's own get_all_tool_info() without loading its adapter."""
    try:
        module = __import__(module_path, fromlist=[class_name])
        service_cls = getattr(module, class_name)
        service = service_cls(**_ENUMERATION_KWARGS.get(class_name, {}))
        tools: List[ToolInfo] = await service.get_all_tool_info()
        return ToolDisclosureSource.PROSPECTIVE, tools, None
    except Exception as e:  # pragma: no cover - defensive; reported honestly to the UI
        logger.warning("[TOOL DISCLOSURE] Could not enumerate %s.%s: %s", module_path, class_name, e)
        return ToolDisclosureSource.UNAVAILABLE, [], _UNAVAILABLE_NOTE


async def _disclose_service_group(
    adapter_id: str, module_path: str, class_name: str, display_name: str, always_on: bool
) -> AdapterToolDisclosure:
    source, tools, note = await _tools_from_service_class(module_path, class_name)
    return AdapterToolDisclosure(
        adapter_id=adapter_id,
        adapter_name=display_name,
        always_on=always_on,
        source=source,
        source_note=note,
        tools=[disclose_tool(t) for t in tools],
    )


async def _disclose_discovered_adapters(skip_ids: Set[str]) -> List[AdapterToolDisclosure]:
    """Disclose tools for adapters under ciris_adapters/ via the existing discovery service."""
    from .discovery_service import AdapterDiscoveryService

    groups: List[AdapterToolDisclosure] = []
    try:
        discovery = AdapterDiscoveryService()
        report = await discovery.get_discovery_report()
    except Exception as e:
        logger.warning("[TOOL DISCLOSURE] Adapter discovery failed: %s", e)
        return groups

    reported: Set[str] = set()
    for status in list(report.eligible) + list(report.ineligible):
        reported.add(status.name)
        if status.name in skip_ids:
            continue
        # An adapter whose tool service could not be enumerated must be disclosed
        # as unknown. An empty list would read as "grants nothing", which is false.
        if status.tools:
            source: ToolDisclosureSource = ToolDisclosureSource.PROSPECTIVE
            note: Optional[str] = None
        else:
            source = ToolDisclosureSource.UNAVAILABLE
            note = _UNAVAILABLE_NOTE
        groups.append(
            AdapterToolDisclosure(
                adapter_id=status.name,
                adapter_name=status.description or status.name,
                always_on=False,
                source=source,
                source_note=note,
                tools=[disclose_tool(t) for t in status.tools],
            )
        )

    # AdapterDiscoveryService drops an adapter entirely when its tool service
    # cannot be constructed without live collaborators (wallet, home_assistant),
    # so those never appear in either list. Silently omitting them is the same
    # failure as disclosing an empty tool list: the operator would conclude the
    # adapter grants nothing. Disclose them as unknown instead.
    try:
        for manifest in discovery.discover_adapters():
            name = manifest.module.name
            if name in reported or name in skip_ids:
                continue
            groups.append(
                AdapterToolDisclosure(
                    adapter_id=name,
                    adapter_name=manifest.module.description or name,
                    always_on=False,
                    source=ToolDisclosureSource.UNAVAILABLE,
                    source_note=_UNAVAILABLE_NOTE,
                    tools=[],
                )
            )
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[TOOL DISCLOSURE] Could not list undisclosed manifests: %s", e)

    return groups


async def build_tool_disclosure(include_discovered: bool = True) -> ToolDisclosureReport:
    """Build the complete tool disclosure from the live tool services.

    Args:
        include_discovered: Also enumerate adapters under ``ciris_adapters/``.
            Instantiating ~60 third-party adapters is slow, so callers that only
            need the built-in and always-on grants can turn it off.

    Returns:
        A :class:`ToolDisclosureReport` whose every entry was read from a real
        ``get_all_tool_info()`` call.
    """
    adapters: List[AdapterToolDisclosure] = []
    always_on: List[AdapterToolDisclosure] = []

    for adapter_id, (module_path, class_name, display_name) in BUILTIN_TOOL_SERVICES.items():
        adapters.append(
            await _disclose_service_group(adapter_id, module_path, class_name, display_name, always_on=False)
        )

    for group_id, (module_path, class_name, display_name) in ALWAYS_ON_TOOL_SERVICES.items():
        always_on.append(
            await _disclose_service_group(group_id, module_path, class_name, display_name, always_on=True)
        )

    if include_discovered:
        adapters.extend(await _disclose_discovered_adapters(skip_ids=set(BUILTIN_TOOL_SERVICES)))

    total = sum(len(g.tools) for g in adapters) + sum(len(g.tools) for g in always_on)
    return ToolDisclosureReport(adapters=adapters, always_on=always_on, total_tools=total)


__all__ = [
    "ALWAYS_ON_TOOL_SERVICES",
    "BUILTIN_TOOL_SERVICES",
    "build_tool_disclosure",
    "derive_capability_flags",
    "disclose_tool",
]
