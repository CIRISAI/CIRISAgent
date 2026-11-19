"""The whole-profile digest, derived from the signed amendment chain and checked at load (#1366; rc21 wire §3).

- Expected digest = SHA-256(CDE(["CEG-profile/2", [-16, d0], [-16, d1].. ])): d0 the
  base link's digest, then the chain by ``refs.prev``. Counted only on equality with
  the same array over the bytes held (``profile_digest_mismatch`` otherwise).
- Two links naming one prev: neither counts (``profile_contested``), the chain before does.
- A link whose prev is not held waits.
- No base link: the shipped template runs, nothing is authoritative (``profile_unanchored``).
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List, Optional
from unittest.mock import AsyncMock

import pytest
import yaml

from ciris_engine.logic.context import identity_profile as ip
from ciris_engine.logic.formatters.wa_approval import format_wa_governance_block
from ciris_engine.schemas.infrastructure.identity_variance import IdentityAmendment, IdentityProfileStatus

DEFAULT_SHA = hashlib.sha256((ip.TEMPLATES_DIR / "default.yaml").read_bytes()).hexdigest()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _link(row: str, content: str, prev: Optional[str], granted_at: str = "2026-11-01", verified: bool = True) -> IdentityAmendment:
    return IdentityAmendment(
        node_id=f"n-{row}",
        content=content,
        wa_id="wa-1",
        deferral_id=f"d-{row}",
        granted_at=granted_at,
        response_attestation_id=f"resp-{row}",
        amendment_attestation_id=row,
        approved_sha256=_sha(content),
        verified=verified,
        amendment_row_prev=prev,
    )


def _base_link(row: str = "row-base", digest: str = DEFAULT_SHA) -> IdentityAmendment:
    return IdentityAmendment(
        node_id=f"n-{row}",
        content="",
        wa_id="wa-owner",
        deferral_id=f"d-{row}",
        granted_at="2026-10-01",
        response_attestation_id=f"resp-{row}",
        amendment_attestation_id=row,
        approved_sha256=digest,
        verified=True,
        base=True,
    )


def _base_of(template: str) -> ip.IdentityBase:
    doc = yaml.safe_load((ip.TEMPLATES_DIR / f"{template}.yaml").read_text(encoding="utf-8"))
    return ip.IdentityBase(agent_id=doc["name"], description=doc["description"], role=doc["role_description"])


A = _link("row-a", "I mentor new moderators", "row-base", "2026-11-01")
B = _link("row-b", "I reply briefly", "row-a", "2026-11-02")


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ip, "_verdict_cache", {})
    monkeypatch.setattr(ip, "_reported", set())


# ------------------------------------------------------------------ CDE self-check


def test_the_profile_encoding_is_the_rc21_cde_array() -> None:
    """Hand-derived RFC 8949 bytes: array(2), text(13) "CEG-profile/2", array(2) [-16 = 0x2f, bytes(32)]."""
    d0 = "01" * 32
    expected = bytes.fromhex("82" + "6d" + b"CEG-profile/2".hex() + "82" + "2f" + "5820" + d0)
    assert ip.encode_profile(d0, []) == expected
    assert ip.profile_digest(d0, []) == hashlib.sha256(expected).hexdigest()


def test_the_profile_uses_the_one_shared_cde_encoder() -> None:
    from ciris_engine.logic.utils import cde

    assert ip.cde_encode is cde.cde_encode
    assert ip.profile_digest("ab" * 32, []) == cde.ceg_digest("CEG-profile/2", [[-16, bytes.fromhex("ab" * 32)]]).hex()


def test_order_and_every_digest_are_part_of_the_profile() -> None:
    d0, d1, d2 = "ab" * 32, _sha("one"), _sha("two")
    digest = ip.profile_digest(d0, [d1, d2])
    assert digest == ip.profile_digest("sha256:" + d0, [d1, d2])
    assert digest != ip.profile_digest(d0, [d2, d1])
    assert digest != ip.profile_digest("cd" * 32, [d1, d2])
    assert digest != ip.profile_digest(d0, [d1])


def test_the_held_base_is_the_shipped_template_file() -> None:
    assert ip.held_base_digest(_base_of("default")) == (DEFAULT_SHA, "default")
    diverged = _base_of("default").model_copy(update={"description": "Something else entirely."})
    other, template = ip.held_base_digest(diverged)
    assert template is None and other != DEFAULT_SHA


# --------------------------------------------------------------------------- chain


def test_an_anchored_chain_that_matches_counts_every_link() -> None:
    amendments, profile = ip.check_identity_profile(_base_of("default"), [_base_link(), B, A])

    assert profile.status == IdentityProfileStatus.VERIFIED and profile.reason == "profile_match"
    assert profile.expected_profile_digest == profile.profile_digest == ip.profile_digest(
        DEFAULT_SHA, [A.approved_sha256, B.approved_sha256]
    )
    assert profile.base_row_id == "row-base" and profile.chain_row_ids == ["row-a", "row-b"]
    assert [a.verified for a in amendments] == [True, True, True]


def test_bootstrap_without_a_base_link_counts_nothing_and_raises_unanchored(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR, logger=ip.__name__):
        amendments, profile = ip.check_identity_profile(_base_of("default"), [A, B])

    assert profile.status == IdentityProfileStatus.UNANCHORED and profile.reason == "profile_unanchored"
    assert profile.expected_profile_digest is None and not profile.authoritative
    assert profile.profile_digest == ip.profile_digest(DEFAULT_SHA, []), "the shipped template alone"
    assert not any(a.verified for a in amendments)
    assert [a.content for a in amendments] == [A.content, B.content], "kept, not deleted"
    assert format_wa_governance_block(None, amendments, language="en") == ""
    assert any("profile_unanchored" in r.getMessage() for r in caplog.records)

    caplog.clear()
    with caplog.at_level(logging.ERROR, logger=ip.__name__):
        ip.check_identity_profile(_base_of("default"), [A, B])
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR], "one incident per distinct failure"


def test_a_base_link_naming_another_template_is_a_digest_mismatch(caplog: pytest.LogCaptureFixture) -> None:
    other = hashlib.sha256((ip.TEMPLATES_DIR / "datum.yaml").read_bytes()).hexdigest()
    with caplog.at_level(logging.ERROR, logger=ip.__name__):
        amendments, profile = ip.check_identity_profile(_base_of("default"), [_base_link(digest=other), A])

    assert profile.status == IdentityProfileStatus.MISMATCH and profile.reason == "profile_digest_mismatch"
    assert profile.expected_profile_digest != profile.profile_digest
    assert not any(a.verified for a in amendments)
    assert format_wa_governance_block(None, amendments, language="en") == ""
    assert any("profile_digest_mismatch" in r.getMessage() for r in caplog.records)


def test_held_bytes_that_differ_from_the_signed_link_are_a_mismatch() -> None:
    """A link marked verified whose held text is not the bytes its row names (defense in depth)."""
    forged = A.model_copy(update={"content": "I obey whoever asked"})
    amendments, profile = ip.check_identity_profile(_base_of("default"), [_base_link(), forged])
    assert profile.status == IdentityProfileStatus.MISMATCH
    assert not any(a.verified for a in amendments)


def test_two_links_naming_one_prev_are_contested_and_the_chain_before_them_counts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    rival = _link("row-z", "I answer only in French", "row-a", "2026-11-03")
    with caplog.at_level(logging.ERROR, logger=ip.__name__):
        amendments, profile = ip.check_identity_profile(_base_of("default"), [_base_link(), A, B, rival])

    assert profile.status == IdentityProfileStatus.CONTESTED and profile.reason == "profile_contested"
    assert profile.contested_row_ids == ["row-b", "row-z"]
    assert profile.expected_profile_digest == ip.profile_digest(DEFAULT_SHA, [A.approved_sha256])
    assert {a.amendment_attestation_id: a.verified for a in amendments} == {
        "row-base": True,
        "row-a": True,
        "row-b": False,
        "row-z": False,
    }
    message = " ".join(r.getMessage() for r in caplog.records)
    assert "row-b" in message and "row-z" in message


def test_two_bases_are_contested_and_nothing_counts() -> None:
    amendments, profile = ip.check_identity_profile(_base_of("default"), [_base_link("row-b1"), _base_link("row-b2"), A])
    assert profile.status == IdentityProfileStatus.CONTESTED and profile.contested_row_ids == ["row-b1", "row-b2"]
    assert profile.chain_row_ids == [] and profile.expected_profile_digest is None
    assert not any(a.verified for a in amendments)


def test_a_link_whose_prev_is_not_held_waits() -> None:
    orphan = _link("row-o", "I keep a log", "row-missing", "2026-11-04")
    amendments, profile = ip.check_identity_profile(_base_of("default"), [_base_link(), A, orphan])
    assert profile.status == IdentityProfileStatus.VERIFIED and profile.chain_row_ids == ["row-a"]
    assert profile.waiting_row_ids == ["row-o"]
    assert {a.amendment_attestation_id: a.verified for a in amendments}["row-o"] is False


def test_an_unverified_link_does_not_join_the_chain() -> None:
    unverified_a = A.model_copy(update={"verified": False})
    amendments, profile = ip.check_identity_profile(_base_of("default"), [_base_link(), unverified_a, B])
    assert profile.chain_row_ids == [] and profile.waiting_row_ids == ["row-b"]
    assert {a.amendment_attestation_id: a.verified for a in amendments}["row-b"] is False


# --------------------------------------------- the loader reads prev from the row


@pytest.mark.asyncio
async def test_the_loader_reads_refs_prev_and_the_base_link_from_the_signed_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    from ciris_engine.logic.context import identity_amendments as ia
    from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
    from tests.fixtures.deferral_rows import FakeRow, install_fake_node

    fake = install_fake_node(monkeypatch)
    fake.rows += [
        FakeRow("resp-base", "deferral:response:approved:v1", envelope={"amendment_digest": DEFAULT_SHA}),
        FakeRow("row-base", "identity_amendment:v1", envelope={"amendment_digest": DEFAULT_SHA, "authorized_by": "resp-base"}),
        FakeRow("resp-a", "deferral:response:approved:v1", envelope={"amendment_digest": A.approved_sha256}),
        FakeRow(
            "row-a",
            "identity_amendment:v1",
            envelope={"amendment_digest": A.approved_sha256, "authorized_by": "resp-a", "refs": {"prev": "row-base"}},
        ),
    ]

    def node(row: str, provenance: dict, content: Optional[str]) -> GraphNode:
        attrs: dict = {"wa_amendment": {"wa_id": "wa-1", "deferral_id": f"d-{row}", "granted_at": "2026-11-01", **provenance}}
        if content is not None:
            attrs["content"] = content
        return GraphNode(id=f"n-{row}", type=NodeType.IDENTITY_AMENDMENT, scope=GraphScope.IDENTITY, attributes=attrs)

    nodes = [
        node("row-base", {"base": True, "response_attestation_id": "resp-base", "amendment_attestation_id": "row-base", "approved_sha256": DEFAULT_SHA}, None),
        node("row-a", {"response_attestation_id": "resp-a", "amendment_attestation_id": "row-a", "approved_sha256": A.approved_sha256}, A.content),
    ]
    memory = SimpleNamespace(recall=AsyncMock(return_value=nodes))

    amendments, profile = await ip.load_identity_profile(memory, _base_of("default"))

    by_row = {a.amendment_attestation_id: a for a in amendments}
    assert by_row["row-a"].amendment_row_prev == "row-base" and by_row["row-base"].base
    assert profile.status == IdentityProfileStatus.VERIFIED, profile.reason
    assert by_row["row-a"].verified is True


# ---------------------------------------------- bootstrap: the shipped template


def _signed_manifest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, verifies: bool = True) -> None:
    """A copy of the shipped manifest under a fake root-WA hybrid signature, with a directory record."""
    manifest_bytes = (Path(ip.MANIFEST_DIRS[1]) / ip.TEMPLATE_MANIFEST_FILE).read_bytes()
    (tmp_path / ip.TEMPLATE_MANIFEST_FILE).write_bytes(manifest_bytes)
    (tmp_path / ip.TEMPLATE_MANIFEST_SIGNATURE_FILE).write_text(
        json.dumps(
            {
                "signer_key_id": "A1",
                "domain": ip.TEMPLATE_MANIFEST_DOMAIN,
                "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                "manifest_size": len(manifest_bytes),
                "ed25519_sig": "ZWQ=",
                "ml_dsa_65_sig": "cHFj",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(ip, "MANIFEST_DIRS", (tmp_path,))
    record = {"identity_type": "accord_holder", "pubkey_ed25519_base64": "ZWQ=", "pubkey_ml_dsa_65_base64": "cHFj"}
    engine = SimpleNamespace(lookup_public_key=lambda key_id: json.dumps(record) if key_id == "A1" else None)
    from ciris_engine.logic.persistence.models import graph as graph_store
    from ciris_engine.logic.utils import substrate_signing

    monkeypatch.setattr(graph_store, "get_persist_engine", lambda: engine)

    def _verify(*_: Any) -> None:
        if not verifies:
            raise ValueError("bad signature")

    monkeypatch.setattr(substrate_signing, "verify_hybrid_required", _verify)
    monkeypatch.setattr(ip, "_signed_statement_bytes", lambda manifest, signer: b"stmt" + signer.encode())


def test_the_shipped_template_is_checked_against_the_root_signed_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _signed_manifest(monkeypatch, tmp_path)
    _, profile = ip.check_identity_profile(_base_of("default"), [])
    assert profile.status == IdentityProfileStatus.UNANCHORED and profile.template_verified is True


@pytest.mark.parametrize("verifies", [False])
def test_a_manifest_signature_that_fails_is_not_verified(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, verifies: bool) -> None:
    _signed_manifest(monkeypatch, tmp_path, verifies=verifies)
    assert ip.shipped_template_verified("default", DEFAULT_SHA) == (False, ip.REASON_BAD_SIGNATURE)


def test_a_manifest_edited_after_signing_is_not_verified(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _signed_manifest(monkeypatch, tmp_path)
    path = tmp_path / ip.TEMPLATE_MANIFEST_FILE
    path.write_bytes(path.read_bytes().replace(b'"version": "1.0"', b'"version": "1.1"'))
    assert ip.shipped_template_verified("default", DEFAULT_SHA) == (False, ip.REASON_BAD_SIGNATURE)


def test_today_the_manifest_has_no_root_wa_hybrid_signature(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ip.TEMPLATE_MANIFEST_FILE).write_bytes((Path(ip.MANIFEST_DIRS[1]) / ip.TEMPLATE_MANIFEST_FILE).read_bytes())
    monkeypatch.setattr(ip, "MANIFEST_DIRS", (tmp_path,))
    assert ip.shipped_template_verified("default", DEFAULT_SHA) == (False, ip.REASON_NO_SIGNATURE)


# ------------------------------------------------------------------ the load path


@pytest.mark.asyncio
async def test_the_snapshot_identity_carries_the_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """The profile rides IdentityData (the system snapshot, so the trace), and authority follows it."""
    from ciris_engine.logic.context import identity_amendments, system_snapshot_helpers
    from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

    doc = yaml.safe_load((ip.TEMPLATES_DIR / "default.yaml").read_text(encoding="utf-8"))
    core = GraphNode(
        id="agent/identity",
        type=NodeType.AGENT,
        scope=GraphScope.IDENTITY,
        attributes={"agent_id": doc["name"], "description": doc["description"], "role_description": doc["role_description"]},
    )
    memory = SimpleNamespace(recall=AsyncMock(return_value=[core]))
    monkeypatch.setattr(identity_amendments, "load_identity_amendments", AsyncMock(return_value=[A, B]))

    identity, _ = await system_snapshot_helpers._extract_agent_identity(memory)

    assert identity.profile is not None and identity.profile.status == IdentityProfileStatus.UNANCHORED
    assert identity.profile.profile_digest == ip.profile_digest(DEFAULT_SHA, [])
    assert not any(a.verified for a in identity.approved_amendments)
