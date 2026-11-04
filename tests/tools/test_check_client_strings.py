"""The gate that keeps pinned-client strings from rendering raw in the app."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "check_client_strings", Path(__file__).resolve().parents[2] / "tools" / "dev" / "check_client_strings.py"
)
assert _spec and _spec.loader
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def test_a_client_key_missing_from_the_bundle_is_reported() -> None:
    client = {"mobile": {"owned_agents_claim": "Claim a node"}, "nav": {"surface": {"owned_agents": "Agents you own"}}}
    bundle = {"mobile": {"other": "x"}}
    assert gate.missing_keys(client, bundle) == ["mobile.owned_agents_claim", "nav.surface.owned_agents"]


def test_agent_owned_sections_are_not_the_clients_to_add() -> None:
    client = {"prompts": {"language_guidance": "old flat string"}, "_meta": {"language": "en"}}
    assert gate.missing_keys(client, {"prompts": {"language_guidance": {"01_preamble": "x"}}}) == []


def test_merge_adds_only_what_is_missing_and_replaces_nothing() -> None:
    client = {"mobile": {"keep": "client text", "new": "added"}, "nav": {"surface": {"a": "1", "b": "2"}}}
    bundle = {"mobile": {"keep": "agent text"}, "prompts": {"x": "y"}}
    assert gate.merge_missing(client, bundle) == 3
    assert bundle["mobile"] == {"keep": "agent text", "new": "added"}
    assert bundle["nav"] == {"surface": {"a": "1", "b": "2"}}
    assert gate.missing_keys(client, bundle) == []


def test_merge_leaves_agent_owned_sections_alone() -> None:
    bundle = {"prompts": {"language_guidance": {"01_preamble": "x"}}}
    assert gate.merge_missing({"prompts": {"language_guidance": "old", "new_one": "z"}}, bundle) == 0
    assert bundle == {"prompts": {"language_guidance": {"01_preamble": "x"}}}


def _integrity():
    spec = importlib.util.spec_from_file_location(
        "check_localization_integrity",
        Path(__file__).resolve().parents[2] / "tools" / "dev" / "check_localization_integrity.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[spec.name] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


def test_a_translated_placeholder_is_still_corrupt() -> None:
    check = _integrity().check_placeholders
    found = check("am", {"k": "የ {የተጠቃሚ} ስም"}, {"k": "the {user} name"}, set())
    assert [f.check for f in found if f.check == "placeholder-corrupt"] == ["placeholder-corrupt"]


def test_literal_sample_text_identical_to_english_is_not_corrupt() -> None:
    check = _integrity().check_placeholders
    en = {"k": '{"transport_destination": {…}, "signature": …}'}
    found = check("am", {"k": '{"transport_destination": {…}, "signature": …} ምሳሌ'}, en, set())
    assert [f for f in found if f.check == "placeholder-corrupt"] == []
