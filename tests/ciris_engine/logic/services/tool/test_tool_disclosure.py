"""Drift protection for the first-run wizard's tool disclosure (#941).

This is the load-bearing test of that feature. The disclosure exists so the
operator accepting the enabled-by-default optional features is told what those
choices actually grant the agent. A disclosure that has drifted from the
implementation is worse than no disclosure at all -- it is a false assurance
shown at the exact moment the operator is deciding.

The cautionary case is in this repo: ``moderation_tools`` in
``ciris_templates/echo.yaml`` names ``discord_slowmode``, which does not exist in
the Discord tool service, and has sat there unnoticed because nothing checked it.

What these tests catch:

* a tool appearing in the disclosure that no tool service actually registers
  (the ``discord_slowmode`` failure mode), and the reverse -- a tool a service
  registers that the disclosure omits;
* a new built-in adapter tool service that nobody added to the disclosure;
* a third always-on tool service registered by ``ServiceInitializer`` that would
  otherwise silently join the set the operator cannot decline;
* a consequential capability (arbitrary fetch, model-authored headers, shell
  execution, plaintext secret retrieval) losing its derived flag and so becoming
  invisible at the consent point.

None of this restricts anything. Wide tool access is intended; these tests only
keep the disclosure of it true.
"""

import re
from pathlib import Path
from typing import Set

import pytest

from ciris_engine.logic.services.tool.tool_disclosure import (
    ALWAYS_ON_TOOL_SERVICES,
    BUILTIN_TOOL_SERVICES,
    build_tool_disclosure,
    derive_capability_flags,
    disclose_tool,
)
from ciris_engine.schemas.adapters.tools import (
    ToolCapabilityFlag,
    ToolDisclosureSource,
    ToolDMAGuidance,
    ToolInfo,
    ToolParameterSchema,
)

REPO_ROOT = Path(__file__).resolve().parents[5]
BUILTIN_ADAPTER_DIR = REPO_ROOT / "ciris_engine" / "logic" / "adapters"
SERVICE_INITIALIZER = REPO_ROOT / "ciris_engine" / "logic" / "runtime" / "service_initializer.py"


def _tool(name: str, properties: dict, **kwargs) -> ToolInfo:
    return ToolInfo(
        name=name,
        description=kwargs.pop("description", "test tool"),
        parameters=ToolParameterSchema(type="object", properties=properties),
        **kwargs,
    )


async def _instantiate(module_path: str, class_name: str):
    """Instantiate a tool service exactly the way the disclosure generator does."""
    from ciris_engine.logic.services.tool.tool_disclosure import _ENUMERATION_KWARGS

    module = __import__(module_path, fromlist=[class_name])
    return getattr(module, class_name)(**_ENUMERATION_KWARGS.get(class_name, {}))


