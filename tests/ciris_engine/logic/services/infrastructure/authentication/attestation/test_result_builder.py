"""Tests for attestation result_builder module."""

import pytest

from ciris_engine.logic.services.infrastructure.authentication.attestation.result_builder import (
    _build_file_integrity_fields,
    _build_module_integrity_fields,
    _build_python_integrity_fields,
    _build_self_verification_fields,
    _count_agreeing_sources,
    _extract_file_integrity,
    _extract_key_attestation,
    _extract_module_integrity,
    _extract_sources,
    build_attestation_result,
)
from ciris_engine.logic.services.infrastructure.authentication.attestation.types import VerifyThreadResult


class TestExtractSources:
    """Tests for _extract_sources function."""

    def test_extracts_sources(self):
        """Test extracting sources from attestation."""
        attestation = {"sources": {"dns_us_valid": True}}
        assert _extract_sources(attestation) == {"dns_us_valid": True}

    def test_returns_empty_dict_when_missing(self):
        """Test returning empty dict when sources missing."""
        assert _extract_sources({}) == {}

    def test_returns_empty_dict_when_none(self):
        """Test returning empty dict when sources is None."""
        assert _extract_sources({"sources": None}) == {}


class TestExtractKeyAttestation:
    """Tests for _extract_key_attestation function."""

    def test_extracts_key_attestation(self):
        """Test extracting key attestation."""
        attestation = {"key_attestation": {"key_type": "portal"}}
        assert _extract_key_attestation(attestation) == {"key_type": "portal"}

    def test_returns_empty_dict_when_missing(self):
        """Test returning empty dict when missing."""
        assert _extract_key_attestation({}) == {}


class TestExtractFileIntegrity:
    """Tests for _extract_file_integrity function."""

    def test_extracts_flat_file_integrity(self):
        """Test extracting flat file integrity."""
        attestation = {"file_integrity": {"valid": True}}
        assert _extract_file_integrity(attestation) == {"valid": True}

    def test_extracts_nested_full_key(self):
        """Test extracting nested 'full' key."""
        attestation = {"file_integrity": {"full": {"valid": True}}}
        assert _extract_file_integrity(attestation) == {"valid": True}

    def test_returns_empty_dict_when_missing(self):
        """Test returning empty dict when missing."""
        assert _extract_file_integrity({}) == {}


class TestExtractModuleIntegrity:
    """Tests for _extract_module_integrity function."""

    def test_extracts_module_integrity(self):
        """Test extracting module integrity."""
        attestation = {
            "module_integrity": {
                "valid": True,
                "summary": "OK",
                "cross_validated": ["mod1"],
                "filesystem_verified": ["mod2"],
                "agent_verified": ["mod3"],
            }
        }
        result = _extract_module_integrity(attestation)
        assert result["valid"] is True
        assert result["summary"] == "OK"

    def test_returns_empty_dict_when_missing(self):
        """Test returning empty dict when missing."""
        assert _extract_module_integrity({}) == {}


class TestCountAgreeSources:
    """Tests for _count_agreeing_sources function."""

    @staticmethod
    def _sources(*checks):
        return {
            "sources": [
                {"endpoint": f"https://h{n}", "reachable": r, "verified": v, "bundle_fingerprint": fp}
                for n, (r, v, fp) in enumerate(checks)
            ],
            "trust_root": {"version": 4, "bundle_fingerprint": "sha256:a"},
            "validation_status": "AllSourcesAgree",
        }

    def test_counts_hosts_that_verified_the_selected_root(self):
        sources = self._sources((True, True, "sha256:a"), (True, True, "sha256:a"), (True, False, None))
        assert _count_agreeing_sources(sources) == 2

    def test_a_different_bundle_does_not_agree(self):
        assert _count_agreeing_sources(self._sources((True, True, "sha256:b"))) == 0

    def test_no_selected_root_means_no_agreement(self):
        sources = self._sources((True, True, "sha256:a"))
        del sources["trust_root"]
        assert _count_agreeing_sources(sources) == 0

    def test_counts_none_agreeing(self):
        """Test counting no agreeing sources."""
        sources = {}
        assert _count_agreeing_sources(sources) == 0


class TestBuildFileIntegrityFields:
    """Tests for _build_file_integrity_fields function."""

    def test_builds_from_valid_data(self):
        """Test building from valid file integrity data."""
        file_integrity = {
            "valid": True,
            "total_files": 100,
            "files_checked": 100,
            "files_passed": 100,
            "files_failed": 0,
        }
        fields = _build_file_integrity_fields(file_integrity, level=4)
        assert fields["file_integrity_ok"] is True
        assert fields["total_files"] == 100

    def test_builds_from_empty_data_with_level(self):
        """Test building from empty data using level."""
        fields = _build_file_integrity_fields({}, level=4)
        assert fields["file_integrity_ok"] is True  # Level >= 4

    def test_builds_from_empty_data_without_level(self):
        """Test building from empty data without level."""
        fields = _build_file_integrity_fields({}, level=3)
        assert fields["file_integrity_ok"] is False  # Level < 4


