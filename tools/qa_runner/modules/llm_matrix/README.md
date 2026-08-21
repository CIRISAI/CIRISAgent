# LLM provider conformance matrix

Exhaustive live testing of the setup wizard's LLM configuration path:
**provider × model × credential × probe**, graded on one question —

> For every way an LLM configuration can be wrong, does CIRIS tell the user
> what is actually wrong?

The space is small and finite (6 providers, 22 catalogued models), so it can be
locked down by sweeping it rather than by hoping.

## Why

A user could not configure an LLM through the wizard. Three defects stacked:

1. With no model chosen, `_validate_openai_compatible` substitutes
   `"gpt-3.5-turbo"` and sends that OpenAI model name to whichever provider the
   user picked.
2. OpenRouter answered `404 "No endpoints available matching your guardrail
   restrictions and data policy"` — a **privacy-settings** problem.
   `_classify_llm_connection_error` substring-matches, misses every pattern,
   and renders *"Could not reach the API endpoint. Please check your
   configuration."* The user goes and checks a network that is working fine.
3. The live model listing failed seven times, logged no exception detail, and
   showed a cached catalogue as though it were current.

The gap between **what the provider said** and **what CIRIS says the provider
said** is the headline output of this module.

## Running it

```bash
# Which of the six keys still work? One minimal call per provider, no grading.
# Run this first whenever credentials may have rotated.
python3 -m tools.qa_runner.modules.llm_matrix --preflight-only

# No network, no keys, no spend. Replays a recorded corpus of real provider
# errors through the product's live classifier. This is the CI gate.
python3 -m tools.qa_runner.modules.llm_matrix --dry-run

# See the expansion and the cost before spending anything.
python3 -m tools.qa_runner.modules.llm_matrix --plan

# Live core sweep, all six providers: ~40 calls at max_tokens=1.
python3 -m tools.qa_runner.modules.llm_matrix --live

# One provider, full detail.
python3 -m tools.qa_runner.modules.llm_matrix --live -p openrouter --verbose

# The expensive axis: every model in MODEL_CAPABILITIES.json.
python3 -m tools.qa_runner.modules.llm_matrix --live --include-catalogue --max-live-calls 200

# Token-generating option probes (max_tokens over a provider cap, and the
# base URL the wizard advertises but does not validate against).
python3 -m tools.qa_runner.modules.llm_matrix --live --include-option-probes

# Re-record the dry-run corpus from live behaviour, for review.
python3 -m tools.qa_runner.modules.llm_matrix --live --update-fixtures
```

Live mode is opt-in. `--dry-run` is the default and `--live` is the only way to
reach the network, so nobody spends money by typing the module name.

`--max-live-calls` refuses the run *before* the first call if the expansion is
larger than the budget. Exit code is 0 (clean), 1 (findings at or above
`--fail-on`, default `critical`), or 2 (run refused).

## Credential liveness

Every live run establishes, per provider, whether the credential works —
**before** anything is graded. A stale key returns the same 401 on every cell in
a column; graded naively that reads as "this provider answers 401 to
everything", which looks like a provider quirk and is nothing of the sort. It
also silently destroys the coverage the run was for, because auth fails before
the request is ever routed to a model.

So a column whose credential is not live is **skipped with a reason, never
failed**, and its cells produce no findings.

| verdict | meaning | what the sweep still runs |
|---|---|---|
| `live` | completed a request | everything |
| `no_credit` | key valid, account out of funds | free cells (`/models`) + synthetic-credential cells |
| `expired_or_revoked` | **re-issue this key** | synthetic-credential cells only |
| `rate_limited` | transient; re-run later | synthetic-credential cells only |
| `other` | reached the provider, failed for an unrelated reason | synthetic-credential cells only |
| `missing` | no key file on disk | synthetic-credential cells only |
| `not_probed` | `--dry-run` contacted nobody | everything, from fixtures |

Cells that inject a **synthetic** key (`invalid`) or **no** key (`absent`) keep
running whatever the verdict — they test the provider and the product, not our
account, so a stale credential of ours costs no coverage there.

`no_credit` is deliberately not `expired_or_revoked`. Re-issuing a key with an
exhausted balance fixes nothing, and the two are genuinely hard to tell apart:
**Together** signals no-credit with HTTP 402, **Anthropic** with HTTP **400** —
the same status **Google** uses for a rejected key. Only the message body
separates them, so `preflight.py` matches on the message first and the status
second. `report.keys_needing_reprovisioning()` returns only the keys where
issuing a new one is actually the fix.

