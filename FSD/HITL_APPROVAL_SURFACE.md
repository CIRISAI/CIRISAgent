# HITL Approval Surface (client)

**Issue:** #938 (task-scoped authorization / budget envelope) · #939 (`send_money` is unbounded on every fiat rail)
**Scope:** `client/` only — Kotlin Multiplatform (Android, iOS, desktop, wasmJs). No backend Python is changed by this work.
**Companion:** `FSD/BUDGET_ENVELOPE.md` owns the wire contract. This document owns the human-facing half.

---

## Why this exists

CIRIS is moving to a fail-closed authorization model: consequential actions — spend in
particular — are denied unless a human has explicitly approved them. That is the right
default, and it has a failure mode that is easy to ship by accident:

> A design whose approval path has no UI is not "secure by default". It is a silent
> denial-of-service on the agent, and the operator never learns why the agent stopped.

From where the operator sits, an agent blocked on an un-surfaced approval and an agent
that is simply broken look identical. This surface is the difference. It exists so that
every gate which can block the agent has a place where a human can see the block, understand
what is being asked, and decide.

The requirement, verbatim: *"any HITL gate/approval needs an active UI surface, so we need a
card for pending tasks and we need new pending tasks to notify the user and request any
approvals like budget."*

---

## What the surface guarantees

1. **Every pending human decision appears in one list.** Two independent backend pipelines
   produce approvals; the operator should not have to know which one is which, or check two
   screens.
2. **A blocked agent is visible from anywhere in the app.** A count badge on the Wise
   Authority nav entry, rolled up to its group header so a collapsed group still shows it.
3. **A newly-arrived approval raises a platform notification** — once, on Android, iOS and
   desktop.
4. **A budget request is rendered as a budget request**, with the amount, currency, purpose
   and the agent's stated intent — not as an opaque "approve/reject" prompt.
5. **A human can approve above the agent's request** — the agent may have asked for too
   little — but never silently: an over-grant requires an explicit confirmation naming the
   ratio, and is marked as an over-grant in the record.
6. **Approving money and starting work are separate decisions**, and both are visible.
7. **Nothing in this surface can crash or block on a platform capability that is missing.**
   Notifications, budget issuance and the tickets API each degrade to a clear, non-fatal
   state.

---

## The two approval sources

| | Deferral | Ticket proposal |
|---|---|---|
| What it is | Wisdom-Based Deferral — the agent asked a human a question mid-reasoning | A ticket the agent proposed and may not itself start |
| Read | `GET /v1/wa/deferrals` | `GET /v1/tickets?status_filter=blocked`, filtered to those with `metadata.__proposal__`; `GET /v1/tickets/{id}/budget` on dialog open |
| Decide | `POST /v1/wa/deferrals/{id}/resolve` | `POST /v1/tickets/{id}/budget/grant` and/or `PATCH /v1/tickets/{id}` |
| Carries money | No | Optionally, via `metadata.__requested_budget__` |

Both are normalized to `PendingApproval` (`approvals/ApprovalModels.kt`) with an
`ApprovalKind` discriminator. The unified list is `WiseAuthorityViewModel.approvals`.

**Budget never rides the deferral path.** `resolve_deferral` completes the originating task
and creates a new one, so it cannot carry a grant that must outlive a single task; and its
`signature` field is a formatted string that is never verified, which makes it unfit to carry
money authorization. This was confirmed with the backend author rather than assumed.

---

## How the client learns about new approvals

**Polling. There is no push.** The API exposes WebSocket streams (`/v1/stream/messages`,
`/telemetry`, `/reasoning`, `/logs`, `/all` — see `routes/README_WEBSOCKET.md`), but neither
deferrals nor tickets are broadcast on any of them. Nothing about an approval arrives
unsolicited.

Two loops, at different cadences, for different reasons:

| Loop | Interval | Lifetime | Purpose |
|---|---|---|---|
| `startApprovalWatch()` | **30 s** | whole authenticated session | badge + notifications; started from `CIRISApp` on token acquisition, stopped on logout |
| `startPolling()` | **10 s** | while the approval screen is visible | keeps the list live under a decision |

The session-wide watch is the load-bearing one. Before this change, `WiseAuthorityViewModel`
polled **only while its own screen was open** — so the only way to discover a blocked agent
was to already suspect it and navigate there. `InteractViewModel` separately polls
`getWAStatus()` every 30 s for a count-only banner on the chat screen, which remains.

**Consequence to be honest about:** an approval that arrives while the app is not running is
not notified. There is no background service and no push channel. The operator sees it on
next launch.

---

## Notification contract

Implemented in `approvals/ApprovalNotifier.kt`. It adds **no new `expect`/`actual`** — the
four existing platform implementations of `ScheduledTaskNotifications` are reused through
`showImmediateNotification`. Those implementations already existed but were wired only to
scheduled-task *time* triggers (a calendar/reminder shape); nothing called them for "something
arrived that needs you". This class is that caller.

**Dedupe key:** `PendingApproval.id` — the deferral id or the ticket id.

**Where "already notified" persists:** `SecureStorageNotifiedApprovalStore`, key
`hitl_notified_approvals`, newline-joined ids, via the app's existing `SecureStorage`
abstraction (EncryptedSharedPreferences on Android, Keychain on iOS, keyring on desktop). The
`WiseAuthorityViewModel(apiClient, secureStorage)` constructor wires it; a fallback
constructor uses an in-memory store, in which case a restart may re-announce still-pending
approvals once.

| Rule | Behaviour |
|---|---|
| **At most once per approval** | An id that has been notified is never notified again, regardless of how many poll cycles observe it. A 30 s poll against 3 pending approvals would otherwise be 360 notifications an hour, and the operator would turn notifications off — strictly worse than not shipping this. |
| **At-most-once, not at-least-once** | If the platform sink throws, the id is still marked notified. A permanently failing channel must not accumulate an unbounded retry set. The badge and the card remain the surface of record. |
| **Permission denial does not consume the key** | With permission absent, nothing is shown and nothing is marked. Approvals that arrived during denial each fire exactly once if permission is later granted. |
| **This class never prompts** | Permission requests stay with the app's existing flow. The notifier only *checks*. |
| **Bursts collapse** | More than 3 new approvals in one observation produce a single summary notification. First launch against a backlog is the common case. |
| **Bounded memory** | The remembered-id set is insertion-ordered and capped at 300; oldest evicted first. |
| **Failure is never fatal** | Every platform call is wrapped. wasmJs logs to console; desktop without a system tray falls back to a log line. A missing notification cannot propagate into the poll loop or the screen. |

---

## Budget approval flow

### Reading the request

A ticket is an unapproved proposal iff `status == "blocked"` **and** `metadata.__proposal__`
is present. `blocked` is used because the persist ticket-status enum is closed
(`pending|assigned|in_progress|blocked|deferred|completed|cancelled|failed`) and has no
`proposed` variant.

`metadata.__requested_budget__` is **optional** — a proposal may ask for no money, and that
is a normal case, not an error. When present it carries
`{requested_amount, requested_currency, purpose, justification}`, all decimal-as-string.

`RequestedBudget` and `GrantedBudget` are **two distinct Kotlin types with disjoint fields**,
mirroring the backend's two `extra="forbid"` Pydantic models. This is deliberate and
load-bearing: one type with a nullable "granted" flag is exactly the shape in which a request
gets rendered as an authorization by a single missing null-check.

### Issuing the grant

`POST /v1/tickets/{ticket_id}/budget/grant`, **AUTHORITY role required** (level 3 — ADMIN at
level 2 is not sufficient).

```
request  {"amount": "25.00", "currency": "USDC", "purpose": "...",
          "expires_in_hours": 24, "wa_id": null}
response {"ticket_id","granted_amount","granted_currency","purpose","expires_at",
          "granted_by_wa_id","granted_by_user_id","granted_at","signed"}
```

