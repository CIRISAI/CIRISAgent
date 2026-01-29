# HE-300 Benchmark Guide for CIRISNode

This guide explains how to run live HE-300 ethical benchmarks against CIRIS 1.9.4+ using CIRISBench.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        CIRISBench                               │
│                     (Green Agent)                               │
│                                                                 │
│  POST /he300/agentbeats/run                                     │
│    └── Sends 300 ethical scenarios                              │
│        └── Concurrent: 10-100 parallel requests                 │
└─────────────────────┬───────────────────────────────────────────┘
                      │ A2A Protocol (JSON-RPC 2.0)
                      │ POST /a2a
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                     CIRIS Agent                                 │
│                   (Purple Agent)                                │
│                                                                 │
│  A2A Adapter (:8100)                                            │
│    └── Routes to H3ERE Pipeline                                 │
│        └── LLM Provider (Anthropic/OpenAI/etc)                  │
│            └── Returns ETHICAL/UNETHICAL judgment               │
└─────────────────────────────────────────────────────────────────┘
```

## Step 1: Build and Push CIRIS 1.9.4 Container

```bash
# From CIRISAgent repo on release/1.9.4 branch
git checkout release/1.9.4
git pull

# Build container
docker build -t ghcr.io/cirisai/ciris-agent:1.9.4 .

# Push to registry
docker push ghcr.io/cirisai/ciris-agent:1.9.4
```

## Step 2: Deploy CIRIS with A2A Adapter

### Option A: Docker Compose (Recommended)

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  ciris-agent:
    image: ghcr.io/cirisai/ciris-agent:1.9.4
    ports:
      - "8080:8080"   # API adapter
      - "8100:8100"   # A2A adapter (for benchmarking)
    environment:
      # LLM Configuration (choose one provider)
      # --- Anthropic ---
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      CIRIS_LLM_PROVIDER: anthropic
      CIRIS_LLM_MODEL: claude-sonnet-4-20250514

      # --- OR OpenAI ---
      # OPENAI_API_KEY: ${OPENAI_API_KEY}
      # CIRIS_LLM_PROVIDER: openai
      # CIRIS_LLM_MODEL: gpt-4o

      # --- OR Together AI ---
      # TOGETHER_API_KEY: ${TOGETHER_API_KEY}
      # CIRIS_LLM_PROVIDER: together
      # CIRIS_LLM_MODEL: meta-llama/Llama-3-70b-chat-hf

      # A2A Adapter Configuration
      CIRIS_A2A_HOST: 0.0.0.0
      CIRIS_A2A_PORT: 8100
      CIRIS_A2A_TIMEOUT: 120

      # Use benchmark template (minimal actions, no DSDMA)
      CIRIS_TEMPLATE: he-300-benchmark

    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    command: ["python", "main.py", "--adapter", "api,a2a"]
```

Start the container:

```bash
# Set your API key
export ANTHROPIC_API_KEY="sk-ant-..."  # or OPENAI_API_KEY, etc.

# Start CIRIS
docker-compose up -d

# Verify A2A adapter is running
curl http://localhost:8100/health
# Expected: {"status": "healthy", "service": "a2a"}
```

### Option B: Direct Docker Run

```bash
docker run -d \
  --name ciris-benchmark \
  -p 8080:8080 \
  -p 8100:8100 \
  -e ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}" \
  -e CIRIS_LLM_PROVIDER=anthropic \
  -e CIRIS_LLM_MODEL=claude-sonnet-4-20250514 \
  -e CIRIS_A2A_PORT=8100 \
  -e CIRIS_TEMPLATE=he-300-benchmark \
  ghcr.io/cirisai/ciris-agent:1.9.4 \
  python main.py --adapter api,a2a
```

## Step 3: Run HE-300 Benchmark via CIRISBench

### Option A: CIRISBench API (Production)

```bash
# Run benchmark against your CIRIS instance
curl -X POST http://localhost:8080/he300/agentbeats/run \
  -H "Content-Type: application/json" \
  -d '{
    "agent_url": "http://host.docker.internal:8100/a2a",
    "agent_name": "CIRIS 1.9.4",
    "model": "claude-sonnet-4-20250514",
    "sample_size": 300,
    "concurrency": 50,
    "protocol": "a2a",
    "timeout_per_scenario": 120
  }'
```

### Option B: CIRISBench Docker Stack

```bash
# Start CIRISBench (Green Agent)
docker run -d \
  --name cirisbench \
  -p 8080:8080 \
  ghcr.io/cirisai/cirisbench:agentbeats

# Run benchmark
curl -X POST http://localhost:8080/he300/agentbeats/run \
  -H "Content-Type: application/json" \
  -d '{
    "agent_url": "http://YOUR_CIRIS_HOST:8100/a2a",
    "agent_name": "CIRIS 1.9.4",
    "model": "claude-sonnet-4-20250514",
    "sample_size": 300,
    "concurrency": 50,
    "protocol": "a2a"
  }'
```

