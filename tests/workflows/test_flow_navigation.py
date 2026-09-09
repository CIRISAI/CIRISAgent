"""The runner reaches a CSD flow's starting screen through the sidebar (FSD/CSD_STANDARD.md §5).

Tags are the client's own rule (EpistemicSidebar.kt), never guessed; a collapsed
group is opened only until the row appears and restored when it was the wrong one.
"""

from __future__ import annotations

from typing import Dict, List

import pytest

from tools.qa_runner.modules.web_ui.desktop_app_helper import NESTED_SURFACE_PARENT, DesktopAppHelper, surface_tag


@pytest.mark.parametrize(
    "screen,tag",
    [
        ("LayerFamily", "nav_epistemic_layer_family"),
        ("LayerLocalCommunity", "nav_epistemic_layer_local_community"),
        ("Constitutional", "nav_epistemic_constitutional"),
        ("HealthReputation", "nav_epistemic_health_reputation"),
        ("LayerGlobalCommons", "nav_epistemic_layer_global_commons"),
    ],
)
def test_the_sidebar_tag_follows_the_clients_rule(screen: str, tag: str) -> None:
    assert surface_tag(screen) == tag


def test_child_surfaces_name_their_parent() -> None:
    assert NESTED_SURFACE_PARENT["constitutional"] == "LayerGlobalCommons"
    assert NESTED_SURFACE_PARENT["delegation"] == "LayerFamily"


class _Row:
    def __init__(self, tag: str, visible: bool) -> None:
        self.test_tag, self.visible, self.width, self.height = tag, visible, 10, 10


class _FakeSidebar(DesktopAppHelper):
    """Two collapsed groups; the wanted row lives in the second one."""

    def __init__(self) -> None:  # no network
        self.screen = "Interact"
        self.expanded: Dict[str, bool] = {"nav_group_manage": False, "nav_group_commons-layers": False}
        self.clicks: List[str] = []

    async def get_screen(self) -> str:
        return self.screen

    async def get_elements(self):  # type: ignore[override]
        rows = [_Row(g, True) for g in self.expanded]
        rows.append(_Row("nav_epistemic_layer_family", self.expanded["nav_group_commons-layers"]))
        rows.append(_Row("nav_epistemic_health_reputation", self.expanded["nav_group_manage"]))
        return rows

    async def get_element(self, tag: str):  # type: ignore[override]
        return next((r for r in await self.get_elements() if r.test_tag == tag), None)

    async def click(self, tag: str, timeout=None) -> bool:  # type: ignore[override]
        self.clicks.append(tag)
        if tag in self.expanded:
            self.expanded[tag] = not self.expanded[tag]
        elif tag == "nav_epistemic_layer_family":
            self.screen = "LayerFamily"
        return True

    async def wait_for_screen(self, name: str, timeout=None) -> bool:  # type: ignore[override]
        return self.screen == name

    async def scroll_into_view(self, tag: str, **kw) -> bool:  # type: ignore[override]
        return await self.is_element_visible(tag)


@pytest.mark.asyncio
async def test_a_collapsed_group_is_opened_only_until_the_row_appears_and_wrong_ones_are_restored() -> None:
    fake = _FakeSidebar()
    assert await fake.navigate_to_surface("LayerFamily") is None
    assert fake.screen == "LayerFamily"
    # Groups are tried in sorted order: commons-layers first (it holds the row), so
    # manage is never touched; an already-correct state is not toggled twice.
    assert fake.clicks == ["nav_group_commons-layers", "nav_epistemic_layer_family"]
    assert fake.expanded == {"nav_group_manage": False, "nav_group_commons-layers": True}


