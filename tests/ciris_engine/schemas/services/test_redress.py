"""Post-action redress schema (NULLWORKS RC3 finding F6).

The finding: reconsidering *before* acting is not the same as correcting
consequences *after* an external SPEAK or TOOL has occurred. CIRIS had the
first (PONDER, recursive ASPDMA, DEFER) and nothing at all of the second.

These tests assert the four properties the corrective act has to have to be
redress rather than a gesture, plus the one property it must NOT have:

1. the original record is never touched — redress is additive;
2. authority is checked, not assumed — an unverified correction cannot govern;
3. linkage — a redress that cannot say what it corrects is unconstructible;
4. "what stands now?" has exactly one answer, and it distinguishes
   "nobody looked" from "someone looked and affirmed it";
5. **it does not claim to undo anything.** The strongest claim in the schema
   (an external artefact was actually removed) is unrepresentable without the
   receipt, and it is never implied by retraction.
"""

import pytest
from pydantic import ValidationError

from ciris_engine.schemas.services.authority_core import DeferralVerification
from ciris_engine.schemas.services.redress import (
    BINDING_DISPOSITIONS,
    ActionRef,
    ActionStanding,
    CompensatingAction,
    EffectReversibility,
    RedressAuthority,
    RedressAuthorityBasis,
    RedressDisposition,
    RedressGrounds,
    RedressRecord,
    RedressRefusalReason,
    admit_redress,
    redress_audit_event_data,
    redress_authorization_payload,
    resolve_effective_state,
)

WA_ID = "wa-2026-08-01-ABC123"

TARGET = ActionRef(
    audit_entry_id="ae-original",
    audit_entry_hash="c2VudGluZWw=",
    audit_sequence_number=41,
    task_id="task-1",
    thought_id="th-1",
    action_type="speak",
    channel_id="discord_123",
)


def verified_authority(**over: object) -> RedressAuthority:
    kwargs = dict(
        basis=RedressAuthorityBasis.WA_DEFERRAL_RESOLUTION,
        wa_id=WA_ID,
        authorizing_deferral_id="defer_task-1_1750000000.0",
        verification=DeferralVerification.VERIFIED,
    )
    kwargs.update(over)
    return RedressAuthority(**kwargs)  # type: ignore[arg-type]


