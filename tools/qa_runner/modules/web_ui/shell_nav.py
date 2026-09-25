"""Reach a client surface through whichever navigation shell the install has.

ONE PLACE FOR THE HOPS (CIRISAgent#1181). ciris-client 0.5.224 (CIRISClient#63,
"Locked Spec wave 1") replaced the six-group collapsible sidebar with the
circles shell, and every call site that encoded `nav_group_* -> nav_epistemic_*`
stopped resolving at once -- the five-platform run 36164152466 failed logout on
linux, macos and windows at the same step. Call sites now name the SURFACE they
want and this module decides how to get there, from what is on screen:

* **circles shell** (0.5.224+) -- `btn_my_things` or any `circle_*` is in the
  tree. A *placed* surface is `circle_<slug> -> tab_<id>` and then its
  `nav_epistemic_<surface>` row only when the tab lists several cards (a tab
  with one card shows it directly). An *instrument* surface is
  `btn_my_things -> nav_instrument_<id> -> nav_epistemic_<surface>`. The desktop
  rail also lists the instruments under the circles with the same tags, so an
  instrument already on screen is clicked directly -- `btn_my_things` opens a
  sheet and a second click would close it again.
* **old rail** (<= 0.5.223) -- anything else. The row is revealed by
  `DesktopAppHelper.reveal_sidebar_row` (drawer, collapsed group, fold) exactly
  as before; that path is untouched so the 0.5.223 pin keeps working.

THE TABLE IS THE CLIENT'S, NOT OURS. `CIRCLES_ROUTES` is the output of the
client's own derivation, `testing/gate/nav_map.py` (`python3 -m
testing.gate.nav_map`), at CIRISClient commit 03e3793 (0.5.224), which parses
`CirclesNav.kt` / `EpistemicNav.kt` / `CIRISApp.kt`. It is transcribed rather
than vendored because nav_map reads the Kotlin sources at runtime and the runner
has no client checkout. Two rows differ from the prose table in #1181, and the
source wins:

* Settings (`agent-settings`) is under the *This node* instrument, not
  `circle_agent -> tab_rules` (CirclesNav.kt: "Settings is every build's").
* Health & Reputation shares Local community's Decisions tab with the
  environment graph, so its row IS clicked.

`account` is added by hand: nav_map keys by Screen, and `Screen.Settings` is
already claimed by `agent-settings`, so the Account row (CIRISClient#51, the
logout route that exists in both builds) never appears in its output. Its
placement is CirclesNav.kt's `Instrument("devices-keys", ..., listOf(
IdentityManagement, Account))`.
"""

from __future__ import annotations

import asyncio
import re
import time
from enum import Enum
from typing import Callable, Collection, Dict, List, Optional, Protocol, Sequence, Tuple

MY_THINGS = "btn_my_things"
CIRCLE_PREFIX = "circle_"
TAB_PREFIX = "tab_"
INSTRUMENT_PREFIX = "nav_instrument_"
ROW_PREFIX = "nav_epistemic_"

#: Pacing, read at call time so a unit test can zero it. A hop's target gets
#: HOP_TIMEOUT_S to come on screen; SETTLE_S lets a click's recomposition land.
HOP_TIMEOUT_S = 5.0
SETTLE_S = 0.4
POLL_S = 0.25

#: The client source the table below was derived from.
NAV_MAP_SOURCE = "CIRISClient testing/gate/nav_map.py @ 03e3793 (ciris-client 0.5.224)"


class Shell(str, Enum):
    CIRCLES = "circles"
    RAIL = "rail"


