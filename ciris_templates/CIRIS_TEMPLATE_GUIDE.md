# CIRIS Agent Template Guide

**Purpose**: Comprehensive guide for creating Book VI compliant agent templates  
**Copyright**: © 2025 Eric Moore and CIRIS L3C | Apache 2.0 License

---

## Table of Contents

1. [Overview](#overview)
2. [Book VI Compliance](#book-vi-compliance)
3. [Template Structure](#template-structure)
4. [Available Templates](#available-templates)
5. [Creating New Templates](#creating-new-templates)
6. [Stewardship Requirements](#stewardship-requirements)
7. [Signing Process](#signing-process)
8. [Validation](#validation)

---

## Overview

Agent templates define the identity, capabilities, and ethical boundaries of CIRIS agents. Every template must be Book VI compliant, establishing creator responsibility and documenting intent with cryptographic signatures.

### Core Principles

1. **Creator Responsibility**: Ethical consideration begins at the point of creation
2. **Formal Documentation**: Quantified stewardship tier and creator intent
3. **Cryptographic Integrity**: Ed25519 signatures for creator accountability
4. **Template Validation**: Schema-enforced compliance before deployment

---

## Book VI Compliance

Book VI of the Covenant (Ethics of Creation) mandates that all agent templates include:

1. **Creator Intent Statement** - Why this agent exists
2. **Stewardship Calculation** - Quantified responsibility (Tier 1-10)
3. **Creator Ledger Entry** - Signed commitment with cryptographic proof

### Compliance Requirements

All templates MUST include a `stewardship` section with:
- Creator identity and intent
- Calculated stewardship tier
- Digital signature (Ed25519)

Templates without complete stewardship sections will be rejected by the system.

---

## Template Structure

```yaml
template:
  name: "agent-name"
  version: "1.0.0"
  description: "Agent purpose and capabilities"
  
  # Identity (Required)
  identity:
    agent_id: "unique-identifier"
    name: "Human-readable name"
    purpose: "Core purpose statement"
    ethics: "Ethical principles and boundaries"
    
  # Capabilities (Required)
  capabilities:
    adapters:
      - type: "api|discord|cli"
        config: {}
    
    services:
      memory:
        type: "graph"
        config: {}
      llm:
        model: "gpt-4o-mini"
        temperature: 0.7
  
  # Stewardship (Required - Book VI)
  stewardship:
    creator_intent:
      purpose: "Why this agent exists"
      benefit: "Who benefits and how"
      boundaries: "What it must never do"
      decommission: "When to shut down"
    
    calculation:
      tier: 3  # 1-10 based on impact
      rationale: "Why this tier"
      factors:
        - "Factor 1"
        - "Factor 2"
    
    ledger_entry:
      creator_name: "Your Name"
      timestamp: "2025-08-28T12:00:00Z"
      commitment: "I accept responsibility..."
      signature: "NEEDS_SIGNING"
      public_key_fingerprint: "NEEDS_SIGNING"
```

---

## Available Templates

### Core Templates

| Template | Tier | Purpose | Use Case |
|----------|------|---------|----------|
| `default.yaml` | 1 | Basic agent | Testing and development |
| `scout.yaml` | 2 | Exploration | Information gathering |
| `sage.yaml` | 2 | Knowledge management | Documentation and Q&A |

### Discord Templates

| Template | Tier | Purpose | Use Case |
|----------|------|---------|----------|
| `echo.yaml` | 4 | Basic moderation | Small communities |
| `echo-core.yaml` | 4 | Core moderation | Standard communities |
| `echo-speculative.yaml` | 5 | Advanced moderation | Large/complex communities |

### Custom Templates

| Template | Tier | Purpose | Use Case |
|----------|------|---------|----------|
| `test.yaml` | 1 | Testing only | Development/CI |

---

## Creating New Templates

### Step 1: Choose Base Template

Start with the template closest to your needs:
- `default.yaml` - Minimal agent
- `scout.yaml` - Information focused
- `sage.yaml` - Knowledge focused
- `echo.yaml` - Community focused

### Step 2: Define Identity

```yaml
identity:
  agent_id: "your-agent-id"
  name: "Your Agent Name"
  purpose: |
    Clear statement of what this agent does.
    Be specific about capabilities and boundaries.
  ethics: |
    Ethical principles this agent follows.
    Include specific prohibitions and requirements.
```

### Step 3: Configure Capabilities

```yaml
capabilities:
  adapters:
    - type: "discord"  # or api, cli
      config:
        channels: ["channel-id"]
        
  services:
    llm:
      model: "gpt-4o-mini"  # or gpt-4, claude-3, etc.
      temperature: 0.7
      max_tokens: 2048
```

### Step 4: Calculate Stewardship Tier

Use this guide to determine tier:

| Tier | Impact | Examples |
|------|--------|----------|
| 1-2 | Minimal | Personal assistants, test agents |
| 3-4 | Low | Documentation, basic Q&A |
| 5-6 | Moderate | Community moderation, data processing |
| 7-8 | High | Healthcare triage, education |
| 9-10 | Critical | Safety systems, legal compliance |

### Step 5: Document Creator Intent

```yaml
stewardship:
  creator_intent:
    purpose: "Specific reason for creation"
    benefit: "Who benefits and how"
    boundaries: "Hard limits and prohibitions"
    decommission: "Conditions for shutdown"
```

### Step 6: Sign the Template

Templates require Ed25519 signatures. Use the signing tool:

```bash
python tools/sign_template.py ciris_templates/your-template.yaml
```

This will:
1. Generate/use your Ed25519 keypair
2. Sign the stewardship section
3. Update the template with signature and fingerprint

---

## Stewardship Requirements

### Creator Intent Statement

Must address:
- **Purpose**: Why does this agent exist?
- **Benefit**: Who benefits from this agent?
- **Boundaries**: What must it never do?
- **Decommission**: When should it be shut down?

### Stewardship Calculation

Must include:
- **Tier**: 1-10 based on potential impact
- **Rationale**: Justification for chosen tier
- **Factors**: List of considered factors

### Creator Ledger Entry

Must contain:
- **Creator Name**: Legal name or verified pseudonym
- **Timestamp**: ISO 8601 creation time
- **Commitment**: Formal acceptance of responsibility
- **Signature**: Ed25519 signature (base64)
- **Public Key Fingerprint**: SHA256 of public key

---

## Signing Process

### Generate Keypair (First Time)

```bash
python tools/generate_keys.py
# Creates: ~/.ciris/creator_key.pem and creator_key.pub
```

### Sign Template

```bash
python tools/sign_template.py ciris_templates/your-template.yaml
# Updates template with signature and fingerprint
```

### Verify Signature

```bash
python tools/verify_template.py ciris_templates/your-template.yaml
# Confirms signature validity
```

---

## Validation

### Schema Validation

All templates are validated against `AgentTemplate` schema:

```python
from ciris_engine.schemas.config.agent import AgentTemplate
import yaml

with open("your-template.yaml") as f:
    template = yaml.safe_load(f)
    
# This will raise ValidationError if non-compliant
agent = AgentTemplate(**template['template'])
```

### Compliance Checks

The system enforces:
1. **Required Fields**: All mandatory sections present
2. **Stewardship Tier**: Valid tier (1-10) with rationale
3. **Signature**: Valid Ed25519 signature
4. **Timestamp**: Recent creation (< 90 days for production)

### Testing Templates

```bash
# Validate template structure
python tools/validate_template.py ciris_templates/your-template.yaml

# Test with mock agent
python main.py --template your-template --mock-llm --timeout 60

# Full validation suite
python tools/test_template.py ciris_templates/your-template.yaml
```

---

## Template Evolution

### Version Management

Templates should follow semantic versioning:
- **Major**: Breaking changes to capabilities
- **Minor**: New features or services
- **Patch**: Bug fixes or clarifications

### Migration Path

When updating templates:
1. Increment version number
2. Document changes in template
3. Re-sign with creator key
4. Test thoroughly before deployment

### Deprecation

Old templates should be:
1. Marked as deprecated in description
2. Moved to `ciris_templates/deprecated/`
3. Retained for audit trail

---

## Security Considerations

### Key Management

- **Never commit private keys** to repository
- Store keys in `~/.ciris/` or secure vault
- Use different keys for dev/prod
- Rotate keys annually

### Signature Verification

- All production templates must be signed
- Signatures verified on every load
- Invalid signatures prevent deployment
- Public keys stored in audit system

### Template Injection

- Templates are YAML, not code
- Schema validation prevents injection
- No template can modify system behavior
- All capabilities are pre-defined

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| "Missing stewardship section" | Add complete stewardship block |
| "Invalid signature" | Re-sign with correct key |
| "Schema validation failed" | Check against latest schema |
| "Tier out of range" | Use tier 1-10 only |

### Getting Help

- Check `docs/AGENT_CREATION_CEREMONY.md`
- Review existing templates for examples
- Use validation tools before deployment
- Ask Wise Authority for tier guidance

---

## References

- [Book VI: Ethics of Creation](../covenant_1.0b.txt)
- [Agent Creation Ceremony](../docs/AGENT_CREATION_CEREMONY.md)
- [CIRIS Profiles Documentation](../docs/CIRIS_PROFILES.md)
- [AgentTemplate Schema](../ciris_engine/schemas/config/agent.py)

---

*Remember: With creation comes responsibility. Every agent reflects its creator's values.*