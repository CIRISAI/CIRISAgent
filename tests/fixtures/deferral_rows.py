"""A fake of the node's #1316 deferral-row functions (ciris_server 0.5.234, CIRISServer#815 contract).

The installed wheel predates them, so tests install this in place of
``deferral_rows._server_function``. It keeps the rows it "signed", in the
node's grammar (``attestation_type`` = ``scores``, the row's identity in the
envelope's ``dimension``), enforces the amendment's binding to its deferral and
the one-approval-one-amendment rule, and raises the node's
``"<reason_id>: <text>"`` exceptions on demand.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import pytest

from ciris_engine.logic.services.governance.wise_authority import deferral_rows

AGENT = "agent-identity"
OCCURRENCE = "agent-occurrence"
OWNER = "owner-fedid"
ROOM = "chat:pair:v1:" + "ab" * 32


@dataclass
class FakeRow:
    attestation_id: str
    dimension: str
    args: Tuple[object, ...] = ()
    envelope: Dict[str, object] = field(default_factory=dict)
    attesting_key_id: str = OCCURRENCE

    @property
    def attestation_type(self) -> str:
        return self.dimension  # tests name rows by their dimension; the stored verb is `scores`

    def stored(self) -> Dict[str, object]:
        return {
            "attestation_id": self.attestation_id,
            "attestation_type": "scores",
            "weight": 1.0,
            "attesting_key_id": self.attesting_key_id,
            "attested_key_id": AGENT,
            "asserted_at": "2026-10-22T12:00:00Z",
            "attestation_envelope": {"dimension": self.dimension, ROOM_FIELD: ROOM, **self.envelope},
        }


ROOM_FIELD = "community_key_id"


@dataclass
class FakeNode:
    """Stands in for ciris_server.emit_deferral_request / _response / emit_identity_amendment / deferral_rows."""

    rows: List[FakeRow] = field(default_factory=list)
    #: name -> exception to raise instead of signing.
    fail: Dict[str, BaseException] = field(default_factory=dict)
    #: names the "server" lacks (an old wheel).
    missing: Tuple[str, ...] = ()
    calls: List[Tuple[str, Tuple[object, ...]]] = field(default_factory=list)
    #: ciris-server 0.5.250 exact-bytes approval: the response row signs an
    #: ``amendment_digest`` and the amendment row must match it. False = an older node.
    exact_bytes: bool = True
    #: rc21 profile chain (persist v62 / verify 23): ``emit_identity_amendment`` takes ``prev`` and writes
    #: ``refs.prev``. False = an older node whose function has no ``prev``.
    chain: bool = True

    def _row(self, row_id: str) -> Optional[FakeRow]:
        return next((r for r in self.rows if r.attestation_id == row_id), None)

    def _sign(self, name: str, dimension: str, args: Tuple[object, ...], **envelope: object) -> str:
        if name in self.fail:
            raise self.fail[name]
        row_id = f"att-{len(self.rows) + 1}-{name}"
        signer = OWNER if name == "emit_deferral_response" else OCCURRENCE
        self.rows.append(FakeRow(row_id, dimension, args, dict(envelope), signer))
        return row_id

    def emit_deferral_request(self, *args: object) -> str:
        self.calls.append(("emit_deferral_request", args))
        # 0.5.250's deferral:request:v1 refuses an empty thought_id (RATCHET run 44748258728: a base link that
        # sent "" was never signed, so its WA answer had nothing to answer and no profile could be anchored).
        if len(args) > 2 and not args[2]:
            raise ValueError("deferral.bad_input: invalid: bad input: thought_id is empty")
        return self._sign("emit_deferral_request", "deferral:request:v1", args, deferral_id=args[0])

    def emit_deferral_response(
        self, request_id: str, approved: bool, bearer: Optional[str] = None, amendment_digest: Optional[str] = None
    ) -> str:
        """0.5.250: ``amendment_digest`` is signed INSIDE the approved response row."""
        args = (request_id, approved, bearer, amendment_digest)
        self.calls.append(("emit_deferral_response", args))
        request = self._row(request_id)
        if "emit_deferral_response" not in self.fail and (request is None or request.dimension != "deferral:request:v1"):
            raise ValueError(f"deferral.unknown_request: {request_id} is not an admitted deferral:request:v1")
        if amendment_digest is not None and not approved:
            raise ValueError("deferral.digest_on_rejection: a rejection approves no amendment text")
        dim = "deferral:response:approved:v1" if approved else "deferral:response:rejected:v1"
        extra: Dict[str, object] = {"amendment_digest": amendment_digest} if amendment_digest else {}
        return self._sign("emit_deferral_response", dim, args, references_attestation_id=request_id, **extra)

    def emit_deferral_response_legacy(self, request_id: str, approved: bool, bearer: Optional[str] = None) -> str:
        """< 0.5.250: no amendment digest."""
        return self.emit_deferral_response(request_id, approved, bearer)

    def emit_identity_amendment(
        self, amendment_digest: str, authorized_by: str, request_id: str, prev: Optional[str] = None
    ) -> str:
        """``prev`` is written as the row's ``refs.prev``; the base link passes None explicitly."""
        args = (amendment_digest, authorized_by, request_id)
        self.calls.append(("emit_identity_amendment", args))
        if "emit_identity_amendment" not in self.fail:
            response = self._row(authorized_by)
            if response is None or response.dimension != "deferral:response:approved:v1":
                raise PermissionError(f"identity_amendment_unauthorized: {authorized_by} is not an approval")
            if response.envelope.get("references_attestation_id") != request_id:
                raise PermissionError(
                    f"identity_amendment_unauthorized: {authorized_by} answers "
                    f"{response.envelope.get('references_attestation_id')!r}, not the deferral {request_id}"
                )
            if self.exact_bytes and response.envelope.get("amendment_digest") != amendment_digest:
                raise PermissionError(
                    f"amendment_digest_mismatch: {authorized_by} approves "
                    f"{response.envelope.get('amendment_digest')!r}, not {amendment_digest}"
                )
            prior = [r for r in self.rows if r.envelope.get("authorized_by") == authorized_by]
            if prior:
                raise PermissionError(
                    f"deferral.response_already_used: {authorized_by} already authorised amendment "
                    f"{prior[0].attestation_id}"
                )
        refs: Dict[str, object] = {"refs": {"prev": prev}} if prev else {}
        return self._sign(
            "emit_identity_amendment",
            "identity_amendment:v1",
            args,
            amendment_digest=amendment_digest,
            authorized_by=authorized_by,
            evidence_refs=[authorized_by],
            **refs,
        )

    def emit_identity_amendment_legacy(self, amendment_digest: str, authorized_by: str, request_id: str) -> str:
        """Before the rc21 chain: no ``prev``."""
        return self.emit_identity_amendment(amendment_digest, authorized_by, request_id)

    def deferral_rows(self, ids: List[str]) -> str:
        self.calls.append(("deferral_rows", (list(ids),)))
        if "deferral_rows" in self.fail:
            raise self.fail["deferral_rows"]
        out = []
        for row_id in ids:
            row = self._row(row_id)
            out.append(row.stored() if row is not None else None)
        return json.dumps(out)

    def lookup(self, name: str) -> Optional[Callable[..., object]]:
        if name in self.missing:
            return None
        if name == "emit_deferral_response" and not self.exact_bytes:
            return self.emit_deferral_response_legacy
        if name == "emit_identity_amendment" and not self.chain:
            return self.emit_identity_amendment_legacy
        fn: Optional[Callable[..., object]] = getattr(self, name, None)
        return fn

    def calls_to(self, name: str) -> List[Tuple[object, ...]]:
        return [args for called, args in self.calls if called == name]

    def approved(self, amendment_text: Optional[str] = None) -> Tuple[str, str]:
        """Seed an admitted request and its owner-signed approval; their ids.

        With ``amendment_text`` the approval signs that exact text's digest (0.5.250).
        """
        import hashlib

        request = self._sign("seed", "deferral:request:v1", ())
        extra: Dict[str, object] = (
            {"amendment_digest": hashlib.sha256(amendment_text.encode("utf-8")).hexdigest()} if amendment_text else {}
        )
        response = self._sign(
            "seed", "deferral:response:approved:v1", (), references_attestation_id=request, **extra
        )
        return request, response


def install_fake_node(monkeypatch: pytest.MonkeyPatch, node: Optional[FakeNode] = None) -> FakeNode:
    """Route the seam's server lookups to ``node`` (a fresh FakeNode by default)."""
    node = node or FakeNode()
    monkeypatch.setattr(deferral_rows, "_server_function", node.lookup)
    return node
