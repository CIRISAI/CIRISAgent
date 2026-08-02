"""
Secrets Management Service for CIRIS Agent.

Coordinates secrets detection, storage, and retrieval with full audit trail
and integration with the agent's action pipeline.

2.9.7 (#896): the former `SecretsStore` / `SecretsEncryption` passthrough
shims were inlined here and deleted. 2.9.7 wave 2 deleted the Python
`SecretsFilter` detection engine too — persist's Engine now owns the FULL
secrets capability: detection (`secrets_process_incoming_text` against the
substrate filter catalog), decapsulation (`secrets_decapsulate`), crypto,
storage, and audit. This class is a thin typed facade plus the agent-side
task-lifecycle auto-forget.

Known upstream gaps (accepted, filed upstream): persist's default filter
catalog is EMPTY (no detections until `update_filter_config` seeds
patterns) and `secrets_decapsulate` is stubbed on SQLite (raises; this
facade degrades by returning the params unchanged).

`self.store` is a back-compat alias for the service itself — pre-2.9.7
callers reached storage via `secrets_service.store.<method>` and the
surviving external accesses (`list_all_secrets`, `migrate_to_hardware_key`,
`list_secrets`) are all methods on this class now.
"""

import base64
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.protocols.services.runtime.secrets import SecretsServiceProtocol
from ciris_engine.schemas.runtime.enums import SensitivityLevel, ServiceType
from ciris_engine.schemas.secrets.core import DetectedSecret, SecretRecord, SecretReference
from ciris_engine.schemas.secrets.service import (
    DecapsulationContext,
    FilterStats,
    FilterUpdateRequest,
    FilterUpdateResult,
    SecretRecallResult,
)
from ciris_engine.schemas.services.core import ServiceStatus
from ciris_engine.schemas.services.core.secrets import SecretsServiceStats
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)

# Default per-sensitivity decapsulation rules persisted with each secret
# (mirrors legacy SecretsStore semantics; lowercase keys match persist's
# sensitivity vocabulary).
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
            "persist engine not initialized — call initialize_database() " "before any secrets operation"
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


def _ref_to_record(ref: JSONDict) -> SecretRecord:
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
        created_at=_parse_iso(str(ref.get("created_at") or "")) or datetime.now(),
        last_accessed=_parse_iso(str(ref.get("last_accessed") or "")),
        access_count=0,  # Persist tracks access via audit log; not surfaced here.
        source_message_id=str(ref["source_message_id"]) if ref.get("source_message_id") else None,
        auto_decapsulate_for_actions=[str(a) for a in (ref.get("auto_decapsulate_actions") or [])],  # type: ignore[union-attr]
        manual_access_only=bool(ref.get("manual_access_only", False)),
    )


def _ref_to_reference(ref: JSONDict) -> SecretReference:
    """Build a SecretReference for the list endpoints."""
    return SecretReference(
        uuid=str(ref["uuid"]),
        description=str(ref.get("description") or ""),
        context_hint=str(ref.get("context_hint") or ""),
        sensitivity=SensitivityLevel(str(ref.get("sensitivity", "medium")).upper()),
        detected_pattern=str(ref.get("detected_pattern") or "unknown"),
        auto_decapsulate_actions=[str(a) for a in (ref.get("auto_decapsulate_actions") or [])],  # type: ignore[union-attr]
        created_at=_parse_iso(str(ref.get("created_at") or "")) or datetime.now(),
        last_accessed=_parse_iso(str(ref.get("last_accessed") or "")),
    )


