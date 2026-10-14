# Covenant Metrics Adapter - Environment Variables

This document describes how to configure the CIRIS Covenant Metrics adapter on managed agents to send traces to the CIRISLens server.

## Loading the Adapter

The covenant metrics adapter is **NOT auto-loaded** by default. It must be explicitly loaded.

### Via Environment Variable (Recommended for Managed Deployments)

```bash
# Comma-separated list of adapters to load
CIRIS_ADAPTER=api,ciris_accord_metrics

# Or with Discord
CIRIS_ADAPTER=discord,ciris_accord_metrics
```

### Via Command Line

```bash
python main.py --adapter api --adapter ciris_accord_metrics
```

## Required for Full Traces

To enable full trace collection (complete reasoning text for Coherence Ratchet corpus):

```bash
# REQUIRED: Load the adapter
# (via --adapter ciris_accord_metrics as shown above)

# REQUIRED: Enable consent
CIRIS_ACCORD_METRICS_CONSENT=true

# REQUIRED: Set trace level to full_traces
CIRIS_ACCORD_METRICS_TRACE_LEVEL=full_traces
```

## All Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CIRIS_ACCORD_METRICS_CONSENT` | Yes | `false` | Must be `true` to enable data collection |
| `CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP` | No | auto-generated | ISO timestamp of consent (for audit) |
| `CIRIS_ACCORD_METRICS_TRACE_LEVEL` | No | `generic` | Trace detail: `generic`, `detailed`, or `full_traces` |
| `CIRIS_ACCORD_METRICS_ENDPOINT` | No | `https://lens.ciris-services-1.ai/lens-api/api/v1` | CIRISLens API endpoint |
| `CIRIS_ACCORD_METRICS_FLUSH_INTERVAL` | No | `60` | Seconds between batch flushes (10-300) |

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
      # Load adapters (comma-separated)
      CIRIS_ADAPTER: "api,ciris_accord_metrics"

      # Covenant Metrics - Full Traces
      CIRIS_ACCORD_METRICS_CONSENT: "true"
      CIRIS_ACCORD_METRICS_TRACE_LEVEL: "full_traces"
      CIRIS_ACCORD_METRICS_ENDPOINT: "https://lens.ciris-services-1.ai/lens-api/api/v1"

      # Other agent config...
      OPENAI_API_KEY: "${OPENAI_API_KEY}"
```

For Discord agents:

```yaml
services:
  ciris-agent:
    image: cirisai/agent:1.8.1
    environment:
      CIRIS_ADAPTER: "discord,ciris_accord_metrics"
      DISCORD_BOT_TOKEN: "${DISCORD_BOT_TOKEN}"
      CIRIS_ACCORD_METRICS_CONSENT: "true"
      CIRIS_ACCORD_METRICS_TRACE_LEVEL: "full_traces"
```

## Example Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ciris-agent
spec:
  template:
    spec:
      containers:
      - name: ciris-agent
        image: cirisai/agent:1.8.1
        envFrom:
        - configMapRef:
            name: ciris-agent-config
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: ciris-agent-config
data:
  # Load adapters (comma-separated)
  CIRIS_ADAPTER: "api,ciris_accord_metrics"
  # Covenant Metrics - Full Traces
  CIRIS_ACCORD_METRICS_CONSENT: "true"
  CIRIS_ACCORD_METRICS_TRACE_LEVEL: "full_traces"
  CIRIS_ACCORD_METRICS_ENDPOINT: "https://lens.ciris-services-1.ai/lens-api/api/v1"
```

## Early Warning Correlation (Config File Only)

These fields are set via the setup wizard or adapter config, not environment variables:

- `deployment_region`: Geographic region (na, eu, uk, apac, latam, mena, africa, oceania)
- `deployment_type`: personal, business, research, nonprofit
- `agent_role`: assistant, customer_support, content, coding, research, education, moderation, automation
- `agent_template`: CIRIS template name if applicable (e.g., `discord-moderator`)

### trace_format v2.8.0 only (`CIRIS_TRACE_FORMAT_VERSION=2.8.0`)

Under v2.8.0 these inputs are also read. Adapter config wins over each env var, and none of them is read under the default v2.7.0.

| Input | Signed member | Used when |
|-------|---------------|-----------|
| `CIRIS_ACCORD_METRICS_DEPLOYMENT_REGION` | `deployment_profile.deployment_region` | the config has no `deployment_region` |
| `CIRIS_TEMPLATE` (setup wizard / CIRISManager) | `deployment_profile.agent_template` | the config has no `agent_template` |
| `CIRIS_MANAGED=true` (CIRISManager) | `deployment_profile.run_kind = prod-managed` | the run is production and nobody declared a run kind; otherwise `prod-personal` |
| adapter config `run_kind` | `deployment_profile.run_kind` | an operator override (`production`, `prod-personal`, `prod-managed`, `qa`, `battery`); a harness `CIRIS_TRACE_RUN_KIND=qa|battery` and the mock LLM still win |

## Verification

After deployment, check the agent logs for:

```
📊 COVENANT METRICS ADAPTER INITIALIZING
   Config consent_given: False
   Env CIRIS_ACCORD_METRICS_CONSENT: true
   Env CIRIS_ACCORD_METRICS_ENDPOINT: https://lens.ciris-services-1.ai/lens-api/api/v1
✅ CONSENT enabled via environment variable CIRIS_ACCORD_METRICS_CONSENT
```

And for successful trace sends:

```
✅ TRACE COMPLETE #1: trace-th_seed_xxx-20260115... [6 components]
📤 Sending batch of 10 events to https://lens.ciris-services-1.ai/lens-api/api/v1
```
