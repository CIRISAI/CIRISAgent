"""Desktop-only host tools on the CLI adapter (#941).

Covers the three things that must stay true:

1. The platform predicate (``is_desktop``) is exercised against real platform
   signals -- ``ANDROID_ROOT``, Chaquopy's ``sys.getandroidapilevel``,
   ``sys.platform`` -- not mocked into always-true, and it **fails closed** on an
   unrecognized platform.
2. A desktop install can actually reach ``shell_command`` and ``write_file``
   *through ToolBus*, because a registered-but-unreachable tool serves nobody.
3. A mobile install can reach neither, proven by executing them through ToolBus
   and getting NOT_FOUND -- not by reading the source.

Plus the collision property: the CLI platform registers exactly one
``ServiceType.TOOL`` provider on every platform, so no tool name is ever served
by two providers and ToolBus's multi-provider fallback never has to guess.
"""

import sys
from datetime import datetime, timezone
from typing import List
from unittest.mock import Mock, patch

import pytest

from ciris_engine.logic.adapters.cli.adapter import CliPlatform
from ciris_engine.logic.adapters.cli.cli_adapter import DESKTOP_ONLY_TOOLS, CLIAdapter
from ciris_engine.logic.adapters.cli.cli_tools import CLIToolService
from ciris_engine.logic.buses.tool_bus import ToolBus
from ciris_engine.logic.registries.base import Priority, ServiceRegistry
from ciris_engine.logic.utils.platform_detection import DESKTOP_PLATFORM_NAMES, get_platform_name, is_desktop
from ciris_engine.schemas.adapters.tools import ToolExecutionStatus
from ciris_engine.schemas.runtime.enums import ServiceType

CLI_OWN_TOOLS = ("list_files", "read_file", "system_info")


# ============================================================================
# Platform simulation helpers
#
# These drive the REAL predicate through the REAL platform signals. Nothing here
# patches is_desktop() or is_android() -- the point is to exercise the predicate,
# not to assert that a stub returns what it was told to return.
# ============================================================================


def _clear_platform_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANDROID_ROOT", raising=False)
    monkeypatch.delenv("ANDROID_DATA", raising=False)
    monkeypatch.delattr(sys, "getandroidapilevel", raising=False)


def make_desktop(monkeypatch: pytest.MonkeyPatch, platform: str = "linux") -> None:
    """Present the process as a desktop host."""
    _clear_platform_env(monkeypatch)
    monkeypatch.setattr(sys, "platform", platform)


def make_android(monkeypatch: pytest.MonkeyPatch) -> None:
    """Present the process as Android, the way the Android system does."""
    _clear_platform_env(monkeypatch)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("ANDROID_ROOT", "/system")


