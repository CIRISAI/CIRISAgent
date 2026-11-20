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

import asyncio
import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Set, Tuple

import yaml
from pydantic import BaseModel, ConfigDict

from ciris_engine.logic.utils.cde import SHA256_ALG, cde_encode, ceg_digest
from ciris_engine.schemas.api.wa import IdentityChangeProposal, ProposedBaseLink
from ciris_engine.schemas.infrastructure.identity_variance import (
    IdentityAmendment,
    IdentityProfile,
    IdentityProfileStatus,
)

logger = logging.getLogger(__name__)

#: The first member of the profile array (rc21 wire, section 3).
PROFILE_DIGEST_DOMAIN = "CEG-profile/2"
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


# ----------------------------------------------------------------------- digest


def _bare_hex(digest: str) -> str:
    return digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else digest.lower()


def encode_profile(base_digest: str, amendment_digests: Sequence[str]) -> bytes:
    """CDE(["CEG-profile/2", [-16, d0], [-16, d1], ..., [-16, dn]]), each digest as bytes.

    The digests stay 64-hex text on the 0.5.250 wire (``amendment_digest``);
    they become ``[-16, digest]`` byte strings only here.
    """
    return cde_encode([PROFILE_DIGEST_DOMAIN, *_profile_members(base_digest, amendment_digests)])


def _profile_members(base_digest: str, amendment_digests: Sequence[str]) -> List[Any]:
    return [[SHA256_ALG, bytes.fromhex(_bare_hex(d))] for d in (base_digest, *amendment_digests)]


def profile_digest(base_digest: str, amendment_digests: Sequence[str]) -> str:
    """SHA-256 (hex) of :func:`encode_profile` (``ceg_digest`` of the shared CDE encoder)."""
    return ceg_digest(PROFILE_DIGEST_DOMAIN, _profile_members(base_digest, amendment_digests)).hex()


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


#: The ``refs.prev`` a first amendment names when its base is a pre-approved shipped template (Eric, 2026-11-20:
#: "the template ships pre-approved"). The base is DERIVED, not a row: the accord-holder-signed template manifest
#: is the authority, verified at boot. The hex is the template file's own sha256 (its manifest checksum), never the
#: manifest's: a release re-signs the manifest, and only a change to the template's bytes should break the chain.
TEMPLATE_BASE_PREFIX = "template:"


def template_base_ref(template_digest: str) -> str:
    """The derived base's reference for a pre-approved shipped template: ``template:<64 lowercase hex>``."""
    return f"{TEMPLATE_BASE_PREFIX}{_bare_hex(template_digest).lower()}"


class ProfileChain(BaseModel):
    """The signed chain as the rows name it: the base, the counted links, and what does not count."""

    base: Optional[IdentityAmendment] = None
    #: A pre-approved shipped template's base (``template:<digest>``), when no base row exists.
    derived_base: Optional[str] = None
    links: List[IdentityAmendment] = []
    contested_row_ids: List[str] = []
    waiting_row_ids: List[str] = []


