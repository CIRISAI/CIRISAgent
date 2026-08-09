"""The KMP client addresses TWO services — guard that it keeps them apart.

FSD ``FIRST_RUN_WIZARD_2.9.14`` §2/§5/§6. The Rust node (:4243) and the Python
brain (:8080) serve disjoint surfaces and 8080 never fronts 4243, so a single
``baseUrl`` cannot be correct. 2.9.13 shipped one, pointed it at the brain, and
first-run looped forever: every node call 404'd, the node read as unowned, and
the wizard restarted.

These are source-level guards. They cannot prove the running app is correct, but
they fail CI the moment the two URLs are conflated again or a route that never
existed is reintroduced — which is exactly how the bug shipped.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CLIENT = Path(__file__).resolve().parents[2] / "client"

SHARED = CLIENT / "shared/src/commonMain/kotlin/ai/ciris/mobile/shared"
CIRIS_APP = SHARED / "CIRISApp.kt"
API_CLIENT = SHARED / "api/CIRISApiClient.kt"
DESKTOP_MAIN = CLIENT / "desktopApp/src/main/kotlin/ai/ciris/desktop/Main.kt"

# Every place CIRISApp() is constructed. All of them must pass the split params.
ENTRY_POINTS = [
    DESKTOP_MAIN,
    CLIENT / "androidApp/src/main/kotlin/ai/ciris/mobile/MainActivity.kt",
    CLIENT / "shared/src/iosMain/kotlin/Main.ios.kt",
    CLIENT / "shared/src/wasmJsMain/kotlin/Main.kt",
]

# Paths the client called that never existed on either port (FSD §0.2), mapped to
# the route that does exist.
NEVER_EXISTED = {
    "/v1/node/health": "/v1/health",
    "/v1/self/key-record": "/v1/federation/self-key-record",
}


def _kotlin_sources() -> list[Path]:
    return [
        p
        for p in CLIENT.rglob("*.kt")
        if "/build/" not in str(p) and "/generated-api/" not in str(p)
    ]


@pytest.mark.skipif(not CLIENT.is_dir(), reason="KMP client not present in this checkout")
class TestClientServiceSplit:
    def test_cirisapp_declares_both_base_urls(self) -> None:
        src = CIRIS_APP.read_text(encoding="utf-8")
        assert "apiBaseUrl: String" in src, "CIRISApp must take an explicit brain base URL"
        assert "nodeBaseUrl: String" in src, "CIRISApp must take an explicit node base URL"
        assert not re.search(
            r"^\s*baseUrl: String\s*=", src, re.MULTILINE
        ), "the single conflated baseUrl parameter must not come back"

    def test_no_entry_point_passes_the_conflated_base_url(self) -> None:
        for path in ENTRY_POINTS:
            src = path.read_text(encoding="utf-8")
            assert "CIRISApp(" in src, f"{path} no longer constructs CIRISApp — update this guard"
            assert not re.search(
                r"^\s*baseUrl\s*=", src, re.MULTILINE
            ), f"{path} still passes the conflated baseUrl to CIRISApp"
            assert re.search(
                r"^\s*apiBaseUrl\s*=", src, re.MULTILINE
            ), f"{path} must pass apiBaseUrl explicitly"

    def test_desktop_does_not_point_the_node_at_the_brain_port(self) -> None:
        """The one divergent line: ours said 8080 where CIRISServer's said 4243."""
        src = DESKTOP_MAIN.read_text(encoding="utf-8")
        node_lines = [line for line in src.splitlines() if re.match(r"\s*nodeBaseUrl\s*=", line)]
        assert node_lines, "desktop Main.kt must pass nodeBaseUrl explicitly"
        node_line = node_lines[0]
        assert "4243" in node_line, f"desktop node URL must be the node read API: {node_line!r}"
        assert "8080" not in node_line, f"desktop node URL must not be the brain: {node_line!r}"

    def test_node_base_url_default_is_the_node_read_api(self) -> None:
        src = CIRIS_APP.read_text(encoding="utf-8")
        default = re.search(r"nodeBaseUrl: String\s*=\s*(.+)", src)
        assert default is not None
        assert "LOCAL_NODE_URL" in default.group(1), (
            "nodeBaseUrl must default to CIRISApiClient.LOCAL_NODE_URL, "
            f"got {default.group(1)!r}"
        )
        assert 'const val LOCAL_NODE_URL = "http://127.0.0.1:4243"' in API_CLIENT.read_text(
            encoding="utf-8"
        )

    @pytest.mark.parametrize("dead_path,live_path", sorted(NEVER_EXISTED.items()))
    def test_routes_that_never_existed_are_not_called(self, dead_path: str, live_path: str) -> None:
        offenders = [
            str(p.relative_to(CLIENT))
            for p in _kotlin_sources()
            if dead_path in p.read_text(encoding="utf-8")
        ]
        assert not offenders, (
            f"{dead_path} 404s on both ports — use {live_path}. Called from: {offenders}"
        )

    def test_no_node_endpoint_is_addressed_via_the_brain_url(self) -> None:
        """Node-native routes must never be built from the client's own baseUrl.

        The shared `CIRISApiClient` is constructed against `apiBaseUrl` (the
        Python brain), so `"$baseUrl/v1/self/..."` inside it means "ask the brain
        for a route only the node serves" — a 404, and the 2.9.13 loop. Node
        routes take an explicit node URL parameter instead.
        """
        # Substrate prefixes (brain_adapter._SUBSTRATE_PREFIXES) plus the node's
        # half of the split /v1/setup surface (FSD §2). /v1/auth and /v1/config
        # are excluded: the Python brain serves its own, and the client's
        # login/config calls legitimately go there.
        node_only = [
            "/v1/federation",
            "/v1/self",
            "/v1/accord",
            "/v1/health",
            "/v1/setup/root",
            "/v1/setup/owned-nodes",
            "/v1/setup/claim-remote",
        ]
        src = API_CLIENT.read_text(encoding="utf-8")
        offenders = [
            line.strip()
            for line in src.splitlines()
            if "$baseUrl" in line and any(p in line for p in node_only)
        ]
        assert not offenders, (
            "these node-native routes are addressed via the client's baseUrl (the brain) "
            f"instead of an explicit node URL: {offenders}"
        )

    def test_owner_hint_gates_nothing(self) -> None:
        """`/v1/auth/owner-hint` is a masked login-screen string, not a predicate.

        It reads the WaCert auth store; `require_owner_bound` reads the CEG graph.
        Routing on the hint is what produced the loop (FSD §5), so the ownership
        probe must not reference it.
        """
        src = CIRIS_APP.read_text(encoding="utf-8")
        probe = re.search(
            r"private suspend fun probeNodeOwnership\(.*?\n\}", src, re.DOTALL
        )
        assert probe is not None, "probeNodeOwnership is the ownership predicate — it must exist"
        assert "getOwnerHint" not in probe.group(0), "ownership routing must not consult owner-hint"
        assert "getOwnedNodes" in probe.group(0), "ownership routing must consult /v1/setup/owned-nodes"

        has_owner = re.search(r"private suspend fun nodeHasOwner\(.*?\n(?=\n|/\*\*)", src, re.DOTALL)
        assert has_owner is not None
        assert "getOwnerHint" not in has_owner.group(0), "nodeHasOwner must not consult owner-hint"
