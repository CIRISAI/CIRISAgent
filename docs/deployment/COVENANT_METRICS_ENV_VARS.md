# Covenant Metrics Adapter - Environment Variables

This document describes the environment variables for configuring the CIRIS Covenant Metrics adapter on managed agents to send traces to the CIRISLens server.

## Required for Full Traces

To enable full trace collection (complete reasoning text for Coherence Ratchet corpus):

```bash
# REQUIRED: Enable consent
CIRIS_COVENANT_METRICS_CONSENT=true

# REQUIRED: Set trace level to full_traces
CIRIS_COVENANT_METRICS_TRACE_LEVEL=full_traces
```

## All Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CIRIS_COVENANT_METRICS_CONSENT` | Yes | `false` | Must be `true` to enable data collection |
| `CIRIS_COVENANT_METRICS_CONSENT_TIMESTAMP` | No | auto-generated | ISO timestamp of consent (for audit) |
| `CIRIS_COVENANT_METRICS_TRACE_LEVEL` | No | `generic` | Trace detail: `generic`, `detailed`, or `full_traces` |
| `CIRIS_COVENANT_METRICS_ENDPOINT` | No | `https://lens.ciris.ai/v1` | CIRISLens API endpoint |
| `CIRIS_COVENANT_METRICS_FLUSH_INTERVAL` | No | `60` | Seconds between batch flushes (10-300) |

## Trace Levels

| Level | Data Sent | Use Case |
|-------|-----------|----------|
| `generic` | Numeric scores only (k_eff, plausibility, entropy, etc.) | Default - powers ciris.ai/ciris-scoring |
| `detailed` | + lists (sources_identified, stakeholders, flags) | Debugging without reasoning exposure |
| `full_traces` | + complete reasoning text and prompts | Research corpus contribution |

## Example Docker Compose

```yaml
services:
  ciris-agent:
    image: cirisai/agent:1.8.1
    environment:
      # Covenant Metrics - Full Traces
      CIRIS_COVENANT_METRICS_CONSENT: "true"
      CIRIS_COVENANT_METRICS_TRACE_LEVEL: "full_traces"
      CIRIS_COVENANT_METRICS_ENDPOINT: "https://lens.ciris.ai/v1"

      # Other agent config...
      DISCORD_TOKEN: "${DISCORD_TOKEN}"
```

## Example Kubernetes ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: ciris-agent-config
data:
  CIRIS_COVENANT_METRICS_CONSENT: "true"
  CIRIS_COVENANT_METRICS_TRACE_LEVEL: "full_traces"
  CIRIS_COVENANT_METRICS_ENDPOINT: "https://lens.ciris.ai/v1"
```

## Early Warning Correlation (Config File Only)

These fields are set via the setup wizard or adapter config, not environment variables:

- `deployment_region`: Geographic region (na, eu, uk, apac, latam, mena, africa, oceania)
- `deployment_type`: personal, business, research, nonprofit
- `agent_role`: assistant, customer_support, content, coding, research, education, moderation, automation
- `agent_template`: CIRIS template name if applicable (e.g., `discord-moderator`)

## Verification

After deployment, check the agent logs for:

```
📊 COVENANT METRICS ADAPTER INITIALIZING
   Config consent_given: False
   Env CIRIS_COVENANT_METRICS_CONSENT: true
   Env CIRIS_COVENANT_METRICS_ENDPOINT: https://lens.ciris.ai/v1
✅ CONSENT enabled via environment variable CIRIS_COVENANT_METRICS_CONSENT
```

And for successful trace sends:

```
✅ TRACE COMPLETE #1: trace-th_seed_xxx-20260115... [6 components]
📤 Sending batch of 10 events to https://lens.ciris.ai/v1
```
