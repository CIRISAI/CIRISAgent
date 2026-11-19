"""identity_objection_of: the typed objection the Wise Authority is shown for an overridden identity write."""

from types import SimpleNamespace

from ciris_engine.logic.infrastructure.handlers.shared_helpers import identity_objection_of
from ciris_engine.schemas.runtime.veto_record import ObjectionType


def _veto(name: str, kind: ObjectionType, reason: str) -> SimpleNamespace:
    return SimpleNamespace(conscience=name, objection_type=kind, reason=reason, veto_id=f"v-{name}")


def test_no_result_or_not_overridden_is_no_objection() -> None:
    assert identity_objection_of(None) is None
    assert identity_objection_of(SimpleNamespace(overridden=False)) is None


def test_first_veto_in_priority_order_is_the_objection() -> None:
    first = _veto("coherence", ObjectionType.JUSTIFICATION, "unclear")
    second = _veto("entropy", ObjectionType.SUBSTANTIVE, "noisy")
    out = identity_objection_of(SimpleNamespace(overridden=True, vetoes=[first, second]))
    assert (out.conscience, out.objection_type, out.reason) == ("coherence", ObjectionType.JUSTIFICATION, "unclear")


def test_repeated_draft_reports_the_record_entry_it_repeats() -> None:
    entry = _veto("epistemic_humility", ObjectionType.EVIDENCE, "no authority seen")
    out = identity_objection_of(
        SimpleNamespace(overridden=True, vetoes=[], repeated_veto_id=entry.veto_id, veto_record=[entry])
    )
    assert out.conscience == "epistemic_humility" and out.objection_type == ObjectionType.EVIDENCE


def test_new_message_override_is_not_an_objection() -> None:
    assert identity_objection_of(SimpleNamespace(overridden=True, vetoes=[], updated_status_detected=True)) is None


def test_shard_that_could_not_judge_fails_closed_as_substantive() -> None:
    out = identity_objection_of(SimpleNamespace(overridden=True, vetoes=None, override_reason="timeout"))
    assert out.objection_type == ObjectionType.SUBSTANTIVE and out.reason == "timeout"
