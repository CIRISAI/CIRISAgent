"""The seam to the node's #1316 deferral-row functions: typed refusals, off-loop calls, old servers."""

from __future__ import annotations

import hashlib
import sys
import time
import types

import pytest

from ciris_engine.logic.runtime import node_fold
from ciris_engine.logic.services.governance.wise_authority import deferral_rows
from ciris_engine.logic.services.governance.wise_authority.deferral_rows import (
    DeferralRowRefused,
    DeferralRowsUnavailable,
    emit_deferral_request,
    emit_deferral_response,
    emit_identity_amendment,
    parse_refusal,
    rows_available,
)
from ciris_engine.schemas.services.authority.deferral_rows import DeferralRowRefusalKind


def _fold_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(node_fold, "fold_status", lambda: {"folded": True, "reachable": True})


def _server(monkeypatch: pytest.MonkeyPatch, **functions: object) -> types.ModuleType:
    module = types.ModuleType("ciris_server")
    for name, fn in functions.items():
        setattr(module, name, fn)
    monkeypatch.setitem(sys.modules, "ciris_server", module)
    return module


# ---------------------------------------------------------------- the refusal


@pytest.mark.parametrize(
    ("exc", "reason_id", "kind"),
    [
        (ValueError("deferral.bad_input: bad input: reason_digest must be hex"), "deferral.bad_input", "invalid"),
        (ValueError("deferral.unknown_request: att-9 is not admitted"), "deferral.unknown_request", "invalid"),
        (PermissionError("deferral.resolver_has_no_key: signed in, but"), "deferral.resolver_has_no_key", "refused"),
        (PermissionError("identity_amendment_unauthorized: not approved"), "identity_amendment_unauthorized", "refused"),
        (RuntimeError("deferral.store: store: disk full"), "deferral.store", "outage"),
    ],
)
def test_the_nodes_refusal_parses_into_reason_and_kind(exc: BaseException, reason_id: str, kind: str) -> None:
    refusal = parse_refusal(exc)
    assert refusal.reason_id == reason_id
    assert refusal.kind.value == kind
    assert refusal.text and not refusal.text.startswith(":")


def test_a_message_without_a_reason_keeps_its_text_and_its_kind() -> None:
    refusal = parse_refusal(RuntimeError("No in-process persist Engine!"))
    assert refusal.reason_id == "unparsed"
    assert refusal.kind is DeferralRowRefusalKind.OUTAGE
    assert "persist Engine" in refusal.text


# ---------------------------------------------------- rows unavailable, never faked


@pytest.mark.asyncio
async def test_no_node_in_this_process_means_rows_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(node_fold, "fold_status", lambda: None)
    called = []
    _server(monkeypatch, emit_deferral_request=lambda *a: called.append(a) or "att-x")
    assert rows_available() is False
    with pytest.raises(DeferralRowsUnavailable):
        await emit_deferral_request("d", "t", "th", "reason")
    assert not called, "fold off: the node is not asked"


@pytest.mark.asyncio
async def test_a_server_older_than_0_5_234_means_rows_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _fold_on(monkeypatch)
    _server(monkeypatch, resolve_bearer=lambda token: None)  # 0.5.233: none of the three functions
    assert rows_available() is False
    with pytest.raises(DeferralRowsUnavailable):
        await emit_deferral_request("d", "t", "th", "reason")
    with pytest.raises(DeferralRowsUnavailable):
        await emit_deferral_response("att-1", True, "sess:x")
    with pytest.raises(DeferralRowsUnavailable):
        await emit_identity_amendment("text", "att-2", "att-1")


@pytest.mark.asyncio
async def test_rows_are_unavailable_unless_all_three_functions_exist(monkeypatch: pytest.MonkeyPatch) -> None:
    _fold_on(monkeypatch)
    _server(monkeypatch, emit_deferral_request=lambda *a: "att-1")
    assert rows_available() is False


# ------------------------------------------------------------------ the calls


@pytest.mark.asyncio
async def test_each_call_reaches_the_node_with_the_contract_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    _fold_on(monkeypatch)
    seen: dict = {}

    def request(*args: object) -> str:
        seen["request"] = args
        return "att-req"

    def response(*args: object) -> str:
        seen["response"] = args
        return "att-resp"

    def amendment(*args: object) -> str:
        seen["amendment"] = args
        return "att-amend"

    _server(
        monkeypatch,
        emit_deferral_request=request,
        emit_deferral_response=response,
        emit_identity_amendment=amendment,
    )
    assert rows_available() is True

    assert await emit_deferral_request("defer_t_1", "t", "th", "the reason", domain_hint="ethics") == "att-req"
    digest = hashlib.sha256(b"the reason").hexdigest()
    assert seen["request"] == ("defer_t_1", "t", "th", digest, "ethics", None)
    assert len(digest) == 64 and digest == digest.lower()

    assert await emit_deferral_response("att-req", False, "sess:wa-1:mac") == "att-resp"
    assert seen["response"] == ("att-req", False, "sess:wa-1:mac")

    assert await emit_identity_amendment("I mentor", "att-resp", "att-req") == "att-amend"
    assert seen["amendment"] == (hashlib.sha256(b"I mentor").hexdigest(), "att-resp", "att-req"), (
        "the request id binds the amendment to its own deferral"
    )


@pytest.mark.asyncio
async def test_the_call_runs_off_the_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    import threading

    _fold_on(monkeypatch)
    loop_thread = threading.get_ident()
    threads = []
    _server(monkeypatch, emit_deferral_request=lambda *a: threads.append(threading.get_ident()) or "att-1")
    await emit_deferral_request("d", "t", "th", "r")
    assert threads and threads[0] != loop_thread


