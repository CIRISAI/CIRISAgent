"""Tests for the verb_specific_data builders on ThoughtProcessor.

These two helpers — `_build_tool_verb_specific_data` and
`_build_defer_verb_specific_data` — are the per-verb adapters that
flatten verb-specific fields into the generic
VerbSecondPassResultEvent.verb_specific_data payload (FSD §4). They're
the seam where adding a new verb-second-pass evaluator picks up its
own field shape without changing the event schema.

Both helpers are state-free (don't read `self` attributes), so we call
them via the class with a MagicMock self stub to avoid pulling in the
full ThoughtProcessor construction machinery.
"""

from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor
from ciris_engine.schemas.actions.parameters import (
    DeferParams,
    PonderParams,
    SpeakParams,
    ToolParams,
)
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.services.agent_credits import DomainCategory
from ciris_engine.schemas.services.deferral_taxonomy import (
    DeferralNeedCategory,
    DeferralOperationalReason,
)


def _build_tool(tool_name: str, tsaspdma_result: ActionSelectionDMAResult) -> Dict[str, Any]:
    """Call the unbound helper without constructing a full ThoughtProcessor."""
    return ThoughtProcessor._build_tool_verb_specific_data(
        MagicMock(), tool_name=tool_name, tsaspdma_result=tsaspdma_result
    )


def _build_defer(dsaspdma_result: ActionSelectionDMAResult) -> Dict[str, Any]:
    return ThoughtProcessor._build_defer_verb_specific_data(MagicMock(), dsaspdma_result=dsaspdma_result)


class TestBuildToolVerbSpecificData:
    """TOOL second-pass payload — replaces TSASPDMAResultEvent's explicit
    fields. Carries original_tool_name, final_tool_name, original/final
    parameters."""

    def test_tool_proceed_with_refined_parameters(self):
        """Happy path: TSASPDMA confirms the TOOL action and may have refined
        parameters — both names are populated and final_parameters carries
        the refined dict."""
        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.TOOL,
            action_parameters=ToolParams(name="curl", parameters={"url": "https://example.com"}),
            rationale="TSASPDMA confirmed",
        )
        data = _build_tool(tool_name="curl", tsaspdma_result=result)

        assert data["original_tool_name"] == "curl"
        assert data["final_tool_name"] == "curl"
        assert data["final_parameters"] == {"url": "https://example.com"}
        # ASPDMA didn't pre-provide params in this path
        assert data["original_parameters"] == {}

    def test_tool_switched_to_speak_clears_tool_fields(self):
        """TSASPDMA can switch to SPEAK for clarification — final_tool_name
        becomes None, final_parameters stays empty. The lens needs that
        signal to know "this thought ended up not running the tool."""
        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.SPEAK,
            action_parameters=SpeakParams(content="please clarify"),
            rationale="TSASPDMA wants clarification",
        )
        data = _build_tool(tool_name="curl", tsaspdma_result=result)

        assert data["original_tool_name"] == "curl"
        assert data["final_tool_name"] is None
        assert data["final_parameters"] == {}

    def test_tool_switched_to_ponder_clears_tool_fields(self):
        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.PONDER,
            action_parameters=PonderParams(questions=["should I pick a different tool?"]),
            rationale="reconsider",
        )
        data = _build_tool(tool_name="curl", tsaspdma_result=result)

        assert data["final_tool_name"] is None
        assert data["final_parameters"] == {}

    def test_dict_action_parameters_handled(self):
        """action_parameters can arrive as a dict or a Pydantic model
        depending on serialization path. Both must produce the same
        verb_specific_data shape."""
        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.TOOL,
            action_parameters={"name": "self_help", "parameters": {"topic": "memory"}},
            rationale="dict-shaped params",
        )
        data = _build_tool(tool_name="self_help", tsaspdma_result=result)

        assert data["final_tool_name"] == "self_help"
        assert data["final_parameters"] == {"topic": "memory"}


class TestBuildDeferVerbSpecificData:
    """DEFER second-pass payload — closes the prior asymmetry where
    DSASPDMA dispatched but emitted no event. Carries the
    rights-basis classification fields that DSASPDMA refines onto
    DeferParams."""

    def test_full_deferral_classification(self):
        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.DEFER,
            action_parameters=DeferParams(
                channel_id="qa-channel",
                reason="Licensed legal review required.",
                defer_until="2026-05-15T00:00:00Z",
                reason_code=DeferralOperationalReason.LICENSED_DOMAIN_REQUIRED,
                needs_category=DeferralNeedCategory.JUSTICE_AND_LEGAL_AGENCY,
                secondary_needs_categories=[DeferralNeedCategory.GENERAL_HUMAN_OVERSIGHT],
                rights_basis=["fair_trial", "access_to_justice"],
                domain_hint=DomainCategory.LEGAL,
            ),
            rationale="DSASPDMA refined defer",
        )
        data = _build_defer(dsaspdma_result=result)

        # All taxonomy fields land in the payload
        assert data["rights_basis"] == ["fair_trial", "access_to_justice"]
        assert data["primary_need_category"] == DeferralNeedCategory.JUSTICE_AND_LEGAL_AGENCY.value
        assert data["secondary_need_categories"] == [
            DeferralNeedCategory.GENERAL_HUMAN_OVERSIGHT.value,
        ]
        assert data["domain_hint"] == DomainCategory.LEGAL.value
        assert data["operational_reason"] == DeferralOperationalReason.LICENSED_DOMAIN_REQUIRED.value
        assert data["defer_reason"] == "Licensed legal review required."
        assert data["defer_until"] == "2026-05-15T00:00:00Z"

    def test_minimal_deferral_with_missing_optional_taxonomy(self):
        """When DSASPDMA produces a deferral without domain_hint /
        reason_code (general oversight cases), the payload carries None
        for those fields rather than crashing."""
        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.DEFER,
            action_parameters=DeferParams(
                channel_id=None,
                reason="Need wise authority guidance.",
                rights_basis=[],
            ),
            rationale="DSASPDMA general oversight",
        )
        data = _build_defer(dsaspdma_result=result)

        assert data["rights_basis"] == []
        assert data["primary_need_category"] is None
        assert data["secondary_need_categories"] == []
        assert data["domain_hint"] is None
        assert data["operational_reason"] is None
        assert data["defer_reason"] == "Need wise authority guidance."
        assert data["defer_until"] is None

    def test_non_defer_params_returns_empty_dict(self):
        """If the path is somehow invoked with non-DeferParams (shouldn't
        happen — _maybe_run_dsaspdma type-checks first — but defensive)
        the helper returns {} rather than raise. Bypass Pydantic
        validation via model_construct to simulate the "wrong shape on
        a DEFER path" case the helper guards against."""
        result = ActionSelectionDMAResult.model_construct(
            selected_action=HandlerActionType.DEFER,
            action_parameters=SpeakParams(content="not a DeferParams"),
            rationale="schema-mismatch defensive check",
        )
        data = _build_defer(dsaspdma_result=result)
        assert data == {}
