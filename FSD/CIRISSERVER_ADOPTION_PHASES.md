# FSD: CIRISServer Adoption — Phases & Gates (agent-side tracking)

**Status:** Active. Tracks CIRISAgent#896. Mirror of the file-level map in
CIRISServer `FSD/CIRISAGENT_ADOPTION.md`, kept on the agent side with the
**live gate status** and the **end-state targeting decision** (2026-06-25).

**Substrate baseline (verified in the wheel):** `ciris-server` **≥ 0.5.43**
(persist v10 / edge v7 / verify v7.2 / lens re-hosted). The agent depends on the
**one wheel only** for substrate; `ciris_verify` stays standalone until Phase 3.

---

## 1. The end state (the target we build toward)

`CIRISAgent = the ciris-server wheel + the brain`, mounted **into the node's own
router** — not a sibling process.

- **One process, one port.** `ciris_server.serve_with_python_adapter(brain, home, key_id)`
  (shipped 0.5.41, CIRISServer#80) folds the Python brain's routes into the
  node's router. Substrate routes (federation/identity/trust/config/accord/
  health/memory-read) **and** brain routes (chat/cognition/LLM-status/skills)
  are served on the **node's single port (4243)**.
- **No standalone substrate wheels.** `from ciris_server import Engine, NotFound,
  reset_engine, Edge, init_edge_runtime, LensClient` — one PyO3 type registry.
- **Zero env vars.** All config is signed `config:*` CEG resolved by the node at
  boot; the agent passes only `--home` / `--key-id`.
- **Brain = `processors` + `dma` + `conscience` + `context` + `handlers` +
  llm/tool services + templates + cognitive adapters** (~30k core + connectors).
  Everything substrate-covered is deleted.

> **Targeting decision (2026-06-25):** build toward the **single-port (4243)**
> end state directly. The original doc's `4243-substrate / 8080-brain` split was
> predicated on the *interim* sibling-listener architecture, which #80 retired.
> Phase 5 (client) therefore points the **unified** client at 4243 and lands
> with/after Phase 4 (brain fold) — avoiding a double refactor of `CIRISApiClient`.

`main.py` target shape:
```python
import ciris_server
from ciris_brain import BrainAdapter   # processors/dma/conscience/... surviving cognition

def main():
    # No .env parsing, no CIRIS_HOME juggling, no load_config():
    # config is signed config:* CEG resolved by the node at boot.
    ciris_server.serve_with_python_adapter(BrainAdapter(), home=..., key_id=...)
```

---

## 2. Bridge vs destination (two tracks, kept in sync)