def build_chain(amendments: Sequence[IdentityAmendment], derived_base: Optional[str] = None) -> ProfileChain:
    """Order the verified links by what they name (``refs.prev``), from the base.

    Only links whose own rows verified take part. Two links naming one slot
    (one ``prev``, or two bases) are concurrent: neither counts, and the chain
    stops before them. A link whose ``prev`` is not in the chain waits.

    ``derived_base`` (``template:<digest>``) is a pre-approved shipped template's base: used when no base ROW
    exists, so the first amendment names it as its ``prev``. A base row (a Wise Authority approved this
    template by hand) still takes precedence.
    """
    linked = [a for a in amendments if a.verified and a.amendment_attestation_id and a.approved_sha256]
    bases = [a for a in linked if a.base and a.amendment_row_prev is None]
    children: Dict[str, List[IdentityAmendment]] = {}
    for a in linked:
        if not a.base and a.amendment_row_prev:
            children.setdefault(a.amendment_row_prev, []).append(a)
    if len(bases) > 1:
        return ProfileChain(contested_row_ids=sorted(str(b.amendment_attestation_id) for b in bases))
    if not bases and derived_base is None:
        return ProfileChain(waiting_row_ids=sorted(str(a.amendment_attestation_id) for a in linked if not a.base))
    if bases:
        chain = ProfileChain(base=bases[0])
        cursor = str(bases[0].amendment_attestation_id)
    else:
        chain = ProfileChain(derived_base=derived_base)
        cursor = str(derived_base)
    placed = {cursor}
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
    """SHA-256 over the chain's SIGNED digests: d0 the base's, then each link's; None with no base.

    For a derived base d0 is the template digest the holder-signed manifest records (in ``template:<digest>``).
    """
    links = [str(a.approved_sha256) for a in chain.links]
    if chain.base is not None and chain.base.approved_sha256:
        return profile_digest(chain.base.approved_sha256, links)
    if chain.derived_base is not None:
        return profile_digest(chain.derived_base[len(TEMPLATE_BASE_PREFIX) :], links)
    return None


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
    # A shipped template the accord holder pre-approved is the anchored base: no deferral, no row (Eric, 2026-11-20).
    chain = build_chain(amendments, derived_base=template_base_ref(base_digest) if template_ok else None)
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
        base_row_id=chain.base.amendment_attestation_id if chain.base else chain.derived_base,
        chain_row_ids=[str(a.amendment_attestation_id) for a in counted],
        amendment_digests=[str(a.approved_sha256) for a in counted],
        contested_row_ids=chain.contested_row_ids,
        waiting_row_ids=chain.waiting_row_ids,
    )
    if status != IdentityProfileStatus.VERIFIED:
        _report_incident(profile)
    keep = {id(a) for a in counted}
    if chain.base is not None and (counted or status == IdentityProfileStatus.VERIFIED):
        keep.add(id(chain.base))
    return [a if id(a) in keep or not a.verified else a.model_copy(update={"verified": False}) for a in amendments], profile


async def load_identity_profile(
    memory_service: object, base: IdentityBase
) -> Tuple[List[IdentityAmendment], IdentityProfile]:
    """Load the amendments, verify each against its rows, then check the whole profile (the one identity load path).

    The latest result is kept for the deferral list (:func:`latest_identity_profile`),
    and an unanchored profile asks a Wise Authority for its base link
    (:func:`maybe_open_base_link`), once.
    """
    global _latest_profile
    from ciris_engine.logic.context.identity_amendments import load_identity_amendments

    per_row = await load_identity_amendments(memory_service)
    amendments, profile = check_identity_profile(base, per_row)
    _latest_profile = profile
    _settle_appended_head(profile)
    maybe_open_base_link(profile)
    maybe_open_reapprovals(per_row, profile)
    return amendments, profile


# --------------------------------------------------------------- the base link


#: The newest whole-profile check this process made (``None`` before the first).
_latest_profile: Optional[IdentityProfile] = None

#: Opens the base-link deferral: the Wise Authority service registers it at start.
BaseLinkOpener = Callable[[ProposedBaseLink], Awaitable[Optional[str]]]
_base_link_opener: Optional[BaseLinkOpener] = None
#: Digests this process already asked for (or found pending): one request per process.
_base_link_requested: Set[str] = set()
_base_link_tasks: Set["asyncio.Task[None]"] = set()


def latest_identity_profile() -> Optional[IdentityProfile]:
    """The newest whole-profile check, or ``None`` before the first identity load."""
    return _latest_profile


def set_base_link_opener(opener: Optional[BaseLinkOpener]) -> None:
    """Register (or clear) what opens the base-link deferral. The Wise Authority service, at start/stop."""
    global _base_link_opener
    _base_link_opener = opener


def _template_manifest_version(manifest_dirs: Optional[Sequence[Path]] = None) -> Optional[str]:
    for directory in manifest_dirs or MANIFEST_DIRS:
        manifest = directory / TEMPLATE_MANIFEST_FILE
        if manifest.is_file():
            try:
                version = json.loads(manifest.read_text(encoding="utf-8")).get("version")
            except (OSError, ValueError, AttributeError):
                return None
            return str(version) if version is not None else None
    return None


def proposed_base_link(profile: IdentityProfile) -> Optional[ProposedBaseLink]:
    """The base link an UNANCHORED profile asks for, or ``None``.

    Its digest is the held base template's (sha256 of the shipped template's
    bytes, the checksum the template manifest records for it): the ``d0`` the
    profile check derives. A held identity that is no shipped template has no
    base to propose.
    """
    if profile.status is not IdentityProfileStatus.UNANCHORED or not profile.template:
        return None
    return ProposedBaseLink(
        template_name=profile.template,
        template_version=_template_manifest_version(),
        manifest_digest=_bare_hex(profile.base_digest),
    )


