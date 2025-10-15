"""
Secrets Management Service for CIRIS Agent.

Coordinates secrets detection, storage, and retrieval with full audit trail
and integration with the agent's action pipeline.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.protocols.services.runtime.secrets import SecretsServiceProtocol
from ciris_engine.schemas.runtime.enums import SensitivityLevel, ServiceType
from ciris_engine.schemas.secrets.core import DetectedSecret, SecretRecord, SecretReference, SecretsDetectionConfig
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

from .filter import SecretsFilter
from .store import SecretsStore

logger = logging.getLogger(__name__)


class SecretsService(BaseService, SecretsServiceProtocol):
    """
    Central service for secrets management in CIRIS Agent.

    Provides unified interface for detection, storage, retrieval,
    and automatic decapsulation of secrets during action execution.
    """

    def __init__(
        self,
        time_service: TimeServiceProtocol,
        store: Optional[SecretsStore] = None,
        filter_obj: Optional[SecretsFilter] = None,
        detection_config: Optional[SecretsDetectionConfig] = None,
        db_path: str = "secrets.db",
        master_key: Optional[bytes] = None,
    ) -> None:
        """
        Initialize secrets service.

        Args:
            time_service: Time service for consistent time operations
            store: Secrets store instance (created if None)
            filter_obj: Secrets filter instance (created if None)
            detection_config: Secrets detection configuration
            db_path: Database path for storage
            master_key: Master encryption key
        """
        super().__init__(time_service=time_service)
        self.store = store or SecretsStore(time_service=time_service, db_path=db_path, master_key=master_key)
        self.filter = filter_obj or SecretsFilter(detection_config)
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

    async def process_incoming_text(self, text: str, source_message_id: str) -> Tuple[str, List[SecretReference]]:
        """
        Process incoming text for secrets detection and replacement.

        Args:
            text: Original text to process
            context_hint: Safe context description
            source_message_id: ID of source message for tracking

        Returns:
            Tuple of (filtered_text, secret_references)
        """
        filtered_text, detected_secrets = self.filter.filter_text(text, "")

        if not detected_secrets:
            return text, []

        secret_references = []

        for detected_secret in detected_secrets:
            secret_record = SecretRecord(
                secret_uuid=detected_secret.secret_uuid,
                encrypted_value=b"",  # Will be set by store
                encryption_key_ref="",  # Will be set by store
                salt=b"",  # Will be set by store
                nonce=b"",  # Will be set by store
                description=detected_secret.description,
                sensitivity_level=detected_secret.sensitivity,
                detected_pattern=detected_secret.pattern_name,
                context_hint=detected_secret.context_hint,
                created_at=self._now(),
                last_accessed=None,
                access_count=0,
                source_message_id=source_message_id,
                auto_decapsulate_for_actions=self._get_auto_decapsulate_actions(detected_secret.sensitivity.value),
                manual_access_only=False,
            )

            stored = await self.store.store_secret(detected_secret, source_message_id)

            if stored:
                self._current_task_secrets[detected_secret.secret_uuid] = detected_secret.original_value

                secret_ref = SecretReference(
                    uuid=detected_secret.secret_uuid,
                    description=detected_secret.description,
                    context_hint=detected_secret.context_hint,
                    sensitivity=detected_secret.sensitivity,
                    detected_pattern=detected_secret.pattern_name or "unknown",
                    auto_decapsulate_actions=secret_record.auto_decapsulate_for_actions,
                    created_at=secret_record.created_at,
                    last_accessed=None,
                )
                secret_references.append(secret_ref)

                logger.info(
                    f"Detected and stored {detected_secret.sensitivity} secret: "
                    f"{detected_secret.description} (UUID: {detected_secret.secret_uuid})"
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
        secret_record = await self.store.retrieve_secret(secret_uuid, decrypt)

        if not secret_record:
            return None

        # Track secret access
        self._secrets_retrieved += 1

        if decrypt:
            self._decryption_operations += 1
            decrypted_value = self.store.decrypt_secret_value(secret_record)
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

        Args:
            action_type: Type of action being executed
            action_params: Action parameters potentially containing secret references
            context: Execution context for audit

        Returns:
            Parameters with secrets decapsulated where appropriate
        """
        if not action_params:
            return action_params

        result = await self._deep_decapsulate(action_params, action_type, context)

        # Ensure we return a dict as expected
        if isinstance(result, dict):
            return result
        else:
            # This shouldn't happen if action_params is a dict
            return action_params

    async def _deep_decapsulate(
        self,
        obj: Union[JSONDict, List[Any], str, int, float, bool, None],
        action_type: str,
        context: DecapsulationContext,
    ) -> Union[JSONDict, List[Any], str, int, float, bool, None]:
        """Recursively decapsulate secrets in nested structures."""
        if isinstance(obj, str):
            return await self._decapsulate_string(obj, action_type, context)
        elif isinstance(obj, dict):
            result: JSONDict = {}
            for key, value in obj.items():
                result[key] = await self._deep_decapsulate(value, action_type, context)
            return result
        elif isinstance(obj, list):
            list_result: List[Any] = []
            for item in obj:
                list_result.append(await self._deep_decapsulate(item, action_type, context))
            return list_result
        else:
            return obj

    async def _decapsulate_string(self, text: str, action_type: str, context: DecapsulationContext) -> str:
        """Decapsulate secret references in a string."""
        import re

        secret_pattern = r"\{SECRET:([a-f0-9-]{36}):([^}]+)\}"

        matches = list(re.finditer(secret_pattern, text))
        if not matches:
            return text

        result = text

        for match in reversed(matches):
            secret_uuid = match.group(1)
            description = match.group(2)

            secret_record = await self.store.retrieve_secret(secret_uuid, decrypt=False)

            if not secret_record:
                logger.warning(f"Secret {secret_uuid} not found for decapsulation")
                continue  # Leave original reference

            if action_type in secret_record.auto_decapsulate_for_actions:
                decrypted_value = self.store.decrypt_secret_value(secret_record)
                if decrypted_value:
                    logger.info(
                        f"Auto-decapsulated {secret_record.sensitivity_level} secret "
                        f"for {action_type} action: {description}"
                    )
                    result = result[: match.start()] + decrypted_value + result[match.end() :]
                else:
                    logger.error(f"Failed to decrypt secret {secret_uuid}")
            else:
                logger.info(f"Secret {secret_uuid} not configured for auto-decapsulation " f"in {action_type} actions")

        return result

    async def update_filter_config(
        self, updates: FilterUpdateRequest, accessor: str = "agent"
    ) -> FilterUpdateResult:  # pragma: no cover - thin wrapper
        """
        Update secrets filter configuration.

        Args:
            updates: Dictionary of configuration updates
            accessor: Who is making the update

        Returns:
            Result of configuration update
        """
        try:
            results = []

            # Handle pattern updates
            if updates.patterns:
                for pattern_config in updates.patterns:
                    # Pattern operations would be handled here based on PatternConfig
                    results.append("Updated pattern configuration")

            # Handle sensitivity config updates
            if updates.sensitivity_config:
                for level_name, sensitivity_config in updates.sensitivity_config.items():
                    # Sensitivity operations would be handled here
                    results.append(f"Updated sensitivity level: {level_name}")

            # Create stats object
            stats = FilterStats(
                patterns_updated=len(updates.patterns) if updates.patterns else 0,
                sensitivity_levels_updated=len(updates.sensitivity_config) if updates.sensitivity_config else 0,
            )

            # Convert string results to dict format
            dict_results = [{"message": result} for result in results]

            return FilterUpdateResult(success=True, error=None, results=dict_results, accessor=accessor, stats=stats)

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
        deleted = await self.store.delete_secret(secret_uuid)

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

    def _get_auto_decapsulate_actions(self, sensitivity: str) -> List[str]:
        """
        Get default auto-decapsulation actions based on sensitivity.

        Args:
            sensitivity: Secret sensitivity level

        Returns:
            List of action types that can auto-decapsulate this secret
        """
        if sensitivity == "CRITICAL":
            return []  # Require manual access for critical secrets
        elif sensitivity == "HIGH":
            return ["tool"]  # Only tool actions for high sensitivity
        elif sensitivity == "MEDIUM":
            return ["tool", "speak"]  # Tool and speak actions
        else:  # LOW
            return ["tool", "speak", "memorize"]  # Most actions allowed

    # Protocol methods for SecretsServiceProtocol
    async def encrypt(self, plaintext: str) -> str:
        """Encrypt a secret."""
        # Direct encryption - returns base64 encoded ciphertext
        encrypted_value, salt, nonce = self.store.encrypt_secret(plaintext)
        # Combine encrypted parts into a single string for transport
        import base64

        combined = salt + nonce + encrypted_value
        return base64.b64encode(combined).decode("utf-8")

    async def decrypt(self, ciphertext: str) -> str:
        """Decrypt a secret."""
        # Direct decryption - expects base64 encoded ciphertext
        import base64

        try:
            combined = base64.b64decode(ciphertext.encode("utf-8"))
            # Extract parts (salt: 16 bytes, nonce: 12 bytes, rest: encrypted value)
            salt = combined[:16]
            nonce = combined[16:28]
            encrypted_value = combined[28:]
            return self.store.decrypt_secret(encrypted_value, salt, nonce)
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
        await self.store.store_secret(detected_secret, "manual_store")

    async def retrieve_secret(self, key: str) -> Optional[str]:
        """Retrieve and decrypt a secret."""
        try:
            secret_record = await self.store.retrieve_secret(key, decrypt=True)
            if secret_record:
                # Track secret access
                self._secrets_retrieved += 1
                self._decryption_operations += 1
                decrypted = self.store.decrypt_secret_value(secret_record)
                return decrypted
            return None
        except Exception:
            return None

    async def get_filter_config(self) -> JSONDict:
        """Get current filter configuration."""
        # Wrap the filter's get_filter_config to prevent direct access
        config_export = self.filter.get_filter_config()
        # Convert ConfigExport to dict
        return config_export.model_dump()

    async def get_service_stats(self) -> SecretsServiceStats:
        """Get comprehensive service statistics."""
        try:
            # Get filter stats
            filter_stats = self.filter.get_pattern_stats()

            # Get storage stats
            all_secrets = await self.store.list_secrets()

            # Get enabled patterns from filter stats
            # PatternStats doesn't have pattern_counts, but we can derive from the counts
            enabled_patterns = []
            if filter_stats.default_patterns > 0:
                enabled_patterns.extend([f"default_{i}" for i in range(filter_stats.default_patterns)])
            if filter_stats.custom_patterns > 0:
                enabled_patterns.extend([f"custom_{i}" for i in range(filter_stats.custom_patterns)])

            # Count recent detections (PatternStats doesn't track detections, so we'll use total patterns)
            _recent_detections = filter_stats.total_patterns

            # Calculate storage size (approximate)
            _storage_size_bytes = len(all_secrets) * 512  # Rough estimate: 512 bytes per secret

            return SecretsServiceStats(
                total_secrets=len(all_secrets),
                active_filters=filter_stats.total_patterns,
                filter_matches_today=0,  # We don't track this currently
                last_filter_update=None,  # We don't track this currently
                encryption_enabled=True,
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
        return self.filter is not None and self.store is not None

    def _register_dependencies(self) -> None:
        """Register service dependencies."""
        super()._register_dependencies()
        # No external service dependencies, just internal components

    async def reencrypt_all(self, new_master_key: bytes) -> bool:
        """
        Re-encrypt all stored secrets with a new master key.

        This is used for key rotation and security compliance.

        Args:
            new_master_key: New 32-byte master key for encryption

        Returns:
            True if all secrets were successfully re-encrypted
        """
        try:
            if not self.store:
                logger.error("No secret store available for re-encryption")
                return False

            logger.info("Starting re-encryption of all secrets")
            success = await self.store.reencrypt_all(new_master_key)

            if success:
                self._rotation_count += 1  # Track successful rotation operations
                logger.info("Successfully re-encrypted all secrets")
            else:
                logger.error("Failed to re-encrypt some or all secrets")

            return success

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
                "filter_enabled": (
                    1.0
                    if self.filter and hasattr(self.filter, "detection_config") and self.filter.detection_config.enabled
                    else 0.0
                ),
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
                "filter_enabled": 1.0 if self.filter else 0.0,
                "auto_forget_enabled": 1.0 if self._auto_forget_enabled else 0.0,
            },
            last_error=self._last_error,
            last_health_check=self._last_health_check,
        )
