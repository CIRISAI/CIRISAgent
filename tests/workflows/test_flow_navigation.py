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
