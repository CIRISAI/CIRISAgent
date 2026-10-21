# CIRIS Logging Standard

**Status:** normative for CIRISAgent; proposed for the substrate crates
(ciris-server, ciris-persist, ciris-edge, ciris-verify, ciris-lens-core).

**Why this exists.** A user reported that his agent did not work. His
`latest.log` covered 3m40s of runtime in **3,810 lines**. The fault was in
there — `HTTP 401 Invalid API Key`, thirteen times — under a thousand lines of
near-identical XML and thousands of lines reporting that routine things had
happened routinely. He was told to check his network. He spent a day on it, and
so did the people helping him.

That log met every reasonable definition of "we have logging". It was still
unusable, because volume is not evidence. This document is the rule set that
would have made that log answer the question on sight.

---

## 0. The one-line test

> **If this line fires 500 times in a healthy run, it is not INFO.**

Everything below follows from that.

---

## 1. Levels mean things

Adapted from the syslog severities (RFC 5424 §6.2.1) and the conventions
`tracing` documents for its five levels. The mapping we use:

| level | means | rule of thumb |
|---|---|---|
| `ERROR` | something failed and a person may need to act | always includes what failed, where, and what the failing component said |
| `WARN` | degraded, fell back, or refused — still running | a fallback is a WARN; taking the fallback successfully is not an ERROR |
| `INFO` | **gross activity, changes, and errors** — state transitions a person would narrate | boot, shutdown, config change, service started, provider registered |
| `DEBUG` | per-request and per-loop detail | anything proportional to traffic |
| `TRACE` | inner-loop detail | rarely on outside a targeted investigation |

**INFO is not "important". INFO is "a person would mention this".** Nobody
narrating an agent's day says "and then it listed the adapters, and then it
listed the adapters, and then it listed the adapters".

### 1.1 Do not put routine progress on the failure channels

An operator's first move on a broken agent is:

```
grep -E 'WARNING|ERROR' latest.log
```

Anything routine on those channels destroys that command. In the reported log,
**19 normal startup messages were emitted at WARNING** — 20% of every WARNING in
the file — reading `[SERVICE 3/11] MemoryService STARTED`. Fixed in
`ciris_engine/logic/runtime/startup_logging.py`.

---

## 2. One event, one line

**A log record must be one line.** Every tool that reads logs works
line-at-a-time: `grep`, `tail`, `journalctl`, the incident capture, a console a
human is watching.

A multi-line record is not "more informative" — it is *less*, because every
line-oriented view shows only its first line and silently discards the rest.
Observed exactly:

```
llm_service.service - ERROR - LLM UNEXPECTED ERROR - InstructorRetryException.
llm_service.service - ERROR - LLM UNEXPECTED ERROR - InstructorRetryException.
llm_service.service - ERROR - LLM UNEXPECTED ERROR - InstructorRetryException.
```

The model, the provider and the provider's own message were all present — on
continuation lines nobody saw. Fixed in
`ciris_engine/logic/services/runtime/llm_service/service.py`; the same record is
now:

```
LLM CALL FAILED (InstructorRetryException) model=gpt-4o-mini
  provider=https://api.groq.com/openai/v1 schema=EthicalDMAResult
  | provider said: HTTP 401 Invalid API Key
```

(shown wrapped here; emitted as one line.)

### 2.1 Flatten and bound at the emitting site

Any interpolated value may contain newlines. Collapse and truncate where it
enters the message, not where you hope someone will read it:

```python
flat = " ".join(str(error).split())[:300]
```

In `ciris_engine/logic/services/base_service.py` this single change took a
generic error hook from ~325 physical lines to ~13, and because the hook is
shared it protects **every** service from the same blow-up.

### 2.2 Tracebacks are not explanations

`exc_info=True` on an expected, classified failure costs ~38 lines and adds
nothing that `HTTP 401 Invalid API Key` does not already say. Reserve it for
genuinely unexpected exceptions.

---

## 3. Say what the component said