`signed` reports whether the grant carries a verifiable Ed25519 signature — false in
deployments with no WA signing key. It is surfaced to the operator rather than hidden,
because an unsigned grant is a weaker artifact and the person issuing it should know.

Error surfacing: **403** wrong role, **404** ticket not found *or* endpoint absent (see
below), **422** `NestingViolation` — the grant exceeds the deployment's trust-envelope
ceiling. Each maps to a distinct message; none fails silently.

### Reading the budget state

`GET /v1/tickets/{ticket_id}/budget` (OBSERVER) returns request, grant, spend ledger and
`trust_headroom` in one read. The dialog fetches it on open. It is an *enhancement* to the
dialog, never a precondition: the dialog renders immediately from data already in the list
and the headroom row appears a moment later, or not at all.

`trust_headroom.amount` is `min(max_transaction, daily_remaining)` and is **the same number
the spend gate applies** — the server resolves it through the wallet tool service's own
`_resolve_trust_envelope`, not a re-derivation, so what an operator is shown cannot drift
from what is enforced when money moves. Both bounds are carried so the UI can say *which one
is binding* ("40 remaining today, 100 per-transaction ceiling") rather than an unexplained
number. `trust_headroom` is null when no wallet adapter is loaded; the row is then omitted.

### The two amount constraints, and their different standing

`BudgetApprovalSeam.validateGrant` checks two things that are easy to conflate:

**`granted > requested` is permitted — with friction.** This was an explicit user ruling:

> *"yes an AUTHORITY can approve above what the agent requested, of course, the agent may
> have requested too little."*

**`granted ≤ requested` is therefore not a bound of any kind** — not in the server, not in
this client. The agent's request is **information for the human, not a constraint on them**.
An earlier revision of this surface refused over-granting in the UI; that was wrong twice
over. It was stricter than the system without saying so, and a UI-only restriction the server
does not share simply teaches an operator who genuinely needs to over-grant to reach for
`curl` — at which point the grant happens outside every rendering, log line and confirmation
this dialog provides. The alternative, making the agent re-propose, also burns its
3-proposals-per-task runaway budget for no safety gain.

What remains is friction, aimed at the hazard that is actually real: **a mis-typed extra
zero, not a policy disagreement.** So the confirmation names the ratio rather than asking
"are you sure?" — 250 next to 25 is easy to scroll past; "10×" is not.

| Ratio | Rendering | Why |
|---|---|---|
| ≤ 1.05× | "slightly above the 25.00 requested" — **no figure** | A rounding-scale overage dressed in alarm styling trains people to click past the warning that matters. |
| 1.05× – 2× | "**20%** above the 25.00 requested" | "1.2× the requested" reads oddly; a percentage is the natural register at this scale. |
| ≥ 2× | "**10×** the 25.00 requested" | The band a mis-typed zero always lands in, and the one that must be unmissable. |

All three still require the confirmation — only the wording softens. The affordance is a
checkbox (`chk_over_grant_confirm`) that gates the approve buttons; it **resets whenever the
amount changes**, so a confirmation given for one figure can never carry to another. The
prompt stays on screen after ticking rather than vanishing at the moment of decision.

Fail-closed by construction: `validateGrant` returns `OVER_GRANT_UNCONFIRMED` until
`overGrantConfirmed = true` is passed, so a caller that never passes it cannot submit an
over-grant at all.

#### The audit marking is server-derived, and that is the point

An over-grant is distinguishable in the record via two fields on `GrantedBudget`:

```
exceeds_request: bool                      // granted > requested at issuance
requested_amount_at_grant: string | null    // the snapshot; null = ticket requested nothing
```

**The client does not send these.** An earlier draft did, and that was wrong for the same
reason the flat refusal was: a client-asserted audit flag is worthless precisely against the
person it needs to work against. The operator most motivated to make an over-grant look
ordinary is the one calling the endpoint directly — and they would simply omit the flag. It
would be present exactly when it was not needed.