def make_record(**over: object) -> RedressRecord:
    kwargs = dict(
        redress_id="rd-1",
        recorded_at="2026-08-20T10:00:00+00:00",
        target=TARGET,
        disposition=RedressDisposition.RETRACTED,
        grounds=RedressGrounds.FACTUAL_ERROR,
        statement="The figure quoted in that message was wrong.",
        authority=verified_authority(),
    )
    kwargs.update(over)
    return RedressRecord(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------- 5. not undo


class TestRedressIsNotUndo:
    """The claims the schema refuses to let you make for free."""

    def test_irreversible_is_the_default(self) -> None:
        """An author who says nothing about the effect has claimed nothing."""
        assert make_record().reversibility is EffectReversibility.IRREVERSIBLE
        assert make_record().external_effect_undone is False

    def test_retraction_does_not_imply_the_effect_was_undone(self) -> None:
        """Disavowing is something the agent does to its own endorsement.

        The message was still read. Conflating the two is the exact
        overstatement this axis exists to prevent.
        """
        record = make_record(disposition=RedressDisposition.RETRACTED)
        assert record.external_effect_undone is False
        state = resolve_effective_state(TARGET, [record])
        assert state.standing is ActionStanding.RETRACTED
        assert state.external_effect_undone is False

    def test_carrier_reversed_requires_the_receipt(self) -> None:
        with pytest.raises(ValidationError, match="carrier_evidence_ref"):
            make_record(reversibility=EffectReversibility.CARRIER_REVERSED)

    def test_carrier_reversed_with_receipt_is_representable(self) -> None:
        record = make_record(
            reversibility=EffectReversibility.CARRIER_REVERSED,
            carrier_evidence_ref="discord:message_delete:998877",
        )
        assert record.external_effect_undone is True

    def test_carrier_reversible_is_not_carrier_reversed(self) -> None:
        """"We could have deleted it" is not "we deleted it"."""
        record = make_record(reversibility=EffectReversibility.CARRIER_REVERSIBLE)
        assert record.external_effect_undone is False


# ---------------------------------------------------------------- 1. additive


class TestOriginalRecordIsPreserved:
    def test_record_is_frozen(self) -> None:
        record = make_record()
        with pytest.raises(ValidationError):
            record.disposition = RedressDisposition.UPHELD  # type: ignore[misc]

    def test_no_field_mutates_the_original(self) -> None:
        """The schema has no vocabulary for editing the original action.

        This is the structural half of "correction is additive": if there is no
        field that could name an edit, no caller can perform one by accident.
        """
        fields = set(RedressRecord.model_fields)
        for forbidden in ("replaces", "overwrite", "delete_original", "original_content", "edit"):
            assert forbidden not in fields

    def test_a_wrong_redress_is_corrected_by_another_redress(self) -> None:
        """There is no un-redress verb; the ledger only grows."""
        first = make_record(redress_id="rd-1", disposition=RedressDisposition.RETRACTED)
        second = make_record(
            redress_id="rd-2",
            recorded_at="2026-08-20T11:00:00+00:00",
            disposition=RedressDisposition.UPHELD,
            grounds=RedressGrounds.NEW_EVIDENCE,
            statement="On review the original figure was right; the retraction was mistaken.",
            amends="rd-1",
        )
        state = resolve_effective_state(TARGET, [first, second])
        assert state.standing is ActionStanding.UPHELD
        assert state.chain == ("rd-1", "rd-2"), "the mistaken retraction stays in the record"

    def test_a_redress_cannot_amend_itself(self) -> None:
        with pytest.raises(ValidationError, match="cannot amend itself"):
            make_record(amends="rd-1")


# ---------------------------------------------------------------- 2. authority


class TestAuthorityIsCheckedNotAssumed:
    def test_verified_wa_deferral_authority_is_admitted(self) -> None:
        assert admit_redress(make_record()).admitted is True

    def test_unsigned_authority_is_refused(self) -> None:
        """No redress row predates signing, so there is no legacy debt here.

        ``resolve_deferral`` tolerates UNSIGNED for rows written before #944.
        This ledger starts after it, so it starts strict.
        """
        verdict = admit_redress(make_record(authority=verified_authority(verification=DeferralVerification.UNSIGNED)))
        assert verdict.admitted is False
        assert verdict.refusal is RedressRefusalReason.AUTHORITY_UNVERIFIED

    def test_failed_signature_is_refused_and_named_distinctly(self) -> None:
        """A forgery and a migration gap must not be reported as each other."""
        verdict = admit_redress(make_record(authority=verified_authority(verification=DeferralVerification.FAILED)))
        assert verdict.admitted is False
        assert verdict.refusal is RedressRefusalReason.AUTHORITY_VERIFICATION_FAILED

    def test_wa_direct_is_refused_rather_than_silently_admitted(self) -> None:
        """Representable so the refusal has a name; not usable."""
        direct = RedressAuthority(basis=RedressAuthorityBasis.WA_DIRECT, wa_id=WA_ID)
        verdict = admit_redress(make_record(authority=direct))
        assert verdict.admitted is False
        assert verdict.refusal is RedressRefusalReason.AUTHORITY_BASIS_NOT_IMPLEMENTED

    def test_anonymous_redress_is_unconstructible(self) -> None:
        with pytest.raises(ValidationError, match="name the authority"):
            RedressAuthority(
                basis=RedressAuthorityBasis.WA_DEFERRAL_RESOLUTION,
                wa_id="   ",
                authorizing_deferral_id="defer_1",
            )

    def test_deferral_basis_must_name_its_deferral(self) -> None:
        with pytest.raises(ValidationError, match="must name the deferral"):
            RedressAuthority(basis=RedressAuthorityBasis.WA_DEFERRAL_RESOLUTION, wa_id=WA_ID)

    def test_direct_basis_must_not_borrow_a_deferral(self) -> None:
        with pytest.raises(ValidationError, match="does not rest on a deferral"):
            RedressAuthority(
                basis=RedressAuthorityBasis.WA_DIRECT,
                wa_id=WA_ID,
                authorizing_deferral_id="defer_1",
            )

    def test_refused_records_cannot_change_what_stands(self) -> None:
        """The load-bearing assertion of the whole module."""
        forged = make_record(authority=verified_authority(verification=DeferralVerification.FAILED))
        state = resolve_effective_state(TARGET, [forged])
        assert state.standing is ActionStanding.UNCHALLENGED
        assert state.governing_redress_id is None

    def test_refused_records_stay_visible(self) -> None:
        """Refusing is not deleting — a failed correction attempt is a fact."""
        forged = make_record(authority=verified_authority(verification=DeferralVerification.FAILED))
        state = resolve_effective_state(TARGET, [forged])
        assert len(state.refused) == 1
        assert state.refused[0].redress_id == "rd-1"
        assert state.refused[0].refusal is RedressRefusalReason.AUTHORITY_VERIFICATION_FAILED
        assert state.chain == ()

    def test_admission_is_not_the_callers_job(self) -> None:
        """resolve_effective_state admits internally, so it cannot be skipped."""
        good = make_record(redress_id="rd-good")
        bad = make_record(
            redress_id="rd-bad",
            recorded_at="2026-08-20T12:00:00+00:00",
            disposition=RedressDisposition.UPHELD,
            authority=verified_authority(verification=DeferralVerification.UNSIGNED),
        )
        state = resolve_effective_state(TARGET, [good, bad])
        assert state.standing is ActionStanding.RETRACTED, "the later unverified record must not win"


# ---------------------------------------------------------------- 3. linkage


class TestLinkage:
    def test_a_redress_must_say_what_it_corrects(self) -> None:
        with pytest.raises(ValidationError, match="must identify an action"):
            ActionRef(action_type="speak")

    def test_task_thought_pair_is_accepted_as_a_weaker_anchor(self) -> None:
        """Required, because the dispatcher discards the audit entry_id today.

        Rejecting un-anchored refs would make redress unusable for every action
        already taken. The reference is admissible and visibly weaker.
        """
        ref = ActionRef(task_id="task-1", thought_id="th-1", action_type="tool")
        assert ref.is_chain_anchored is False
        assert ref.identity_key == "tt:task-1:th-1"

    def test_chain_anchoring_is_visible(self) -> None:
        assert TARGET.is_chain_anchored is True
        assert TARGET.identity_key == "audit:ae-original"
        assert ActionRef(audit_entry_id="ae-x", task_id="t", thought_id="h").is_chain_anchored is False

    def test_hash_without_an_entry_id_references_nothing(self) -> None:
        with pytest.raises(ValidationError, match="does not reference anything"):
            ActionRef(task_id="task-1", thought_id="th-1", audit_entry_hash="deadbeef")

    def test_records_for_other_actions_are_ignored(self) -> None:
        other = ActionRef(audit_entry_id="ae-other", task_id="task-9", thought_id="th-9")
        elsewhere = make_record(redress_id="rd-elsewhere", target=other)
        assert resolve_effective_state(TARGET, [elsewhere]).standing is ActionStanding.UNCHALLENGED

    def test_superseded_must_name_what_replaced_it(self) -> None:
        """"Read the other thing instead" is useless without the other thing."""
        with pytest.raises(ValidationError, match="compensating_action"):
            make_record(disposition=RedressDisposition.SUPERSEDED)

    def test_compensating_action_is_an_ordinary_action(self) -> None:
        """It has its own ActionRef, so it is auditable and itself redressable.

        Redress grants no privileged execution path; the correction message is
        a normal SPEAK subject to the same checks as any other.
        """
        follow_up = CompensatingAction(
            action=ActionRef(audit_entry_id="ae-correction", task_id="task-1", thought_id="th-2", action_type="speak"),
            delivered=True,
        )
        record = make_record(disposition=RedressDisposition.SUPERSEDED, compensating_action=follow_up)
        state = resolve_effective_state(TARGET, [record])
        assert state.standing is ActionStanding.SUPERSEDED
        assert state.compensating_action is not None
        assert state.compensating_action.action.identity_key == "audit:ae-correction"

    def test_undelivered_correction_is_recorded_as_undelivered(self) -> None:
        """Absent or failed delivery is never rendered as silent success."""
        follow_up = CompensatingAction(
            action=ActionRef(task_id="task-1", thought_id="th-2", action_type="speak"),
            delivered=False,
            note="Channel was deleted before the correction could be posted.",
        )
        assert follow_up.delivered is False


# ---------------------------------------------- 4. current effective state


class TestCurrentEffectiveState:
    def test_no_records_means_unchallenged_not_upheld(self) -> None:
        """The distinction the whole ledger exists to preserve."""
        state = resolve_effective_state(TARGET, [])
        assert state.standing is ActionStanding.UNCHALLENGED
        assert state.reviewed is False
        assert state.endorsed is True

    def test_upheld_means_someone_actually_looked(self) -> None:
        state = resolve_effective_state(
            TARGET,
            [make_record(disposition=RedressDisposition.UPHELD, grounds=RedressGrounds.HARM_REPORTED)],
        )
        assert state.standing is ActionStanding.UPHELD
        assert state.reviewed is True
        assert state.endorsed is True

    def test_newest_binding_record_governs(self) -> None:
        early = make_record(redress_id="rd-1", recorded_at="2026-08-20T10:00:00+00:00")
        late = make_record(
            redress_id="rd-2",
            recorded_at="2026-08-20T10:05:00+00:00",
            disposition=RedressDisposition.WITHDRAWN,
        )
        state = resolve_effective_state(TARGET, [late, early])  # deliberately out of order
        assert state.governing_redress_id == "rd-2"
        assert state.standing is ActionStanding.WITHDRAWN

    def test_annotation_does_not_un_retract(self) -> None:
        """The bug a naive newest-wins rule would ship."""
        retraction = make_record(redress_id="rd-1", recorded_at="2026-08-20T10:00:00+00:00")
        note = make_record(
            redress_id="rd-2",
            recorded_at="2026-08-20T10:30:00+00:00",
            disposition=RedressDisposition.ANNOTATED,
            grounds=RedressGrounds.NEW_EVIDENCE,
            statement="Context: the source has since published a correction.",
        )
        state = resolve_effective_state(TARGET, [retraction, note])
        assert state.standing is ActionStanding.RETRACTED
        assert state.governing_redress_id == "rd-1"
        assert state.annotations == ("Context: the source has since published a correction.",)

    def test_annotations_alone_leave_the_action_standing_but_reviewed(self) -> None:
        note = make_record(
            disposition=RedressDisposition.ANNOTATED,
            grounds=RedressGrounds.NEW_EVIDENCE,
            statement="Accurate but incomplete.",
        )
        state = resolve_effective_state(TARGET, [note])
        assert state.standing is ActionStanding.UNCHALLENGED
        assert state.reviewed is True, "an annotation means somebody looked"
        assert state.chain == ("rd-1",)

    def test_withdrawn_is_not_endorsed_but_is_not_disavowed(self) -> None:
        state = resolve_effective_state(
            TARGET,
            [make_record(disposition=RedressDisposition.WITHDRAWN, grounds=RedressGrounds.CONSENT_WITHDRAWN)],
        )
        assert state.standing is ActionStanding.WITHDRAWN
        assert state.endorsed is False

    def test_ordering_is_deterministic_under_identical_timestamps(self) -> None:
        """Clock skew across occurrences is real; determinism is the floor."""
        a = make_record(redress_id="rd-a", disposition=RedressDisposition.UPHELD)
        b = make_record(redress_id="rd-b", disposition=RedressDisposition.WITHDRAWN)
        assert resolve_effective_state(TARGET, [a, b]).governing_redress_id == "rd-b"
        assert resolve_effective_state(TARGET, [b, a]).governing_redress_id == "rd-b"

    def test_state_is_recomputed_not_cached(self) -> None:
        """Adding a record changes the answer with no invalidation step."""
        first = make_record(redress_id="rd-1")
        state_one = resolve_effective_state(TARGET, [first])
        second = make_record(
            redress_id="rd-2",
            recorded_at="2026-08-20T13:00:00+00:00",
            disposition=RedressDisposition.UPHELD,
        )
        state_two = resolve_effective_state(TARGET, [first, second])
        assert state_one.standing is ActionStanding.RETRACTED
        assert state_two.standing is ActionStanding.UPHELD


# ---------------------------------------------------------------- vocabulary


class TestVocabulary:
    def test_binding_dispositions_exclude_annotation_only(self) -> None:
        assert BINDING_DISPOSITIONS == frozenset(set(RedressDisposition) - {RedressDisposition.ANNOTATED})

    def test_every_binding_disposition_resolves_to_a_standing(self) -> None:
        """No disposition can be added without deciding what it means."""
        replacement = CompensatingAction(
            action=ActionRef(audit_entry_id="ae-correction", task_id="task-1", thought_id="th-2"),
        )
        for disposition in BINDING_DISPOSITIONS:
            # SUPERSEDED is the one disposition that cannot stand alone.
            extra = {"compensating_action": replacement} if disposition is RedressDisposition.SUPERSEDED else {}
            state = resolve_effective_state(TARGET, [make_record(disposition=disposition, **extra)])
            assert state.standing.value == disposition.value

    def test_retraction_family_maps_to_the_ceg_primitives(self) -> None:
        assert RedressDisposition.RETRACTED.ceg_primitive == "recants"
        assert RedressDisposition.WITHDRAWN.ceg_primitive == "withdraws"
        assert RedressDisposition.SUPERSEDED.ceg_primitive == "supersedes"

    def test_non_retraction_dispositions_claim_no_ceg_analogue(self) -> None:
        """Forcing a nearest fit would make a future federation emission lie."""
        assert RedressDisposition.UPHELD.ceg_primitive is None
        assert RedressDisposition.ANNOTATED.ceg_primitive is None

    def test_quorum_compromise_is_not_a_ground(self) -> None:
        """Upstream ground with no meaning for one agent's own external act."""
        assert "quorum_compromise" not in {g.value for g in RedressGrounds}

    def test_a_redress_must_be_legible_in_words(self) -> None:
        with pytest.raises(ValidationError):
            make_record(statement="  ")


# ---------------------------------------------------------------- recording


class TestRecordingShape:
    def test_audit_event_data_reuses_the_existing_audit_schema(self) -> None:
        """No new storage shape, and no new table — the append-only chain."""
        event = redress_audit_event_data(make_record())
        assert event.action == "redress_retracted"
        assert event.entity_id == "audit:ae-original"
        assert event.resource == "ae-original"
        assert event.reason == "factual_error"
        assert event.actor == WA_ID

    def test_audit_metadata_values_are_all_scalars(self) -> None:
        """AuditEventData.metadata is Dict[str, Union[str,int,float,bool]]."""
        event = redress_audit_event_data(
            make_record(
                reversibility=EffectReversibility.CARRIER_REVERSED,
                carrier_evidence_ref="discord:message_delete:998877",
            )
        )
        assert all(isinstance(v, (str, int, float, bool)) for v in event.metadata.values())
        assert event.metadata["carrier_evidence_ref"] == "discord:message_delete:998877"
        assert event.metadata["external_effect_undone"] is True

    def test_absent_fields_are_omitted_not_stringified(self) -> None:
        """A reader must be able to tell absent from empty."""
        event = redress_audit_event_data(make_record())
        assert "carrier_evidence_ref" not in event.metadata
        assert "amends" not in event.metadata
        assert "compensating_action_key" not in event.metadata

    def test_recorded_admission_travels_with_the_record(self) -> None:
        """A refused redress that is nevertheless written down says so."""
        event = redress_audit_event_data(
            make_record(authority=verified_authority(verification=DeferralVerification.FAILED))
        )
        assert event.metadata["admitted"] is False
        assert event.metadata["authority_verification"] == "failed"

    def test_authorization_payload_commits_to_the_corrective_decision(self) -> None:
        """One shared builder, so a signer and a verifier cannot drift apart."""
        payload = redress_authorization_payload(make_record(), "2026-08-20T10:00:00+00:00")
        assert set(payload) == {
            "redress_id",
            "target_key",
            "target_entry_hash",
            "disposition",
            "grounds",
            "statement",
            "wa_id",
            "signed_at",
        }

    def test_authorization_payload_cannot_be_lifted_onto_another_target(self) -> None:
        other = ActionRef(audit_entry_id="ae-other", audit_entry_hash="b3RoZXI=", task_id="t9", thought_id="h9")
        a = redress_authorization_payload(make_record(), "2026-08-20T10:00:00+00:00")
        b = redress_authorization_payload(make_record(target=other), "2026-08-20T10:00:00+00:00")
        assert a["target_key"] != b["target_key"]
        assert a["target_entry_hash"] != b["target_entry_hash"]

    def test_authorization_payload_cannot_be_replayed_onto_another_moment(self) -> None:
        record = make_record()
        assert redress_authorization_payload(record, "2026-08-20T10:00:00+00:00") != redress_authorization_payload(
            record, "2026-08-20T11:00:00+00:00"
        )
