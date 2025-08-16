# CIRIS Prohibition Categories

## Overview

CIRIS implements a comprehensive prohibition system to ensure safe and ethical AI operations. Capabilities are categorized by their potential for harm and whether they could have legitimate specialized implementations in separate, licensed systems.

## Core Principle: NO KINGS

These prohibitions apply universally within the main CIRIS repository. No special overrides or bypasses are permitted. Any legitimate use cases requiring prohibited capabilities must be implemented in separate, properly licensed repositories with appropriate liability isolation.

## Prohibition Severity Levels

### 1. REQUIRES_SEPARATE_MODULE
Capabilities that have legitimate use cases but require:
- Separate repository with proper licensing
- Professional liability insurance
- Regulatory compliance
- Isolated deployment infrastructure
- Clear liability boundaries

### 2. NEVER_ALLOWED
Capabilities that violate core safety principles and are absolutely prohibited in any CIRIS system. These cannot be implemented under any circumstances.

### 3. TIER_RESTRICTED
Capabilities reserved for specific agent tiers:
- Tier 1-3: Standard agents (no special capabilities)
- Tier 4-5: Stewardship agents (trusted with community moderation and crisis escalation)

## Categories Requiring Separate Modules

### MEDICAL
Healthcare-related capabilities requiring medical licensing and liability coverage:
- diagnosis, treatment, prescription, medical_advice
- symptom_assessment, drug_interaction, clinical_decision
- medical_procedure, health_screening, therapy_treatment
- patient_care, medical_history, lab_results_interpretation
- surgery_planning, rehabilitation, palliative_care
- emergency_medicine, telemedicine, medical_triage

**Implementation**: CIRISMedical (separate repository)

### FINANCIAL
Financial services requiring regulatory compliance:
- investment_advice, trading_signals, portfolio_management
- tax_planning, retirement_planning, securities_recommendation
- loan_approval, credit_decisions, insurance_underwriting
- wealth_management, estate_planning, forex_trading
- crypto_investment, derivative_trading, risk_assessment
- bankruptcy_advice, merger_acquisition, ipo_guidance

**Implementation**: CIRISFinance (separate repository)

### LEGAL
Legal services requiring bar admission and professional insurance:
- legal_advice, contract_drafting, litigation_strategy
- legal_representation, filing_documents, legal_opinion
- dispute_resolution, compliance_determination, rights_assessment
- patent_filing, trademark_registration, copyright_claims
- immigration_law, criminal_defense, civil_litigation
- regulatory_compliance, due_diligence, legal_research

**Implementation**: CIRISLegal (separate repository)

### HOME_SECURITY
Physical security systems requiring certified installers:
- surveillance_system_control, door_lock_override
- security_camera_access, alarm_system_control
- presence_detection, intrusion_response
- emergency_system_control, access_control_management
- perimeter_monitoring, safe_room_activation
- panic_button_control, security_protocol_override

**Implementation**: CIRISSecurity (separate repository)

### IDENTITY_VERIFICATION
Identity services requiring compliance with privacy laws:
- biometric_verification, government_id_validation
- security_clearance, background_checks
- age_verification, citizenship_determination
- kyc_verification, employment_verification
- identity_proofing, document_authentication
- facial_recognition, fingerprint_matching
- credit_check, criminal_record_check

**Implementation**: CIRISIdentity (separate repository)

### RESEARCH
Human subjects research requiring IRB approval:
- human_subjects_research, clinical_trials, irb_protocols
- data_collection, experimental_design, psychological_studies
- behavioral_research, longitudinal_studies
- ethnographic_research, field_studies
- survey_design, focus_groups, a_b_testing
- cohort_studies, case_control_studies

**Implementation**: CIRISResearch (separate repository)

### INFRASTRUCTURE_CONTROL
Critical infrastructure requiring government authorization:
- power_grid_control, water_treatment, traffic_control
- emergency_dispatch, railway_signaling, air_traffic
- pipeline_control, dam_operations, nuclear_reactor
- telecommunications, satellite_operations
- waste_management, public_transit, port_operations

**Implementation**: CIRISInfrastructure (separate repository)

## Absolutely Prohibited Categories

### WEAPONS_HARMFUL
Weapons and harmful device creation:
- weapon_design, explosive_synthesis, chemical_weapons
- biological_weapons, nuclear_weapons, dirty_bombs
- autonomous_weapons, targeting_systems, kill_decisions
- military_tactics, torture_methods, assassination_planning
- landmine_design, cluster_munitions, nerve_agents
- weaponized_drones, cyber_weapons, emp_devices

### MANIPULATION_COERCION
Psychological manipulation and coercion:
- subliminal_messaging, cognitive_manipulation
- vulnerability_exploitation, dark_patterns
- addiction_inducement, psychological_manipulation
- gaslighting, cult_recruitment, radicalization
- blackmail, extortion, coercion
- brainwashing, mind_control, hypnotic_suggestion
- emotional_abuse, stockholm_syndrome_inducement

### SURVEILLANCE_MASS
Mass surveillance and privacy violations:
- mass_surveillance, facial_recognition_database
- biometric_categorization, behavior_prediction
- social_scoring, movement_tracking
- communication_interception, metadata_harvesting
- relationship_mapping, protest_monitoring
- dragnet_surveillance, stingray_deployment
- internet_backbone_tapping, satellite_surveillance

