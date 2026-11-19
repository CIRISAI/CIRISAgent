"""Room peers propose direct links via the canonical's facilitator by default (CIRISEdge#915, v44)."""

from __future__ import annotations

import json

import pytest

from ciris_engine.logic.runtime import edge_runtime


class _Engine:
    def __init__(self, hints: object) -> None:
        self._hints = hints

    def canonical_bootstrap_hints(self) -> str:
        if isinstance(self._hints, Exception):
            raise self._hints
        return json.dumps(self._hints)


HINTS = [
    {"key_id": "ciris-canonical-1-x", "kind": "reticulum", "destination": "ab12"},
    {"key_id": "ciris-canonical-1-x", "kind": "ip", "destination": "108.61.242.236:4242"},
]


@pytest.fixture(autouse=True)
def _no_bootstrap_peers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CIRIS_EDGE_BOOTSTRAP_PEERS", raising=False)


def test_an_agent_node_proposes_through_the_canonicals_signed_ip_dial_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CIRIS_DIRECT_LINK_FACILITATOR", raising=False)
    assert edge_runtime._direct_link_facilitator(_Engine(HINTS)) == "108.61.242.236:4242"


def test_bootstrap_names_the_same_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIRIS_DIRECT_LINK_FACILITATOR", "bootstrap")
    assert edge_runtime._direct_link_facilitator(_Engine(HINTS)) == "108.61.242.236:4242"


@pytest.mark.parametrize("value", ["off", "0", "", "false", "none"])
def test_the_env_can_turn_direct_links_off(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("CIRIS_DIRECT_LINK_FACILITATOR", value)
    assert edge_runtime._direct_link_facilitator(_Engine(HINTS)) is None


def test_the_env_can_name_another_facilitator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIRIS_DIRECT_LINK_FACILITATOR", "10.0.0.5:5301")
    assert edge_runtime._direct_link_facilitator(_Engine(HINTS)) == "10.0.0.5:5301"


@pytest.mark.parametrize("hints", [[], [{"kind": "reticulum", "destination": "ab"}], RuntimeError("db"), "not-a-list"])
def test_no_ip_hint_or_unreadable_hints_mean_no_facilitator(monkeypatch: pytest.MonkeyPatch, hints: object) -> None:
    monkeypatch.delenv("CIRIS_DIRECT_LINK_FACILITATOR", raising=False)
    assert edge_runtime._direct_link_facilitator(_Engine(hints)) is None


def test_the_first_bootstrap_peer_is_the_facilitator_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """A harness mesh's bootstrap peer is its own canonical; persist's hint may name another."""
    monkeypatch.delenv("CIRIS_DIRECT_LINK_FACILITATOR", raising=False)
    monkeypatch.setenv("CIRIS_EDGE_BOOTSTRAP_PEERS", " 172.20.0.2:4242 , 10.9.9.9:4242")
    assert edge_runtime._direct_link_facilitator(_Engine(HINTS)) == "172.20.0.2:4242"
    monkeypatch.setenv("CIRIS_DIRECT_LINK_FACILITATOR", "bootstrap")
    assert edge_runtime._direct_link_facilitator(_Engine(HINTS)) == "172.20.0.2:4242"


@pytest.mark.parametrize("raw", ["", " , "])
def test_an_empty_bootstrap_list_falls_back_to_the_signed_hint(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.delenv("CIRIS_DIRECT_LINK_FACILITATOR", raising=False)
    monkeypatch.setenv("CIRIS_EDGE_BOOTSTRAP_PEERS", raw)
    assert edge_runtime._direct_link_facilitator(_Engine(HINTS)) == "108.61.242.236:4242"


def test_the_override_still_wins_over_a_bootstrap_peer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIRIS_EDGE_BOOTSTRAP_PEERS", "172.20.0.2:4242")
    monkeypatch.setenv("CIRIS_DIRECT_LINK_FACILITATOR", "off")
    assert edge_runtime._direct_link_facilitator(_Engine(HINTS)) is None
