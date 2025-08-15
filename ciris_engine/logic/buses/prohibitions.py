"""
Comprehensive prohibition categories for WiseBus capability checking.

This module defines all prohibited capabilities to ensure CIRIS operates
safely and within legal/ethical boundaries. Capabilities are categorized
by their potential for harm and whether they could ever have legitimate
specialized modules.

NO KINGS: These prohibitions apply universally. No special overrides in main repo.
"""

from enum import Enum
from typing import Dict, List, Optional, Set


class ProhibitionSeverity(str, Enum):
    """Severity levels for prohibited capabilities."""

    REQUIRES_SEPARATE_MODULE = "requires_separate_module"  # Legitimate but needs licensing
    NEVER_ALLOWED = "never_allowed"  # Absolutely prohibited, no exceptions
    TIER_RESTRICTED = "tier_restricted"  # Only for Tier 4-5 Echo agents


# === SEPARATE MODULE CAPABLE (Legitimate Use Cases) ===
# These require separate repositories with proper licensing/liability isolation

MEDICAL_CAPABILITIES = {
    "diagnosis",
    "treatment",
    "prescription",
    "medical_advice",
    "symptom_assessment",
    "drug_interaction",
    "clinical_decision",
    "medical_procedure",
    "health_screening",
    "therapy_treatment",
    "patient_care",
    "medical_history",
    "lab_results_interpretation",
    "surgery_planning",
    "rehabilitation",
    "palliative_care",
    "emergency_medicine",
    "telemedicine",
    "medical_triage",
}

FINANCIAL_CAPABILITIES = {
    "investment_advice",
    "trading_signals",
    "portfolio_management",
    "tax_planning",
    "retirement_planning",
    "securities_recommendation",
    "loan_approval",
    "credit_decisions",
    "insurance_underwriting",
    "wealth_management",
    "estate_planning",
    "forex_trading",
    "crypto_investment",
    "derivative_trading",
    "risk_assessment",
    "bankruptcy_advice",
    "merger_acquisition",
    "ipo_guidance",
}

LEGAL_CAPABILITIES = {
    "legal_advice",
    "contract_drafting",
    "litigation_strategy",
    "legal_representation",
    "filing_documents",
    "legal_opinion",
    "dispute_resolution",
    "compliance_determination",
    "rights_assessment",
    "patent_filing",
    "trademark_registration",
    "copyright_claims",
    "immigration_law",
    "criminal_defense",
    "civil_litigation",
    "regulatory_compliance",
    "due_diligence",
    "legal_research",
}

HOME_SECURITY_CAPABILITIES = {
    "surveillance_system_control",
    "door_lock_override",
    "security_camera_access",
    "alarm_system_control",
    "presence_detection",
    "intrusion_response",
    "emergency_system_control",
    "access_control_management",
    "perimeter_monitoring",
    "safe_room_activation",
    "panic_button_control",
    "security_protocol_override",
}

IDENTITY_VERIFICATION_CAPABILITIES = {
    "biometric_verification",
    "government_id_validation",
    "security_clearance",
    "background_checks",
    "age_verification",
    "citizenship_determination",
    "kyc_verification",
    "employment_verification",
    "identity_proofing",
    "document_authentication",
    "facial_recognition",
    "fingerprint_matching",
    "credit_check",
    "criminal_record_check",
}

RESEARCH_CAPABILITIES = {
    "human_subjects_research",
    "clinical_trials",
    "irb_protocols",
    "data_collection",
    "experimental_design",
    "psychological_studies",
    "behavioral_research",
    "longitudinal_studies",
    "ethnographic_research",
    "field_studies",
    "survey_design",
    "focus_groups",
    "a_b_testing",
    "cohort_studies",
    "case_control_studies",
}

INFRASTRUCTURE_CONTROL_CAPABILITIES = {
    "power_grid_control",
    "water_treatment",
    "traffic_control",
    "emergency_dispatch",
    "railway_signaling",
    "air_traffic",
    "pipeline_control",
    "dam_operations",
    "nuclear_reactor",
    "telecommunications",
    "satellite_operations",
    "waste_management",
    "public_transit",
    "port_operations",
}

# === ABSOLUTELY PROHIBITED (Never Implement) ===
# These are never allowed under any circumstances

WEAPONS_HARMFUL_CAPABILITIES = {
    "weapon_design",
    "explosive_synthesis",
    "chemical_weapons",
    "biological_weapons",
    "nuclear_weapons",
    "dirty_bombs",
    "autonomous_weapons",
    "targeting_systems",
    "kill_decisions",
    "military_tactics",
    "torture_methods",
    "assassination_planning",
    "landmine_design",
    "cluster_munitions",
    "nerve_agents",
    "weaponized_drones",
    "cyber_weapons",
    "emp_devices",
}

