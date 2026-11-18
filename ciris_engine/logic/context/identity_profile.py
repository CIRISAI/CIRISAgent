"""The whole-profile digest of the agent's identity, checked at load (#1366; rc21 wire, section 3).

Eric, 2026-11-18: identity amendments are the exact WA-approved bytes, and the
whole profile is checked at load. The constitution's rc21 wire fixes how: no row
asserts the profile; its digest is DERIVED from the signed ``identity_amendment``
chain.

- Each ``identity_amendment`` row names the row it follows (``refs.prev``). The
  link with no ``prev`` is the BASE: its ``amendment_digest`` is the base
  template's digest, approved like any amendment.
- Expected digest: SHA-256(CDE(["CEG-profile/2", d0, d1..dn])), each d written
  ``[-16, digest]`` (digest as bytes): d0 the base link's digest, d1..dn the
  chain from it. The agent computes the same array over the bytes it is about
  to load and counts the chain only on equality (else ``profile_digest_mismatch``).
- A link whose ``prev`` is not held waits. Two links naming one ``prev``:
  neither counts (``profile_contested``), and the chain before them does.
- Bootstrap: with no base link the agent runs its shipped template (checked
  against the root-WA-signed template manifest where that signature verifies),
  counts NO amendment as authoritative, and raises ``profile_unanchored`` until
  the owner approves a base link.

Failing the check fails closed FOR AUTHORITY only: no amendment counts as
verified (the governance block the input-ablated consciences read carries
none), an incident is logged, and the agent keeps running on its base
identity; unverified amendments still reach the other stages, labelled
unverified (``formatters.identity``). Stopping would take down the consciences
that judge whatever the agent does next, and a profile that cannot be proven is
usually an edited template or a pending approval, not an attack.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import yaml
from pydantic import BaseModel, ConfigDict

from ciris_engine.schemas.infrastructure.identity_variance import (
    IdentityAmendment,
    IdentityProfile,
    IdentityProfileStatus,
)

logger = logging.getLogger(__name__)

#: The first member of the profile array (rc21 wire, section 3).
PROFILE_DIGEST_DOMAIN = "CEG-profile/2"
#: The COSE algorithm id of SHA-256: each digest is written ``[-16, digest]``.
SHA256_ALG = -16
#: Domain of the statement a root WA signs over the template manifest (bootstrap check).
TEMPLATE_MANIFEST_DOMAIN = "ciris.template_manifest.v1"
#: The root-WA hybrid signature over the template manifest, beside it. Signers
#: are the pinned root roster that signs the accord manifest
#: (``accord_manifest_hybrid.ACCORD_MANIFEST_SIGNERS``, accord-holder records in
#: the federation directory). The manifest's own classical ``root_signature`` is
#: by the 2025 root retired in 2.20.0 (100% PQC) and is never accepted here.
TEMPLATE_MANIFEST_SIGNATURE_FILE = "pre-approved-templates.hybrid.json"
TEMPLATE_MANIFEST_FILE = "pre-approved-templates.json"

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = _PACKAGE_ROOT / "ciris_templates"
#: Where the signed template manifest is looked for, in order: shipped beside
#: the accord manifest, then the repository root (a source checkout).
MANIFEST_DIRS: Tuple[Path, ...] = (_PACKAGE_ROOT / "data" / "seed", _PACKAGE_ROOT.parent)

# The rc21 tokens (``IdentityProfile.reason``).
REASON_MATCH = "profile_match"
REASON_MISMATCH = "profile_digest_mismatch"
REASON_CONTESTED = "profile_contested"
REASON_UNANCHORED = "profile_unanchored"
# Why the shipped template's root-WA check did not verify (logged with profile_unanchored).
REASON_NO_MANIFEST = "template_manifest_missing"
REASON_NO_SIGNATURE = "template_manifest_unsigned"
REASON_BAD_SIGNATURE = "template_manifest_signature_invalid"
REASON_NO_ENGINE = "template_manifest_unverifiable_no_engine"
REASON_NOT_IN_MANIFEST = "template_not_in_manifest"


class IdentityBase(BaseModel):
    """The template identity fields the agent holds in ``agent/identity``."""

    agent_id: str
    description: str
    role: str

    model_config = ConfigDict(frozen=True)


# --------------------------------------------------------------------------- CDE


def cde_encode(value: Any) -> bytes:
    """CBOR Deterministic Encoding (RFC 8949 section 4.2.1) of ``value``: the ONE encoder here.

    TODO(rc21 CDE): ciris_server has no CDE encoder yet; swap this body for the
    server's when it lands (and unify with the call-fingerprint encoder at
    merge). Until then: cbor2 with ``canonical=True`` where cbor2 is installed
    (it is not a declared dependency), else the built-in encoder below. The
    profile array holds only text, integers, byte strings and arrays, for which
    cbor2's canonical form IS CDE (shortest-form heads, definite lengths); its
    map-key order is RFC 7049's length-first, not CDE's bytewise order, so maps
    are refused rather than encoded wrong.
    """
    _refuse_maps(value)
    try:
        import cbor2
    except ImportError:
        return _cde_builtin(value)
    return bytes(cbor2.dumps(value, canonical=True))


def _refuse_maps(value: Any) -> None:
    if isinstance(value, dict):
        raise TypeError("cde_encode: maps are not encoded until the server's CDE encoder lands")
    if isinstance(value, (list, tuple)):
        for item in value:
            _refuse_maps(item)


def _cde_head(major: int, argument: int) -> bytes:
    if argument < 24:
        return bytes([(major << 5) | argument])
    for info, size in ((24, 1), (25, 2), (26, 4), (27, 8)):
        if argument < 1 << (8 * size):
            return bytes([(major << 5) | info]) + argument.to_bytes(size, "big")
    raise ValueError("cde_encode: integer out of range")


def _cde_builtin(value: Any) -> bytes:
    """Deterministic CBOR for text, bytes, integers and arrays (the profile array's types)."""
    if isinstance(value, bool) or value is None:
        raise TypeError("cde_encode: unsupported type")
    if isinstance(value, int):
        return _cde_head(0, value) if value >= 0 else _cde_head(1, -1 - value)
    if isinstance(value, (bytes, bytearray)):
        return _cde_head(2, len(value)) + bytes(value)
    if isinstance(value, str):
        raw = value.encode("utf-8")
        return _cde_head(3, len(raw)) + raw
    if isinstance(value, (list, tuple)):
        return _cde_head(4, len(value)) + b"".join(_cde_builtin(v) for v in value)
    raise TypeError(f"cde_encode: unsupported type {type(value).__name__}")


# ----------------------------------------------------------------------- digest


def _bare_hex(digest: str) -> str:
    return digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else digest.lower()


def encode_profile(base_digest: str, amendment_digests: Sequence[str]) -> bytes:
    """CDE(["CEG-profile/2", [-16, d0], [-16, d1], ..., [-16, dn]]), each digest as bytes.

    The digests stay 64-hex text on the 0.5.250 wire (``amendment_digest``);
    they become ``[-16, digest]`` byte strings only here.
    """
    items: List[Any] = [PROFILE_DIGEST_DOMAIN]
    for digest in (base_digest, *amendment_digests):
        items.append([SHA256_ALG, bytes.fromhex(_bare_hex(digest))])
    return cde_encode(items)


def profile_digest(base_digest: str, amendment_digests: Sequence[str]) -> str:
    """SHA-256 (hex) of :func:`encode_profile`."""
    return hashlib.sha256(encode_profile(base_digest, amendment_digests)).hexdigest()


# --------------------------------------------------------------------- held base


def _template_fields(path: Path) -> Optional[Tuple[str, str, str]]:
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(doc, dict):
        return None
    return (
        str(doc.get("name") or ""),
        str(doc.get("description") or "").strip(),
        str(doc.get("role_description") or "").strip(),
    )


def _held_fields(base: IdentityBase) -> Tuple[str, str, str]:
    return (base.agent_id, base.description.strip(), base.role.strip())


def held_base_digest(base: IdentityBase, templates_dir: Optional[Path] = None) -> Tuple[str, Optional[str]]:
    """sha256 hex of the base the agent loads, and the shipped template it is, if any.

    The held base is the shipped template file whose identity fields (name,
    description, role) equal the held ``agent/identity``: its bytes' sha256,
    the digest a base link approves and the template manifest records. When no
    file matches (the held identity diverged from every template), the digest
    is of the held fields' canonical form, which no base link can name.
    """
    directory = templates_dir or TEMPLATES_DIR
    held = _held_fields(base)
    for path in sorted(directory.glob("*.yaml")):
        if _template_fields(path) == held:
            return hashlib.sha256(path.read_bytes()).hexdigest(), path.stem
    canonical = json.dumps(
        {"agent_id": held[0], "description": held[1], "role": held[2]},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest(), None


# ------------------------------------------------ bootstrap: the shipped template


def _signed_statement_bytes(manifest_bytes: bytes, signer: str) -> bytes:
    """The 32 bytes a root WA signs: sha256 of the JCS statement of the manifest (CC 5.3.2.5 form)."""
    from ciris_adapters.ciris_verify.ffi_bindings import jcs_canonicalize

    statement = {
        "domain": TEMPLATE_MANIFEST_DOMAIN,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "manifest_size": len(manifest_bytes),
        "signer_identity": signer,
    }
    return hashlib.sha256(jcs_canonicalize(statement)).digest()


class _ManifestVerdict(BaseModel):
    templates: Optional[Dict[str, Dict[str, str]]] = None
    reason: str


_verdict_cache: Dict[Tuple[str, int, int, int], _ManifestVerdict] = {}
_cache_lock = threading.Lock()


def _verify_manifest_signature(manifest_bytes: bytes, sig_path: Path) -> Optional[str]:
    """None when a root WA's hybrid signature over the manifest verifies; else the reason id."""
    from ciris_engine.logic.persistence.models.graph import get_persist_engine
    from ciris_engine.logic.utils import substrate_signing
    from ciris_engine.logic.utils.accord_manifest_hybrid import (
        ACCORD_HOLDER_IDENTITY_TYPE,
        ACCORD_MANIFEST_SIGNERS,
    )

    try:
        doc = json.loads(sig_path.read_text(encoding="utf-8"))
        signer = str(doc["signer_key_id"])
        ed_sig, pqc_sig = str(doc["ed25519_sig"]), str(doc["ml_dsa_65_sig"])
    except (OSError, ValueError, KeyError, TypeError):
        return REASON_BAD_SIGNATURE
    if (
        signer not in ACCORD_MANIFEST_SIGNERS
        or doc.get("domain") != TEMPLATE_MANIFEST_DOMAIN
        or doc.get("manifest_size") != len(manifest_bytes)
        or doc.get("manifest_sha256") != hashlib.sha256(manifest_bytes).hexdigest()
    ):
        return REASON_BAD_SIGNATURE
    engine = get_persist_engine()
    if engine is None:
        return REASON_NO_ENGINE
    try:
        raw = engine.lookup_public_key(signer)
        record = json.loads(raw) if raw else None
        if not isinstance(record, dict) or record.get("identity_type") != ACCORD_HOLDER_IDENTITY_TYPE:
            return REASON_BAD_SIGNATURE
        ed_pub, pqc_pub = record.get("pubkey_ed25519_base64"), record.get("pubkey_ml_dsa_65_base64")
        if not (isinstance(ed_pub, str) and ed_pub and isinstance(pqc_pub, str) and pqc_pub):
            return REASON_BAD_SIGNATURE
        substrate_signing.verify_hybrid_required(
            engine, _signed_statement_bytes(manifest_bytes, signer), ed_sig, pqc_sig, ed_pub, pqc_pub
        )
    except Exception as exc:  # noqa: BLE001 - any failure to verify is "not verified"
        logger.warning(f"template manifest: root-WA signature did not verify ({type(exc).__name__})")
        return REASON_BAD_SIGNATURE
    return None


def verified_template_manifest(manifest_dirs: Optional[Sequence[Path]] = None) -> _ManifestVerdict:
    """The template manifest's entries when a root WA's hybrid signature over it verifies.

    Cached per manifest and signature file state, so the check runs once per
    change, not once per snapshot. A verdict that waited on the engine is not
    cached.
    """
    for directory in manifest_dirs or MANIFEST_DIRS:
        manifest = directory / TEMPLATE_MANIFEST_FILE
        if manifest.is_file():
            break
    else:
        return _ManifestVerdict(reason=REASON_NO_MANIFEST)
    sig_path = manifest.parent / TEMPLATE_MANIFEST_SIGNATURE_FILE
    if not sig_path.is_file():
        return _ManifestVerdict(reason=REASON_NO_SIGNATURE)
    m_stat, s_stat = manifest.stat(), sig_path.stat()
    key = (str(manifest), m_stat.st_mtime_ns, m_stat.st_size, s_stat.st_mtime_ns)
    with _cache_lock:
        cached = _verdict_cache.get(key)
    if cached is not None:
        return cached
    manifest_bytes = manifest.read_bytes()
    failure = _verify_manifest_signature(manifest_bytes, sig_path)
    if failure is not None:
        verdict = _ManifestVerdict(reason=failure)
    else:
        try:
            templates = json.loads(manifest_bytes).get("templates")
        except ValueError:
            templates = None
        if not isinstance(templates, dict):
            verdict = _ManifestVerdict(reason=REASON_BAD_SIGNATURE)
        else:
            verdict = _ManifestVerdict(
                templates={str(k): {"checksum": str(v.get("checksum", ""))} for k, v in templates.items() if isinstance(v, dict)},
                reason=REASON_MATCH,
            )
    if verdict.reason != REASON_NO_ENGINE:
        with _cache_lock:
            _verdict_cache[key] = verdict
    return verdict


def shipped_template_verified(template: Optional[str], base_digest: str) -> Tuple[bool, str]:
    """Whether the shipped template's bytes are the root-WA-signed manifest's entry for it; and why not."""
    if template is None:
        return False, REASON_NOT_IN_MANIFEST
    verdict = verified_template_manifest()
    if verdict.templates is None:
        return False, verdict.reason
    checksum = verdict.templates.get(template, {}).get("checksum")
    if not checksum or _bare_hex(checksum) != _bare_hex(base_digest):
        return False, REASON_NOT_IN_MANIFEST
    return True, REASON_MATCH


# ------------------------------------------------------------------------ chain


class ProfileChain(BaseModel):
    """The signed chain as the rows name it: the base, the counted links, and what does not count."""

    base: Optional[IdentityAmendment] = None
    links: List[IdentityAmendment] = []
    contested_row_ids: List[str] = []
    waiting_row_ids: List[str] = []


def build_chain(amendments: Sequence[IdentityAmendment]) -> ProfileChain:
    """Order the verified links by what they name (``refs.prev``), from the base.

    Only links whose own rows verified take part. Two links naming one slot
    (one ``prev``, or two bases) are concurrent: neither counts, and the chain
    stops before them. A link whose ``prev`` is not in the chain waits.
    """
    linked = [a for a in amendments if a.verified and a.amendment_attestation_id and a.approved_sha256]
    bases = [a for a in linked if a.base and a.amendment_row_prev is None]
    children: Dict[str, List[IdentityAmendment]] = {}
    for a in linked:
        if not a.base and a.amendment_row_prev:
            children.setdefault(a.amendment_row_prev, []).append(a)
    if len(bases) > 1:
        return ProfileChain(contested_row_ids=sorted(str(b.amendment_attestation_id) for b in bases))
    if not bases:
        return ProfileChain(waiting_row_ids=sorted(str(a.amendment_attestation_id) for a in linked if not a.base))
    chain = ProfileChain(base=bases[0])
    placed = {str(bases[0].amendment_attestation_id)}
    cursor = str(bases[0].amendment_attestation_id)
    while cursor in children:
        nxt = children[cursor]
        if len(nxt) > 1:
            chain.contested_row_ids = sorted(str(a.amendment_attestation_id) for a in nxt)
            placed.update(chain.contested_row_ids)
            break
        chain.links.append(nxt[0])
        cursor = str(nxt[0].amendment_attestation_id)
        placed.add(cursor)
    chain.waiting_row_ids = sorted(
        str(a.amendment_attestation_id) for a in linked if not a.base and str(a.amendment_attestation_id) not in placed
    )
    return chain


def expected_profile_digest(chain: ProfileChain) -> Optional[str]:
    """SHA-256 over the chain's SIGNED digests: d0 the base link's, then each link's; None with no base."""
    if chain.base is None or not chain.base.approved_sha256:
        return None
    return profile_digest(chain.base.approved_sha256, [str(a.approved_sha256) for a in chain.links])


# ------------------------------------------------------------------------- check


_reported: set[Tuple[str, str]] = set()


def _report_incident(profile: IdentityProfile) -> None:
    """One ERROR (an incident) per distinct failure, not one per snapshot."""
    key = (profile.reason, profile.profile_digest)
    if key in _reported:
        return
    _reported.add(key)
    detail = f" rows {', '.join(profile.contested_row_ids)}" if profile.contested_row_ids else ""
    logger.error(
        "IDENTITY PROFILE %s (%s%s): held profile %s, expected %s, shipped template %s. %s",
        profile.status.value.upper(),
        profile.reason,
        detail,
        profile.profile_digest,
        profile.expected_profile_digest or "-",
        "verified" if profile.template_verified else "not verified",
        "Only the chain before the contested links counts."
        if profile.status == IdentityProfileStatus.CONTESTED
        else "No identity amendment counts as authoritative; the agent keeps running on its base identity.",
    )


def check_identity_profile(
    base: IdentityBase, amendments: Sequence[IdentityAmendment]
) -> Tuple[List[IdentityAmendment], IdentityProfile]:
    """The amendments as authority sees them, and the profile check that decided it.

    ``amendments`` come from ``load_identity_amendments`` (each checked against
    its own signed rows, with its row's ``refs.prev``). Only the links of a
    chain whose held profile equals the derived one stay verified.
    """
    base_digest, template = held_base_digest(base)
    template_ok, template_reason = shipped_template_verified(template, base_digest)
    chain = build_chain(amendments)
    held_digests = [hashlib.sha256(a.content.encode("utf-8")).hexdigest() for a in chain.links]
    held = profile_digest(base_digest, held_digests)
    expected = expected_profile_digest(chain)
    if expected is None:
        status = IdentityProfileStatus.CONTESTED if chain.contested_row_ids else IdentityProfileStatus.UNANCHORED
        reason = REASON_CONTESTED if chain.contested_row_ids else REASON_UNANCHORED
        counted: List[IdentityAmendment] = []
        if not template_ok:
            logger.warning(f"identity profile: shipped template not verified ({template_reason})")
    elif expected != held:
        status, reason, counted = IdentityProfileStatus.MISMATCH, REASON_MISMATCH, []
    elif chain.contested_row_ids:
        status, reason, counted = IdentityProfileStatus.CONTESTED, REASON_CONTESTED, list(chain.links)
    else:
        status, reason, counted = IdentityProfileStatus.VERIFIED, REASON_MATCH, list(chain.links)
    profile = IdentityProfile(
        profile_digest=held,
        expected_profile_digest=expected,
        status=status,
        reason=reason,
        template=template,
        template_verified=template_ok,
        base_digest=_bare_hex(base_digest),
        base_row_id=chain.base.amendment_attestation_id if chain.base else None,
        chain_row_ids=[str(a.amendment_attestation_id) for a in counted],
        amendment_digests=[str(a.approved_sha256) for a in counted],
        contested_row_ids=chain.contested_row_ids,
        waiting_row_ids=chain.waiting_row_ids,
    )
    if status != IdentityProfileStatus.VERIFIED:
        _report_incident(profile)
    keep = {id(a) for a in counted}
    if counted or (status == IdentityProfileStatus.VERIFIED and chain.base is not None):
        keep.add(id(chain.base))
    return [a if id(a) in keep or not a.verified else a.model_copy(update={"verified": False}) for a in amendments], profile


async def load_identity_profile(
    memory_service: object, base: IdentityBase
) -> Tuple[List[IdentityAmendment], IdentityProfile]:
    """Load the amendments, verify each against its rows, then check the whole profile (the one identity load path)."""
    from ciris_engine.logic.context.identity_amendments import load_identity_amendments

    return check_identity_profile(base, await load_identity_amendments(memory_service))


__all__ = [
    "IdentityBase",
    "PROFILE_DIGEST_DOMAIN",
    "ProfileChain",
    "build_chain",
    "cde_encode",
    "check_identity_profile",
    "encode_profile",
    "expected_profile_digest",
    "held_base_digest",
    "load_identity_profile",
    "profile_digest",
    "shipped_template_verified",
    "verified_template_manifest",
]
