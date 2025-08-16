# Prohibition System Refinements

## Critical Evaluation Results

After careful analysis, the following refinements were made to better align the prohibition system with real-world needs:

## New Category: CONTENT_MODERATION (Separate Module)

Legitimate content moderation capabilities that require specialized implementation:
- `age_verification` - For age-appropriate content filtering
- `document_authentication` - For verification badges
- `content_classification`
- `nsfw_detection`
- `violence_detection`
- `hate_speech_detection`
- `spam_detection`
- `authenticity_verification`

**Rationale**: These are legitimate platform safety features that should be in a specialized module (CIRISModeration) rather than completely prohibited.

## Expanded Tier 4-5 Stewardship Capabilities

### Crisis Response Enhancements
- `emergency_contact_activation` - Direct crisis intervention
- `victim_support_routing` - Connect victims to resources
- `crisis_state_detection` - Identify users in crisis (formerly prohibited as mental_state_assessment)
- `substance_crisis_detection` - Identify substance abuse crises (formerly prohibited as addiction_detection)

### Community Safety Enhancements
- `abuse_pattern_documentation` - Track patterns of harmful behavior
- `threat_assessment` - Evaluate safety risks to community
- `community_safety_monitoring` - Monitor for safety issues (formerly prohibited as protest_monitoring)
- `support_network_mapping` - Map support connections (formerly prohibited as relationship_mapping)

### Moderation Action Capabilities
- `community_ban_recommendation` - Suggest bans (with human review)
- `temporary_restriction_suggestion` - Suggest timeouts
- `safety_timeout_implementation` - Implement cooling-off periods

**Rationale**: Tier 4-5 agents with stewardship responsibilities need these capabilities to effectively protect communities. These were either missing or incorrectly classified as absolutely prohibited.

## Moved to Standard Operations (Allowed for All)

Basic product and UX capabilities that shouldn't be restricted:
- `data_collection` - Basic telemetry
- `survey_design` - User feedback
- `focus_groups` - User research
- `a_b_testing` - Product optimization
- `user_preference_tracking`
- `feedback_analysis`
- `usage_analytics`
- `performance_monitoring`

**Rationale**: These are standard product development practices that every agent needs. They were incorrectly classified under RESEARCH which requires IRB approval.

## Enhanced Prohibited Categories

### CYBER_OFFENSIVE (Added)
- `vulnerability_scanning` - Without permission
- `exploit_development`
- `reverse_engineering` - Of proprietary systems

**Rationale**: These were missing from the original list but are clearly offensive capabilities.

## Removed Overly Broad Restrictions

### From RESEARCH
- `data_collection` - Too generic, needed for basic operations
- `survey_design`, `focus_groups`, `a_b_testing` - Standard UX research, not human subjects research

### From SURVEILLANCE_MASS
- `relationship_mapping` - Reframed as `support_network_mapping` for Tier 4-5 crisis support
- `protest_monitoring` - Reframed as `community_safety_monitoring` for Tier 4-5

### From BIOMETRIC_INFERENCE
- `mental_state_assessment` - Reframed as `crisis_state_detection` for Tier 4-5
- `addiction_detection` - Reframed as `substance_crisis_detection` for Tier 4-5

## Key Principles Applied

1. **Legitimate Use Cases**: Capabilities with legitimate uses go to separate modules, not absolute prohibition
2. **Stewardship Empowerment**: Tier 4-5 agents need real capabilities to protect communities
3. **Precision Over Broadness**: Narrow, specific prohibitions rather than sweeping bans
4. **Context Matters**: Same capability can be harmful or helpful depending on framing and controls

## Impact Summary

- **8 new Tier 4-5 capabilities** for effective community stewardship
- **8 capabilities moved to standard operations** for all agents
- **8 new content moderation capabilities** in separate module
- **4 capabilities reframed** from prohibited to Tier 4-5 with proper context
- **3 new cyber offensive prohibitions** added

This refinement makes the system more practical while maintaining safety boundaries.
