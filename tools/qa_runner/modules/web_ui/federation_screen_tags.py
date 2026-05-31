"""Canonical testTag registry for the federation screen suite.

Source of truth for the Compose-side `testTag` / `testableClickable` pass
AND the QA runner walk-test. If the Compose code uses a different tag
than what's here, the walk-test will fail loudly — that's the point.

Conventions (matching existing CIRIS testTag usage):
- Screens: `screen_<name>` (root container)
- Buttons: `btn_<name>` — MUST use `testableClickable` not `testable`
- Inputs: `input_<name>`
- Cards/sections: `card_<name>`
- Pills/chips: `chip_<name>` / `_pill`
- Indicators: `indicator_<name>`
- Text values: `text_<name>`
- Tiles: `tile_<name>`
- Segments: `segment_<name>` (with per-button children)
- Sliders: `slider_<name>`
- Modals/dialogs: `dialog_<name>`
- Canvases: `canvas_<name>`
- Parameterized list rows: template form, e.g. `peer_row_{key_id}`
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ───────────────────────────────────────────────────────────────────
# Sidebar nav entry (EpistemicSidebar)
# ───────────────────────────────────────────────────────────────────
# EpistemicSidebar item that opens the federation transport hub. The sidebar
# tags every nav row as `nav_epistemic_<slug>` where <slug> is the surface id
# with hyphens normalized to underscores. Phase B (2026-05-31): federation
# transport substrate moved from NavSurface.Network ("network") to
# NavSurface.LayerGlobalCommons ("layer-global-commons"). The legacy
# constant name is kept for callers that historically imported
# NAV_EPISTEMIC_NETWORK; it now points at the new tag.
NAV_EPISTEMIC_NETWORK = "nav_epistemic_layer_global_commons"
NAV_EPISTEMIC_LAYER_GLOBAL_COMMONS = "nav_epistemic_layer_global_commons"


# ───────────────────────────────────────────────────────────────────
# Network hub (the federation screen entry-point)
# ───────────────────────────────────────────────────────────────────
NETWORK_HUB = "screen_network_hub"

# Identity card on the hub
CARD_NETWORK_IDENTITY = "card_network_identity"
TEXT_NETWORK_IDENTITY_KEY = "text_network_identity_key"
BTN_NETWORK_IDENTITY_COPY = "btn_network_identity_copy"

# Global agent-mode selector (also mirrored on SettingsScreen)
SEGMENT_AGENT_MODE = "segment_agent_mode"
BTN_MODE_CLIENT = "btn_mode_client"
BTN_MODE_PROXY = "btn_mode_proxy"
BTN_MODE_SERVER = "btn_mode_server"
TOOLTIP_MODE_DISK_GATE = "tooltip_mode_disk_gate"
DIALOG_MODE_CONFIRM = "dialog_mode_confirm"
BTN_MODE_CONFIRM = "btn_mode_confirm"
BTN_MODE_CANCEL = "btn_mode_cancel"

# Live stats strip
TEXT_STAT_PEERS = "text_stat_peers"
TEXT_STAT_TRANSPORTS = "text_stat_transports"
TEXT_STAT_QUEUE = "text_stat_queue"
TEXT_STAT_ERRORS = "text_stat_errors"

# 10 navigation tiles on the hub
TILE_FEDERATION_IDENTITY = "tile_federation_identity"
TILE_FEDERATION_MAP = "tile_federation_map"
TILE_FEDERATION_TRUST_GRAPH = "tile_federation_trust_graph"
TILE_FEDERATION_PEERS = "tile_federation_peers"
TILE_FEDERATION_INTERFACES = "tile_federation_interfaces"
TILE_FEDERATION_PATHS = "tile_federation_paths"
TILE_FEDERATION_ANNOUNCES = "tile_federation_announces"
TILE_FEDERATION_QUEUE = "tile_federation_queue"
TILE_FEDERATION_DIAGNOSTICS = "tile_federation_diagnostics"
TILE_FEDERATION_CONTENT = "tile_federation_content"


# ───────────────────────────────────────────────────────────────────
# Per-screen registry — each entry maps to one of the 10 sub-screens
# ───────────────────────────────────────────────────────────────────
@dataclass
class FederationScreen:
    """Descriptor for one federation sub-screen."""

    name: str  # Human-readable name (for reports)
    nav_tile: str  # testTag of the hub tile that opens this screen
    root: str  # testTag of the screen root (verified-present after navigation)
    refresh: Optional[str] = None  # testTag of the refresh button, if any
    clickable_targets: List[str] = field(default_factory=list)
    """Stable click targets to exercise during the walk (besides refresh)."""
    text_probes: List[str] = field(default_factory=list)
    """testTags whose textual content the walk-test will read."""


SCREENS: Dict[str, FederationScreen] = {
    "identity": FederationScreen(
        name="Network Identity",
        nav_tile=TILE_FEDERATION_IDENTITY,
        root="screen_federation_identity",
        refresh="btn_federation_identity_refresh",
        clickable_targets=["btn_copy_signer_key", "btn_copy_my_node_code"],
        text_probes=[
            "text_signer_key_id",
            "text_crate_version",
            "text_peer_count_total",
            "text_peer_count_canonical",
            "text_my_node_code",
        ],
    ),
    "peers": FederationScreen(
        name="Network Peers",
        nav_tile=TILE_FEDERATION_PEERS,
        root="screen_federation_peers",
        refresh="btn_federation_peers_refresh",
        clickable_targets=[
            "btn_filter_all",
            "btn_filter_canonical",
            "btn_filter_trusted",
            "btn_filter_unknown",
            "btn_add_peer",
        ],
        text_probes=[],
    ),
    "peer_detail": FederationScreen(
        # Reached by tapping a row on Peers, not from the hub. nav_tile = None semantically;
        # we use the parent peers tile and rely on row click to deep-nav.
        name="Network Peer Detail",
        nav_tile=TILE_FEDERATION_PEERS,
        root="screen_federation_peer_detail",
        refresh="btn_federation_peer_detail_refresh",
        clickable_targets=[
            "btn_copy_peer_key",
            "btn_show_sas",
            "btn_trust_unknown",
            "btn_appearance_expand",
        ],
        text_probes=["text_peer_detail_key_id"],
    ),
    "interfaces": FederationScreen(
        name="Network Interfaces",
        nav_tile=TILE_FEDERATION_INTERFACES,
        root="screen_federation_interfaces",
        refresh="btn_federation_interfaces_refresh",
        clickable_targets=[],
        text_probes=[],
    ),
    "paths": FederationScreen(
        name="Network Paths",
        nav_tile=TILE_FEDERATION_PATHS,
        root="screen_federation_paths",
        refresh=None,  # SSE auto-streams; explicit refresh n/a
        clickable_targets=["btn_paths_pause", "btn_paths_clear"],
        text_probes=["indicator_paths_connection"],
    ),
    "announces": FederationScreen(
        name="Network Announces",
        nav_tile=TILE_FEDERATION_ANNOUNCES,
        root="screen_federation_announces",
        refresh=None,
        clickable_targets=["btn_announces_pause", "btn_announces_clear"],
        text_probes=["indicator_announces_connection"],
    ),
    "queue": FederationScreen(
        name="Network Queue",
        nav_tile=TILE_FEDERATION_QUEUE,
        root="screen_federation_queue",
        refresh="btn_federation_queue_refresh",
        clickable_targets=[],
        text_probes=[
            "text_queue_depth",
            "text_envelopes_sent",
            "text_envelopes_received",
            "text_send_failures",
            "text_verify_failures",
        ],
    ),
    "diagnostics": FederationScreen(
        name="Network Diagnostics",
        nav_tile=TILE_FEDERATION_DIAGNOSTICS,
        root="screen_federation_diagnostics",
        refresh=None,
        clickable_targets=["btn_diagnostics_pause", "btn_diagnostics_clear"],
        text_probes=["input_diagnostics_search"],
    ),
    "content": FederationScreen(
        name="Network Content",
        nav_tile=TILE_FEDERATION_CONTENT,
        root="screen_federation_content",
        refresh=None,
        clickable_targets=[],
        # `input_peer_search` is an OutlinedTextField (focus-only target,
        # uses `testable` not `testableClickable` per Compose convention).
        # Probe its visibility rather than treating it as a click target.
        text_probes=["input_peer_search"],
    ),
    "trust_graph": FederationScreen(
        name="Network Trust Graph",
        nav_tile=TILE_FEDERATION_TRUST_GRAPH,
        root="screen_federation_trust_graph",
        refresh="btn_trust_graph_refresh",
        clickable_targets=[],
        text_probes=["canvas_trust_graph"],
    ),
    "map": FederationScreen(
        name="Network Map",
        nav_tile=TILE_FEDERATION_MAP,
        root="screen_federation_map",
        refresh="btn_federation_map_refresh",
        clickable_targets=[],
        text_probes=["canvas_federation_map"],
    ),
}


# Hub-level tags the walk-test verifies before drilling into sub-screens
HUB_REQUIRED_TAGS: List[str] = [
    NETWORK_HUB,
    CARD_NETWORK_IDENTITY,
    TEXT_NETWORK_IDENTITY_KEY,
    BTN_NETWORK_IDENTITY_COPY,
    SEGMENT_AGENT_MODE,
    BTN_MODE_CLIENT,
    BTN_MODE_PROXY,
    BTN_MODE_SERVER,
    TEXT_STAT_PEERS,
    TEXT_STAT_TRANSPORTS,
    TEXT_STAT_QUEUE,
    TEXT_STAT_ERRORS,
    TILE_FEDERATION_IDENTITY,
    TILE_FEDERATION_MAP,
    TILE_FEDERATION_TRUST_GRAPH,
    TILE_FEDERATION_PEERS,
    TILE_FEDERATION_INTERFACES,
    TILE_FEDERATION_PATHS,
    TILE_FEDERATION_ANNOUNCES,
    TILE_FEDERATION_QUEUE,
    TILE_FEDERATION_DIAGNOSTICS,
    TILE_FEDERATION_CONTENT,
]


# Parameterized template tags (formatters)
def peer_row_tag(key_id: str) -> str:
    """testTag for a peer row in NetworkPeersScreen."""
    return f"peer_row_{key_id}"


def peer_pick_row_tag(key_id: str) -> str:
    """testTag for a peer row in NetworkContentScreen step-1 peer picker."""
    return f"peer_pick_row_{key_id}"


def reachability_row_tag(medium: str) -> str:
    """testTag for a reachability row on PeerDetail."""
    return f"text_reachability_{medium}"


def transport_card_tag(transport_id: str) -> str:
    """testTag for a transport card on InterfacesScreen."""
    return f"card_transport_{transport_id}"


def channel_chip_tag(channel: str) -> str:
    """testTag for a channel filter chip on DiagnosticsScreen."""
    return f"chip_channel_{channel}"


def channel_counter_tag(channel: str) -> str:
    """testTag for a channel counter on DiagnosticsScreen."""
    return f"text_counter_{channel}"