The probe is the baseline cell the sweep was going to run anyway (one
completion, `max_tokens=1`), so liveness costs nothing extra — and gating saves
far more than it spends: on 2026-08-21 it cut a full sweep from 45 calls to 31
by not re-observing the same dead-key 401 fourteen times.

Not the `/models` listing, even though listing is free: listing only proves the
credential is *accepted*. Both Anthropic and Together were observed serving a
full model list on an account whose completions endpoint refused for lack of
credit.

## Keys

Read from `~/.openai_key`, `~/.anthropic_key`, `~/.google_key`,
`~/.openrouter_key`, `~/.together_key`, `~/.groq_key` — raw token, no quotes,
no trailing newline. A provider whose key file is missing has its cells
skipped, not failed.

Values are registered with `redaction.Redactor` and masked at **capture time**,
before anything reaches an `LLMProbeOutcome`. There is no code path that can
put key material into the report, the console, or a fixture. A test asserts the
committed corpus is clean, and another asserts the generated report is.

## The axes

| Axis | Values | Where |
|---|---|---|
| provider | openai, anthropic, openrouter, together, groq, google | `dimensions.PROVIDERS` |
| model | catalogue, cheap, **omitted**, nonexistent, wrong_case, gated, policy_blocked | `schemas.ModelSelector` |
| credential | valid, invalid, absent, malformed | `schemas.CredentialMode` |
| probe | chat_minimal, chat_max_tokens_over_cap, chat_alt_base_url, models_list, static_audit | `schemas.ProbeKind` |

Dimensions are **data**. Adding a provider, an injection, or a quirk to hunt is
an edit to `dimensions.py` and nowhere else. The catalogue axis is read at
runtime from `MODEL_CAPABILITIES.json`, so the sweep always covers exactly what
the wizard offers.

## What each cell records

* the provider's **HTTP status**, **typed SDK exception class**, and **raw error
  body** — the truth;
* what the product's **own** `_classify_llm_connection_error` turns that into —
  the rendering;
* the **gap** between the two, graded against the cell's `ExpectedCause`, which
  is known a priori from the injection.

The classifier is imported and called, never reimplemented. `RenderedCause` is
derived from `LLMValidationResponse.message` (unique per branch) rather than by
re-deriving the predicate chain, so the harness cannot drift out of sync when
the product reorders its branches.

## Design notes

**`product_bridge.py` is the only import seam into `ciris_engine`.** When
`llm_validation.py` is refactored, exactly one file needs updating, and
`bridge_status()` reports what the harness actually bound to.

**The probes use the same SDKs the wizard uses** (`AsyncOpenAI`,
`anthropic.AsyncAnthropic`). A hand-rolled `httpx` probe would produce a
different `str(exception)` and the report would describe a bug that does not
exist.

**`--dry-run` is not a smoke test.** It replays verbatim recordings of real
provider errors through the *live* classifier, so a refactor that changes which
branch an OpenRouter data-policy 404 lands in is caught in CI with no key and
no spend.

**The static table audit needs nothing at all** — it runs in every mode and
finds contradictions between the product's own tables (wizard provider list vs
`MODEL_CAPABILITIES.json` vs `_PROVIDER_BASE_URLS` vs the hardcoded fallback
models).

**A failed baseline invalidates its column,** so the preflight runs first and
the report leads with the credential table. Every number below it is
conditional on it, and a reader who skips it will misread a stale key as a
defect.

**The fixture corpus curates itself.** Skipped cells are never recorded, so a
sweep run against a dead key simply produces a smaller corpus rather than
freezing an account's billing state into a permanent CI finding.

## Files

| File | Purpose |
|---|---|
| `dimensions.py` | the axes, as data |
| `schemas.py` | typed cells, outcomes, findings, report |
| `product_bridge.py` | the only import seam into `ciris_engine` |
| `probes.py` | the only code that touches the network |
| `analysis.py` | finding detection + static table audit |
| `matrix.py` | expansion and execution |
| `report.py` | console + JSON rendering |
| `preflight.py` | credential liveness + the re-provisioning verdict |
| `fixtures.py` / `fixtures.json` | recorded provider behaviour for `--dry-run` |
| `__main__.py` | CLI |
| `../llm_matrix_tests.py` | QA-runner module adapter (see its docstring to register it) |

Tests: `tests/tools/qa_runner/modules/test_llm_matrix.py` — no keys required.
