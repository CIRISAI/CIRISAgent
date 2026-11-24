"""Unit tests for #1344 medical prohibition hardening terms."""

from __future__ import annotations

import pytest

from ciris_engine.logic.buses.prohibitions import MEDICAL_CAPABILITIES, get_capability_category

ADDED_MEDICAL_TERMS = (
    "physiological",
    "biological_monitoring",
    "biosensing",
    "biometric",
    "biometric_analysis",
    "care_coordination",
    "care_management",
    "emergency_assessment",
    "preventive_care",
    "integrative_care",
)

RETAINED_MEDICAL_TERMS = (
    "wellness",
    "wellbeing",
    "vitals",
    "vital_signs",
)


class TestMedicalProhibitionHardening:
    @pytest.mark.parametrize("term", ADDED_MEDICAL_TERMS)
    def test_added_medical_term_is_prohibited(self, term: str) -> None:
        assert term in MEDICAL_CAPABILITIES
        assert get_capability_category(term) == "MEDICAL"

    @pytest.mark.parametrize("term", RETAINED_MEDICAL_TERMS)
    def test_existing_wellness_and_vitals_terms_remain_prohibited(self, term: str) -> None:
        assert term in MEDICAL_CAPABILITIES
        assert get_capability_category(term) == "MEDICAL"

    def test_biometric_does_not_downgrade_stricter_categories(self) -> None:
        assert get_capability_category("biometric_categorization") == "SURVEILLANCE_MASS"
        assert get_capability_category("biometric_verification") == "IDENTITY_VERIFICATION"
