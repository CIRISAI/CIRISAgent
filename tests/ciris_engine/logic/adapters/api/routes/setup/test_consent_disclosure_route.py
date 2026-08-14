"""The consent screen RENDERS the substrate's copy — it does not compose it.

``ciris_server.consent_disclosure()`` is exported so the wizard can show the
substrate's own wording; until now the only caller was a test. Two things have to
hold for that to be worth anything:

1. The route actually serves the substrate's payload, unedited.
2. The typed models carry EVERY field the substrate publishes. A model that
   silently drops a key is the same drift the export exists to prevent, just
   moved one layer down — so a missing key fails here rather than vanishing from
   the screen.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import ciris_server as cs
import pytest

from ciris_engine.schemas.consent.disclosure import ConsentDisclosure


@pytest.fixture(scope="module")
def raw() -> Dict[str, Any]:
    payload = cs.consent_disclosure()
    return json.loads(payload) if isinstance(payload, str) else payload


def _keys(node: Any, prefix: str = "") -> List[str]:
    """Every dotted key path in the payload, list elements collapsed by shape."""
    out: List[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            path = f"{prefix}.{k}" if prefix else k
            out.append(path)
            out.extend(_keys(v, path))
    elif isinstance(node, list):
        for item in node:
            out.extend(_keys(item, f"{prefix}[]"))
    return out


class TestModelsCarryTheWholeDisclosure:
    def test_the_payload_validates(self, raw: Dict[str, Any]) -> None:
        ConsentDisclosure.model_validate(raw)

    def test_no_substrate_key_is_dropped(self, raw: Dict[str, Any]) -> None:
        """New substrate copy must reach the UI, not be silently discarded."""
        model = ConsentDisclosure.model_validate(raw)
        round_tripped = model.model_dump(exclude_none=True)
        missing = sorted(set(_keys(raw)) - set(_keys(round_tripped)))
        assert not missing, (
            "the substrate publishes copy the typed disclosure drops, so it can never "
            f"reach the consent screen — add these fields: {missing}"
        )

    def test_every_string_carries_a_localization_id(self, raw: Dict[str, Any]) -> None:
        """The 29-locale catalogue is keyed on these ids — a missing one is untranslatable."""
        model = ConsentDisclosure.model_validate(raw)
        strings = [
            model.primary_action,
            model.announce_requirement,
            model.independent,
            model.location.title,
            model.location.purpose,
            model.location.permits,
        ]
        strings += [g.title for g in model.grants] + [g.permits for g in model.grants]
        strings += model.declining_analyze.costs + model.location.declining.costs
        for s in strings:
            assert s.id and "." in s.id, f"string has no catalogue key: {s!r}"
            assert s.text, f"catalogue key {s.id} has no substrate text"


class TestTheContractTheScreenDependsOn:
    def test_announce_is_the_floor_not_a_choice(self, raw: Dict[str, Any]) -> None:
        """Screen 2 states a REQUIREMENT here; it must not be rendered as optional."""
        model = ConsentDisclosure.model_validate(raw)
        assert model.announce_requirement.id == "mesh.announce_requirement"
        assert model.announce_requirement.text.strip()

    def test_replication_is_required_and_analyze_is_not(self, raw: Dict[str, Any]) -> None:
        model = ConsentDisclosure.model_validate(raw)
        replication = model.grant("replication")
        analyze = model.grant("analyze")
        assert replication is not None and replication.required is True
        assert analyze is not None and analyze.required is False, (
            "analyze is required=false with named costs — the wizard must render it "
            "as a real toggle, not hardcode it"
        )

    def test_declining_analyze_states_its_costs(self, raw: Dict[str, Any]) -> None:
        model = ConsentDisclosure.model_validate(raw)
        assert model.declining_analyze.allowed is True
        assert len(model.declining_analyze.costs) >= 1

    def test_location_is_optional_and_declinable_with_named_costs(self, raw: Dict[str, Any]) -> None:
        model = ConsentDisclosure.model_validate(raw)
        assert model.location.required is False
        assert model.location.declining.allowed is True
        assert len(model.location.declining.costs) >= 1

    def test_location_bound_is_read_not_restated(self, raw: Dict[str, Any]) -> None:
        """The screen must read max_resolution from here — a copied literal drifts."""
        model = ConsentDisclosure.model_validate(raw)
        assert isinstance(model.location.max_resolution, int)
        assert model.location.cell_format == "h3"

    def test_grant_lookup_is_tolerant_of_a_build_that_omits_one(self, raw: Dict[str, Any]) -> None:
        model = ConsentDisclosure.model_validate(raw)
        assert model.grant("no-such-grant") is None
