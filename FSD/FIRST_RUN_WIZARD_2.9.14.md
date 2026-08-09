# FSD — First-Run Wizard, 2.9.14

**Status:** specification, not yet implemented
**Supersedes:** the 6-declared-step flow shipped through 2.9.13
**Why now:** 2.9.13 ships a wizard that **cannot complete first-run on desktop**. It loops.

---

## 0. What is broken today (all verified against a live 2.9.13 run)

### 0.1 First-run loops forever — one divergent line

```
ours    client/desktopApp/.../Main.kt:175   ?: "http://localhost:8080"
server  client/desktopApp/.../Main.kt:176   ?: "http://127.0.0.1:4243"
```

The same file in CIRISServer says 4243. Ours says 8080. It flows into
`CIRISApp(baseUrl=…)` (`CIRISApp.kt:338`), whose own default is
`"http://127.0.0.1:4243"` (`CIRISApp.kt:322`) — so on mobile the default applies
and the bug is invisible; the desktop entry point overrides it with the Python
brain's port and every node call lands on the wrong service.

Chain, observed end to end:

1. `nodeHasOwner(baseUrl)` → `getOwnerHint()` → `GET $baseUrl/v1/auth/owner-hint`
2. On `:8080` that is **404** (`{"detail":"owner-hint is only exposed on personal-install clients"}`); on `:4243` it is **200**
3. `nodeHasOwner` → `false`, permanently
4. The post-setup hold (`CIRISApp.kt:898-920`) polls `reachable && owned` for 240 iterations
5. Its own rule fires: *"Reachable-but-unowned ⇒ a genuinely fresh node ⇒ Setup"*
6. Setup completes → `reconfiguring` set again → **loop** (68 holds observed in one run)

`isNodeReachable`/`nodeHasOwner` are called at **six** sites, all with the same
conflated `baseUrl`: `CIRISApp.kt:909, 910, 4047, 4054, 4073, 4077`.

### 0.2 Two client calls use paths that never existed

| client calls | status | correct path (`:4243`) |
|---|---|---|
| `/v1/node/health` (`CIRISApiClient.kt:5090-5108`) | 404 on both ports | **`/v1/health`** (`health.rs:97-100`) |
| `/v1/self/key-record` (`CIRISApiClient.kt:1541-1546`) | 404 on both ports | **`/v1/federation/self-key-record`** (`federation_admin.rs:883-886`) |
| `/v1/self/identity` | 405 on `:4243` | correct — POST-only, the 405 proves it is mounted |

### 0.3 The consent layer is sealed shut — no production node can consent

Two paths, each missing the other's control:

* **Non-OAuth** reaches `AnnounceDecisionCard` (on FEDERATION_IDENTITY_SETUP) but the
  trace-consent checkbox lives on `OPTIONAL_FEATURES` — **unreachable**, never a
  `nextStep()` target.
* **OAuth** jumps WELCOME → QUICK_SETUP (`SetupViewModel.kt:116-120`), which *does*
  carry the trace checkbox — but it is gated `if (state.announceOwnership)`
  (`SetupScreen.kt:4055`), and `announceOwnership` is only settable from the announce
  card on a step the OAuth path skips. The user sees *"Turn on announcing above"*
  pointing at a control that is not on the screen.

**Neither path can produce a trace consent.** `grant_trace_sharing` therefore never
fires from the wizard at all: `complete.py:667` returns early unless
`ciris_accord_metrics` is in `enabled_adapters`, and that id is added only when
`accordMetricsConsent` is true (`SetupViewModel.kt:2354-2357`). The layer is
fail-closed and correct in its degradation — and the consequence is that **no
production node can ever ship a trace.** (QA passes only because the runner sets
`CIRIS_ACCORD_METRICS_CONSENT=true` in the environment.)

### 0.4 The LLM screen's default is a dead end

Default provider is `"OpenAI"`, which requires a key, so Next is disabled with
`API key is required` and nothing signposts the way out. **Three keyless paths
already exist** and are buried in a 15-item dropdown:

* `local_inference` — "Local Inference Server"
* `local` — "Local (Ollama)"
* on-device Gemma4 E2B via llama.cpp — rendered as `menu_provider_mobile_local`,
  gated on ≥6 GB RAM + ≥3 GB free disk (`LocalInferenceCapability.desktop.kt:12-43`)