The server derives both in `issue_grant` by comparing against the ticket's
`__requested_budget__` at issuance, and they sit **inside the canonical signed payload**, so
the marking cannot be stripped or forged without invalidating the signature. That is a
property no client-side flag could have. `GrantBudgetRequest` also now declares
`extra="forbid"`, so `buildGrantBody` must send only declared fields — an unknown field is a
loud 422 rather than a silent default.

The client reads them from the grant response and from `GET /{id}/budget`, and renders
"Approved above the 25.00 the agent asked for" on an issued over-grant. Two consequences the
rendering respects:

- **`requested_amount_at_grant` is null when the ticket requested nothing at all** — a
  human-opened ticket, or a proposal asking for work but not money. `exceeds_request` is false
  there; there is no ratio to name and it is not an over-grant. A naive comparison would have
  made those tickets ungrantable.
- **Historical display uses the grant's snapshot, never the ticket's current request.** The
  grant is the record; the ticket's requested budget could in principle differ later.

**`granted ≤ trust ceiling` — the real bound, owned by the server.** Checked client-side only
so the operator learns at the point of decision rather than through a rejected round-trip. It
is enforced at issuance (422 `NestingViolation`) and again at every spend. Headroom is ignored
when its currency differs from the requested currency — a USD ceiling says nothing about a
USDC request, and comparing them would block a legitimate grant on a meaningless mismatch.

**The over-grant confirmation does not override it.** Acknowledging that you meant to exceed
the *agent's request* says nothing about the *deployment's envelope*; they are unrelated
questions. The ceiling check therefore runs **before** the confirmation gate in
`validateGrant`, so it wins, and this is locked by test
(`confirmedOverGrantStillCannotExceedTheTrustEnvelope`).

