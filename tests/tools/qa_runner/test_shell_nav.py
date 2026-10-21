"""The runner reaches client surfaces through whichever shell the install renders (CIRISAgent#1181).

ciris-client 0.5.224 replaced the six-group sidebar with the circles shell, and
run 36164152466 failed logout on linux/macos/windows at the same step: the
runner only knew `nav_group_* -> nav_epistemic_*`. These tests drive the one
navigation helper (shell_nav + DesktopAppHelper.reach_surface + the mobile
`_reach_surface`) against two fakes:

* `_CirclesApp` -- an independent transcription of CirclesNav.kt at CIRISClient
  03e3793 (which cards sit in which tab, which rows sit under which instrument),
  so the vendored route table is checked against the placements, not against itself;
* `_RailApp` -- a 0.5.223-shaped app: collapsible `nav_group_*` headers over rows.
"""

from __future__ import annotations

import importlib
from typing import Dict, List, Optional, Set, Tuple

import pytest

from tools.qa_runner.modules.web_ui import shell_nav
from tools.qa_runner.modules.web_ui.desktop_app_helper import DesktopAppHelper
from tools.qa_runner.modules.web_ui.shell_nav import (
    CIRCLES_ROUTES,
    Shell,
    detect_shell,
    remaining_hops,
    surface_for_screen,
    walk_circles_sync,
)

web_ui = importlib.import_module("tools.qa_runner.modules.web_ui.__main__")
mobile = importlib.import_module("tools.qa_runner.modules.mobile.test_cases")

#: What /tree held when logout failed on run 36164152466 (run-without-AI home = Contacts).
RUN_36164152466 = {
    "btn_contacts_add_open", "btn_contacts_add_submit", "btn_contacts_refresh", "btn_my_things",
    "btn_rail_toggle", "btn_stop_everything", "circle_agent", "circle_family", "circle_global_commons",
    "circle_global_communities", "circle_local_community", "nav_instrument_devices_keys",
    "nav_instrument_everything_i_shared", "nav_instrument_help", "nav_instrument_someone_i_trust",
    "nav_instrument_this_node", "tab_chats", "tab_decisions", "tab_files", "tab_people", "tab_record",
    "tab_rules", "tab_safety",
}  # fmt: skip

CIRCLES = ["agent", "family", "local_community", "global_communities", "global_commons"]
TABS = ["files", "chats", "people", "safety", "rules", "decisions", "record"]
INSTRUMENTS = ["devices_keys", "everything_i_shared", "this_node", "someone_i_trust", "help"]
_RULES_ALL = ["trust", "manage_consent", "consent", "delegations"]

#: CirclesNav.kt placements (agent build), as (circle, tab) -> cards in order.
TAB_CARDS: Dict[Tuple[str, str], List[str]] = {
    ("agent", "chats"): ["interact"],
    **{(c, "people"): ["contacts"] for c in CIRCLES if c != "global_communities"},
    ("global_communities", "people"): ["contacts", "users"],
    ("agent", "rules"): ["layer_agent", *_RULES_ALL],
    ("family", "rules"): ["layer_family", *_RULES_ALL, "delegation"],
    ("local_community", "rules"): ["layer_local_community", *_RULES_ALL],
    ("global_communities", "rules"): ["layer_global_communities", *_RULES_ALL, "billing", "wallet"],
    ("global_commons", "rules"): ["layer_global_commons", *_RULES_ALL],
    ("local_community", "decisions"): ["health_reputation", "environment_graph"],
    ("global_communities", "decisions"): ["health_reputation"],
    ("global_commons", "decisions"): ["health_reputation", "commons"],
}
INSTRUMENT_ROWS = {
    "devices_keys": ["identity_management", "account"],
    "everything_i_shared": ["data", "storage"],
    "this_node": ["nodes", "agent_settings", "llm_settings", "adapters", "network_ops", "services"],
    "someone_i_trust": ["wise_authority"],
    "help": ["help"],
}
#: surface (row stem) -> /screen name, where it differs from CamelCase.
SCREEN_OF = {"account": "Settings", "agent_settings": "Settings", "nodes": "ManageNodes"}


