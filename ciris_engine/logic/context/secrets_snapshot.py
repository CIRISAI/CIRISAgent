import logging
from typing import Any, Dict, List

from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)

# Key for error metadata in the returned dictionary
ERROR_KEY = "error"


async def build_secrets_snapshot(secrets_service: SecretsService) -> JSONDict:
    """Build secrets information for SystemSnapshot.

    Returns a JSON-compatible dictionary with keys matching SystemSnapshot fields:
    - detected_secrets: List[str]
    - secrets_filter_version: int
    - total_secrets_stored: int

    When an error occurs, the payload includes an ``error`` key so downstream
    consumers can distinguish between an empty dataset and a failure.
    """
    try:
        # `detected_secrets` is deliberately EMPTY here.
        #
        # It used to carry the 10 most recently created secret UUIDs from
        # `list_all_secrets()` — every task's, not this one's. `recall_secret`
        # decrypts any UUID it is handed with no ownership check, so that made
        # one task's secrets addressable from any other task's reasoning.
        #
        # Nothing is lost by removing it. A secret the agent legitimately needs
        # is already reachable: the observer substitutes a
        # `{SECRET:<uuid>:<description>}` placeholder INTO the message being
        # processed (base_observer.py:299), so the reference arrives with the
        # content it belongs to and is task-local by construction.
        #
        # And there is no other way in: `recall_secret`, `update_secrets_filter`
        # and `self_help` are the only tools this service exposes — there is NO
        # enumerate-secrets tool — and after this change `list_all_secrets()`
        # has no caller that reaches a prompt. So the snapshot was the sole
        # source of cross-task references, which is what makes dropping it
        # sufficient rather than merely a mitigation.
        #
        # The COUNT is retained: it is situational awareness ("secrets exist")
        # and addresses nothing.
        detected_secrets: List[str] = []
        all_secrets = await secrets_service.list_all_secrets()

        # Filter version comes from the substrate catalog envelope
        filter_config = await secrets_service.get_filter_config()
        _raw_version = filter_config.get("version", 0)
        filter_version = int(_raw_version) if isinstance(_raw_version, (int, float, str)) else 0

        # Get total count
        total_secrets = len(all_secrets)

        return {
            "detected_secrets": detected_secrets,
            "secrets_filter_version": filter_version,
            "total_secrets_stored": total_secrets,
        }

    except Exception as e:  # pragma: no cover - defensive
        logger.exception("Error building secrets snapshot")
        return {
            "detected_secrets": [],
            "secrets_filter_version": 0,
            "total_secrets_stored": 0,
            ERROR_KEY: f"Failed to build secrets snapshot: {type(e).__name__}: {e}",
        }