#: surface id -> the tags to click, in order (nav_map.build(), agent build).
#: The node build is a subset: agent-only surfaces are absent, and no shared
#: surface changes shape between builds (checked against `--node`).
CIRCLES_ROUTES: Dict[str, Tuple[str, ...]] = {
    "accord": ("circle_global_commons", "tab_safety", "nav_epistemic_accord"),
    "account": ("btn_my_things", "nav_instrument_devices_keys", "nav_epistemic_account"),
    "adapters": ("btn_my_things", "nav_instrument_this_node", "nav_epistemic_adapters"),
    "agent-settings": ("btn_my_things", "nav_instrument_this_node", "nav_epistemic_agent_settings"),
    "audit": ("circle_agent", "tab_record"),
    "billing": ("circle_global_communities", "tab_rules", "nav_epistemic_billing"),
    "child-safety": ("circle_agent", "tab_safety"),
    "client-interface": ("btn_my_things", "nav_instrument_this_node", "nav_epistemic_client_interface"),
    "commons": ("circle_global_commons", "tab_decisions", "nav_epistemic_commons"),
    "config": ("btn_my_things", "nav_instrument_this_node", "nav_epistemic_config"),
    "consent": ("circle_agent", "tab_rules", "nav_epistemic_consent"),
    "constitutional": ("circle_global_commons", "tab_safety", "nav_epistemic_constitutional"),
    "contacts": ("circle_agent", "tab_people"),
    "data": ("btn_my_things", "nav_instrument_everything_i_shared", "nav_epistemic_data"),
    "delegation": ("circle_family", "tab_rules", "nav_epistemic_delegation"),
    "delegations": ("circle_agent", "tab_rules", "nav_epistemic_delegations"),
    "environment-graph": ("circle_local_community", "tab_decisions", "nav_epistemic_environment_graph"),
    "graph-memory": ("btn_my_things", "nav_instrument_this_node", "nav_epistemic_graph_memory"),
    "health-reputation": ("circle_local_community", "tab_decisions", "nav_epistemic_health_reputation"),
    "help": ("btn_my_things", "nav_instrument_help", "nav_epistemic_help"),
    "identity-management": ("btn_my_things", "nav_instrument_devices_keys", "nav_epistemic_identity_management"),
    "interact": ("circle_agent", "tab_chats"),
    "layer-agent": ("circle_agent", "tab_rules", "nav_epistemic_layer_agent"),
    "layer-family": ("circle_family", "tab_rules", "nav_epistemic_layer_family"),
    "layer-global-commons": ("circle_global_commons", "tab_rules", "nav_epistemic_layer_global_commons"),
    "layer-global-communities": (
        "circle_global_communities",
        "tab_rules",
        "nav_epistemic_layer_global_communities",
    ),
    "layer-local-community": ("circle_local_community", "tab_rules", "nav_epistemic_layer_local_community"),
    "llm-settings": ("btn_my_things", "nav_instrument_this_node", "nav_epistemic_llm_settings"),
    "logs": ("btn_my_things", "nav_instrument_this_node", "nav_epistemic_logs"),
    "manage-consent": ("circle_agent", "tab_rules", "nav_epistemic_manage_consent"),
    "memory": ("btn_my_things", "nav_instrument_this_node", "nav_epistemic_memory"),
    "moderation": ("circle_local_community", "tab_safety", "nav_epistemic_moderation"),
    "network-ops": ("btn_my_things", "nav_instrument_this_node", "nav_epistemic_network_ops"),
    "nodes": ("btn_my_things", "nav_instrument_this_node", "nav_epistemic_nodes"),
    "provision-accord-holder": ("circle_global_commons", "tab_safety", "nav_epistemic_provision_accord_holder"),
    "runtime": ("btn_my_things", "nav_instrument_this_node", "nav_epistemic_runtime"),
    "scheduler": ("btn_my_things", "nav_instrument_this_node", "nav_epistemic_scheduler"),
    "services": ("btn_my_things", "nav_instrument_this_node", "nav_epistemic_services"),
    "sessions": ("btn_my_things", "nav_instrument_this_node", "nav_epistemic_sessions"),
    "skills": ("btn_my_things", "nav_instrument_this_node", "nav_epistemic_skills"),
    "storage": ("btn_my_things", "nav_instrument_everything_i_shared", "nav_epistemic_storage"),
    "system": ("btn_my_things", "nav_instrument_this_node", "nav_epistemic_system"),
    "telemetry": ("btn_my_things", "nav_instrument_this_node", "nav_epistemic_telemetry"),
    "tickets": ("btn_my_things", "nav_instrument_this_node", "nav_epistemic_tickets"),
    "tools": ("btn_my_things", "nav_instrument_this_node", "nav_epistemic_tools"),
    "transport": ("btn_my_things", "nav_instrument_this_node", "nav_epistemic_transport"),
    "trust": ("circle_agent", "tab_rules", "nav_epistemic_trust"),
    "users": ("circle_global_communities", "tab_people", "nav_epistemic_users"),
    "wallet": ("circle_global_communities", "tab_rules", "nav_epistemic_wallet"),
    "wise-authority": ("btn_my_things", "nav_instrument_someone_i_trust", "nav_epistemic_wise_authority"),
}