def make_android_chaquopy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Present the process as Android the way Chaquopy does (no env vars)."""
    _clear_platform_env(monkeypatch)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sys, "getandroidapilevel", lambda: 34, raising=False)


def make_ios(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_platform_env(monkeypatch)
    monkeypatch.setattr(sys, "platform", "ios")


def make_unknown_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_platform_env(monkeypatch)
    monkeypatch.setattr(sys, "platform", "sunos5")


@pytest.fixture
def time_service() -> Mock:
    svc = Mock()
    now = datetime.now(timezone.utc)
    svc.now.return_value = now
    svc.timestamp.return_value = now.timestamp()
    return svc


def build_adapter(time_service: Mock) -> CLIAdapter:
    """Construct a CLIAdapter usable for tool execution without a live runtime."""
    adapter = CLIAdapter(runtime=None, interactive=False)
    adapter._time_service = time_service
    # ServiceRegistry lookups are health-gated; a registered adapter is running.
    adapter._running = True
    return adapter


def build_bus(adapter: CLIAdapter, time_service: Mock) -> ToolBus:
    """Register the adapter exactly as CliPlatform does, then wire a ToolBus."""
    registry = ServiceRegistry()
    registry.register_service(
        service_type=ServiceType.TOOL,
        provider=adapter,
        priority=Priority.LOW,
        capabilities=["execute_tool", "get_available_tools", "get_tool_result", "validate_parameters"],
    )
    return ToolBus(service_registry=registry, time_service=time_service)


# ============================================================================
# The predicate itself
# ============================================================================


class TestIsDesktopPredicate:
    @pytest.mark.parametrize(
        "platform,expected_name",
        [("linux", "linux"), ("linux2", "linux"), ("darwin", "macos"), ("win32", "windows")],
    )
    def test_desktop_platforms_are_desktop(
        self, monkeypatch: pytest.MonkeyPatch, platform: str, expected_name: str
    ) -> None:
        make_desktop(monkeypatch, platform)
        assert get_platform_name() == expected_name
        assert expected_name in DESKTOP_PLATFORM_NAMES
        assert is_desktop() is True

    def test_android_env_is_not_desktop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        make_android(monkeypatch)
        assert get_platform_name() == "android"
        assert is_desktop() is False

    def test_android_chaquopy_is_not_desktop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Chaquopy hosts the runtime inside the Android app and sets no env vars."""
        make_android_chaquopy(monkeypatch)
        assert get_platform_name() == "android"
        assert is_desktop() is False

    def test_ios_is_not_desktop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        make_ios(monkeypatch)
        assert get_platform_name() == "ios"
        assert is_desktop() is False

    def test_unknown_platform_fails_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An unrecognized platform must lose the capability, never gain it."""
        make_unknown_platform(monkeypatch)
        assert get_platform_name() == "unknown"
        assert "unknown" not in DESKTOP_PLATFORM_NAMES
        assert is_desktop() is False


# ============================================================================
# What the adapter exposes, per platform
# ============================================================================


class TestDesktopToolSurface:
    def test_desktop_exposes_host_tools(self, monkeypatch: pytest.MonkeyPatch, time_service: Mock) -> None:
        make_desktop(monkeypatch)
        adapter = build_adapter(time_service)
        tools = adapter._available_tools

        for name in CLI_OWN_TOOLS:
            assert name in tools
        for name in DESKTOP_ONLY_TOOLS:
            assert name in tools, f"{name} must be available on a desktop install"
        assert "shell_command" in tools
        assert "write_file" in tools

    @pytest.mark.asyncio
    async def test_desktop_tool_metadata_comes_from_cli_tool_service(
        self, monkeypatch: pytest.MonkeyPatch, time_service: Mock
    ) -> None:
        """Metadata is read from CLIToolService, never restated on the adapter.

        This is also what makes the generated first-run tool disclosure correct:
        it calls get_all_tool_info() on the registered provider.
        """
        make_desktop(monkeypatch)
        adapter = build_adapter(time_service)

        shell = await adapter.get_tool_info("shell_command")
        assert shell is not None
        assert shell.dma_guidance is not None
        assert shell.dma_guidance.requires_approval is True
        # The rich documentation is CLIToolService's, proving delegation not duplication.
        assert shell.documentation is not None
        # The disclosure generator derives capability flags from parameter names.
        assert sorted((shell.parameters.properties or {}).keys()) == ["command"]

        write = await adapter.get_tool_info("write_file")
        assert write is not None
        assert sorted((write.parameters.properties or {}).keys()) == ["content", "path"]

        names = {info.name for info in await adapter.get_all_tool_info()}
        assert {"shell_command", "write_file", "search_text"} <= names

    @pytest.mark.asyncio
    async def test_desktop_validates_host_tool_parameters(
        self, monkeypatch: pytest.MonkeyPatch, time_service: Mock
    ) -> None:
        make_desktop(monkeypatch)
        adapter = build_adapter(time_service)

        assert await adapter.validate_parameters("shell_command", {"command": "true"}) is True
        assert await adapter.validate_parameters("shell_command", {"path": "/tmp"}) is False
        assert await adapter.validate_parameters("write_file", {"path": "/tmp/x", "content": "y"}) is True
        assert await adapter.validate_parameters("write_file", {"path": "/tmp/x"}) is False


class TestMobileToolSurface:
    """The mobile denial, proven by execution rather than inspection."""

    @pytest.mark.parametrize("make_mobile", [make_android, make_android_chaquopy, make_ios, make_unknown_platform])
    def test_mobile_has_no_host_tools(
        self, monkeypatch: pytest.MonkeyPatch, time_service: Mock, make_mobile: object
    ) -> None:
        make_mobile(monkeypatch)  # type: ignore[operator]
        adapter = build_adapter(time_service)

        assert sorted(adapter._available_tools) == sorted(CLI_OWN_TOOLS)
        assert "shell_command" not in adapter._available_tools
        assert "write_file" not in adapter._available_tools
        assert adapter._desktop_tools is None

    @pytest.mark.asyncio
    async def test_mobile_reports_no_metadata_for_host_tools(
        self, monkeypatch: pytest.MonkeyPatch, time_service: Mock
    ) -> None:
        make_android(monkeypatch)
        adapter = build_adapter(time_service)

        assert await adapter.get_tool_info("shell_command") is None
        assert await adapter.get_tool_info("write_file") is None
        assert await adapter.get_tool_schema("shell_command") is None
        assert await adapter.validate_parameters("shell_command", {"command": "true"}) is False

        names = {info.name for info in await adapter.get_all_tool_info()}
        assert names == set(CLI_OWN_TOOLS)


# ============================================================================
# Reachability through ToolBus -- the only measure that matters to the agent
# ============================================================================


class TestReachabilityThroughToolBus:
    @pytest.mark.asyncio
    async def test_desktop_shell_command_is_reachable(
        self, monkeypatch: pytest.MonkeyPatch, time_service: Mock
    ) -> None:
        make_desktop(monkeypatch)
        adapter = build_adapter(time_service)
        bus = build_bus(adapter, time_service)

        with patch("ciris_engine.logic.adapters.cli.cli_adapter.persistence.add_correlation"):
            result = await bus.execute_tool("shell_command", {"command": "echo ciris-941"})

        assert result.status == ToolExecutionStatus.COMPLETED
        assert result.success is True
        assert result.data is not None
        assert "ciris-941" in str(result.data.get("stdout"))
        assert result.data.get("returncode") == 0

    @pytest.mark.asyncio
    async def test_desktop_write_file_is_reachable(
        self, monkeypatch: pytest.MonkeyPatch, time_service: Mock, tmp_path: object
    ) -> None:
        """A real write to a real path -- this is the capability being granted."""
        make_desktop(monkeypatch)
        adapter = build_adapter(time_service)
        bus = build_bus(adapter, time_service)
        target = tmp_path / "written_by_agent.txt"  # type: ignore[operator]

        with patch("ciris_engine.logic.adapters.cli.cli_adapter.persistence.add_correlation"):
            result = await bus.execute_tool("write_file", {"path": str(target), "content": "hello from #941"})

        assert result.status == ToolExecutionStatus.COMPLETED
        assert result.success is True
        assert target.read_text() == "hello from #941"  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_desktop_failed_host_tool_reports_failure(
        self, monkeypatch: pytest.MonkeyPatch, time_service: Mock
    ) -> None:
        """CLIToolService results signal failure via `error` alone, with no
        `success` key. The adapter must not report those as successes."""
        make_desktop(monkeypatch)
        adapter = build_adapter(time_service)
        bus = build_bus(adapter, time_service)

        with patch("ciris_engine.logic.adapters.cli.cli_adapter.persistence.add_correlation"):
            result = await bus.execute_tool("write_file", {"path": "/nonexistent-dir-941/x.txt", "content": "x"})

        assert result.success is False
        assert result.status == ToolExecutionStatus.FAILED
        assert result.error is not None

    @pytest.mark.parametrize("tool_name", ["shell_command", "write_file", "search_text"])
    @pytest.mark.asyncio
    async def test_mobile_host_tools_are_not_reachable(
        self, monkeypatch: pytest.MonkeyPatch, time_service: Mock, tool_name: str
    ) -> None:
        """The load-bearing denial: ToolBus itself cannot find these on mobile."""
        make_android(monkeypatch)
        adapter = build_adapter(time_service)
        bus = build_bus(adapter, time_service)

        with patch("ciris_engine.logic.adapters.cli.cli_adapter.persistence.add_correlation"):
            result = await bus.execute_tool(tool_name, {"command": "echo pwned", "path": "/tmp/x", "content": "x"})

        assert result.status == ToolExecutionStatus.NOT_FOUND
        assert result.success is False
        # And the bus does not advertise it either -- against a live, non-empty
        # tool list, so this is a real absence rather than an empty lookup.
        advertised = await bus.get_available_tools()
        assert advertised, "bus must see the CLI adapter for this assertion to mean anything"
        assert tool_name not in advertised

    @pytest.mark.asyncio
    async def test_mobile_keeps_its_existing_tools(self, monkeypatch: pytest.MonkeyPatch, time_service: Mock) -> None:
        """Denying the host tools must not cost mobile anything it had."""
        make_android(monkeypatch)
        adapter = build_adapter(time_service)
        bus = build_bus(adapter, time_service)

        assert sorted(await bus.get_available_tools()) == sorted(CLI_OWN_TOOLS)


# ============================================================================
# No ambiguous tool-name collision
# ============================================================================


class TestNoProviderCollision:
    @pytest.mark.parametrize("make_platform", [make_desktop, make_android])
    def test_cli_platform_registers_exactly_one_tool_provider(
        self, monkeypatch: pytest.MonkeyPatch, make_platform: object
    ) -> None:
        """Two providers for one adapter would make ToolBus choose between
        aliases of one surface. The CLI platform registers exactly one, and it
        is the adapter itself -- which is also the anchor the generated wizard
        tool-disclosure drift guard resolves (`provider=self.<attr>`)."""
        make_platform(monkeypatch)  # type: ignore[operator]
        runtime = Mock()
        runtime.bus_manager = None
        runtime.template = None
        platform = CliPlatform(runtime=runtime)

        tool_regs = [r for r in platform.get_services_to_register() if r.service_type == ServiceType.TOOL]
        assert len(tool_regs) == 1
        assert tool_regs[0].provider is platform.cli_adapter

    def test_overlapping_names_resolve_to_one_implementation(
        self, monkeypatch: pytest.MonkeyPatch, time_service: Mock
    ) -> None:
        """`list_files` / `read_file` exist on both classes. The adapter's own
        implementations win; CLIToolService contributes only the names the
        adapter does not already have."""
        make_desktop(monkeypatch)
        adapter = build_adapter(time_service)

        assert adapter._available_tools["list_files"] == adapter._tool_list_files
        assert adapter._available_tools["read_file"] == adapter._tool_read_file
        assert not set(DESKTOP_ONLY_TOOLS) & set(CLI_OWN_TOOLS)

        borrowed = set(CLIToolService().get_tool_callable(n) is not None for n in DESKTOP_ONLY_TOOLS)
        assert borrowed == {True}

    @pytest.mark.asyncio
    async def test_each_tool_name_has_exactly_one_supporting_provider(
        self, monkeypatch: pytest.MonkeyPatch, time_service: Mock
    ) -> None:
        """The condition ToolBus's fallback branch (tool_bus.py:140-172) needs to
        never be entered for CLI tools."""
        make_desktop(monkeypatch)
        adapter = build_adapter(time_service)
        registry = ServiceRegistry()
        registry.register_service(service_type=ServiceType.TOOL, provider=adapter, priority=Priority.LOW)

        providers = registry._services.get(ServiceType.TOOL, [])
        for tool_name in await adapter.get_available_tools():
            supporting: List[object] = [
                p.instance for p in providers if tool_name in await p.instance.get_available_tools()
            ]
            assert len(supporting) == 1, f"{tool_name} is served by {len(supporting)} providers"
