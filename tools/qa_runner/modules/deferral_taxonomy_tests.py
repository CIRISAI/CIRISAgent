"""QA module for DSASPDMA taxonomy coverage and deferral routing guarantees."""

from unittest.mock import AsyncMock, MagicMock

from rich.console import Console

from ciris_engine.logic.buses.prohibitions import COMMUNITY_MODERATION_CAPABILITIES, PROHIBITED_CAPABILITIES
from ciris_engine.logic.buses.prohibitions import get_capability_category
from ciris_engine.logic.buses.wise_bus import WiseBus
from ciris_engine.schemas.services.agent_credits import DomainCategory
from ciris_engine.schemas.services.authority_core import GuidanceRequest
from ciris_engine.schemas.services.deferral_taxonomy import (
    DOMAIN_TO_NEED_CATEGORY,
    NEED_CATEGORY_RIGHTS_BASIS,
    PROHIBITION_CATEGORY_TO_NEED_CATEGORY,
    DeferralOperationalReason,
    build_deferral_taxonomy_prompt,
)

from .base_test_module import BaseTestModule


class DeferralTaxonomyTests(BaseTestModule):
    """QA checks for taxonomy completeness and DSASPDMA prompt/routing behavior."""

    def __init__(
        self,
        client,
        console: Console,
        fail_fast: bool = True,
        test_timeout: float = 30.0,
    ) -> None:
        super().__init__(client, console, fail_fast=fail_fast, test_timeout=test_timeout)

    async def run(self):
        self.console.print("\n[cyan]Deferral Taxonomy QA[/cyan]")

        tests = [
            ("domain_taxonomy_exhaustive", self.test_domain_taxonomy_exhaustive),
            ("prohibited_capability_coverage", self.test_prohibited_capability_coverage),
            ("localized_prompt_rendering", self.test_localized_prompt_rendering),
            ("operational_reasons_exhaustive", self.test_operational_reasons_exhaustive),
            ("wisebus_auto_deferral_taxonomy", self.test_wisebus_auto_deferral_taxonomy),
        ]

        for test_name, test_func in tests:
            try:
                await test_func()
                self._record_result(test_name, True)
            except Exception as exc:  # noqa: BLE001
                self._record_result(test_name, False, str(exc))
                if self.fail_fast:
                    break

        return self.results

    async def test_domain_taxonomy_exhaustive(self) -> None:
        """Every licensed domain should map into the rights-based taxonomy."""

        assert set(DOMAIN_TO_NEED_CATEGORY) == set(DomainCategory)
        for rights_basis in NEED_CATEGORY_RIGHTS_BASIS.values():
            assert rights_basis

    async def test_prohibited_capability_coverage(self) -> None:
        """Every prohibited capability must be recognized and mapped."""

        expected_categories = set(PROHIBITED_CAPABILITIES) | {
            f"COMMUNITY_{category}" for category in COMMUNITY_MODERATION_CAPABILITIES
        }
        assert set(PROHIBITION_CATEGORY_TO_NEED_CATEGORY) == expected_categories

        for category, capabilities in PROHIBITED_CAPABILITIES.items():
            for capability in capabilities:
                detected_category = get_capability_category(capability)
                assert detected_category is not None
                assert detected_category in PROHIBITION_CATEGORY_TO_NEED_CATEGORY

        for category, capabilities in COMMUNITY_MODERATION_CAPABILITIES.items():
            expected_category = f"COMMUNITY_{category}"
            for capability in capabilities:
                detected_category = get_capability_category(capability)
                assert detected_category is not None
                assert detected_category in PROHIBITION_CATEGORY_TO_NEED_CATEGORY

    async def test_localized_prompt_rendering(self) -> None:
        """Localized DSASPDMA prompts should show the taxonomy in the prompt language."""

        localized_prompt = build_deferral_taxonomy_prompt("es")

        assert "TAXONOMÍA DE DERECHOS / NECESIDADES" in localized_prompt
        assert "Fundamento de derechos" in localized_prompt
        assert "justice_and_legal_agency" in localized_prompt
        assert "Se requiere un especialista con licencia" in localized_prompt

    async def test_operational_reasons_exhaustive(self) -> None:
        """Every deferral reason code should be presented to the classifier."""

        prompt = build_deferral_taxonomy_prompt("en")
        for reason in DeferralOperationalReason:
            assert reason.value in prompt

    async def test_wisebus_auto_deferral_taxonomy(self) -> None:
        """WiseBus auto-deferrals should carry typed taxonomy fields."""

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