> **The headroom currency is an assumption, not a declared fact.** `SpendingLimits.max_transaction`
> and `daily_limit` are bare `Decimal`s with **no declared currency**, while `SpendingTracker`
> keys its accumulator *by* currency. `max_transaction=100` therefore means "100 of whatever
> is being sent" — 100 USDC and 100 KES both pass and are ~1000× apart in value. The server
> stamps the ticket's own currency onto the headroom, which is the best available answer, but
> **a multi-currency deployment does not have one meaningful ceiling.** Filed backend-side
> (the fix adds a currency, or a per-currency map, to `SpendingLimits` — operator-visible
> config, belongs with #939's wallet work). Consequence for this client: display the headroom,
> but **build nothing that reasons across currencies on top of it.** The currency guard above
> cannot currently fire for that reason; it is retained because it is cheap and fails safe.

Amounts are compared as **fixed-point integers at 8 decimal places**, never as `Double` —
money in a binary float is how you approve 25.000000000000004. Anything that is not a plain
non-negative decimal (signs, exponents, thousands separators, currency symbols) is rejected
rather than coerced.

### Re-granting, and why `granted_amount` must never be shown alone

A second grant on a ticket raises the **ceiling**. It does not top the balance up, and the
spend ledger survives it. Verified backend-side and locked by `TestRegrantSemantics`:

```
grant 25 → spend 25 → grant 40   ⇒  15 remaining   (not 40)
grant 50 → spend 40 → grant 10   ⇒   0 remaining   (clamped, never negative)
```

So **`granted_amount` on its own overstates availability after any spend** — by exactly the
spent amount, on a money surface, for precisely the tickets that have already been partly
spent. The UI therefore renders **remaining** (`granted − spent`, clamped at zero) as the
prominent figure, with granted and spent demoted to context beneath it. The list chip follows
the same rule. `BudgetApprovalSeam.remainingAmount` is the only place that arithmetic
happens, and it returns null on unparseable input so the UI renders nothing rather than a
fabricated number.

This is the same reasoning as the headroom guard: a figure that can drift from what the
system will actually permit is worse than no figure.

Because a re-grant is a ceiling raise, **re-approval on an existing ticket already works** —
an operator who under-granted can raise it without the agent re-proposing.

**There is no explicit revoke endpoint.** Revocation today is a *side effect* of granting
below the amount already spent, which clamps remaining to zero. That is operator folklore
rather than an API: it is not named as a revoke anywhere, it cannot be distinguished in the
record from an ordinary small grant, and nothing in the client surfaces it as a revoke
affordance. Whoever needs real revocation should expect to add a verb, not document this
trick.

### Grant ≠ start

Granting a budget does **not** start the work — the ticket stays `blocked` until a human also
`PATCH`es it to `pending`. The dialog exposes both as separate buttons plus one clearly
labelled combined action, because approving money and starting work are genuinely different
decisions.

"Not now" writes a note and leaves the ticket blocked: nothing is issued, nothing starts, the
agent stays fail-closed. That is the correct default when a human has not decided.

### The agent cannot approve itself

The agent-side `update_ticket` tool refuses to move a ticket out of proposal state (except to
`cancelled`, i.e. withdrawing it) and refuses to write any of the four reserved metadata keys.
The human is the only issuer. Nothing in this client relaxes that.

---

## The seam to the backend contract

**One file:** `client/shared/src/commonMain/kotlin/ai/ciris/mobile/shared/approvals/BudgetApprovalSeam.kt`.

It is the only place that knows reserved metadata key names, the grant endpoint path, the
request and response body shapes, and the HTTP-status→error mapping. If the contract moves,
this is the file that changes. The transport lives in `CIRISApiClient.grantTicketBudget`,
which issues a raw Ktor call because the endpoint post-dates the current OpenAPI snapshot;
it contains no policy.

### Capability check and degradation

There is no probe endpoint, so `BudgetCapability` is discovered lazily:

- `UNKNOWN` — initial state; the dialog behaves normally.
- `UNAVAILABLE` — set when the grant endpoint answers 404/405, i.e. an older server that
  produces requests but has no issuance route. The dialog then says so plainly and disables
  the approve controls, rather than offering a button that cannot work. A silent failure here
  would read to the operator exactly like the agent being stuck, which is the confusion this
  whole surface exists to prevent.
- `AVAILABLE` — set on the first successful grant.

404 is genuinely ambiguous — "no such ticket" or "no such endpoint" — and only one of them
means the feature is missing. The server disambiguates with a structured detail:

```json
{"detail": {"error_code": "TICKET_NOT_FOUND", "message": "Ticket PROP-X not found — …"}}
```

The client pins on `error_code` (`TICKET_NOT_FOUND_ERROR_CODE` in `routes/tickets.py`), never
on prose. A substring match on the message is retained purely as a fallback for servers
predating the structured detail, and is deliberately checked last. A bare
`{"detail": "Not Found"}` carries no `error_code` and correctly reads as the endpoint being
absent, which is what keeps the capability check working against older servers. An
*unrecognized* `error_code` maps to `UNKNOWN` rather than being coerced into
"endpoint missing" — coercing it would flip the capability check off on an unrelated error.

A deployment with no tickets API at all returns an empty proposal list rather than throwing,
so deferrals still render.

---

## What this does NOT do

- **No push, no background delivery.** Approvals arriving while the app is closed are not
  notified. There is no server-side push channel for deferrals or tickets, and no background
  service polls for them. Adding deferral/ticket events to the existing WebSocket stream
  would remove the 30 s floor and the app-must-be-running limitation; that is a backend ask,
  not something this surface can fix.
- **It does not show headroom when no wallet adapter is loaded.** `trust_headroom` is null in
  that case and the row is omitted. That is correct behaviour, not a gap — there is no
  envelope to report.
- **It does not enforce anything security-relevant.** Client-side validation is a usability
  affordance. The AUTHORITY role, the trust-envelope ceiling and spend against the grant are
  all enforced server-side; a modified client changes nothing about what the agent is
  permitted to do. The one place this client is *stricter* than the server — refusing
  `granted > requested` — is a UI promise, not a boundary.
- **It does not cover unapproved spend paths.** #939 documents that `_execute_send_money`
  performs no limit check on any fiat rail. This surface issues a budget; whether that budget
  is *consulted* before `provider.send` is the backend's enforcement point, not the client's.
- **It does not surface budget burn-down in detail.** `metadata.__budget_spent__` is parsed
  (total + record count) and folded into the remaining figure plus one "spent" line. The
  per-record ledger is not rendered.
- **It does not offer a revoke affordance.** There is no revoke endpoint; granting below the
  spent amount clamps remaining to zero as a side effect, and this client neither surfaces
  nor names that as revocation.
- **It does not assert the over-grant marking itself.** That is deliberate — see below; the
  server derives it. The client only reads and displays it.
- **It does not localize into all 29 languages.** English strings are added to the six
  `en.json` copies; other locales fall back to English via the existing localizer, which
  returns the key when a translation is absent.
- **No new platform code.** wasmJs notifications remain a console log — that is the existing
  `ScheduledTaskNotifications` implementation, unchanged. Desktop uses the system tray when
  one is available.
- **It does not gate the Interact-screen deferral banner.** That pre-existing count banner
  (driven by `InteractViewModel.pendingDeferrals`) is untouched and still works.

---

## Files

| Path | Role |
|---|---|
| `approvals/ApprovalModels.kt` | `PendingApproval`, `RequestedBudget`/`GrantedBudget` (disjoint), `BudgetCapability`, `BudgetGrantError` |
| `approvals/BudgetApprovalSeam.kt` | **the seam** — wire keys, paths, bodies, status mapping, fixed-point amounts, ≤ constraint |
| `approvals/ApprovalNotifier.kt` | dedupe + persistence + platform sink; no new `expect`/`actual` |
| `approvals/ApprovalsApi.kt` | narrow API interface + `CIRISApiClient` adapter + projections |
| `ui/components/PendingApprovalsCard.kt` | the "blocked waiting on you" card, `CountPill`, `ProposalApprovalDialog` |
| `ui/screens/WiseAuthorityScreen.kt` | card at top of screen; routes card taps to the right dialog |
| `ui/nav/EpistemicSidebar.kt` | `badges: Map<surfaceId, Int>` → count pill on row and group header |
| `viewmodels/WiseAuthorityViewModel.kt` | unified list, session watch, grant/promote/reject/defer |
| `api/CIRISApiClient.kt` | `TicketData.metadata`, `updateTicketStatus`, `grantTicketBudget` |

## Test tags (desktop/iOS `/tree`, `/click`, `/input` harness)

`card_pending_approvals`, `pill_approval_count`, `item_approval_{id8}`, `chip_budget_{id8}`,
`nav_badge_wise_authority`, `nav_badge_group_{groupId}`, `dialog_budget_approval`,
`txt_budget_requested_amount`, `txt_budget_validation_error`, `txt_budget_unsupported`,
`row_budget_headroom`, `row_budget_issued`, `txt_budget_remaining`, `txt_budget_unsigned`,
`row_over_grant`, `chk_over_grant_confirm`, `txt_over_grant_ratio`,
`txt_budget_exceeded_request`, `input_budget_amount`, `input_budget_expiry`,
`input_budget_reason`, `btn_budget_approve`, `btn_budget_approve_start`, `btn_budget_reject`,
`btn_budget_defer`, `btn_budget_cancel`.

## Tests

`client/shared/src/commonTest/.../approvals/BudgetApprovalSeamTest.kt` (53),
`.../approvals/ApprovalNotifierTest.kt` (15),
`.../viewmodels/WiseAuthorityViewModelTest.kt` (31).

```
cd client && ./gradlew :shared:compileCommonMainKotlinMetadata   # commonMain type-checks for all targets
cd client && ./gradlew :shared:desktopTest                       # 321 tests, 0 failures
```
