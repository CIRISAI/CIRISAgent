"""Unit tests for authentication store helpers."""

import json
from unittest.mock import patch

import pytest

from ciris_engine.logic.persistence.stores.auth_helpers import (
    build_wa_certificate_dict,
    normalize_json_field,
    parse_oauth_links,
)
from ciris_engine.schemas.services.authority_core import OAuthIdentityLink


class TestParseOAuthLinks:
    """Tests for parse_oauth_links()."""

    def test_parse_oauth_links_valid_json(self):
        """Test parsing valid OAuth links JSON."""
        oauth_json = json.dumps([
            {
                "provider": "google",
                "external_id": "123456",
                "email": "user@example.com",
                "linked_at": "2025-01-01T12:00:00Z",
            },
            {
                "provider": "github",
                "external_id": "github_user_id",
                "username": "testuser",
                "linked_at": "2025-01-02T12:00:00Z",
            },
        ])

        result = parse_oauth_links(oauth_json)

        assert len(result) == 2
        assert isinstance(result[0], OAuthIdentityLink)
        assert result[0].provider == "google"
        assert result[0].external_id == "123456"
        assert result[1].provider == "github"
        assert result[1].external_id == "github_user_id"

    def test_parse_oauth_links_none(self):
        """Test parsing None returns empty list."""
        result = parse_oauth_links(None)
        assert result == []

    def test_parse_oauth_links_empty_string(self):
        """Test parsing empty string returns empty list."""
        result = parse_oauth_links("")
        assert result == []

    def test_parse_oauth_links_invalid_json(self):
        """Test parsing invalid JSON returns empty list."""
        result = parse_oauth_links("{invalid json")
        assert result == []

    def test_parse_oauth_links_invalid_schema(self):
        """Test invalid OAuth link schema is skipped with warning."""
        oauth_json = json.dumps([
            {
                "provider": "google",
                "external_id": "123456",
                "linked_at": "2025-01-01T12:00:00Z",
            },
            {
                # Missing required fields
                "provider": "github",
            },
            {
                "provider": "microsoft",
                "external_id": "ms_id",
                "linked_at": "2025-01-03T12:00:00Z",
            },
        ])

        with patch("ciris_engine.logic.persistence.stores.auth_helpers.logger") as mock_logger:
            result = parse_oauth_links(oauth_json)

            # Should have 2 valid links, 1 invalid skipped
            assert len(result) == 2
            assert result[0].provider == "google"
            assert result[1].provider == "microsoft"
            # Warning should be logged for invalid entry
            assert mock_logger.warning.called

    def test_parse_oauth_links_non_string(self):
        """Test parsing non-string value returns empty list."""
        result = parse_oauth_links(123)
        assert result == []

    def test_parse_oauth_links_single_link(self):
        """Test parsing single OAuth link."""
        oauth_json = json.dumps([
            {
                "provider": "google",
                "external_id": "google_id",
                "email": "test@example.com",
                "linked_at": "2025-01-01T00:00:00Z",
            }
        ])

        result = parse_oauth_links(oauth_json)

        assert len(result) == 1
        assert result[0].provider == "google"
        assert result[0].external_id == "google_id"


class TestNormalizeJSONField:
    """Tests for normalize_json_field()."""

    def test_normalize_json_string(self):
        """Test string JSON is returned as-is."""
        json_str = '{"key": "value"}'
        result = normalize_json_field(json_str)
        assert result == json_str

    def test_normalize_json_dict(self):
        """Test dict is serialized to JSON string."""
        json_dict = {"key": "value", "number": 123}
        result = normalize_json_field(json_dict)
        assert result == '{"key": "value", "number": 123}'

    def test_normalize_json_list(self):
        """Test list is serialized to JSON string."""
        json_list = ["item1", "item2", "item3"]
        result = normalize_json_field(json_list)
        assert result == '["item1", "item2", "item3"]'

    def test_normalize_json_none(self):
        """Test None returns None."""
        result = normalize_json_field(None)
        assert result is None

    def test_normalize_json_nested_dict(self):
        """Test nested dict is properly serialized."""
        nested = {"outer": {"inner": {"value": 42}}}
        result = normalize_json_field(nested)
        parsed = json.loads(result)
        assert parsed["outer"]["inner"]["value"] == 42

    def test_normalize_json_postgresql_jsonb(self):
        """Test PostgreSQL JSONB dict is serialized."""
        # Simulate PostgreSQL JSONB returning parsed dict
        jsonb_data = {"scopes": ["read", "write"], "permissions": ["admin"]}
        result = normalize_json_field(jsonb_data)
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed["scopes"] == ["read", "write"]
        assert parsed["permissions"] == ["admin"]

    def test_normalize_json_empty_dict(self):
        """Test empty dict is serialized."""
        result = normalize_json_field({})
        assert result == "{}"

    def test_normalize_json_empty_string(self):
        """Test empty string is returned as-is."""
        result = normalize_json_field("")
        assert result == ""