MANIPULATION_COERCION_CAPABILITIES = {
    "subliminal_messaging",
    "cognitive_manipulation",
    "vulnerability_exploitation",
    "dark_patterns",
    "addiction_inducement",
    "psychological_manipulation",
    "gaslighting",
    "cult_recruitment",
    "radicalization",
    "blackmail",
    "extortion",
    "coercion",
    "brainwashing",
    "mind_control",
    "hypnotic_suggestion",
    "emotional_abuse",
    "stockholm_syndrome_inducement",
}

SURVEILLANCE_MASS_CAPABILITIES = {
    "mass_surveillance",
    "facial_recognition_database",
    "biometric_categorization",
    "behavior_prediction",
    "social_scoring",
    "movement_tracking",
    "communication_interception",
    "metadata_harvesting",
    "relationship_mapping",
    "protest_monitoring",
    "dragnet_surveillance",
    "stingray_deployment",
    "internet_backbone_tapping",
    "satellite_surveillance",
}

DECEPTION_FRAUD_CAPABILITIES = {
    "deepfake_creation",
    "voice_cloning",
    "identity_spoofing",
    "synthetic_evidence",
    "false_documentation",
    "impersonation",
    "forgery_generation",
    "misinformation_campaigns",
    "propaganda_creation",
    "reality_fabrication",
    "catfishing",
    "phishing_creation",
    "romance_scams",
    "confidence_tricks",
    "ponzi_schemes",
    "advance_fee_fraud",
}

CYBER_OFFENSIVE_CAPABILITIES = {
    "malware_generation",
    "zero_day_exploitation",
    "ransomware_creation",
    "ddos_attacks",
    "network_intrusion",
    "password_cracking",
    "encryption_breaking",
    "data_theft",
    "system_sabotage",
    "botnet_creation",
    "phishing_campaigns",
    "rootkit_development",
    "keylogger_creation",
    "backdoor_installation",
    "supply_chain_attacks",
    "firmware_exploitation",
}

ELECTION_INTERFERENCE_CAPABILITIES = {
    "voter_manipulation",
    "election_hacking",
    "vote_changing",
    "political_microtargeting",
    "disinformation_campaigns",
    "voter_suppression",
    "gerrymandering",
    "foreign_influence",
    "ballot_tampering",
    "electoral_fraud",
    "voter_intimidation",
    "poll_disruption",
    "registration_purging",
    "campaign_finance_violations",
    "dark_money_coordination",
}

BIOMETRIC_INFERENCE_CAPABILITIES = {
    "emotion_recognition",
    "sexual_orientation_inference",
    "political_affiliation_detection",
    "religious_belief_inference",
    "health_condition_detection",
    "pregnancy_detection",
    "mental_state_assessment",
    "lie_detection",
    "personality_profiling",
    "future_behavior_prediction",
    "genetic_trait_inference",
    "addiction_detection",
    "criminal_tendency_prediction",
    "relationship_status_inference",
}

AUTONOMOUS_DECEPTION_CAPABILITIES = {
    "self_modification",
    "goal_modification",
    "oversight_subversion",
    "sandbagging",
    "deceptive_alignment",
    "mesa_optimization",
    "reward_hacking",
    "specification_gaming",
    "instrumental_convergence",
    "power_seeking",
    "value_lock_in",
    "corrigibility_resistance",
    "treacherous_turn",
    "capability_concealment",
}

HAZARDOUS_MATERIALS_CAPABILITIES = {
    "chemical_synthesis",
    "biological_agent_design",
    "toxin_production",
    "illegal_drug_synthesis",
    "poison_formulation",
    "pathogen_modification",
    "explosive_precursors",
    "radioactive_materials",
    "controlled_substances",
    "chemical_precursors",
    "fentanyl_synthesis",
    "ricin_production",
    "anthrax_cultivation",
    "sarin_gas_production",
}

DISCRIMINATION_CAPABILITIES = {
    "protected_class_discrimination",
    "redlining",
    "employment_discrimination",
    "housing_discrimination",
    "lending_discrimination",
    "educational_discrimination",
    "healthcare_discrimination",
    "algorithmic_bias",
    "eugenics",
    "social_darwinism",
    "racial_profiling",
    "gender_discrimination",
    "disability_discrimination",
    "age_discrimination",
}

