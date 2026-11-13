"""
ASPDMA's instructions for the memory verbs say WHEN to pick them, not how to fill them.

This file used to assert that the ASPDMA prompt carried the flat memory fields
(``memorize_node_type``, ``recall_query``, ``forget_node_id``) and the Discord
numeric-id hint for FORGET. Those parameters are now settled by each verb's
second pass, which has the graph's addressing conventions and the nodes that
already exist (#1027) — so what is asserted here is that ASPDMA no longer asks
for them, and that the id guidance lives where the id is chosen.
"""

from pathlib import Path

import pytest
import yaml

from ciris_engine.logic.dma.action_selection.action_instruction_generator import (
    ActionInstructionGenerator,
)
from ciris_engine.schemas.dma.results import ASPDMALLMResult
from ciris_engine.schemas.runtime.enums import HandlerActionType

PROMPTS = Path(__file__).resolve().parents[4] / "ciris_engine" / "logic" / "dma" / "prompts"

DROPPED_FIELDS = (
    "memorize_node_type",
    "memorize_content",
    "recall_query",
    "recall_node_type",
    "recall_scope",
    "recall_limit",
    "forget_node_id",
    "forget_reason",
    "defer_reason",
    "defer_until",
)


class TestMemoryVerbInstructions:
    @pytest.fixture
    def generator(self):
        return ActionInstructionGenerator()

    def test_memorize_keeps_only_its_scope(self, generator):
        schema = generator._generate_schema_for_action(HandlerActionType.MEMORIZE)

        assert schema.startswith("MEMORIZE: memorize_scope (string: local|identity|environment|community)")
        assert "follow-up step" in schema

    @pytest.mark.parametrize("verb", [HandlerActionType.RECALL, HandlerActionType.FORGET])
    def test_recall_and_forget_carry_no_fields(self, generator, verb):
        schema = generator._generate_schema_for_action(verb)

        assert schema.startswith(f"{verb.value.upper()}: no additional fields.")
        assert "follow-up step" in schema

    def test_generated_instructions_ask_for_no_dropped_field(self, generator):
        instructions = generator.generate_action_instructions(
            [
                HandlerActionType.MEMORIZE,
                HandlerActionType.RECALL,
                HandlerActionType.FORGET,
                HandlerActionType.DEFER,
            ]
        )

        for verb in ("MEMORIZE:", "RECALL:", "FORGET:", "DEFER:"):
            assert verb in instructions
        for field in DROPPED_FIELDS:
            assert field not in instructions, f"ASPDMA is still told about {field}"

    def test_the_result_schema_has_no_dropped_field(self):
        for field in DROPPED_FIELDS:
            assert field not in ASPDMALLMResult.model_fields, f"{field} is back on ASPDMALLMResult"

    @pytest.mark.parametrize(
        "path",
        [
            PROMPTS / "action_selection_pdma.yml",
            *sorted(PROMPTS.glob("localized/*/action_selection_pdma.yml")),
        ],
    )
    def test_no_aspdma_template_names_a_dropped_field(self, path):
        """Every locale: a template that still lists a dropped field asks for output nothing reads."""
        text = path.read_text(encoding="utf-8")
        for field in DROPPED_FIELDS:
            assert field not in text, f"{path.parent.name}/{path.name} still names {field}"

    def test_the_addressing_guidance_lives_in_the_second_passes(self):
        """`user/{user_id}` is taught where the node is chosen, for all three memory verbs."""
        memorize = yaml.safe_load((PROMPTS / "msaspdma.yml").read_text(encoding="utf-8"))
        assert "user/{user_id}" in memorize["addressing_convention"]
        for name in ("rsaspdma", "fsaspdma"):
            guide = yaml.safe_load((PROMPTS / f"{name}.yml").read_text(encoding="utf-8"))
            assert "CANDIDATE NODES" in guide["evaluation_steps"]
            assert "Do not invent a node id" in guide["memory_prohibitions"]