def _screen(stem: str) -> str:
    return SCREEN_OF.get(stem) or "".join(w.capitalize() for w in stem.split("_"))


class _El:
    def __init__(self, tag: str, visible: bool) -> None:
        self.test_tag, self.visible, self.width, self.height = tag, visible, 10, 10


class _CirclesApp(DesktopAppHelper):
    """The circles shell. `rail=True` is a >=900dp desktop: instruments listed under the circles."""

    def __init__(self, rail: bool = True, circle: str = "local_community", screen: str = "Contacts") -> None:
        self.rail = rail
        self.circle, self.tab = circle, "people"
        self.sheet = False
        self.page: Tuple[str, str] = ("screen", screen)  # ("screen", name) | ("tab", c/t) | ("instrument", id)
        self.clicks: List[str] = []

    # what is on screen
    def on_screen(self) -> Set[str]:
        tags = {"btn_my_things", "btn_rail_toggle", "btn_stop_everything"}
        tags |= {f"circle_{c}" for c in CIRCLES} | {f"tab_{t}" for t in TABS}
        if self.rail or self.sheet:
            tags |= {f"nav_instrument_{i}" for i in INSTRUMENTS}
        kind, what = self.page
        if kind == "tab":
            tags |= {f"nav_epistemic_{s}" for s in TAB_CARDS.get((self.circle, self.tab), [])}
        elif kind == "instrument":
            tags |= {f"nav_epistemic_{s}" for s in INSTRUMENT_ROWS[what]}
        elif what == "Contacts":
            tags |= {"btn_contacts_add_open", "btn_contacts_add_submit", "btn_contacts_refresh"}
        elif what == "Settings":
            tags.add("btn_logout")
        return tags

    def _open_tab(self, circle: str, tab: str) -> None:
        self.circle, self.tab = circle, tab
        cards = TAB_CARDS.get((circle, tab), [])
        self.page = ("screen", _screen(cards[0])) if len(cards) == 1 else ("tab", f"{circle}/{tab}")

    # the DesktopAppHelper surface the walk and _logout use
    async def get_screen(self) -> str:
        return self.page[1] if self.page[0] == "screen" else "CircleTab"

    async def get_elements(self):  # type: ignore[override]
        return [_El(t, True) for t in sorted(self.on_screen())]

    async def get_element(self, tag: str):  # type: ignore[override]
        return _El(tag, True) if tag in self.on_screen() else None

    async def scroll_into_view(self, tag: str, **kw) -> bool:  # type: ignore[override]
        return tag in self.on_screen()

    async def wait_for_element(self, tag: str, timeout=None) -> bool:  # type: ignore[override]
        if tag not in self.on_screen():
            raise RuntimeError(f"Wait for element '{tag}' timed out")
        return True

    async def wait_for_screen(self, name: str, timeout=None) -> bool:  # type: ignore[override]
        return await self.get_screen() == name

    async def click(self, tag: str, timeout=None) -> bool:  # type: ignore[override]
        if tag not in self.on_screen():
            raise RuntimeError(f"Click '{tag}' failed: not on screen")
        self.clicks.append(tag)
        if tag == "btn_my_things":
            self.sheet = not self.sheet  # clicking it twice closes it
        elif tag.startswith("nav_instrument_"):
            self.sheet = False
            self.page = ("instrument", tag[len("nav_instrument_") :])
        elif tag.startswith("circle_"):
            self._open_tab(tag[len("circle_") :], self.tab or "files")
        elif tag.startswith("tab_"):
            self._open_tab(self.circle, tag[len("tab_") :])
        elif tag.startswith("nav_epistemic_"):
            self.page = ("screen", _screen(tag[len("nav_epistemic_") :]))
        elif tag == "btn_logout":
            self.page = ("screen", "Login")
        return True


