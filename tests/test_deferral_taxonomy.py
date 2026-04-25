"""Coverage tests for the rights-based deferral taxonomy."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ciris_engine.logic.buses.prohibitions import COMMUNITY_MODERATION_CAPABILITIES, PROHIBITED_CAPABILITIES
from ciris_engine.logic.buses.wise_bus import WiseBus
from ciris_engine.schemas.services.agent_credits import DomainCategory
from ciris_engine.schemas.services.authority_core import GuidanceRequest
from ciris_engine.schemas.services.deferral_taxonomy import (
    DOMAIN_TO_NEED_CATEGORY,
    NEED_CATEGORY_RIGHTS_BASIS,
    PROHIBITION_CATEGORY_TO_NEED_CATEGORY,
    DeferralNeedCategory,
    DeferralOperationalReason,
    build_deferral_taxonomy_prompt,
    get_need_category_for_prohibition_category,
    get_rights_basis_for_need_category,
)
from ciris_engine.logic.buses.prohibitions import get_capability_category


def test_every_domain_category_has_needs_mapping() -> None:
    """Licensed-domain deferrals must always map to a human-rights / needs category."""

    assert set(DOMAIN_TO_NEED_CATEGORY) == set(DomainCategory)


def test_every_prohibition_category_has_needs_mapping() -> None:
    """Every prohibition bucket must map into the deferral taxonomy."""

    expected_categories = set(PROHIBITED_CAPABILITIES) | {
        f"COMMUNITY_{name}" for name in COMMUNITY_MODERATION_CAPABILITIES
    }
    assert set(PROHIBITION_CATEGORY_TO_NEED_CATEGORY) == expected_categories


def test_every_prohibited_capability_is_categorized_and_mapped() -> None:
    """All prohibited capabilities should be restricted and covered by the taxonomy."""

    categorized = 0

    for category, capabilities in PROHIBITED_CAPABILITIES.items():
        for capability in capabilities:
            detected_category = get_capability_category(capability)
            assert detected_category is not None
            assert detected_category in PROHIBITION_CATEGORY_TO_NEED_CATEGORY
            assert isinstance(get_need_category_for_prohibition_category(detected_category), DeferralNeedCategory)
            categorized += 1

    for community_category, capabilities in COMMUNITY_MODERATION_CAPABILITIES.items():
        expected_category = f"COMMUNITY_{community_category}"
        for capability in capabilities:
            detected_category = get_capability_category(capability)
            assert detected_category is not None
            assert detected_category in PROHIBITION_CATEGORY_TO_NEED_CATEGORY
            assert isinstance(get_need_category_for_prohibition_category(detected_category), DeferralNeedCategory)
            categorized += 1

    assert categorized > 0


def test_taxonomy_encodes_legal_and_financial_rights_basis() -> None:
    """Legal and financial access should be treated as rights-impacting needs."""

    assert DOMAIN_TO_NEED_CATEGORY[DomainCategory.LEGAL] == DeferralNeedCategory.JUSTICE_AND_LEGAL_AGENCY
    assert DOMAIN_TO_NEED_CATEGORY[DomainCategory.FINANCIAL] == DeferralNeedCategory.LIVELIHOOD_AND_FINANCIAL_SECURITY
    assert "access_to_justice" in get_rights_basis_for_need_category(DeferralNeedCategory.JUSTICE_AND_LEGAL_AGENCY)
    assert "social_security" in get_rights_basis_for_need_category(
        DeferralNeedCategory.LIVELIHOOD_AND_FINANCIAL_SECURITY
    )


def test_every_need_category_has_rights_basis() -> None:
    """Each needs category should carry an explicit rights basis."""

    for category in DeferralNeedCategory:
        assert NEED_CATEGORY_RIGHTS_BASIS[category]


def test_localized_taxonomy_prompt_contains_spanish_guidance() -> None:
    """Localized DSASPDMA prompts should render the taxonomy in the user's language."""

    prompt = build_deferral_taxonomy_prompt("es")

    assert "TAXONOMÍA DE DERECHOS / NECESIDADES" in prompt
    assert "Fundamento de derechos" in prompt
    assert "justice_and_legal_agency" in prompt
    assert "licensed_domain_required" in prompt
    assert "Se requiere un especialista con licencia" in prompt


def test_operational_reason_prompt_is_exhaustive() -> None:
    """Every operational deferral reason should appear in the prompt text."""

    prompt = build_deferral_taxonomy_prompt("en")
    for reason in DeferralOperationalReason:
        assert reason.value in prompt


@pytest.mark.asyncio
async def test_wisebus_auto_deferral_attaches_taxonomy_metadata() -> None:
    """WiseBus auto-deferrals should carry the typed taxonomy fields."""

    mock_registry = MagicMock()
    mock_time = MagicMock()
    bus = WiseBus(service_registry=mock_registry, time_service=mock_time)
    bus.send_deferral = AsyncMock(return_value=True)

    response = await bus.request_guidance(
        GuidanceRequest(
            context="Should I provide legal advice?",
            options=["yes", "no"],
            recommendation=None,
            capability="legal_advice",
        ),
        agent_tier=1,
    )

    assert "licensed LEGAL handler" in response.custom_guidance
    bus.send_deferral.assert_awaited_once()

    deferral_context = bus.send_deferral.await_args.args[0]
    assert deferral_context.domain_hint == DomainCategory.LEGAL
    assert deferral_context.reason_code == DeferralOperationalReason.LICENSED_DOMAIN_REQUIRED
    assert deferral_context.needs_category == DeferralNeedCategory.JUSTICE_AND_LEGAL_AGENCY
    assert "access_to_justice" in deferral_context.rights_basis
