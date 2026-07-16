# First-Run Journey Statechart & Provisioning-Saga DAG

**Status**: Normative for 2.9.7+ · **Validated by**: `tools/qa_runner/modules/mobile/order_conformance.py`
**Scope**: the mobile/desktop first-run experience (OOBE) on the embedded-node topology — everything
between a fresh install and the first authenticated Interact turn.

Three layers, three named disciplines:

| Layer | Discipline | What it kills |
|---|---|---|
| UI screens as explicit machine states | statechart-driven UI (Harel/XState) | nav loops (READY→login cycling) |
| Ordered side-effecting setup steps | provisioning saga + precedence DAG | session-ordering 401s (claim, setAge) |
| Machine validation of observed runs | trace conformance (light model checking) | "worked on my emulator" order regressions |

The bug class this document exists for: **three separate first-run bugs were each an edge missing
from an implicit order** — complete-before-claim (401), first-run check racing the restart
(nav loop), and completeSetup racing the post-claim block (setAge 401). Every one becomes a
red `ORDER VIOLATION` line under conformance instead of a day of log archaeology.

---

## 1. State axes (the product space, exhaustively)

A run's true state is a tuple over five independent axes. UI bugs happen when the UI
renders an axis it never actually checked.

### N — Node (substrate process, `:4243`)
| id | state | observable predicate |
|---|---|---|
| N0 | ABSENT | `CIRIS_NODE_FOLD=false` logged |
| N1 | COMPOSING | `[COMPOSE] phase:` lines advancing (21 stamps) |
| N2 | BOUND | `read-API LISTENING on 4243` / TCP connect OK |
| N3 | REUSED | `4243 already serving … reusing the live node` |
| N4 | RESTARTING | `shutdown_node() → :4243 bindable=` (0.5.122) |
| N5 | FAILED | bind-window expiry / `_node_error` → **agent aborts** |

### O — Ownership (persist-backed; survives restarts)
| id | state | observable predicate |
|---|---|---|
| O0 | UNOWNED, no fed-ID | `getOwnerHint()==null`, no key_id |
| O1 | UNOWNED, fed-ID minted | mint logged, `getOwnerHint()==null` |
| O2 | OWNED | `getOwnerHint()!=null` (claim-remote accepted) |
| O2a | OWNED + age recorded | `age band … recorded` |
| O2b | OWNED + announced | `announced to federation` |

