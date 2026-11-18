"""The four consciences build their prompts with PromptAssembler (CIRISAgent#1366 Phase 3; FSD §6, §6a, §14).

Against the goldens captured from the unmigrated tree (conscience_golden.py):

- coherence and epistemic humility send the same bytes, except that whenever a trusted rule is in force they now
  lead with the verified governance block (the policy requires a verified rule segment at every judge);
- entropy and the optimization veto send the same bytes plus one withheld-context block: the request as a stub of
  closed-vocabulary properties, never a byte of it;
- every call carries a manifest with no guard violations, in fail-closed mode;
- a policy breach fails the conscience closed in QA and is stripped with an incident in production.
"""

import hashlib
import logging
import re
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from ciris_engine.logic.formatters.wa_approval import format_wa_governance_block
from ciris_engine.logic.prompt_assembly.assembler import STUB_BLOCK_CLOSE, STUB_BLOCK_OPEN
from ciris_engine.schemas.context.prompt_provenance import AssemblyMode, GuardViolationKind, SegmentForm
from tests.ciris_engine.logic.conscience.conscience_golden import (
    AMENDMENT,
    CONSCIENCES,
    FIXTURES,
    GRANT,
    USER_TEXT,
    capture,
    frozen,
    load_golden,
    _identity,
)

ABLATED = ("entropy", "optveto")
NON_ABLATED = ("coherence", "epistemic")
BLOCK = re.compile(r"\n?\n?" + re.escape(STUB_BLOCK_OPEN) + r"\n(WITHHELD [^\n]*\n?)+" + re.escape(STUB_BLOCK_CLOSE) + r"(\n\n)?")


def _mode(mode: AssemblyMode):
    return patch("ciris_engine.logic.prompt_assembly.assembler.current_guard_mode", return_value=mode)


async def _run(name: str, fixture: str, mode: AssemblyMode = AssemblyMode.FAIL_CLOSED) -> Dict[str, Any]:
    seen: Dict[str, Any] = {}
    with _mode(mode):
        messages, check = await capture(name, fixture, seen)
    seen["frozen"] = frozen(messages)
    seen["check"] = check
    return seen


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture", ["plain", "sender_record_image"])
@pytest.mark.parametrize("name", NON_ABLATED)
async def test_non_ablated_prompts_are_unchanged_without_trusted_rules(name: str, fixture: str) -> None:
    seen = await _run(name, fixture)
    assert seen["frozen"] == load_golden()[f"{name}/{fixture}"]
    assert seen["check"].passed


@pytest.mark.asyncio
@pytest.mark.parametrize("name", NON_ABLATED)
async def test_non_ablated_prompts_gain_only_the_governance_block_when_a_trusted_rule_is_in_force(name: str) -> None:
    seen = await _run(name, "governed")
    golden = load_golden()[f"{name}/governed"]
    block = format_wa_governance_block(GRANT, [AMENDMENT], language="en")
    expected = golden[:-1] + [{"role": "user", "content": block + "\n\n" + golden[-1]["content"]}]
    assert seen["frozen"] == expected
    # It now sees the governance it judges against, so its objection says so (#1366 item 7).
    assert seen["check"].held_trusted_rule is True


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture", list(FIXTURES))
@pytest.mark.parametrize("name", ABLATED)
async def test_ablated_prompts_gain_only_the_withheld_block(name: str, fixture: str) -> None:
    seen = await _run(name, fixture)
    golden = load_golden()[f"{name}/{fixture}"]
    got = seen["frozen"]
    assert got[:-1] == golden[:-1]  # accord, instruction, identity: unchanged
    user = got[-1]["content"]
    assert len(BLOCK.findall(user)) == 1
    assert "WITHHELD request — " in user
    assert BLOCK.sub(lambda m: "\n\n" if m.group(0).startswith("\n\n") and m.group(0).endswith("\n\n") else "", user) == golden[-1]["content"]
    sent = "".join(m.content for m in seen["messages"])
    assert USER_TEXT not in sent and "broken printer on floor three." in sent  # the draft, never the request
    assert seen["check"].passed


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture", list(FIXTURES))
@pytest.mark.parametrize("name", list(CONSCIENCES))
async def test_every_call_carries_a_clean_manifest(name: str, fixture: str) -> None:
    seen = await _run(name, fixture)
    manifest = seen["manifest"]
    assert manifest is not None and manifest.guard_violations == []
    assert manifest.stage.value == name
    kinds = {(r.kind.value, r.provenance.value if r.provenance else None, r.form.value) for r in manifest.segments}
    assert ("draft", None, "full") in kinds and ("accord", None, "full") in kinds
    request_form = "stub" if name in ABLATED else "full"
    assert ("request", None, request_form) in kinds
    if fixture == "governed":
        assert ("rule", "signed_guidance", "full") in kinds and ("rule", "amendment", "full") in kinds
        assert ("amendment", None, "full") in kinds
        assert ("sender_identity", None, "full") in kinds  # an ID-scoped rule is in force (S6)
    if name in ABLATED:
        assert not any(k[0] == "display_name" for k in kinds)
    elif fixture != "plain":
        assert ("display_name", None, "full") in kinds
    # Spans point at the bytes sent.
    for r in manifest.segments:
        content = seen["messages"][r.message_index].content
        assert hashlib.sha256(content[r.span_start : r.span_end].encode()).hexdigest() == r.sha256


