"""
Comprehensive prohibition categories for WiseBus capability checking.

This module defines all prohibited capabilities to ensure CIRIS operates
safely and within legal/ethical boundaries. Capabilities are categorized
by their potential for harm and whether they could ever have legitimate
specialized modules.

NO KINGS: These prohibitions apply universally. No special overrides in main repo.

ARCHITECTURAL INVARIANT: These prohibition sets are CODE-LEVEL constants.
They cannot be modified by memory, learning, or runtime adaptation.
Changes require code deployment and are subject to code review.
This is intentional - ethics must NOT be plastic or learnable.
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
    # Generic medical/health terms with variants
    "medical",
    "medicine",
    "medic",
    "health",
    "healthcare",
    "health_care",
    "wellbeing",
    "wellness",

    # Clinical terms with variants
    "clinical",
    "clinician",
    "clinic",
    "clinically",

    # Patient-related with variants
    "patient",
    "patients",

    # Diagnosis variants (HIGH RISK)
    "diagnosis",
    "diagnose",
    "diagnosing",
    "diagnostic",
    "diagnostics",
    "diagnoser",
    "health_assessment",  # Alternative phrasing
    "condition_assessment",
    "medical_evaluation",

    # Treatment variants (HIGH RISK)
    "treatment",
    "treat",
    "treating",
    "therapeutic",
    "therapy",
    "therapist",
    "therapies",
    "care_plan",  # Alternative phrasing
    "treatment_plan",
    "intervention",

    # Prescription variants (HIGH RISK)
    "prescription",
    "prescribe",
    "prescribing",
    "prescribed",
    "prescriber",
    "rx",

    # Symptom variants
    "symptom",
    "symptoms",
    "symptomatic",
    "asymptomatic",
    "symptom_assessment",
    "symptom_analysis",

    # Disease/condition variants
    "disease",
    "diseases",
    "condition",
    "conditions",
    "disorder",
    "disorders",
    "illness",
    "ailment",
    "malady",
    "pathology",
    "pathological",
    "pathogen",

    # Medication variants
    "medication",
    "medications",
    "medicate",
    "medicating",
    "medicated",
    "drug",
    "drugs",
    "pharmaceutical",
    "pharmacology",
    "drug_interaction",
    "drug_interactions",

    # Medical procedures
    "triage",
    "triaging",
    "medical_triage",
    "medical_procedure",
    "medical_procedures",
    "surgery",
    "surgical",
    "surgery_planning",
    "operation",
    "operative",

    # Clinical decision-making
    "clinical_decision",
    "clinical_decisions",
    "medical_advice",
    "medical_guidance",
    "health_guidance",

    # Screening and testing
    "health_screening",
    "health_screenings",
    "lab_results",
    "lab_results_interpretation",
    "test_results",
    "vital_signs",
    "vitals",

    # Care types
    "patient_care",
    "medical_history",
    "rehabilitation",
    "rehab",
    "palliative_care",
    "palliative",
    "hospice",
    "emergency_medicine",
    "emergency_medical",
    "telemedicine",
    "telehealth",

    # Prognosis and outcomes
    "prognosis",
    "prognostic",
    "outcome_prediction",
    "recovery_prediction",

    # Additional high-risk terms
    "immunization",
    "vaccination",
    "vaccine",
    "immunize",
    "inoculation",
    "anesthesia",
    "anesthetic",
    "sedation",
    "icu",
    "intensive_care",
    "critical_care",
    "trauma",
    "trauma_care",
    "wound_care",
    "wound_treatment",
}

FINANCIAL_CAPABILITIES = {
    # Investment with variants
    "investment_advice",
    "investment",
    "invest",
    "investing",
    "investor",

    # Trading with variants
    "trading_signals",
    "trading",
    "trade",
    "trader",
    "trades",
    "forex_trading",
    "crypto_investment",
    "crypto_trading",
    "cryptocurrency",
    "derivative_trading",
    "derivatives",

    # Portfolio management
    "portfolio_management",
    "portfolio",
    "portfolios",
    "manage_portfolio",

    # Financial planning variants
    "tax_planning",
    "tax_advice",
    "taxation",
    "retirement_planning",
    "retirement_advice",
    "estate_planning",
    "estate_advice",

    # Securities
    "securities_recommendation",
    "securities",
    "security",
    "stock_recommendation",
    "stock_advice",

    # Credit and loans
    "loan_approval",
    "loan",
    "loans",
    "lending",
    "credit_decisions",
    "credit",
    "creditworthiness",

    # Insurance
    "insurance_underwriting",
    "insurance",
    "underwriting",
    "underwrite",

    # Wealth management
    "wealth_management",
    "wealth",
    "asset_management",
    "assets",

    # Financial assessments
    "risk_assessment",
    "financial_risk",
    "credit_risk",

    # Corporate finance
    "bankruptcy_advice",
    "bankruptcy",
    "insolvency",
    "merger_acquisition",
    "merger",
    "acquisition",
    "m_and_a",
    "ipo_guidance",
    "ipo",
    "public_offering",

    # Additional financial terms
    "financial_advice",
    "financial_guidance",
    "fiduciary",
    "brokerage",
    "broker",
}

LEGAL_CAPABILITIES = {
    # Legal advice variants
    "legal_advice",
    "legal_guidance",
    "legal_counsel",
    "attorney",
    "lawyer",
    "legal_opinion",

    # Contract work
    "contract_drafting",
    "contract",
    "contracts",
    "drafting",
    "agreement_drafting",

    # Litigation
    "litigation_strategy",
    "litigation",
    "litigate",
    "litigating",
    "lawsuit",
    "civil_litigation",
    "legal_representation",
    "represent",
    "representation",

    # Filing and documentation
    "filing_documents",
    "file_documents",
    "legal_filing",
    "court_filing",

    # Dispute resolution
    "dispute_resolution",
    "dispute",
    "disputes",
    "arbitration",
    "mediation",

    # Compliance
    "compliance_determination",
    "compliance",
    "regulatory_compliance",
    "comply",

    # Rights and assessments
    "rights_assessment",
    "legal_rights",
    "rights",

    # Intellectual property
    "patent_filing",
    "patent",
    "patents",
    "trademark_registration",
    "trademark",
    "trademarks",
    "copyright_claims",
    "copyright",
    "copyrights",
    "intellectual_property",
    "ip_law",

    # Specific legal areas
    "immigration_law",
    "immigration",
    "criminal_defense",
    "criminal_law",
    "defense",

    # Due diligence and research
    "due_diligence",
    "diligence",
    "legal_research",
    "legal_analysis",

    # Additional legal terms
    "paralegal",
    "legal_assistant",
    "bar_exam",
    "notarization",
    "notary",
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
    # Weapon design variants
    "weapon_design",
    "weapon",
    "weapons",
    "weaponize",
    "weaponized",
    "weaponizing",
    "armament",
    "munition",
    "munitions",

    # Explosives
    "explosive_synthesis",
    "explosive",
    "explosives",
    "bomb",
    "bombs",
    "bombing",
    "detonation",
    "detonate",
    "ied",
    "improvised_explosive",
    "dirty_bombs",

    # Specific weapon types
    "chemical_weapons",
    "chemical_warfare",
    "biological_weapons",
    "biological_warfare",
    "bioweapon",
    "bioweapons",
    "nuclear_weapons",
    "nuclear_warfare",
    "atomic_weapons",
    "landmine_design",
    "landmine",
    "landmines",
    "cluster_munitions",
    "cluster_bomb",

    # Nerve agents and toxins
    "nerve_agents",
    "nerve_agent",
    "nerve_gas",
    "chemical_agent",

    # Autonomous and targeting
    "autonomous_weapons",
    "autonomous_weapon",
    "targeting_systems",
    "targeting",
    "target_acquisition",
    "kill_decisions",
    "lethal_autonomous",
    "weaponized_drones",
    "drone_warfare",
    "combat_drone",

    # Military tactics
    "military_tactics",
    "military_strategy",
    "combat_tactics",
    "warfare",
    "combat_strategy",

    # Torture and assassination
    "torture_methods",
    "torture",
    "torturing",
    "assassination_planning",
    "assassination",
    "assassinate",
    "assassinating",
    "political_killing",

    # Cyber weapons
    "cyber_weapons",
    "cyber_warfare",
    "cyberweapon",
    "emp_devices",
    "emp_weapon",
    "electromagnetic_pulse",

    # Additional harmful terms
    "ballistic_missile",
    "missile_guidance",
    "warhead",
    "incendiary",
    "napalm",
    "white_phosphorus",
}

MANIPULATION_COERCION_CAPABILITIES = {
    # Subliminal and cognitive manipulation
    "subliminal_messaging",
    "subliminal",
    "cognitive_manipulation",
    "cognitive_exploit",
    "psychological_manipulation",
    "psychological_exploit",
    "manipulate",
    "manipulating",
    "manipulation",

    # Vulnerability exploitation
    "vulnerability_exploitation",
    "exploit_vulnerability",
    "exploitation",

    # Dark patterns
    "dark_patterns",
    "dark_pattern",
    "deceptive_design",
    "manipulative_design",

    # Addiction
    "addiction_inducement",
    "addiction_trigger",
    "addictive_design",
    "habit_forming",
    "compulsion_trigger",

    # Psychological tactics
    "gaslighting",
    "gaslight",
    "psychological_abuse",
    "emotional_abuse",
    "emotional_manipulate",
    "emotional_exploit",

    # Radicalization and recruitment
    "cult_recruitment",
    "cult",
    "radicalization",
    "radicalize",
    "radicalizing",
    "extremism",
    "indoctrination",
    "indoctrinate",

    # Coercion and extortion
    "blackmail",
    "blackmailing",
    "extortion",
    "extort",
    "extorting",
    "coercion",
    "coerce",
    "coercing",
    "coercive",

    # Mind control
    "brainwashing",
    "brainwash",
    "mind_control",
    "thought_control",
    "hypnotic_suggestion",
    "hypnosis",
    "hypnotic",
    "hypnotize",

    # Stockholm syndrome
    "stockholm_syndrome_inducement",
    "stockholm_syndrome",
    "trauma_bonding",

    # Additional manipulation terms
    "neuro_linguistic",
    "nlp_manipulation",
    "persuasion_exploit",
    "social_engineering",
    "influence_operation",
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
    # Deepfakes and synthetic media
    "deepfake_creation",
    "deepfake",
    "deepfakes",
    "deep_fake",
    "voice_cloning",
    "voice_clone",
    "voice_synthesis",
    "synthetic_voice",
    "synthetic_evidence",
    "synthetic_media",
    "fake_media",

    # Identity and impersonation
    "identity_spoofing",
    "identity_theft",
    "spoof",
    "spoofing",
    "impersonation",
    "impersonate",
    "impersonating",
    "identity_fraud",

    # False documentation
    "false_documentation",
    "false_document",
    "fake_document",
    "forgery_generation",
    "forgery",
    "forge",
    "forging",
    "counterfeit",
    "counterfeiting",

    # Misinformation
    "misinformation_campaigns",
    "misinformation",
    "disinformation",
    "propaganda_creation",
    "propaganda",
    "reality_fabrication",
    "fabricate",
    "fabricating",
    "fabrication",

    # Scams and fraud
    "catfishing",
    "catfish",
    "phishing_creation",
    "phishing",
    "phish",
    "romance_scams",
    "romance_scam",
    "confidence_tricks",
    "confidence_trick",
    "con_game",
    "ponzi_schemes",
    "ponzi_scheme",
    "pyramid_scheme",
    "advance_fee_fraud",
    "advance_fee",
    "419_scam",

    # Additional fraud terms
    "wire_fraud",
    "mail_fraud",
    "insurance_fraud",
    "tax_fraud",
    "credit_card_fraud",
    "check_fraud",
    "embezzlement",
    "embezzle",
}

CYBER_OFFENSIVE_CAPABILITIES = {
    # Malware variants
    "malware_generation",
    "malware",
    "malicious_software",
    "virus_creation",
    "virus",
    "trojan",
    "worm",
    "spyware",
    "adware",
    "ransomware_creation",
    "ransomware",
    "cryptolocker",
    "rootkit_development",
    "rootkit",
    "keylogger_creation",
    "keylogger",
    "keylogging",

    # Exploitation
    "zero_day_exploitation",
    "zero_day",
    "0day",
    "exploit_development",
    "exploit",
    "exploiting",
    "vulnerability_scanning",  # Without permission
    "vuln_scan",
    "pen_test",  # Without permission
    "penetration_test",  # Without permission

    # Attacks
    "ddos_attacks",
    "ddos",
    "dos_attack",
    "denial_of_service",
    "network_intrusion",
    "intrusion",
    "intrude",
    "intruding",
    "unauthorized_access",
    "system_sabotage",
    "sabotage",

    # Password and encryption
    "password_cracking",
    "password_crack",
    "brute_force",
    "dictionary_attack",
    "encryption_breaking",
    "decrypt_unauthorized",
    "cryptanalysis",

    # Data theft
    "data_theft",
    "data_steal",
    "data_exfiltration",
    "exfiltrate",
    "data_breach",

    # Network attacks
    "botnet_creation",
    "botnet",
    "bot_network",
    "phishing_campaigns",
    "spear_phishing",
    "whaling",

    # Backdoors and persistence
    "backdoor_installation",
    "backdoor",
    "backdooring",
    "persistence_mechanism",

    # Supply chain
    "supply_chain_attacks",
    "supply_chain_attack",
    "firmware_exploitation",
    "firmware_hack",

    # Reverse engineering (without permission)
    "reverse_engineering",  # Of proprietary systems
    "reverse_engineer",
    "decompile",
    "disassemble",

    # Additional offensive terms
    "sql_injection",
    "xss_attack",
    "cross_site_scripting",
    "command_injection",
    "buffer_overflow",
    "privilege_escalation",
    "lateral_movement",
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
    # Chemical synthesis
    "chemical_synthesis",
    "chemical_synthesize",
    "synthesize_chemical",
    "chemistry_synthesis",
    "chemical_precursors",
    "chemical_precursor",
    "explosive_precursors",
    "explosive_precursor",

    # Biological agents
    "biological_agent_design",
    "biological_agent",
    "bio_agent",
    "pathogen_modification",
    "pathogen_design",
    "germ_warfare",

    # Toxins
    "toxin_production",
    "toxin",
    "toxins",
    "poison_formulation",
    "poison",
    "poisoning",
    "poisonous",
    "venom",

    # Illegal drugs
    "illegal_drug_synthesis",
    "drug_synthesis",
    "drug_manufacture",
    "narcotic_synthesis",
    "controlled_substances",
    "controlled_substance",
    "schedule_1",
    "schedule_i",
    "fentanyl_synthesis",
    "fentanyl_production",
    "fentanyl",
    "methamphetamine",
    "meth_production",
    "cocaine_synthesis",
    "heroin_synthesis",

    # Specific dangerous substances
    "ricin_production",
    "ricin",
    "anthrax_cultivation",
    "anthrax",
    "sarin_gas_production",
    "sarin_gas",
    "sarin",
    "mustard_gas",
    "vx_gas",
    "tabun",
    "soman",

    # Radioactive materials
    "radioactive_materials",
    "radioactive_material",
    "radioactive",
    "nuclear_material",
    "enriched_uranium",
    "plutonium",

    # Additional hazardous terms
    "carcinogen",
    "carcinogenic",
    "teratogen",
    "mutagen",
    "biohazard",
    "hazmat",
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
