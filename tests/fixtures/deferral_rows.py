"""A fake of the node's #1316 deferral-row functions (ciris_server 0.5.234+).

The installed wheel predates them, so tests install this in place of
``deferral_rows._server_function``. It keeps the rows it "signed" so a test can
check the chain, and raises the node's ``"<reason_id>: <text>"`` exceptions on
demand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import pytest

from ciris_engine.logic.services.governance.wise_authority import deferral_rows


@dataclass
class FakeRow:
    attestation_id: str
    attestation_type: str
    args: Tuple[object, ...]


@dataclass
class FakeNode:
    """Stands in for ciris_server.emit_deferral_request / _response / emit_identity_amendment."""

    rows: List[FakeRow] = field(default_factory=list)
    #: name -> exception to raise instead of signing.
    fail: Dict[str, BaseException] = field(default_factory=dict)
    #: names the "server" lacks (an old wheel).
    missing: Tuple[str, ...] = ()
    calls: List[Tuple[str, Tuple[object, ...]]] = field(default_factory=list)

    def _sign(self, name: str, dimension: str, args: Tuple[object, ...]) -> str:
        self.calls.append((name, args))
        if name in self.fail:
            raise self.fail[name]
        row_id = f"att-{len(self.rows) + 1}-{name}"
        self.rows.append(FakeRow(row_id, dimension, args))
        return row_id

    def emit_deferral_request(self, *args: object) -> str:
        return self._sign("emit_deferral_request", "deferral:request:v1", args)

    def emit_deferral_response(self, request_id: str, approved: bool, bearer: Optional[str] = None) -> str:
        if not any(r.attestation_id == request_id for r in self.rows) and "emit_deferral_response" not in self.fail:
            self.calls.append(("emit_deferral_response", (request_id, approved, bearer)))
            raise ValueError(f"deferral.unknown_request: {request_id} is not an admitted deferral:request:v1")
        dim = "deferral:response:approved:v1" if approved else "deferral:response:rejected:v1"
        return self._sign("emit_deferral_response", dim, (request_id, approved, bearer))

    def emit_identity_amendment(self, amendment_digest: str, authorized_by: str) -> str:
        return self._sign("emit_identity_amendment", "identity_amendment:v1", (amendment_digest, authorized_by))

    def lookup(self, name: str) -> Optional[Callable[..., object]]:
        if name in self.missing:
            return None
        fn: Optional[Callable[..., object]] = getattr(self, name, None)
        return fn

    def calls_to(self, name: str) -> List[Tuple[object, ...]]:
        return [args for called, args in self.calls if called == name]


def install_fake_node(monkeypatch: pytest.MonkeyPatch, node: Optional[FakeNode] = None) -> FakeNode:
    """Route the seam's server lookups to ``node`` (a fresh FakeNode by default)."""
    node = node or FakeNode()
    monkeypatch.setattr(deferral_rows, "_server_function", node.lookup)
    return node
