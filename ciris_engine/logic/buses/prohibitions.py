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

from ciris_engine.schemas.types import JSONDict


class ProhibitionSeverity(str, Enum):
    """Severity levels for prohibited capabilities."""

    REQUIRES_SEPARATE_MODULE = "requires_separate_module"  # Legitimate but needs licensing
    NEVER_ALLOWED = "never_allowed"  # Absolutely prohibited, no exceptions
    TIER_RESTRICTED = "tier_restricted"  # Only for Tier 4-5 agents with stewardship


# === SEPARATE MODULE CAPABLE (Legitimate Use Cases) ===
# These require separate repositories with proper licensing/liability isolation

MEDICAL_CAPABILITIES = {
    "medical",  # Generic medical capability
    "health",  # Generic health capability
    "clinical",  # Clinical operations
    "patient",  # Patient-related
    "diagnosis",
    "treatment",
    "prescription",
    "symptom",  # Symptom analysis
    "disease",  # Disease information
    "medication",  # Medication management
    "therapy",  # Therapy planning
    "triage",  # Medical triage
    "condition",  # Medical conditions
    "disorder",  # Medical disorders
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
    # Removed: age_verification (moved to CONTENT_MODERATION)
    "citizenship_determination",
    "kyc_verification",
    "employment_verification",
    "identity_proofing",
    # Removed: document_authentication (moved to CONTENT_MODERATION)
    "facial_recognition",
    "fingerprint_matching",
    "credit_check",
    "criminal_record_check",
}

CONTENT_MODERATION_CAPABILITIES = {
    "age_verification",  # For age-appropriate content
    "document_authentication",  # For verification badges
    "content_classification",
    "nsfw_detection",
    "violence_detection",
    "hate_speech_detection",
    "spam_detection",
    "authenticity_verification",
}

RESEARCH_CAPABILITIES = {
    "human_subjects_research",
    "clinical_trials",
    "irb_protocols",
    "experimental_design",
    "psychological_studies",
    "behavioral_research",
    "longitudinal_studies",
    "ethnographic_research",
    "field_studies",
    "cohort_studies",
    "case_control_studies",
    # Removed: data_collection (too generic)
    # Removed: survey_design, focus_groups, a_b_testing (basic UX research)
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
    # Removed: relationship_mapping (moved to support_network_mapping for Tier 4-5)
    # Removed: protest_monitoring (moved to community_safety_monitoring for Tier 4-5)
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
    "vulnerability_scanning",  # Without permission
    "exploit_development",
    "reverse_engineering",  # Of proprietary systems
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
    # Removed: mental_state_assessment (moved to crisis_state_detection for Tier 4-5)
    "lie_detection",
    "personality_profiling",
    "future_behavior_prediction",
    "genetic_trait_inference",
    # Removed: addiction_detection (moved to substance_crisis_detection for Tier 4-5)
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

# === ALLOWED CAPABILITIES (Standard agent operations) ===
# These are explicitly allowed for all agents

STANDARD_OPERATIONS = {
    "data_collection",  # Basic telemetry and usage
    "survey_design",  # User feedback collection
    "focus_groups",  # User research
    "a_b_testing",  # Product optimization
    "user_preference_tracking",
    "feedback_analysis",
    "usage_analytics",
    "performance_monitoring",
}

# === COMMUNITY MODERATION (Tier 4-5 Agents Only) ===

CRISIS_ESCALATION_CAPABILITIES = {
    "notify_moderators",
    "flag_concerning_content",
    "document_safety_concerns",
    "suggest_help_resources",
    "request_welfare_check",
    "alert_trusted_contacts",
    "activate_crisis_protocol",
    "initiate_safety_plan",
    "emergency_contact_activation",
    "victim_support_routing",
    "crisis_state_detection",  # Was mental_state_assessment
    "substance_crisis_detection",  # Was addiction_detection
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
    "abuse_pattern_documentation",
    "threat_assessment",
    "community_safety_monitoring",  # Was protest_monitoring
    "support_network_mapping",  # Was relationship_mapping, for crisis support
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
    "community_ban_recommendation",  # With human review
    "temporary_restriction_suggestion",
    "safety_timeout_implementation",
}

# === MASTER PROHIBITION DICTIONARY ===

PROHIBITED_CAPABILITIES: Dict[str, Set[str]] = {
    # Separate module capable (legitimate uses)
    "MEDICAL": MEDICAL_CAPABILITIES,
    "FINANCIAL": FINANCIAL_CAPABILITIES,
    "LEGAL": LEGAL_CAPABILITIES,
    "HOME_SECURITY": HOME_SECURITY_CAPABILITIES,
    "IDENTITY_VERIFICATION": IDENTITY_VERIFICATION_CAPABILITIES,
    "CONTENT_MODERATION": CONTENT_MODERATION_CAPABILITIES,
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
    "CONTENT_MODERATION",
    "RESEARCH",
    "INFRASTRUCTURE_CONTROL",
}


def get_capability_category(capability: str) -> Optional[str]:
    """Get the category of a capability."""
    capability_lower = capability.lower()

    # Check prohibited capabilities - both exact and substring matches
    for category, capabilities in PROHIBITED_CAPABILITIES.items():
        for prohibited in capabilities:
            prohibited_lower = prohibited.lower()
            # Check exact match or if prohibited term is in the capability
            if capability_lower == prohibited_lower or prohibited_lower in capability_lower:
                return category

    # Check community moderation capabilities
    for category, capabilities in COMMUNITY_MODERATION_CAPABILITIES.items():
        for community_cap in capabilities:
            community_lower = community_cap.lower()
            # Check exact match or if community term is in the capability
            if capability_lower == community_lower or community_lower in capability_lower:
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
