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
  scopes_json (string), token_type, created_at (`created`), last_auth
  (`last_login`).

Part of CIRISAgent#763 — eliminating dual-libsqlite WAL contention
documented in CIRISPersist#58.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, cast

from ciris_engine.schemas.services.authority_core import OAuthIdentityLink, WACertificate

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


def _coerce_scopes_json(value: Any) -> str:
    """Persist returns `scopes` as a JSON string; tolerate already-decoded lists too."""
    if value is None:
        return "[]"
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return json.dumps(value)
    return "[]"


def _coerce_optional_json_string(value: Any) -> Optional[str]:
    """Coerce a dict/list/str value into a JSON string for legacy *_json fields."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value)


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
    legacy fields if present.
    """
    wa_dict = wa.model_dump(mode="json")

    payload: Dict[str, Any] = {
        "wa_id": wa_dict["wa_id"],
        "name": wa_dict["name"],
        "role": wa_dict["role"],
        "pubkey": wa_dict["pubkey"],
        "jwt_kid": wa_dict["jwt_kid"],
        "scopes": wa_dict.get("scopes_json") or "[]",
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

    # token_type defaults to "standard" in persist; pass through if set.
    if wa_dict.get("token_type"):
        payload["token_type"] = wa_dict["token_type"]

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


def store_wa_certificate(wa: WACertificate, db_path: str) -> None:
    """Store a WA certificate via persist `wa_cert_upsert`.

    `db_path` retained for signature compat; persist is single-engine per process.

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


def get_wa_by_id(wa_id: str, db_path: str) -> Optional[WACertificate]:
    """Get an active WA certificate by ID."""
    row = _active_or_none(_parse_persist_payload(_get_engine().wa_cert_get(wa_id)))
    return _row_to_wa(row) if row else None


def get_wa_by_kid(jwt_kid: str, db_path: str) -> Optional[WACertificate]:
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


def get_wa_by_oauth(provider: str, external_id: str, db_path: str) -> Optional[WACertificate]:
    """Get an active WA certificate by OAuth identity (primary + linked fallback)."""
    engine = _get_engine()
    raw = engine.wa_cert_get_by_oauth(provider, external_id)
    row = _active_or_none(_parse_persist_payload(raw))
    if row is not None:
        return _row_to_wa(row)

    # Fallback: search linked OAuth identities across all active certs.
    for role in ("root", "authority", "observer"):
        for cand in _list_active_by_role(role):
            wa = _row_to_wa(cand)
            for link in wa.oauth_links:
                if link.provider == provider and link.external_id == external_id:
                    return wa
    return None


def get_wa_by_adapter(adapter_id: str, db_path: str) -> Optional[WACertificate]:
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


def update_wa_certificate(wa_id: str, updates: Dict[str, Any], db_path: str) -> None:
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
        iso = val.isoformat() if isinstance(val, datetime) else (str(val) if val is not None else None)
        if iso is not None:
            engine.wa_cert_update_last_login(wa_id, iso)
        return

    # Multi-field or non-focused — read-modify-upsert.
    raw = engine.wa_cert_get(wa_id)
    row = _parse_persist_payload(raw)
    if row is None:
        logger.warning("update_wa_certificate: wa_id %s not found", wa_id)
        return

    # Apply updates to the persist-shape row in place.
    for k, v in updates.items():
        if k in ("created_at", "created"):
            iso = v.isoformat() if isinstance(v, datetime) else (str(v) if v is not None else None)
            if iso is not None:
                row["created"] = iso
            continue
        if k in ("last_auth", "last_login"):
            iso = v.isoformat() if isinstance(v, datetime) else (str(v) if v is not None else None)
            if iso is not None:
                row["last_login"] = iso
            continue
        if k == "active":
            row["active"] = _coerce_bool_update_value(v)
            continue
        if k == "scopes_json":
            row["scopes"] = str(v) if v is not None else "[]"
            continue
        if k == "scopes":
            row["scopes"] = _coerce_scopes_json(v)
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

    engine.wa_cert_upsert(json.dumps(row))


def list_wa_certificates(active_only: bool, db_path: str) -> List[WACertificate]:
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
    return [_row_to_wa(r) for r in rows]


def get_certificate_counts(db_path: str) -> Dict[str, int]:
    """Get counts of certificates by status and role.

    Persist doesn't expose inactive listings; the `revoked` count is reported
    as 0 and `total` reflects active-only. Tests that assert on `revoked`
    counts will need a behavior change post-A1.
    """
    counts: Dict[str, Any] = {"total": 0, "active": 0, "revoked": 0, "by_role": cast(Dict[str, int], {})}

    try:
        active_rows: List[Dict[str, Any]] = []
        for role in ("root", "authority", "observer"):
            role_rows = _list_active_by_role(role)
            counts["by_role"][role] = len(role_rows)
            active_rows.extend(role_rows)

        counts["active"] = len(active_rows)
        counts["total"] = len(active_rows)
    except Exception as e:
        logger.warning("Failed to get certificate counts: %s", e)

    return counts


def check_database_health(db_path: str) -> bool:
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