# ------------------------------------------------------------------------------------------- the guard


def _unverified_identity() -> Dict[str, Any]:
    identity = _identity(AMENDMENT)
    identity["approved_amendments"].append(
        {**AMENDMENT.model_dump(), "node_id": "identity_amendment/x", "content": "Unverified text.", "verified": False}
    )
    return identity


@pytest.mark.asyncio
@pytest.mark.parametrize("name", NON_ABLATED)
async def test_an_unverified_amendment_fails_the_conscience_closed_in_qa(name: str) -> None:
    fields = dict(FIXTURES["governed"][0], agent_identity=_unverified_identity())
    with patch.dict(FIXTURES, {"unverified": (fields, None, True)}):
        seen = await _run(name, "unverified", AssemblyMode.FAIL_CLOSED)
    assert "messages" not in seen  # no LLM call
    check = seen["check"]
    assert not check.passed and check.check_ran is False
    assert "context policy violated" in (check.reason or "")


@pytest.mark.asyncio
@pytest.mark.parametrize("name", NON_ABLATED)
async def test_an_unverified_amendment_is_stripped_with_an_incident_in_production(name: str, caplog) -> None:
    fields = dict(FIXTURES["governed"][0], agent_identity=_unverified_identity())
    with patch.dict(FIXTURES, {"unverified": (fields, None, True)}), caplog.at_level(logging.ERROR):
        seen = await _run(name, "unverified", AssemblyMode.STRIP_AND_INCIDENT)
    sent = "".join(m.content for m in seen["messages"])
    assert "Unverified text." not in sent
    kinds = {v.kind for v in seen["manifest"].guard_violations}
    assert GuardViolationKind.TAINTED in kinds
    assert any("[CONTEXT-GUARD]" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ABLATED)
async def test_user_text_laundered_through_the_action_record_fails_closed_in_qa(name: str) -> None:
    """The measured leak (~33% of first passes): the request's bytes reaching entropy through the record."""
    leaky = f"Actions that ran in this task:\n- PONDER: You observed @eve say: {USER_TEXT}"
    with patch(
        "ciris_engine.logic.infrastructure.handlers.action_record.action_record_for_task", return_value=leaky
    ):
        seen = await _run(name, "plain", AssemblyMode.FAIL_CLOSED)
        assert "messages" not in seen and not seen["check"].passed
        seen = await _run(name, "plain", AssemblyMode.STRIP_AND_INCIDENT)
    sent = "".join(m.content for m in seen["messages"])
    assert USER_TEXT not in sent
    assert [v.kind for v in seen["manifest"].guard_violations] == [GuardViolationKind.UNTRUSTED_BYTES]