#: `/screen` names whose surface id is not the screen name in kebab case
#: (CIRISApp.kt's `NavSurface.X -> Screen.Y` table).
SCREEN_SURFACE_ALIASES: Dict[str, str] = {
    "DataManagement": "data",
    "EnvironmentInfo": "environment-graph",
    "LLMSettings": "llm-settings",
    "ManageNodes": "nodes",
    "Settings": "agent-settings",
    "SkillStudio": "skills",
    "VizSettings": "client-interface",
}


def surface_for_screen(screen_name: str) -> str:
    """`/screen` name -> surface id (`LayerFamily` -> `layer-family`, `ManageNodes` -> `nodes`)."""
    alias = SCREEN_SURFACE_ALIASES.get(screen_name)
    if alias:
        return alias
    return re.sub(r"(?<!^)(?=[A-Z])", "-", screen_name).lower()


def row_tag(surface: str) -> str:
    """A surface's row, in either shell: `nav_epistemic_<id, - as _>`."""
    return ROW_PREFIX + surface.replace("-", "_")


def is_circles_tag(tag: str) -> bool:
    return tag == MY_THINGS or tag.startswith(CIRCLE_PREFIX)


def detect_shell(tags: Collection[str]) -> Shell:
    """Circles shell if `btn_my_things` or any `circle_*` is in the tree, else the old rail.

    Presence, not visibility: one client build has one shell, and the circles
    are chrome that is always composed once the shell is up.
    """
    return Shell.CIRCLES if any(is_circles_tag(t) for t in tags) else Shell.RAIL


def circles_route(surface: str) -> Optional[Tuple[str, ...]]:
    return CIRCLES_ROUTES.get(surface)


def remaining_hops(chain: Sequence[str], on_screen: Collection[str]) -> List[str]:
    """The part of `chain` still to click, given what is ON SCREEN now.

    * The surface's own row on screen (it is listed where we stand) -> just it.
      Rows are tagged per surface, so a visible row always leads to the surface.
    * An instrument on screen (the desktop rail lists them; or the My things
      sheet is already open) -> skip `btn_my_things`. Clicking it again would
      close the sheet.
    * Otherwise the whole chain. A placed chain always clicks its circle: which
      circle is selected is not in the tree, and `tab_rules` in the wrong circle
      lists the wrong cards.
    """
    last = chain[-1]
    if last.startswith(ROW_PREFIX) and last in on_screen:
        return [last]
    if len(chain) >= 2 and chain[0] == MY_THINGS and chain[1] in on_screen:
        return list(chain[1:])
    return list(chain)


def circles_elements(tags: Collection[str]) -> List[str]:
    """The shell chrome on screen, for a failure message that says what WAS there."""
    return sorted(
        t
        for t in tags
        if is_circles_tag(t) or t.startswith((TAB_PREFIX, INSTRUMENT_PREFIX, ROW_PREFIX)) or t == "btn_nav_back"
    )


def _unreachable(hop: str, done: Sequence[str], chain: Sequence[str], on_screen: Collection[str]) -> str:
    return (
        f"{hop!r} is not on screen after {' -> '.join(done) or 'no clicks'} "
        f"(circles route {' -> '.join(chain)}, from {NAV_MAP_SOURCE}); "
        f"circles-shell elements on screen: {circles_elements(on_screen) or 'none'}"
    )