class _RailApp(DesktopAppHelper):
    """ciris-client 0.5.223: collapsible groups; a row is on screen only while its group is open."""

    GROUPS = {
        "nav_group_agent": ["nav_epistemic_agent_settings"],
        "nav_group_commons-layers": ["nav_epistemic_layer_family", "nav_epistemic_layer_global_commons"],
        "nav_group_manage": [
            "nav_epistemic_account",
            "nav_epistemic_nodes",
            "nav_epistemic_contacts",
            "nav_epistemic_health_reputation",
        ],
    }

    def __init__(self) -> None:
        self.expanded = {g: False for g in self.GROUPS}
        self.screen = "Contacts"
        self.clicks: List[str] = []

    def on_screen(self) -> Set[str]:
        tags = set(self.GROUPS)
        for g, rows in self.GROUPS.items():
            if self.expanded[g]:
                tags |= set(rows)
        if self.screen == "Settings":
            tags.add("btn_logout")
        return tags

    async def get_screen(self) -> str:
        return self.screen

    async def get_elements(self):  # type: ignore[override]
        tags = self.on_screen()
        every = set(self.GROUPS) | {r for rows in self.GROUPS.values() for r in rows}
        return [_El(t, t in tags) for t in sorted(every | tags)]

    async def get_element(self, tag: str):  # type: ignore[override]
        return next((e for e in await self.get_elements() if e.test_tag == tag), None)

    async def scroll_into_view(self, tag: str, **kw) -> bool:  # type: ignore[override]
        return tag in self.on_screen()

    async def wait_for_element(self, tag: str, timeout=None) -> bool:  # type: ignore[override]
        if tag not in self.on_screen():
            raise RuntimeError(f"Wait for element '{tag}' timed out")
        return True

    async def wait_for_screen(self, name: str, timeout=None) -> bool:  # type: ignore[override]
        return self.screen == name

    async def click(self, tag: str, timeout=None) -> bool:  # type: ignore[override]
        self.clicks.append(tag)
        if tag in self.expanded:
            self.expanded[tag] = not self.expanded[tag]
        elif tag.startswith("nav_epistemic_"):
            self.screen = _screen(tag[len("nav_epistemic_") :])
        elif tag == "btn_logout":
            self.screen = "Login"
        return True


@pytest.fixture(autouse=True)
def _no_pacing(monkeypatch):
    monkeypatch.setattr(shell_nav, "SETTLE_S", 0.0)
    monkeypatch.setattr(shell_nav, "POLL_S", 0.0)
    monkeypatch.setattr(shell_nav, "HOP_TIMEOUT_S", 0.0)
    monkeypatch.setattr(mobile.time, "sleep", lambda s: None)


def _runner(helper: DesktopAppHelper):
    runner = web_ui.DesktopAppTestRunner()
    runner.helper = helper

    async def _no_dump(label: str) -> None:
        return None

    runner._dump_tree = _no_dump  # type: ignore[method-assign]
    return runner


# ─── shell detection ────────────────────────────────────────────────────────


def test_the_failing_runs_tree_is_the_circles_shell() -> None:
    assert detect_shell(RUN_36164152466) is Shell.CIRCLES


def test_a_0_5_223_tree_is_the_old_rail() -> None:
    tags = {"nav_group_manage", "nav_group_agent", "nav_epistemic_account", "btn_nav_drawer_open", "tab_x"}
    assert detect_shell(tags) is Shell.RAIL


def test_the_fake_reproduces_the_failing_runs_tree() -> None:
    """The circles fake, parked where run 36164152466 was, shows exactly what that run saw."""
    assert _CirclesApp(rail=True).on_screen() == RUN_36164152466


# ─── the logout route (the failing step) ────────────────────────────────────


@pytest.mark.asyncio
async def test_logout_on_the_failing_runs_elements_goes_through_devices_and_keys() -> None:
    app = _CirclesApp(rail=True)
    await _runner(app)._logout()
    # The rail already lists the instruments, so My things is not opened (a
    # second click on it would close the sheet).
    assert app.clicks == ["nav_instrument_devices_keys", "nav_epistemic_account", "btn_logout"]
    assert app.page == ("screen", "Login")


@pytest.mark.asyncio
async def test_logout_on_a_phone_opens_my_things_first() -> None:
    app = _CirclesApp(rail=False)
    await _runner(app)._logout()
    assert app.clicks == ["btn_my_things", "nav_instrument_devices_keys", "nav_epistemic_account", "btn_logout"]


