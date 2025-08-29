import logging
from typing import List

from ciris_engine.logic.secrets.service import SecretsService

logger = logging.getLogger(__name__)


async def build_secrets_snapshot(secrets_service: SecretsService) -> dict:
    """Build secrets information for SystemSnapshot."""
    try:
        # Get recent secrets (limit to last 10 for context)
        all_secrets = await secrets_service.store.list_all_secrets()
        recent_secrets = sorted(all_secrets, key=lambda s: s.created_at, reverse=True)[:10]

        # Convert SecretReference objects to strings for SystemSnapshot compatibility
        detected_secrets: List[str] = [str(s.uuid) for s in recent_secrets]

        # Get filter version
        filter_config = secrets_service.filter.get_filter_config()
        filter_version = filter_config.version

        # Get total count
        total_secrets = len(all_secrets)

        return {
            "detected_secrets": detected_secrets,
            "secrets_filter_version": filter_version,
            "total_secrets_stored": total_secrets,
        }

    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error building secrets snapshot: {e}")
        return {
            "detected_secrets": [],
            "secrets_filter_version": 0,
            "total_secrets_stored": 0,
        }
