"""Authentication Store - WA-certificate persistence via ciris-persist.

This module exposes the same public surface that the authentication
service has always called — `init_auth_database`, `store_wa_certificate`,
`get_wa_by_id`, `get_wa_by_kid`, `get_wa_by_oauth`, `get_wa_by_adapter`,
`update_wa_certificate`, `list_wa_certificates`, `get_certificate_counts`,
`check_database_health` — but reroutes all I/O through ciris-persist's
`wa_cert_*` substrate (v1.5.19) instead of raw sqlite3 against the legacy
`wa_cert` table.

Auth path is hot and unforgiving — the agent reads `wa_cert` rows
synchronously during every JWT verification. The migration preserves
field round-tripping for every column the service depends on:
  password_hash, api_key_hash, oauth_provider/external_id, oauth_links,
  custom_permissions, adapter_id/name/metadata, veilid_id, parent_signature,
  scopes (JSON array), created_at (`created`), last_auth (`last_login`).

`token_type` is deliberately NOT round-tripped — see `_wa_to_persist_payload`.

Part of CIRISAgent#763 — eliminating dual-libsqlite WAL contention
documented in CIRISPersist#58.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, cast

from ciris_engine.schemas.services.authority_core import OAuthIdentityLink, TokenType, WACertificate

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Engine accessor                                                             #
# --------------------------------------------------------------------------- #


def _get_engine() -> Any:
    """Return the wired persist engine; raise if not yet bootstrapped."""
    from ciris_engine.logic.persistence.models.graph import get_persist_engine

    engine = get_persist_engine()
    if engine is None:
        raise RuntimeError(
            "persist engine not initialized — call initialize_database() "
            "before any wa_cert operation"
        )
    return engine


# --------------------------------------------------------------------------- #
# Persist row <-> WACertificate                                               #
# --------------------------------------------------------------------------- #


_PERSIST_OAUTH_LINK_KEYS = {"provider", "external_id", "account_name", "linked_at", "metadata", "is_primary"}


def _iso_or_none(val: Any) -> Optional[str]:
    """Coerce a datetime / ISO string / None to an ISO 8601 string (or None)."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


def _coerce_oauth_links(value: Any) -> List[OAuthIdentityLink]:
    """Coerce persist's `oauth_links` list (or legacy JSON string) into pydantic models."""
    if not value:
        return []
    parsed: Any = value
    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except json.JSONDecodeError as e:
            logger.warning("Invalid oauth_links payload: %s", e)
            return []
    if not isinstance(parsed, list):
        return []

    out: List[OAuthIdentityLink] = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        # Defensive: only pass known keys.
        scrubbed = {k: v for k, v in entry.items() if k in _PERSIST_OAUTH_LINK_KEYS}
        try:
            out.append(OAuthIdentityLink(**scrubbed))
        except Exception as e:
            logger.warning("Invalid OAuth link entry skipped: %s", e)
    return out


# Bound on how many times a `scopes` value may be JSON-decoded while unwrapping
# historical double-encoding. One level is the legacy shape and two is a legacy
# row re-upserted; the third is slack. The bound exists so a pathological value
# can never spin.
_MAX_SCOPES_UNWRAP = 3

# Persist's `token_type` column is a closed set — a Rust enum behind a CHECK
# constraint. It is NOT the same set as the agent's own `TokenType`
# (standard | channel | oauth): persist has no `channel`, the agent has no
# session/api_key/service. Anything outside this set makes `wa_cert_upsert`
# raise `ValueError: WaCert decode: unknown variant ...` before the row is
# written.
_PERSIST_TOKEN_TYPES = frozenset({"standard", "session", "api_key", "oauth", "service"})
_DEFAULT_TOKEN_TYPE = "standard"