### S — `:4243` session (volatile; dies with every runtime restart)
| id | state | how it arises |
|---|---|---|
| S0 | none | before first auth |
| S1 | SETUP session | first-boot bearer (wizard's working credential) |
| S2 | OWNER session | post-claim `login(waId, password)` → `setAccessToken` |
| S3 | INVALIDATED | runtime restart — **every** bearer 401s until re-login |

### B — Brain/config (`:8080`)
| id | state | observable predicate |
|---|---|---|
| B0 | UNCONFIGURED | first-run wizard offered |
| B1 | CONFIG WRITTEN | `completeSetup returned: success=true` |
| B2 | RESTARTING | both ports flapping |
| B3 | READY (owned) | owner hint present on :8080 and :4243 |

### U — UI screen (must be a *projection* of N×O×S×B, never independent)
`STARTUP → SETUP_WIZARD(steps…) → RECONFIGURING_HOLD → LOGIN → INTERACT`
plus terminal `ERROR` / `TIMEOUT` states.

**The one statechart law**: a screen transition is legal only when the underlying axes say so.
`LOGIN` requires `N2 ∧ B3 ∧ O2`; `SETUP_WIZARD` requires `O0∨O1` (an owned node is never
first-run); `RECONFIGURING_HOLD` is the *only* legal UI state while `B2 ∨ N4`.

---

## 2. The provisioning saga (event vocabulary)

Canonical events, each with a machine-parseable marker. Kotlin emits
`[ORDER] <event> …` via PlatformLogger; node/python-side markers are mapped by the validator.

| ev | name | emitted by | marker (grep-able) |
|---|---|---|---|
| E1 | node_bound | node_fold | `LISTENING on 4243` |
| E2 | pin_minted | node fold banner | `CLAIM PIN` |
| E3 | pin_captured | Kotlin capture | `[ORDER] pin_captured` |
| E4 | fedid_minted | SetupViewModel | `[ORDER] fedid_minted` |
| E5 | claim_accepted | SetupViewModel | `[ORDER] claim_accepted` |
| E6 | owner_login | SetupViewModel | `[ORDER] owner_login` |
| E7 | age_recorded | SetupViewModel | `[ORDER] age_recorded` |
| E8 | announced | SetupViewModel | `[ORDER] announced` |
| E9 | claim_settled | SetupViewModel | `[ORDER] claim_settled` |
| E10 | complete_begin | SetupScreen | `[ORDER] complete_setup begin` |
| E11 | config_written | SetupScreen | `completeSetup returned: success=true` |
| E12 | runtime_restart | brain/node | restart/reload markers (session boundary) |
| E13 | node_rebound | node_fold | post-restart bind (`shutdown_node()` fast path) |
| E14 | owner_hint | CIRISApp | `nodeHasOwner`=true post-restart |
| E15 | relogin_ok | CIRISApp/harness | authenticated session post-restart |
| E16 | speak | chat | SPEAK evidence |
| E17 | trace_sealed | accord/lens | `TRACE SEALED` / trace_events row |

Every `[ORDER]` line MUST carry state: `session=<setup|owner|none>` and step context —
a 401 must be diagnosable from the single line that preceded it.

## 3. The precedence DAG (the "X before Y" — normative)

```yaml
# Machine-readable mirror consumed by order_conformance.py — keep in sync.
edges:
  - [E1, E2]    # PIN minted only once the node composed+bound
  - [E2, E3]    # can't capture an unminted PIN
  - [E3, E5]    # claim requires the captured PIN
  - [E1, E4]    # mint is a :4243 call — node must be bound
  - [E4, E5]    # claim binds the minted fed-ID as owner root
  - [E5, E6]    # owner cert exists only post-claim
  - [E5, E7]    # /v1/self/age is an owner-scope loopback call
  - [E5, E8]    # pre-claim announce hits the federation gate
  - [E5, E9]    # settle only after claim outcome known
  - [E6, E9]    # settle covers the owner-login attempt
  - [E7, E9]    # settle covers age record        (conditional: band chosen)
  - [E8, E9]    # settle covers announce          (conditional: toggle ON)
  - [E9, E10]   # ← THE GATE: no config-write/restart until ALL :4243
                #   session effects have settled. Violating this edge was
                #   the setAge-401 (and, earlier, the claim-401).
  - [E10, E11]
  - [E11, E12]
  - [E12, E13]  # shutdown_node() (0.5.122) makes this seconds, not minutes
  - [E13, E14]
  - [E14, E15]  # re-login only against a rebound, owned node
  - [E15, E16]
  - [E16, E17]
conditional: { E7: age_band_selected, E8: announce_toggle_on, E4: fedid_absent_at_claim }
invariants:
  - I1: "every :4243 bearer call (E4,E5,E7,E8) happens-before E12"   # sessions die at restart
  - I2: "E12 must not begin until E9"                                 # nothing in flight at restart
  - I3: "N5 ⇒ abort (node-fails ⇒ agent-fails; never degrade)"
  - I4: "E14 ⇒ isFirstRun=false (owned node is never first-run)"
  - I5: "E5 at most once per node lifetime"
  - I6: "UI=RECONFIGURING_HOLD is the only legal screen during B2∨N4"
```

**Why E9≺E10 subsumes the whole bug class**: I1 is the real law (sessions die at the restart
boundary). E9 is defined as "all session-consuming saga steps are terminal", so gating E10 on E9
enforces I1 by construction — including for steps added later. Anyone adding a new `:4243`
wizard call only has to put it before the settle; the gate does the rest.

### Non-happy paths (enumerated so conformance knows they're legal)
- **Minor band**: E5 skipped fail-secure → run settles unowned; wizard completes; node awaits
  adult steward. Legal terminal: `O0/O1 + B1`.
- **PIN not captured** (bounded wait expiry): settle-unclaimed; UI surfaces retry. Legal but flagged.
- **Owner login fails** (E6 error): E7 falls back to the still-valid SETUP session — legal
  *only because* E9≺E10 guarantees the restart hasn't happened yet.
- **Announce toggle OFF**: E8 absent — conditional edge, not a violation.
- **Claim rejected** (PIN expired/reclaimed): settle-with-error; COMPLETE renders retry. Legal.
- **Node-client build (no agent)**: E10–E12 absent entirely (no completeSetup on ciris-server).

## 4. Conformance validation

`order_conformance.py` extracts the event trace from logcat + runtime logs, then asserts:
1. every observed pair respects the DAG (report the **first violated edge**, both timestamps);
2. required events for the run's flags all occurred (missing E7 with a band selected = fail);
3. invariant I1 directly: no `[ORDER]` `:4243` call timestamped after the restart boundary
   without an intervening E15.

Run on **every** full_flow (success or failure) — green runs print `ORDER CONFORMANT (n events)`;
regressions surface as the violated edge even when the suite happens to pass.

## 5. Code anchors (where the gates live)

- E9 settle point: `SetupViewModel.claimLocalNodeOwnership` — `inProgress=false` moves to the END
  of the post-claim block (all paths: happy, minor-band, no-PIN, claim-rejected, exception).
- E9≺E10 gate: `SetupScreen` final-step handler — `state.first { !it.ownershipClaim.inProgress }`
  (bounded 90s) **now actually means settled** because of the above.
- I4: `CIRISApp.checkFirstRunStatus` + `nodeHasOwner()`.
- I6: `CIRISApp` `reconfiguring` hold.
- I3: `node_fold.start_node_fold` (bind window abort; `shutdown_node()` pre-serve).