When wrapping a failure from another system, report **its** words, not your
wrapper's class name. `InstructorRetryException` names our library; `Invalid API
Key` names the problem.

Where a wrapper hides the cause, dig it out — see `_root_provider_error()` in
`llm_service/service.py`, which walks `__cause__`/`__context__` for the
provider's own status and message.

**Corollary for user-facing messages.** `/v1/system/health` used to say *"All
LLM providers are currently unavailable. Check your provider settings or network
connection."* The user's actual faults were a revoked key on one provider and a
non-existent model on the other. Neither is a network problem, and the two need
opposite fixes.

---

## 4. Repetition is a bug, not a volume problem

If a line repeats, the interesting fact is the *count*, not the *instances*.

- **Identical consecutive records** are collapsed by
  `ciris_engine/logic/utils/log_dedup.py` into `… [repeated N more times]`. The
  first occurrence always emits unchanged and the count is always reported, so
  no failure is hidden.
- **Answers that cannot change** are logged once. `first_run.py` emitted 5 INFO
  lines on each of 66 calls — 330 lines, 12% of the file — restating a decision
  that cannot change without a restart. It now logs its full reasoning at INFO
  once and at DEBUG thereafter.
- **Do not collapse by message shape.** It is tempting (79% reduction in the
  reported log) and wrong: it merges `channel: A` with `channel: B` and destroys
  a real distinction. Under-collapsing is recoverable; over-collapsing loses
  evidence.

---

## 5. What must never be logged

- **Credentials in any form.** A PostgreSQL DSN contains the database password;
  `postgresql://user:password@host/db` reached stdout and the log file on every
  boot (GHSA-jghc-9g86-xg7c). Redact at the emitting site —
  `_redact_dsn()` in `ciris_engine/logic/persistence/db/core.py` — and enforce
  it with a test, not a convention: see
  `tests/ciris_engine/logic/persistence/test_dsn_is_never_logged_raw.py`, which
  reads the AST rather than grepping.
- API keys, bearer tokens, PINs, private key material, and personal data.

---

## 6. What must always survive

This standard exists to make failures **more** visible, never less. Nothing here
authorises removing or demoting:

- any failure, refusal, fallback, or degraded-state report;
- state transitions (circuit breaker opened/closed, provider admitted/refused);
- the one-shot notice that a capability is unavailable or unconfigured;
- anything that names *why* a request did not succeed.

When a diagnostic line is noisy, make it **denser** — one line, more facts —
rather than removing it.

---

## 7. Asks for the substrate

The substrate crates emit through Rust `tracing`. Per
`ciris_engine/logic/utils/substrate_logging.py`, those events reach stdout via
`init_tracing()` and **do not pass through Python `logging`**, so none of the
above can be applied from the host: the agent cannot re-level, deduplicate, or
flatten a substrate line.

Requested, in priority order:

1. **§2 — one event, one line.** Audit multi-line `tracing` events; flatten
   interpolated values at the emitting site.
2. **§1 — level discipline.** Per-request and per-loop events at `DEBUG`/`TRACE`;
   reserve `INFO` for state changes. The host default filter is
   `warn,ciris_persist=info,ciris_server=info,ciris_edge=info`, so anything at
   `info` in those crates is on by default for every user.
3. **§4 — repeat collapsing** in the subscriber, equivalent to `log_dedup`.
4. **§5 — credential redaction** at the emitting site, with a test.
5. **A stable event vocabulary.** Structured fields (`tracing`'s native model)
   rather than message-only records, so counting and filtering do not require
   regex over prose.

---

## 8. References

- RFC 5424 §6.2.1 — syslog severity levels
- `tracing` level semantics (`ERROR` … `TRACE`)
- OpenTelemetry logs data model — severity and structured attributes
- `ciris_engine/logic/utils/log_dedup.py` — repeat collapsing
- `ciris_engine/logic/utils/logging_config.py` — handler setup
- `ciris_engine/logic/utils/substrate_logging.py` — the Rust/Python boundary
- `tests/ciris_engine/logic/persistence/test_dsn_is_never_logged_raw.py` — §5 enforcement