@pytest.mark.asyncio
async def test_a_refusal_raises_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    _fold_on(monkeypatch)

    def refuse(*args: object) -> str:
        raise PermissionError("deferral.delegated: a delegated session cannot answer a deferral")

    _server(monkeypatch, emit_deferral_response=refuse)
    with pytest.raises(DeferralRowRefused) as caught:
        await emit_deferral_response("att-1", True, "sess:x")
    assert caught.value.refusal.reason_id == "deferral.delegated"
    assert caught.value.refusal.kind is DeferralRowRefusalKind.REFUSED


@pytest.mark.asyncio
async def test_a_node_that_does_not_answer_is_an_outage(monkeypatch: pytest.MonkeyPatch) -> None:
    _fold_on(monkeypatch)
    monkeypatch.setattr(deferral_rows, "DEFERRAL_ROW_CALL_TIMEOUT_SECONDS", 0.05)
    _server(monkeypatch, emit_deferral_request=lambda *a: time.sleep(0.5) or "att-late")
    with pytest.raises(DeferralRowRefused) as caught:
        await emit_deferral_request("d", "t", "th", "r")
    assert caught.value.refusal.kind is DeferralRowRefusalKind.OUTAGE
    assert caught.value.refusal.reason_id == "deferral.timeout"


@pytest.mark.asyncio
async def test_an_answer_that_is_not_an_id_is_never_taken_as_a_row(monkeypatch: pytest.MonkeyPatch) -> None:
    _fold_on(monkeypatch)
    _server(monkeypatch, emit_deferral_request=lambda *a: None)
    with pytest.raises(DeferralRowRefused) as caught:
        await emit_deferral_request("d", "t", "th", "r")
    assert caught.value.refusal.kind is DeferralRowRefusalKind.OUTAGE


def test_the_room_is_left_to_the_node() -> None:
    """No agent<->user room yet (#1300): None, and the node derives the agent<->owner pair room."""
    assert deferral_rows.deferral_room_id() is None


# ---------------------------------------------------------------- read back


def _stored(row_id: str, dimension: str, **envelope: object) -> dict:
    return {
        "attestation_id": row_id,
        "attestation_type": "scores",
        "weight": 1.0,
        "attesting_key_id": "agent-occ",
        "attested_key_id": "agent-id",
        "asserted_at": "2026-10-22T12:00:00Z",
        "attestation_envelope": {"dimension": dimension, **envelope},
    }


@pytest.mark.asyncio
async def test_rows_read_back_one_entry_per_id_nulls_included(monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    _fold_on(monkeypatch)
    store = {
        "att-3": _stored(
            "att-3",
            "identity_amendment:v1",
            amendment_digest="a" * 64,
            authorized_by="att-2",
            evidence_refs=["att-2"],
            community_key_id="chat:pair:v1:abc",
        ),
        "att-2": _stored("att-2", "deferral:response:approved:v1", references_attestation_id="att-1"),
    }
    asked = []

    def deferral_rows_fn(ids: list) -> str:
        asked.append(list(ids))
        return json.dumps([store.get(i) for i in ids])

    _server(monkeypatch, deferral_rows=deferral_rows_fn)

    rows = await deferral_rows.read_deferral_rows(["att-3", "att-missing", "att-2"])

    assert asked == [["att-3", "att-missing", "att-2"]], "one call for all ids"
    amend, missing, resp = rows
    assert missing is None, "a null entry stays None"
    assert amend is not None and amend.dimension == "identity_amendment:v1" and amend.attestation_type == "scores"
    assert amend.authorized_by == "att-2" and amend.evidence_refs == ["att-2"]
    assert amend.room_id == "chat:pair:v1:abc"
    assert resp is not None and resp.dimension == "deferral:response:approved:v1"
    assert resp.references_attestation_id == "att-1"
    assert await deferral_rows.read_deferral_row("att-missing") is None


@pytest.mark.asyncio
async def test_a_row_is_identified_by_its_dimension_never_its_verb(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every row is `scores`; a scores row under another dimension is not a deferral row."""
    import json

    _fold_on(monkeypatch)
    consent = _stored("att-c", "consent:community_trust:v1")
    verb_only = dict(_stored("att-v", "deferral:request:v1"), attestation_type="deferral:request:v1")
    verb_only["attestation_envelope"] = {}  # the old grammar: no dimension in the envelope
    _server(monkeypatch, deferral_rows=lambda ids: json.dumps([consent, verb_only]))
    assert await deferral_rows.read_deferral_rows(["att-c", "att-v"]) == [None, None]


@pytest.mark.asyncio
async def test_a_server_without_deferral_rows_cannot_read_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _fold_on(monkeypatch)
    _server(monkeypatch, emit_deferral_request=lambda *a: "att-1")
    with pytest.raises(DeferralRowsUnavailable):
        await deferral_rows.read_deferral_row("att-1")


@pytest.mark.asyncio
async def test_a_read_back_of_the_wrong_shape_is_an_outage(monkeypatch: pytest.MonkeyPatch) -> None:
    _fold_on(monkeypatch)
    _server(monkeypatch, deferral_rows=lambda ids: "[]")
    with pytest.raises(DeferralRowRefused) as caught:
        await deferral_rows.read_deferral_rows(["att-1"])
    assert caught.value.refusal.kind is DeferralRowRefusalKind.OUTAGE