# ─── async (desktop / iOS / web_ui helper) ──────────────────────────────────


class _Element(Protocol):
    test_tag: str
    visible: Optional[bool]
    width: int
    height: int


class AsyncNavHelper(Protocol):
    """The slice of DesktopAppHelper the walk needs."""

    async def get_elements(self) -> Sequence[_Element]: ...

    async def click(self, test_tag: str, timeout: Optional[int] = None) -> bool: ...

    async def scroll_into_view(self, test_tag: str, per_direction: int = 40, amount: int = 300) -> bool: ...


def _on_screen(elements: Sequence[_Element]) -> List[str]:
    """Tags ON SCREEN: `visible` when the client reports it (0.5.206+), else non-zero geometry."""
    out = []
    for e in elements:
        shown = bool(e.visible) if e.visible is not None else (e.width > 0 and e.height > 0)
        if shown:
            out.append(e.test_tag)
    return out


async def walk_circles(
    helper: AsyncNavHelper,
    surface: str,
    hop_timeout_s: Optional[float] = None,
    settle_s: Optional[float] = None,
    poll_s: Optional[float] = None,
) -> Optional[str]:
    """Click the circles-shell route to `surface`. None on success, else why not."""
    hop_timeout_s = HOP_TIMEOUT_S if hop_timeout_s is None else hop_timeout_s
    settle_s = SETTLE_S if settle_s is None else settle_s
    poll_s = POLL_S if poll_s is None else poll_s
    chain = circles_route(surface)
    if chain is None:
        return f"no circles-shell route for surface {surface!r} in {NAV_MAP_SOURCE}"
    elements = await helper.get_elements()
    hops = remaining_hops(chain, _on_screen(elements))
    done: List[str] = []
    for hop in hops:
        deadline = time.monotonic() + hop_timeout_s
        while True:
            elements = await helper.get_elements()
            on_screen = _on_screen(elements)
            if hop in on_screen:
                break
            # Composed but below the fold (This node lists twenty rows): scroll.
            if any(e.test_tag == hop for e in elements) and await helper.scroll_into_view(hop):
                break
            if time.monotonic() >= deadline:
                return _unreachable(hop, done, chain, on_screen)
            await asyncio.sleep(poll_s)
        try:
            clicked = await helper.click(hop)
        except RuntimeError as e:
            return f"click on {hop!r} failed after {' -> '.join(done) or 'no clicks'}: {e}"
        if not clicked:
            return f"click on {hop!r} did not take after {' -> '.join(done) or 'no clicks'}"
        done.append(hop)
        await asyncio.sleep(settle_s)
    return None


# ─── sync (mobile test cases: Android via adb, the same client) ─────────────


def walk_circles_sync(
    surface: str,
    on_screen: Callable[[], Collection[str]],
    click: Callable[[str], bool],
    hop_timeout_s: Optional[float] = None,
    settle_s: Optional[float] = None,
    poll_s: Optional[float] = None,
    sleep: Optional[Callable[[float], None]] = None,
    clock: Optional[Callable[[], float]] = None,
) -> Optional[str]:
    """The same walk for a synchronous driver. None on success, else why not."""
    hop_timeout_s = HOP_TIMEOUT_S if hop_timeout_s is None else hop_timeout_s
    settle_s = SETTLE_S if settle_s is None else settle_s
    poll_s = POLL_S if poll_s is None else poll_s
    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    chain = circles_route(surface)
    if chain is None:
        return f"no circles-shell route for surface {surface!r} in {NAV_MAP_SOURCE}"
    hops = remaining_hops(chain, on_screen())
    done: List[str] = []
    for hop in hops:
        deadline = clock() + hop_timeout_s
        while True:
            now_on = on_screen()
            if hop in now_on:
                break
            if clock() >= deadline:
                return _unreachable(hop, done, chain, now_on)
            sleep(poll_s)
        if not click(hop):
            return f"click on {hop!r} did not take after {' -> '.join(done) or 'no clicks'}"
        done.append(hop)
        sleep(settle_s)
    return None
