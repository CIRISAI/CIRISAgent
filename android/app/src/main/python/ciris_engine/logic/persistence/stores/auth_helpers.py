"""Authentication store helper functions for cognitive complexity reduction.

This module provides helper functions to reduce cognitive complexity in
authentication_store.py, particularly for JSON field parsing and WA certificate building.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from ciris_engine.schemas.services.authority_core import OAuthIdentityLink, WACertificate

logger = logging.getLogger(__name__)


def parse_oauth_links(oauth_links_json: Any) -> List[OAuthIdentityLink]:
    """Parse oauth_links JSON field into OAuthIdentityLink objects.

    Args:
        oauth_links_json: Raw JSON value from database (could be str or None)

    Returns:
        List of OAuthIdentityLink objects (empty if parsing fails)

    Handles both PostgreSQL JSONB (returns parsed) and SQLite TEXT (returns string).
    """
    oauth_links: List[OAuthIdentityLink] = []

    if not oauth_links_json:
        return oauth_links

    try:
        # Type narrow: json.loads expects str
        if isinstance(oauth_links_json, str):
            raw_links = json.loads(oauth_links_json)
            for link in raw_links:
                try:
                    oauth_links.append(OAuthIdentityLink(**link))
                except Exception as exc:
                    logger.warning("Invalid OAuth link entry skipped: %s", exc)
    except json.JSONDecodeError as e:
        logger.warning("Invalid oauth_links_json: %s", e)

    return oauth_links


def normalize_json_field(raw_value: Any) -> Optional[str]:
    """Normalize JSON field for database storage.

    PostgreSQL JSONB returns parsed objects, SQLite TEXT returns strings.
    This function ensures we always get a JSON string for WACertificate fields.

    Args:
        raw_value: Raw value from database (could be str, dict, list, or None)

    Returns:
        JSON string if value exists, None otherwise

    Examples:
        normalize_json_field('{"key": "value"}') -> '{"key": "value"}'
        normalize_json_field({'key': 'value'}) -> '{"key": "value"}'
        normalize_json_field(None) -> None
    """
    if raw_value is None:
        return None

    if isinstance(raw_value, str):
        return raw_value
    else:
        # PostgreSQL JSONB returns parsed object - serialize it
        return json.dumps(raw_value)


def build_wa_certificate_dict(row_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Build WACertificate constructor dict from database row.

    This extracts the complex field mapping logic from _row_to_wa() to reduce
    cognitive complexity.

    Args:
        row_dict: Database row as dictionary

    Returns:
        Dictionary suitable for WACertificate(**dict) construction
    """
    # Parse OAuth links
    oauth_links = parse_oauth_links(row_dict.get("oauth_links_json"))

    # Normalize JSON fields (handles PostgreSQL JSONB vs SQLite TEXT)
    scopes_json = normalize_json_field(row_dict["scopes_json"])
    custom_permissions_json = normalize_json_field(row_dict.get("custom_permissions_json"))
    adapter_metadata_json = normalize_json_field(row_dict.get("adapter_metadata_json"))

    # Build WACertificate constructor dict
    return {
        "wa_id": row_dict["wa_id"],
        "name": row_dict["name"],
        "role": row_dict["role"],
        "pubkey": row_dict["pubkey"],
        "jwt_kid": row_dict["jwt_kid"],
        "password_hash": row_dict.get("password_hash"),
        "api_key_hash": row_dict.get("api_key_hash"),
        "oauth_provider": row_dict.get("oauth_provider"),
        "oauth_external_id": row_dict.get("oauth_external_id"),
        "oauth_links": oauth_links,
        "auto_minted": bool(row_dict.get("auto_minted", 0)),
        "veilid_id": row_dict.get("veilid_id"),
        "parent_wa_id": row_dict.get("parent_wa_id"),
        "parent_signature": row_dict.get("parent_signature"),
        "scopes_json": scopes_json,
        "custom_permissions_json": custom_permissions_json,
        "adapter_id": row_dict.get("adapter_id"),
        "adapter_name": row_dict.get("adapter_name"),
        "adapter_metadata_json": adapter_metadata_json,
        "created_at": row_dict["created"],
        "last_auth": row_dict.get("last_login"),
    }