class TestBuildPythonIntegrityFields:
    """Tests for _build_python_integrity_fields function."""

    def test_builds_from_valid_data(self):
        """Test building from valid Python integrity data."""
        python_integrity = {
            "valid": True,
            "modules_checked": 50,
            "modules_passed": 50,
            "modules_failed": 0,
            "actual_total_hash": "abc123",
            "total_hash_valid": True,
        }
        fields = _build_python_integrity_fields(python_integrity)
        assert fields["python_integrity_ok"] is True
        assert fields["python_modules_checked"] == 50

    def test_builds_from_empty_data(self):
        """Test building from empty data."""
        fields = _build_python_integrity_fields({})
        assert fields["python_integrity_ok"] is False
        assert fields["python_modules_checked"] is None


class TestBuildModuleIntegrityFields:
    """Tests for _build_module_integrity_fields function."""

    def test_builds_from_valid_data(self):
        """Test building from valid module integrity data."""
        module_integrity = {
            "valid": True,
            "summary": "All modules verified",
            "cross_validated": ["mod1", "mod2"],
            "filesystem_verified": ["mod3"],
            "agent_verified": ["mod4"],
        }
        fields = _build_module_integrity_fields(module_integrity)
        assert fields["module_integrity_ok"] is True
        assert fields["module_integrity_summary"] == "All modules verified"

    def test_truncates_to_50_items(self):
        """Test truncating lists to 50 items."""
        module_integrity = {
            "valid": True,
            "cross_validated": [f"mod{i}" for i in range(100)],
            "filesystem_verified": [],
            "agent_verified": [],
        }
        fields = _build_module_integrity_fields(module_integrity)
        assert len(fields["cross_validated_files"]) == 50


class TestBuildSelfVerificationFields:
    """Tests for _build_self_verification_fields function."""

    def test_builds_from_valid_data(self):
        """Test building from valid self verification data."""
        self_verification = {
            "binary_valid": True,
            "binary_hash": "abc123",
            "functions_valid": True,
            "functions_checked": 10,
            "functions_passed": 10,
            "target": "x86_64-unknown-linux-gnu",
        }
        fields = _build_self_verification_fields(self_verification, {})
        assert fields["binary_self_check"] == "verified"
        assert fields["function_self_check"] == "verified"
        assert fields["functions_checked"] == 10

    def test_falls_back_to_python_integrity(self):
        """Test falling back to python_integrity for function counts."""
        self_verification = {}
        python_integrity = {
            "modules_checked": 20,
            "modules_passed": 20,
        }
        fields = _build_self_verification_fields(self_verification, python_integrity)
        assert fields["functions_checked"] == 20
        assert fields["functions_passed"] == 20


class TestBuildAttestationResult:
    """Tests for build_attestation_result function."""

    def test_builds_error_result(self):
        """Test building result from error."""
        verify_result = VerifyThreadResult(error="Test error")
        result = build_attestation_result(verify_result, "full")

        assert result.loaded is False
        assert result.error == "Test error"
        assert result.attestation_status == "failed"

    def test_builds_success_result(self):
        """Test building result from successful verification."""
        verify_result = VerifyThreadResult(
            result={
                "version": "1.0.0",
                "attestation": {
                    "valid": True,
                    "level": 4,
                    "sources": {
                        "sources": [
                            {"endpoint": "https://h", "reachable": True, "verified": True, "bundle_fingerprint": "sha256:a"}
                        ],
                        "trust_root": {"version": 4, "bundle_fingerprint": "sha256:a"},
                        "validation_status": "AllSourcesAgree",
                    },
                    "key_attestation": {"key_type": "portal"},
                    "self_verification": {"binary_valid": True},
                },
            }
        )
        result = build_attestation_result(verify_result, "full")

        assert result.loaded is True
        assert result.version == "1.0.0"
        # An unreachable reading here would skip the tamper check every cycle (#862).
        assert result.registry_reachable is True
        assert result.sources_agreeing == 1
        assert result.https_us_ok is True
        assert result.dns_us_ok is False
        assert result.max_level == 4
        assert result.attestation_status == "verified"

    def test_builds_partial_result(self):
        """Test building result when not fully valid."""
        verify_result = VerifyThreadResult(
            result={
                "version": "1.0.0",
                "attestation": {
                    "valid": False,
                    "level": 2,
                },
            }
        )
        result = build_attestation_result(verify_result, "partial")

        assert result.loaded is True
        assert result.attestation_status == "partial"
        assert result.max_level == 2
