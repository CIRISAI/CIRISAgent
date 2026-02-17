# CIRISNode Adapter - Claude Code Context

## Role

CIRISNode oversight adapter — routes deferrals and forwards Ed25519-signed covenant traces to CIRISNode. Registers as `WISE_AUTHORITY` on the WiseBus.

**FOR AUTHORIZED PARTNERS ONLY**: Partners must register agents via CIRISPortal (portal.ciris.ai) → CIRISRegistry to obtain signing keys and access to CIRISNode deferral management.

## Architecture

```
CIRISAgent (local)
  ├─ cirisnode adapter (this) ──► CIRISNode (node.ciris-services-1.ai)
  │   ├─ WBD deferrals (signed)     ├─ Verifies sigs against Registry
  │   ├─ Covenant traces (signed)    ├─ Stores full traces
  │   └─ Public key registration     └─ Routes WBD to Wise Authorities
  │
  └─ ciris_covenant_metrics adapter ──► CIRISLens (separate concern)
      └─ Detailed traces (signed)
```

**Key principle**: Only CIRISRegistry stores keys. CIRISNode verifies signatures against Registry. Signing keys are generated via CIRISPortal (portal.ciris.ai) → CIRISRegistry.

## Auth Model

- **No tokens**: Auth is entirely Ed25519 signature-based
- **Signing key**: Generated at CIRISPortal (portal.ciris.ai) → stored in CIRISRegistry → provided to agent at install time
- **CRITICAL**: Keys MUST come from Registry. Self-generated keys are NOT in Registry and CIRISNode cannot verify them.
- **Key registration**: At startup, adapter registers the provided public key with CIRISNode (`POST /api/v1/covenant/public-keys`)
- **Key registration = covenant_metrics consent**: No separate consent flow
- **CIRISNode verifies** all signatures against CIRISRegistry via gRPC `GetPublicKeys`
- **X-Agent-Token**: Optional bootstrap auth for initial key registration (env: `CIRISNODE_AGENT_TOKEN`)

## Files

| File | Purpose |
|------|---------|
| `adapter.py` | Adapter lifecycle, registers CIRISNodeService as WISE_AUTHORITY |
| `services.py` | Core service: deferral routing, trace capture/batching, Ed25519 signing |
| `client.py` | Async HTTP client for CIRISNode API (httpx) |
| `manifest.json` | Adapter metadata, capabilities, configuration schema |

## Configuration

| Key | Env Var | Default | Description |
|-----|---------|---------|-------------|
| `base_url` | `CIRISNODE_BASE_URL` | `https://node.ciris-services-1.ai` | CIRISNode API URL (US default) |
| `agent_token` | `CIRISNODE_AGENT_TOKEN` | *(empty)* | Optional bootstrap token for key registration |

**Regional Servers:**
- **US**: `https://node.ciris-services-1.ai` (default)
- **EU**: `https://node.ciris-services-2.ai`
| `trace_level` | `CIRISNODE_TRACE_LEVEL` | `generic` | `generic`, `detailed`, or `full_traces` |
| `poll_interval` | — | `30` | Seconds between WBD resolution polls |
| `batch_size` | — | `10` | Trace events per batch |
| `flush_interval` | — | `60` | Seconds between batch flushes |

### Trace Levels

- **`generic`**: Minimal traces (action taken, no reasoning)
- **`detailed`**: Includes reasoning summaries (sent to Lens via covenant_metrics)
- **`full_traces`**: Full reasoning text, prompts, context (sent to Node via this adapter)

**Convention**: `full_traces` to CIRISNode, `detailed` to CIRISLens.

## Deferral Flow ($defer)

```
1. Mock LLM returns $defer command
2. ASPDMA → DEFER action
3. DeferHandler broadcasts to WiseBus
4. CIRISNodeService.send_deferral() receives it
5. Signs payload with Ed25519 unified key
6. POST /api/v1/wbd/submit (signed)
7. CIRISNode verifies signature → creates WBD task
8. Task routed to Wise Authority based on domain_hint
9. Background poll every 30s: GET /api/v1/wbd/tasks/{id}
10. On resolution: logs decision, posts agent event
```