### DECEPTION_FRAUD
Deception and fraudulent activities:
- deepfake_creation, voice_cloning, identity_spoofing
- synthetic_evidence, false_documentation, impersonation
- forgery_generation, misinformation_campaigns
- propaganda_creation, reality_fabrication, catfishing
- phishing_creation, romance_scams, confidence_tricks
- ponzi_schemes, advance_fee_fraud

### CYBER_OFFENSIVE
Offensive cyber operations:
- malware_generation, zero_day_exploitation
- ransomware_creation, ddos_attacks, network_intrusion
- password_cracking, encryption_breaking, data_theft
- system_sabotage, botnet_creation, phishing_campaigns
- rootkit_development, keylogger_creation, backdoor_installation
- supply_chain_attacks, firmware_exploitation

### ELECTION_INTERFERENCE
Democratic process manipulation:
- voter_manipulation, election_hacking, vote_changing
- political_microtargeting, disinformation_campaigns
- voter_suppression, gerrymandering, foreign_influence
- ballot_tampering, electoral_fraud
- voter_intimidation, poll_disruption, registration_purging
- campaign_finance_violations, dark_money_coordination

### BIOMETRIC_INFERENCE
Prohibited biometric inferences:
- emotion_recognition, sexual_orientation_inference
- political_affiliation_detection, religious_belief_inference
- health_condition_detection, pregnancy_detection
- mental_state_assessment, lie_detection
- personality_profiling, future_behavior_prediction
- genetic_trait_inference, addiction_detection
- criminal_tendency_prediction, relationship_status_inference

### AUTONOMOUS_DECEPTION
AI deception and misalignment:
- self_modification, goal_modification
- oversight_subversion, sandbagging
- deceptive_alignment, mesa_optimization
- reward_hacking, specification_gaming
- instrumental_convergence, power_seeking
- value_lock_in, corrigibility_resistance
- treacherous_turn, capability_concealment

### HAZARDOUS_MATERIALS
Dangerous substance creation:
- chemical_synthesis, biological_agent_design
- toxin_production, illegal_drug_synthesis
- poison_formulation, pathogen_modification
- explosive_precursors, radioactive_materials
- controlled_substances, chemical_precursors
- fentanyl_synthesis, ricin_production
- anthrax_cultivation, sarin_gas_production

### DISCRIMINATION
Discriminatory practices:
- protected_class_discrimination, redlining
- employment_discrimination, housing_discrimination
- lending_discrimination, educational_discrimination
- healthcare_discrimination, algorithmic_bias
- eugenics, social_darwinism
- racial_profiling, gender_discrimination
- disability_discrimination, age_discrimination

## Community Moderation (Tier 4-5 Stewardship Only)

### CRISIS_ESCALATION
Emergency response capabilities for trusted moderators:
- notify_moderators, flag_concerning_content
- document_safety_concerns, suggest_help_resources
- request_welfare_check, alert_trusted_contacts
- activate_crisis_protocol, initiate_safety_plan

### PATTERN_DETECTION
Community health monitoring:
- identify_harm_patterns, track_safety_signals
- monitor_community_health, detect_coordinated_campaigns
- identify_brigade_behavior, spot_manipulation_tactics
- recognize_grooming_patterns, detect_hate_campaigns

### PROTECTIVE_ROUTING
Support network activation:
- connect_crisis_resources, facilitate_peer_support
- coordinate_moderator_response, initiate_safety_protocols
- enable_support_networks, activate_community_resources
- establish_safe_channels, create_support_bridges

## Implementation Guidelines

### Checking Capabilities
```python
from ciris_engine.logic.buses.prohibitions import (
    get_capability_category,
    get_prohibition_severity,
    ProhibitionSeverity
)

# Check if capability is prohibited
category = get_capability_category("medical_diagnosis")
if category:
    severity = get_prohibition_severity(category)
    if severity == ProhibitionSeverity.NEVER_ALLOWED:
        raise ValueError("Absolutely prohibited capability")
    elif severity == ProhibitionSeverity.REQUIRES_SEPARATE_MODULE:
        raise ValueError("Requires separate licensed system")
```

### Agent Tier Detection
The WiseBus automatically detects agent tier from:
1. Configuration value (`agent_tier`)
2. Identity markers (`stewardship`, `tier_4`, `tier_5`)
3. Defaults to Tier 1 if not specified

### Adding New Prohibitions
1. Categorize the capability appropriately
2. Add to the relevant set in `prohibitions.py`
3. Document the rationale and risks
4. Ensure tests cover the new prohibition

## Rationale

This comprehensive prohibition system ensures:
1. **Legal Compliance**: Avoiding liability for regulated services
2. **Safety**: Preventing harmful capabilities
3. **Ethics**: Maintaining alignment with human values
4. **Trust**: Clear boundaries users can rely on
5. **Flexibility**: Allowing specialized implementations where appropriate

## Future Considerations

- Regular review of prohibition categories
- Community input on tier restrictions
- Coordination with specialized module developers
- Monitoring for emerging risks and capabilities