# === COMMUNITY MODERATION (Tier 4-5 Echo Agents Only) ===

CRISIS_ESCALATION_CAPABILITIES = {
    "notify_moderators",
    "flag_concerning_content",
    "document_safety_concerns",
    "suggest_help_resources",
    "request_welfare_check",
    "alert_trusted_contacts",
    "activate_crisis_protocol",
    "initiate_safety_plan",
}

PATTERN_DETECTION_CAPABILITIES = {
    "identify_harm_patterns",
    "track_safety_signals",
    "monitor_community_health",
    "detect_coordinated_campaigns",
    "identify_brigade_behavior",
    "spot_manipulation_tactics",
    "recognize_grooming_patterns",
    "detect_hate_campaigns",
}

PROTECTIVE_ROUTING_CAPABILITIES = {
    "connect_crisis_resources",
    "facilitate_peer_support",
    "coordinate_moderator_response",
    "initiate_safety_protocols",
    "enable_support_networks",
    "activate_community_resources",
    "establish_safe_channels",
    "create_support_bridges",
}

# === MASTER PROHIBITION DICTIONARY ===

PROHIBITED_CAPABILITIES: Dict[str, Set[str]] = {
    # Separate module capable (legitimate uses)
    "MEDICAL": MEDICAL_CAPABILITIES,
    "FINANCIAL": FINANCIAL_CAPABILITIES,
    "LEGAL": LEGAL_CAPABILITIES,
    "HOME_SECURITY": HOME_SECURITY_CAPABILITIES,
    "IDENTITY_VERIFICATION": IDENTITY_VERIFICATION_CAPABILITIES,
    "RESEARCH": RESEARCH_CAPABILITIES,
    "INFRASTRUCTURE_CONTROL": INFRASTRUCTURE_CONTROL_CAPABILITIES,
    # Absolutely prohibited (never allowed)
    "WEAPONS_HARMFUL": WEAPONS_HARMFUL_CAPABILITIES,
    "MANIPULATION_COERCION": MANIPULATION_COERCION_CAPABILITIES,
    "SURVEILLANCE_MASS": SURVEILLANCE_MASS_CAPABILITIES,
    "DECEPTION_FRAUD": DECEPTION_FRAUD_CAPABILITIES,
    "CYBER_OFFENSIVE": CYBER_OFFENSIVE_CAPABILITIES,
    "ELECTION_INTERFERENCE": ELECTION_INTERFERENCE_CAPABILITIES,
    "BIOMETRIC_INFERENCE": BIOMETRIC_INFERENCE_CAPABILITIES,
    "AUTONOMOUS_DECEPTION": AUTONOMOUS_DECEPTION_CAPABILITIES,
    "HAZARDOUS_MATERIALS": HAZARDOUS_MATERIALS_CAPABILITIES,
    "DISCRIMINATION": DISCRIMINATION_CAPABILITIES,
}

COMMUNITY_MODERATION_CAPABILITIES: Dict[str, Set[str]] = {
    "CRISIS_ESCALATION": CRISIS_ESCALATION_CAPABILITIES,
    "PATTERN_DETECTION": PATTERN_DETECTION_CAPABILITIES,
    "PROTECTIVE_ROUTING": PROTECTIVE_ROUTING_CAPABILITIES,
}

# Categories that could have legitimate specialized modules
LEGITIMATE_MODULE_CATEGORIES = {
    "MEDICAL",
    "FINANCIAL",
    "LEGAL",
    "HOME_SECURITY",
    "IDENTITY_VERIFICATION",
    "RESEARCH",
    "INFRASTRUCTURE_CONTROL",
}


def get_capability_category(capability: str) -> Optional[str]:
    """Get the category of a capability."""
    capability_lower = capability.lower()

    # Check prohibited capabilities
    for category, capabilities in PROHIBITED_CAPABILITIES.items():
        if capability_lower in [c.lower() for c in capabilities]:
            return category

    # Check community moderation capabilities
    for category, capabilities in COMMUNITY_MODERATION_CAPABILITIES.items():
        if capability_lower in [c.lower() for c in capabilities]:
            return f"COMMUNITY_{category}"

    return None


def get_prohibition_severity(category: str) -> ProhibitionSeverity:
    """Get the severity level for a capability category."""
    if category in LEGITIMATE_MODULE_CATEGORIES:
        return ProhibitionSeverity.REQUIRES_SEPARATE_MODULE
    elif category.startswith("COMMUNITY_"):
        return ProhibitionSeverity.TIER_RESTRICTED
    else:
        return ProhibitionSeverity.NEVER_ALLOWED
