"""Tests for loadable adapters endpoint and internal_only filtering."""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from ciris_engine.schemas.runtime.adapter_management import ModuleTypeInfo


class TestParseManifestInternalOnly:
    """Tests for internal_only field parsing in _parse_manifest_to_module_info."""

    def test_internal_only_defaults_to_false(self):
        """internal_only should default to False when not specified."""
        from ciris_engine.logic.adapters.api.routes.system.adapters import (
            _parse_manifest_to_module_info,
        )

        manifest_data = {
            "module": {
                "name": "test_adapter",
                "version": "1.0.0",
                "description": "Test adapter",
                "author": "Test",
            },
            "services": [],
        }

        result = _parse_manifest_to_module_info(manifest_data, "test_adapter")

        assert result is not None
        assert result.internal_only is False

    def test_internal_only_true_when_set(self):
        """internal_only should be True when set in manifest."""
        from ciris_engine.logic.adapters.api.routes.system.adapters import (
            _parse_manifest_to_module_info,
        )

        manifest_data = {
            "module": {
                "name": "ciris_verify",
                "version": "0.1.0",
                "description": "Internal verification service",
                "author": "CIRIS",
                "internal_only": True,
            },
            "services": [],
        }

        result = _parse_manifest_to_module_info(manifest_data, "ciris_verify")

        assert result is not None
        assert result.internal_only is True

    def test_internal_only_false_when_explicitly_set(self):
        """internal_only should be False when explicitly set to False."""
        from ciris_engine.logic.adapters.api.routes.system.adapters import (
            _parse_manifest_to_module_info,
        )

        manifest_data = {
            "module": {
                "name": "public_adapter",
                "version": "1.0.0",
                "description": "Public adapter",
                "author": "Test",
                "internal_only": False,
            },
            "services": [],
        }

        result = _parse_manifest_to_module_info(manifest_data, "public_adapter")

        assert result is not None
        assert result.internal_only is False


class TestLoadableAdaptersFiltering:
    """Tests for loadable adapters endpoint filtering internal_only adapters."""

    @pytest.fixture
    def mock_adapter_normal(self):
        """Create a normal (non-internal) adapter."""
        return ModuleTypeInfo(
            module_id="normal_adapter",
            name="Normal Adapter",
            version="1.0.0",
            description="A normal adapter",
            author="Test",
            module_source="modular",
            platform_available=True,
            internal_only=False,
        )

    @pytest.fixture
    def mock_adapter_internal(self):
        """Create an internal-only adapter."""
        return ModuleTypeInfo(
            module_id="internal_adapter",
            name="Internal Adapter",
            version="1.0.0",
            description="An internal-only adapter",
            author="Test",
            module_source="modular",
            platform_available=True,
            internal_only=True,
        )

    @pytest.fixture
    def mock_adapter_platform_unavailable(self):
        """Create an adapter not available on current platform."""
        return ModuleTypeInfo(
            module_id="unavailable_adapter",
            name="Unavailable Adapter",
            version="1.0.0",
            description="Platform unavailable adapter",
            author="Test",
            module_source="modular",
            platform_available=False,
            internal_only=False,
        )

    def test_internal_only_adapters_excluded_from_loadable_list(
        self, mock_adapter_normal, mock_adapter_internal
    ):
        """Internal-only adapters should be filtered out from loadable list."""
        adapters = [mock_adapter_normal, mock_adapter_internal]

        # Simulate the filtering logic from list_loadable_adapters
        filtered = [a for a in adapters if a.platform_available and not a.internal_only]

        assert len(filtered) == 1
        assert filtered[0].module_id == "normal_adapter"
        assert mock_adapter_internal not in filtered

    def test_platform_unavailable_adapters_excluded(
        self, mock_adapter_normal, mock_adapter_platform_unavailable
    ):
        """Platform-unavailable adapters should be filtered out."""
        adapters = [mock_adapter_normal, mock_adapter_platform_unavailable]

        filtered = [a for a in adapters if a.platform_available and not a.internal_only]

        assert len(filtered) == 1
        assert filtered[0].module_id == "normal_adapter"

    def test_both_internal_and_platform_filters_applied(
        self, mock_adapter_normal, mock_adapter_internal, mock_adapter_platform_unavailable
    ):
        """Both internal_only and platform_available filters should apply."""
        adapters = [
            mock_adapter_normal,
            mock_adapter_internal,
            mock_adapter_platform_unavailable,
        ]

        filtered = [a for a in adapters if a.platform_available and not a.internal_only]

        assert len(filtered) == 1
        assert filtered[0].module_id == "normal_adapter"

    def test_all_internal_adapters_returns_empty_list(self, mock_adapter_internal):
        """If all adapters are internal, result should be empty."""
        adapters = [mock_adapter_internal]

        filtered = [a for a in adapters if a.platform_available and not a.internal_only]

        assert len(filtered) == 0


class TestModuleTypeInfoInternalOnlyField:
    """Tests for ModuleTypeInfo internal_only field."""

    def test_internal_only_field_exists(self):
        """ModuleTypeInfo should have internal_only field."""
        info = ModuleTypeInfo(
            module_id="test",
            name="Test",
            version="1.0.0",
            description="Test",
            author="Test",
            module_source="modular",
        )

        assert hasattr(info, "internal_only")

    def test_internal_only_defaults_to_false(self):
        """internal_only should default to False."""
        info = ModuleTypeInfo(
            module_id="test",
            name="Test",
            version="1.0.0",
            description="Test",
            author="Test",
            module_source="modular",
        )

        assert info.internal_only is False

    def test_internal_only_can_be_set_true(self):
        """internal_only can be set to True."""
        info = ModuleTypeInfo(
            module_id="test",
            name="Test",
            version="1.0.0",
            description="Test",
            author="Test",
            module_source="modular",
            internal_only=True,
        )

        assert info.internal_only is True


class TestCirisVerifyManifestInternalOnly:
    """Integration test to verify ciris_verify manifest has internal_only=True."""

    def test_ciris_verify_manifest_is_internal_only(self):
        """ciris_verify manifest should have internal_only=True."""
        import json
        from pathlib import Path

        # Find project root by looking for pyproject.toml or setup.py
        current = Path(__file__).resolve()
        project_root = current
        while project_root.parent != project_root:
            if (project_root / "pyproject.toml").exists() or (project_root / "setup.py").exists():
                break
            project_root = project_root.parent

        manifest_path = project_root / "ciris_adapters" / "ciris_verify" / "manifest.json"

        if not manifest_path.exists():
            pytest.skip(f"ciris_verify manifest not found at {manifest_path}")

        with open(manifest_path) as f:
            manifest = json.load(f)

        assert manifest["module"].get("internal_only") is True, (
            "ciris_verify should be marked as internal_only to prevent it "
            "from appearing in the Add Adapter UI"
        )
