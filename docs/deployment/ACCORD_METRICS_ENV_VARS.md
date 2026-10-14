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
- `deployment_type`: operator free-form label; the wizard offers personal, business, research, nonprofit. On a non-production run (trace_format v2.7.0) the agent overrides it with the run kind `mock`, `qa` or `battery`; see "Run kind" below.
- `agent_role`: assistant, customer_support, content, coding, research, education, moderation, automation
- `agent_template`: CIRIS template name if applicable (e.g., `discord-moderator`)

## Run kind (`CIRIS_TRACE_RUN_KIND`)

Every trace says what kind of run produced it: `production`, `qa`,
`battery` or `mock` (CIRISAgent#1245). Anything outside a harness run is
production, so production deployments set nothing.

- `mock`: the mock LLM is active. Always wins, cannot be overridden;
  mock traces never leave the node.
- `qa` / `battery`: declared by the harness with
  `CIRIS_TRACE_RUN_KIND`. The QA runner, its web_ui and mobile
  harnesses, the HE-300 runner, the AgentBeats image and the demo
  recorder all declare it themselves, and replace an inherited
  `production`.
- Backstop: if a process carries a harness-only launch flag
  (`CIRIS_TESTING_MODE`, `CIRIS_BENCHMARK_MODE`, `CIRIS_TEST_MODE`,
  `CIRIS_RESEARCH_PROMPT_OVERRIDES`) but declares no run kind (or
  `production`), its traces are marked `qa`. These flags only ever move
  a run away from production.

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
