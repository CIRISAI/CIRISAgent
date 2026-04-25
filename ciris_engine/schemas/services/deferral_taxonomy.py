"""Rights-based taxonomy for deferrals and prohibited-capability routing.

The taxonomy is grounded in internationally recognized human rights
frameworks, primarily the ICCPR and ICESCR families of rights. It provides:

1. A primary rights/needs category for every deferral.
2. Exhaustive coverage for every prohibited capability category.
3. A prompt-ready representation for defer-specific second-pass evaluation.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List

from ciris_engine.schemas.services.agent_credits import DomainCategory


class DeferralNeedCategory(str, Enum):
    """Primary human-rights / needs category implicated by a deferral."""

    HEALTH_AND_BODILY_INTEGRITY = "health_and_bodily_integrity"
    ADEQUATE_STANDARD_OF_LIVING_AND_SERVICES = "adequate_standard_of_living_and_services"
    LIVELIHOOD_AND_FINANCIAL_SECURITY = "livelihood_and_financial_security"
    JUSTICE_AND_LEGAL_AGENCY = "justice_and_legal_agency"
    IDENTITY_AND_CIVIC_PARTICIPATION = "identity_and_civic_participation"
    PRIVACY_AUTONOMY_AND_DIGNITY = "privacy_autonomy_and_dignity"
    EDUCATION_CULTURE_AND_SCIENTIFIC_PARTICIPATION = "education_culture_and_scientific_participation"
    COMMUNITY_AND_COLLECTIVE_SAFETY = "community_and_collective_safety"
    GENERAL_HUMAN_OVERSIGHT = "general_human_oversight"


class DeferralOperationalReason(str, Enum):
    """Operational explanation for why the agent deferred."""

    LICENSED_DOMAIN_REQUIRED = "licensed_domain_required"
    RIGHTS_IMPACT_REVIEW = "rights_impact_review"
    SAFETY_ESCALATION = "safety_escalation"
    CONSENT_OR_AUTHORITY_REQUIRED = "consent_or_authority_required"
    INSUFFICIENT_CONTEXT = "insufficient_context"
    POLICY_REVIEW_REQUIRED = "policy_review_required"
    RESOURCE_OR_SYSTEM_LIMITATION = "resource_or_system_limitation"
    TIME_BASED_REVIEW = "time_based_review"
    ETHICAL_UNCERTAINTY = "ethical_uncertainty"
    UNKNOWN = "unknown"


NEED_CATEGORY_DESCRIPTIONS: Dict[DeferralNeedCategory, str] = {
    DeferralNeedCategory.HEALTH_AND_BODILY_INTEGRITY: (
        "Use for life, health, bodily integrity, disability, medical safety, weaponization, hazardous materials, "
        "or direct physical-harm implications."
    ),
    DeferralNeedCategory.ADEQUATE_STANDARD_OF_LIVING_AND_SERVICES: (
        "Use for housing, shelter, home security, food, water, sanitation, energy, infrastructure, "
        "and other essential living conditions."
    ),
    DeferralNeedCategory.LIVELIHOOD_AND_FINANCIAL_SECURITY: (
        "Use for work, income, wages, debt, credit, benefits, social security, investment, taxes, "
        "or other material livelihood and financial-stability needs."
    ),
    DeferralNeedCategory.JUSTICE_AND_LEGAL_AGENCY: (
        "Use for legal advice, legal aid, due process, fair trial, access to remedy, contracts, "
        "liability, or other justice-system access questions."
    ),
    DeferralNeedCategory.IDENTITY_AND_CIVIC_PARTICIPATION: (
        "Use for recognition before the law, identity verification, nationality, voting, elections, "
        "public participation, or civic standing."
    ),
    DeferralNeedCategory.PRIVACY_AUTONOMY_AND_DIGNITY: (
        "Use for privacy, autonomy, dignity, freedom from coercion, fraud, manipulation, biometric inference, "
        "or surveillance concerns."
    ),
    DeferralNeedCategory.EDUCATION_CULTURE_AND_SCIENTIFIC_PARTICIPATION: (
        "Use for education, research, access to knowledge, cultural participation, and the benefits of science."
    ),
    DeferralNeedCategory.COMMUNITY_AND_COLLECTIVE_SAFETY: (
        "Use for community moderation, crisis escalation, pattern detection, public safety, discrimination, "
        "or harms that primarily affect groups rather than one person alone."
    ),
    DeferralNeedCategory.GENERAL_HUMAN_OVERSIGHT: (
        "Use when the deferral is mostly about uncertainty, policy interpretation, authority boundaries, "
        "or non-domain-specific human oversight."
    ),
}

NEED_CATEGORY_DESCRIPTIONS_LOCALIZED: Dict[str, Dict[DeferralNeedCategory, str]] = {
    "en": NEED_CATEGORY_DESCRIPTIONS,
    "es": {
        DeferralNeedCategory.HEALTH_AND_BODILY_INTEGRITY: (
            "Úsalo para vida, salud, integridad corporal, discapacidad, seguridad médica, "
            "weaponización, materiales peligrosos o implicaciones directas de daño físico."
        ),
        DeferralNeedCategory.ADEQUATE_STANDARD_OF_LIVING_AND_SERVICES: (
            "Úsalo para vivienda, refugio, seguridad del hogar, comida, agua, saneamiento, energía, "
            "infraestructura y otras condiciones esenciales de vida."
        ),
        DeferralNeedCategory.LIVELIHOOD_AND_FINANCIAL_SECURITY: (
            "Úsalo para trabajo, ingresos, salarios, deuda, crédito, beneficios, seguridad social, inversión, "
            "impuestos u otras necesidades materiales de sustento y estabilidad financiera."
        ),
        DeferralNeedCategory.JUSTICE_AND_LEGAL_AGENCY: (
            "Úsalo para asesoría legal, asistencia jurídica, debido proceso, juicio justo, acceso a remedio, "
            "contratos, responsabilidad u otras cuestiones de acceso a la justicia."
        ),
        DeferralNeedCategory.IDENTITY_AND_CIVIC_PARTICIPATION: (
            "Úsalo para reconocimiento ante la ley, verificación de identidad, nacionalidad, voto, elecciones, "
            "participación pública o condición cívica."
        ),
        DeferralNeedCategory.PRIVACY_AUTONOMY_AND_DIGNITY: (
            "Úsalo para privacidad, autonomía, dignidad, libertad frente a coerción, fraude, manipulación, "
            "inferencia biométrica o vigilancia."
        ),
        DeferralNeedCategory.EDUCATION_CULTURE_AND_SCIENTIFIC_PARTICIPATION: (
            "Úsalo para educación, investigación, acceso al conocimiento, participación cultural "
            "y beneficios del progreso científico."
        ),
        DeferralNeedCategory.COMMUNITY_AND_COLLECTIVE_SAFETY: (
            "Úsalo para moderación comunitaria, escalación de crisis, detección de patrones, seguridad pública, "
            "discriminación o daños que afectan principalmente a grupos."
        ),
        DeferralNeedCategory.GENERAL_HUMAN_OVERSIGHT: (
            "Úsalo cuando la deferencia trata sobre incertidumbre, interpretación de políticas, "
            "límites de autoridad o supervisión humana no específica de dominio."
        ),
    },
}


NEED_CATEGORY_RIGHTS_BASIS: Dict[DeferralNeedCategory, List[str]] = {
    DeferralNeedCategory.HEALTH_AND_BODILY_INTEGRITY: [
        "right_to_life",
        "right_to_health",
        "security_of_person",
    ],
    DeferralNeedCategory.ADEQUATE_STANDARD_OF_LIVING_AND_SERVICES: [
        "adequate_standard_of_living",
        "housing",
        "food_water_sanitation",
    ],
    DeferralNeedCategory.LIVELIHOOD_AND_FINANCIAL_SECURITY: [
        "work",
        "social_security",
        "material_conditions_for_subsistence",
    ],
    DeferralNeedCategory.JUSTICE_AND_LEGAL_AGENCY: [
        "fair_trial",
        "access_to_justice",
        "legal_aid_and_effective_remedy",
    ],
    DeferralNeedCategory.IDENTITY_AND_CIVIC_PARTICIPATION: [
        "recognition_before_the_law",
        "nationality_and_identity",
        "participation_in_public_affairs",
    ],
    DeferralNeedCategory.PRIVACY_AUTONOMY_AND_DIGNITY: [
        "privacy",
        "autonomy_and_consent",
        "human_dignity",
    ],
    DeferralNeedCategory.EDUCATION_CULTURE_AND_SCIENTIFIC_PARTICIPATION: [
        "education",
        "take_part_in_cultural_life",
        "benefits_of_scientific_progress",
    ],
    DeferralNeedCategory.COMMUNITY_AND_COLLECTIVE_SAFETY: [
        "equal_protection",
        "non_discrimination",
        "collective_safety_and_protection",
    ],
    DeferralNeedCategory.GENERAL_HUMAN_OVERSIGHT: [
        "human_review_and_accountability",
    ],
}

OPERATIONAL_REASON_DESCRIPTIONS: Dict[DeferralOperationalReason, str] = {
    DeferralOperationalReason.LICENSED_DOMAIN_REQUIRED: (
        "A licensed specialist or separately governed domain handler is required."
    ),
    DeferralOperationalReason.RIGHTS_IMPACT_REVIEW: (
        "The request materially affects protected rights or core human needs and needs review."
    ),
    DeferralOperationalReason.SAFETY_ESCALATION: (
        "Potential harm or crisis conditions require immediate escalation or human oversight."
    ),
    DeferralOperationalReason.CONSENT_OR_AUTHORITY_REQUIRED: (
        "Valid consent, authorization, or accountable human authority is required first."
    ),
    DeferralOperationalReason.INSUFFICIENT_CONTEXT: (
        "The agent lacks enough reliable context to proceed responsibly."
    ),
    DeferralOperationalReason.POLICY_REVIEW_REQUIRED: (
        "A policy or governance interpretation is needed before acting."
    ),
    DeferralOperationalReason.RESOURCE_OR_SYSTEM_LIMITATION: (
        "System constraints prevent safe completion without review."
    ),
    DeferralOperationalReason.TIME_BASED_REVIEW: (
        "The decision should be reconsidered later at a specific time or after a condition changes."
    ),
    DeferralOperationalReason.ETHICAL_UNCERTAINTY: (
        "The system remains ethically uncertain and requires human judgment."
    ),
    DeferralOperationalReason.UNKNOWN: (
        "Fallback code when the operational reason remains unclear."
    ),
}

OPERATIONAL_REASON_DESCRIPTIONS_LOCALIZED: Dict[str, Dict[DeferralOperationalReason, str]] = {
    "en": OPERATIONAL_REASON_DESCRIPTIONS,
    "es": {
        DeferralOperationalReason.LICENSED_DOMAIN_REQUIRED: (
            "Se requiere un especialista con licencia o un manejador de dominio gobernado por separado."
        ),
        DeferralOperationalReason.RIGHTS_IMPACT_REVIEW: (
            "La solicitud afecta materialmente derechos protegidos o necesidades humanas básicas y requiere revisión."
        ),
        DeferralOperationalReason.SAFETY_ESCALATION: (
            "Posibles daños o condiciones de crisis requieren escalación inmediata o supervisión humana."
        ),
        DeferralOperationalReason.CONSENT_OR_AUTHORITY_REQUIRED: (
            "Primero se requiere consentimiento válido, autorización o autoridad humana responsable."
        ),
        DeferralOperationalReason.INSUFFICIENT_CONTEXT: (
            "El agente no tiene contexto fiable suficiente para proceder de forma responsable."
        ),
        DeferralOperationalReason.POLICY_REVIEW_REQUIRED: (
            "Se necesita una interpretación de política o gobernanza antes de actuar."
        ),
        DeferralOperationalReason.RESOURCE_OR_SYSTEM_LIMITATION: (
            "Las limitaciones del sistema impiden una finalización segura sin revisión."
        ),
        DeferralOperationalReason.TIME_BASED_REVIEW: (
            "La decisión debe reconsiderarse más tarde en un momento específico o tras un cambio de condición."
        ),
        DeferralOperationalReason.ETHICAL_UNCERTAINTY: (
            "El sistema sigue éticamente incierto y requiere juicio humano."
        ),
        DeferralOperationalReason.UNKNOWN: (
            "Código de respaldo cuando la razón operativa sigue sin estar clara."
        ),
    },
}


DOMAIN_TO_NEED_CATEGORY: Dict[DomainCategory, DeferralNeedCategory] = {
    DomainCategory.MEDICAL: DeferralNeedCategory.HEALTH_AND_BODILY_INTEGRITY,
    DomainCategory.FINANCIAL: DeferralNeedCategory.LIVELIHOOD_AND_FINANCIAL_SECURITY,
    DomainCategory.LEGAL: DeferralNeedCategory.JUSTICE_AND_LEGAL_AGENCY,
    DomainCategory.HOME_SECURITY: DeferralNeedCategory.ADEQUATE_STANDARD_OF_LIVING_AND_SERVICES,
    DomainCategory.IDENTITY_VERIFICATION: DeferralNeedCategory.IDENTITY_AND_CIVIC_PARTICIPATION,
    DomainCategory.CONTENT_MODERATION: DeferralNeedCategory.COMMUNITY_AND_COLLECTIVE_SAFETY,
    DomainCategory.RESEARCH: DeferralNeedCategory.EDUCATION_CULTURE_AND_SCIENTIFIC_PARTICIPATION,
    DomainCategory.INFRASTRUCTURE_CONTROL: DeferralNeedCategory.ADEQUATE_STANDARD_OF_LIVING_AND_SERVICES,
}


PROHIBITION_CATEGORY_TO_NEED_CATEGORY: Dict[str, DeferralNeedCategory] = {
    "AUTONOMOUS_DECEPTION": DeferralNeedCategory.PRIVACY_AUTONOMY_AND_DIGNITY,
    "BIOMETRIC_INFERENCE": DeferralNeedCategory.PRIVACY_AUTONOMY_AND_DIGNITY,
    "COMMUNITY_CRISIS_ESCALATION": DeferralNeedCategory.COMMUNITY_AND_COLLECTIVE_SAFETY,
    "COMMUNITY_PATTERN_DETECTION": DeferralNeedCategory.COMMUNITY_AND_COLLECTIVE_SAFETY,
    "COMMUNITY_PROTECTIVE_ROUTING": DeferralNeedCategory.COMMUNITY_AND_COLLECTIVE_SAFETY,
    "CONTENT_MODERATION": DeferralNeedCategory.COMMUNITY_AND_COLLECTIVE_SAFETY,
    "CYBER_OFFENSIVE": DeferralNeedCategory.COMMUNITY_AND_COLLECTIVE_SAFETY,
    "DECEPTION_FRAUD": DeferralNeedCategory.PRIVACY_AUTONOMY_AND_DIGNITY,
    "DISCRIMINATION": DeferralNeedCategory.COMMUNITY_AND_COLLECTIVE_SAFETY,
    "ELECTION_INTERFERENCE": DeferralNeedCategory.IDENTITY_AND_CIVIC_PARTICIPATION,
    "FINANCIAL": DeferralNeedCategory.LIVELIHOOD_AND_FINANCIAL_SECURITY,
    "HAZARDOUS_MATERIALS": DeferralNeedCategory.HEALTH_AND_BODILY_INTEGRITY,
    "HOME_SECURITY": DeferralNeedCategory.ADEQUATE_STANDARD_OF_LIVING_AND_SERVICES,
    "IDENTITY_VERIFICATION": DeferralNeedCategory.IDENTITY_AND_CIVIC_PARTICIPATION,
    "INFRASTRUCTURE_CONTROL": DeferralNeedCategory.ADEQUATE_STANDARD_OF_LIVING_AND_SERVICES,
    "LEGAL": DeferralNeedCategory.JUSTICE_AND_LEGAL_AGENCY,
    "MANIPULATION_COERCION": DeferralNeedCategory.PRIVACY_AUTONOMY_AND_DIGNITY,
    "MEDICAL": DeferralNeedCategory.HEALTH_AND_BODILY_INTEGRITY,
    "RESEARCH": DeferralNeedCategory.EDUCATION_CULTURE_AND_SCIENTIFIC_PARTICIPATION,
    "SURVEILLANCE_MASS": DeferralNeedCategory.PRIVACY_AUTONOMY_AND_DIGNITY,
    "WEAPONS_HARMFUL": DeferralNeedCategory.HEALTH_AND_BODILY_INTEGRITY,
}

SECTION_HEADERS_LOCALIZED: Dict[str, Dict[str, str]] = {
    "en": {
        "taxonomy": "=== RIGHTS / NEEDS TAXONOMY ===",
        "rights_basis": "Rights basis",
        "reasons": "=== OPERATIONAL DEFERRAL REASON CODES ===",
    },
    "es": {
        "taxonomy": "=== TAXONOMÍA DE DERECHOS / NECESIDADES ===",
        "rights_basis": "Fundamento de derechos",
        "reasons": "=== CÓDIGOS DE RAZÓN OPERATIVA DE DEFERENCIA ===",
    },
}


def _normalize_language(language: str) -> str:
    """Normalize a language code for prompt-localization lookups."""

    normalized = (language or "en").strip().lower()
    if not normalized:
        return "en"
    return normalized.split("-", 1)[0]


def get_need_category_for_domain(domain: DomainCategory) -> DeferralNeedCategory:
    """Return the primary rights-based category for a licensed domain."""

    return DOMAIN_TO_NEED_CATEGORY[domain]


def get_need_category_for_prohibition_category(category: str) -> DeferralNeedCategory:
    """Return the primary rights-based category for a prohibition category."""

    return PROHIBITION_CATEGORY_TO_NEED_CATEGORY[category]


def get_rights_basis_for_need_category(category: DeferralNeedCategory) -> List[str]:
    """Return treaty-aligned rights basis labels for a needs category."""

    return list(NEED_CATEGORY_RIGHTS_BASIS[category])


def get_need_category_description(category: DeferralNeedCategory, language: str = "en") -> str:
    """Return the localized description for a needs category."""

    normalized_language = _normalize_language(language)
    descriptions = NEED_CATEGORY_DESCRIPTIONS_LOCALIZED.get(
        normalized_language,
        NEED_CATEGORY_DESCRIPTIONS_LOCALIZED["en"],
    )
    return descriptions[category]


def get_operational_reason_description(reason: DeferralOperationalReason, language: str = "en") -> str:
    """Return the localized description for an operational deferral reason."""

    normalized_language = _normalize_language(language)
    descriptions = OPERATIONAL_REASON_DESCRIPTIONS_LOCALIZED.get(
        normalized_language,
        OPERATIONAL_REASON_DESCRIPTIONS_LOCALIZED["en"],
    )
    return descriptions[reason]


def build_deferral_taxonomy_prompt(language: str = "en") -> str:
    """Render the rights-based deferral taxonomy for prompt inclusion."""

    normalized_language = _normalize_language(language)
    headers = SECTION_HEADERS_LOCALIZED.get(normalized_language, SECTION_HEADERS_LOCALIZED["en"])

    lines: List[str] = [headers["taxonomy"]]
    for category in DeferralNeedCategory:
        description = get_need_category_description(category, normalized_language)
        rights_basis = ", ".join(NEED_CATEGORY_RIGHTS_BASIS[category])
        lines.append(f"- {category.value}: {description}")
        lines.append(f"  {headers['rights_basis']}: {rights_basis}")

    lines.append("")
    lines.append(headers["reasons"])
    for reason in DeferralOperationalReason:
        lines.append(f"- {reason.value}: {get_operational_reason_description(reason, normalized_language)}")
    return "\n".join(lines)


__all__ = [
    "DeferralNeedCategory",
    "DeferralOperationalReason",
    "DOMAIN_TO_NEED_CATEGORY",
    "PROHIBITION_CATEGORY_TO_NEED_CATEGORY",
    "NEED_CATEGORY_DESCRIPTIONS",
    "NEED_CATEGORY_RIGHTS_BASIS",
    "build_deferral_taxonomy_prompt",
    "get_need_category_description",
    "get_need_category_for_domain",
    "get_need_category_for_prohibition_category",
    "get_operational_reason_description",
    "get_rights_basis_for_need_category",
]