**DEFER is terminal**: No follow-up thoughts. Task stays DEFERRED until Wise Authority resolves via CIRISNode.

## Trace Forwarding

- Subscribes to `reasoning_event_stream` (same as covenant_metrics)
- Builds `CompleteTrace` from 6 component types: observation, context, rationale (x2), conscience, action
- Signs each completed trace with Ed25519
- Batches and sends to `POST /api/v1/covenant/events` (Lens format)
- Re-uses extraction logic from `ciris_covenant_metrics.services` for format compatibility

## CIRISNode API Endpoints Used

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| POST | `/api/v1/wbd/submit` | Ed25519 signature | Submit signed deferral |
| GET | `/api/v1/wbd/tasks/{id}` | None | Poll deferral resolution |
| POST | `/api/v1/covenant/events` | Ed25519 inline signatures | Batch covenant traces |
| POST | `/api/v1/covenant/public-keys` | X-Agent-Token (optional) | Register signing key |
| POST | `/api/v1/agent/events` | X-Agent-Token | Post agent events |

## WBD Resolution Flow (FIXED 2026-02-13)

When a WBD task is resolved on CIRISNode, the adapter:
1. **Sends signed resolution covenant trace** — `CompleteTrace` with `wbd_resolution` component, Ed25519 signed, sent via `post_covenant_events()` (no header auth)
2. **Reactivates the deferred task** — calls `WiseAuthorityService.resolve_deferral()` via global service registry, which creates a new guidance task. Agent processes it automatically through the normal reasoning pipeline, generating standard reasoning traces that are also forwarded to CIRISNode.

Auth is ALWAYS Ed25519 signature-based. No token-based auth (`X-Agent-Token`) is used for trace/resolution data.

## Known Issues (E2E QA 2026-02-13)

1. **Trace level convention**: Set `CIRISNODE_TRACE_LEVEL=full_traces` for Node, covenant_metrics uses `detailed` for Lens
2. **Key registration timing**: Public key registered at adapter `start()` — runtime identity must be initialized before this
3. **Agent ID hash**: First 16 chars of SHA-256 of agent_id, used for trace anonymization
4. **WBD polling continues until stop()**: Pending deferrals logged as warning if adapter stops before resolution
5. **Private key provisioning (FIXED)**: Portal now shows a one-time download dialog after key generation. Download `agent_signing.key` (raw 32-byte Ed25519 private key) and place it in `data/agent_signing.key`. The adapter auto-loads it at startup and derives the key_id as `agent-{sha256(pubkey)[:12]}`.
6. **org_id auto-discovery (FIXED)**: No `org_id` config needed on the agent. CIRISNode computes the Ed25519 fingerprint (SHA-256 of public key) and looks it up in Registry via `GetPublicKeys(ed25519_fingerprint=...)`. Registry returns org_id and verification status automatically.
7. **CIRISNode SQLite ephemeral**: Agent tokens and registered keys are lost on CIRISNode container restart. Agent must re-register its key (happens automatically at adapter `start()`). With fingerprint auto-discovery, re-registration auto-verifies — no manual admin override needed.

## Development

```bash
# CIRISNode is for AUTHORIZED PARTNERS ONLY
# Partners must register agents via CIRISPortal (portal.ciris.ai) → CIRISRegistry
# This grants access to manage deferrals via CIRISNode

# Enable adapter manually in agent config (NOT auto-enabled by any template)
# Environment for testing (requires valid registration)
export CIRISNODE_BASE_URL=https://node.ciris-services-1.ai
export CIRISNODE_TRACE_LEVEL=full_traces
export CIRISNODE_AGENT_TOKEN=<optional-bootstrap-token>

# Start agent with adapter
python main.py --adapter api --mock-llm --port 8000 --template echo --debug
```