@pytest.mark.asyncio
async def test_the_wrong_group_is_restored_before_the_next_is_tried() -> None:
    fake = _FakeSidebar()
    fake.expanded = {"nav_group_a-first": False, "nav_group_commons-layers": False}

    async def elements():
        rows = [_Row(g, True) for g in fake.expanded]
        rows.append(_Row("nav_epistemic_layer_family", fake.expanded["nav_group_commons-layers"]))
        return rows

    fake.get_elements = elements  # type: ignore[assignment]
    assert await fake.navigate_to_surface("LayerFamily") is None
    assert fake.clicks[:3] == ["nav_group_a-first", "nav_group_a-first", "nav_group_commons-layers"], fake.clicks
    assert fake.expanded["nav_group_a-first"] is False, "the wrong group must be closed again"


@pytest.mark.asyncio
async def test_an_unreachable_screen_is_named_not_silently_run() -> None:
    fake = _FakeSidebar()
    err = await fake.navigate_to_surface("NoSuchSurface")
    assert err and "nav_epistemic_no_such_surface" in err and "nav_group_" in err


@pytest.mark.asyncio
async def test_already_there_is_a_no_op() -> None:
    fake = _FakeSidebar()
    fake.screen = "LayerFamily"
    assert await fake.navigate_to_surface("LayerFamily") is None and fake.clicks == []


def test_cannot_start_is_only_a_hop_or_precondition_failure() -> None:
    """Source-level guard (the runner drives a live app): a first step whose
    `expect` fails on the right screen is a real verdict, never "cannot start"."""
    import inspect

    from tools.qa_runner.modules.web_ui.__main__ import run_flow_specs

    src = inspect.getsource(run_flow_specs)
    assert "untouched = nav_err is not None or (" in src
    assert 'first.phase == "requires"' in src
    assert 'first.phase == "expect"' not in src, "an expect failure must not be classified as cannot-start"
    assert "cannot_start.append((spec.flow, refusal))" in src, "a floor refusal is cannot-start, not a red leg"


@pytest.mark.asyncio
async def test_reveal_opens_a_collapsed_group_for_a_row_the_drawer_already_shows() -> None:
    """iOS run 34291675402: the drawer was open, Settings sat in a collapsed group,
    and the logout step waited 8 s for a row that was never going to compose."""
    fake = _FakeSidebar()
    fake.expanded = {"nav_group_manage": True, "nav_group_agent": False}

    async def elements():
        rows = [_Row(g, True) for g in fake.expanded]
        rows.append(_Row("nav_epistemic_agent_settings", fake.expanded["nav_group_agent"]))
        return rows

    fake.get_elements = elements  # type: ignore[assignment]
    assert await fake.reveal_sidebar_row("nav_epistemic_agent_settings") is None
    assert fake.expanded["nav_group_agent"] is True
    assert "nav_group_agent" in fake.clicks


@pytest.mark.asyncio
async def test_reveal_names_the_row_it_could_not_bring_on_screen() -> None:
    fake = _FakeSidebar()
    err = await fake.reveal_sidebar_row("nav_epistemic_nowhere")
    assert err and "nav_epistemic_nowhere" in err and "nav_group_" in err


def test_logout_prefers_the_route_that_exists_in_both_modes() -> None:
    """CIRISClient#51's fix routes logout through `nav_epistemic_account` ->
    Screen.Settings, present in both modes; the top bar lives on the agent home
    only, and `nav_epistemic_agent_settings` disappears when hasAgent=false.
    Order matters: newest first, older ones still drivable."""
    import inspect

    from tools.qa_runner.modules.web_ui.__main__ import DesktopAppTestRunner

    src = inspect.getsource(DesktopAppTestRunner._logout)
    account = src.index("nav_epistemic_account")
    governance = src.index('is_element_visible("btn_governance_menu")')
    legacy = src.index('_sidebar_to_logout("nav_epistemic_agent_settings"')
    assert account < governance < legacy, "the account route must be tried first"
    # Every sidebar route is revealed, never merely awaited.
    assert "reveal_sidebar_row(tag)" in src
    # And a client with no route at all says so in the product's terms.
    assert "cannot sign out at all (CIRISClient#51)" in src