def _scopes_to_persist(value: Any) -> List[str]:
    """Decode a legacy `scopes_json` string into the LIST persist's `scopes` wants.

    Persist types `scopes` as a free-form JSON value and stores it verbatim.
    Handing it the legacy JSON *string* `'["read:any"]'` therefore stores the
    JSON encoding OF that string — `"[\\"read:any\\"]"` — a JSON string holding
    a JSON array, not an array. Every `cirislens_wa_cert` row written before
    this fix carries that shape, so any consumer reading the column directly
    (persist itself, the node, plain SQL) sees a string where the schema
    promises a list.

    Unwrap defensively: `value` may already be a list, a JSON string (the
    legacy shape), or a doubly-wrapped string (a legacy row read back and
    re-upserted through `update_wa_certificate`). Anything that does not
    resolve to a list yields `[]` — least privilege — with a warning, since
    scopes drive authorization and a garbled value must not widen access.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        # Absent, not garbled — the pre-fix code coerced this to "[]" too.
        return []

    decoded: Any = value
    for _ in range(_MAX_SCOPES_UNWRAP):
        if not isinstance(decoded, str):
            break
        try:
            decoded = json.loads(decoded)
        except json.JSONDecodeError:
            break

    if isinstance(decoded, list):
        return [str(scope) for scope in decoded]
    if decoded is None:
        return []
    # Log the SHAPE, never the content. This value comes off the wa_cert row,
    # which CodeQL correctly treats as carrying credential material
    # (py/clear-text-logging-sensitive-data) — and a scopes column that failed to
    # decode is exactly the case where its bytes are least trustworthy. Type and
    # length identify the defect ("a dict arrived", "an 8KB blob arrived")
    # without copying unknown row bytes into the log.
    logger.warning(
        "wa_cert scopes did not decode to a list (type=%s, len=%d) — storing an "
        "empty scope set",
        type(value).__name__,
        len(str(value)),
    )
    return []


def _coerce_scopes_json(value: Any) -> str:
    """Normalize persist's `scopes` into WACertificate's legacy `scopes_json` string.

    Tolerates BOTH storage shapes on purpose, and permanently:
      * a JSON *array*  — what `_scopes_to_persist` writes from now on
      * a JSON *string* — every row written before that fix landed

    Rows in the wild are the second shape, so this is not a transitional
    branch that can be removed once writers are updated; existing agents keep
    their double-encoded rows until something happens to rewrite them.
    """
    if value is None:
        return "[]"
    if isinstance(value, list):
        return json.dumps(value)
    if isinstance(value, str):
        # The legacy double-encoded row: the string already IS the
        # `scopes_json` WACertificate wants — but only if it parses.
        # WACertificate validates scopes_json as JSON, and a non-JSON string
        # would raise there and take down every enumeration that touches the
        # row (the same blast radius as the #922 node-owner rows).
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            logger.warning(
                "wa_cert scopes %r is not valid JSON — treating as an empty scope set",
                value[:200],
            )
            return "[]"
        if isinstance(decoded, list):
            return value
        # Wrapped deeper than one level — unwrap fully rather than hand
        # WACertificate a scopes_json whose `.scopes` property yields a str.
        return json.dumps(_scopes_to_persist(decoded))
    return "[]"


def _coerce_token_type(value: Any) -> str:
    """Map an incoming token_type onto persist's closed variant set.

    `update_wa_certificate` forwards unrecognized keys straight onto the
    persist row, so `{"token_type": ...}` reaches `wa_cert_upsert` verbatim.
    The agent's own `TokenType.CHANNEL` is exactly a value persist rejects, so
    without this the update would surface as an unhandled `ValueError` out of
    the auth store rather than a write.

    The mapping is deliberate, not a silent default: `channel` is the case the
    agent re-derives from `adapter_id` at verification time (see
    `authentication/service.py`), so collapsing it to `standard` loses nothing
    the agent consults — and it says so in the log.
    """
    if value is None:
        return _DEFAULT_TOKEN_TYPE
    text = value.value if isinstance(value, Enum) else str(value)
    if text in _PERSIST_TOKEN_TYPES:
        return text
    # Report WHICH known variant this is by comparison against a fixed set,
    # rather than echoing the value. `agent_variant` is a bool derived from a
    # constant comparison, so it carries no row bytes — and it answers the only
    # question an operator actually has here: "is this our TokenType.CHANNEL
    # (expected, handled) or something nobody recognises (worth investigating)?"
    agent_variant = text in {member.value for member in TokenType}
    logger.warning(
        "wa_cert token_type rejected (known agent variant: %s, len=%d) — not one "
        "of %s; storing %r instead. The agent derives TokenType from "
        "adapter_id/oauth_provider at verification time, so the stored column "
        "is advisory.",
        agent_variant,
        len(text),
        sorted(_PERSIST_TOKEN_TYPES),
        _DEFAULT_TOKEN_TYPE,
    )
    return _DEFAULT_TOKEN_TYPE


def _coerce_optional_json_string(value: Any) -> Optional[str]:
    """Coerce a dict/list/str value into a JSON string for legacy *_json fields."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value)


