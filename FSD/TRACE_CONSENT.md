# Trace Consent — the `consent:community_trust:v1` CEG object end-to-end

**Status:** 2.9.7. Owner: agent + client. Related: `FSD/FIRST_RUN_STATECHART.md`,
`FSD/TRACE_EVENT_LOG_PERSISTENCE.md`, `FSD/TRACE_WIRE_FORMAT.md`.

This is the one-stop map + troubleshooting recipe for "did the user opt in to
sending reasoning traces, and are traces actually sealing?"

---

## 1. The happy CEG object

Trace consent is a CEG attestation, not a config flag (the 2.9.6 LensCore fold —
`ciris_engine/logic/services/governance/consent/attestation.py`). One row:

| field | value |
|---|---|
| `dimension` | `consent:community_trust:v1` |
| `attestation_type` | `scores` (grant) — revoke writes `withdraws`/`recants`/`supersedes` |
| `attestation_envelope.claim.stream` | `community_trust` |
| `attestation_envelope.claim.categories` | `["accord_traces"]` |
| `attestation_envelope.claim.state` | `active` |
| `attestation_envelope.score` | `1.0` |
| `subject_key_ids` | `[<canonical community key>]` (directed) or `[]` (interim, unpublished) |
| `cohort_scope` | `self` |
| `tier` | `federation` once promoted (directed) / `local` (interim) |
| `attesting_key_id` | the agent's federation signer (Edge `get_federation_address()`) |

There is no "observer/lens_core" role literal — the *role vocabulary* is
`stream=community_trust` + `categories=[accord_traces]`, directed at the
**canonical CIRIS community** (`ciris-canonical-1-*`, genesis-baked by persist
v13.4.0+). Built by `build_community_consent_grant()`; emitted by
`emit_community_consent_grant()`.

## 2. The three write paths (all produce the SAME object)

- **Path A — first-run wizard.** Client toggle `accordMetricsConsent`
  (AnnounceDecisionCard `toggle_trace_opt_in` → `SetupViewModel`) puts
  `ciris_accord_metrics` into `enabled_adapters`; `completeSetup`
  (`routes/setup/complete.py::_emit_accord_metrics_consent`) calls
  `emit_community_consent_grant()`.
- **Path B — settings, post-config.** Data & Privacy → **Send traces** card
  (`ManageConsentScreen.SendTracesCard`) → `DataManagementViewModel.updateAccordConsent`
  → `PUT /v1/my-data/accord-settings` → `adapter.update_consent()` **and**
  `emit_community_consent_grant()`. This is the *alternative view of the same
  object*; it re-arms the running adapter directly.
- **Path C — legacy migration.** `CIRIS_ACCORD_METRICS_CONSENT` env / adapter
  config `consent_given` → `AccordMetricsAdapter.start()` emits the grant
  carrying the original timestamp, then purges the legacy sources.

## 3. The seal gate (why traces do / don't persist)

The agent runs the **cohabitation** LensClient path (`engine=` passed —
`ciris_adapters/ciris_accord_metrics/services.py::_build_lens_client`). In that
path lens-core gates each `ACTION_RESULT` seal on the **config-fallback
consent** (`_consent_given` + `_consent_timestamp`), NOT a live per-seal CEG read
(that's the unwired CIRISEdge#85 follow-up). So the grant must be *translated*
into that fallback. As of 2.9.7 `AccordMetricsService` derives it from the CEG
grant — the source of truth — in two places:

1. `start()` → `_derive_consent_from_ceg()` **before** building the LensClient
   (clean restart, or any boot where the grant already exists).
2. `_process_single_event()` → `_maybe_self_heal_consent()` (throttled) while
   consent is OFF — arms **without a restart** when the grant lands after boot.
   This is the fix for the mobile first-run case: Chaquopy keeps ONE Python
   process across the Android UI "restart", so the boot-time derivation never
   re-runs and nothing else re-armed the already-built LensClient.

Capture is unconditional; only the **seal** is consent-gated. Events with no
`ACTION_RESULT` are ephemeral by design.

---

## 4. Validation recipe — "is trace consent healthy?" in < 1 min

Three checks. (a) the log, (b) the DB, (c) the HTTP endpoint.

### (a) The log one-liner

Every boot prints exactly one `[CONSENT]` line (rides logcat → mobile
pull-logs). Per-seal lines are `[SEAL]`.

```bash
# Mobile: pull logs first
python3 -m tools.qa_runner.modules.mobile pull-logs
# Then, in the newest bundle:
grep -h "\[CONSENT\]" mobile_qa_reports/*/logs/latest.log | tail -3
grep -h "\[SEAL\]"    mobile_qa_reports/*/logs/latest.log | tail -5
```

- Healthy: `[CONSENT] trace consent ARMED — source=ceg:grant <id> ... → traces WILL seal`
  and `[SEAL] sealed thought=<id> trace_id=<id> ...`.
- Unhealthy: `[CONSENT] trace consent ABSENT — traces will NOT seal (checked: ceg=none config=... env=...)`
  and, per decision, `[SEAL] SKIPPED thought=<id> reason=no-consent`.
- Recovered-at-runtime: `[CONSENT] trace consent SELF-ARMED at runtime — ...`
  followed by `[CONSENT] LensClient rebuilt — seals now persist`.

Client side, the write is traceable in `logcat_app.txt`:
`grep "\[ORDER\] trace_consent" mobile_qa_reports/*/logcat_app.txt`.

### (b) The DB (device / node `ciris_engine.db`)

```bash
DB=mobile_qa_reports/<ts>/databases/ciris_engine.db   # or the live node's DB

# 1) The consent object exists, directed, promoted:
sqlite3 -json "$DB" "SELECT attestation_type, tier, cohort_scope, subject_key_ids, promoted_at
  FROM federation_attestations WHERE dimension='consent:community_trust:v1'
  ORDER BY asserted_at DESC LIMIT 1;"
#   expect: attestation_type=scores, subject_key_ids=[\"ciris-canonical-1-…\"] (directed)

# 2) Traces are actually sealing after a chat:
sqlite3 "$DB" "SELECT count(*) FROM trace_events;"     # expect > 0 after ≥1 SPEAK
```

The failure signature the 2.9.7 fix closes: **grant row present but
`trace_events = 0`** — the seal never armed.

### (c) The HTTP check (live node, :4243 / server :8080)

```bash
TOKEN=$(curl -s -X POST http://localhost:4243/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"qauser","password":"qa_test_password_12345"}' \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['access_token'])")

curl -s http://localhost:4243/v1/my-data/accord-settings \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
#   expect: consent_given=true, trace_level set, events_sent climbing
```

(Mobile forwards the node: `adb -s emulator-5554 forward tcp:14243 tcp:4243`,
then use `http://localhost:14243`.)