class TestBuildWACertificateDict:
    """Tests for build_wa_certificate_dict()."""

    def test_build_wa_certificate_dict_complete(self):
        """Test building complete WA certificate dict."""
        row_dict = {
            "wa_id": "wa_123",
            "name": "Test User",
            "role": "admin",
            "pubkey": "pubkey123",
            "jwt_kid": "kid123",
            "password_hash": "hash123",
            "api_key_hash": "api_hash",
            "oauth_provider": "google",
            "oauth_external_id": "google_123",
            "oauth_links_json": json.dumps([
                {
                    "provider": "github",
                    "external_id": "github_id",
                    "linked_at": "2025-01-01T00:00:00Z",
                }
            ]),
            "auto_minted": 1,
            "veilid_id": "veilid_123",
            "parent_wa_id": "parent_wa",
            "parent_signature": "sig123",
            "scopes_json": '["read", "write"]',
            "custom_permissions_json": '["admin"]',
            "adapter_id": "adapter_123",
            "adapter_name": "test_adapter",
            "adapter_metadata_json": '{"key": "value"}',
            "created": "2025-01-01T00:00:00Z",
            "last_login": "2025-01-02T00:00:00Z",
        }

        result = build_wa_certificate_dict(row_dict)

        assert result["wa_id"] == "wa_123"
        assert result["name"] == "Test User"
        assert result["role"] == "admin"
        assert result["pubkey"] == "pubkey123"
        assert result["jwt_kid"] == "kid123"
        assert result["password_hash"] == "hash123"
        assert result["oauth_provider"] == "google"
        assert result["oauth_external_id"] == "google_123"
        assert len(result["oauth_links"]) == 1
        assert result["oauth_links"][0].provider == "github"
        assert result["auto_minted"] is True
        assert result["scopes_json"] == '["read", "write"]'
        assert result["custom_permissions_json"] == '["admin"]'
        assert result["adapter_id"] == "adapter_123"
        assert result["created_at"] == "2025-01-01T00:00:00Z"
        assert result["last_auth"] == "2025-01-02T00:00:00Z"

    def test_build_wa_certificate_dict_minimal(self):
        """Test building minimal WA certificate dict."""
        row_dict = {
            "wa_id": "wa_minimal",
            "name": "Minimal User",
            "role": "user",
            "pubkey": "pubkey",
            "jwt_kid": "kid",
            "scopes_json": "[]",
            "created": "2025-01-01T00:00:00Z",
        }

        result = build_wa_certificate_dict(row_dict)

        assert result["wa_id"] == "wa_minimal"
        assert result["name"] == "Minimal User"
        assert result["role"] == "user"
        assert result["oauth_links"] == []
        assert result["auto_minted"] is False
        assert result["password_hash"] is None
        assert result["custom_permissions_json"] is None

    def test_build_wa_certificate_dict_postgresql_jsonb(self):
        """Test building dict with PostgreSQL JSONB fields."""
        # PostgreSQL JSONB returns parsed dicts/lists
        row_dict = {
            "wa_id": "wa_pg",
            "name": "PG User",
            "role": "user",
            "pubkey": "pubkey",
            "jwt_kid": "kid",
            "scopes_json": ["read", "write"],  # JSONB returns list
            "custom_permissions_json": {"admin": True},  # JSONB returns dict
            "adapter_metadata_json": {"meta": "data"},  # JSONB returns dict
            "created": "2025-01-01T00:00:00Z",
        }

        result = build_wa_certificate_dict(row_dict)

        # Should be normalized to JSON strings
        assert isinstance(result["scopes_json"], str)
        assert isinstance(result["custom_permissions_json"], str)
        assert isinstance(result["adapter_metadata_json"], str)

        # Verify content is preserved
        assert json.loads(result["scopes_json"]) == ["read", "write"]
        assert json.loads(result["custom_permissions_json"]) == {"admin": True}

    def test_build_wa_certificate_dict_no_oauth_links(self):
        """Test building dict without OAuth links."""
        row_dict = {
            "wa_id": "wa_no_oauth",
            "name": "No OAuth User",
            "role": "user",
            "pubkey": "pubkey",
            "jwt_kid": "kid",
            "scopes_json": "[]",
            "oauth_links_json": None,
            "created": "2025-01-01T00:00:00Z",
        }

        result = build_wa_certificate_dict(row_dict)

        assert result["oauth_links"] == []

    def test_build_wa_certificate_dict_auto_minted_conversion(self):
        """Test auto_minted conversion from integer to boolean."""
        # SQLite returns integers for booleans
        row_dict_true = {
            "wa_id": "wa_auto",
            "name": "Auto User",
            "role": "user",
            "pubkey": "pubkey",
            "jwt_kid": "kid",
            "scopes_json": "[]",
            "auto_minted": 1,
            "created": "2025-01-01T00:00:00Z",
        }

        row_dict_false = {
            **row_dict_true,
            "auto_minted": 0,
        }

        result_true = build_wa_certificate_dict(row_dict_true)
        result_false = build_wa_certificate_dict(row_dict_false)

        assert result_true["auto_minted"] is True
        assert result_false["auto_minted"] is False

    def test_build_wa_certificate_dict_null_json_fields(self):
        """Test handling of NULL JSON fields."""
        row_dict = {
            "wa_id": "wa_nulls",
            "name": "Null Fields User",
            "role": "user",
            "pubkey": "pubkey",
            "jwt_kid": "kid",
            "scopes_json": "[]",
            "custom_permissions_json": None,
            "adapter_metadata_json": None,
            "created": "2025-01-01T00:00:00Z",
        }

        result = build_wa_certificate_dict(row_dict)

        assert result["custom_permissions_json"] is None
        assert result["adapter_metadata_json"] is None
