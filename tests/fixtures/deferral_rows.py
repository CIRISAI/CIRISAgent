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
        return self._sign("emit_deferral_request", "deferral:request:v1", args, deferral_id=args[0])

    def emit_deferral_response(self, request_id: str, approved: bool, bearer: Optional[str] = None) -> str:
        args = (request_id, approved, bearer)
        self.calls.append(("emit_deferral_response", args))
        request = self._row(request_id)
        if "emit_deferral_response" not in self.fail and (request is None or request.dimension != "deferral:request:v1"):
            raise ValueError(f"deferral.unknown_request: {request_id} is not an admitted deferral:request:v1")
        dim = "deferral:response:approved:v1" if approved else "deferral:response:rejected:v1"
        return self._sign("emit_deferral_response", dim, args, references_attestation_id=request_id)

    def emit_identity_amendment(self, amendment_digest: str, authorized_by: str, request_id: str) -> str:
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
            prior = [r for r in self.rows if r.envelope.get("authorized_by") == authorized_by]
            if prior:
                raise PermissionError(
                    f"deferral.response_already_used: {authorized_by} already authorised amendment "
                    f"{prior[0].attestation_id}"
                )
        return self._sign(
            "emit_identity_amendment",
            "identity_amendment:v1",
            args,
            amendment_digest=amendment_digest,
            authorized_by=authorized_by,
            evidence_refs=[authorized_by],
        )

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
        fn: Optional[Callable[..., object]] = getattr(self, name, None)
        return fn

    def calls_to(self, name: str) -> List[Tuple[object, ...]]:
        return [args for called, args in self.calls if called == name]

    def approved(self) -> Tuple[str, str]:
        """Seed an admitted request and its owner-signed approval; their ids."""
        request = self._sign("seed", "deferral:request:v1", ())
        response = self._sign("seed", "deferral:response:approved:v1", (), references_attestation_id=request)
        return request, response


def install_fake_node(monkeypatch: pytest.MonkeyPatch, node: Optional[FakeNode] = None) -> FakeNode:
    """Route the seam's server lookups to ``node`` (a fresh FakeNode by default)."""
    node = node or FakeNode()
    monkeypatch.setattr(deferral_rows, "_server_function", node.lookup)
    return node