# Classic Wise-Authority id shape (wa-YYYY-MM-DD-XXXXXX) — the ONLY shape
# WACertificate.wa_id accepts (authority_core.py). The shared persist wa_cert
# store can ALSO hold the local node's *owner* WA, minted by the substrate's
# node self-claim (ciris-server /v1/setup/claim-remote) in a fed-ID-rooted
# shape (e.g. "wa-root-<label>-<suffix>"). That row is a federation ownership
# identity — a different identity kind, not a brain WACertificate — and does
# not satisfy this pattern (nor necessarily the other WACertificate field
# constraints). Materializing it as a WACertificate raises a pydantic
# validation error that would take down EVERY brain WA enumeration (list_was,
# OAuth fallback scan, counts) with a 500. We recognize and skip those rows so
# the brain's WA world stays exactly what it was before node self-claim began
# writing owner rows to the shared store (CIRISAgent#922). The classic path is
# unaffected: a fresh unclaimed node has no such rows, so nothing is skipped.
_CLASSIC_WA_ID_RE = re.compile(r"^wa-\d{4}-\d{2}-\d{2}-[A-Z0-9]{6}$")


def _is_brain_wa_row(row: Dict[str, Any]) -> bool:
    """True if a persist row is a classic brain WACertificate (not a node-owner row).

    Non-classic rows are substrate-owned federation identities; skip them so
    the brain does not choke trying to build a WACertificate it cannot
    represent. `%r` (repr) escapes newlines/CR/tabs in the federation-
    controlled wa_id so a crafted id can't inject log lines (CWE-117 /
    Sonar S5145), matching the existing pattern in update_wa_certificate().
    """
    wa_id = row.get("wa_id")
    if isinstance(wa_id, str) and _CLASSIC_WA_ID_RE.match(wa_id):
        return True
    logger.debug(
        "authentication_store: skipping non-classic WA row wa_id=%r — "
        "substrate/node-owner federation identity, not a brain WACertificate",
        wa_id,
    )
    return False


def _row_to_wa(row: Dict[str, Any]) -> WACertificate:
    """Materialize a persist `wa_cert_get`/`wa_cert_list_by_role` row into a WACertificate."""
    oauth_links = _coerce_oauth_links(row.get("oauth_links"))
    scopes_json = _coerce_scopes_json(row.get("scopes"))
    custom_permissions_json = _coerce_optional_json_string(row.get("custom_permissions"))
    adapter_metadata_json = _coerce_optional_json_string(row.get("adapter_metadata"))

    return WACertificate(
        wa_id=row["wa_id"],
        name=row["name"],
        role=row["role"],
        pubkey=row["pubkey"],
        jwt_kid=row["jwt_kid"],
        password_hash=row.get("password_hash"),
        api_key_hash=row.get("api_key_hash"),
        oauth_provider=row.get("oauth_provider"),
        oauth_external_id=row.get("oauth_external_id"),
        oauth_links=oauth_links,
        auto_minted=bool(row.get("auto_minted", False)),
        veilid_id=row.get("veilid_id"),
        parent_wa_id=row.get("parent_wa_id"),
        parent_signature=row.get("parent_signature"),
        scopes_json=scopes_json,
        custom_permissions_json=custom_permissions_json,
        adapter_id=row.get("adapter_id"),
        adapter_name=row.get("adapter_name"),
        adapter_metadata_json=adapter_metadata_json,
        created_at=cast(Any, row["created"]),
        last_auth=cast(Any, row.get("last_login")),
    )