- **Bridge (Option 1):** the persist **brain-data feature flags** (`cirislens_tasks/
  thoughts/tickets/correlations/...`, `secrets`, `cirisaudit`, `telemetry`) are
  enabled in the wheel (CIRISServer#83/#86/#87, shipped 0.5.43), so the agent's
  *current* data layer keeps working on the one wheel **today**.
- **Destination (Option 2 / 3.0):** migrate each domain off the bridge to
  CEG-native (`attestation_upsert_local` / `cirisgraph_*`) or `ciris_keyring`,
  then delete the Python **and** drop that persist feature. The bridge shrinks as
  the destination advances. Design: `FSD/CEG_NATIVE_AGENT.md` (#840).

---

## 3. Upstream gates — status (the agent is only *blocked* on these)

| Gate | Unblocks | Status |
|---|---|---|
| **#1** one-wheel re-export (`reset_engine`/`init_edge_runtime`) | Phase 0 imports | ✅ 0.5.39 |
| **CIRISServer#83** audit-write surface (`audit_record_entry`) | Phase 0 audit | ✅ 0.5.40 |
| **CIRISServer#86/#87** 11 brain-data persist features (38 Engine methods) | Phase 0 data layer | ✅ 0.5.43 |
| **CIRISServer#80** `serve_with_python_adapter` (Python brain folds into router) | Phase 4 in-router mount | ✅ 0.5.41 |
| **CIRISPersist#171** shared CEG attestation surface (write/query/promote) | Phase 1 CEG-native migration | ✅ **substrate shipped** in v10 (issue stays open as the 4-impl RC1 gate; the agent's #840 conformance is what closes its quarter) |
| **CIRISServer#118** lens seal stamps the **derived** key (`verify_unknown_key`) | Phase 0 **live trace-shipping** | ⏳ **PENDING — server 0.5.53** (the only remaining upstream blocker in the whole adoption) |

**Net:** after #118, the agent has **no** remaining upstream dependency. Phases
1–5 are all agent-side work, unblocked today.

---

## 4. Phases & gates

### Phase 0 — Single-wheel swap (no behavior change) — `PR #897`
- **Entry:** wheel re-exports the full 69-method agent surface → ✅ (0.5.43)
- **Work:** `_substrate.py` seam + import flips (`graph.py`, `db/core.py`,
  `chain_bridge.py`, `edge_runtime.py`); drop standalone persist/edge; pin
  `ciris-server>=0.5.43`; `register_self_federation_key` (v10 self-key reg).
- **Exit:** agent boots, full suite green on one wheel, **live trace-shipping works**.
- **Status:** green except trace-shipping — **8/8 shards ✅, Type Check ✅,
  Staged QA (all_2) ✅, 13,933 tests ✅**. The only red (Staged QA all_1) is
  `verify_unknown_key`, root-caused to **CIRISServer#118** and clears with 0.5.53.
  Release-gate **stage7**.

### Phase 1 — Delete persistence + audit + secrets (~12k LOC) — *unblocked*
- **Entry:** #118 green (trace persist works) — substrate write/query/promote shipped.
- **Work:** secrets → `ciris_keyring` (clean, self-contained); cognitive store
  (task/thought/ticket) → `attestation_upsert_local` self-attestations + the
  one-shot `migrate_graph_nodes_to_attestations()` boot pass (hard cut, **no
  dual-write**, per `FSD/CEG_NATIVE_AGENT.md`); audit → verify chain. Delete
  `logic/persistence`, `logic/audit`, `logic/secrets`; drop those persist features.
- **Exit:** memory/audit/keystore route through the wheel; no `secrets.db`; no
  SQLite layer; the agent's quarter of CIRISPersist#171 conforms.

### Phase 2 — Delete config + env-var handling (config-as-CEG)
- **Entry:** node resolves signed `config:*` CEG (in-wheel; verify present).
- **Work:** delete `logic/config`; remove **every** `os.environ`/`getenv` (incl.
  LLM keys → brain config, not fabric env).
- **Exit:** agent boots with **zero env vars** (only `--home`/`--key-id`).

### Phase 3 — Delete auth + identity + federation + accord (~20k LOC, biggest)
- **Entry:** node's 4243 auth/federation/accord surface usable end-to-end.
- **Work:** delete `services/governance`, `services/infrastructure/authentication`,
  `routes/{auth,setup,federation}`, `logic/accord`, `ciris_adapters/cirisnode`.
  *Ship the auth cut alone first, behind a flag.*
- **Exit:** login/OAuth/claim/peering/device-grant/accord-kill-switch all work
  against ciris-server; the disk halt latch gates the agent.

### Phase 4 — Fold the brain into the node router — *unblocked (end-state)*
- **Entry:** `serve_with_python_adapter` ✅ (0.5.41). **No interim :8080 sibling.**
- **Work:** reduce `logic/runtime` to a thin `BrainAdapter` (the cognitive loop
  on the Adapter seam) + `main.py` → `ciris_server.serve_with_python_adapter(...)`.
  The brain's routes serve on the node's single port (4243).
- **Exit:** node + brain are **one process on one port** sharing one Engine; ctrl-c
  stops both.

### Phase 5 — Unify the client on the node port + adopt the superset screens
- **Entry:** Phase 4 landed (single-port end state). *(Screen adoption can start in parallel.)*
- **Work:** vendor CIRISServer's superset `client/` (+6 screens: Identity/
  self-occurrence, Contacts, Delegations, Accord ceremony/provision; YubiKey NFC
  fed-ID). Point `CIRISApiClient` at the **single node port (4243)** for both
  substrate and brain routes — replacing the legacy `8080` default and retiring
  the `LOCAL_NODE_URL` split-port concept (no longer needed once the brain folds in).
- **Exit:** the unified client connects to a brain-less node (4243) **and** a full
  agent (4243), and the 6 new screens function.

### Phase 6 — Cut: agent 2.9.x adoption → unblock Server 0.6
- **Entry:** Phases 0–5 green.
- **Exit:** CIRISServer `tests/release_gates.rs` **stage7 + stage8** flip green → cut 0.6.

---

## 5. Critical path / sequencing

1. **#118 lands (0.5.53)** → Phase 0 fully green → **merge #897** (stage7 evidence).
2. **Phase 1 CEG-native migration** + **Phase 2 config-as-CEG**: both agent-side,
   unblocked. Secrets→keyring and config are the clean, self-contained starts;
   the cognitive-store CEG cut is the long pole (#840 conformance).
3. **Phase 3** (auth/federation/accord deletion): biggest, stage behind a flag.
4. **Phase 4 (brain fold) + Phase 5 (unified client)**: land together toward the
   single-port end state — the client targets 4243 once the brain is folded in.
5. **Phase 6**: stage7/stage8 green → cut 0.6.

Phase 5 *screen adoption* (the +6 superset screens, additive) has no hard
dependency and can begin in parallel any time; only the **port unification**
waits on Phase 4.
