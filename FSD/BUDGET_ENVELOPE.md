# Budget Envelope — human-approved spend, nested in the trust envelope

**Status:** implemented on `feat/938-create-ticket`
**Issues:** #938 (task envelope), #905 (tool gate), #939 (wallet spend path)

---

## The problem

Privilege in this agent is identity-scoped, not task-scoped. Every tool enabled in
a deployment is granted to every task, and that is *correct* for most tools —
task type is unknowable at creation, so echo's kick/ban must always be available
(see the correction comment on #938).

**Spend is the exception.** Money is the one capability where the deployment-wide
default grant is indefensible, because unlike a ban, a payment cannot be undone
and its magnitude is unbounded by anything the reasoning loop respects.

Before this change, the wallet path was:

```
_execute_send_money  →  Decimal(amount)  →  _get_provider(...)  →  provider.send(...)
```

with **no limit check of any kind** in the tool service (#939). The only limits
that existed (`WalletValidator` / `SpendingTracker`) were imported by exactly one
provider — `x402_provider.py:57` — so six fiat rails holding live merchant API
keys had no agent-side spend limit at all. `WalletAdapterConfig.spending_limits`
was declared, defaulted, and had **zero readers**: configuration that reads as a
control and enforces nothing, the same shape as `ToolHandlerData.sandbox_mode`,
on the money path.

## The model: propose → approve → spend

```
  ┌─ reasoning loop ─────────────────┐      ┌─ outside the loop ──────────┐
  │                                  │      │                             │
  │  create_ticket(                  │      │  POST /v1/tickets/{id}/     │
  │    goal_description=...,         │      │       budget/grant          │
  │    requested_budget_amount=25)   │      │  require_authority          │
  │           │                      │      │           │                 │
  │           ▼                      │      │           ▼                 │
  │  ticket status = blocked         │      │  __granted_budget__         │
  │  __proposal__                    │      │  (Ed25519-signed,           │
  │  __requested_budget__  ──────────┼──────┼──▶ bound to ticket_id)      │
  │   (a REQUEST — no authority)     │      │   (an AUTHORIZATION)        │
  └──────────────────────────────────┘      └─────────────────────────────┘
                                                        │
                                                        ▼
                              send_money → authorize_spend →
                              amount ≤ min(granted_remaining, trust_remaining)
```

The agent **may propose an envelope but never mint or widen one.** Approval is
the issuance event, and it happens outside the reasoning loop.

---

## Object model (as found, not invented)

No fourth concept was introduced. The three that exist:

| Object | Where | What it is |
|---|---|---|
| **Ticket** | `logic/persistence/models/tickets.py`, persist `ticket_*` | The durable, human-visible work item. SOP + stages + status + metadata. *Not* a service. Has a full CRUD API at `/v1/tickets`. |
| **Task** | `schemas/runtime/models.py:106` | The runtime unit the processor executes. Created **from** tickets by `WorkProcessor._create_seed_task_for_ticket`. |
| **ScheduledTask** | `schemas/runtime/extended.py:122` | A *time-triggered* goal that generates Thoughts. A different axis (when), not (what/whether). Not used here. |

`create_ticket` already existed **in persistence** (`tickets.py:176`) and on the
**human API** (`POST /v1/tickets`). What did not exist was the agent-facing tool.
That is the gap this closes: the agent could read, update and defer tickets but
could not open one.

The budget lives on the **Ticket**, because the Ticket is the durable object that
outlives any single Task, is already human-visible, and already gates task
creation.

### Why not `Task.signed_by` / `signature` / `signed_at`?

Those fields exist and are populated in three places, but **`verify_task_signature`
has zero production callers** — signatures are written and never checked. The
canonical payload also excludes `signed_by`, `signed_at`, `updated_at` and
`agent_occurrence_id`. Reusing a write-only mechanism for money would have been
theater. The grant carries its own signature over its own canonical payload, and
that signature **is** verified, on every spend.

---

## Proposal state

`create_ticket` writes the ticket with **`status = "blocked"`**.

The ticket status vocabulary is a **closed enum in the persist substrate**:
`pending | assigned | in_progress | blocked | deferred | completed | cancelled |
failed`. `ticket_upsert` rejects anything else with
`Ticket decode: unknown variant`. A dedicated `proposed` variant would require a
CIRISPersist change (noted as an upstream ask below).

`blocked` is the honest fit — a proposal is blocked on a human decision it cannot
make itself — and it is load-bearing:

- `_process_pending_tickets` lists `status="pending"` only
- `_process_active_tickets` lists `assigned` and `in_progress` only
- `_should_skip_ticket_by_status` already contains `blocked`

so **a proposal never becomes an executing task on its own**, and that holds
without depending on the persist status filter being honored (the same substrate
silently ignores `correlation_id` in `ticket_list`).

A proposal is distinguished from an ordinary blocked ticket by the presence of
`__proposal__`, which no agent-reachable path can write.

---

## Requested is not granted

Two Pydantic models, both `extra="forbid"`, with **disjoint field names**:

| `RequestedBudget` (agent) | `GrantedBudget` (human/WA) |
|---|---|
| `requested_amount` | `granted_amount` |
| `requested_currency` | `granted_currency` |
| `purpose` | `purpose` |
| `justification` | `expires_at`, `granted_by_wa_id`, `granted_by_user_id`, `granted_at`, `ticket_id`, `signature` |

Because the amount/currency names are disjoint and both models forbid extras,
`GrantedBudget(**requested.model_dump())` raises `ValidationError` (10 errors)
and so does the reverse. A request **cannot** be laundered into a grant by any
dict round-trip. This is asserted directly in
`test_create_ticket.py::test_types_are_not_interchangeable`.

They also live under different reserved metadata keys, and the grant key is
refused by every agent-reachable write path.

---

## Reserved metadata keys

```
__proposal__          provenance (origin task/thought, goal)
__requested_budget__  what the agent asked for
__granted_budget__    what a human authorized     ← authorization
__budget_spent__      running ledger against the grant
```

`update_ticket` is otherwise an **arbitrary metadata write primitive** with deep
merge. Without a guard, the agent could mint its own grant by calling
`update_ticket(ticket_id, metadata={"__granted_budget__": {...}})`. That was the
central vulnerability of the naive design.

Both agent write paths (`create_ticket`, `update_ticket`) **refuse loudly** when
any reserved key appears — including when metadata arrives as a JSON *string*,
which `update_ticket` also accepts and which would otherwise be a bypass.

---

## Enforcement point

**`WalletToolService._execute_send_money`, before `provider.send(...)`.**

This is deliberate and is the single most important placement decision in this
design. It is the only point every rail converges through on the agent path.
Provider-level checks are opt-in by construction and six of seven providers never
opted in — so enforcing "where the limits already live" would have enforced for
USDC and silently skipped stripe, wise, mpesa, razorpay, pix and chapa, **while
producing a passing test suite**. The all-rails test
(`test_budget_envelope_enforcement.py::TestEveryRailIsGated`) parametrizes over
`PROVIDER_MODULES` and asserts `provider.send` is never awaited without an
approved budget.

### The rule

```python
granted_remaining = grant.granted_amount - ledger.total_spent
trust_remaining   = min(trust.max_transaction, trust.daily_remaining)
effective_limit   = min(granted_remaining, trust_remaining)

allowed = amount <= effective_limit
```

The denial names which bound bit — `binding_constraint` is `"task_grant"` or
`"trust_envelope"`, and the message says `Bound by: task grant` /
`Bound by: trust envelope` with both numbers.

### Fail-closed ladder

Every one of these is a **denial**, never a fallthrough to unbounded:

| Condition | Reason code |
|---|---|
| no `task_id` | `NO_TASK_CONTEXT` |
| task is not processing a ticket | `NO_TICKET_FOR_TASK` |
| ticket has no grant | `NO_GRANTED_BUDGET` |
| grant is not a valid `GrantedBudget` | `GRANT_MALFORMED` |
| grant's `ticket_id` ≠ this ticket | `GRANT_TICKET_MISMATCH` |
| signature present and does not verify | `GRANT_SIGNATURE_INVALID` |
| signature present, no verifier available | `GRANT_SIGNATURE_INVALID` |
| `expires_at` passed | `GRANT_EXPIRED` |
| spend currency ≠ grant currency | `CURRENCY_MISMATCH` |
| over the grant | `TASK_BUDGET_EXHAUSTED` |
| over the trust envelope | `TRUST_ENVELOPE_EXCEEDED` |

A **corrupt ledger reads as exhausted**, not as zero-spent — otherwise wiping the
ledger would refill the budget.

### `spending_limits` is now load-bearing

`WalletAdapterConfig.spending_limits` (`max_transaction`, `daily_limit`) is read
by `_resolve_trust_envelope` and is the outer bound the grant nests inside. It had
zero readers before (#939). Where a provider exposes a live tracker (x402), the
tighter of config and tracker is used.

Three distinct objects are kept distinct, per #939: `SpendingLimits` (the trust
envelope here), `SpendingAuthority` (x402 attestation-level limits, still enforced
inside `X402Provider.send`), and `GasSponsorshipPolicyConfig.monthly_budget_usd`
(gas sponsorship — unrelated to agent spend).

---

## The nesting invariant

**A granted budget can never exceed the trust-driven envelope.**

Enforced in two places, with different strengths:

1. **At issuance** (`issue_grant`, advisory): raises `NestingViolation` → HTTP 422
   when `granted_amount > trust_ceiling`. The ceiling is resolved from the wallet
   config when a wallet is loaded; when no wallet is loaded the check is skipped.
2. **At spend** (`authorize_spend`, **authoritative**): `min(granted, trust)`
   binds *regardless of what was issued*. A grant of 10 000 against a trust
   envelope of 100 permits exactly 100.

Test `test_grant_larger_than_trust_never_permits_more_than_trust` is the decisive
one: it issues a 10 000 grant, allows a spend of exactly 100, and denies 100.01.

Spending decrements **both**: the inner (per-ticket, persisted in
`__budget_spent__`) and the outer (the provider's own `SpendingTracker` inside
`validate_send`).

---

## Why the agent cannot approve its own proposal

Four independent structural facts:

1. **No tool writes `__granted_budget__`.** Both agent ticket-write paths refuse
   every reserved key, dict form and JSON-string form.
2. **No tool promotes a proposal.** `update_ticket` refuses to move a ticket out
   of proposal state except to `cancelled` (withdrawing narrows; it never widens).
3. **`issue_grant` is not imported by any tool service or adapter.** Asserted by a
   test that greps `logic/services/tools/` and `ciris_adapters/`.
4. **The only issuance route requires `AUTHORITY`.** `UserRole.ADMIN` (level 2)
   does *not* satisfy it; AUTHORITY (3) and SYSTEM_ADMIN (4) do.

The strongest test is `test_no_tool_can_write_a_grant`: it iterates **every tool
the core tool service exposes**, hands each a grant-shaped payload, and asserts
that afterwards `load_grant` still returns `NO_GRANTED_BUDGET` and spend is still
denied. It is written against `get_available_tools()` rather than a hardcoded
list, so a future tool that opens a write path fails this test.

**What that proof does NOT cover** — stated plainly because it matters:

- It covers the *core tool service*. An adapter that ships its own ticket-writing
  tool is not covered by construction. The signature is the backstop there, not
  the enumeration.
- It does not defend against arbitrary code execution in the agent process. The
  System WA private key is a file that process can read, so a compromised process
  can forge a signed grant. The signature binds the grant to the *issuance route*
  against the *reasoning loop*, which can only act through tools — it is not a
  defense against process compromise.
- It does not cover the human API. `PATCH /v1/tickets/{id}` (ADMIN) can still
  write arbitrary metadata. A signed grant written that way fails verification;
  an *unsigned* grant written that way is honored in an unsigned deployment.
- It says nothing about whether the human approving is exercising judgment. A
  human who approves everything reproduces the problem in a slower loop.

---

## Runaway bound on proposals

An agent that can create tasks can create infinite tasks.

| Bound | Value | Catches |
|---|---|---|
| per originating task | **3** | one task looping on propose |
| per rolling window | **20 / hour** | runaway spread across many tasks |

Both fail with an explicit, actionable error ("consolidate into a proposal you
already opened"), not a silent drop. Rate-limited proposals are **not persisted** —
asserted by `test_rate_limited_proposals_are_not_persisted`.

Counters are in-process and reset on restart. See "what this does NOT do".

---

## Why `create_ticket` is not `requires_approval=True`

Deliberate, and worth arguing:

- A proposal has **no external effect**. It writes a row no processor picks up and
  notifies no one.
- Gating it behind approval is **circular** — the proposal exists in order to ask
  for approval.
- It would turn every ask into a human interrupt, which is the
  denial-of-service-on-the-human that #905 warns about ("asking a human 70 times
  is not a control").

Separately: **`requires_approval` is not enforced anywhere.** Its single
consumption site is `dma/tsaspdma.py:247`, which appends the markdown line
`**⚠️ Requires wise authority approval**` to an LLM prompt. Nothing branches on
it — not the handler, not the bus, not a conscience. `send_money` has carried
`requires_approval=True` since it shipped and it has never gated anything. The
docs in `CLAUDE.md:429` and `ciris_adapters/README.md:249` claiming it "triggers
DEFER" are inaccurate. **That is precisely why this design does not rely on it**;
the budget gate is deterministic and sits on the spend path.

---

## The seam to `TaskEnvelope` (Phase 1, `feat/938-task-envelope`)

That branch owns `TaskEnvelope` and `ToolBus.execute_tool`. Nothing here touches
either. No competing envelope type is defined — `GrantedBudget` is a *spend*
authorization on a ticket, not a capability envelope on a task.

The intended fold, when `TaskEnvelope` lands:

1. `authorize_spend(task_id=...)` currently reads `task_id` from tool
   **parameters**, injected by `ToolHandler._build_tool_params:138`. That line is
   `if thought.source_task_id and "task_id" not in tool_params` — **a
   model-authored `task_id` is not overwritten**, so today it is spoofable. This
   does not currently escalate (see below) but it should become
   handler-authoritative, or better, arrive via `TaskEnvelope` rather than through
   the parameter dict at all. **This is the single seam to change.**
2. `TaskEnvelope` should carry the resolved `ticket_id` so
   `resolve_ticket_id_for_task` (which today re-reads the raw persist row because
   `TaskContext` is `extra="forbid"` and drops `ticket_id`) becomes a field read.
3. The spend gate can then move to the bus as one more envelope-keyed policy,
   with `_execute_send_money` keeping its check as defense in depth.

**On the spoofable `task_id`:** spoofing it only lets a task point at a *different
ticket*, and the grant is bound to that ticket with an expiry and a purpose. It
cannot conjure a grant where none exists, and the total spend across all tasks
pointing at one ticket is still capped by that ticket's single ledger. It is a
real weakness in attribution, not in magnitude. It should still be fixed.

---

## The human-approval surface (client contract)

The HITL approval UI lives in `client/` on `feat/938-hitl-approval-ui` and is
documented in `FSD/HITL_APPROVAL_SURFACE.md`. Its `approvals/BudgetApprovalSeam.kt`
is the **sole owner** on the client side of the metadata key names, the endpoint
paths, the request/response bodies, the fixed-point amount math and the
≤-requested constraint. If a field name here changes, that one file changes.

Wire contract:

| Direction | Call | Auth |
|---|---|---|
| read proposals | `GET /v1/tickets?status_filter=blocked`, proposal iff `status=="blocked"` **and** `metadata.__proposal__` present | OBSERVER |
| read budget state | `GET /v1/tickets/{id}/budget` | OBSERVER |
| issue grant | `POST /v1/tickets/{id}/budget/grant` | **AUTHORITY** |
| promote to work | `PATCH /v1/tickets/{id}` `{"status": "pending"}` | existing |

**Granting and promoting are deliberately separate calls.** Approving money and
starting work are different decisions and the UI keeps them distinct.

**404 disambiguation.** A missing ticket returns a structured detail:

```json
{"detail": {"error_code": "TICKET_NOT_FOUND",
            "message": "Ticket PROP-X not found — no such ticket on this node"}}
```

A server predating this feature answers a bare `{"detail": "Not Found"}`. Clients
should branch on `detail.error_code` (`TICKET_NOT_FOUND_ERROR_CODE`), never on
prose; the lowercase word "ticket" is also present in the message for
substring-matching clients, but that is a courtesy, not the contract.

**Trust headroom.** `GET /v1/tickets/{id}/budget` returns `trust_headroom` with
`{amount, currency, max_transaction, daily_remaining, source}`. This is the
**same number the gate applies** — it is resolved by calling the wallet tool
service's own `_resolve_trust_envelope`, not by re-deriving it in the API layer,
so the figure shown to the approving human cannot drift from the figure enforced
at spend. It is `null` when no wallet adapter is loaded, and the client renders
nothing rather than guessing.

Rationale: a human asked to approve $X with no view of whether the deployment has
$50 or $50,000 of remaining envelope cannot give meaningful consent, which would
undercut the point of making approval the issuance event.

The client no longer enforces `granted ≤ requested` (see the ruling below); it
now renders an explicit confirmation naming the ratio instead, because the hazard
on an over-grant is a mis-typed zero rather than a policy disagreement. Nothing
about the gate depends on the client behaving either way.

**The server does not enforce `granted ≤ requested`.** The agent's request is
*information for the human*, not a constraint on them. An AUTHORITY user who
knows the true cost may grant above a lowballed request, and forcing a re-propose
instead would burn the agent's proposal rate budget and add a reasoning
round-trip for no safety gain. The bound the server does enforce is
`granted ≤ trust ceiling`.

#### RULED — over-request grants are permitted

The user ruled: *"yes an AUTHORITY can approve above what the agent requested, of
course, the agent may have requested too little."*

So **`granted ≤ requested` is a constraint nowhere in the system** — not in the
server, and not in the HITL client either, which dropped its local restriction on
the same ruling. The agent's request is information for the human, not a bound on
them. An agent that lowballs a fee out of ignorance must not be able to cap what
a human who knows better may authorize.

The real bound is unchanged and unweakened: **`granted ≤ trust ceiling`**, checked
at issuance and again as `min()` at every spend. Tests assert that an
over-request grant is still denied when it exceeds headroom, and that issuance
still raises `NestingViolation` above the ceiling — the ruling relaxed the
request comparison, nothing else.

**Over-request grants are recorded, not blocked.** Two fields on `GrantedBudget`:

| Field | Meaning |
|---|---|
| `exceeds_request: bool` | True when `granted_amount` exceeded the request at issuance |
| `requested_amount_at_grant: Decimal \| None` | Snapshot of the request, so the ratio stays reconstructable from the grant alone |

Both are **derived server-side** in `issue_grant` from the ticket's
`__requested_budget__`, and are never read from the request body. A
client-asserted audit flag would be worthless: the operator most motivated to
hide an over-grant is the one calling the endpoint directly, who would simply
omit it — the same curl-bypass argument that decided the ruling. The API model
accepts the client's transitional fields and ignores them; a test asserts a lying
body cannot change the record.

Both fields sit inside the canonical signed payload, so the marking cannot be
stripped or forged without invalidating the signature.

`requested_amount_at_grant` is `None` when the ticket carried no request at all —
a human-opened ticket, or an agent proposal that asked for work but not money.
Those are ordinary, grantable, and explicitly tested: **a null request must never
block issuance**, which is the failure mode a naive comparison would have
introduced.

### Re-granting: raises the ceiling, never refunds

Issuing a second grant on a ticket **replaces the grant and preserves the spend
ledger**. Granting 40 after 25 was already spent leaves 15 remaining, not 40.
This is a security property, not a convenience: if a re-grant reset the ledger,
"raising the budget" would silently refund spent money and repeated re-grants
would be an unbounded spend channel. Locked by
`TestRegrantSemantics::test_regrant_preserves_the_spend_ledger`.

Re-granting *below* the amount already spent clamps remaining to zero — the
effective revocation path, since there is no explicit revoke verb yet.

Consequence for any UI: never render the granted amount alone. Render
granted / spent / remaining, because after any spend the granted figure alone
overstates what is available.

---

## What this does NOT do

Stated plainly, because a security control described in absolutes is a control
nobody can audit.

- **It does not gate the human `/v1/wallet/transfer` route.** `wallet.py:674`
  calls `provider.send()` directly, bypassing the tool service. That is an
  ADMIN-authed human path, not the reasoning loop, so it is out of scope by
  design — but it means "all spend is budget-gated" would be a false claim.
  **Agent spend is gated. Human spend is not.**
- **The trust envelope's limits carry no currency.** `SpendingLimits.max_transaction`
  and `.daily_limit` are bare `Decimal`s with no declared unit, while
  `SpendingTracker` keys its accumulator *by* currency. So `max_transaction=100`
  means "100 of whatever is being sent" — 100 USDC and 100 KES are ~1000× apart
  in value and both pass. The `GET /{id}/budget` response stamps
  `trust_headroom.currency` with the *ticket's* currency, which is the best
  available answer but is strictly an assumption, not a declared fact from
  config. A deployment transacting in more than one currency does not have one
  meaningful ceiling. Fixing this means adding a currency (or a per-currency map)
  to `SpendingLimits` — an operator-visible config change, filed rather than done
  here.
- **There is no explicit revoke endpoint.** Re-issuing a grant below the amount
  already spent is the effective revocation (remaining clamps to zero), and
  re-issuing above it raises the ceiling while preserving the ledger. Both are
  locked by tests, but "revoke" deserves to be its own verb rather than a
  side effect operators have to know about.
- **The outer trust envelope is still process-global and lost on restart.**
  `SpendingTracker` is in-memory, wall-clock-windowed, keyed by currency only.
  N occurrences give N× the daily limit against one shared wallet, and a restart
  silently refills it (#939 item 3). The **inner** envelope does not have this
  problem — the per-ticket ledger is persisted in ticket metadata and shared
  across occurrences via the database.
- **Fiat rails still have no daily accumulation.** They have no tracker, so
  `daily_remaining` falls back to the configured ceiling each call. Per-transaction
  and per-grant bounds hold; a per-day bound for fiat does not.
- **Proposal rate limits are in-process.** A restart resets them. They bound a
  runaway loop, not a determined adversary.
- **An unsigned grant is honored in an unsigned deployment.** If no WA signing key
  is available, `signature` is `None` and the structural defense (no tool writes
  the key) is the whole defense. A *signed* grant that fails verification is
  always denied.
- **It does not make an approved spend wise.** A human who approves a budget for a
  harmful purpose has authorized a harmful spend. This is a magnitude control and
  an authorization control; it is not a judgment control. That remains the
  conscience layer and WBD, which are semantic, not deterministic.
- **It does not cover non-spend consequential actions.** Kick/ban and the rest stay
  where they are, gated by judgment about specific content, exactly as #938's
  correction requires.

---

## Upstream asks

1. **CIRISPersist** — add a `proposed` variant to the ticket-status enum. Today
   proposals ride `blocked`, which is semantically defensible but conflates
   "waiting on a human decision to start" with "waiting on an external
   dependency mid-flight".
2. **CIRISAgent** — make `ToolHandler._build_tool_params` authoritative for
   `task_id` (drop the `not in tool_params` condition), or thread task identity
   outside the parameter dict.
3. **CIRISAgent** — either enforce `ToolDMAGuidance.requires_approval` or delete
   it and fix the docs that claim it works. It is `sandbox_mode` in a different
   costume, and it is currently the *only* thing standing between a selected
   `send_money` and a fiat merchant API (#939).

---

## Files

| Path | Role |
|---|---|
| `ciris_engine/schemas/services/budget_envelope.py` | Schemas, reserved keys, `is_unapproved_proposal` |
| `ciris_engine/logic/services/governance/budget_envelope.py` | Resolution, `authorize_spend`, `record_spend`, `issue_grant` |
| `ciris_engine/logic/services/tools/core_tool_service/service.py` | `create_ticket` tool, reserved-key + promotion guards |
| `ciris_engine/logic/adapters/api/routes/tickets.py` | `POST /{ticket_id}/budget/grant` (AUTHORITY), `GET /{ticket_id}/budget` (headroom) |
| `client/.../approvals/BudgetApprovalSeam.kt` | Client-side sole owner of the wire contract (separate branch) |
| `ciris_adapters/wallet/tool_service.py` | The spend gate, `_resolve_trust_envelope` |
| `ciris_engine/logic/processors/states/work_processor.py` | Comment documenting the `blocked` dependency |