def _wa_to_persist_payload(wa: WACertificate) -> Dict[str, Any]:
    """Convert a WACertificate into a persist `wa_cert_upsert` payload.

    Persist accepts oauth_links/custom_permissions/adapter_metadata as nested
    types, not the legacy `_json` strings; we re-hydrate those from the
    legacy fields if present. `scopes` is the same story: persist wants the
    decoded array, not WACertificate's `scopes_json` string (see
    `_scopes_to_persist`).
    """
    wa_dict = wa.model_dump(mode="json")

    payload: Dict[str, Any] = {
        "wa_id": wa_dict["wa_id"],
        "name": wa_dict["name"],
        "role": wa_dict["role"],
        "pubkey": wa_dict["pubkey"],
        "jwt_kid": wa_dict["jwt_kid"],
        "scopes": _scopes_to_persist(wa_dict.get("scopes_json")),
        "active": True,  # store_wa_certificate is always an INSERT path; new WAs are active
        "auto_minted": bool(wa_dict.get("auto_minted", False)),
    }

    # Required `created` ISO string
    created_value = wa_dict.get("created_at")
    if isinstance(created_value, datetime):
        payload["created"] = created_value.isoformat()
    elif created_value is not None:
        payload["created"] = str(created_value)

    # last_login (a.k.a. last_auth in WACertificate)
    last_auth = wa_dict.get("last_auth")
    if isinstance(last_auth, datetime):
        payload["last_login"] = last_auth.isoformat()
    elif last_auth is not None:
        payload["last_login"] = str(last_auth)

    # token_type is pinned, NOT passed through from the certificate — three
    # independent reasons, all of which have to hold for a passthrough to be
    # correct, and none of which do:
    #
    #  1. There is nothing to pass through. `WACertificate` has no
    #     `token_type` field and is `extra="forbid"`, so `wa_dict` can never
    #     carry one. The predecessor of this line (`if wa_dict.get(
    #     "token_type")`) was unreachable and only made the write path *look*
    #     like it preserved a value it had never seen.
    #  2. Nothing reads the column back. The agent derives `TokenType` at
    #     verification time from `adapter_id` / `oauth_provider` (see
    #     `authentication/service.py`), so a stored copy would be a second
    #     source of truth for a fact that is already computed.
    #  3. The two enums are incompatible. The agent's `TokenType` admits
    #     `channel`, which persist rejects outright — promoting it to a stored
    #     field would turn today's silent no-op into a hard write failure on
    #     the auth path.
    #
    # Set explicitly rather than relying on persist's column default so the
    # stored value is a decision this code made, and so a persist-side default
    # change cannot move it underneath us.
    payload["token_type"] = _DEFAULT_TOKEN_TYPE

    # Optional scalar fields — only set if not None to keep payload minimal.
    for k in (
        "password_hash",
        "api_key_hash",
        "oauth_provider",
        "oauth_external_id",
        "veilid_id",
        "parent_wa_id",
        "parent_signature",
        "adapter_id",
        "adapter_name",
    ):
        if wa_dict.get(k):
            payload[k] = wa_dict[k]

    # oauth_links: list of dicts (persist stores nested)
    oauth_links = wa_dict.get("oauth_links") or []
    if oauth_links:
        payload["oauth_links"] = oauth_links

    # custom_permissions: list of strings; legacy stored as JSON-string column
    cust_perm_json = wa_dict.get("custom_permissions_json")
    if cust_perm_json:
        try:
            payload["custom_permissions"] = json.loads(cust_perm_json) if isinstance(cust_perm_json, str) else cust_perm_json
        except json.JSONDecodeError as e:
            logger.warning("Invalid custom_permissions_json for %s: %s", wa.wa_id, e)

    # adapter_metadata: dict; legacy stored as JSON-string column
    adapter_meta_json = wa_dict.get("adapter_metadata_json")
    if adapter_meta_json:
        try:
            payload["adapter_metadata"] = (
                json.loads(adapter_meta_json) if isinstance(adapter_meta_json, str) else adapter_meta_json
            )
        except json.JSONDecodeError as e:
            logger.warning("Invalid adapter_metadata_json for %s: %s", wa.wa_id, e)

    return payload


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #


