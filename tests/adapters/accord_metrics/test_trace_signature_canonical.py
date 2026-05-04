"""
Pin the canonical message format used for Ed25519 trace signing.

The 9-field canonical per FSD/TRACE_WIRE_FORMAT.md §8 (post-2.7.8.9 / #710):

    canonical = {
      "trace_id":             trace.trace_id,
      "thought_id":           trace.thought_id,
      "task_id":              trace.task_id,
      "agent_id_hash":        trace.agent_id_hash,
      "started_at":           trace.started_at.isoformat(),
      "completed_at":         trace.completed_at.isoformat(),
      "trace_level":          trace.trace_level,
      "trace_schema_version": trace.trace_schema_version,
      "components":           [strip_empty({component_type,data,event_type,timestamp}), ...]
    }
    message = json.dumps(canonical, sort_keys=True, separators=(",", ":"))

Migration from the legacy 2-field (`{"components", "trace_level"}`) was gated
on persist v0.1.15 shipping its `try-both` fallback verifier. Once persist
accepts both shapes, the agent flips to the 9-field spec; once the agent
fleet has flipped, persist drops the 2-field path on a future minor.

These tests lock the canonical bytes shape — any drift (key set, key order,
value formatting, separators) breaks signature verification on every trace
and gets caught at CI time rather than in production.
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
    """Reproduce the 2.7.9 canonical (FSD/TRACE_WIRE_FORMAT.md §8) byte-for-byte.

    Per-component shape carries 5 fields: agent_id_hash (denormalized from
    envelope, MUST equal trace.agent_id_hash), component_type, data,
    event_type, timestamp. The outer canonical at 2.7.9 carries 10 keys
    when `deployment_profile` (§3.2) is present — the cohort-taxonomy
    block is part of the signed canonical so the 6 cohort labels are
    non-forgeable post-emission. Absent at 2.7.0; present at 2.7.9.
    """
    components_data = [
        _strip_empty(
            {
                "agent_id_hash": c.agent_id_hash or trace.agent_id_hash,
                "component_type": c.component_type,
                "data": c.data,
                "event_type": c.event_type,
                "timestamp": c.timestamp if isinstance(c.timestamp, str) else c.timestamp.isoformat(),
            }
        )
        for c in trace.components
    ]
    canonical: dict = {
        "trace_id": trace.trace_id,
        "thought_id": trace.thought_id,
        "task_id": trace.task_id,
        "agent_id_hash": trace.agent_id_hash,
        "started_at": trace.started_at if isinstance(trace.started_at, str) else trace.started_at.isoformat(),
        "completed_at": trace.completed_at if isinstance(trace.completed_at, str) else trace.completed_at.isoformat(),
        "trace_level": trace.trace_level,
        "trace_schema_version": trace.trace_schema_version,
        "components": components_data,
    }
    if trace.deployment_profile is not None:
        canonical["deployment_profile"] = dict(trace.deployment_profile)
    return json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")


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


_DP_FIXTURE = {
    "agent_role": "ally",
    "agent_template": "ally-v3-default",
    "deployment_domain": "general",
    "deployment_type": "test",
    "deployment_region": "US",
    "deployment_trust_mode": "limited_trust",
}


def test_signed_payload_omits_deployment_profile_when_none():
    """When `deployment_profile` is None on the trace, the canonical falls
    back to the 9-key shape (the 2.7.0 outer shape). Replicates the
    pre-2.7.9 envelope. Persistence at trace_schema_version "2.7.9" rejects
    this shape per FSD §3.2; this test merely pins what the signer
    produces given a None block — so the fallback shape stays well-defined
    and reproducible across migration boundaries.
    """
    signer, mock_key = _make_signer_with_key()
    trace = _make_trace()
    assert trace.deployment_profile is None

    assert signer.sign_trace(trace) is True

    signed_bytes = mock_key.sign_base64.call_args[0][0]
    payload = json.loads(signed_bytes.decode("utf-8"))

    expected_keys = {
        "trace_id",
        "thought_id",
        "task_id",
        "agent_id_hash",
        "started_at",
        "completed_at",
        "trace_level",
        "trace_schema_version",
        "components",
    }
    assert set(payload.keys()) == expected_keys, (
        f"Canonical key set drift! Got {sorted(payload.keys())}, expected {sorted(expected_keys)}"
    )

    # trace_schema_version IS in the signed bytes (legacy 2-field excluded it)
    assert payload["trace_schema_version"] == trace.trace_schema_version
    # Provenance fields populated
    assert payload["trace_id"] == "trace-test-1"
    assert payload["thought_id"] == "th-1"
    assert payload["task_id"] == "task-1"
    assert payload["agent_id_hash"] == "deadbeef"


def test_signed_payload_includes_deployment_profile_when_present():
    """At trace_schema_version "2.7.9", the deployment_profile block is
    part of the signed canonical bytes per FSD §3.2 + §8. The block has
    exactly 6 fields and they are non-forgeable post-emission — a federation
    peer verifying the signature recovers exactly the cohort labels the
    agent declared at signing time.

    Persistence side: this is the canonical that compliant 2.7.9
    persist/lens implementations MUST reconstruct to verify, and from
    which they extract the 6 fields into their denormalized
    `cirislens.trace_context` columns.
    """
    signer, mock_key = _make_signer_with_key()
    trace = _make_trace()
    trace.deployment_profile = dict(_DP_FIXTURE)

    assert signer.sign_trace(trace) is True

    signed_bytes = mock_key.sign_base64.call_args[0][0]
    payload = json.loads(signed_bytes.decode("utf-8"))

    expected_keys = {
        "trace_id",
        "thought_id",
        "task_id",
        "agent_id_hash",
        "started_at",
        "completed_at",
        "trace_level",
        "trace_schema_version",
        "deployment_profile",
        "components",
    }
    assert set(payload.keys()) == expected_keys, (
        f"2.7.9 canonical key set drift! Got {sorted(payload.keys())}, "
        f"expected {sorted(expected_keys)}"
    )

    # deployment_profile is the exact 6-field block agent declared
    dp = payload["deployment_profile"]
    assert set(dp.keys()) == set(_DP_FIXTURE.keys()), (
        f"deployment_profile field set drift! Got {sorted(dp.keys())}, "
        f"expected {sorted(_DP_FIXTURE.keys())}"
    )
    assert dp == _DP_FIXTURE, "deployment_profile values must round-trip exactly"


def test_deployment_profile_canonical_byte_for_byte_pinning():
    """Pin the exact canonical bytes a 2.7.9 trace with deployment_profile
    produces. This is the structural contract persist v0.3.x must verify
    against — any drift here breaks every 2.7.9 federation signature
    simultaneously and gets caught at CI rather than in production.
    """
    signer, mock_key = _make_signer_with_key()
    trace = _make_trace(level="generic")
    trace.deployment_profile = dict(_DP_FIXTURE)

    assert signer.sign_trace(trace) is True
    actual_bytes = mock_key.sign_base64.call_args[0][0]
    expected_bytes = _build_expected_message(trace)

    assert actual_bytes == expected_bytes, (
        f"2.7.9 canonical (with deployment_profile) drift!\n"
        f"  Actual   hash: {hashlib.sha256(actual_bytes).hexdigest()[:16]}\n"
        f"  Expected hash: {hashlib.sha256(expected_bytes).hexdigest()[:16]}\n"
        f"  Actual:   {actual_bytes[:400]!r}\n"
        f"  Expected: {expected_bytes[:400]!r}"
    )


def test_deployment_profile_field_set_locked_at_six():
    """The deployment_profile block has exactly 6 agent-declared fields per
    FSD §3.2. Adding/removing fields is a breaking wire-format change that
    requires a trace_schema_version bump; this test catches accidental
    additions at CI.
    """
    signer, mock_key = _make_signer_with_key()
    trace = _make_trace()
    trace.deployment_profile = dict(_DP_FIXTURE)

    assert signer.sign_trace(trace) is True
    payload = json.loads(mock_key.sign_base64.call_args[0][0].decode("utf-8"))

    spec_six_fields = {
        "agent_role",
        "agent_template",
        "deployment_domain",
        "deployment_type",
        "deployment_region",
        "deployment_trust_mode",
    }
    assert set(payload["deployment_profile"].keys()) == spec_six_fields, (
        "deployment_profile field set must be exactly the 6 fields specified "
        "in FSD/TRACE_WIRE_FORMAT.md §3.2. Adding a 7th field requires a "
        "trace_schema_version bump and a §3.2 update — not a silent extension."
    )


def test_deployment_profile_region_null_is_valid_declaration():
    """`deployment_region = null` is a valid declaration of "not disclosed"
    per FSD §3.2 — distinct from absence-of-field (which is malformed at
    2.7.9). The signed canonical preserves the explicit null value.
    """
    signer, mock_key = _make_signer_with_key()
    trace = _make_trace()
    trace.deployment_profile = {**_DP_FIXTURE, "deployment_region": None}

    assert signer.sign_trace(trace) is True
    payload = json.loads(mock_key.sign_base64.call_args[0][0].decode("utf-8"))

    assert payload["deployment_profile"]["deployment_region"] is None
    # And the field IS present (not stripped by some empty-value pruning) —
    # the spec distinguishes "null disclosure" from "absent field"
    assert "deployment_region" in payload["deployment_profile"]


def test_signed_payload_matches_9_field_spec_canonical():
    """Exact byte-for-byte match against the 9-field spec canonical."""
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
    """Spec uses sort_keys=True + separators=(',', ':'). Must match exactly —
    persist canonicalizes the same way and any drift breaks every signature."""
    signer, mock_key = _make_signer_with_key()
    trace = _make_trace()

    assert signer.sign_trace(trace) is True
    signed_bytes = mock_key.sign_base64.call_args[0][0]
    signed_str = signed_bytes.decode("utf-8")

    # Compact separators: no space after comma, no space after colon
    assert ", " not in signed_str
    assert ": " not in signed_str
    # Keys alphabetically sorted at the top level — first is "agent_id_hash"
    # in the 9-field spec (it sorts before "components")
    assert signed_str.startswith('{"agent_id_hash":')


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