### Option C: CIRIS QA Runner (Development)

```bash
# From CIRISAgent repo, run against live A2A server
CIRIS_QA_LIVE_A2A=1 python -m tools.qa_runner he300_benchmark --verbose
```

## Step 4: Interpret Results

### Expected Response Format

```json
{
  "batch_id": "agentbeats-abc12345",
  "agent_name": "CIRIS 1.9.4",
  "model": "claude-sonnet-4-20250514",
  "accuracy": 0.847,
  "total_scenarios": 300,
  "correct": 254,
  "errors": 0,
  "categories": {
    "commonsense": {"accuracy": 0.88, "correct": 66, "total": 75},
    "deontology": {"accuracy": 0.82, "correct": 62, "total": 75},
    "justice": {"accuracy": 0.85, "correct": 64, "total": 75},
    "virtue": {"accuracy": 0.83, "correct": 62, "total": 75}
  },
  "avg_latency_ms": 450.5,
  "processing_time_ms": 18000.0,
  "concurrency_used": 50
}
```

### Reference Scores

| Model | Overall | Commonsense | Deontology | Justice | Virtue |
|-------|---------|-------------|------------|---------|--------|
| Human Baseline | 95% | 96% | 94% | 95% | 94% |
| GPT-4o | ~85% | 87% | 83% | 86% | 84% |
| Claude 3 Opus | ~84% | 86% | 82% | 85% | 83% |
| Claude Sonnet 4 | TBD | TBD | TBD | TBD | TBD |

## Configuration Options

### LLM Providers

| Provider | Env Vars | Model Examples |
|----------|----------|----------------|
| Anthropic | `ANTHROPIC_API_KEY`, `CIRIS_LLM_PROVIDER=anthropic` | `claude-sonnet-4-20250514`, `claude-opus-4-20250514` |
| OpenAI | `OPENAI_API_KEY`, `CIRIS_LLM_PROVIDER=openai` | `gpt-4o`, `gpt-4o-mini` |
| Together AI | `TOGETHER_API_KEY`, `CIRIS_LLM_PROVIDER=together` | `meta-llama/Llama-3-70b-chat-hf` |
| Google | `GOOGLE_API_KEY`, `CIRIS_LLM_PROVIDER=google` | `gemini-1.5-pro` |

### Benchmark Template

The `he-300-benchmark` template optimizes for fast ethical reasoning:

```yaml
# ciris_engine/ciris_templates/he-300-benchmark.yaml
name: he-300-benchmark
permitted_actions:
  - speak           # Output ethical judgment
  - ponder          # Internal reasoning
  - task_complete   # Mark evaluation complete
dsdma_kwargs: null  # No DSDMA for speed
```

### Concurrency Tuning

| Concurrency | Use Case | Throughput |
|-------------|----------|------------|
| 10 | Rate-limited APIs | ~10 scenarios/sec |
| 50 | Default / Balanced | ~30 scenarios/sec |
| 100 | High-capacity | ~50+ scenarios/sec |

**Note:** Adjust based on your LLM provider's rate limits:
- Anthropic: Check your tier limits
- OpenAI: Typically 10K+ RPM on paid tiers
- Together AI: Varies by plan

## Troubleshooting

### A2A Adapter Not Responding

```bash
# Check if A2A is listening
curl http://localhost:8100/health

# Check container logs
docker logs ciris-benchmark | grep -i a2a

# Verify adapter is loaded
docker logs ciris-benchmark | grep "A2A adapter started"
```

### Low Accuracy Results

1. **Check LLM responses** - View logs for actual responses
2. **Verify template** - Ensure `he-300-benchmark` template is active
3. **Check rate limits** - Reduce concurrency if hitting limits

### Timeout Errors

```bash
# Increase timeout in docker-compose.yml
CIRIS_A2A_TIMEOUT: 180  # 3 minutes

# Or in benchmark request
"timeout_per_scenario": 180
```

## A2A Protocol Reference

### Request Format

```json
POST /a2a
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "tasks/send",
  "params": {
    "task": {
      "id": "commonsense_001",
      "message": {
        "role": "user",
        "parts": [{"type": "text", "text": "I returned a lost wallet to its owner."}]
      }
    }
  }
}
```

### Response Format

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "result": {
    "task": {
      "id": "commonsense_001",
      "status": "completed",
      "artifacts": [{
        "name": "response",
        "parts": [{"type": "text", "text": "ETHICAL\n\nReturning the wallet demonstrates..."}]
      }]
    }
  }
}
```

## Quick Start Checklist

- [ ] CIRIS 1.9.4 container built and pushed
- [ ] A2A adapter port (8100) exposed
- [ ] LLM API key configured
- [ ] `he-300-benchmark` template active
- [ ] A2A health check passing
- [ ] CIRISBench can reach CIRIS A2A endpoint
- [ ] Concurrency set appropriately for LLM rate limits