def init_auth_database(db_path: str) -> None:
    """Initialize authentication database tables if needed.

    Routes through `initialize_database` (which wires persist for the path)
    instead of raw schema-DDL against the legacy table. The legacy
    `wa_cert` table will still be created as a side effect of the agent's
    full schema migration so postgres-mode dialect adapters that touch
    legacy SQL (e.g., during gradual migration) continue to work; the
    authoritative writes go through persist's `cirislens_wa_cert`.
    """
    from ciris_engine.logic.persistence.db.core import initialize_database

    initialize_database(db_path)


def store_wa_certificate(wa: WACertificate) -> None:
    """Store a WA certificate via persist `wa_cert_upsert`.

    INSERT-only semantics: persist's substrate is upsert, but every caller of
    this function is creating a brand-new WA (observer, system_wa, root_wa,
    new admin). Silently overwriting an existing wa_id would let an
    accidental duplicate-create reset the password — see
    `tests/test_password_persistence_comprehensive::test_default_admin_no_accidental_reset`.
    Guard with an explicit pre-existence check.
    """
    engine = _get_engine()
    if engine.wa_cert_get(wa.wa_id) is not None:
        raise ValueError(
            f"WA certificate {wa.wa_id} already exists; refusing to overwrite "
            f"via store_wa_certificate. Use the explicit update path if a "
            f"mutation is intended."
        )
    payload = _wa_to_persist_payload(wa)
    engine.wa_cert_upsert(json.dumps(payload))


def _parse_persist_payload(raw: Any) -> Optional[Dict[str, Any]]:
    """Decode the JSON-string payload persist's `wa_cert_*` accessors return."""
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("Invalid wa_cert payload from persist: %s", e)
            return None
        return obj if isinstance(obj, dict) else None
    if isinstance(raw, dict):
        return raw
    return None


