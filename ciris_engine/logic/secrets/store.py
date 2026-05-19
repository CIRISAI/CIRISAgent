"""Encrypted secrets storage — routed through ciris-persist 1.6.0 substrate.

2.9.0 Phase 2a (CIRISAgent#763, CIRISPersist#66): every public method now
delegates to persist's `secrets_*` substrate. The agent owns *detection*
(language-aware patterns in `secrets.filter`); persist owns *crypto +
storage + audit log*.

Public API surface preserved: `SecretsStore.store_secret`,
`retrieve_secret`, `delete_secret`, `list_secrets`, `list_all_secrets`,
`encrypt_secret`, `decrypt_secret`, `rotate_master_key`, `test_encryption`,
`get_access_logs`, `reencrypt_all`, `migrate_to_hardware_key`,
`decrypt_secret_value`, `update_access_log`.

`SecretRecord.encrypted_value` / `salt` / `nonce` / `encryption_key_ref`
fields are kept on the dataclass for shape compatibility but populated as
empty bytes / strings — no caller outside this file ever read them
(grep-confirmed in PHASE0_GAP_AUDIT.md). Persist's `secrets_recall_secret`
returns plaintext directly; we never reconstruct ciphertext.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import SensitivityLevel
from ciris_engine.schemas.secrets.core import (
    DetectedSecret,
    SecretRecord,
    SecretReference,
)

from .encryption import KeyStorageMode, SecretsEncryption

logger = logging.getLogger(__name__)

# Default per-sensitivity decapsulation rules (mirrors legacy semantics).
_AUTO_DECAPSULATE_BY_SENSITIVITY: Dict[str, List[str]] = {
    "low": ["speak", "memorize", "tool"],
    "medium": ["speak", "tool"],
    "high": ["tool"],
    "critical": [],
}


def _get_engine() -> Any:
    """Return the wired persist engine; raise if bootstrap hasn't run."""
    from ciris_engine.logic.persistence.models.graph import get_persist_engine

    engine = get_persist_engine()
    if engine is None:
        raise RuntimeError(
            "persist engine not initialized — call initialize_database() "
            "before any secrets operation"
        )
    return engine


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    """Tolerant ISO-8601 → datetime, returning None on bad input."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _ref_to_record(ref: Dict[str, Any]) -> SecretRecord:
    """Build a SecretRecord from a persist `SecretReference` envelope.

    Persist returns only metadata + handle; the agent's SecretRecord
    schema still has crypto-byte fields (legacy contract). Those are
    populated with empty bytes — they are never read off SecretRecord
    by any caller; persist's recall path returns plaintext directly.
    """
    return SecretRecord(
        secret_uuid=str(ref["uuid"]),
        encrypted_value=b"",
        encryption_key_ref="",
        salt=b"",
        nonce=b"",
        description=str(ref.get("description") or ""),
        sensitivity_level=SensitivityLevel(str(ref.get("sensitivity", "medium")).upper()),
        detected_pattern=str(ref.get("detected_pattern") or "unknown"),
        context_hint=str(ref.get("context_hint") or ""),
        created_at=_parse_iso(ref.get("created_at")) or datetime.now(),
        last_accessed=_parse_iso(ref.get("last_accessed")),
        access_count=0,  # Persist tracks access via audit log; not surfaced here.
        source_message_id=ref.get("source_message_id"),
        auto_decapsulate_for_actions=list(ref.get("auto_decapsulate_actions") or []),
        manual_access_only=bool(ref.get("manual_access_only", False)),
    )


def _ref_to_reference(ref: Dict[str, Any]) -> SecretReference:
    """Build a SecretReference for the list endpoints."""
    return SecretReference(
        uuid=str(ref["uuid"]),
        description=str(ref.get("description") or ""),
        context_hint=str(ref.get("context_hint") or ""),
        sensitivity=SensitivityLevel(str(ref.get("sensitivity", "medium")).upper()),
        detected_pattern=str(ref.get("detected_pattern") or "unknown"),
        auto_decapsulate_actions=list(ref.get("auto_decapsulate_actions") or []),
        created_at=_parse_iso(ref.get("created_at")) or datetime.now(),
        last_accessed=_parse_iso(ref.get("last_accessed")),
    )


class SecretsStore:
    """Encrypted storage for secrets — thin persist-substrate wrapper."""

    def __init__(
        self,
        time_service: TimeServiceProtocol,
        db_path: str = "secrets.db",
        master_key: Optional[bytes] = None,
        max_accesses_per_minute: int = 10,
        max_accesses_per_hour: int = 100,
        key_storage_mode: KeyStorageMode | str = "auto",
    ):
        """Initialize secrets store.

        `db_path` and `master_key` retained for signature compat — persist
        owns the database (single Engine per process) and the master key
        is initialized via `secrets_rotate_master_key` if absent. The
        `SecretsEncryption` instance is kept for callers that import it
        directly (deprecated; new code should call the store methods).
        """
        self.time_service = time_service
        # Kept for signature compat; persist owns the underlying file.
        self.db_path: str | Path = db_path if isinstance(db_path, str) else Path(db_path)

        valid_modes: tuple[KeyStorageMode, ...] = ("software", "hardware", "auto")
        if key_storage_mode not in valid_modes:
            logger.warning(
                f"Invalid key_storage_mode '{key_storage_mode}', defaulting to 'auto'"
            )
            validated_mode: KeyStorageMode = "auto"
        else:
            validated_mode = key_storage_mode  # type: ignore[assignment]

        # Legacy encryption instance — kept so external callers that
        # import SecretsEncryption directly keep working. The store's own
        # public methods route through persist.
        self.encryption = SecretsEncryption(master_key, key_storage_mode=validated_mode)
        self.max_accesses_per_minute = max_accesses_per_minute
        self.max_accesses_per_hour = max_accesses_per_hour
        self._access_counts: Dict[str, List[datetime]] = {}
        self._lock = asyncio.Lock()

        # Ensure persist has a master key. Idempotent — persist returns
        # the existing handle if one is set.
        self._ensure_master_key_ready()

    # ------------------------------------------------------------------
    # Boot-time helpers
    # ------------------------------------------------------------------

    def _ensure_master_key_ready(self) -> None:
        """Ensure persist has a master key initialized.

        Persist's substrate raises a `crypto: no active master key` error
        on the first encrypt call if `rotate_master_key` hasn't been run.
        We probe via `secrets_test_encryption`; if it fails, rotate once.
        """
        try:
            engine = _get_engine()
        except RuntimeError:
            # Engine not wired yet (early boot before initialize_database).
            # The first real call will hit _get_engine and surface the issue
            # with the same message.
            return
        try:
            if engine.secrets_test_encryption():
                return
        except Exception:
            # `secrets_test_encryption` raises if no master key exists.
            pass
        try:
            engine.secrets_rotate_master_key(None, "system")
            logger.info("Initialized persist secrets master key")
        except Exception as e:
            logger.warning(f"Failed to initialize persist master key: {type(e).__name__}: {e}")

    # ------------------------------------------------------------------
    # Detected-secret CRUD
    # ------------------------------------------------------------------

    async def store_secret(
        self, secret: DetectedSecret, source_id: Optional[str] = None
    ) -> SecretRecord:
        """Store a detected secret via persist's `secrets_store_detected_secret`.

        Persist owns encryption, audit logging, and the access counter.
        Returns a SecretRecord populated from persist's `SecretReference`
        envelope; crypto-byte fields are empty (no caller reads them).
        """
        async with self._lock:
            engine = _get_engine()
            sensitivity = secret.sensitivity.value if hasattr(secret.sensitivity, "value") else str(secret.sensitivity)
            payload = json.dumps(
                {
                    "secret_uuid": secret.secret_uuid,
                    "value": secret.original_value,
                    "description": secret.description,
                    "sensitivity": sensitivity.lower(),
                    "detected_pattern": secret.pattern_name,
                    "context_hint": secret.context_hint,
                    "source_message_id": source_id,
                    "auto_decapsulate_for_actions": _AUTO_DECAPSULATE_BY_SENSITIVITY.get(
                        sensitivity.lower(), []
                    ),
                    "manual_access_only": False,
                }
            )
            try:
                raw = engine.secrets_store_detected_secret(payload, "system")
                envelope = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
                ref = envelope.get("ref") if isinstance(envelope, dict) else None
                if not isinstance(ref, dict):
                    raise RuntimeError(
                        f"secrets_store_detected_secret envelope missing ref: {envelope!r}"
                    )
                logger.info(f"Stored encrypted secret {ref['uuid']}")
                return _ref_to_record(ref)
            except Exception as e:
                logger.error(
                    f"Failed to store secret {secret.secret_uuid}: {type(e).__name__}"
                )
                logger.debug(f"Secret storage error details: {e}")
                raise

    async def retrieve_secret(
        self, secret_uuid: str, decrypt: bool = False
    ) -> Optional[SecretRecord]:
        """Retrieve a secret via persist's recall path.

        Returns a SecretRecord. If `decrypt=True`, the plaintext is *not*
        attached to the SecretRecord (no field for it on the dataclass);
        callers wanting plaintext should call `decrypt_secret_value`
        which is now a thin persist call.
        """
        async with self._lock:
            if not await self._check_rate_limits("system"):
                return None
            try:
                engine = _get_engine()
                # `recall` flags persist's access log either way; pass
                # decrypt=False here — we only need the metadata. If a
                # caller wants the plaintext they go through
                # `decrypt_secret_value` below.
                raw = engine.secrets_recall_secret(secret_uuid, "retrieve", "system", False)
                if raw is None:
                    return None
                parsed = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
                if not isinstance(parsed, dict) or not parsed.get("found"):
                    return None
                ref_payload = parsed.get("ref") or self._lookup_ref(engine, secret_uuid)
                if not isinstance(ref_payload, dict):
                    # Fall back to list-stored to find the metadata.
                    ref_payload = self._lookup_ref(engine, secret_uuid) or {"uuid": secret_uuid}
                return _ref_to_record(ref_payload)
            except Exception as e:
                logger.error(
                    f"Failed to retrieve secret {secret_uuid}: {type(e).__name__}"
                )
                logger.debug(f"Secret retrieval error details: {e}")
                return None

    def _lookup_ref(self, engine: Any, secret_uuid: str) -> Optional[Dict[str, Any]]:
        """Find a single SecretReference by uuid via list_stored."""
        try:
            raw = engine.secrets_list_stored(500, json.dumps({"uuid": secret_uuid}))
            parsed = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
            if not isinstance(parsed, list):
                return None
            for ref in parsed:
                if isinstance(ref, dict) and str(ref.get("uuid")) == secret_uuid:
                    return ref
            return None
        except Exception:
            return None

    def decrypt_secret_value(self, secret_record: SecretRecord) -> Optional[str]:
        """Return the plaintext value for a stored secret.

        Routes through persist's `secrets_recall_secret(decrypt=True)`.
        The legacy implementation accepted ciphertext bytes off the
        SecretRecord; post-migration those bytes are empty placeholders
        and persist re-decrypts internally from the stored ciphertext.
        """
        try:
            engine = _get_engine()
            raw = engine.secrets_recall_secret(
                secret_record.secret_uuid, "decrypt_secret_value", "system", True
            )
            if raw is None:
                return None
            parsed = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
            if not isinstance(parsed, dict) or not parsed.get("found"):
                return None
            value = parsed.get("value")
            return str(value) if value is not None else None
        except Exception as e:
            logger.error(
                f"Failed to decrypt secret {secret_record.secret_uuid}: {type(e).__name__}"
            )
            return None

    async def delete_secret(self, secret_uuid: str) -> bool:
        """Delete a secret via persist's `secrets_forget_secret`."""
        async with self._lock:
            try:
                engine = _get_engine()
                result = engine.secrets_forget_secret(secret_uuid, "system")
                if result:
                    logger.info(f"Deleted secret {secret_uuid}")
                return bool(result)
            except Exception as e:
                logger.error(f"Failed to delete secret {secret_uuid}: {type(e).__name__}")
                return False

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    async def list_secrets(
        self,
        sensitivity_filter: Optional[str] = None,
        pattern_filter: Optional[str] = None,
    ) -> List[SecretReference]:
        """List stored secrets (metadata only).

        Filters are applied client-side over persist's `secrets_list_stored`
        response — persist's filter_json doesn't yet expose
        sensitivity/pattern predicates.
        """
        try:
            engine = _get_engine()
            raw = engine.secrets_list_stored(500, "{}")
            parsed = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
            if not isinstance(parsed, list):
                return []

            out: List[SecretReference] = []
            for ref in parsed:
                if not isinstance(ref, dict):
                    continue
                if sensitivity_filter and str(ref.get("sensitivity", "")).lower() != sensitivity_filter.lower():
                    continue
                if pattern_filter and str(ref.get("detected_pattern", "")) != pattern_filter:
                    continue
                out.append(_ref_to_reference(ref))
            # Persist returns DESC by created_at; preserve that ordering.
            return out
        except Exception as e:
            logger.error(f"Failed to list secrets: {type(e).__name__}")
            return []

    async def list_all_secrets(self) -> List[SecretReference]:
        """List all stored secrets (no filters)."""
        return await self.list_secrets()

    # ------------------------------------------------------------------
    # Rate limiting (in-memory; not persisted)
    # ------------------------------------------------------------------

    async def _check_rate_limits(self, accessor: str) -> bool:  # pragma: no cover - simple
        """In-memory rate limiter — protects against caller abuse, not a
        security boundary. Persist's audit log records every actual access.
        """
        now = self.time_service.now()

        if accessor not in self._access_counts:
            self._access_counts[accessor] = []

        access_times = self._access_counts[accessor]
        from datetime import timedelta

        minute_ago = now - timedelta(minutes=1)
        hour_ago = now - timedelta(hours=1)

        # Prune
        self._access_counts[accessor] = [t for t in access_times if t > hour_ago]
        access_times = self._access_counts[accessor]

        recent_minute = sum(1 for t in access_times if t > minute_ago)
        if recent_minute >= self.max_accesses_per_minute:
            return False
        if len(access_times) >= self.max_accesses_per_hour:
            return False

        access_times.append(now)
        return True

    async def _log_access(
        self,
        secret_uuid: str,
        access_type: str,
        accessor: str,
        purpose: str,
        success: bool,
        failure_reason: Optional[str] = None,
    ) -> None:
        """Audit log entry — no-op shim.

        Persist's substrate emits its own audit row for every secrets_*
        call. This shim is kept so legacy callers don't NoneType-crash.
        """
        return None

    # ------------------------------------------------------------------
    # Direct crypto (used by SecretsService.encrypt / .decrypt)
    # ------------------------------------------------------------------

    def encrypt_secret(self, value: str) -> Tuple[bytes, bytes, bytes]:
        """Encrypt a value via persist's `secrets_encrypt`.

        Returns `(ciphertext_b64_bytes, b"", b"")` — the agent's legacy
        3-tuple shape. The salt and nonce slots are empty because persist
        bundles them into the single base64 envelope it returns. Callers
        that concatenate `salt + nonce + encrypted` get the same envelope
        back; the symmetric `decrypt_secret` below pulls the full bytes
        out and hands them to persist verbatim.
        """
        try:
            engine = _get_engine()
            ct = engine.secrets_encrypt(value)
            ct_bytes = ct.encode() if isinstance(ct, str) else bytes(ct)
            return ct_bytes, b"", b""
        except Exception as e:
            logger.error(f"persist encrypt failed: {type(e).__name__}: {e}")
            raise

    def decrypt_secret(self, encrypted_value: bytes, salt: bytes, nonce: bytes) -> str:
        """Decrypt a value via persist's `secrets_decrypt`.

        `salt` and `nonce` are accepted for legacy signature compat — persist
        embeds them in the base64 envelope and only needs the ciphertext blob.
        """
        try:
            engine = _get_engine()
            blob = encrypted_value
            # Some callers may have concatenated empty bytes + ciphertext; if
            # salt/nonce were provided we treat the full concatenation as the
            # blob (this also covers the legacy-encrypted-at-rest path during
            # the one-shot reencrypt migration window).
            if salt or nonce:
                blob = salt + nonce + encrypted_value
            ct_str = blob.decode() if isinstance(blob, (bytes, bytearray)) else str(blob)
            pt = engine.secrets_decrypt(ct_str)
            return str(pt)
        except Exception as e:
            logger.error(f"persist decrypt failed: {type(e).__name__}: {e}")
            raise

    def rotate_master_key(self, new_master_key: Optional[bytes] = None) -> bytes:
        """Rotate persist's master key. Returns a placeholder bytes value
        for legacy signature compat — the actual key handle is persist-internal.
        """
        try:
            engine = _get_engine()
            arg: Optional[str] = None
            if new_master_key:
                arg = base64.b64encode(new_master_key).decode()
            engine.secrets_rotate_master_key(arg, "system")
            # Legacy API returned the new key bytes; persist abstracts the
            # key away. Return an empty bytes placeholder for shape compat.
            return b""
        except Exception as e:
            logger.error(f"rotate_master_key failed: {type(e).__name__}: {e}")
            raise

    def test_encryption(self) -> bool:
        """Verify encryption round-trips via persist."""
        try:
            engine = _get_engine()
            return bool(engine.secrets_test_encryption())
        except Exception:
            return False

    async def reencrypt_all(self, new_encryption_key: bytes) -> bool:
        """Rotate the master key and re-encrypt every stored secret.

        Persist's `secrets_reencrypt_all` walks every row internally; this
        wrapper combines the rotate + reencrypt steps so the legacy single-
        call contract still works.
        """
        try:
            engine = _get_engine()
            arg = base64.b64encode(new_encryption_key).decode() if new_encryption_key else None
            engine.secrets_rotate_master_key(arg, "system")
            engine.secrets_reencrypt_all("system")
            logger.info("persist secrets master key rotated + all rows re-encrypted")
            return True
        except Exception as e:
            logger.error(f"reencrypt_all failed: {type(e).__name__}: {e}")
            return False

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    async def get_access_logs(
        self, secret_uuid: Optional[str] = None, limit: int = 100
    ) -> List[Any]:
        """Pull access log entries via persist's substrate."""
        try:
            engine = _get_engine()
            raw = engine.secrets_get_access_logs(secret_uuid, limit)
            parsed = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
            return list(parsed) if isinstance(parsed, list) else []
        except Exception as e:
            logger.error(f"Failed to retrieve access logs: {type(e).__name__}: {e}")
            return []

    async def update_access_log(self, log_entry: Any) -> None:
        """No-op: persist's substrate records every access automatically."""
        return None

    # ------------------------------------------------------------------
    # Hardware key migration
    # ------------------------------------------------------------------

    async def migrate_to_hardware_key(self) -> bool:
        """Migrate persist's master key to the CIRISVerify hardware path."""
        try:
            engine = _get_engine()
            engine.secrets_migrate_to_hardware_key("system")
            logger.info("persist secrets migrated to hardware-backed master key")
            return True
        except Exception as e:
            logger.error(
                f"Failed to migrate to hardware key: {type(e).__name__}: {e}"
            )
            return False

    async def _verify_hardware_key_works(self) -> bool:
        """Canary round-trip to verify hardware-backed crypto.

        Persist's `secrets_test_encryption` performs the round-trip; we
        keep the legacy name for callers that probe via this method.
        """
        return self.test_encryption()