async def request_base_link(proposal: ProposedBaseLink) -> Optional[str]:
    """Ask the registered opener for the base-link deferral; its id, or ``None``. Never raises."""
    opener = _base_link_opener
    if opener is None:
        _base_link_requested.discard(proposal.manifest_digest)
        return None
    try:
        deferral_id = await opener(proposal)
    except Exception as exc:  # noqa: BLE001 - asking must never take identity loading down
        logger.warning(f"identity profile: could not open the base-link deferral ({type(exc).__name__}: {exc})")
        _base_link_requested.discard(proposal.manifest_digest)
        return None
    if deferral_id:
        logger.warning(
            "identity profile unanchored: base-link deferral %s asks a Wise Authority to approve template %s (%s)",
            deferral_id,
            proposal.template_name,
            proposal.manifest_digest,
        )
    return deferral_id


def maybe_open_base_link(profile: IdentityProfile) -> None:
    """When the profile is unanchored, open ONE base-link deferral (in the background, once per process).

    Idempotent twice over: this process asks once per digest, and the opener
    re-uses a pending base-link deferral instead of opening another.
    """
    proposal = proposed_base_link(profile)
    if proposal is None or _base_link_opener is None or proposal.manifest_digest in _base_link_requested:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _base_link_requested.add(proposal.manifest_digest)

    async def _run() -> None:
        await request_base_link(proposal)

    task = loop.create_task(_run())
    _base_link_tasks.add(task)
    task.add_done_callback(_base_link_tasks.discard)


# ------------------------------------------------------------ the chain's head


#: Why a text amendment has no link to follow (rc21 section 3): the profile is not anchored and verified.
REASON_NO_CHAIN_HEAD = "identity_amendment.no_chain_head"

#: The newest link THIS process appended since the last profile check, so two
#: amendments applied between checks chain on each other instead of forking.
_appended_head: Optional[str] = None


def chain_head_row_id() -> Tuple[Optional[str], str]:
    """The row id a new text amendment names as ``refs.prev``, or ``(None, why)``.

    The head is the last counted link of a VERIFIED profile (the base link when
    no amendment follows it yet). Any other standing has no head to extend: an
    unanchored profile has no base, a mismatched or contested one would fork.
    Nothing is written then; the caller says why.
    """
    profile = _latest_profile
    if profile is None:
        return None, f"{REASON_NO_CHAIN_HEAD} (identity profile not yet checked)"
    if profile.status is not IdentityProfileStatus.VERIFIED:
        return None, f"{REASON_NO_CHAIN_HEAD} ({profile.reason})"
    head = _appended_head or (profile.chain_row_ids[-1] if profile.chain_row_ids else profile.base_row_id)
    if not head:
        return None, f"{REASON_NO_CHAIN_HEAD} (verified profile names no base row)"
    return head, ""


def note_chain_link(row_id: str) -> None:
    """Record the link this process just appended: the next amendment follows it."""
    global _appended_head
    _appended_head = row_id


def _settle_appended_head(profile: IdentityProfile) -> None:
    """Forget the appended head once a profile check counts it (the check is then the source)."""
    global _appended_head
    if _appended_head is not None and _appended_head in profile.chain_row_ids:
        _appended_head = None


# ------------------------------------------------------------- re-approval


#: The M-1 justification a re-approval deferral carries. Engine-authored: the amendment's text is not the agent's
#: new proposal but text a Wise Authority approved before exact-text binding, offered back unchanged.
REAPPROVAL_M1_JUSTIFICATION = (
    "Meta-Goal M-1 (Adaptive Coherence): this amendment is already part of how the agent describes itself, but it "
    "was approved before approvals bound exact text, so it no longer counts. Re-approving these exact bytes keeps "
    "the agent's identity continuous and accountable to its Wise Authority; declining removes it from authority."
)

#: Opens one re-approval deferral: the Wise Authority service registers it at start.
ReapprovalOpener = Callable[["IdentityChangeProposal"], Awaitable[Optional[str]]]
_reapproval_opener: Optional[ReapprovalOpener] = None
#: Amendment node ids this process already asked to re-approve.
_reapproval_requested: Set[str] = set()