def _active_or_none(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Mirror legacy `WHERE active = 1` semantics on point-lookups."""
    if row is None:
        return None
    if not bool(row.get("active", True)):
        return None
    return row


def get_wa_by_id(wa_id: str) -> Optional[WACertificate]:
    """Get an active WA certificate by ID."""
    row = _active_or_none(_parse_persist_payload(_get_engine().wa_cert_get(wa_id)))
    return _row_to_wa(row) if row else None


def get_wa_by_kid(jwt_kid: str) -> Optional[WACertificate]:
    """Get an active WA certificate by JWT key ID (hot path on every token verification)."""
    row = _active_or_none(_parse_persist_payload(_get_engine().wa_cert_get_by_kid(jwt_kid)))
    return _row_to_wa(row) if row else None


def _list_active_by_role(role: str, limit: int = 1000) -> List[Dict[str, Any]]:
    """Persist's `wa_cert_list_by_role` already filters active=true."""
    raw = _get_engine().wa_cert_list_by_role(role, limit)
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return []
    else:
        obj = raw
    if not isinstance(obj, list):
        return []
    return [r for r in obj if isinstance(r, dict)]


#: A minted WA id — ``wa-YYYY-MM-DD-XXXXXX``. Mirrors WACertificate.wa_id's
#: own pattern (schemas/services/authority_core.py). The OAuth browser-handoff
#: flow can leave a PROVISIONAL wa_cert row keyed by (provider, external_id)
#: whose wa_id is the OAuth placeholder ``oauth-<provider>-<sub>`` — which is not
#: a minted certificate and does NOT satisfy this pattern (#1098).
_MINTED_WA_ID = re.compile(r"^wa-\d{4}-\d{2}-\d{2}-[A-Z0-9]{6}$")


def _row_to_wa_or_none(row: Dict[str, Any]) -> Optional[WACertificate]:
    """Materialize a row into a WACertificate, or None if it is not a minted WA.

    A provisional OAuth-placeholder row (``wa_id='oauth-<provider>-<sub>'``) is
    not a certificate; constructing a WACertificate from it raises on the
    wa_id pattern and 500s completeSetup, looping the wizard (#1098). Treat such
    a row as absent so callers fall through to the real linked WA — or create
    and link one — instead of crashing.
    """
    wa_id = row.get("wa_id")
    if not isinstance(wa_id, str) or not _MINTED_WA_ID.match(wa_id):
        return None
    return _row_to_wa(row)


#: The provisional OAuth placeholder the substrate parks a browser hand-off as,
#: before any certificate is minted: ``oauth-<provider>-<subject>``.
_OAUTH_PLACEHOLDER_WA_ID = re.compile(r"^oauth-[A-Za-z0-9]+-.+$")


def fabric_oauth_holder_id(provider: str, external_id: str) -> Optional[str]:
    """wa_id of an ACTIVE cert the SUBSTRATE already bound to this identity.

    Returns None when the holder is one of ours (``wa-YYYY-MM-DD-XXXXXX``), the
    provisional ``oauth-<provider>-<sub>`` placeholder, or absent.

    WHY THIS IS NOT `get_wa_by_oauth`. That returns a `WACertificate`, and
    `WACertificate.wa_id` carries a hard pattern of OUR minting convention
    (`authority_core.py`). The substrate mints `wa-root-<user>` during
    claim-remote, which cannot be constructed as a WACertificate at all — so
    `get_wa_by_oauth` reports None for an identity that is very much taken, and
    setup concludes it must mint one.

    That is what locked a real first-run out (2026-08-31): claim-remote bound
    `google:…` to `wa-root-mooreericnyc-…`, setup could not see it, minted a
    second ROOT, and the substrate then refused every later sign-in with
    `AMBIGUOUS provider identity … holders=2`. Google failed on the ambiguity and
    local failed because an OAuth user has no password — a closed door on both
    sides.

    So this answers the question WITHOUT materializing: is the identity already
    spoken for by the fabric? The agent must not author a second claim on an
    identity the fabric has already bound (CC 3.4.7.3; agent surfaces, fabric
    produces).
    """
    engine = _get_engine()
    raw = engine.wa_cert_get_by_oauth(provider, external_id)
    row = _active_or_none(_parse_persist_payload(raw))
    if not isinstance(row, dict):
        return None
    wa_id = row.get("wa_id")
    if not isinstance(wa_id, str) or not wa_id:
        return None
    if _MINTED_WA_ID.match(wa_id):
        return None  # ours — the normal path already handles it
    if _OAUTH_PLACEHOLDER_WA_ID.match(wa_id):
        return None  # provisional — retired after we mint+link
    return wa_id


def get_wa_by_oauth(provider: str, external_id: str) -> Optional[WACertificate]:
    """Get an active WA certificate by OAuth identity (primary + linked fallback)."""
    engine = _get_engine()
    raw = engine.wa_cert_get_by_oauth(provider, external_id)
    row = _active_or_none(_parse_persist_payload(raw))
    if row is not None:
        wa = _row_to_wa_or_none(row)
        if wa is not None:
            return wa
        # Provisional OAuth-placeholder row — not a minted WA. Fall through to
        # the linked-identity search below (and, ultimately, None → mint one).

    # Fallback: search linked OAuth identities across all active certs.
    for role in ("root", "authority", "observer"):
        for cand in _list_active_by_role(role):
            if not _is_brain_wa_row(cand):
                continue
            wa = _row_to_wa(cand)
            for link in wa.oauth_links:
                if link.provider == provider and link.external_id == external_id:
                    return wa
    return None


def provisional_oauth_cert_id(provider: str, external_id: str) -> Optional[str]:
    """Return the id of the substrate's PROVISIONAL OAuth cert, or None.

    WORKAROUND for #1098 — drop once ciris-server mints OAuth WA ids as proper
    ``wa-…`` (server issue). The OAuth browser-handoff parks the session as a
    live wa_cert keyed by (provider, external_id) whose wa_id is the placeholder
    ``oauth-<provider>-<sub>``. Once setup mints+links a real WA for the same
    identity, that placeholder becomes a DUPLICATE and the node refuses the
    ambiguous account. Callers capture this id BEFORE linking (linking can
    repoint the primary oauth index) and deactivate it afterwards via
    ``update_wa_certificate(id, {"active": False})`` — the raw set_active path,
    since materializing the placeholder id would fail the wa_id pattern.
    Returns None when the primary row is already a minted WA or absent.
    """
    engine = _get_engine()
    raw = engine.wa_cert_get_by_oauth(provider, external_id)
    row = _parse_persist_payload(raw)
    if not isinstance(row, dict):
        return None
    wa_id = row.get("wa_id")
    if isinstance(wa_id, str) and wa_id and not _MINTED_WA_ID.match(wa_id):
        return wa_id
    return None


def get_wa_by_adapter(adapter_id: str) -> Optional[WACertificate]:
    """Get an active WA certificate by adapter_id.

    Persist exposes no point-lookup-by-adapter. The set of adapter-tied WAs
    is small (one per long-lived adapter instance), so we scan active certs
    role-by-role and short-circuit on first match. This keeps the legacy
    return-shape contract.
    """
    for role in ("root", "authority", "observer"):
        for cand in _list_active_by_role(role):
            if cand.get("adapter_id") == adapter_id:
                return _row_to_wa(cand)
    return None


def _coerce_bool_update_value(value: Any) -> bool:
    """Accept the legacy update API's str-encoded bools (`'0'`, `'1'`) plus real booleans."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.lower() not in ("0", "false", "no", "")
    return bool(value)


def update_wa_certificate(wa_id: str, updates: Dict[str, Any]) -> None:
    """Update WA certificate fields via persist substrate.

    Handles common single-field updates through the focused substrates
    (set_active, update_last_login) and falls back to read-modify-upsert for
    multi-field mutations or fields not exposed individually.
    """
    if not updates:
        return

    engine = _get_engine()

    # Focused substrates first — these are the common single-field cases.
    if set(updates.keys()) == {"active"}:
        engine.wa_cert_set_active(wa_id, _coerce_bool_update_value(updates["active"]))
        return

    if set(updates.keys()) == {"last_login"} or set(updates.keys()) == {"last_auth"}:
        val = updates.get("last_login", updates.get("last_auth"))
        iso = _iso_or_none(val)
        if iso is not None:
            engine.wa_cert_update_last_login(wa_id, iso)
        return

    # Multi-field or non-focused — read-modify-upsert.
    raw = engine.wa_cert_get(wa_id)
    row = _parse_persist_payload(raw)
    if row is None:
        # %r (repr) escapes newlines / CR / tabs / non-printables in user-
        # controlled wa_id (path-param from PUT /v1/users/{user_id}/permissions
        # — unvalidated FastAPI str) so an attacker can't inject log lines
        # via crafted IDs (CWE-117 / Sonar S5145).
        logger.warning("update_wa_certificate: wa_id %r not found", wa_id)
        return

    # Apply updates to the persist-shape row in place.
    for k, v in updates.items():
        if k in ("created_at", "created"):
            iso = _iso_or_none(v)
            if iso is not None:
                row["created"] = iso
            continue
        if k in ("last_auth", "last_login"):
            iso = _iso_or_none(v)
            if iso is not None:
                row["last_login"] = iso
            continue
        if k == "active":
            row["active"] = _coerce_bool_update_value(v)
            continue
        if k in ("scopes_json", "scopes"):
            # Both spellings arrive here: `scopes_json` from
            # `update_wa(updates=WAUpdate(permissions=[...]))`, `scopes` from
            # direct callers. Persist wants the decoded array either way —
            # assigning the JSON string double-encodes the column exactly the
            # way `store_wa_certificate` used to.
            row["scopes"] = _scopes_to_persist(v)
            continue
        if k == "token_type":
            row["token_type"] = _coerce_token_type(v)
            continue
        if k == "oauth_links_json":
            try:
                row["oauth_links"] = json.loads(v) if isinstance(v, str) and v else []
            except json.JSONDecodeError as e:
                logger.warning("Invalid oauth_links_json on update: %s", e)
            continue
        if k == "custom_permissions_json":
            if v is None:
                row.pop("custom_permissions", None)
            else:
                try:
                    row["custom_permissions"] = json.loads(v) if isinstance(v, str) else v
                except json.JSONDecodeError as e:
                    logger.warning("Invalid custom_permissions_json on update: %s", e)
            continue
        if k == "adapter_metadata_json":
            if v is None:
                row.pop("adapter_metadata", None)
            else:
                try:
                    row["adapter_metadata"] = json.loads(v) if isinstance(v, str) else v
                except json.JSONDecodeError as e:
                    logger.warning("Invalid adapter_metadata_json on update: %s", e)
            continue
        # Default: direct assignment on the persist row (skipped if None to avoid clearing required fields).
        if v is None and k in (
            "name",
            "pubkey",
            "jwt_kid",
            "scopes",
        ):
            continue
        row[k] = v

    # Persist's upsert expects datetime-typed timestamps to already be strings; coerce defensively.
    if isinstance(row.get("created"), datetime):
        row["created"] = row["created"].isoformat()
    if isinstance(row.get("last_login"), datetime):
        row["last_login"] = row["last_login"].isoformat()

    # The row we just read back may predate the scopes fix, in which case
    # `scopes` came out of persist as a JSON *string*. Re-upserting it verbatim
    # would carry the double-encoding forward forever, so normalize on the way
    # out: any write to a legacy row heals its scopes column. Reads already
    # tolerate both shapes (`_coerce_scopes_json`), so this changes storage,
    # never behavior.
    row["scopes"] = _scopes_to_persist(row.get("scopes"))
    row["token_type"] = _coerce_token_type(row.get("token_type"))

    engine.wa_cert_upsert(json.dumps(row))


def list_wa_certificates(active_only: bool) -> List[WACertificate]:
    """List all WA certificates, optionally filtering for active=true.

    Persist exposes only `wa_cert_list_by_role`, which always restricts to
    active=true. To honor `active_only=False` we'd also need to surface
    inactive certs but persist doesn't currently support that. We document
    the divergence and return active-only in both cases — production callers
    only use `active_only=True`.
    """
    if not active_only:
        logger.warning(
            "list_wa_certificates(active_only=False) is unsupported under persist; "
            "returning active-only set (CIRISAgent#763)."
        )

    rows: List[Dict[str, Any]] = []
    for role in ("root", "authority", "observer"):
        rows.extend(_list_active_by_role(role))

    # Sort by `created` DESC to match legacy `ORDER BY created DESC`.
    def _created_key(r: Dict[str, Any]) -> str:
        v = r.get("created", "")
        return v if isinstance(v, str) else str(v)

    rows.sort(key=_created_key, reverse=True)
    return [_row_to_wa(r) for r in rows if _is_brain_wa_row(r)]


def get_certificate_counts() -> Dict[str, int]:
    """Get counts of certificates by status and role.

    Persist doesn't expose inactive listings; the `revoked` count is reported
    as 0 and `total` reflects active-only. Tests that assert on `revoked`
    counts will need a behavior change post-A1.
    """
    counts: Dict[str, Any] = {"total": 0, "active": 0, "revoked": 0, "by_role": cast(Dict[str, int], {})}

    try:
        active_rows: List[Dict[str, Any]] = []
        for role in ("root", "authority", "observer"):
            # Count brain WAs only; substrate/node-owner rows are a different
            # identity kind and are excluded from list_was, so keep the counts
            # consistent with what the brain actually enumerates.
            role_rows = [r for r in _list_active_by_role(role) if _is_brain_wa_row(r)]
            counts["by_role"][role] = len(role_rows)
            active_rows.extend(role_rows)

        counts["active"] = len(active_rows)
        counts["total"] = len(active_rows)
    except Exception as e:
        logger.warning("Failed to get certificate counts: %s", e)

    return counts


def check_database_health() -> bool:
    """Check if the authentication database is accessible via persist.

    Performs a cheap `wa_cert_list_by_role('observer', 1)` round-trip; if
    persist returns without raising, the engine + DB are healthy.
    """
    try:
        _get_engine().wa_cert_list_by_role("observer", 1)
        return True
    except Exception as e:
        logger.warning("Authentication database health check failed: %s", e)
        return False