@pytest.mark.asyncio
async def test_logout_failure_names_the_circles_route_it_looked_for() -> None:
    app = _CirclesApp(rail=True)
    INSTRUMENT_ROWS_BACKUP = dict(INSTRUMENT_ROWS)
    INSTRUMENT_ROWS["devices_keys"] = ["identity_management"]
    INSTRUMENT_ROWS["this_node"] = ["nodes"]
    try:
        with pytest.raises(RuntimeError) as e:
            await _runner(app)._logout()
    finally:
        INSTRUMENT_ROWS.clear()
        INSTRUMENT_ROWS.update(INSTRUMENT_ROWS_BACKUP)
    msg = str(e.value)
    assert "btn_my_things -> nav_instrument_devices_keys -> nav_epistemic_account" in msg
    assert "btn_my_things -> nav_instrument_this_node -> nav_epistemic_agent_settings" in msg
    assert "Shell detected: circles" in msg
    assert "circle_agent" in msg and "nav_instrument_devices_keys" in msg
    assert "cannot sign out at all (CIRISClient#51)" in msg


@pytest.mark.asyncio
async def test_logout_on_the_old_rail_is_unchanged() -> None:
    """0.5.223: the Account row is revealed by opening groups in sorted order,
    restoring each wrong one, exactly as reveal_sidebar_row always has."""
    app = _RailApp()
    await _runner(app)._logout()
    assert app.clicks == [
        "nav_group_agent",
        "nav_group_agent",
        "nav_group_commons-layers",
        "nav_group_commons-layers",
        "nav_group_manage",
        "nav_epistemic_account",
        "btn_logout",
    ]
    assert not any(shell_nav.is_circles_tag(c) for c in app.clicks)


# ─── every #1181 row, walked on the fake ────────────────────────────────────

#: (surface, the clicks from a phone parked on Contacts). The two rows that
#: differ from #1181's prose follow CirclesNav.kt, which the client's own
#: nav_map derives from: Settings is under This node, and Local community's
#: Decisions tab holds two cards (health, environment graph) so the row is clicked.
ISSUE_1181_ROWS = [
    ("nodes", ["btn_my_things", "nav_instrument_this_node", "nav_epistemic_nodes"], "ManageNodes"),
    ("layer-family", ["circle_family", "tab_rules", "nav_epistemic_layer_family"], "LayerFamily"),
    (
        "layer-local-community",
        ["circle_local_community", "tab_rules", "nav_epistemic_layer_local_community"],
        "LayerLocalCommunity",
    ),
    (
        "layer-global-commons",
        ["circle_global_commons", "tab_rules", "nav_epistemic_layer_global_commons"],
        "LayerGlobalCommons",
    ),
    (
        "health-reputation",
        ["circle_local_community", "tab_decisions", "nav_epistemic_health_reputation"],
        "HealthReputation",
    ),
    ("contacts", ["circle_agent", "tab_people"], "Contacts"),
    ("agent-settings", ["btn_my_things", "nav_instrument_this_node", "nav_epistemic_agent_settings"], "Settings"),
    ("account", ["btn_my_things", "nav_instrument_devices_keys", "nav_epistemic_account"], "Settings"),
]


@pytest.mark.parametrize("surface,clicks,screen", ISSUE_1181_ROWS, ids=[r[0] for r in ISSUE_1181_ROWS])
@pytest.mark.asyncio
async def test_each_issue_1181_row_lands_on_its_screen(surface: str, clicks: List[str], screen: str) -> None:
    app = _CirclesApp(rail=False, screen="Interact")
    assert await app.reach_surface(surface) is None
    assert app.clicks == clicks
    assert await app.get_screen() == screen


@pytest.mark.parametrize("surface,clicks,screen", ISSUE_1181_ROWS, ids=[r[0] for r in ISSUE_1181_ROWS])
def test_each_issue_1181_row_is_the_vendored_route(surface: str, clicks: List[str], screen: str) -> None:
    assert list(CIRCLES_ROUTES[surface]) == clicks