# ============================================================================
# The core drift guard: disclosure names == registered names, per service
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter_id", sorted(BUILTIN_TOOL_SERVICES))
async def test_builtin_disclosure_matches_registered_tools(adapter_id: str) -> None:
    """Disclosed tool names must equal what the tool service actually registers.

    This is the check that ``moderation_tools`` never had. A disclosure naming a
    tool the service does not provide fails here, and so does a service tool the
    disclosure omits.
    """
    module_path, class_name, _ = BUILTIN_TOOL_SERVICES[adapter_id]
    service = await _instantiate(module_path, class_name)

    registered: Set[str] = set(await service.get_available_tools())
    report = await build_tool_disclosure(include_discovered=False)
    group = next(g for g in report.adapters if g.adapter_id == adapter_id)
    disclosed: Set[str] = {t.name for t in group.tools}

    assert disclosed == registered, (
        f"tool disclosure for '{adapter_id}' has drifted from the tool service.\n"
        f"  disclosed but not registered: {sorted(disclosed - registered)}\n"
        f"  registered but not disclosed: {sorted(registered - disclosed)}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("group_id", sorted(ALWAYS_ON_TOOL_SERVICES))
async def test_always_on_disclosure_matches_registered_tools(group_id: str) -> None:
    """Same parity check for the tools no wizard choice controls."""
    module_path, class_name, _ = ALWAYS_ON_TOOL_SERVICES[group_id]
    service = await _instantiate(module_path, class_name)

    registered: Set[str] = set(await service.get_available_tools())
    report = await build_tool_disclosure(include_discovered=False)
    group = next(g for g in report.always_on if g.adapter_id == group_id)
    disclosed: Set[str] = {t.name for t in group.tools}

    assert disclosed == registered, (
        f"always-on tool disclosure for '{group_id}' has drifted.\n"
        f"  disclosed but not registered: {sorted(disclosed - registered)}\n"
        f"  registered but not disclosed: {sorted(registered - disclosed)}"
    )


# ============================================================================
# Completeness: no tool service may exist without being disclosed
# ============================================================================


def _self_attr_classes(source: str) -> dict:
    """Map ``self.<attr>`` -> the class name assigned to it."""
    return dict(re.findall(r"self\.(\w+)\s*(?::[^=\n]+)?=\s*([A-Z]\w+)\s*\(", source))


def _tool_provider_classes(path: Path) -> Set[str]:
    """Classes registered as ``ServiceType.TOOL`` providers in ``path``.

    Anchored on the registration itself (``service_type=ServiceType.TOOL`` with a
    ``provider=self.<attr>``) rather than on which classes happen to define
    ``get_all_tool_info``. That distinction matters: the CLI platform registers
    ``CLIAdapter``, not the ``CLIToolService`` that also defines the method and
    that nothing registers.
    """
    source = path.read_text(encoding="utf-8")
    assigns = _self_attr_classes(source)
    providers: Set[str] = set()
    for match in re.finditer(r"service_type=ServiceType\.TOOL", source):
        window = source[match.end() : match.end() + 400]
        provider = re.search(r"provider=self\.(\w+)", window)
        if provider and provider.group(1) in assigns:
            providers.add(assigns[provider.group(1)])
    return providers


def test_every_builtin_adapter_tool_provider_is_disclosed() -> None:
    """A built-in adapter's registered TOOL provider must be in the disclosure.

    Built-in adapters live under ``ciris_engine/logic/adapters/`` and are invisible
    to ``AdapterDiscoveryService`` (which only scans ``ciris_adapters/``), so
    nothing else would ever notice one was missing.
    """
    declared = {class_name for _, class_name, _ in BUILTIN_TOOL_SERVICES.values()}
    found: Set[str] = set()
    for adapter_py in BUILTIN_ADAPTER_DIR.rglob("adapter.py"):
        found |= _tool_provider_classes(adapter_py)

    assert found, (
        "found no ServiceType.TOOL provider registrations under "
        f"{BUILTIN_ADAPTER_DIR} -- this drift guard has lost its anchor and must "
        "be repaired, not deleted."
    )

    undisclosed = found - declared
    assert not undisclosed, (
        "built-in adapter(s) register tool provider(s) the first-run wizard never "
        f"discloses: {sorted(undisclosed)}. Add them to BUILTIN_TOOL_SERVICES in "
        "ciris_engine/logic/services/tool/tool_disclosure.py."
    )


def test_disclosed_builtin_pointers_are_actually_registered() -> None:
    """The reverse: the disclosure must not name a provider nothing registers.

    Disclosing tools from a class the runtime never registers is the same class of
    lie as ``discord_slowmode`` -- it would tell the operator they are granting
    something they are not, and hide what they actually are.
    """
    registered: Set[str] = set()
    for adapter_py in BUILTIN_ADAPTER_DIR.rglob("adapter.py"):
        registered |= _tool_provider_classes(adapter_py)

    declared = {class_name for _, class_name, _ in BUILTIN_TOOL_SERVICES.values()}
    phantom = declared - registered
    assert not phantom, (
        f"the wizard discloses tools from {sorted(phantom)}, but no built-in adapter "
        "registers that class as a ServiceType.TOOL provider."
    )


def test_every_always_on_tool_registration_is_disclosed() -> None:
    """Every core ``ServiceType.TOOL`` provider ServiceInitializer registers must
    appear in the always-on disclosure.

    These are the tools that appear in no wizard list and that the operator has no
    way to decline. Adding a third one without disclosing it fails here.

    Resolved through ``provider=self.<attr>`` to the class actually constructed,
    not through the registration metadata: that metadata still says
    ``"service_name": "SecretsToolService"`` while the provider is a
    ``CoreToolService``, so trusting the label would reintroduce the very drift
    this test exists to prevent.
    """
    source = SERVICE_INITIALIZER.read_text(encoding="utf-8")
    assigns = _self_attr_classes(source)

    registered_classes: Set[str] = set()
    for match in re.finditer(r"service_type=ServiceType\.TOOL", source):
        window = source[match.end() : match.end() + 1200]
        provider = re.search(r"provider=self\.(\w+)", window)
        # Only core providers are registered regardless of adapter choice;
        # adapter-supplied TOOL services arrive with their adapter.
        is_core = re.search(r'"provider":\s*"core"', window)
        if provider and is_core and provider.group(1) in assigns:
            registered_classes.add(assigns[provider.group(1)])

    assert registered_classes, (
        "could not find any core ServiceType.TOOL registrations in "
        "service_initializer.py -- the always-on drift guard has lost its anchor "
        "and must be repaired, not deleted."
    )

    disclosed = {class_name for _, class_name, _ in ALWAYS_ON_TOOL_SERVICES.values()}
    undisclosed = registered_classes - disclosed
    assert not undisclosed, (
        "core tool service(s) are registered regardless of every wizard choice but "
        f"are never disclosed to the operator: {sorted(undisclosed)}. Add them to "
        "ALWAYS_ON_TOOL_SERVICES in ciris_engine/logic/services/tool/tool_disclosure.py."
    )


# ============================================================================
# Capability derivation is structural, not a name table
# ============================================================================


@pytest.mark.parametrize(
    "properties,expected",
    [
        ({"url": {}}, ToolCapabilityFlag.NETWORK_FETCH),
        ({"headers": {}}, ToolCapabilityFlag.CUSTOM_HEADERS),
        ({"command": {}}, ToolCapabilityFlag.SHELL_EXECUTION),
        ({"path": {}}, ToolCapabilityFlag.FILE_READ),
        ({"path": {}, "content": {}}, ToolCapabilityFlag.FILE_WRITE),
        ({"decrypt": {}}, ToolCapabilityFlag.SECRET_PLAINTEXT),
        ({"user_id": {}}, ToolCapabilityFlag.AFFECTS_OTHER_PEOPLE),
    ],
)
def test_capability_flags_derive_from_parameter_shape(properties: dict, expected: ToolCapabilityFlag) -> None:
    """Flags come from the declared parameter shape, so a brand-new tool with the
    same shape is flagged automatically. Name-keyed classification is exactly the
    pattern that rotted ``moderation_tools``."""
    flags = derive_capability_flags(_tool("a_tool_nobody_has_heard_of", properties))
    assert expected in flags


def test_request_body_requires_a_fetch_target() -> None:
    """A ``data`` parameter alone is not an egress signal; ``data`` plus a URL is."""
    assert ToolCapabilityFlag.REQUEST_BODY not in derive_capability_flags(_tool("t", {"data": {}}))
    assert ToolCapabilityFlag.REQUEST_BODY in derive_capability_flags(_tool("t", {"url": {}, "data": {}}))


def test_requires_approval_comes_from_dma_guidance() -> None:
    assert ToolCapabilityFlag.REQUIRES_APPROVAL in derive_capability_flags(
        _tool("t", {}, dma_guidance=ToolDMAGuidance(requires_approval=True))
    )
    assert ToolCapabilityFlag.REQUIRES_APPROVAL not in derive_capability_flags(_tool("t", {}))


def test_disclosure_copies_tool_metadata_verbatim() -> None:
    """Name, description and category are copied, never re-authored."""
    tool = _tool("some_tool", {"b": {}, "a": {}}, description="Does a thing", category="widgets")
    disclosed = disclose_tool(tool)
    assert disclosed.name == "some_tool"
    assert disclosed.description == "Does a thing"
    assert disclosed.category == "widgets"
    # Sorted for stable rendering, but complete.
    assert disclosed.model_authored_parameters == ["a", "b"]


# ============================================================================
# The uncomfortable grants must actually reach the consent point
# ============================================================================


@pytest.mark.asyncio
async def test_consequential_capabilities_are_flagged_on_the_live_tools() -> None:
    """Invariant over whatever the tool services currently declare.

    Phrased against the live parameter schema rather than a hardcoded expectation,
    so it stays true if a tool's shape legitimately changes -- while still failing
    if the derivation stops working.
    """
    report = await build_tool_disclosure(include_discovered=False)
    all_tools = [t for g in report.adapters + report.always_on for t in g.tools]
    assert all_tools, "disclosure produced no tools at all"

    for tool in all_tools:
        params = {p.lower() for p in tool.model_authored_parameters}
        if "url" in params:
            assert ToolCapabilityFlag.NETWORK_FETCH in tool.capability_flags, tool.name
        if "headers" in params:
            assert ToolCapabilityFlag.CUSTOM_HEADERS in tool.capability_flags, tool.name
        if "command" in params:
            assert ToolCapabilityFlag.SHELL_EXECUTION in tool.capability_flags, tool.name
        if "decrypt" in params:
            assert ToolCapabilityFlag.SECRET_PLAINTEXT in tool.capability_flags, tool.name


@pytest.mark.asyncio
async def test_default_adapter_egress_is_disclosed() -> None:
    """``api`` is the default adapter, so its egress tools are what most operators
    are actually accepting. They ship enabled on purpose -- and must be visible."""
    report = await build_tool_disclosure(include_discovered=False)
    api = next(g for g in report.adapters if g.adapter_id == "api")
    by_name = {t.name: t for t in api.tools}

    assert "curl" in by_name, "the default adapter's HTTP tool is not disclosed"
    curl = by_name["curl"]
    # The header surface is the part an operator would not guess from "curl".
    assert "headers" in curl.model_authored_parameters
    assert ToolCapabilityFlag.CUSTOM_HEADERS in curl.capability_flags
    assert ToolCapabilityFlag.NETWORK_FETCH in curl.capability_flags


@pytest.mark.asyncio
async def test_plaintext_secret_tool_is_disclosed_as_undeclinable() -> None:
    """``recall_secret`` returns plaintext secret material and is registered
    regardless of every adapter choice. It appeared in no wizard list before #941."""
    report = await build_tool_disclosure(include_discovered=False)
    always_on_tools = {t.name: (g, t) for g in report.always_on for t in g.tools}

    assert "recall_secret" in always_on_tools
    group, tool = always_on_tools["recall_secret"]
    assert group.always_on is True
    assert ToolCapabilityFlag.SECRET_PLAINTEXT in tool.capability_flags


@pytest.mark.asyncio
async def test_discord_moderation_tools_are_disclosed() -> None:
    """Enabling Discord grants moderation inseparably from messaging. Both halves
    must be visible; the template text that used to stand in for this had drifted."""
    report = await build_tool_disclosure(include_discovered=False)
    discord = next(g for g in report.adapters if g.adapter_id == "discord")
    names = {t.name for t in discord.tools}

    assert "discord_send_message" in names
    for destructive in ("discord_ban_user", "discord_kick_user", "discord_timeout_user"):
        assert destructive in names, f"{destructive} is granted but not disclosed"


# ============================================================================
# Report shape / honesty about what is not known
# ============================================================================


@pytest.mark.asyncio
async def test_report_marks_always_on_groups_and_counts_every_tool() -> None:
    report = await build_tool_disclosure(include_discovered=False)

    assert all(g.always_on for g in report.always_on)
    assert not any(g.always_on for g in report.adapters)
    expected = sum(len(g.tools) for g in report.adapters) + sum(len(g.tools) for g in report.always_on)
    assert report.total_tools == expected


@pytest.mark.asyncio
async def test_unenumerable_service_is_disclosed_as_unknown_not_empty() -> None:
    """An adapter whose tools cannot be read must say so.

    Reporting an empty list would read as "this grants nothing", which is the
    precise false assurance the disclosure exists to remove.
    """
    from ciris_engine.logic.services.tool.tool_disclosure import _tools_from_service_class

    source, tools, note = await _tools_from_service_class(
        "ciris_engine.logic.services.tool.does_not_exist", "NoSuchService"
    )
    assert source == ToolDisclosureSource.UNAVAILABLE
    assert tools == []
    assert note and "after it loads" in note


@pytest.mark.asyncio
async def test_no_discovered_adapter_is_silently_omitted() -> None:
    """Every adapter manifest on disk must reach the disclosure somehow.

    ``AdapterDiscoveryService`` drops an adapter entirely when its tool service
    cannot be constructed without live collaborators -- ``wallet`` (send_money)
    and ``home_assistant`` (device control) both fall out this way. Omitting them
    is the same failure as disclosing an empty list: the operator would conclude
    the adapter grants nothing. They must appear, marked unknown.
    """
    from ciris_engine.logic.services.tool.discovery_service import AdapterDiscoveryService

    on_disk = {m.module.name for m in AdapterDiscoveryService().discover_adapters()}
    report = await build_tool_disclosure(include_discovered=True)
    disclosed = {g.adapter_id for g in report.adapters}

    # Built-in adapters are disclosed under their own ids, not via manifests.
    missing = on_disk - disclosed - set(BUILTIN_TOOL_SERVICES)
    assert not missing, (
        f"adapter manifest(s) exist on disk but reach the wizard's disclosure not at all: "
        f"{sorted(missing)}. Silently omitting one reads as 'grants nothing'."
    )


@pytest.mark.asyncio
async def test_every_disclosed_adapter_has_tools_or_says_why_not() -> None:
    report = await build_tool_disclosure(include_discovered=False)
    for group in report.adapters + report.always_on:
        if not group.tools:
            assert group.source == ToolDisclosureSource.UNAVAILABLE and group.source_note, (
                f"'{group.adapter_id}' discloses an empty tool list with no explanation, "
                "which reads as 'grants nothing'"
            )