def set_reapproval_opener(opener: Optional[ReapprovalOpener]) -> None:
    """Register (or clear) what opens a re-approval deferral. The Wise Authority service, at start/stop."""
    global _reapproval_opener
    _reapproval_opener = opener


def amendments_needing_reapproval(per_row: Sequence[IdentityAmendment]) -> List[IdentityAmendment]:
    """Held text amendments that can never count as they stand: re-approve each by its exact bytes.

    ``per_row`` is each amendment checked against its own signed rows
    (``load_identity_amendments``). One needs re-approval when it did not
    verify (approved before exact-text binding, or its rows are not held), or
    when it verified but names no ``prev`` (written before the profile chain),
    so it can never join the chain. Skipped when a verified chained amendment
    already holds the same text: it was re-approved.
    """
    rechained = {a.content for a in per_row if not a.base and a.verified and a.amendment_row_prev}
    return [
        a
        for a in per_row
        if not a.base and a.content and (not a.verified or not a.amendment_row_prev) and a.content not in rechained
    ]


def reapproval_proposal(amendment: IdentityAmendment) -> "IdentityChangeProposal":
    """The re-approval deferral's proposal: the held text unchanged, with its M-1 justification."""
    from ciris_engine.schemas.api.wa import IdentityChangeKind, IdentityChangeProposal

    return IdentityChangeProposal(
        kind=IdentityChangeKind.REAPPROVAL,
        summary=(
            f"Re-approve identity amendment {amendment.node_id} (approved by {amendment.wa_id or 'unknown'} "
            "before exact-text binding) by its exact text; until then it does not apply."
        ),
        proposed_text=amendment.content,
        m1_justification=REAPPROVAL_M1_JUSTIFICATION,
        supersedes_node_id=amendment.node_id,
    )


def maybe_open_reapprovals(per_row: Sequence[IdentityAmendment], profile: IdentityProfile) -> None:
    """Open ONE re-approval deferral per held amendment that cannot count (in the background, once per process).

    Only once the profile is anchored and verified: a re-approved amendment is
    written as a link naming the chain's head, so before the base link is
    approved it would have nothing to follow. Idempotent: this process asks once
    per amendment, and the opener re-uses a pending re-approval of the same node.
    """
    if _reapproval_opener is None or profile.status is not IdentityProfileStatus.VERIFIED:
        return
    pending = [a for a in amendments_needing_reapproval(per_row) if a.node_id not in _reapproval_requested]
    if not pending:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    opener = _reapproval_opener
    for amendment in pending:
        _reapproval_requested.add(amendment.node_id)
        proposal = reapproval_proposal(amendment)

        async def _run(p: "IdentityChangeProposal" = proposal, node_id: str = amendment.node_id) -> None:
            try:
                deferral_id = await opener(p)
            except Exception as exc:  # noqa: BLE001 - asking must never take identity loading down
                logger.warning(f"identity profile: could not open the re-approval of {node_id} ({type(exc).__name__}: {exc})")
                _reapproval_requested.discard(node_id)
                return
            if deferral_id:
                logger.warning("identity amendment %s awaits re-approval by exact text: deferral %s", node_id, deferral_id)

        task = loop.create_task(_run())
        _base_link_tasks.add(task)
        task.add_done_callback(_base_link_tasks.discard)


def reset_base_link_state() -> None:
    """For tests and runtime teardown."""
    global _latest_profile, _appended_head
    _latest_profile = None
    _appended_head = None
    _base_link_requested.clear()
    _reapproval_requested.clear()


__all__ = [
    "BaseLinkOpener",
    "IdentityBase",
    "PROFILE_DIGEST_DOMAIN",
    "ProfileChain",
    "build_chain",
    "cde_encode",
    "check_identity_profile",
    "encode_profile",
    "expected_profile_digest",
    "held_base_digest",
    "latest_identity_profile",
    "load_identity_profile",
    "amendments_needing_reapproval",
    "chain_head_row_id",
    "maybe_open_base_link",
    "maybe_open_reapprovals",
    "note_chain_link",
    "reapproval_proposal",
    "set_reapproval_opener",
    "proposed_base_link",
    "request_base_link",
    "reset_base_link_state",
    "set_base_link_opener",
    "profile_digest",
    "shipped_template_verified",
    "verified_template_manifest",
]
