"""Golden-bytes proof for the #972 compose_messages() seam extraction.

The snapshots in ``golden/`` were captured from the UNMODIFIED inline
composition paths (commit "golden capture ... BEFORE #972 seam extraction")
using the exact fixtures in ``compose_golden.py``. These tests prove:

1. ``evaluate()`` still produces byte-identical messages after the extraction
   (the rewiring changed nothing), and
2. the new ``compose_messages()`` seams, called DIRECTLY with the gathered
   inputs and no LLM/persistence access, reproduce the same bytes - i.e.
   composition is now callable without an LLM call (the #973 prerequisite).

Any change to composition (block order, separator, interpolation, template
routing) turns these red.
"""

from typing import List, cast
from unittest.mock import Mock

import pytest

from ciris_engine.schemas.runtime.system_context import SystemSnapshot
from ciris_engine.schemas.types import JSONDict
from tests.ciris_engine.logic.dma.compose_golden import (
    DMA_NAMES,
    canonical_json,
    capture_via_evaluate,
    deterministic_prompt_environment,
    load_golden,
    make_context,
    make_csdma_result,
    make_defer_aspdma_result,
    make_dsdma_queue_item,
    make_dsdma_result,
    make_enhanced_inputs,
    make_ethical_result,
    make_queue_item,
    make_task,
    pin_aspdma_context_builder,
)


def _assert_matches_golden(name: str, messages: List[JSONDict]) -> None:
    golden = load_golden(name)
    assert len(messages) == len(golden), (
        f"{name}: composed {len(messages)} messages, pre-refactor golden has {len(golden)}"
    )
    for i, (got, want) in enumerate(zip(messages, golden)):
        assert got == want, f"{name}: message {i} (role={want.get('role')}) diverged from pre-refactor golden bytes"
    assert canonical_json(messages) == canonical_json(golden)


# ---------------------------------------------------------------------------
# 1. evaluate() path still produces the pre-refactor bytes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", DMA_NAMES)
@pytest.mark.asyncio
async def test_evaluate_path_reproduces_pre_refactor_bytes(name: str) -> None:
    messages = await capture_via_evaluate(name)
    _assert_matches_golden(name, messages)


# ---------------------------------------------------------------------------
# 2. compose_messages() seams, called directly (no LLM, no awaits, no
#    persistence), reproduce the pre-refactor bytes
# ---------------------------------------------------------------------------


def test_pdma_compose_seam_matches_golden() -> None:
    from ciris_engine.logic.dma.pdma import EthicalPDMAEvaluator

    with deterministic_prompt_environment():
        dma = EthicalPDMAEvaluator(service_registry=Mock())
        item = make_queue_item()
        # Gathered inputs, replicated from evaluate()'s data-gathering phase.
        task_context_str = dma.format_task_context(make_task(), item.thought_depth)
        system_snapshot_str, user_profile_str = dma._build_context_strings(make_context(), thought=item)
        full_context_str = f"=== ORIGINAL TASK ===\n{task_context_str}\n\n{system_snapshot_str}{user_profile_str}"

        messages = dma.compose_messages(str(item.content), full_context_str, [])
    _assert_matches_golden("pdma", messages)


def test_csdma_compose_seam_matches_golden() -> None:
    from ciris_engine.logic.dma.csdma import CSDMAEvaluator

    with deterministic_prompt_environment():
        dma = CSDMAEvaluator(service_registry=Mock())
        item = make_queue_item()
        task_context_str = dma.format_task_context(make_task(), item.thought_depth)
        system_snapshot_str, user_profiles_str, context_summary = dma._extract_context_data(make_context())

        messages = dma.compose_messages(
            str(item.content),
            context_summary,
            task_context_str,
            system_snapshot_str,
            user_profiles_str,
            images=[],
        )
    _assert_matches_golden("csdma", messages)


def test_idma_compose_seam_matches_golden() -> None:
    from ciris_engine.logic.dma.idma import IDMAEvaluator

    with deterministic_prompt_environment():
        dma = IDMAEvaluator(service_registry=Mock())
        item = make_queue_item()
        task_context_str = dma.format_task_context(make_task(), item.thought_depth)
        system_snapshot_str, user_profiles_str, context_summary = dma._extract_context_data(make_context())
        prior_dma_context = dma._build_prior_dma_context(
            make_ethical_result(), make_csdma_result(), make_dsdma_result()
        )

        messages = dma.compose_messages(
            str(item.content),
            context_summary,
            task_context_str,
            system_snapshot_str,
            user_profiles_str,
            prior_dma_context,
            images=[],
        )
    _assert_matches_golden("idma", messages)


def test_dsdma_compose_seam_matches_golden() -> None:
    from ciris_engine.logic.dma.dsdma_base import BaseDSDMA, _format_domain_specific_knowledge
    from ciris_engine.logic.formatters import format_system_snapshot

    with deterministic_prompt_environment():
        dma = BaseDSDMA(
            domain_name="golden_domain",
            service_registry=Mock(),
            domain_specific_knowledge={
                "rules_summary": "Golden rules: always be deterministic.",
                "escalation_paths": ["wise_authority", "human_operator"],
            },
        )
        item = make_dsdma_queue_item()
        # Gathered inputs, replicated from evaluate_thought()'s no-DMAInputData path.
        task_context_str = dma.format_task_context(make_task(), item.thought_depth)
        task_context_block = f"=== ORIGINAL TASK ===\n{task_context_str}\n\n"
        context_str = "No specific platform context provided."
        rules_summary_str = _format_domain_specific_knowledge(dma.domain_specific_knowledge)
        assert isinstance(item.initial_context, dict)
        snapshot_raw = item.initial_context["system_snapshot"]
        assert isinstance(snapshot_raw, dict)
        identity = snapshot_raw["agent_identity"]
        assert isinstance(identity, dict)
        identity_block = (
            "=== CORE IDENTITY - THIS IS WHO YOU ARE! ===\n"
            f"Agent: {identity['agent_id']}\n"
            f"Description: {identity['description']}\n"
            f"Role: {identity['role']}\n"
            "============================================"
        )
        dma._sync_language_from_context(snapshot_raw)
        system_snapshot_block = format_system_snapshot(cast(SystemSnapshot, snapshot_raw))

        messages = dma.compose_messages(
            str(item.content),
            item.thought_id,
            task_context_block,
            identity_block,
            system_snapshot_block,
            user_profiles_block="",
            context_str=context_str,
            rules_summary_str=rules_summary_str,
            images=[],
        )
    _assert_matches_golden("dsdma", messages)


def test_aspdma_compose_seam_matches_golden() -> None:
    from ciris_engine.logic.dma.action_selection_pdma import ActionSelectionPDMAEvaluator

    with deterministic_prompt_environment():
        registry = Mock()
        registry.get_services_by_type.return_value = []
        dma = ActionSelectionPDMAEvaluator(service_registry=registry)
        pin_aspdma_context_builder(dma)

        messages = dma.compose_messages(make_enhanced_inputs(), "CIRISAgent")
    _assert_matches_golden("aspdma", messages)


def test_dsaspdma_compose_seam_matches_golden() -> None:
    from ciris_engine.logic.dma.dsaspdma import DSASPDMAEvaluator

    with deterministic_prompt_environment():
        dma = DSASPDMAEvaluator(service_registry=Mock())

        messages = dma.compose_messages(make_queue_item(), make_defer_aspdma_result(), context=None)
    _assert_matches_golden("dsaspdma", messages)