Keyless whitelist: `SetupState.kt:694-701`.

### 0.5 Dead steps

`PREFERENCES`, `OPTIONAL_FEATURES`, `QUICK_SETUP`, `NODE_AUTH`, `VERIFY_SETUP` are
never a `nextStep()` target. `enterNodeFlow()` (`SetupViewModel.kt:2091`) — the only
route to NODE_AUTH — **has no callers**. `AnnounceOwnershipCard`
(`SetupScreen.kt:3622-3667`) is defined and never called.

`isNodeFlow` has **zero effect on step order**: both branches of `nextStep()` produce
byte-identical transitions.

---

## 1. Ordering constraints — these are enforced, not preferences

Three acts. The order is dictated by the substrate.

**ACT 1 — mint federation ID.** `POST /v1/self/identity` (`:4243`, loopback-only).
Owner-gated *only after* first-run; during first-run the gate opens because
*"minting the founder's fed-ID is itself part of becoming the owner"*
(`identity.rs:1095-1107`). **It carries no reference to the local account** —
`SelfIdentityRequest` is custody backend, display name, user alias, and two PKCS#11
options (`identity.rs:988-1002`).

→ *Therefore the fed-ID may be minted before or after the local account exists.*

**ACT 2 — claim the node.** `POST /v1/setup/root` (`:4243`). Produces
`delegates_to(user → node)` with `delegation_purpose: owner_binding` and **`infra:*`
scopes only** — `agency:*` is actively refused (`ownership.rs:19-23, 280-282`).
Returns **503** without a fed-ID: *"no responsible-user identity yet"*
(`claim_remote.rs:390-393`).

→ *Therefore Act 1 strictly precedes Act 2.*

**ACT 3 — agent delegation.** `POST /v1/self/login`, the self-at-login ceremony.
**Out of scope for 2.9.14.** It has zero call sites in either repo, and would fail if
called: the Kotlin body shape does not match the Rust handler, and it is sent
unsigned against a route that 401s without `x-ciris-*` headers. No install has ever
produced an agency delegation, and nothing requires one — no delegation check exists
in the runtime, and the capability gate that would enforce it is specified but
unwired.

**Consent cannot precede the claim.** `author_consent_embedded` refuses on an
unclaimed node: *"there is no owner on whose behalf to consent"*
(`federation_delivery.rs:963-983`).

→ **Therefore the wizard COLLECTS the consent decision; COMPLETION performs it,
after the claim.** This is not a design choice.

---

## 2. Port and endpoint map

The Rust node has exactly **one** HTTP listener: `read_api_addr() = listen_addr.port() + 1`
= **4243** (`config.rs:288-294`). 4242 is the Reticulum mesh port, not HTTP.

4243 reverse-proxies **to** 8080 for `_BRAIN_PREFIXES`; `_SUBSTRATE_PREFIXES`
(`/v1/federation`, `/v1/self`, `/v1/accord`, `/v1/auth`, `/v1/config`, `/v1/health`,
`/v1/system/health`) are node-native and never proxied (`brain_adapter.py:56-90`).
**8080 never fronts 4243.**

`/v1/setup` is in **neither** prefix list and is genuinely split:

| endpoint | service | port |
|---|---|---|
| `/v1/setup/status`, `/v1/setup/complete` | Python brain | **8080** |
| `/v1/setup/root`, `/v1/setup/owned-nodes`, `/v1/setup/claim-remote`, `/v1/self/upgrade-owner` | Rust node | **4243** |

**Requirement:** the client must address these per-endpoint. A single `baseUrl`
cannot be correct. See §6.

---

## 3. The flow — three screens

Six declared steps → three. One question per screen:
*who are you* → *do you join* → *what powers it*.

### Screen 1 — **You**

Merges the former WELCOME, ACCOUNT_AND_CONFIRMATION, FEDERATION_IDENTITY_SETUP and
AGE_RANGE.

Rationale for each merge:

* **WELCOME had zero interactive elements** (169 lines, no `testable*` tags). It
  collected nothing. Its content is mostly LLM-mode explanation
  (`setup.byok_mode_title/_desc`, `setup.ciris_mode_desc`, `mobile.setup_free_badge`)
  which belongs adjacent to the AI decision, not two screens before it. Its
  "what CIRIS is" paragraph becomes this screen's header.
* **Fed-ID and account are both "you."** The fed-ID copy says *"your portable digital
  identity… how the network knows it is you."* The mint carries no account reference
  and the ordering is not enforced (§1). Asking "who are you" twice on consecutive
  screens in two vocabularies is the defect.
* **Age range is already optional with a safe default** ("declining sets the
  protective default — treated as a minor"). It is a property of the same person.

Collects:

| field | required | notes |
|---|---|---|
| Federation ID name | **yes** | the human's display name → FSD-002 `label-fingerprint` key_id |
| Username | **yes** | local account |
| Password + confirm | **yes** | ≥8 chars, must match |
| Device name | no | friendly label for this device |
| Age range | no | Under 18 / 18+; declining ⇒ protective default |

**The fed-ID mint keeps an explicit button.** It is an apex act with a hardware
ceremony (TPM / Secure Enclave / StrongBox). It must not hide behind Next: a failure
there would strand the user mid-screen with no legible cause. Give it its own card
with visual weight within the screen, not a fourth text field.

**Removed from this screen:** the "Setup Summary — AI: OpenAI" card that currently
leads ACCOUNT_AND_CONFIRMATION. It summarises a step that has not happened yet
(LLM is later), so it reports unconfigured defaults as if they were the user's
configuration. This is the single largest cause of the screen reading as an
API-key prompt.

**Removed from this screen:** the title *"Confirm Setup — Review your configuration
and complete setup."* on screen 2 of a 5-step wizard.

### Screen 2 — **Join the federation**

Primary action, on by default:

> **Consent to join the federation and start forming reputation**

Expandable detail — three toggles:

| toggle | default | what it is |
|---|---|---|
| **Announce** | ON | **Not a consent choice — the floor for service.** *"A node that does not announce gets no service access on the mesh and no agent services"* (`peer.rs:355-361`), because the accord's kill switch must be able to reach it. |
| **Send traces and be scored** | ON | `consent:replication:v1` (ship) + CC#46 `analyze` (be scored). |
| **Include rough location** | OFF | `required: false`, declining allowed with two named costs. Substrate clamps to H3 resolution ≤ 7. |

**Copy is RENDERED, not composed.** `ciris_server.consent_disclosure()` is exported
to Python precisely so the wizard renders it — *"a wizard that writes its own version
of that paragraph drifts from the substrate the moment either changes"*
(`peer.rs:186-206`). Today our only caller is a test. **The 29-locale catalogue is
already staged and unused**: `consent.grant.replication.*`, `consent.grant.analyze.*`,
`consent.decline_analyze.cost.*`, `consent.mesh_participation.action`,
`mesh.announce_requirement`, `location.*`.

**Corrections this screen must make to existing copy:**

1. The announce card currently says OFF is *"(recommended): fully private. Your node
   stays self-scoped — everything works locally…"*. That recommends the option that
   silently disables the product. State the requirement and the reason.
2. `analyze` is currently **hardcoded true** with no UI — `trace_sharing.py:145`
   (`author(peer, None, True)`), `CIRISApiClient.kt:4392` (`analyze: Boolean = true`).
   The substrate marks it `required: false` with named costs, and
   `fold_consent_surface.rs:270-274` asserts *"marking it required misrepresents a
   legitimate choice as a misconfiguration."* It becomes a visible toggle.
3. Location must lead with **what it is FOR** (regional pattern reporting, regional
   community membership), not with the restriction —
   `fold_consent_surface.rs:373-379`: *"Presented first as a restriction mechanism it
   reads as a pure cost, and an operator declines it."*

### Screen 3 — **AI**

Arrives pre-answered for almost everyone. Defaults by platform:

| platform | default | key needed |
|---|---|---|
| Android / iOS **with OAuth** | **CIRIS proxy** — the credential is the OAuth ID token | **none** |
| Desktop, `DESKTOP_CAPABLE` | **on-device Gemma4 E2B** | **none** |
| Desktop, not capable | provider choice, **keyless options listed first** | depends |
| Any, explicit opt-out | **"Run without AI"** | none |

`CIRIS_PROXY` is gated on `isGoogleAuth` (`SetupScreen.kt:1339`), which desktop
first-run never sets (`CIRISApp.kt:1301`). That is why the proxy card is invisible on
desktop — not a bug, a consequence. **Do not "fix" it by showing the card on desktop;
there is no OAuth token to use as the credential.**

**"Run without AI" writes `CIRIS_SERVICES_DISABLED=true`.** This is the existing,
shipped mechanism — the same state `POST /v1/system/llm/ciris-services/disable`
produces (`llm_routes.py:973-1000`). It is what keeps `llm_service` optional at
`service_initializer.py:1754-1760`.

> **CRITICAL — do not default to this.** Defaulting AI off would disable a working
> agent on capable hardware and would turn off CIRIS services on the platforms where
> they are the entire point. It is an option, never a default.

> **CRITICAL — the step cannot simply be deleted.** With it gone, untouched defaults
> (`provider="OpenAI"`, `key=""`) ship `OPENAI_API_KEY=""`; and on the *next* boot
> `is_first_run()` is false so `verify_core_services` makes `llm_service` critical
> (`service_initializer.py:1758-1760`) → **initialization aborts, it does not
> degrade.** Any path that ends without a usable provider MUST write
> `CIRIS_SERVICES_DISABLED=true`.

**Just-in-time hint.** When a user opens chat with no provider, the processor was
never constructed (`ciris_runtime.py:1247-1257`), so interact degrades to HTTP 200
with `agent.still_processing` — silent. Surface a hint pointing at the existing
repair, `POST /v1/system/llm/providers`, which hot-builds the processor with no
restart (`llm_routes.py:936-950`). Health already reports the condition:
`code="no_llm_provider"`, `action_url="/settings/llm"` (`health.py:81-85`).

---

## 4. Completion sequence

Strictly ordered. Each step's precondition is the previous step's product.

1. **Mint fed-ID** (screen 1, explicit button) — `POST /v1/self/identity` → `:4243`
2. **Create local account** — part of `POST /v1/setup/complete` → `:8080`
3. **Claim the node** — `POST /v1/setup/root` → `:4243`. *Requires 1.*
4. **Author consent** — replays screen 2's decision. *Requires 3.*
   * announce → `POST /v1/federation/announce` (takes effect **next boot**; the
     attestation is built once at transport construction, `claim_remote.rs:975-980`)
   * send + score → `grant_trace_sharing(...)` with `analyze` from the toggle
   * location → per the disclosure's envelope-field contract
5. **Write `.env`** — including `CIRIS_SERVICES_DISABLED=true` if "run without AI"

A failure at any step must name which act failed and what it blocks. Failing at 4
must not roll back 3.

---

## 5. Post-setup routing — three states, not two

The loop exists because the router knows only *fresh* vs *claimed*. There is a third,
named state.

| state | signals | route |
|---|---|---|
| **fresh** | no ROOT WaCert, no owner-binding | Setup |
| **legacy-owned** | WaCert present, **owner-binding absent** | `POST /v1/self/upgrade-owner` |
| **claimed** | owner-binding present | Login |

**`nodeHasOwner` must consult `/v1/setup/owned-nodes`, not `/v1/auth/owner-hint`.**

* `owner-hint` (`session.rs:678-705`) reads the **WaCert auth store**. It is a
  GDPR-masked login-screen "welcome back" hint. **It gates nothing.**
* `owned-nodes` (`bootstrap.rs:1043-1071`) reads the **CEG graph** via
  `admission::owner_of`, and is the same predicate `require_owner_bound` consults at
  every owner-gated operation (config writes, peering, commons, mesh config, peers).

The legacy-owned state is real and named: *"An existing node may be owned the legacy
way — a ROOT WA with a password/OAuth login but NO fed-ID delegates_to
owner-binding"* (`claim_remote.rs:760-767`). `POST /v1/self/upgrade-owner` exists
solely to repair it.

Observed on a live node: `owner-hint` returned `first_name: "qaadmin"` while
`owned-nodes` returned `{"owner":null,"nodes":[]}`, `owner_binding` appeared **0
times** in the log, `setup/root` was 409-closed, and no claim PIN was minted. A router
that trusts `owner-hint` sends that node to Setup, where `setup/root` 409s — **the
loop**.

**Root cause of that state is UNVERIFIED.** Python's `is_first_run` asks *does `.env`
exist*; Rust's asks *does a ROOT WaCert exist* (`bootstrap.rs:286-290`). They can
disagree. Whether a genuinely fresh home claims successfully **has not been tested**
— see §8.

---

## 6. Client base-URL model

Replace the single `baseUrl` with two, so the two services cannot be confused:

```kotlin
CIRISApp(
    apiBaseUrl: String  = "http://127.0.0.1:8080",   // Python brain
    nodeBaseUrl: String = CIRISApiClient.LOCAL_NODE_URL,  // "http://127.0.0.1:4243"
)
```

* `client/desktopApp/.../Main.kt:175` must stop passing 8080 as the node URL.
* All six `isNodeReachable`/`nodeHasOwner` call sites take `nodeBaseUrl`.
* `getNodeHealth()`, `getSelfKeyRecord()`, `getOwnerHint()`, `selfLogin()` take
  `nodeBaseUrl`.
* `/v1/setup/status` and `/v1/setup/complete` take `apiBaseUrl`.
* `/v1/setup/root`, `/v1/setup/owned-nodes`, `/v1/setup/claim-remote`,
  `/v1/self/upgrade-owner` take `nodeBaseUrl`.

`LOCAL_NODE_URL` already exists (`CIRISApiClient.kt:369`) and the mint/claim/
owned-nodes call sites already pass it explicitly. This change makes the remainder
consistent rather than introducing a new concept.

---

## 7. Deletions

Remove, do not deprecate — all are unreachable today:

* `SetupStep.PREFERENCES`, `.OPTIONAL_FEATURES`, `.QUICK_SETUP`, `.NODE_AUTH`,
  `.VERIFY_SETUP` and their composables
* `enterNodeFlow()` (no callers) and the `isNodeFlow` field (zero effect on step order)
* `AnnounceOwnershipCard` (`SetupScreen.kt:3622-3667`, defined and never called)
* The duplicated `nextStep()`/`previousStep()` branches — one `when`, not two

**Preserve:** the location picker and the accord/location checkboxes currently on the
dead steps carry working logic. Move them to screen 2 rather than deleting them.

---

## 8. Acceptance

Functional:

1. **A fresh home completes first-run and lands on the agent, not Setup.**
2. **A legacy-owned home routes to `upgrade-owner`, not Setup**, and completes.
3. A desktop install with no key and no OAuth completes via on-device inference.
4. "Run without AI" completes, and the node **boots again** (the regression guard for
   §3's abort).
5. Consent toggles produce the artifacts: `consent:community_trust:v1`,
   `consent:replication:v1`, and `analyze` matching the toggle. Declining produces
   none and the node still boots.
6. No client call 404s during first-run.

Tests:

* `nodeHasOwner` consults `owned-nodes`; a test asserts `owner-hint` is not used for
  any gating decision.
* The three-state router: one test per state, including that legacy-owned does **not**
  route to Setup.
* Base-URL split: a test asserts no node endpoint is reachable via `apiBaseUrl`.
* `analyze` is passed from the toggle, not hardcoded — assert both values reach
  `author_federation_consent`.
* An unreachable-step guard: assert every `SetupStep` is a `nextStep()` target, so a
  future dead step fails CI rather than shipping.

**Untested and must be established before implementation is called complete:**

* Whether a genuinely fresh home claims successfully. Only the dirty-home failure has
  been observed. If fresh also fails, the claim itself is broken and this FSD's §5 is
  a workaround rather than a fix.
* Whether `net.announce_ownership` is actually `true` on the boot *after* an announce.
  The deferral logic was read; a second boot was not observed.
* What lens-core actually receives for location. `services.py:484-504` passes raw
  `user_latitude`/`user_longitude`; a comment claims lens-core fuzzes to ~11 km; the
  substrate calls a producer shipping raw coordinates *"non-conformant"*. **Nobody has
  read lens-core.** Do not change the location path on the strength of the comment.
