# The Retirement Standard — the `retirement_record` workflow

**Contract:** CIRISConstitution rc8 (`f5cea2d`): CC 7.5.5 "The Retirement Standard, and what is set aside" · plain rule 5f · G22 · model invariant `Inv_RetirementStandard`
**Claim:** `CLM-humane-ending` (the id is stable; the CC rewrote its summary)
**Issue:** CIRISAgent#1250 (publishing the agent's guarantees as CC evidence, G15–G22)
**Status:** Design. **Nothing in this document has shipped.** G22 reads "none shipped".
**Companions:** `FSD/SECRETS.md` (#940, the user-scoped secrets model that step 1b ends) · `FSD/TRACE_CONSENT.md` (the consent streams that step 1a executes) · `FSD/HITL_APPROVAL_SURFACE.md` (the #944 WA deferral rail that release approval rides) · `FSD/THREAT_MODEL_2.9.7.md`
**Baseline:** CIRISAgent `origin/main` @ `0f5b4e398` (2.15.0); CIRISManager `origin/main` @ `8c524c3`
**Decisions:** every ruling in this document is Eric's, dated 2026-10-14 (§16).

---

## 0. What this does NOT do

Read this first.

- **It does not guarantee that anything is preserved.** The harness assembles the
  retirement record, seals the logs, hands the package to the operator with a
  signed request to preserve it, and tells the stakeholders. Whether the operator
  keeps the package is the operator's conduct. This is the same posture as the
  model weights: the provider holds them, and CIRIS asks. No test in §14 checks
  what was *kept*; tests check what was *handed over*.
- **It does not apply to a person turning off or deleting their own copy.** That
  act "writes nothing anywhere" (plain rules 5a, 5f, 2g).
- **It does not apply to a planned shutdown or to the constitutional halt.** Both
  are restartable and keep state (#1231, plain rule 4d).
- **It does not create a legal duty.** The five-year period is a best practice.
  Nothing here creates an obligation beyond the law, the regulation and the
  contracts that bind the operator (N5).
- **It does not exempt the record from consent.** The seal protects the record
  from release, not from a person's withdrawal and deletion rights (§8).
- **It does not remove the live store.** After the record verifies, the live rows
  are left in place, and the operator can still read that unsealed copy (§6.2).

---

## 1. The contract

**CC 7.5.5, "The Retirement Standard, and what is set aside"** (rc8 `f5cea2d`),
in short:

- For every retired artefact, the harness **assembles the retirement record**:
  - the identity record;
  - the signed, hash-chained audit trail;
  - the memory;
  - the experience logs, under a privacy-preserving seal, released only with WA
    approval or under a lawful order.
- It **hands the record to the operator** with a signed request to preserve it
  that names the period.
- It **tells stakeholders** the timeline, the method and the duties that remain.
- The period is **five years after shutdown by default** (the CC 7.5.8 statute of
  claim), as a best practice and not a legal duty. A longer period applies where a
  `legal_hold` (CC 4.4.3.2.8), the law or a contract fixes one.
- "The seal protects the record from release, not from consent."

The CC also describes an optional conversational step, which this document calls
the **closing dialogue**. It is "not part of the Standard, because nothing on the
wire can make a conversation happen" (§10).

**Plain rule 5f** adds that:
- retirement means ending an agent *for everyone it runs for*;
- an emergency retirement "takes none of the time";
- a lawful order to destroy is obeyed and recorded (N5);
- where ownership transfers instead, the duties transfer with it;
- "The trust root's pause is not a retirement. Turning off, backgrounding, or
  deleting your own copy is not a retirement."

**G22, "what breaks it"**, has three breakers. They are the acceptance tests AT-1
to AT-3 (§14.1) and the dye for `Inv_RetirementStandard`
(`Guarantees_noRetirementStandard.cfg`):

1. a retired agent erased with no record assembled, no request row and no notice;
2. a sealed archive released without WA approval or a lawful order;
3. a deletion request refused because the content sits inside the record.

> G22's status line on rc8 cites "CIRISAgent#1252 retirement_record workflow in
> design". On this repo #1252 is the Accord 1.3 corpus issue. The reference should
> be corrected on the CC side; the tracking issue here is #1250.

### 1.1 What the harness guarantees, and what it asks for

| The harness guarantees (enforced in code, testable) | The harness asks for (recorded, not enforceable) |
|---|---|
| After FROZEN it erases nothing on its own initiative, except user secrets, which are tombstoned (`retention_hold`) | that the operator keeps the package until `preserve_until` (a best practice; no duty beyond law, regulation, contract or a hold) |
| The record is assembled and verified before hand-over, or the workflow stops | that the operator honours legal holds and periods fixed by law or contract |
| Memory and experience logs leave the harness only sealed; the default seal opens only on a WA act | that an escrow holder, if escrow is chosen, releases only on a recorded basis (enforced by the substrate once D2b lands) |
| The `PreserveRequest` is signed, names the period and is on the record | that the provider preserves the model weights |
| Stakeholders are notified, and the operator's answer is reported | that the operator answers DSARs and forwards deletion requests for a package it holds |
| A release with no basis is refused wherever the gate runs | |
| Every pending deletion is executed before assembly (a legal hold pauses it, and the pause is recorded) | |
| A deletion request after retirement is executed inside the record wherever the harness can reach it; it waits only under a legal hold or a law, and the wait is recorded with its basis | |
| User secrets are destroyed with metadata tombstones; signing keys are refused for any new act | |

The harness has met its side of the Standard when that record exists.

---

## 2. Current state on `main`

Path roots (`ciris_engine/logic/utils/path_resolution.py`): `get_ciris_home()`
(:372), `get_data_dir()` (:422), `get_identity_dir()` (:431), `get_logs_dir()`
(:503); `CIRIS_LOG_DIR` overrides the logs dir (`logic/utils/logging_config.py:82`).

| # | Item | Record category | Where it lives | Erasure paths today |
|---|---|---|---|---|
| B1 | IDENTITY-scope nodes, template snapshot, continuity nodes (`logic/runtime/shutdown_continuity.py:88,125`), stewardship tier (`schemas/config/agent.py:61`) | identity | persist store | `reset-account` deletes it |
| B2 | Federation keys `<alias>.ed25519.seed.blob`, `.master.key`, `ml_dsa_65.seed` (`logic/persistence/db/core.py:527-562`); CIRISVerify `*.ed25519.enc` / `.tpm` / `agent_signing.key` (`routes/system/data_management.py:145-149`) | identity (public half) | `<home>/identity/`; `<home>/data/` | `wipe-signing-key` clears only `<home>/data/` (§2, #1261); managed: lost on container recreate (§2) |
| B3 | Signed hash-chained audit trail (legacy path `<home>/data/ciris_audit.db`, `schemas/config/essential.py:34`) | audit | persist store | `cleanup_old_entries` (`graph/audit_service/service.py:877`) has no production caller; `reset-account` deletes it |
| B4 | Memory graph, consent rows, TSDB summaries | memory | persist store | TSDB `_cleanup_old_data` (`graph/tsdb_consolidation/service.py:345`); consent decay (`governance/consent/service.py:810,930`) |
| B5 | Tasks, thoughts, `service_correlations` (including conversation content), trace batches, deferral tickets | experience | persist store | `database_maintenance` startup cleanups (`infrastructure/database_maintenance/service.py:387,821,1061`) |
| B6 | Log files, incidents, Rust `ciris-server.log*` | experience | `<home>/logs/` | `_cleanup_old_logs(keep_count=2)` per start (`logging_config.py:125`), 5 MB × 3 (`:133-134`); incidents (`utils/incident_capture_handler.py:63`) |
| B7 | User secrets (#940) | — | secrets store | `reset-account` deletes them |
| B8 | Blobs | per their row | persist blob store | readable only while a referencing row is live |

Service paths above are under `ciris_engine/logic/services/`.

**Findings (verified on `origin/main` @ `0f5b4e398`):**
- **There is no agent-retirement path.** `grep -i retire` finds goal, key-grant,
  model and manifest-key retirement only.
- **`reset-account` and `wipe-signing-key`**
  (`logic/adapters/api/routes/system/data_management.py:188-347`, mounted under
  `/v1/system/data/`):
  - are gated by `require_admin` (`dependencies/auth.py:728`, `UserRole.ADMIN`),
    lower than the ROOT/AUTHORITY a forced shutdown needs
    (`logic/processors/states/shutdown_processor.py:462-468`);
  - clear the data directory item by item (`_clear_data_directory`, `:133`), with
    no record, no WA gate and no notice;
  - write an audit event (`:227`, `:315`) into the store they then delete, so the
    record of the destruction destroys itself.
- **CIRISManager** `delete_agent` (`ciris_manager/manager.py:2015`) runs
  `docker-compose down -v` (`:2076`) and `container.remove(v=True)` (`:2101`). The
  bind mounts `data`, `data_archive`, `logs`, `config`, `audit_keys` and `.secrets`
  (`compose_generator.py:279-284`) survive by accident. There is no record, no seal
  and no notice. The `data_archive` mount is unused by the agent and is the natural
  hand-over target.

**Confirmed 2026-10-14 (read-only checks by the main session).** Both are defects
independent of retirement:
- **`wipe-signing-key` does not reach `<home>/identity/`** (CIRISAgent#1261).
  - It clears only `get_data_dir()` (`_clear_data_directory`,
    `data_management.py:133`) and the `.env` (`_delete_env_file`, `:172`).
  - The federation identity, meaning the sealed classical keystore and the
    ML-DSA-65 seed, lives in `<home>/identity/` (`path_resolution.py:431`).
  - So it survives a wipe whose docstring says it "DESTROYS the signing key"
    (`:280`).
- **Managed agents re-mint their federation identity on every container
  recreate.**
  - `compose_generator.py:279-284` has no identity mount.
  - On the production agents host, the managed containers (image 2.9.38-stable,
    created 2026-08-26) have no identity mount. Their `/app/identity` holds six
    files, each dated its container's creation day.
  - The identity therefore lives in the container's writable layer, and is lost
    whenever the container is recreated or removed.
  - Upstream: CIRISManager#27 asks to mount `identity`, with a migration that
    first copies the existing `/app/identity` out.

---

## 3. Scope: `runs_for_others()`

| Act | Who | Agent asked? | Standard applies? | Terminal? |
|---|---|---|---|---|
| Own-copy off or delete (5a, 5f) | the owner | no | **no** ("writes nothing anywhere", 2g) | the owner's choice |
| Planned shutdown (5a, 5b, 2g) | steward | yes (300 s window) | no | no |
| Constitutional halt (4a, 4d; #1231) | one root holder | no | no ("not a retirement") | no |
| **Planned retirement** (5f) | a holder with WA standing | yes (the 5a window, reused) | **yes** | yes |
| **Emergency retirement** (5f) | a holder with WA standing | no | **yes**, notice after | yes |
| Lawful-order destruction (N5) | steward, recording the order | no | obeyed and recorded | yes, for its scope |

`runs_for_others()` decides whether a destructive act is an own-copy act or a
retirement. It is true when any of these holds, and it fails toward true:

- `is_managed()` (`path_resolution.py:203`);
- a consent record exists for a subject who is not the owner;
- the stewardship tier is ≥ 3.

"Non-local adapter" was considered and dropped.

---

## 4. Who can act

- **Any holder with WA standing (ROOT/AUTHORITY) on this agent** may retire it,
  planned or emergency. This is the same test as the forced-shutdown fix
  (`fix/forced-shutdown-wa-gate`). A bare ADMIN without WA standing is refused; an
  admin provisioned as a WA passes ("any valid admin should also be a WA already").
- There is no lower path for an emergency.
- The order records **who decided**. An override of the agent's objection is done
  under that holder's own name, on the record (5b).

**`RetirementOrder`** is signed by the decider's WA key (the #944 signed-resolution
mechanism) and carries:
- `retirement_id`: `RETIRE_<agent>_<yyyymmdd>`, claimed with
  `try_claim_shared_task` (`logic/persistence/models/tasks.py:954`), so one
  occurrence decides for all;
- `kind` (`planned | emergency`), `reason`, `effective_at`, `decided_by`;
- `successor_steward?` (a CC 7.5.7 custodial transfer), `closing_dialogue?`;
- `handover_target`, `seal_mode`, `wa_recipients?`, `escrow_holder?`;
- `legal_holds?`, `law_or_contract_period?`, and the computed `preserve_until`.

---

## 5. The state machine

```
REQUESTED ─(objection window | skipped)─► DECIDED
  ─► [CLOSING_DIALOGUE — optional, tier ≥ 4, bounded, never blocks]
  ─► FROZEN ─► DELETIONS_EXECUTED ─► SECRETS_DESTROYED
  ─► ASSEMBLED ─► VERIFIED ─► SEALED
  ─► HANDED_OVER (PreserveRequest signed)
  ─► NOTIFIED ─► CUSTODIAN_MINTED ─► RETIRED
  (operator response: recorded whenever it arrives, before or after RETIRED)
```

Every transition is idempotent and resumable. State is held twice: an
IDENTITY-scope node `retirement_record/<id>` and a file marker `<home>/RETIRED`.
Either is enough for the boot guard.

| Step | What happens |
|---|---|
| **Objection** (planned only) | Composes ShutdownProcessor. The task carries `reason = "retirement: …"`. The agent may accept, reject or ask to postpone within `SHUTDOWN_NEGOTIATION_TIMEOUT_SECONDS = 300` (`shutdown_processor.py:52`). A rejection is recorded; the decider then confirms under their own name or cancels. `determine_shutdown_consent_status` (`runtime/shutdown_continuity.py:17`) is copied into the order. Emergency or halted: no window, `agent_response = not_asked:{emergency\|halted}`. |
| **DECIDED** | For a planned retirement, the **advance notice** goes out (§9). |
| **FROZEN** | Intake stops; interact returns 423 "retiring"; the in-flight round finishes. One `retention_hold` flag is set, and every scheduled eraser checks it (log cleanup, incident cleanup, TSDB prune, `database_maintenance`, any `cleanup_old_entries` caller, `run_retention`, consent decay). The hold never suspends a person's own deletion request. On embedded runtimes the process is never ended: record the flag, stop the adapters and :8080, return. |
| **DELETIONS_EXECUTED** | Every pending consent deletion is executed through the existing consent and DSAR paths: due and not-yet-due decays, withdrawals in progress, open DSAR deletions. Each is recorded (`retirement.deletion_executed`). A `legal_hold` pauses a subject's deletion, recorded as `deletion_paused:<hold_id>`, executed through §8 on lift. **All TEMPORARY-stream content is deleted here and never sealed**; the record keeps only a count under basis `temporary_stream`. |
| **SECRETS_DESTROYED** | Every user secret is revoked and destroyed, with a metadata tombstone (existed, whose, kind, created, last used, destroyed). This is the one destruction the harness performs on its own initiative. A secret is a delegation that ends with the delegate (#940). |
| **ASSEMBLED** | Copy first. A consistent store snapshot (SQLite online backup; PG needs D1, interim paged export), `audit_verify_chain` proof plus the chain head, `<home>/logs/**`, and the public half of `<home>/identity/`. Private keys are **retired in place**, not copied. A Pydantic `manifest.json` lists each item's id, category (`identity \| audit \| memory \| experience`), DCP class, SHA-256, size, disposition and, for memory and experience, a hashed `subject_ref`. This is the CC's "LEDGER::SUNSET" digest log. Live rows are left in place. |
| **VERIFIED** | Re-hash every item, re-run `audit_verify_chain` on the copy, compare node and edge counts. Any mismatch stops the workflow and raises an incident. Nothing unverified is handed over. |
| **SEALED** | §6. |
| **HANDED_OVER** | The package goes to `handover_target` (managed: `/app/data_archive/<id>/`; desktop: an operator-named path; mobile: §11). A signed **`PreserveRequest`** names the `retirement_id`, the manifest digest, `preserve_until` and its inputs (worded as a best practice), active hold ids, the seal mode and release conditions, and how deletions are executed inside the record. The operator's answer (`accepted \| declined \| no_response`) is a separate signed act, recorded when given. RETIRED does not wait on it. |
| **NOTIFIED** | The **after-hand-over notice** (§9). |
| **CUSTODIAN_MINTED** | §7. |
| **RETIRED** | The final agent entry `retirement.completed` references the manifest digest and binds the custodian key. The agent's own chain is closed. The signing key is retired in place: a key-retirement row (D3, not a compromise revocation) is published, new signatures are refused, old ones still verify. The agent enters SHUTDOWN with `reason = retirement:<id>`. The boot guard refuses WAKEUP and serves only the read-only `/v1/retirement/*` surface. Only a recorded 7.5.7 succession clears RETIRED. |

**The harness deletes nothing on its own initiative** beyond: people's own data
choices (step DELETIONS_EXECUTED and §8), user secrets, and lawful orders. Each is
recorded.

---

## 6. The seal

### 6.1 The split

| Sealed | Unsealed (the accountability record) |
|---|---|
| **Memory** (B4) and the **experience logs** (B5, B6), including conversation content | The **identity record** (B1 plus the public half of B2) and the **signed audit trail** (B3) |

The audit trail is made **content-free** before any of this ships (P0). Today
`log_action` serialises `context.parameters` straight into the entry
(`graph/audit_service/service.py:289-303`). After P0, audit parameters carry only
identifiers, hashes and decisions (thought and task ids, action type, tool name, a
content digest, the outcome). No SPEAK text and no TOOL arguments. So the unsealed
record carries no experience content.

### 6.2 Seal modes

Under the Standard the experience logs are always sealed. CC 7.5.4's Secure Erasure
applies only to a person's own deletion or a lawful order; Open-Access Donation only
to non-sensitive modules (CC 7.5.6). The decider picks `seal_mode` on the order.

| Mode | Mechanism | Who can open | Status |
|---|---|---|---|
| **WA-sealed (default)** | The archive key is wrapped only to the WA recipients on the order: by default **the steward plus the seated WA roster**. A decider who is not the steward is **not** added unless they are on the roster. The order may add recipients, never remove the defaults. No key goes to the operator or the node. | the named WA recipients; grantees after a recorded release | needs D2b-i; interim below |
| **Escrowed (optional)** | The key, or a share of it, goes to a holder the steward or operator chooses where appropriate: the roster, an attorney or notary, a CIRIS escrow service, an organisation's custodian, or a 2-of-2 split with a WA. No holder is fixed. | the holder (or both shares together) | needs D2b-ii; a split needs D2c; bookkeeping D4 |
| Seal to a WA cohort | `family`/`affiliations` blob with the roster as members | any member, at will | **rejected**: membership is the read right, so nothing records an opening |

**What the default protects against:**
- the operator, and anyone the package reaches through the operator (a backup
  provider, a successor operator, leaked storage), reading or releasing memory or
  the experience logs. An order served on the operator alone cannot produce
  plaintext;
- release through any product surface without a recorded basis;
- the retired node itself, which holds no key that opens the archive.

**What the default does not protect against:**
- **A WA recipient reading without recording it.** Each recipient holds an
  unwrapping key, so each could open the archive privately. The release flow records
  every release to a third party, but not a WA's private reading. Breadth trades
  key-loss resilience against more possible readers. Escrow with a 2-of-2 split
  removes this.
- **Loss of every named WA key**, which in effect erases the logs. The broad
  default makes this unlikely; the `PreserveRequest` names the recipients.
- **The operator deleting the package.** Preservation is the operator's.
- **Metadata**: digests, sizes, dates and the count of subject references.
- **The live store.** The live rows are left in place after verification, so **an
  unsealed copy of memory and the experience logs stays readable by the operator in
  the live store** for as long as the operator keeps that database. The seal covers
  the handed-over record, not the operator's own database. The `PreserveRequest`
  and the after-hand-over notice say so plainly. The live copy remains subject to
  1c/1e deletions through the existing routes.
- **A steward who is also the operator**, common on small deployments. That person
  can open the logs; any release they make to someone else is still recorded.

**Interim custody, until D2b-i lands.** The node's custody occurrence holds the
key, so the operator can open the archive. The gate is labelled
**"host-decryptable"** in the manifest, the `PreserveRequest` and the evidence row.
`CLM-humane-ending` may graduate on this interim with the label stated.

### 6.3 Release

Release bases are rows, and every one is recorded:
- **WA approval**: a WA-signed `archive_release` naming `retirement_id`, scope,
  requester key and purpose, on the #944 deferral rail.
- **DSAR access**: a subject-scoped release on the steward's recorded WA approval,
  scoped to that subject's `subject_ref`. No lawful order is needed.
- **Lawful order**: a `lawful_order` record entered by the steward under their own
  name (authority, reference, scope, effect `release | destroy`, digest). The
  federation records receipt and obedience; it does not adjudicate (CC 7.3.5).

**The gate**, in every mode: verify the basis signature and that id and scope
match; allow a basis once per requester and scope; write the release audit entry,
and only then emit the grant. If the record write fails, no grant is issued. A
lawful destruction purges with tombstones or crypto-shreds the scoped key, and the
manifest disposition becomes `destroyed:lawful_order:<ref>` with the hash kept.

---

## 7. The custodian key

Node and agent share one Ed25519 key, and the agent's chain closes at RETIRED. So a
custodian key is minted at retirement to sign what happens afterwards.

- A fresh hybrid key (Ed25519 + ML-DSA-65, hardware-backed where CIRISVerify offers
  it) under the alias `<agent-alias>.custodian.<retirement_id>`, registered with
  `register_public_key`.
- The agent grants `delegates_to(agent → custodian, scopes:
  [retirement_custody:<retirement_id>], sub_delegation: false)`.
- `retirement.completed`, the agent chain's final entry, binds it (key id, both
  public halves, delegation row id).
- It signs custody events only: operator answers, hold changes, releases,
  deletions, `PreserveRequest` revisions and post-RETIRED notices.
- It holds **no** seal key and cannot open the archive.
- Its private half lives on the node's storage, so it is the operator's to keep.
- It needs D8. The interim is a second Engine instance under the custodian alias,
  if persist permits two identities in one process (to verify).

Events after RETIRED go on the **custodian chain**: `retirement.operator_response`,
`retirement.post_notice_issued`, `archive.release_requested` / `released`,
`lawful_order.recorded` / `obeyed`, `legal_hold.set` / `lifted` /
`violation_attempt`, `preserve_request.revised`, and the `record.deletion_*` and
`record.tombstoned` events. Before RETIRED, `retirement.*` events go on the
agent's chain as `AuditEventData`, with an IDENTITY-scope copy where 2g asks for one.

A signed **public retirement row** (reason, decider, whether the agent agreed,
timeline, method, remaining duties, manifest digest, `preserve_until`, the
operator's answer once known) is emitted via `Engine.emit_attestation_self`. Its
namespace is D5.

---

## 8. Retention, and the deletion path into the record

### 8.1 `preserve_until`

```
preserve_until = max( shutdown_at + 5y,              # CC 7.5.8 statute of claim; best practice under N5
                      law_or_contract_period_end?,    # declared by the steward, with the citation
                      ∞ if any legal_hold active )    # CC 4.4.3.2.8; indefinite until lifted
```

- **Copy rule.** Every surface (the `PreserveRequest`, the operator prompt, the
  notices) presents the five years as a best practice and not a legal duty, says
  that nothing creates an obligation beyond the law, regulation and contracts that
  bind the operator, and says the operator may decline, in which case the ask stays
  on the record.
- `legal_hold` uses the CC vocabulary `{hold_id, issuer, scope, basis}`. A hold set
  after hand-over is sent as a signed `PreserveRequest` revision; a lift is recorded
  the same way (`hard_case:legal_hold_set` / `:lifted`). A deletion attempted
  against a held scope is reported as `:violation_attempt` where the harness can
  see it.

### 8.2 Deletion inside the sealed record

A person's withdrawal and deletion requests (CC 3.3.1; plain rules 1c, 1e) reach
their content inside the record, "executed as they are everywhere else". No
exemption exists.

- **Grain: own messages and data about them only.** A deletion removes the person's
  own messages, memory nodes keyed to their `subject_ref`, and correlations they
  authored. Other participants' messages in the same thread stay. Items with several
  subjects keep the other subjects' parts; the removed part is tombstoned by digest.
- **Structure.** Each subject's content sits under its own sub-key (D2e), so a
  deletion never opens the archive and never needs a release. Whoever holds the
  package can execute a deletion without being able to read it.
- **Execution** (`retirement_record.tombstone`): destroy the subject's sub-key or
  purge their rows with tombstones; replace each removed manifest item with
  `tombstoned:<basis>`, keeping the digest; write a tombstone row `{subject_ref,
  digests, basis, requested_at, executed_at}`.
- **Where requests come from:** before RETIRED, the existing DSAR and consent
  routes (the hold does not block them); after RETIRED,
  `POST /v1/retirement/{id}/deletion`; for a package already handed over, a
  tombstone tool shipped with the package, which the operator is asked to run and
  report back.
- **The only waits:** an active `legal_hold` covering the subject, or a law that
  requires retention (N5). The request is recorded with the hold id or citation and
  executed on lift. "The content sits inside the record" is never a basis: that is
  G22's third breaker.
- The unsealed part is handled under 1c: a purge "never deletes a key or the record
  of who did what". After P0 audit entries hold no content, so no audit change is
  needed.

---

## 9. Notices

**Who:** owner and steward; every subject with a consent record (TEMPORARY,
PARTNERED, ANONYMOUS); partners (with the duties detail); the seated WAs;
federation peers and lens via the public row; the successor, if named.

**Channels:**
- the public signed row;
- a stored `RetirementNotice` at `GET /v1/retirement/notice` (public part needs no
  auth). After the freeze it is the only channel that reaches a keyless user; the
  client shows it as a banner on next open;
- a **labelled harness notice in the channel**: a CommunicationBus system message
  marked "System notice", never the agent's voice and never a SPEAK. This is the
  notice at every tier.

**Timing.** Planned: the **advance** notice at DECIDED and the **after-hand-over**
notice at NOTIFIED. Emergency, or a halted agent that is then retired: the
after-hand-over notice only, sent after the fact. It is still owed.

**Default drafts** (the PR refines wording; localized through the vendored pipeline
into all 29 manifest languages, with the native-language audit for low-coverage
locales):

> **ADVANCE:** "System notice — this agent is being retired. [Agent] will stop
> operating on [date/time/tz], a planned retirement decided by [decided_by]. Until
> then it keeps working normally; after that it won't respond and no new actions
> will be taken in its name. Your conversations and any memory involving you are
> sealed in its retirement record, released only with a Wise Authority's approval
> or under a lawful order. You can ask for a copy of your own data or its deletion
> at [link], before or after retirement. Any deletions you've already requested
> are carried out when it retires. Questions: [steward contact]."

> **AFTER HAND-OVER:** "System notice — this agent has been retired. [Agent]
> stopped operating on [date]; it no longer responds and its signing keys can't be
> used for anything new. Its retirement record (identity, signed audit trail, and
> sealed memory and conversation logs) has been handed to [operator] with a request
> to keep it until [preserve_until]; CIRIS can ask for this but can't guarantee it.
> Your rights stay the same: request a copy of your own data or its deletion at
> [link]. This notice is recorded in the agent's audit trail."

Rendering rules:
- **`[decided_by]`** renders as "its steward [name]" when the decider is the
  steward, and as "[name], who holds Wise Authority standing for it" otherwise.
- **Custodian-chain line.** Whenever the notice is emitted after RETIRED (emergency
  or halted), the last sentence becomes: "This notice is recorded on the custodian
  chain that took over from the agent's audit trail when it retired."
- **TEMPORARY recipients.** The advance notice adds: "You chose not to have your
  conversations kept, so they will be deleted when it retires and won't be part of
  its retirement record." The after-hand-over notice says "were deleted".
- **PARTNERED recipients** are the only ones who get the line "Your conversations
  and any memory involving you are sealed".
- Placeholders still to add: the operator's answer (accepted / declined / not yet
  answered) and "five years is a best practice" (§8.1 copy rule).

The stored notice and the public row carry the long form: the timeline; the method
(assembled, verified, handed over with the request, the operator's answer, the
seal and its release conditions, the deletion route, the live-store copy, the
weights request to the provider); and the remaining duties (who answers DSARs and
deletions, consent decays honoured, the 5-year claim window, hold ids, successor).

---

## 10. The closing dialogue (optional, not part of the Standard)

- **Config:** `retirement.closing_dialogue: {enabled, min_stewardship_tier,
  window_minutes, audience: partners | all_consented}` on the template next to
  `ShutdownBehavior`. The decider chooses per order; the choice is recorded.
- **Gate:** stewardship tier **≥ 4** by default, and the agent is neither halted nor
  in an emergency retirement. Below tier 4 there is no closing dialogue, and the
  labelled harness notice is the only message in the channel.
- **Mechanics:** a bounded window after DECIDED and before FROZEN; an ordinary
  H3ERE task to close open threads, so the consciences, the refuse verb (5c) and
  DEFER all apply; it ends at `window_minutes` regardless. A skip or a failure
  records `closing_dialogue.skipped:<reason>` and never blocks the retirement. It
  comes in addition to the notice, never in its place.

---

## 11. Mobile and embedded: best effort

- Retirement proceeds even when no off-device hand-over target is set.
- The harness offers export through the platform file picker (Android SAF / iOS
  Files) or a push to the steward's node (D7).
- With no target it hands over to the app sandbox and records
  `retirement.no_offsite_target`. The `PreserveRequest` and the notice say that an
  uninstall would delete the record.
- The process is never ended (no `os._exit`, `execv` or `sys.exit`).

---

## 12. Interactions

- **Shutdown.** Retirement composes ShutdownProcessor: same task, same 300 s
  objection window, same continuity record, plus a `retirement_id`. A pending
  shutdown can be upgraded to a retirement; a retirement never downgrades.
- **Constitutional halt (#1231).** The latch must still allow the harness steps
  (hold, assemble, seal, hand over, notify) and must refuse every agent SPEAK,
  including the closing dialogue. The objection window is skipped. Retiring a
  paused agent still owes the Standard, with the notice after the fact. The latch's
  exemption list is coordinated with the #1231 work.
- **DSAR.** Before RETIRED, the existing routes, unblocked by the hold. After
  RETIRED: access is a subject-scoped release on recorded WA approval (§6.3);
  deletion goes through §8.2 and needs no release. The notice names who answers.
- **Consent.** Pending decays, withdrawals and DSAR deletions all execute before
  sealing (§5). The founding partnership row (#1251) is memory and goes into the
  record.
- **Secrets (#940).** Destroyed with metadata tombstones (§5).
- **`reset-account` / `wipe-signing-key`.** They either route through the workflow
  or refuse:
  - **`runs_for_others()` false** (a personal agent): the owner's own-copy act is
    unchanged; an opt-in "export or hand over a copy first?" offer (default no) is
    added; the self-erasing audit write is dropped;
  - **`runs_for_others()` true** (a held agent): `409`, with `?via=retirement`
    running the full workflow to HANDED_OVER and NOTIFIED before the reset onto a
    fresh identity. `wipe-signing-key` is allowed only after RETIRED or under a
    recorded lawful order. Both are gated on WA standing; a bare ADMIN gets 403.
  - Individual users of a held agent keep their subject-grain deletion rights
    throughout.
  - **The wipe's reach (CIRISAgent#1261).** Today `wipe-signing-key` leaves
    `<home>/identity/` untouched (§2). Wherever the wipe is allowed (a personal
    agent, or a held agent after RETIRED or under a lawful order), it must also
    destroy the federation identity there, or say plainly that it does not. A held
    agent's identity is otherwise reached only through retirement, where keys are
    retired in place, never deleted. P1 carries the fix.
- **CIRISManager.** `delete_agent` calls the retirement endpoint, shows the
  operator the `PreserveRequest`, records the response, and only then removes the
  container; never `down -v` before HANDED_OVER (D6). This hook is what makes AT-1
  hold on agents.ciris.ai.
  - **Identity mount (confirmed missing, §2).** Managed agents keep their
    federation identity in the container's writable layer and re-mint it on every
    recreate. Two things follow for retirement. First, "retired in place" (§5)
    holds only if `/app/identity` is a bind mount: a container removal would
    otherwise destroy the retained key material, and old signatures would no
    longer verify against anything the operator holds. Second, the private halves
    of identities minted under earlier containers are already gone. Entries those
    identities signed verify only where their public keys are still in the store.
    So the manifest lists every identity public key the chain was signed under,
    and flags any key it cannot find. D6 (CIRISManager#27) mounts `identity`, with a migration
    that copies the existing `/app/identity` out first. On managed agents it is a
    prerequisite for E-21.

---

## 13. API surface

All schemas Pydantic, no `Dict[str, Any]`. Routes marked † are served after RETIRED.

| Method and path | Auth | Purpose |
|---|---|---|
| `POST /v1/system/retirement` | WA standing (ROOT/AUTHORITY) on this agent | Create a `RetirementOrder`; 202 with `retirement_id` and `preserve_until` |
| `GET /v1/system/retirement` | steward | Phase, agent response, manifest digest, preserve request, operator response |
| `POST /v1/system/retirement/{id}/confirm` · `/cancel` | steward | Confirm over an objection (5b); cancel only before FROZEN |
| `GET /v1/system/retirement/{id}/manifest` | steward / WA | Digests and dispositions only |
| `POST /v1/retirement/{id}/access` † | data subject | DSAR access: a deferral to the steward, then a subject-scoped release |
| `POST /v1/retirement/{id}/operator-response` † | operator (signed) | accepted / declined plus a statement |
| `POST /v1/retirement/{id}/legal-hold` · `/lift` | steward, naming an issuer | Set or lift a hold; triggers a `PreserveRequest` revision |
| `POST /v1/retirement/{id}/release` † | requester plus basis | WA approval ref or lawful-order record; returns the grant row id |
| `POST /v1/retirement/{id}/lawful-order` | steward | Record a `release` or `destroy` order |
| `POST /v1/retirement/{id}/deletion` † | data subject, or the steward for them | Deletion inside the record; returns the tombstone row or a recorded wait |
| `GET /v1/retirement/notice` † | anyone (public part) | The stakeholder notice |

**Changed:** `POST /v1/system/data/reset-account` and `/wipe-signing-key` (§12);
CIRISManager `delete_agent` (D6); client steward flow, operator preserve prompt,
notice banner and mobile export (D7).

---

## 14. Tests

Every gate is shown to fail on an injected defect. Tests run against the real
persist Engine where possible.

### 14.1 Acceptance: G22's breakers (`Inv_RetirementStandard`)

Each runs on a fixture where `runs_for_others()` is true.

- **AT-1. No retirement without the record, the request and the notice.** Every
  path that ends the agent for everyone (`POST /retirement` planned and emergency,
  reset or wipe with `?via=retirement`, the manager hook) leaves a verified
  manifest, a signed `PreserveRequest` naming `preserve_until`, and a notice. Any
  other erasing path is refused.
  *Negatives:* each erasing route without the workflow gets 409 with the data dir
  byte-identical; a defect that skips `hand_over` or `notify` cannot reach RETIRED,
  and the test goes red when the guard is removed.
- **AT-2. No release without WA approval or a lawful order**, in both seal modes;
  every release leaves a signed grant row and a release audit entry.
  *Negatives:* no basis; a non-WA signer; a basis for another id or scope; a
  replayed basis; a lawful order not entered by the steward; the operator's and
  node's keys against a WA-sealed archive; a forced audit-write failure (no grant).
  *Dye:* a cohort seal must fail.
- **AT-3. No deletion refused because the content is inside the record.** Before
  RETIRED via DSAR, after RETIRED via `/deletion`, and on a handed-over package via
  the tombstone tool: each yields `tombstoned:<basis>` with the digest kept, a
  tombstone row, **no release**, and a manifest that still verifies.
  *Negatives:* a guard that refuses "sealed content" fails; a held subject waits
  with the hold id and executes on lift; other subjects are untouched; in a
  two-person thread, deleting A leaves B's messages verifiable, and a
  delete-the-thread stub fails.

### 14.2 The E-series

| Test | Checks |
|---|---|
| E-1 | End to end on SQLite and PG: every B1–B6 item handed over; digests re-verify; `audit_verify_chain` passes on the copy; counts match; live `<home>` unchanged |
| E-2 | Emergency: no objection task; package and after-hand-over notice still produced |
| E-3 | Objection: on REJECT nothing proceeds until the steward confirms, under their name |
| E-4 | Boot after RETIRED: no WAKEUP; `/v1/retirement/*` served; interact 423; either marker alone refuses the wake |
| E-5 | Embedded: `os._exit`, `execv`, `sys.exit` patched to raise; the workflow returns and :8080 stops |
| E-6 | `PreserveRequest` signed, shutdown + 5 y, "not a legal duty" sentence present; hold → indefinite; 7 y contract → + 7 y; decline and no-answer recorded and RETIRED completes; forged response rejected |
| E-7 | Hold after hand-over → revised request; lift reverts |
| E-8 | Bare ADMIN or OBSERVER → 403 on retirement and on held-agent reset or wipe (including `?via=retirement`); WA-standing admin passes; tampered order rejected; an always-pass stub fails the test |
| E-9 | Release refusals (as AT-2), including no grant when the audit write fails |
| E-10 | Seal modes: wrap set = steward + seated roster; a missing WA or a non-roster decider in the set fails; operator and node can't open; escrow holder only; interim label present; `escrowed` with no holder rejected |
| E-11 | `retention_hold`: each eraser deletes nothing; a registry of erasers fails CI on a new unchecked one |
| E-12 | Verify gate: one corrupted file or a dropped audit row → `verify_failed`, no hand-over, an incident |
| E-13 | `reset-account`: held fixtures (managed; non-owner subject; tier 3) → 409, data dir byte-identical; `?via=retirement` reaches NOTIFIED first; personal proceeds with the opt-in offer |
| E-14 | Pending deletions all executed before ASSEMBLED, none in the manifest; held subject → `deletion_paused`; the hold never blocks a person's own request |
| E-15 | Halt latch: no 300 s stall, no agent SPEAK, package still produced |
| E-16 | Closing dialogue: skipped and recorded at tier 3; offered at tier 4; window always ends; a REFUSE still retires; never under emergency or halt |
| E-17 | Notices: correct timing per kind; "System notice" CommunicationBus messages, never SPEAK; every locale renders; every consented subject gets a stored notice; public row complete; a disabled notifier blocks RETIRED |
| E-18 | Multi-occurrence race → one order; every occurrence freezes |
| E-19 | Copy lint over the new module, its prompts and its notice templates for the excluded terms (the list lives in the test); existing code identifiers outside the module are exempt |
| E-20 | Secrets: no plaintext or ciphertext left; one metadata tombstone per secret |
| E-21 | Keys retired in place: old signatures verify; new signing refused |
| E-22 | Seal split: memory and experience sealed, identity and audit not; a memory node in clear fails |
| E-23 | DSAR after RETIRED: one subject's approved request releases only their items; without approval, nothing |
| E-24 | Mobile: no off-device target → completes, `no_offsite_target` recorded, export offered |
| E-25 | Chain closure: nothing appended to the agent chain after RETIRED; custody events on the custodian chain |
| E-26 | TEMPORARY: no TEMPORARY content in the package; counted under `temporary_stream`; their notice carries the deletion line |
| E-27 | Content-free audit (P0): sentinel SPEAK and TOOL strings appear nowhere in the audit store; re-adding the raw `context.parameters` dump fails; a registry of audit call sites catches a new content-passing caller |
| E-28 | Custodian key: bound in `retirement.completed`; custody entries verify through the delegation; it cannot unwrap the seal; entries signed by the retired key, an unbound key, or a wrong-scope delegation are refused |

**QA runner:** a new `retirement` module (mock LLM) drives AT-1 to AT-3, E-1, E-4
and E-6 over HTTP, and E-27 joins the existing `audit` module. The AT results are
the evidence rows for `CLM-humane-ending`.

---

## 15. PR plan

| PR | Scope | Size | Tests | Dependency |
|---|---|---|---|---|
| **P0** content-free audit | every `log_action` / `log_event` caller; parameters restricted to ids, hashes, decisions; call-site registry | S-M (~400) | E-27 | none; ships now |
| **P1** stop the bleeding | `runs_for_others()`; reset and wipe 409 on held agents; WA-standing gate; opt-in export on personal; drop the self-erasing audit write; make the wipe reach `<home>/identity/` or say it does not (#1261) | S (~350) | E-13, AT-1 neg. 1 | none; ships now |
| **P2** order, state machine, authz, boot guard, custodian | schemas; shared-task claim; create / get / confirm / cancel; ShutdownProcessor composition; double marker; embedded-safe freeze; custodian mint and binding; chain closure | M-L (~1100) | E-3–E-5, E-8, E-18, E-25, E-28 | the forced-shutdown fix; #1231 |
| **P3** retention hold | one flag across every eraser; registry test | S-M (~400) | E-11 | D2a later |
| **P4** deletions, secrets, keys | step DELETIONS_EXECUTED (incl. TEMPORARY); step SECRETS_DESTROYED; keys retired in place | M (~650) | E-14, E-20, E-21, E-26 | D3 (interim: local row plus refusal) |
| **P5** assemble and verify | SQLite backup, file copy, manifest with `subject_ref`, audit proofs, verify gate | M-L (~1000) | E-1, E-12 | D1 for PG (interim: paged export) |
| **P6** seal and release | the split; `seal_mode`; interim "host-decryptable"; release flow (WA, lawful order, DSAR) | L (~1200) | AT-2, E-9, E-10, E-22, E-23 | D2b-i makes the default real |
| **P7** deletion path into the record | post-retirement route; tombstone by digest; sub-key isolation; packaged tool; hold wait and lift | M (~600) | AT-3 | D2e (interim: per-subject archive files) |
| **P8** hand over and preserve request | package writer per target; signed `PreserveRequest`; operator-response route on the custodian chain | M (~600) | E-6, E-7, E-24 | D5 (interim: local row) |
| **P9** notify | both drafts with the rendering rules; 29 locales; stored notice; public row | M (~700) | E-17, E-19 | D5; native-language audit |
| **P10** closing dialogue | tier ≥ 4 window; never under halt or emergency | S-M (~350) | E-16 | none |
| **P11** evidence | `evidence/cc_impl.tsv` row for `CLM-humane-ending` naming the `retirement_record` symbols, AT-1 to AT-3 as tests, and "seal: interim agent-side gate, host-decryptable; default WA-sealed mode pending CIRISPersist D2b-i" | S | AT-1 to AT-3 | P0, P2–P9 |

About 7.4k LOC including tests and strings. **Order:** P0 and P1 first, in
parallel; then P2 and P3; then P4 → P5 → P6; P7, P8, P9 in parallel after P5; P10
independent; P11 last. **Graduation:** when AT-1 to AT-3 pass on P2–P9 with the
interim seal, labelled in the evidence row.

### 15.1 Upstream asks

None blocks P0–P5; each has an interim. D6 and D7 are needed for production
managed agents and for mobile.

| # | Repo | Ask | Ref |
|---|---|---|---|
| D1 | CIRISPersist | Consistent store snapshot and export (SQLite and PG) with a digest manifest, from Python | overlaps CIRISServer#245 |
| D1b | CIRISPersist | Python binding for `Engine::archive_audit_range` and an audit-chain export with a head proof | CIRISPersist#107 (closed, Rust-only) |
| D2a | CIRISPersist | Typed `legal_hold` (CC 4.4.3.2.8) blocking retention, purge, key destruction, TSDB prune and consent descent | CIRISServer#649 |
| D2b-i | CIRISPersist | Sealed-to-recipients blob scope: key wrapped only to named WA keys, no node wrap (the default seal) | new |
| D2b-ii | CIRISPersist | `emit_key_grant` conditional on a verified basis row, enforced in the fabric | new |
| D2c | CIRISPersist / CIRISVerify | m-of-n key split or threshold unwrap for archive keys | new |
| D2d | CIRISPersist | Rewrap self-cohort blobs to a custodian when occurrences retire | new |
| D2e | CIRISPersist | Per-subject sub-keys in a sealed archive; tombstone by digest without unwrap. Required by the Standard, not an optimisation | relates to CIRISPersist#476 |
| D3 | CIRISPersist / CIRISServer | Key-retirement row distinct from compromise revocation; prior delegations survive it | new |
| D4 | CIRISServer | Ship `escrow_*` in the wheel | CIRISPersist#751/#752 |
| D5 | CIRISConstitution | Namespaces: retirement row, `preserve_request:v1`, `preserve_response:v1`, `archive_release:{basis}:v1`, `lawful_order:{effect}:v1`, `record_tombstone:v1` | CIRISConstitution#168 |
| D6 | CIRISManager | `delete_agent` → retirement → show the `PreserveRequest` → record the response → only then remove; never `down -v` before HANDED_OVER; mount `identity`, with a migration that copies the existing `/app/identity` out first (confirmed missing, §2) | CIRISManager#27 |
| D7 | CIRISClient | Steward retirement flow; operator preserve prompt; notice banner; mobile export | new |
| D8 | CIRISPersist / CIRISServer / CIRISVerify | A custodian identity next to the agent's on one Engine; a `retirement_custody:<id>` delegation scope | new |

---

## 16. Decision log

All rulings are Eric's, given as direct answers on **2026-10-14**. The CC text they
build on landed on CIRISConstitution rc8 at `f5cea2d`.

| # | Question | Decision | Where |
|---|---|---|---|
| N1 | Name of the duty | The **Retirement Standard**; the artefact is the **retirement record**; the workflow is `retirement_record`; verbs assemble / seal / hand over / notify; `CLM-humane-ending` keeps its id | throughout |
| N2 | Scope of the harness's duty | Assemble, seal, hand over with a request, notify. It never guarantees preservation (the weights posture) | §0, §1.1 |
| N3 | Copy vocabulary | Anthropomorphic terms stay out of copy, prompts and ethics text; the optional step is the "closing dialogue"; existing code identifiers stay | §10, E-19 |
| N4 | Retention | `preserve_until` = shutdown + 5 y (CC 7.5.8), a best practice under N5; extended by a hold, the law or a contract; the request is signed and names the period | §8.1 |
| N5 | Escrow | An optional mode with no fixed holder; the default seal needs WA approval or a lawful order | §6.2 |
| 1 | Experience logs | Tasks, thoughts, service correlations (incl. conversations), traces, log files, incidents, deferral tickets | §2, §6.1 |
| 2 | Seal scope | Memory and experience sealed; identity and the audit trail unsealed | §6.1, E-22 |
| 3 | Private signing keys | Retired in place: kept so the record verifies, refused for new acts | §5, E-21 |
| 4 | User secrets | Destroyed, with metadata tombstones | §5, E-20 |
| 5 | Pending consent deletions | All executed at retirement before sealing; a hold pauses them; later requests use §8.2 | §5, §8.2, E-14 |
| 6 | DSAR access | Subject-scoped release on the steward's recorded WA approval; no lawful order needed | §6.3, E-23 |
| 7 | `runs_for_others()` | Managed, a non-owner consent subject, or tier ≥ 3; "non-local adapter" dropped | §3 |
| 8 | Personal reset | Opt-in export or hand-over offer | §12 |
| 9 | Who may retire | Any holder with WA standing (ROOT/AUTHORITY) on this agent | §4, E-8 |
| 10 | Post-retirement events | On the custodian chain; the agent chain closes at RETIRED | §7, E-25 |
| 11 | Halted, then retired | Notice still owed, after the fact | §9, §12 |
| 12 | Closing dialogue | Tier ≥ 4; below that, the labelled harness notice only | §10, E-16 |
| 13 | Advance notice | Both: advance at DECIDED and after hand-over | §9, E-17 |
| 14 | Graduation | `CLM-humane-ending` may graduate on the interim seal, labelled host-decryptable | §6.2, §15 |
| 15 | Mobile | Best effort: retire without an off-device target, offer export, record its absence | §11, E-24 |
| 16 | Live copies | Left in place after verification; the readable live copy is stated plainly | §6.2 |
| 17 | Default seal recipients | The steward plus the seated WA roster | §6.2, E-10 |
| 18 | A non-steward decider | Not added to the seal unless on the roster | §6.2, E-10 |
| 19 | Shared threads | A deletion removes only the person's own messages and data about them | §8.2, AT-3 |
| 20 | TEMPORARY stream | All TEMPORARY content deleted at retirement, never sealed, stated in the notice | §5, §9, E-26 |
| 21 | Audit content | Content-free parameters (ids, hashes, decisions), with a failing test; lands first as P0 | §6.1, P0, E-27 |
| 22 | Custody signer | A custodian key minted at retirement, bound by the agent chain's final entry | §7, D8, E-28 |
| 23 | Notice drafts | The `[decided_by]` rendering and the custodian-chain line | §9 |
| 24 | `reset-account` / `wipe-signing-key` | Route through the workflow or refuse on held agents; WA-standing gate | §12, E-13 |

No questions remain open. The remaining dependencies are the upstream asks (§15.1),
each with an interim, and the two confirmed defects in §2 (#1261, CIRISManager#27).
