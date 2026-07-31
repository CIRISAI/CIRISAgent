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
5. **A human can approve at or below the requested amount, never above.** This is a UI
   guarantee — see the asymmetry note below; the server permits over-granting and this
   client does not.
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

**`granted ≤ requested` — a UI policy, and this client is stricter than the server.** The
server does **not** enforce it: an AUTHORITY user is permitted to grant more than the agent
asked for, e.g. when the agent lowballed. This client refuses it anyway, because "approve at
or below what was asked" is the promise the approval dialog makes to the person using it, and
a dialog that quietly allows more than the request on screen can surprise its operator. It is
a product decision, not a security boundary, and a modified client bypassing it is not a
vulnerability.

**`granted ≤ trust ceiling` — the real bound, owned by the server.** Checked client-side only
so the operator learns at the point of decision rather than through a rejected round-trip. It
is enforced at issuance (422 `NestingViolation`) and again at every spend. Headroom is ignored
when its currency differs from the requested currency — a USD ceiling says nothing about a
USDC request, and comparing them would block a legitimate grant on a meaningless mismatch.

Amounts are compared as **fixed-point integers at 8 decimal places**, never as `Double` —
money in a binary float is how you approve 25.000000000000004. Anything that is not a plain
non-negative decimal (signs, exponents, thousands separators, currency symbols) is rejected
rather than coerced.

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
  (total + record count) and shown as one line. The per-record ledger is not rendered.
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
`row_budget_headroom`, `input_budget_amount`, `input_budget_expiry`, `input_budget_reason`,
`btn_budget_approve`, `btn_budget_approve_start`, `btn_budget_reject`, `btn_budget_defer`,
`btn_budget_cancel`.

## Tests

`client/shared/src/commonTest/.../approvals/BudgetApprovalSeamTest.kt` (33),
`.../approvals/ApprovalNotifierTest.kt` (15),
`.../viewmodels/WiseAuthorityViewModelTest.kt` (23).

```
cd client && ./gradlew :shared:compileCommonMainKotlinMetadata   # commonMain type-checks for all targets
cd client && ./gradlew :shared:desktopTest                       # 293 tests, 0 failures
```