class SecretsService(BaseService, SecretsServiceProtocol):
    """
    Central service for secrets management in CIRIS Agent.

    Provides unified interface for detection, storage, retrieval,
    and automatic decapsulation of secrets during action execution.
    """

    def __init__(
        self,
        time_service: TimeServiceProtocol,
        db_path: str = "secrets.db",
    ) -> None:
        """
        Initialize secrets service.

        Args:
            time_service: Time service for consistent time operations
            db_path: Legacy no-op — persist's Engine owns the database.
                Accepted so pre-2.9.7 call sites keep constructing.
        """
        super().__init__(time_service=time_service)
        # Back-compat alias: pre-2.9.7 callers reached storage via `.store`
        # (the deleted SecretsStore shim). The service IS the store now.
        self.store: "SecretsService" = self
        self._auto_forget_enabled = True
        self._current_task_secrets: Dict[str, str] = {}  # UUID -> original_value

        # Tracking variables for metrics
        self._secrets_stored = 0
        self._secrets_retrieved = 0
        self._secrets_deleted = 0
        self._encryption_operations = 0
        self._decryption_operations = 0
        self._filter_detections = 0
        self._auto_encryptions = 0
        self._failed_decryptions = 0
        self._rotation_count = 0
        self._start_time = time_service.now()

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
    # Persist-substrate storage (inlined from the deleted SecretsStore)
    # ------------------------------------------------------------------

    async def _store_detected_secret(self, secret: DetectedSecret, source_id: Optional[str] = None) -> SecretRecord:
        """Store a detected secret via persist's `secrets_store_detected_secret`.

        Persist owns encryption, audit logging, and the access counter.
        Returns a SecretRecord populated from persist's `SecretReference`
        envelope; crypto-byte fields are empty (no caller reads them).
        """
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
                "auto_decapsulate_for_actions": _AUTO_DECAPSULATE_BY_SENSITIVITY.get(sensitivity.lower(), []),
                "manual_access_only": False,
            }
        )
        try:
            raw = engine.secrets_store_detected_secret(payload, "system")
            envelope = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
            ref = envelope.get("ref") if isinstance(envelope, dict) else None
            if not isinstance(ref, dict):
                raise RuntimeError(f"secrets_store_detected_secret envelope missing ref: {envelope!r}")
            logger.info(f"Stored encrypted secret {ref['uuid']}")
            return _ref_to_record(ref)
        except Exception as e:
            logger.error(f"Failed to store secret {secret.secret_uuid}: {type(e).__name__}")
            logger.debug(f"Secret storage error details: {e}")
            raise

    async def _retrieve_secret_record(self, secret_uuid: str) -> Optional[SecretRecord]:
        """Retrieve a secret's metadata via persist's recall path.

        Returns a metadata-only SecretRecord — the plaintext is never
        attached (no field for it on the schema). Callers wanting
        plaintext go through `_decrypt_secret_value`.
        """
        try:
            engine = _get_engine()
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
            logger.error(f"Failed to retrieve secret {secret_uuid}: {type(e).__name__}")
            logger.debug(f"Secret retrieval error details: {e}")
            return None

    def _lookup_ref(self, engine: Any, secret_uuid: str) -> Optional[JSONDict]:
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

    def _decrypt_secret_value(self, secret_record: SecretRecord) -> Optional[str]:
        """Return the plaintext value for a stored secret.

        Routes through persist's `secrets_recall_secret(decrypt=True)` —
        persist decrypts internally from the stored ciphertext.
        """
        try:
            engine = _get_engine()
            raw = engine.secrets_recall_secret(secret_record.secret_uuid, "decrypt_secret_value", "system", True)
            if raw is None:
                return None
            parsed = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
            if not isinstance(parsed, dict) or not parsed.get("found"):
                return None
            value = parsed.get("value")
            return str(value) if value is not None else None
        except Exception as e:
            logger.error(f"Failed to decrypt secret {secret_record.secret_uuid}: {type(e).__name__}")
            return None

    async def _delete_secret(self, secret_uuid: str) -> bool:
        """Delete a secret via persist's `secrets_forget_secret`."""
        try:
            engine = _get_engine()
            result = engine.secrets_forget_secret(secret_uuid, "system")
            if result:
                logger.info(f"Deleted secret {secret_uuid}")
            return bool(result)
        except Exception as e:
            logger.error(f"Failed to delete secret {secret_uuid}: {type(e).__name__}")
            return False

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

    async def migrate_to_hardware_key(self) -> bool:
        """Migrate persist's master key to the CIRISVerify hardware path."""
        try:
            engine = _get_engine()
            engine.secrets_migrate_to_hardware_key("system")
            logger.info("persist secrets migrated to hardware-backed master key")
            return True
        except Exception as e:
            # Not an error: persist's secrets-hw path is pending upstream
            # (CIRISPersist#87). The service keeps its software-backed master
            # key as a graceful fallback — logged at WARNING, not ERROR.
            logger.warning(
                f"Hardware-backed master key unavailable; using software-backed " f"key: {type(e).__name__}: {e}"
            )
            return False

    # ------------------------------------------------------------------
    # Detection + facade methods
    # ------------------------------------------------------------------

    async def process_incoming_text(self, text: str, source_message_id: str) -> Tuple[str, List[SecretReference]]:
        """
        Process incoming text for secrets detection and replacement.

        Detection + encrypt-and-store are owned by persist's
        `secrets_process_incoming_text`, which regex-matches the substrate
        filter catalog and returns `{"filtered_text": ..., "refs": [...]}`.
        An empty catalog (persist's default) means no detections — seed it
        via `update_filter_config`.

        Args:
            text: Original text to process
            source_message_id: ID of source message for tracking

        Returns:
            Tuple of (filtered_text, secret_references)
        """
        try:
            engine = _get_engine()
            raw = engine.secrets_process_incoming_text(text, source_message_id, "system")
            envelope = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
        except Exception as e:
            logger.error(f"Substrate secrets detection failed: {type(e).__name__}: {e}")
            return text, []

        if not isinstance(envelope, dict):
            logger.error(f"secrets_process_incoming_text returned non-dict envelope: {envelope!r}")
            return text, []

        refs = envelope.get("refs") or []
        if not refs:
            return text, []

        filtered_text = str(envelope.get("filtered_text", text))
        self._filter_detections += len(refs)

        secret_references: List[SecretReference] = []
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            secret_ref = _ref_to_reference(ref)
            # Track for task-lifecycle auto-forget (keys only matter;
            # persist never returns plaintext here).
            self._current_task_secrets[secret_ref.uuid] = secret_ref.description
            secret_references.append(secret_ref)
            logger.info(
                f"Detected and stored {secret_ref.sensitivity} secret: "
                f"{secret_ref.description} (UUID: {secret_ref.uuid})"
            )

        return filtered_text, secret_references

    async def recall_secret(
        self, secret_uuid: str, purpose: str, accessor: str = "agent", decrypt: bool = False
    ) -> Optional[SecretRecallResult]:
        """
        Recall a stored secret for agent use.

        Args:
            secret_uuid: UUID of secret to recall
            purpose: Purpose for accessing secret (for audit)
            accessor: Who is accessing the secret
            decrypt: Whether to return decrypted value

        Returns:
            Secret information dict or None if not found/denied
        """
        secret_record = await self._retrieve_secret_record(secret_uuid)

        if not secret_record:
            return None

        # Track secret access
        self._secrets_retrieved += 1

        if decrypt:
            self._decryption_operations += 1
            decrypted_value = self._decrypt_secret_value(secret_record)
            result = SecretRecallResult(
                found=True, value=decrypted_value, error=None if decrypted_value else "Failed to decrypt secret value"
            )
        else:
            result = SecretRecallResult(found=True, value=None, error=None)

        return result

    async def decapsulate_secrets_in_parameters(
        self, action_type: str, action_params: JSONDict, context: DecapsulationContext
    ) -> JSONDict:
        """
        Automatically decapsulate secrets in action parameters.

        Persist's `secrets_decapsulate` walks the params JSON, replacing
        every `{SECRET:<uuid>:<description>}` placeholder with decrypted
        plaintext when `action_type` is in the secret's whitelist, and
        audits each access.

        Known gap (filed upstream): stubbed on SQLite — this facade
        degrades by returning the params unchanged (placeholders intact).

        Args:
            action_type: Type of action being executed
            action_params: Action parameters potentially containing secret references
            context: Execution context for audit

        Returns:
            Parameters with secrets decapsulated where appropriate
        """
        if not action_params:
            return action_params

        ctx_json = json.dumps(
            {
                "action_type": context.action_type,
                "thought_id": context.thought_id,
                "user_id": context.user_id,
                "accessor": "agent",
                "purpose": f"auto-decapsulation for {action_type} action",
            }
        )
        try:
            engine = _get_engine()
            raw = engine.secrets_decapsulate(action_type, json.dumps(action_params), ctx_json)
            result = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
        except Exception as e:
            # SQLite decapsulation is stubbed upstream (`Permanent:
            # pipeline orchestration deferred`) — degrade gracefully.
            logger.warning(f"Substrate decapsulation unavailable, params returned unchanged: {type(e).__name__}: {e}")
            return action_params

        if isinstance(result, dict):
            # DecapsulateResult envelope carries the rewritten params.
            for key in ("action_params", "params", "rewritten_params", "decapsulated_params"):
                params = result.get(key)
                if isinstance(params, dict):
                    return params

        logger.warning(f"Unrecognized secrets_decapsulate envelope shape: {type(result).__name__}")
        return action_params

    def _read_substrate_catalog(self, engine: Any) -> Tuple[List[JSONDict], int]:
        """Read persist's filter catalog → (patterns, version)."""
        raw = engine.secrets_get_filter_config()
        parsed = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
        if not isinstance(parsed, dict):
            return [], 0
        config_value = parsed.get("config_value") or {}
        patterns = config_value.get("patterns") if isinstance(config_value, dict) else []
        version = int(parsed.get("version", 0))
        return [p for p in (patterns or []) if isinstance(p, dict)], version

    async def update_filter_config(self, updates: FilterUpdateRequest, accessor: str = "agent") -> FilterUpdateResult:
        """
        Update the substrate secrets filter catalog.

        Merges the requested patterns into persist's catalog (upsert by
        pattern name; `enabled=False` removes) and writes it back via
        `secrets_update_filter_config`. Sensitivity-level updates have no
        substrate representation and are acknowledged as no-ops.

        Args:
            updates: Filter configuration updates
            accessor: Who is making the update

        Returns:
            Result of configuration update
        """
        try:
            engine = _get_engine()
            results: List[JSONDict] = []

            patterns_updated = 0
            if updates.patterns:
                catalog, version = self._read_substrate_catalog(engine)
                by_id = {str(p.get("pattern_id")): p for p in catalog}
                for pattern_config in updates.patterns:
                    if pattern_config.enabled:
                        sensitivity = pattern_config.sensitivity.value.lower()
                        by_id[pattern_config.name] = {
                            "pattern_id": pattern_config.name,
                            "regex": pattern_config.pattern,
                            "description": pattern_config.name,
                            "sensitivity": sensitivity,
                            "auto_decapsulate_for_actions": _AUTO_DECAPSULATE_BY_SENSITIVITY.get(sensitivity, []),
                        }
                        results.append({"message": f"Upserted pattern: {pattern_config.name}"})
                    else:
                        by_id.pop(pattern_config.name, None)
                        results.append({"message": f"Removed pattern: {pattern_config.name}"})
                    patterns_updated += 1

                new_config = {"patterns": list(by_id.values()), "version": version + 1}
                engine.secrets_update_filter_config(
                    json.dumps({"config_id": "global", "new_config": new_config}), accessor
                )

            if updates.sensitivity_config:
                for level_name in updates.sensitivity_config:
                    results.append({"message": f"Sensitivity level acknowledged (no substrate mapping): {level_name}"})

            stats = FilterStats(
                patterns_updated=patterns_updated,
                sensitivity_levels_updated=len(updates.sensitivity_config) if updates.sensitivity_config else 0,
            )
            return FilterUpdateResult(success=True, error=None, results=results, accessor=accessor, stats=stats)

        except Exception as e:
            logger.error(f"Failed to update filter config: {e}")
            return FilterUpdateResult(success=False, error=str(e), results=None, accessor=accessor, stats=None)

    async def list_stored_secrets(self, limit: int = 10) -> List[SecretReference]:
        """
        List stored secrets (metadata only, no decryption).

        Args:
            limit: Maximum number of secrets to return

        Returns:
            List of SecretReference objects
        """
        secrets = await self.store.list_secrets(sensitivity_filter=None, pattern_filter=None)

        limited_secrets = secrets[:limit] if secrets else []

        return limited_secrets

    async def forget_secret(self, secret_uuid: str, accessor: str = "agent") -> bool:
        """
        Delete/forget a stored secret.

        Args:
            secret_uuid: UUID of secret to forget
            accessor: Who is forgetting the secret

        Returns:
            True if successfully forgotten
        """
        deleted = await self._delete_secret(secret_uuid)

        if secret_uuid in self._current_task_secrets:
            del self._current_task_secrets[secret_uuid]

        return deleted

    async def _auto_forget_task_secrets(self) -> List[str]:
        """
        Automatically forget secrets from current task.

        Returns:
            List of forgotten secret UUIDs
        """
        if not self._auto_forget_enabled:
            return []

        forgotten_secrets = []

        for secret_uuid in list(self._current_task_secrets.keys()):
            deleted = await self.forget_secret(secret_uuid, "auto_forget")
            if deleted:
                forgotten_secrets.append(secret_uuid)

        self._current_task_secrets.clear()

        if forgotten_secrets:
            logger.info(f"Auto-forgot {len(forgotten_secrets)} task secrets")

        return forgotten_secrets

    def _enable_auto_forget(self) -> None:
        """Enable automatic forgetting of task secrets."""
        self._auto_forget_enabled = True

    def _disable_auto_forget(self) -> None:
        """Disable automatic forgetting of task secrets."""
        self._auto_forget_enabled = False

    # Protocol methods for SecretsServiceProtocol
    async def encrypt(self, plaintext: str) -> str:
        """Encrypt a secret via persist's `secrets_encrypt`.

        Persist returns a single base64 envelope (`salt || nonce ||
        ciphertext`) — the symmetric `decrypt` below hands it back verbatim.
        """
        engine = _get_engine()
        return str(engine.secrets_encrypt(plaintext))

    async def decrypt(self, ciphertext: str) -> str:
        """Decrypt a secret via persist's `secrets_decrypt`."""
        try:
            engine = _get_engine()
            return str(engine.secrets_decrypt(ciphertext))
        except Exception as e:
            logger.error(f"Failed to decrypt: {e}")
            return ""

    async def store_secret(self, key: str, value: str) -> None:
        """Store an encrypted secret."""
        # Create a DetectedSecret and store it
        detected_secret = DetectedSecret(
            secret_uuid=key,
            original_value=value,
            replacement_text=f"{{SECRET:{key}:manual}}",
            pattern_name="manual",
            description="Manually stored secret",
            sensitivity=SensitivityLevel.MEDIUM,
            context_hint="Manual storage via API",
        )
        await self._store_detected_secret(detected_secret, "manual_store")

    async def retrieve_secret(self, key: str) -> Optional[str]:
        """Retrieve and decrypt a secret."""
        try:
            secret_record = await self._retrieve_secret_record(key)
            if secret_record:
                # Track secret access
                self._secrets_retrieved += 1
                self._decryption_operations += 1
                decrypted = self._decrypt_secret_value(secret_record)
                return decrypted
            return None
        except Exception:
            return None

    async def get_filter_config(self) -> JSONDict:
        """Get the current substrate filter catalog envelope."""
        try:
            engine = _get_engine()
            raw = engine.secrets_get_filter_config()
            parsed = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
            return parsed if isinstance(parsed, dict) else {}
        except Exception as e:
            logger.error(f"Failed to get filter config: {type(e).__name__}: {e}")
            return {}

    async def get_service_stats(self) -> SecretsServiceStats:
        """Get comprehensive service statistics from the substrate."""
        try:
            engine = _get_engine()
            raw = engine.secrets_get_service_stats()
            parsed = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
            if not isinstance(parsed, dict):
                raise RuntimeError(f"secrets_get_service_stats returned non-dict: {parsed!r}")
            return SecretsServiceStats(
                total_secrets=int(parsed.get("total_secrets", 0)),
                active_filters=int(parsed.get("active_filters", 0)),
                filter_matches_today=int(parsed.get("filter_matches_today", 0)),
                last_filter_update=_parse_iso(parsed.get("last_filter_update")),
                encryption_enabled=bool(parsed.get("encryption_enabled", True)),
            )

        except Exception as e:
            logger.error(f"Failed to get service stats: {e}")
            # Return default stats on error
            return SecretsServiceStats(
                total_secrets=0,
                active_filters=0,
                filter_matches_today=0,
                last_filter_update=None,
                encryption_enabled=True,
            )

    async def _on_start(self) -> None:
        """Custom startup logic for secrets service."""
        logger.info("SecretsService started")

    async def _on_stop(self) -> None:
        """Custom cleanup logic for secrets service."""
        # Auto-forget any remaining task secrets
        if self._auto_forget_enabled and self._current_task_secrets:
            logger.info(f"Auto-forgetting {len(self._current_task_secrets)} task secrets on shutdown")
            await self._auto_forget_task_secrets()
        logger.info("SecretsService stopped")

    def get_service_type(self) -> ServiceType:
        """Get the service type enum value."""
        return ServiceType.SECRETS

    def _check_dependencies(self) -> bool:
        """Check if all required dependencies are available."""
        try:
            _get_engine()
            return True
        except RuntimeError:
            return False

    def _register_dependencies(self) -> None:
        """Register service dependencies."""
        super()._register_dependencies()
        # No external service dependencies, just internal components

    async def reencrypt_all(self, new_master_key: bytes) -> bool:
        """
        Re-encrypt all stored secrets with a new master key.

        This is used for key rotation and security compliance. Persist's
        `secrets_reencrypt_all` walks every row internally; this method
        combines the rotate + reencrypt steps so the legacy single-call
        contract still works.

        Args:
            new_master_key: New 32-byte master key for encryption

        Returns:
            True if all secrets were successfully re-encrypted
        """
        try:
            logger.info("Starting re-encryption of all secrets")
            engine = _get_engine()
            arg = base64.b64encode(new_master_key).decode() if new_master_key else None
            new_key_ref = engine.secrets_rotate_master_key(arg, "system")
            raw = engine.secrets_reencrypt_all(new_key_ref, "system")
            result = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
            if isinstance(result, dict) and not result.get("success", False):
                logger.error(f"Failed to re-encrypt some or all secrets: {result.get('failures')}")
                return False
            self._rotation_count += 1  # Track successful rotation operations
            logger.info("Successfully re-encrypted all secrets")
            return True
        except Exception as e:
            logger.error(f"Re-encryption failed with error: {e}")
            return False

    def _get_actions(self) -> List[str]:
        """Get list of actions this service provides."""
        return [
            "process_incoming_text",
            "decapsulate_secrets_in_parameters",
            "list_stored_secrets",
            "recall_secret",
            "update_filter_config",
            "forget_secret",
            "get_service_stats",
            "get_filter_config",
            "encrypt",
            "decrypt",
            "store_secret",
            "retrieve_secret",
            "reencrypt_all",
        ]

    def _substrate_filter_active(self) -> bool:
        """True when the substrate filter catalog has at least one pattern."""
        try:
            patterns, _version = self._read_substrate_catalog(_get_engine())
            return len(patterns) > 0
        except Exception:
            return False

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect secrets service metrics."""
        metrics = super()._collect_custom_metrics()

        # Count vault size
        vault_size = 0
        try:
            vault_size = len(self._vault) if hasattr(self, "_vault") else 0
        except (AttributeError, TypeError):
            # Ignore attribute errors when checking vault size
            pass

        metrics.update(
            {
                "secrets_stored": float(self._secrets_stored),
                "secrets_retrieved": float(self._secrets_retrieved),
                "secrets_deleted": float(self._secrets_deleted),
                "vault_size": float(vault_size),
                "encryption_operations": float(self._encryption_operations),
                "decryption_operations": float(self._decryption_operations),
                "filter_detections": float(self._filter_detections),
                "auto_encryptions": float(self._auto_encryptions),
                "failed_decryptions": float(self._failed_decryptions),
                "filter_enabled": 1.0 if self._substrate_filter_active() else 0.0,
            }
        )

        return metrics

    async def get_metrics(self) -> Dict[str, float]:
        """
        Get all secrets service metrics including base, custom, and v1.4.3 specific.
        """
        # Get all base + custom metrics
        metrics = self._collect_metrics()
        # Calculate accessed secrets from retrievals and decryptions
        accessed_total = self._secrets_retrieved + self._decryption_operations

        # Rotated secrets = re-encryption operations (when master key changes)
        rotated_total = 0  # Track via reencrypt_all calls
        if hasattr(self, "_rotation_count"):
            rotated_total = self._rotation_count

        # Active secrets = current secrets in store
        active_secrets = 0
        try:
            all_secrets = await self.store.list_secrets()
            active_secrets = len(all_secrets) if all_secrets else 0
        except Exception:
            # Fallback to current task secrets if store query fails
            active_secrets = len(self._current_task_secrets)

        # Service uptime in seconds
        uptime_seconds = self._calculate_uptime()

        # Add v1.4.3 specific metrics
        metrics.update(
            {
                "secrets_accessed_total": float(accessed_total),
                "secrets_rotated_total": float(rotated_total),
                "secrets_active": float(active_secrets),
                "secrets_uptime_seconds": uptime_seconds,
            }
        )

        return metrics

    def get_status(self) -> ServiceStatus:
        """Get service status."""
        return ServiceStatus(
            service_name="SecretsService",
            service_type="core_service",
            is_healthy=self._check_dependencies(),
            uptime_seconds=self._calculate_uptime(),
            metrics={
                "secrets_stored": float(len(self._current_task_secrets)),
                "filter_enabled": 1.0 if self._substrate_filter_active() else 0.0,
                "auto_forget_enabled": 1.0 if self._auto_forget_enabled else 0.0,
            },
            last_error=self._last_error,
            last_health_check=self._last_health_check,
        )
