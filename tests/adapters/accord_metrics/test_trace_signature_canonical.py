"""
Pin the canonical message format used for Ed25519 trace signing.

Lens verifies signatures by rebuilding the canonical JSON from the received
trace and comparing against the signature. If the agent's signed bytes differ
by even one character from what lens reconstructs, every trace is rejected
with BadSignatureError and nothing lands in the DB.

The shape is defined by CIRISLens/api/accord_api.py::verify_trace_signature:

    components_data = [strip_empty(c.model_dump()) for c in trace.components]
    signed_payload = {"components": components_data, "trace_level": trace_level}
    message = json.dumps(signed_payload, sort_keys=True, separators=(",", ":"))

These tests lock in the contract so future schema evolution can't silently
drift — if lens updates its verifier, these must be updated in lockstep.
"""

import hashlib
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from ciris_adapters.ciris_accord_metrics.services import (
    CompleteTrace,
    Ed25519TraceSigner,
    TraceComponent,
    _strip_empty,
)


def _build_expected_message(trace: CompleteTrace) -> bytes:
    """Reproduce lens's canonical-message construction byte-for-byte."""
    components_data = [
        _strip_empty(
            {
                "component_type": c.component_type,
                "data": c.data,
                "event_type": c.event_type,
                "timestamp": c.timestamp if isinstance(c.timestamp, str) else c.timestamp.isoformat(),
            }
        )
        for c in trace.components
    ]
    signed_payload = {
        "components": components_data,
        "trace_level": trace.trace_level,
    }
    return json.dumps(signed_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _make_signer_with_key():
    """Build a signer with a mocked unified key so signing succeeds."""
    signer = Ed25519TraceSigner()
    mock_key = MagicMock()
    mock_key.sign_base64 = MagicMock(return_value="mock-signature-b64")
    signer._unified_key = mock_key
    signer._key_id = "agent-test-key"
    return signer, mock_key


def _make_trace(level: str = "generic") -> CompleteTrace:
    ts = datetime(2026, 4, 23, 12, 0, 0, tzinfo=timezone.utc).isoformat()
    return CompleteTrace(
        trace_id="trace-test-1",
        thought_id="th-1",
        task_id="task-1",
        agent_id_hash="deadbeef",
        started_at=ts,
        completed_at=ts,
        trace_level=level,
        components=[
            TraceComponent(
                component_type="observation",
                event_type="THOUGHT_START",
                timestamp=ts,
                data={"k_eff": 0.9, "phase": "healthy", "empty_field": None, "empty_list": []},
            ),
            TraceComponent(
                component_type="action",
                event_type="ACTION_RESULT",
                timestamp=ts,
                data={"action": "speak", "rationale": "test"},
            ),
        ],
    )


def test_signed_payload_excludes_trace_schema_version():
    """trace_schema_version must NOT appear in the signed bytes.

    Lens's verify_trace_signature does NOT include it in the canonical
    payload. Including it on the agent side breaks every signature.
    """
    signer, mock_key = _make_signer_with_key()
    trace = _make_trace()

    assert signer.sign_trace(trace) is True

    # Capture what was signed
    signed_bytes = mock_key.sign_base64.call_args[0][0]
    payload = json.loads(signed_bytes.decode("utf-8"))

    assert "trace_schema_version" not in payload
    assert set(payload.keys()) == {"components", "trace_level"}


def test_signed_payload_matches_lens_canonical_format():
    """Exact byte-for-byte match against lens's reconstruction."""
    signer, mock_key = _make_signer_with_key()
    trace = _make_trace(level="detailed")

    assert signer.sign_trace(trace) is True

    actual_bytes = mock_key.sign_base64.call_args[0][0]
    expected_bytes = _build_expected_message(trace)

    assert actual_bytes == expected_bytes, (
        f"Canonical message drift!\n"
        f"  Actual   hash: {hashlib.sha256(actual_bytes).hexdigest()[:16]}\n"
        f"  Expected hash: {hashlib.sha256(expected_bytes).hexdigest()[:16]}\n"
        f"  Actual:   {actual_bytes[:300]!r}\n"
        f"  Expected: {expected_bytes[:300]!r}"
    )


def test_signed_payload_has_sorted_keys_and_compact_separators():
    """Lens uses sort_keys=True + separators=(',', ':'). Must match exactly."""
    signer, mock_key = _make_signer_with_key()
    trace = _make_trace()

    assert signer.sign_trace(trace) is True
    signed_bytes = mock_key.sign_base64.call_args[0][0]
    signed_str = signed_bytes.decode("utf-8")

    # Compact separators: no space after comma, no space after colon
    assert ", " not in signed_str
    assert ": " not in signed_str
    # Keys are alphabetically sorted at the top level
    assert signed_str.startswith('{"components":')


def test_strip_empty_applies_to_component_wrapper_not_just_data():
    """The whole component dict is strip_empty'd (matching lens), not just the
    inner `data` field. This catches the earlier bug where only data was
    stripped, producing a different byte sequence from what lens reconstructs.
    """
    signer, mock_key = _make_signer_with_key()
    ts = "2026-04-23T12:00:00+00:00"
    trace = CompleteTrace(
        trace_id="t",
        thought_id="th",
        task_id=None,
        agent_id_hash="abc",
        started_at=ts,
        trace_level="generic",
        components=[
            TraceComponent(
                component_type="observation",
                event_type="",  # empty — must be stripped
                timestamp=ts,
                data={"k_eff": 1.0},
            )
        ],
    )

    assert signer.sign_trace(trace) is True
    signed_bytes = mock_key.sign_base64.call_args[0][0]
    payload = json.loads(signed_bytes.decode("utf-8"))

    # Empty event_type got stripped — not present in the component dict
    assert "event_type" not in payload["components"][0]
    # Non-empty fields survive
    assert payload["components"][0]["component_type"] == "observation"


def test_sign_trace_and_verify_trace_roundtrip():
    """Agent's sign + verify pair must agree: what we sign, we can verify."""
    # Use a real Ed25519 key so sign/verify exercise the full crypto path.
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    import base64

    pub_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    pub_b64 = base64.urlsafe_b64encode(pub_bytes).decode("ascii").rstrip("=")

    class RealKey:
        def sign_base64(self, msg: bytes) -> str:
            sig = private_key.sign(msg)
            return base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")

    signer = Ed25519TraceSigner()
    signer._unified_key = RealKey()
    signer._key_id = "test-key"
    signer._root_pubkey = pub_b64

    trace = _make_trace()
    assert signer.sign_trace(trace) is True
    assert signer.verify_trace(trace) is True
