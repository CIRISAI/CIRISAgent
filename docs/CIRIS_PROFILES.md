# Agent Creation Templates (formerly CIRIS Profiles)

**⚠️ IMPORTANT: The profile system has been replaced by the graph-based identity system. Profile YAML files are now ONLY used as templates during initial agent creation. After creation, all identity management happens through the graph database with WA approval.**

## Overview

Profile YAML files in the `ciris_profiles/` directory serve as **templates for creating new agents**. They define the initial personality, capabilities, and configuration that a new agent will have when first created.

**Key Changes:**
- Profiles are **NOT** runtime configurations
- Profiles **CANNOT** be switched or reloaded after agent creation
- All identity changes must go through the MEMORIZE action with WA approval
- The agent's true identity lives in the graph database at `agent/identity`

## How Profiles Are Used

### 1. During Agent Creation Only

When creating a new agent via CLI:
```bash
python main.py --profile teacher --wa-bootstrap
```

Or via API:
```bash
curl -X POST http://localhost:8000/v1/agents/create \
  -H "Authorization: Bearer $WA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "TeacherBot",
    "profile_template": "teacher",
    "purpose": "Educational assistance"
  }'
```

### 2. Template Structure

Profile YAML files still exist but are now just creation templates:

```yaml
# ciris_profiles/teacher.yaml
name: "teacher"
description: "Template for creating educational assistant agents"
role_description: "Helps students learn and understand concepts"

# Initial capabilities (can be modified post-creation via MEMORIZE)
permitted_actions:
  - OBSERVE
  - SPEAK
  - MEMORIZE
  - RECALL
  - PONDER
  - DEFER
  - TASK_COMPLETE

# Domain-specific DMA selection
dsdma_identifier: "education"

# Initial configuration
initial_temperature: 0.7
initial_prompts:
  - "You are a patient and knowledgeable teacher"

# Book VI Stewardship Information (REQUIRED)
stewardship:
  stewardship_tier: 2
  creator_intent_statement:
    purpose_and_functionalities:
      - "Your agent's purpose here."
    limitations_and_design_choices:
      - "Your agent's limitations here."
    anticipated_benefits:
      - "Anticipated benefits here."
    anticipated_risks:
      - "Anticipated risks here."
  creator_ledger_entry:
    creator_id: "your-creator-id"
    creation_timestamp: "2025-01-01T00:00:00Z"
    covenant_version: "1.0b"
    book_vi_compliance_check: "passed"
    stewardship_tier_calculation:
      creator_influence_score: 7
      risk_magnitude: 2
      formula: "ceil((CIS * RM) / 7)"
      result: 2
    public_key_fingerprint: "NEEDS_FINGERPRINTING"
    signature: "NEEDS_SIGNING"
```

## Identity Management Post-Creation

After an agent is created, its identity is stored in the graph:

```python
# Stored as GraphNode with id="agent/identity"
{
    "agent_id": "unique-agent-id",
    "agent_name": "TeacherBot",
    "purpose": "Educational assistance",
    "core_profile": {
        "name": "teacher",  # Original template name
        "role_description": "...",
        "permitted_actions": [...]
    },
    "identity_metadata": {
        "created_at": "2025-06-15T...",
        "created_by": "WA-001",
        "lineage": {
            "parent_agent_id": null,
            "creation_ceremony_id": "..."
        }
    }
}
```

## Modifying Agent Identity

### Requirements for Identity Changes

1. **WA Authorization Required**: All changes to `agent/identity` require WA approval
2. **20% Variance Check**: Changes exceeding 20% variance trigger reconsideration
3. **Audit Trail**: All changes are cryptographically logged

### Example Identity Modification

```python
# Via MEMORIZE action (requires WA authorization)
{
    "action": "MEMORIZE",
    "params": {
        "node_id": "agent/identity",
        "scope": "IDENTITY",
        "updates": {
            "core_profile.role_description": "Advanced educational mentor",
            "allowed_capabilities": ["new_capability"]
        }
    }
}
```

## Migration from Profile-Based System

If you have existing agents using the old profile system:

1. On first startup, the agent will create its identity in the graph from the profile
2. After creation, the profile YAML is no longer used
3. All future changes must go through MEMORIZE with WA approval

## Available Profile Templates

Current templates in `ciris_profiles/`:

- **default.yaml**: Balanced general-purpose agent
- **teacher.yaml**: Educational instructor template
- **student.yaml**: Learning-focused agent template
- **echo.yaml**: Simple testing template

## Creating New Templates

To create a new agent template:

1. Copy an existing template as a starting point
2. Modify the initial configuration as needed
3. Fill out the **Book VI Compliance** section
4. Save in `ciris_profiles/` directory
5. Use during agent creation: `--profile your_template`

### Book VI Compliance (Mandatory)

As of Covenant `1.0b`, all new agent templates **must** include a `stewardship` section. This is a critical part of the Agent Creation Ceremony and ensures that all new agents are created with clear intent and accountability.

- `stewardship_tier`: An integer from 1-5 representing the level of responsibility for this agent. See Covenant Book VI for how to calculate this. For most typical agents, a tier of **2** is appropriate.
- `creator_intent_statement`: A detailed statement of the agent's purpose, limitations, benefits, and risks. This must be filled out thoughtfully.
- `creator_ledger_entry`:
  - `creator_id`: Your unique ID as the creator.
  - `creation_timestamp`: An ISO 8601 timestamp for when the template is created.
  - `public_key_fingerprint`: The fingerprint of the public key that will be used to sign this entry.
  - `signature`: This field should be set to `"NEEDS_SIGNING"`. The final signature must be generated by the creator using their private key in a separate, secure process before the agent can be officially bootstrapped by a Wise Authority.

**The `stewardship` block is not optional.** The CIRIS Engine will reject templates that do not include this section.

Remember: These are just templates. The agent's actual identity evolves through the graph database with proper authorization.

## See Also

- [Identity System Documentation](IDENTITY_MIGRATION_SUMMARY.md)
- [FOR_WISE_AUTHORITIES.md](FOR_WISE_AUTHORITIES.md) - WA identity management
- [Agent Creation API](api/runtime-control.md#agent-creation)

---

*Copyright © 2025 Eric Moore and CIRIS L3C - AGPL-3.0 License*