@pytest.mark.parametrize("surface,clicks,screen", ISSUE_1181_ROWS, ids=[r[0] for r in ISSUE_1181_ROWS])
@pytest.mark.asyncio
async def test_navigate_to_surface_by_screen_name_uses_the_circles_route(
    surface: str, clicks: List[str], screen: str
) -> None:
    if screen == "Settings" and surface == "account":
        pytest.skip("Screen.Settings resolves to agent-settings; account is reached by surface id")
    app = _CirclesApp(rail=False, screen="Interact")
    assert surface_for_screen(screen) == surface
    assert await app.navigate_to_surface(screen) is None
    assert app.clicks == clicks


def test_a_visible_row_is_clicked_directly_and_a_visible_instrument_skips_my_things() -> None:
    chain = CIRCLES_ROUTES["nodes"]
    assert remaining_hops(chain, {"nav_epistemic_nodes"}) == ["nav_epistemic_nodes"]
    assert remaining_hops(chain, {"nav_instrument_this_node"}) == ["nav_instrument_this_node", "nav_epistemic_nodes"]
    assert remaining_hops(chain, {"btn_my_things"}) == list(chain)
    # A placed chain always clicks its circle: the selected circle is not in the tree.
    assert remaining_hops(CIRCLES_ROUTES["layer-family"], {"tab_rules", "circle_family"})[0] == "circle_family"


@pytest.mark.asyncio
async def test_an_unreachable_hop_names_what_the_shell_showed() -> None:
    app = _CirclesApp(rail=False)
    INSTRUMENT_ROWS_BACKUP = list(INSTRUMENT_ROWS["this_node"])
    INSTRUMENT_ROWS["this_node"] = ["agent_settings"]
    try:
        err = await app.reach_surface("nodes")
    finally:
        INSTRUMENT_ROWS["this_node"] = INSTRUMENT_ROWS_BACKUP
    assert err and "'nav_epistemic_nodes' is not on screen after btn_my_things -> nav_instrument_this_node" in err
    assert "nav_epistemic_agent_settings" in err and "03e3793" in err


# ─── the old rail, through the same entry point ─────────────────────────────


@pytest.mark.asyncio
async def test_reach_surface_on_the_old_rail_reveals_the_row_as_before() -> None:
    app = _RailApp()
    assert await app.reach_surface("layer-family") is None
    assert app.clicks == [
        "nav_group_agent",
        "nav_group_agent",
        "nav_group_commons-layers",
        "nav_epistemic_layer_family",
    ]
    assert app.screen == "LayerFamily"


# ─── mobile (Android / iOS run the same client) ─────────────────────────────


class _MobileClient:
    """TestServerClient over a fake app's on-screen set."""

    def __init__(self, app) -> None:
        self.app = app

    def tags(self) -> List[str]:
        return sorted(self.app.on_screen())

    def on_screen_tags(self) -> List[str]:
        return self.tags()

    def is_visible(self, tag: str) -> bool:
        return tag in self.app.on_screen()

    def wait_for_element(self, tag: str, timeout: float = 8.0) -> bool:
        return self.is_visible(tag)

    def click(self, tag: str) -> Tuple[bool, Optional[Tuple[int, int]]]:
        if tag not in self.app.on_screen():
            return False, None
        import asyncio

        return asyncio.new_event_loop().run_until_complete(self.app.click(tag)), None


def test_mobile_reaches_manage_nodes_through_my_things() -> None:
    app = _CirclesApp(rail=False)
    assert mobile._reach_surface(_MobileClient(app), None, "nodes") is None
    assert app.clicks == ["btn_my_things", "nav_instrument_this_node", "nav_epistemic_nodes"]


def test_mobile_on_the_old_rail_expands_a_group() -> None:
    app = _RailApp()
    assert mobile._reach_surface(_MobileClient(app), None, "nodes") is None
    assert app.clicks[-2:] == ["nav_group_manage", "nav_epistemic_nodes"]
    assert not any(shell_nav.is_circles_tag(c) for c in app.clicks)


def test_the_sync_walk_matches_the_async_one() -> None:
    app = _CirclesApp(rail=False)
    client = _MobileClient(app)
    err = walk_circles_sync("layer-global-commons", client.on_screen_tags, lambda t: client.click(t)[0])
    assert err is None
    assert app.clicks == list(CIRCLES_ROUTES["layer-global-commons"])
