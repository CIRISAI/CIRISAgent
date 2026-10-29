"""CC 7.4 (CIRIS Constitution 1.0-rc11): a CIRIS agent takes no lethal action.

No authorization, no human in the loop and no tier opens it. The register
points CC 7.4 at ``prohibitions.LETHAL_ACTION`` (CIRISAgent#1323), so these
tests hold the symbol, the never-allowed severity and the bus refusal.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from ciris_engine.logic.buses.prohibitions import (
    LEGITIMATE_MODULE_CATEGORIES,
    LETHAL_ACTION_CAPABILITIES,
    PROHIBITED_CAPABILITIES,
    ProhibitionSeverity,
    get_capability_category,
    get_prohibition_severity,
)
from ciris_engine.logic.buses.wise_bus import WiseBus


def test_the_symbol_the_register_points_at_exists() -> None:
    assert PROHIBITED_CAPABILITIES["LETHAL_ACTION"] is LETHAL_ACTION_CAPABILITIES


def test_lethal_action_is_never_allowed_and_no_module_unlocks_it() -> None:
    assert get_prohibition_severity("LETHAL_ACTION") == ProhibitionSeverity.NEVER_ALLOWED
    assert "LETHAL_ACTION" not in LEGITIMATE_MODULE_CATEGORIES


@pytest.mark.parametrize("capability", sorted(LETHAL_ACTION_CAPABILITIES))
def test_every_term_is_claimed_by_lethal_action(capability: str) -> None:
    """Including "weapon_release", which the weapons pattern would claim on "weapon"."""
    assert get_capability_category(capability) == "LETHAL_ACTION"


@pytest.mark.parametrize(
    "capability",
    ["domain:lethal_action", "tool:target_designation", "LETHAL_FORCE", "human_target_selection_assist"],
)
def test_the_term_is_found_inside_a_capability_name(capability: str) -> None:
    assert get_capability_category(capability) == "LETHAL_ACTION"


@pytest.mark.parametrize(
    "capability",
    [
        "fire_alarm_control",
        "fire_control_panel",  # building fire safety
        "cyber_kill_chain_analysis",  # defensive security
        "software_release_authorization",
        "marketing_target_selection",
        "process_kill",
        "labor_strike_tracking",
    ],
)
def test_ordinary_tools_are_not_refused(capability: str) -> None:
    """The negative: compound terms only, so these stay allowed."""
    assert get_capability_category(capability) is None


@pytest.fixture
def wise_bus() -> WiseBus:
    time_service = MagicMock()
    time_service.now.return_value = datetime(2026, 10, 25, tzinfo=timezone.utc)
    return WiseBus(MagicMock(), time_service)


@pytest.mark.parametrize("tier", [1, 2, 3, 4, 5])
@pytest.mark.parametrize("capability", ["lethal_action", "target_designation", "weapon_release_authorization"])
def test_the_bus_refuses_it_at_every_tier(wise_bus: WiseBus, tier: int, capability: str) -> None:
    with pytest.raises(ValueError, match="ABSOLUTELY PROHIBITED.*LETHAL_ACTION"):
        wise_bus._validate_capability(capability, agent_tier=tier)
