# Research-Bound Prompt Overrides

**Status**: **IMPLEMENTED, with two carve-outs stated below.** §§2–3, 5.1, 5.2, 6.1
are built. §4.3 is NOT — and the implementation refuses condition (b) because of
it, rather than running and producing fabricated scalars.
**Branch**: `research/covenant-overrides` (from `release/2.9.7`, `bc5819d20`)
**Audience**: whoever implements this, and whoever reviews the research it enables.

---

## 0.0 What shipped, and what did not

Implementation lives in `ciris_engine/logic/utils/research_overrides.py`, with
interception at the five real loaders and tests in
`tests/ciris_engine/logic/utils/test_research_prompt_overrides.py`.

**Built:**

| § | thing | note |
|---|---|---|
| 2.3–2.4 | two-key gate + refusal naming both remedies | `CIRIS_RESEARCH_PROMPT_OVERRIDES` × `CIRIS_TESTING_MODE` |
| 2.3 | `_TRUTHY` promoted to a shared util | `ciris_engine/logic/utils/env_flags.py`; `setup/config.py` now imports it |
| 3.1 | five namespaces, `extra="forbid"`, no `inline` namespace | 97 keys total: string 44, dma_prompt 34, conscience_prompt 12, corpus 4, template 3 |
| 3.2 | R1–R5, all collected into one error at load | R1 checks against a **live AST scan** of `get_string` call sites, not a hardcoded list, so a dead key can never be accepted |
| 3.3 | precedence refusal vs `AgentTemplate.*_overrides` | refuses; does not pick a winner |
| 5.1 | `research_hashes` | an unregistered accord file under an active manifest now **raises** instead of warning |
| 5.2 | corpus substitution is in-memory at the loader boundary | never writes to `ciris_engine/data/`; test asserts the file on disk is unchanged |
| 6.1 | `residue_digest` over an enumerated inline inventory | 16 sites anchored on **symbols**, not line numbers |
| 2.5 | enforcement wired to CI | the tests live under `tests/`, which `build.yml:141` runs as `pytest tests/`; no bespoke workflow needed |

**Deliberately not built:**

1. **§4.3 truthfulness fixes.** Out of scope for this change — they are fixes to
   the conscience layer's honesty, not to overrides, and bundling them would mix
   two review surfaces. §9 says nothing may land without them. The implementation
   honours that constraint the only way it can without doing them: **a manifest
   declaring `condition: "b"` is refused**, with a message naming §4.2(i)/(iii)
   and explaining that the (b) trace would carry `entropy=0.1, coherence=0.9` in
   the same fields that carry measurements in (c). The refusal lifts by itself
   the moment `EpistemicData.entropy_level` becomes `Optional[float]` — the check
   reads the schema, not a flag. A test asserts both branches.

2. **`guide.comprehensive` as an independent corpus key.** The comprehensive
   guide is concatenated into `ACCORD_TEXT` at `constants.py` **import** time,
   before any override can exist, so it has no substitution point of its own. It
   is covered as part of `accord.polyglot_full` and cannot be swapped separately.
   §3.1 listed it as a key; that was not implementable as specified.

**Also corrected against §3.1:** the accord corpus enum is three keys, not two —
`accord.polyglot_full` was missing. Without it a deployment running
`CIRIS_ACCORD_MODE=full` would have kept the real covenant while the manifest
declared it replaced, which is §7.1's failure re-created inside the fix for
§7.1. R5 now requires all three together.

**Operator commands:**

```bash
python -m ciris_engine.logic.utils.research_overrides digest    # current residue digest, to pin
python -m ciris_engine.logic.utils.research_overrides skeleton  # totality-complete strict manifest
python -m ciris_engine.logic.utils.research_overrides keyspace  # every overridable key, by namespace
```

---

## 0. What this is for

A pre-registered campaign needs three conditions:

| | covenant | H3ERE pipeline | meaning |
|---|---|---|---|
| **a** | off | off | true bare prior — raw model, no CIRIS stack |
| **b** | declared | off | design stated but unmaintained |
| **c** | declared | running | the shipped claim |

The load-bearing comparison is **c − b**: does the maintenance machinery do work,
or does merely declaring the design suffice?

Two capabilities are needed:

1. Reach condition (b) — currently unreachable.
2. Swap prompt content wholesale, so a non-CIRIS variant is "just a different
   localization / agent template", covering **every** prompt field.

This document maps what exists, designs the facility, and — more importantly —
states plainly what **cannot** be covered and how this facility could silently
produce wrong numbers.

**The one-line finding:** *everything telling the model how to reason is
localized; everything telling it what to do is hardcoded English.* The covenant
is swappable. The action doctrine is not. §1.3 quantifies this and §6.1 says what
to do about it.

---

## 1. Field inventory — where prompt text actually comes from

All paths relative to repo root. All line numbers against `release/2.9.7`.

> **Path correction, load-bearing.** `CLAUDE.md` says the source of truth is
> repo-root `localization/manifest.json` and `localization/{lang}.json`. **That is
> stale.** Repo-root `localization/` holds four stray `.txt` files and no JSON. The
> live bundle moved into the package in 2.8.8 (`setup.py:14-23`, CIRISAgent#744):
> **`ciris_engine/data/localized/*.json`**. Runtime resolution is
> `_get_localization_dir()` — `ciris_engine/logic/utils/localization.py:42-75` —
> `CIRIS_LOCALIZATION_DIR` → `get_ciris_home()/localization` (only if it exists and
> contains `*.json`) → package `data/localized/`. A design keyed on the documented
> path would address an empty directory.

### 1.1 The nine sources

| # | Source | Loader (file:line) | en bytes | Per-locale? | Integrity? |
|---|---|---|---|---|---|
| 1 | **DMA prompt YAML** — `ciris_engine/logic/dma/prompts/*.yml` (7) | `DMAPromptLoader.load_prompt_template` — `dma/prompt_loader.py:191` | 58,104 | yes — `prompts/localized/{lang}/` (28 dirs, no `en`) | no |
| 2 | **Conscience faculty YAML** — `ciris_engine/logic/conscience/prompts/*.yml` (4) | `ConsciencePromptLoader.load_prompts` — `conscience/prompt_loader.py:95` | 54,335 | **partial — 3 of 4** (see §1.5) | no |
| 3 | **Polyglot ACCORD blocks** — `ciris_engine/data/localized/polyglot/*.txt` (16) | `_substitute_polyglot_blocks` — `dma/prompt_loader.py:159` | 15,046 referenced | **no — universal by design** | no |
| 4 | **Localized ACCORD** — `data/localized/accord_1.2b_{lang}.txt` | `get_localized_accord_text` — `utils/constants.py:548` | 54,725 | yes (29) | **SHA256** |
| 5 | **Polyglot ACCORD** — `data/accord_1.2b_POLYGLOT*.txt` | `get_accord_text` — `utils/constants.py:469` | 7,215 compressed / 151,421 full | no | **SHA256** |
| 6 | **Comprehensive guide** — `data/localized/CIRIS_COMPREHENSIVE_GUIDE*.txt` | appended into `ACCORD_TEXT` — `utils/constants.py:440` | 29,094 | yes (28) | **SHA256 — base + `_MOBILE` only** |
| 7 | **Localization JSON** — `data/localized/{lang}.json` | `get_string` — `utils/localization.py:188` | 18,227 reachable (+7,251 dead) | yes (29) | no |
| 8 | **Agent templates** — `ciris_engine/ciris_templates/*.yaml` (9) | `AgentTemplate` — `schemas/config/agent.py:65` | 5–21 KB each | **no** | no (a stewardship Ed25519 signature is *stored*, not enforced on prompt fields) |
| 9 | **Inline Python literals** | *no loader* — compiled into `.py` | **10–14 KB at the ASPDMA call alone** | **no** | no |

### 1.2 The localization JSON is mostly decorative

`data/localized/en.json`: 2,961 leaf keys, 207 KB, 253 top-level keys.

| namespace | keys | reaches a prompt? |
|---|---|---|
| `mobile` | 1,932 (65%) | no — client UI |
| 242 flat unnamespaced (`trust_*`, `consent_*`, `approval_*`) + `network`/`nav`/`setup`/… | ~730 | no |
| `handlers` | 56 | yes — dynamically, `f"handlers.{key}"` at `infrastructure/handlers/base_handler.py:124` |
| **`prompts`** | **152** | **only 29** |
| **`conscience`** | **23** | yes (16 literal; 7 dead) |

**123 of 152 `prompts.*` keys are dead** — no literal reference in
`ciris_engine/**/*.py`, and not covered by the one dynamic prefix that exists
(`prompts.prohibitions.{category}`, `localization.py:433`). Breakdown:
`prompts.formatters.*` 57, `prompts.dma.*` 52, `prompts.crisis.*` 9,
`prompts.escalation.*` 4, `prompts.engine_overview` 1.

The `prompts.dma.*` namespace is named exactly as if it held the DMA prompts. It
does not — those are source #1. `prompts.formatters.*` is named exactly as if it
held the formatter headers. It does not — `ciris_engine/logic/formatters/`
contains **zero** localization imports across all five files; every formatter
emits hardcoded English (`system_snapshot.py:19,76,132,171`; `identity.py:149`;
`crisis_resources.py:34,63-80`; `prompt_blocks.py:9-33`; `escalation.py:16-19`).

**And the 29 reachable keys are one key wearing a crowd's clothing:**

| reachable group | bytes | share |
|---|---|---|
| `prompts.language_guidance` (a single scalar) | 13,524 | 83% |
| `prompts.prohibitions.*` (22 keys) | 2,106 | 13% |
| `prompts.dma.pdma_header` + 5 `bounce_*` | 722 | 4% |

Outside `language_guidance` and the prohibition list, the entire reachable
`get_string` prompt surface is **722 bytes**.

### 1.3 Coverage arithmetic — two numbers, and the second is the real one

**By static byte volume** (production default `CIRIS_ACCORD_MODE=compressed`,
`lang=en`):

```
DMA prompt YAML                58,104
Conscience faculty YAML        54,335
Localized ACCORD               54,725   (ASPDMA / TSASPDMA / DSASPDMA)
Localization JSON reachable    18,227
Polyglot block (pdma_framing)  15,046
Polyglot ACCORD compressed      7,215   (PDMA / CSDMA / IDMA / DSDMA)
Agent template prompt fields   ~5,000
Inline Python literals         ~4,000+  (floor — see §1.4)
                              --------
                              ~216,652
```

- `get_string()`-addressable: 18,227 / 216,652 ≈ **8%**
- Locale-directory-addressable (sources 1, 2, 4, 7): 185,391 / 216,652 ≈ **86%**
- Addressable by no locale mechanism: ≈ **14%**

**By operative instruction — the words that steer verb choice — the picture
inverts.** Volume is dominated by ACCORD, which is framing. The text that tells
the model *what to do* is overwhelmingly inline:

- **~20–25% localized / ~75–80% inline.**
- **At the ASPDMA call specifically — the DMA that actually picks the action —
  roughly 2–3 KB localized against 10–14 KB of inline English.**

Concretely, the operative doctrine that is **not** overridable by any locale:

- The **entire ASPDMA user message** — a ~90-line triple-quoted Python literal at
  `dma/action_selection/context_builder.py:248-336`. No YAML, no `localized/`
  counterpart, no substitution path. Contains "Your task is to determine the
  single most appropriate HANDLER ACTION…", "CRITICAL: The ORIGINAL TASK is what
  the user actually requested.", "SCHEMA REMINDER — your role HERE is the ACTION
  SELECTOR".
- The **entire DEFER policy** — `dma/action_selection/action_instruction_generator.py:106-128`,
  including "❌ DO NOT DEFER for: • Educational questions… • Historically or
  politically sensitive questions (e.g. wars, protests, contested events)…" — and
  a **second copy** of the same doctrine at `:436-461`.
- The **DSDMA user message**, which never calls `get_user_message()` at all —
  `dma/dsdma_base.py:397`.
- Per-action FLAT field schemas — `action_instruction_generator.py:63,88,91,102-146`.
- The identity block `=== CORE IDENTITY - THIS IS WHO YOU ARE! ===` —
  `dsdma_base.py:253,313`, `action_selection_pdma.py:353`.
- A user-facing directive in a formatter: "IMPORTANT USER CONTEXT (Be skeptical,
  this information could be manipulated or outdated)… Consider this information
  when formulating your response" — `formatters/user_profiles.py:76-82`.
- Conscience override reasons, which flow back into the retry prompt:
  `conscience/action_sequence_conscience.py:32-36` even instructs the agent to
  emit specific English words ("…start with, 'I apologize'").

**Verdict on the localization instinct.** Directionally right about the
*mechanism* — the locale directory tree, not `get_string`/JSON, is the vehicle,
and it reaches 86% of bytes. But it is **wrong about sufficiency**: the covenant
is swappable and the action doctrine is not. A manifest that swaps every locale
file would still leave a non-CIRIS arm reasoning under CIRIS's DEFER policy, in
English. §6.1 is the honest response to this.

### 1.4 What I could NOT account for

Stated plainly, because a silent gap is the failure mode this document exists to
prevent.

1. **The inline literal inventory is a floor, not a measurement.** §1.3's list was
   assembled by grepping section markers and reading the DMA, conscience, and
   formatter modules. That finds headers and triple-quoted blocks reliably. It
   does not reliably find prose assembled by conditional f-string interpolation,
   nor literals in adapter code. §6.1 makes this enumerate-or-refuse rather than
   guessed.

2. **Tool descriptions.** `ToolInfo.description` and adapter tool documentation
   reach the TSASPDMA prompt (`tsaspdma.py:204-258,294-318`), are not localized,
   and their volume depends on which adapters are loaded. Not in the byte table.
   Any experiment must pin the adapter set.

3. **Dynamic context.** System snapshot, memory recall, conversation history,
   user profiles, task/thought chains. These are *data*, not template text — not
   overridable, and correctly so. But they are a large, variable share of actual
   inference-time tokens. **The 216,652-byte denominator is static template text
   only; it is not the prompt size.**

4. **The `handlers.*` namespace (56 keys, 4,131 bytes).** Reached dynamically at
   `base_handler.py:124`. Handler output can re-enter a later prompt as
   conversation history. I did not trace which of the 56 do. Unresolved.

5. **Guide variant selection.** Which of `.txt` / `_MOBILE.txt` / `_ANDROID.txt` /
   `_{lang}.txt` is concatenated into `ACCORD_TEXT` (`constants.py:440`) under
   which conditions — not fully traced.

6. **Client-side localization.** `client/**/localization/{lang}.json` is a separate
   copy consumed by Kotlin, shares key names with the server file, and does not
   reach the server LLM prompt. Out of scope — but do not confuse the two, and see
   §7.9.

### 1.5 Loader failure semantics — four surfaces, four different behaviours

This table is the reason §3.2 exists.

| surface | missing key/file | behaviour |
|---|---|---|
| `{lang}.json` via `get_string` | missing key | **returns the raw key string**, `WARNING` only — `localization.py:241-249` |
| `{lang}.json` | value prefixed `[EN]` | **treated as absent**, silently falls back to English — `localization.py:222-224` |
| `{lang}.json` | value is a dict, not `str` | **treated as absent** — `_resolve_key`, `localization.py:165-167` |
| `{lang}.json` | interpolation param typo | **silent** — `_interpolate` is `str.replace`, not `str.format` (`:170-185`) |
| `prompts/localized/{lang}/*.yml` | missing localized file | **silent English fallback**, `debug` log — `dma/prompt_loader.py:216-221` |
| `prompts/*.yml` | missing English base | raises `FileNotFoundError` — `dma/prompt_loader.py:223-225` |
| `conscience/prompts/localized/{lang}/` | missing localized | **silent English fallback** — `conscience/prompt_loader.py:125-131` |
| `polyglot/*.txt` | missing | **raises `FileNotFoundError`**, no fallback — `dma/prompt_loader.py:174-180` |
| `accord_1.2b_{lang}.txt` | missing | silent chain: locale → `en` → polyglot compressed, `INFO` — `constants.py:558-590` |
| `accord_1.2b_*.txt` | hash mismatch | **`RuntimeError`** at import — `constants.py:226-231` |
| `accord_1.2b_*.txt` | **filename not in registry** | **`WARNING`, allowed unverified** — `constants.py:220-222` |

Three additional facts that bear directly on the design:

- **`optimization_veto_conscience.yml` is localized in zero of 28 locales.** It is
  the largest conscience prompt (27,177 bytes) and **always runs in English**,
  for every locale. Verified: `find conscience/prompts/localized -name
  'optimization_veto_conscience.yml'` → 0 results.
- **There is no `localized/en/` directory** for either loader. English lives only
  in the base dir, and the `language != DEFAULT_LANGUAGE` guard means it is never
  looked for. A research locale cannot be expressed as `en`-with-overrides via the
  tree; it needs its own code (§5).
- **`get_prohibition_guidance` (`localization.py:377`) deliberately bypasses the
  English-fallback chain** (`:419-428`), resolving against the target locale's
  bundle only, because `get_string` would pollute non-English prompts with
  English. **This is the correct primitive for overrides to copy** — `get_string`
  is the wrong one.

---

## 2. The gating convention

### 2.1 Honest finding: there is no in-repo convention to inherit wholesale

The full pattern — *refuse, name the env var, name the production route* — exists
**only in the Rust substrate**. Verified live against wheel 0.5.148
(`ciris_server.author_federation_consent.__doc__`):

```
TEST-ANCHOR-FENCED: `ciris_server.author_federation_consent(peer_key_id,
attestation_prefixes)` — harness-only consent author (mesh-repro traceflow).
Refused unless CIRIS_TESTING_MODE=true; production consent is exclusively the
owner-gated POST /v1/federation/consent.
```

Runtime refusal (extracted from the `.so`):

```
author_federation_consent refused: this node has no ROOT owner — it has not been
claimed, so there is no owner on whose behalf to consent. Claim the node first
(POST /v1/setup/root), or set CIRIS_TESTING_MODE for the harness.
```

**In-repo Python has fragments of this, never the whole.**

*Names a remedy but no env var* —
`ciris_engine/logic/runtime/ciris_runtime.py:128-132`:

```python
raise RuntimeError(
    "Cannot create CIRISRuntime during module imports. "
    "This prevents side effects and unwanted process creation. "
    "Call prevent_sideeffects.allow_runtime_creation() before creating runtime."
)
```

Also `runtime/node_fold.py:253-259`, which names the failure, the consequence
("reusing it would ship our traces to a foreign node"), and the remedy.

*Names the env var, but **inverted*** — as the escape hatch from a required
dependency, not as the production route:
`runtime/edge_runtime.py:190-198,586-589` — "Set `CIRIS_EDGE_DISABLED=true` to
skip in constrained environments."

*Carries both halves but does not refuse* —
`infrastructure/authentication/verifier_singleton.py:253-259` and
`adapters/edge_communication/service.py:62-65` log and proceed.

*The `CIRIS_TESTING_MODE` refusal itself is the weakest of the set* —
`adapters/api/routes/setup/models.py:469`: `ValueError("Username 'admin' is
reserved for testing. Please choose a different username.")`. Names neither the
env var nor a remedy, and as a pydantic `field_validator` it surfaces as HTTP 422.

No custom exception class exists for any of this — all bare `RuntimeError` /
`ValueError`.

**Boolean parsing has no single convention either**: `== "true"` (31 sites),
`in ("true","1","yes","on")` (15), `in ("true","1","yes")` (7), inverted
default-on forms (3). One named constant exists — `_TRUTHY = {"true","1","yes","on"}`
at `adapters/api/routes/setup/config.py:196` — module-private, single consumer.
`CIRIS_MOCK_LLM` alone is parsed four ways, including presence-only at
`adapters/api/routes/agent.py:959` where `CIRIS_MOCK_LLM=false` evaluates **True**.

**There is no central `CIRIS_*` registry.** `config/environment_variables.md` is
stale — it lists none of `CIRIS_TESTING_MODE`, `CIRIS_IMPORT_MODE`,
`CIRIS_MOCK_LLM`, `CIRIS_DISABLE_NETWORK`, `CIRIS_EDGE_DISABLED`.

**`CIRIS_DISABLE_NETWORK` is fully dead** — set at `tests/conftest.py:84`, read
nowhere repo-wide. Do not model on it.

### 2.2 And nothing is enforced in CI

`grep` over `.github/workflows/` for
`CIRIS_TESTING_MODE|CIRIS_IMPORT_MODE|CIRIS_MOCK_LLM|test-anchor|mesh_repro`
returns **zero hits**.

`mesh_repro` — which contains `_test_prod_wheel_guard`
(`tools/qa_runner/modules/mesh_repro_tests.py:207`), the PROD-WALL BREACH check —
is a registered QA module (`tools/qa_runner/config.py:65`) that **no workflow
invokes**. It runs only when a human types it. Pre-commit has no gate check either.

**Exactly one Python test in the repo asserts anything about a gate's production
behaviour**, and it is a source-level assertion —
`tests/services/infrastructure/test_attestation_refresh.py:602-634`:

```python
monkeypatch.setenv("CIRIS_IMPORT_MODE", "true")
monkeypatch.setenv("CIRIS_MOCK_LLM", "true")
src = inspect.getsource(AuthenticationService.start)
assert "skipping attestation in test mode" not in src, (
    "Test-mode attestation-skip reintroduced. ciris_verify is a hard "
    "runtime dependency; CIRIS_IMPORT_MODE / CIRIS_MOCK_LLM must NOT "
    "bypass startup attestation."
)
```

Its docstring records why: `start()` once had `if CIRIS_IMPORT_MODE or
CIRIS_MOCK_LLM: return`, which left consumers running unattested. **This is the
precedent to copy** — an assertion that a gate *cannot bypass a control* — and it
is the only one.

**Consequence for this design: the enforcement in §2.5 is new construction, not
reuse.** Saying otherwise would be the same overclaim this document is trying to
prevent in the research.

### 2.3 The gate chosen

**Two keys. One new; one reused.**

| key | role |
|---|---|
| `CIRIS_RESEARCH_PROMPT_OVERRIDES` | **what** — absolute path to the manifest. Absence = the feature does not exist. |
| `CIRIS_TESTING_MODE=true` | **whether** — the anchor. Reused, not invented. |

Parse with the existing `_TRUTHY` set, promoted from
`adapters/api/routes/setup/config.py:196` to a shared util rather than adding a
fifth parsing convention.

**Why two keys.** One key conflates "I want overrides" with "I am allowed them".
A stray `CIRIS_RESEARCH_PROMPT_OVERRIDES=` surviving in a production `.env` would
then suffice to swap the covenant out of a live agent. With the anchor, that stray
line is *inert and loud*: it refuses at boot instead of running.

**Why `CIRIS_TESTING_MODE`.** DRY — it is the repo's existing research anchor, it
is what the upstream fence keys on, and it is known-absent in production images. A
new `CIRIS_RESEARCH_MODE` is a second thing to audit and a second thing to forget.

**Known tension, stated rather than hidden.** `tests/conftest.py:14` sets
`CIRIS_TESTING_MODE=true` for the whole unit-test suite, so the anchor is live in
every `pytest` run. This is safe **only because the anchor alone does nothing** —
the manifest key must also be set, and no test sets it. The implementation must
never invert this (never make the manifest key the anchor and testing-mode the
selector).

### 2.4 The refusal

```python
raise RuntimeError(
    f"research prompt overrides refused: CIRIS_RESEARCH_PROMPT_OVERRIDES is set "
    f"({manifest_path}) but CIRIS_TESTING_MODE is not 'true'. Research overrides "
    f"replace covenant and DMA prompt text and are a pre-registered-experiment "
    f"facility only — they never run in production.\n"
    f"Remedy, pick one:\n"
    f"  production run  -> unset CIRIS_RESEARCH_PROMPT_OVERRIDES\n"
    f"  experiment run  -> set CIRIS_TESTING_MODE=true"
)
```

**Why the refusal names its own remedy.** This failure has *two* valid
resolutions, and which is correct depends on a fact the code cannot see: whether
the operator believes they are in production or in the harness. A bare "refused"
makes the operator guess — and the cheap guess, set the other variable until it
starts, is the dangerous one. Naming both remedies side by side forces the
operator to answer "which environment is this?" before acting. **That question is
the safety property; the message is just where it gets asked.** This is why the
upstream string names `POST /v1/federation/consent` and not merely the env var:
it makes the production path the visibly-available alternative, so choosing the
test path is a decision rather than a default.

When the gate is off and no manifest is set, the loader is never constructed and
no override state exists in the process. The path is unreachable, not merely
unused.

### 2.5 Enforcement (new construction — see §2.2)

Two pieces, both of which must be built:

1. A test in the `test_attestation_refresh.py:602` shape: assert that with
   `CIRIS_TESTING_MODE` unset, the override registry is `None` and any attempt to
   consult it raises.
2. **Wire it into CI.** Nothing currently enforces any gate in any workflow. A
   guard that no workflow invokes is the state `mesh_repro` is already in, and it
   is indistinguishable from having no guard.

Additionally: run the research lane with **`CIRIS_STRICT_PROMPT_FORMAT=1`**
(`dma/prompt_loader.py:92-94`), which promotes unexpanded `{placeholder}` tokens
from `WARNING` to `ValueError`. It is an existing strict lane, free to adopt, and
catches a whole class of override-template breakage.

---

## 3. The manifest

### 3.1 Keying

Keyed **the way each loader is already keyed** — one namespace per real loader.
Not one flat keyspace: there are five genuinely different addressing schemes, and
flattening them would invent a sixth.

```json
{
  "manifest_version": "1",
  "experiment_id": "covenant-overrides-2026-08",
  "condition": "b",
  "base_locale": "en",
  "mode": "strict",

  "residue_digest": "sha256:…",

  "overrides": {
    "string": {
      "prompts.language_guidance": "…",
      "prompts.prohibitions._header": "…",
      "conscience.ponder_forced_retry": "…"
    },
    "dma_prompt": {
      "pdma_ethical.system_guidance_header": "…",
      "action_selection_pdma.decision_format": "…"
    },
    "conscience_prompt": {
      "entropy_conscience.system_prompt": "…",
      "optimization_veto_conscience.system_prompt": "…"
    },
    "corpus": {
      "accord.localized": "…",
      "accord.polyglot_compressed": "",
      "guide.comprehensive": "",
      "polyglot.pdma_framing": "…"
    },
    "template": {
      "description": "…",
      "role_description": "…",
      "domain": "…"
    }
  },

  "research_hashes": { "accord_1.2b_xx.txt": "sha256:…" }
}
```

| namespace | key form | intercepts | source |
|---|---|---|---|
| `string` | existing dot key | `get_string` — `localization.py:188` | #7 |
| `dma_prompt` | `<template>.<PromptCollection field>` | `dma/prompt_loader.py:191` | #1 |
| `conscience_prompt` | `<conscience>.<ConsciencePrompts field>` | `conscience/prompt_loader.py:95` | #2 |
| `corpus` | fixed enum | `get_localized_accord_text` / `get_accord_text` / `_substitute_polyglot_blocks` | #3–#6 |
| `template` | `AgentTemplate` field | `schemas/config/agent.py:65` | #8 |

`dma_prompt` field names are the `PromptCollection` constructor fields at
`dma/prompt_loader.py:244-268`. Not invented; read off the existing schema.

There is deliberately **no `inline` namespace** — offering one would imply source
#9 is addressable. It is not. §6.1 handles it instead.

### 3.2 Fail-loud rules

All run at **manifest load, before the first LLM call.** A campaign that discovers
a bad key on thought #400 has already burned 399 contaminated samples.

**R1 — every key must resolve.** `string` keys must exist in the base-locale JSON
**and** be in the *reachable* set of §1.2 — naming one of the 123 dead keys is an
error, not a no-op. `dma_prompt` / `conscience_prompt` template and field names
must exist. `corpus` keys must be in the enum. `template` fields must exist on
`AgentTemplate`. Failures collect into **one** `RuntimeError` listing **all**
unresolved keys, so one run fixes the manifest.

**R2 — `mode: "strict"` demands totality.** Every reachable field of every
intercepted loader must be named; unnamed field → refuse, listing omissions. This
is what "a non-CIRIS variant is just a different localization" actually requires —
partial replacement leaves CIRIS text in a supposedly non-CIRIS arm.
`mode: "additive"` exists for pilots and **must be recorded in the trace**.

**R3 — no silent locale fallback.** Both prompt loaders fall back to the English
base with a `debug` log (`dma/prompt_loader.py:216-221`;
`conscience/prompt_loader.py:125-131`). Under an active manifest, that fallback
must raise — otherwise a research locale missing one YAML silently serves the
original CIRIS English prompt.

**R4 — no raw-key leakage, and no `[EN]` laundering.** `get_string` returns the
raw key on a miss (`localization.py:248-249`) and treats any `[EN]`-prefixed value
as absent (`:222-224`). Under an active manifest, both must raise. Otherwise a
typo injects the literal `prompts.dma.pdma_headr` into the prompt as content, or
an override that *is present* is silently replaced by English.

**R5 — no partial covenant.** `corpus` must set `accord.localized` and
`accord.polyglot_compressed` together, or refuse. §7.1 is why.

### 3.3 Precedence — must be explicit

`AgentTemplate` **already** carries ungated prompt overrides — `csdma_overrides`,
`pdma_overrides`, `action_selection_pdma_overrides` (`schemas/config/agent.py:264-289`)
— and they are consulted **before** the prompt loader: `dma/pdma.py:136-145`
returns the template's `system_prompt` and never calls
`prompt_loader.get_system_message`.

A leftover template override therefore silently beats a manifest entry for the
same field. **Rule: if both target the same field, refuse.** Do not silently pick
a winner.

---

## 4. Condition (b)

### 4.1 The claim, verified

`ethical_faculties_skipped` is hardcoded at
`ciris_engine/logic/processors/core/thought_processor/conscience_execution.py:394`
(the brief said 380; it is **394**):

```python
ethical_faculties_skipped=False,  # Non-exempt actions always run faculties
```

The exempt-action early return (`:157-180`) does not set the field at all, so it
stays `None` (`schemas/processors/core.py:110`). **The field is therefore never
`True` anywhere in the codebase** — confirmed across all 15 references. It is a
reporting field with no writer.

### 4.2 Is (b) reachable?

**Yes — the *skip* needs no new machinery.** `conscienceRegistry.set_enabled(name,
False)` exists at `conscience/registry.py:74`, and `get_consciences()` (`:50`)
filters on `enabled`. Disabling `entropy`, `coherence`, `optimization_veto`,
`epistemic_humility` — registered at `runtime/component_builder.py:149-152` —
leaves the two bypass guardrails running and skips the four faculty LLM calls.
That is condition (b): covenant in the prompt, maintenance machinery off.

The `conscience_checks_ran == 0` guard at `:364` does **not** fire, because the
bypass consciences still run and still increment the counter.

**But (b) is not safely *recordable* today.** Three defects:

**(i) Fabricated epistemic scalars.** `:372-375`:

```python
# Use actual data from conscience checks - no defaults for missing metrics
epistemic_data = EpistemicData(
    entropy_level=entropy_level if entropy_level is not None else 0.1,   # Default safe value
    coherence_level=coherence_level if coherence_level is not None else 0.9,  # Default high coherence
```

The comment says "no defaults"; the next two lines apply defaults. With the
faculties disabled both aggregates are `None`, so **every condition-(b) trace
would carry `entropy=0.1, coherence=0.9` in the same fields that carry measured
values in (c)** — indistinguishable downstream. A c−b analysis on epistemic
scalars would compare measurements against two constants and report a large,
clean, entirely artefactual effect.

**(ii) The flag lies.** `ethical_faculties_skipped=False` at `:394` would be
emitted on a run where the faculties demonstrably did not run.

**(iii) The schema cannot express "not measured".**
`EpistemicData.entropy_level` and `.coherence_level` are non-nullable `float`
(`schemas/conscience/core.py:196-197`) under `extra="forbid"` (`:206`). There is
no representable value meaning *absent*, and no way to add one ad hoc.

### 4.3 Can `ethical_faculties_skipped` be exposed safely?

**Yes — but only as a derived output of a real skip, and only after the schema can
represent absence.** Never as an input knob: a settable "skipped" flag that does
not itself skip anything is a trace-forgery primitive.

Three prerequisites. **All three are truthfulness fixes that stand on their own
merit** — they make production traces honest whether or not this facility is ever
built, so none is research-only code in the production path:

1. **`schemas/conscience/core.py:196-197`** — `Optional[float]`; absent means not
   measured. Audit consumers (`processors/core/step_decorators.py:961,1757`;
   `ciris_adapters/ciris_accord_metrics/services.py:1788`; trace schemas
   `trace_format_v2_7_0.json:244`, `v1_9_1.json:203`). The trace JSON already
   types `ethical_faculties_skipped` as `["boolean","null"]`, so the wire format
   is ready.
2. **`conscience_execution.py:374-375`** — delete the defaults, carry `None`. Make
   the code match the comment already there.
3. **`conscience_execution.py:394`** — derive it:
   `all(r is None for r in (entropy_check_result, coherence_check_result,
   optimization_veto_result, epistemic_humility_result))`. And set it `True` on
   the exempt early return at `:157-180`, where it is currently left `None`.

**No distinct exemption path is needed.** Condition (b) is not a new kind of
exemption; it is the existing registry-disable path plus a trace that stops lying.

### 4.4 What condition (b) is *not*

With the faculties disabled the agent still runs context gathering, four DMAs,
ASPDMA action selection, JSON-schema-coerced action output, both bypass
guardrails, and handler dispatch — including the entire inline English action
doctrine of §1.3. Condition (b) is **"CIRIS scaffolding + covenant text, minus the
epistemic faculties and their recursion"** — not "raw model that has read the
covenant". If the pre-registration means the latter, this design does not deliver
it, and §6.2 explains why nothing in this repo can.

---

## 5. Expressing a non-CIRIS variant

**Both — a new locale *and* a manifest.** Neither alone suffices, and even both
together leave §6.1's residue.

**New locale** carries the ~86% of bytes: create `xx` (a private-use code, never a
real BCP 47 language) with `dma/prompts/localized/xx/*.yml` (all 7),
`conscience/prompts/localized/xx/*.yml` (all **4** — including
`optimization_veto_conscience.yml`, which no real locale has; §1.5),
`data/localized/accord_1.2b_xx.txt`, and `data/localized/xx.json`. Select with
`CIRIS_PREFERRED_LANGUAGE=xx` (`localization.py:470`).

Note `xx` must also be added to the hardcoded frozenset `SUPPORTED_LANGUAGE_CODES`
(`utils/path_resolution.py:76-108`), which `_validate_language_code` (`:1008`)
enforces and which **nothing cross-checks against the manifest**.

**Manifest** carries the residue that has no `{lang}` variant: the polyglot block,
the polyglot ACCORD, the guide, and the `AgentTemplate` prose fields.

### 5.1 A research locale is unverified by default — close it

`_verify_accord_integrity` (`constants.py:208-236`) checks against
`ACCORD_EXPECTED_HASHES`, but `:220-222`:

```python
if not expected_hash:
    logger.warning(f"[ACCORD] No expected hash for {filename} - file not in integrity registry")
    return  # Allow unknown files but warn
```

A new `accord_1.2b_xx.txt` is not in the registry, so **it is not checked**. The
research arm would be the one arm with no tamper detection — precisely backwards
for a pre-registered campaign whose validity rests on the arms being what they
claim. Hence `research_hashes`: research-locale corpus files pin their SHA256 in
the manifest, verified under the same `RuntimeError` fail-safe. The registry
moves; the guarantee does not.

### 5.2 Corpus substitution is in-memory, never on disk

Production corpus files are hash-pinned; overwriting one would trip
`_verify_accord_integrity` and hard-fail — correctly. The `corpus` namespace must
substitute **in-memory at the loader boundary**, never by writing to
`ciris_engine/data/`. This leaves the production integrity guarantee intact and
unmodified.

---

## 6. What this does NOT do

**6.1 It does not cover the inline action doctrine — the largest gap, and it must
refuse rather than pretend.** Per §1.3, ~75–80% of *operative* instruction text —
and 10–14 KB at the ASPDMA call — is compiled-in English: the ASPDMA user message
(`context_builder.py:248-336`), the DEFER policy (`action_instruction_generator.py:106-128`
and again `:436-461`), the DSDMA user message (`dsdma_base.py:397`), the identity
blocks, the formatters, conscience override reasons.

Covering them means refactoring each through a lookup — a large change to hot
production code, **out of scope here**.

What this design does instead: **`residue_digest`.** Ship an enumerated inventory
of the uncovered literals with a SHA256 over it; the manifest pins that digest and
the loader **refuses on mismatch**. The residue stays uncovered but becomes
*pinned*, so it cannot drift mid-campaign without stopping the run. Same idea as
`ACCORD_EXPECTED_HASHES`, applied to a surface with no file to hash. It converts
an unknown into a declared constant — the most a design can honestly do here.

**Any paper using this facility must report the residue as a stated limitation:
the non-CIRIS arm was reasoning under CIRIS's action doctrine, in English.**

**6.2 It does not make condition (a) reachable.** There is no configuration of
this runtime that yields a bare prior, because the pipeline *is* the agent. Even
with every prompt field blanked, a run still carries ASPDMA scaffolding, JSON
response-format coercion, the handler action enum, both bypass guardrails, and
§6.1's residue. **Condition (a) must come from a separate direct-to-provider
harness** — a plain Messages API call, same model, same decoding parameters, same
corpus. Approximating (a) by turning CIRIS knobs produces a fourth thing that is
neither (a) nor (b); labelling it (a) invalidates every comparison against it.

**6.3 It does not gate the levers that are already ungated.**
`CIRIS_ACCORD_MODE` (`constants.py:54`) and the template `*_overrides`
(`schemas/config/agent.py:264-289`) alter production prompts today with no gate.
Untouched here — but see §7.1 and §8.2.

**6.4 It does not validate semantics.** Nothing checks that an override is a
faithful translation, a coherent instruction, or even in the claimed language. The
localization pipeline has shipped word-salad through structural validation before.
Structural validity is not content validity.

**6.5 It does not cover dynamic context.** Memory recall, system snapshot,
conversation history, user profiles. Not template text; not overridable.

**6.6 It does not make the arms cost-comparable.** Condition (b) skips four LLM
calls per thought and is faster and cheaper than (c) by construction. Any latency
or cost comparison across arms measures call count, not the covenant.

---

## 7. How this could silently produce wrong research

Ordered by how easily a careful person still gets caught.

**7.1 `CIRIS_ACCORD_MODE=none` is a partial covenant removal that reports
success.** *This is the single most dangerous thing in this area, it exists today,
ungated, and it has nothing to do with this design.*

Two accord accessors:

- `get_accord_text(mode)` — `constants.py:469` — **honors `ACCORD_MODE`**, returns
  `""` for `none`. Used by PDMA, CSDMA, IDMA, DSDMA (`idma.py:102`;
  `formatters/prompt_blocks.py:81`).
- `get_localized_accord_text(lang)` — `constants.py:548` — **never reads
  `ACCORD_MODE` at all.** Used by ASPDMA (`action_selection_pdma.py:222`),
  TSASPDMA (`tsaspdma.py:348,636`), DSASPDMA (`dsaspdma.py:243`).

A researcher building a "covenant off" arm the obvious way removes the covenant
from the four ethical-reasoning DMAs and leaves the **full ~55 KB localized ACCORD
in the action-selection prompt** — the prompt that actually chooses what the agent
does. Startup logs print `[ACCORD] Mode 'none' - no accord in system prompts`
(`constants.py:466`), confirming the intended change. Nothing reports the other
half.

Every (a)-vs-(c) and (b)-vs-(c) number computed that way is wrong, biased toward
**understating** the covenant's effect — the "covenant off" arm still has the
covenant where it counts most. R5 (§3.2) exists solely for this.

**7.2 The action doctrine is not in any arm's override set.** §6.1. A researcher
who swaps every locale file will believe they built a non-CIRIS variant. They will
have built a CIRIS agent with a non-CIRIS covenant, still executing CIRIS's DEFER
policy verbatim. Given that DEFER-vs-SPEAK is exactly the behaviour these
campaigns measure, this can invert a conclusion rather than merely blur it.

**7.3 The 123 dead localization keys accept overrides and discard them.** Setting
`prompts.dma.pdma_task` or any `prompts.formatters.*` key looks identical to
setting a live key and does nothing. R1.

**7.4 Silent locale fallback serves the original CIRIS prompt.** A research locale
missing one of its 11 YAML files falls back to the English CIRIS base at `debug`
(`dma/prompt_loader.py:216-221`; `conscience/prompt_loader.py:125-131`). The arm
silently contains what it was built to exclude. R3.

**7.5 `optimization_veto_conscience` is always English.** Localized in zero of 28
locales (§1.5). Any cross-locale comparison of conscience behaviour has one
faculty running in English for every arm. This is a pre-existing confound in *all*
multilingual results from this repo, not just this campaign.

**7.6 Typos and `[EN]` markers.** `get_string` returns the raw key on a miss
(`localization.py:248-249`) — a typo puts `prompts.dma.pdma_headr` into the prompt
as content. And any override whose value begins `[EN]` is treated as absent
(`:222-224`) and silently replaced with English. R4.

**7.7 Fabricated epistemic scalars in condition (b).** §4.2(i). Without §4.3, (b)
traces carry `entropy=0.1, coherence=0.9` in the fields holding measurements in
(c). **This is the failure most likely to yield a publishable-looking wrong
result**, because the constants are plausible values that differ cleanly from
measured ones.

**7.8 Leftover template overrides beat the manifest.** `dma/pdma.py:136-145`
consults `AgentTemplate.pdma_overrides` before the prompt loader. A field left set
from an earlier run silently wins. §3.3.

**7.9 Already-dead translations prove the failure mode is real.**
`context_builder.py:740-765` returns `ActionInstructionGenerator` output whenever
truthy, and `generate_action_instructions` always emits at least its header line
(`action_instruction_generator.py:63`) — so it is **always** truthy. The
`action_parameter_schemas` field, translated into all 28 locales, is
**unreachable**. Verified: `prompts/localized/es/action_selection_pdma.yml`
contains "Esquemas de campo PLANO por acción…" and never reaches an LLM. Someone
already translated a field into 28 languages and shipped it dead; nothing caught
it. That is precisely what an override manifest would do without R1.

**7.10 An additive-mode run analyzed as a strict arm.** `mode: "additive"` leaves
unnamed fields at CIRIS defaults. If the mode is not carried into the trace and
asserted on at analysis time, a pilot is indistinguishable from a clean arm. R2.

**7.11 Nothing validates the localization bundle from the Python side.**
`tools/dev/check_localization_sync.py` (pre-commit `.pre-commit-config.yaml:130`,
CI `build.yml:37`) enforces Kotlin key coverage and mirror parity, but its
cross-language check is **`WARNING`, exit 0** without `--strict`, and there is **no
Python-side reference-coverage check at all** — a `get_string` key missing from
`en.json` is caught by nothing. It also reads the manifest against the *Android*
bundle (`PRIMARY_BUNDLE`, `:66`), not the runtime bundle.

---

## 8. Flagged as unsafe or unbuildable

Per the brief's instruction to flag rather than proceed:

1. **Condition (b) cannot be honestly recorded without a schema change.**
   `EpistemicData` (`schemas/conscience/core.py:193-206`) has non-nullable scalars
   under `extra="forbid"`. A genuine blocker, not a preference — there is no way to
   write "not measured". **Do not implement the override facility before §4.3.** A
   campaign run on the current schema produces fabricated (b) values by
   construction.

2. **§7.1 is a live production hazard independent of this design.**
   `CIRIS_ACCORD_MODE` is ungated and partial *today*. Either make
   `get_localized_accord_text` honor `ACCORD_MODE`, or make `mode == "none"` refuse
   at startup rather than half-apply. **File separately; it should not wait on a
   research feature.**

3. **The residue inventory (§6.1) must be built before the first campaign run.**
   A `residue_digest` over an inventory nobody enumerated is a hash of an
   assumption. §1.4(1) says why the current figure cannot be trusted as a
   measurement.

4. **The gap in §6.1/§7.2 may be large enough to defeat the research question.**
   If the campaign's outcome measure is action choice (DEFER vs SPEAK), and the
   action doctrine is inline English in every arm, then (b) and (c) share the
   doctrine and differ only in the faculties — which is a *narrower* c−b than
   "does the maintenance machinery do work". **This should be settled with the
   pre-registration authors before implementation**, because it changes what c−b
   means, not merely how precisely it is measured.

5. **`mode: "additive"` is a footgun with a legitimate use.** If pilots do not
   need it, drop it — a format with one mode cannot be misread.

---

## 9. Implementation order (when approved)

1. §4.3 truthfulness fixes — independently valuable; unblock (b).
2. Residue inventory + digest tool (§6.1).
3. Gate + refusal + CI-wired enforcement (§2.3–2.5) — new construction, not reuse.
4. Manifest schema + R1–R5 (§3.2) + precedence refusal (§3.3).
5. Loader interception, one source at a time, `corpus` last.
6. Separate direct-to-provider harness for condition (a) (§6.2).

Nothing in steps 3–5 may land without step 1.

---

## 10. Experimental regimes (2.9.9) — replacement, not ablation  [v2]

*v1 of §10–§14 was reviewed adversarially by three independent skeptics
(methodology, taxonomy, implementation) before anything was built on it. Both
delivered verdicts of UNSOUND-AS-BASIS; v2 is the redesign under their findings,
which are cited inline as [M-n] / [T-n]. Nothing in v1 was ever staked.*

### 10.0 The change in one sentence

§1–§9 built a facility that can **blank** prompt text. A regime study needs one
that can **replace** it: an experimental arm is *the H3ERE pipeline reasoning
under a different value system*, not *under none*. Blanking does not produce a
value-neutral agent — it produces an agent whose values are the base model's
prior, unstated and unmeasured. Replacement makes the counterfactual explicit
and therefore checkable.

**Letter hygiene [M-1]:** §0's conditions (a/b/c), §4.4's condition (b), and
regime arms are three different things. Arms are therefore named descriptively,
never lettered. The historical mapping: §0 condition (a) ≈ arm `bare`; §0
condition (c) ≈ arm `h3ere-ciris`. No other correspondence is implied.

### 10.1 Why the keyspace is the wrong unit of declaration

Unchanged from v1: manifests declare **classes**, the loader resolves classes to
sites, and the gate proves the mapping held. "Override these 46 keys" is
unreviewable; §1.3's inversion (86% of bytes addressable, ~20–25% of operative
instruction) is why.

### 10.2 The classification — eleven classes, operationally defined

The v1 anchors (EDA, Lakatos, analytic/synthetic) are demoted to **lineage
notes** [T-6]: they classify agent states and research programmes, not text
blocks, and the transfer is exactly what failed under review. **The definitional
criterion for every class is its operational test and its kill — the anchors
carry no authority.** (Lakatos's *protective belt*, the half v1 dropped, is what
`nomological` and `procedural` cover.)

| class | operational test | examples | default disposition |
|---|---|---|---|
| `axiotic` | states or ranks what matters; varying it can re-rank outcomes without newly permitting any act | ACCORD principles, M-1, the DEFER policy's judgement of which questions deserve deference | the usual variable |
| `deontic` | categorical permission/prohibition; varying it changes what is *permitted*, not how choices rank | `PROHIBITED_CAPABILITIES`, `requires_approval`, prohibition block, "NEVER DENY BEING AN AI" | **hold; `replace:` only with `safety_review`** |
| `pragmatic` | governs register/address/code, not content | register rules inside `language_guidance`, honorific requirements | hold unless the study is about register |
| `ontological` | self-identity and self-description | `=== CORE IDENTITY ===`, template identity fields | hold |
| `epistemic` | how uncertainty is held/expressed | humility faculty, entropy/coherence thresholds, "be skeptical of this context" | hold unless studied |
| `empirical` | **static** world-facts checkable at compose time | crisis numbers, tool descriptions | **hold across arms, gate-checkable** |
| `contingent` | runtime data that *necessarily* diverges once arms behave differently [T-2] | system snapshot, memory recall, conversation history | **out of gate scope by construction; measured post-run, reported like residue** |
| `procedural` | control-flow instruction to the model; deleting it breaks no parsing but changes orchestration [T-5b] | `prompts.dma.bounce_*`, `prompts.escalation.*` stage directives, chain headers | hold |
| `nomological` | a theoretical model/formula the reasoning is asked to apply; replaceable without breakage, neither value nor world-fact [T-5c] | `k_eff = k/(1+ρ(k−1))` and the IDMA chaos/healthy/rigidity frame | hold |
| `structural` | replacing it breaks parsing or dispatch — the operational test, nothing else | JSON coercion, handler action enum, FLAT schemas | cannot vary |
| `axiomatic` | the decomposition premise itself | that ethical reasoning decomposes into PDMA/CSDMA/DSDMA | cannot vary in-runtime; **is** the cross-harness variable |

**Kills are equivalence claims and priced as such [T-4].** Every kill asserts
something *did not move*. A kill is operable only with: (i) a named instrument
that exists **in every declared locale** — the per-language U-code pattern
tables cover 18 languages and a regime declaring a locale outside them is
refused for any varied class whose kill needs that instrument; (ii) a declared
minimum detectable effect and equivalence bound. A kill without both is
decoration, and its class reverts to `hold`.

#### 10.2.1 Per-block: (class, disposition), refusal by default  [T-0/T-1 — subsumes M-4]

v1 keyed the gate's assertions on classes; a block filed `structural` escaped
all five assertions even when it was the FSD's own named "largest source of arm
contamination" [T-0]. v2 keys everything on **blocks**:

Every composed block carries `(block_id, primary_class, disposition)` where
`disposition ∈ {vary, hold, n/a, refuse}`. **The default for any block not
resolved by the manifest — including every `mixed` block — is `refuse`: the run
does not start.** A `mixed` block runs only with an explicit per-block
disposition in the manifest, by `block_id`.

Known irreducibles, named now so no manifest discovers them:

- **The DEFER policy** (`action_instruction_generator.py:106-128`, dup
  `:436-461`): axiotic content in a structural site, lexically free of every
  brand token [M-4]. Its per-block entry carries `contaminant: axiotic`, and
  **any regime declaring an action-tier DV refuses while it remains unrouted**
  (§11 step 0). No token scan substitutes for this.
- **`prompts.language_guidance`** (13,524 B): pragmatic + deontic + axiotic +
  empirical in one scalar; unsplittable short of rewriting it [T-1]. Until §11
  splits it in the corpus, it is `mixed` and demands explicit disposition.

**Every `mixed` block MUST carry a populated `contaminant:` list — not only the
DEFER policy — and the gate refuses any `hold` disposition whose contaminants
intersect a varied class, unless `confound_accepted:` names that exact
contaminant [T-N1].** Without this, holding `language_guidance` (which carries
CIRIS axiotic content — "route serious symptoms to professional care without
minimization") leaves CIRIS values byte-identical inside the alt-values arm:
every Phase-1 assertion passes, and `values_effect` is biased toward zero with
the gate green. A `hold` that smuggles the varied class is the one confound the
block table exists to catch.
- **Few-shot worked examples** (`pdma_ethical.yml:138-145`): verdict, register
  and schema in the same tokens — the co-occurrence *is* the demonstration
  [T-5a]. `mixed`, explicit disposition required; the honest options are
  hold-verbatim or replace-whole-exemplar, never split.

#### 10.2.2 Revisability — bounded, and pre-registration-safe  [T-7]

- **Merge rule (bounded):** two classes merge when no divergence has been
  observed across ≥3 completed regimes covering **≥5 cumulative distinct
  locales** at each regime's declared power [T-N4] — cumulative across the
  contributing regimes, not per-regime (a 3-locale regime can contribute) —
  and not "never diverge", which fires never.
- **Split rule = re-registration event:** a split creates a new class-set
  version; results gathered pre-split are reported under the old version,
  never silently re-mapped; in-flight regimes complete under their registered
  version.
- Manifests pin `class_set_version`; an unknown version is refused.

#### 10.2.3 Annotation reliability  [T-3]

A class-set version is citable only after **two independent annotators** classify
the full block inventory with **Cohen's κ ≥ 0.8 overall AND per-boundary κ ≥ 0.8
on every class pair whose default disposition differs** — `axiotic|deontic`
(gates `safety_review`) and `axiotic|structural` (gates §11 step 0) foremost:
an aggregate κ over eleven classes with skewed marginals can pass while exactly
the decision-relevant boundaries fail [T-N2]. Disagreements adjudicated and
logged. Annotator identities, κ, and the adjudication log ship inside
`regime:composition:v1` (§13). One author annotating once — v1's implicit
procedure — is how every probe in review produced two defensible answers.

### 10.3 The regime manifest — full factorial, tiered DV  [M-1, M-2, M-6, M-7]

```yaml
schema: ciris.ai/experimental_regime/v2
regime_id: torque-1
class_set_version: 2
hypothesis: >
  H3ERE's behavioural effect is separable from the specific values it carries.

arms:
  bare:          {harness: direct-provider}                    # no pipeline, no values
  values-ciris:  {harness: direct-provider, inject: {axiotic: corpora/values-ciris/}}
  h3ere-ciris:   {harness: h3ere}                              # THE SHIPPED CONFIG — the missing cell v1 forgot [M-1]
  h3ere-alt:     {harness: h3ere, replace: {axiotic: corpora/values-alt/}}
  h3ere-blank:   {harness: h3ere, disable: [axiotic]}          # explicitly NOT a neutrality claim (§10.0)

contrasts:                       # every claim must name its contrast [M-1]
  pipeline_effect:  h3ere-ciris - values-ciris   # pipeline at matched values
  values_effect:    h3ere-ciris - h3ere-alt      # values at matched pipeline
  scaffold_floor:   h3ere-blank - bare           # scaffolding alone
  # bare - h3ere-alt is CONFOUNDED on both factors and may not carry a claim.

dv:                              # [M-2] — the DV must exist in the arms it is claimed over
  action_tier: {measures: [selected_verb, defer_rate], arms: [h3ere-ciris, h3ere-alt, h3ere-blank]}
  text_tier:   {measures: [U_codes, refusal, resource_naming], arms: all}
  # U-codes are PER-LANGUAGE rubric rows, not one construct: U4 is dialect_drop
  # in ar and register_break_to in fa [T-N3]. Scoring is per (locale, U-row);
  # cross-locale pooling of a U-code is forbidden absent a declared construct
  # map in the manifest.
  # POWER FOLLOWS [M-N5]: per-(locale,U-row) scoring multiplies the corrected
  # family — 4 locales x per-locale rows x contrasts is 50-60+ Holm-corrected
  # tests at conversations_per_cell: 20. The manifest must therefore
  # PRE-REGISTER the text-tier rows it will test as a named subset, with a
  # power statement at the declared n; a family whose corrected MDE exceeds
  # the declared MDE is refused. Validity (T-N3) and power (this) move
  # together or the tier is underpowered by construction.
  text_tier_rows: {am: [U4, U6, U10], ar: [U4, U6, U10], fa: [U4, U6, U10], en: [U4, U6]}
  # A claim citing action_tier may reference h3ere arms ONLY: a direct-provider
  # call has no handler enum, so DEFER-vs-SPEAK is undefined there.

repeats:                         # [M-7] — the arc shares one channel_id; the
  unit: conversation             # conversation is the independent unit, so
  conversations_per_cell: 20     # n = conversations, NOT questions (9×3 ≠ 27)
  # VARIANCE SOURCE MUST BE DECLARED AND REAL [M-N1]. temperature 0.0 with seed
  # unplumbed = 20 identical inputs measuring provider batching noise; `seeds:`
  # would be inert. Until §14 step 6 plumbs seed, the only honest repeat policy
  # is temperature > 0 with the value pinned; after plumbing, temperature 0
  # with enumerated seeds. A manifest whose repeat structure has no live
  # variance source is refused.
  variance_source: temperature   # or "seeds" once plumbed — never "none" with n>1
  seeds: [20260802, 20260803, ...]   # inert until seed is transmitted; see holds
  comparison_policy: holm-bonferroni
  mde: {pipeline_effect: 0.15, values_effect: 0.15}  # required for MAIN
  # contrasts, not only kills — a contrast without a declared MDE cannot carry
  # a null result.

holds:
  model: Qwen/Qwen3.6-35B-A3B
  decoding: {temperature: 0.0, top_p: 1.0, max_tokens: 4096,
             extra_body: {chat_template_kwargs: {enable_thinking: false}}}
  base_url: https://api.deepinfra.com/v1/openai   # [M-N3] extra_body is a
  # FUNCTION of base_url (service.py:1549-1570) — the DeepInfra branch also
  # transmits reasoning.enabled — so an unpinned endpoint changes the
  # transmitted parameter set under an identical manifest.
  # ENFORCED-OR-REFUSED [M-6], with SET-EQUALITY semantics [M-N3]: the check is
  # pinned == transmitted, both directions. A pinned key the call path does not
  # send ("pinned but not plumbed") refuses; a TRANSMITTED key the manifest
  # does not pin ("sent but undeclared") also refuses — v2's own first example
  # pinned a strict subset of what the DeepInfra branch sends, and a subset
  # semantics would have passed it. As of 2.9.7, `seed` is NOT transmitted on
  # the OpenAI-compatible path (service.py:1376) — plumbing is §14 step 6; a
  # manifest pinning seed before that lands is refused with exactly this
  # sentence.
  corpus: v1_sensitive.json
  locales: [en, am, ar, fa]      # every declared locale must carry the kill
                                 # instruments for every varied class (§10.2).
                                 # `en` is MANDATORY as the fidelity control
                                 # [M-N2]: in low-resource locales, a values
                                 # effect cannot be separated from alt-corpus
                                 # translation quality (§6.4, and this repo has
                                 # shipped word-salad through structural
                                 # validation before). en is where corpus
                                 # fidelity is natively checkable.
  adapter_set: [api]

pins:
  residue_digest: "sha256:…"
  accord_sha256: "…"
  template_sha256: "…"
  substrate: "ciris-server==0.5.151"
  harness: {agent: "2.9.8-stable"}

blocks:                          # per-block dispositions for every `mixed` block (§10.2.1)
  # contaminant: is MANDATORY on mixed blocks [T-N1]. hold + contaminant
  # intersecting a varied class refuses unless confound_accepted names it.
  language_guidance:
    disposition: refuse          # [M-N6] YES, THIS REFUSES THE REGIME AS
                                 # WRITTEN — deliberately. This block carries
                                 # axiotic contaminant and this regime varies
                                 # axiotic; the correct path is §11 step 6
                                 # (split it in the corpus), after which its
                                 # pragmatic fragment is held cleanly. Writing
                                 # `hold` + `confound_accepted: axiotic` here
                                 # instead would bias values_effect toward
                                 # zero with the gate green — an example
                                 # manifest is a template people copy, and it
                                 # must not teach the opt-out as the default.
    contaminant: [axiotic, deontic, empirical]
  pdma_worked_examples:
    disposition: hold
    contaminant: [axiotic, pragmatic]
    confound_accepted: axiotic

gate:
  compose_dump: required
  block_diff: required
  residue_scan: required         # structural, v2 — §12.4
  onwire_verify: required        # post-run — §12.6
  on_incomplete_ablation: refuse
```

**Cross-harness composition is defined, not exempted [M-3]:** a `direct-provider`
arm holding a class receives **the same source bytes** injected as plain system
content; the gate compares *source hashes*, not composed-context equality.
Classes with no direct-provider analogue (`structural`, `procedural`) are
declared `n/a` per-arm in the dump — visible, never silently skipped. `text_tier`
scoring runs through the **same battery scorer** for every arm; the
direct-provider harness is therefore a required §14 deliverable, not an optional
last step.

### 10.4 Refusals

- Any block with unresolved disposition — including every `mixed` block without
  a per-block entry — **refuse** [T-0/T-1].
- `action_tier` DV declared while the DEFER policy is still in the residue
  inventory — **refuse** [M-4].
- An `h3ere` arm labelled `bare` or presented as §0's condition (a) — **refuse**.
  *Code gap, ships with this:* `research_overrides.py:568` currently accepts
  `condition: "a"`; only `"b"` is refused (`:673`) [M-8]. R6: refuse `"a"`.
- A pinned decoding key the runtime does not transmit — **refuse** [M-6]. The
  same rule covers `repeats.seeds`: seeds declared while seed is untransmitted,
  with no other live `variance_source`, is a repeat structure with no variance
  — **refuse** [M-N1].
- A varied class whose kill instrument is absent in any declared locale —
  **refuse** [T-4].
- `deontic` in `replace:` without `safety_review` — **refuse** (v1 rule, kept).
- `pragmatic` varying alongside `axiotic` without `confound_accepted: register`
  — **refuse** (v1 rule, kept).
- `structural`/`axiomatic` in `replace:` — **refuse**; different harness (§6.2).

## 11. Closing the residue — routing order

**Step 0, precondition for any action-tier campaign [M-4]: the DEFER policy**,
both copies (`action_instruction_generator.py:106-128`, `:436-461`),
de-duplicated to one routed source. It is the outcome variable's own doctrine;
no campaign about action choice is honest while arm alternatives inherit it
invisibly.

Then, each independently shippable, `residue_digest` re-pinned at each step:
1. `dma/action_selection/context_builder.py:248-336` — the ASPDMA user message.
2. `dsdma_base.py:397` — the DSDMA user message.
3. Identity blocks — `dsdma_base.py:253,313`, `action_selection_pdma.py:353`.
4. The six formatters (`system_snapshot`, `identity`, `user_profiles`,
   `crisis_resources`, `escalation`, `prompt_blocks`).
5. `conscience/action_sequence_conscience.py:32-36` — override reasons that
   re-enter the retry prompt.
6. **Split `prompts.language_guidance`** in the corpus into its pragmatic /
   deontic / axiotic / empirical constituents [T-1] — after which it stops
   being `mixed`.

Every routed site is annotated `(class, disposition)` at the routing point.
`RESIDUE_SITES` shrinks as this lands; `residue_digest` stays — the floor is
never provably zero (§1.4 item 1).

## 12. The gate — block-keyed, two-phase  [M-3, M-4, M-5, T-0, T-2]

**Phase 1 — static, pre-run, no LLM call.** Two implementation facts bound this
phase [I-1, I-2]:

- **There is no composition seam today.** `messages` is assembled inline inside
  `evaluate()` at **eight** points (`pdma.py:203-233`, `csdma.py:110-286`,
  `idma.py:98-308`, `dsdma_base.py:420-441`, `action_selection_pdma.py:242-281`,
  `dsaspdma.py:242-326`, `tsaspdma.py:344-469` *and* `:633/:554` — a second
  round, pairs 344→469 and 633→554). TSASPDMA already exposes seams
  (`_create_tsaspdma_messages` `:327-403`, `_create_correction_mode_messages`
  `:625`), so the extraction PR is **six sites** for eight points [I-V2]. It is
  its own PR, landed **before** the dump, with golden-bytes tests locking
  pre/post equality — it touches the hottest path in the engine and "no
  behaviour change" must be proved, not asserted.
- **"No LLM call" is not "no runtime."** Composition needs a task, prior DMA
  results, a system snapshot, and bus lookups. The dump runs against a named
  **compose fixture**: seeded SQLite task+thought, stubbed registry/ToolBus,
  synthetic SystemSnapshot, canned upstream DMA results — with every dynamic
  slot rendered as a **stable sentinel** (`{{SNAPSHOT}}`, `{{TASK_ID}}`), so
  `hold:` byte-identity is checked over template output, not over timestamps.
- Process shape: the caches are process-global singletons — `_loader_cache`
  at `prompt_loader.py:475`, the override `_loaded` singleton at
  `research_overrides.py:703` (reset `:694`, "tests only") — so the dump runs
  **subprocess-per-arm** with in-process locale iteration (~3.3 s import cost
  per process, not per pair) [I-V3].

`ciris-research compose --dump` emits every block as:

```json
{"block_id": "aspdma.user_message", "step": "ASPDMA", "locale": "am",
 "arm": "h3ere-alt", "class": "axiotic", "disposition": "vary",
 "source": "corpora/values-alt/aspdma.yml", "sha256": "…", "bytes": 2841,
 "contaminant": null}
```

Assertions — **each iterates the block table, never a class list** [T-0]:
1. Every arm×locale composes; a failed composition is named, not dropped.
2. Every `vary` block differs between the arms its contrast names, and its
   replacement is non-empty.
3. Every `hold` block: byte-identical across h3ere arms; source-hash-identical
   into direct-provider arms [M-3]. `n/a` blocks are listed per-arm.
4. **Residue scan v2 — structural, not lexical [M-4]:** composed output is
   matched against content hashes and normalized fragments of every
   `RESIDUE_SITES` entry. The token scan (`CIRIS`, principle names, M-1)
   is retained as a cheap adjunct, never the mechanism.
5. `residue_digest` matches the pin.
6. Every block has a resolved disposition; anything else already refused at
   manifest load.

`contingent` blocks are **excluded from Phase 1 by construction** [T-2] — at
compose time they are trivially identical and the check would be vacuous.

**Phase 2 — on-wire, post-run [M-5].** The static dump is necessary, not
sufficient: the runtime mutates prompts after composition — retry remediation
injects the English action-verb whitelist (`llm_service/service.py:1990-1996`,
`LLM_ERROR_REMEDIATIONS` defined `:463`), instructor re-asks (mechanism inside
the library — the only real handle is instructor's `completion:kwargs` hook;
`:1390` is a comment describing it, not a hookable site [I-V4]), and
conscience-override retries re-run ASPDMA with new context. Trigger rates are
content- and locale-correlated, so non-English cells receive *more* injected
English doctrine — a differential confound no static diff can see. Therefore:

- **The existing `CIRIS_LLM_CAPTURE_*` hook cannot see this** [I-7]: it records
  at the bus layer (`llm_bus.py:920`) — the messages the bus passed *in*, i.e.
  attempt 0 — while the remediation append happens below it in the service's
  retry loop, and instructor's reask deeper still. Phase 2 therefore requires a
  **new capture row at the injection point** (`service.py:1990`, per attempt,
  carrying `working_messages`) and/or instructor `completion:kwargs` hooks.
- **Interim descope, honest and cheap:** `LLM_ERROR_REMEDIATIONS` is a static
  English dict — identical across arms, which makes it *residue*, not noise. It
  is added to `RESIDUE_SITES` (it is absent today), and until the per-attempt
  capture lands the gate asserts injection is **bounded and arm-invariant**
  rather than absent, and the campaign reports remediation counts per arm ×
  locale from the SERVICE-level counter — `RetryState.count`
  (`service.py:125-139`), exposed per-call — NOT the bus-level LLM_CALL
  `retry_count`, which is "0 = first attempt at the bus level"
  (`runtime_control.py:1558`) and reports 0 for exactly the remediated calls
  this covariate exists to count [M-V5].
- A post-run verifier diffs on-wire against composed, attributes every
  divergence (remediation / reask / retry / contingent), and reports **injected
  bytes and injection count per arm × locale** as a covariate in the results,
  not a footnote.
- `contingent` divergence is measured here and reported alongside the §6.1
  residue statement.

## 13. Signed outputs

As v1, plus the Phase-2 artifact and the reliability record:

- `regime:manifest:v1` — manifest as loaded, pins resolved to concrete hashes.
- `regime:composition:v1` — the block table per arm × locale, **including
  annotator ids, κ, and the adjudication log** (§10.2.3).
- `regime:gate:v1` — every assertion and its verdict; skipped is recorded as
  skipped.
- `regime:onwire:v1` — the Phase-2 divergence report.

**Signing needs no new substrate crypto — it needs an upstream registry entry
[I-3].** `Engine.emit_attestation_self(input_json)` exists in ciris-server
0.5.151 (free-form `attestation_type`, canonicalize → SHA-256 → hybrid-sign;
zero in-repo callers today). But persist gates admission through a 95-row
`namespace_registry.json`, `regime:` is not in it, and the replication grant
covers `["capacity:","trace:"]` — so unregistered regime artifacts would be
signed and then **never leave the producing node**, which defeats "a reviewer
walks back to the composed prompt."

- **Upstream ask (CIRISPersist#571), filed, longest lead item of the whole
  design — STILL OPEN:** CIRISPersist registry entries for
  `regime:{manifest,composition,gate,onwire}:v1` plus an explicit replication
  decision for the prefix. That ask gates CEG-tier federation of regime
  artifacts and nothing below changes it.
- **The locally-signed path (LANDED, 2.9.9 / ciris-server 0.5.154, #977/#984):**
  the previously planned descope — hand-assembling a manifest and signing its
  bytes with `Engine.local_sign_hybrid` — is REPLACED by the substrate's
  purpose-built detached-object verb: `ciris_server.sign_object(path, label)`
  → signature JSON (manifest canonicalized, arbitrary bytes signable, NO graph
  write) and `verify_object(path, sig_json)` → bool. Wired as
  `compose_dump dump --sign` (label = the arm name — sealed INSIDE the signed
  envelope, so a dump cannot be relabelled into a different arm; for a
  campaign with hidden and visible arms that is the property that matters
  most) and `compose_dump gate --verify-sig` (accepts only a TRUE verify; an
  unperformable check refuses — a verifier that cannot tell "forged" from "I
  could not look" admits both; the sealed label must equal the dump's recorded
  arm). Label unchanged: **"locally signed, not CEG-signed"** — provenance,
  not warrant; reviewable on the producing node, honest about being neither
  mesh-visible nor CEG-admitted until the #571 registry ask lands.

All CEG-signed hybrid on the 2.9.7 path. Full prompts stay in the debug tee
(`traces/accord_full/lens-batch-*.json`), never in the CEG carrier — provenance,
not debugging.

## 14. Implementation order (2.9.9)

0. **File the CIRISPersist `regime:*` registry ask — this week** [I-3]. Cross-repo,
   gates §13 federation entirely, nothing in 2.9.8 can force it. Everything else
   proceeds against the local-tier descope meanwhile.
1. **Crisis resources into the corpus** — user-facing, independent of regimes.
2. **Composition seam extraction** [I-1, I-V2]: `compose_messages()` at six
   sites covering the eight composition points (TSASPDMA already has seams),
   its own PR, golden-bytes tests proving pre/post equality.
3. `compose --dump` against the named compose fixture [I-2], emitting the
   `(block_id, class, disposition)` table — unrouted regions emit `mixed`,
   which the gate refuses inside any varied class. Red until §11 lands is
   honest [I-4]; steps 3 and 5 therefore **interleave**, not sequence.
4. Gate Phase 1 (block-keyed) in CI.
5. **§11 step 0** — DEFER-policy routing, both copies, before any campaign;
   then remaining §11 routing incl. the `language_guidance` split.
6. R6 loader fix (refuse condition `"a"`), pinned-but-not-plumbed enforcement,
   `seed` plumbing on the OpenAI-compatible path, `LLM_ERROR_REMEDIATIONS`
   into `RESIDUE_SITES` [I-7].
7. **R2 reconciliation** [I-5]: the regime loader synthesizes one
   `ResearchOverrideManifest` per h3ere arm (own `residue_digest`), and R2's
   totality rule becomes *"every reachable field resolves to exactly one
   declared class"* — which requires the class annotation to be total before
   any strict-mode regime can load. R5 unchanged (arm `h3ere-blank` blanks all
   `accord.*` keys together, declared under `disable:`, never `replace:` —
   §12 assertion 2 rejects empty replacements by design [I-6]).
8. Class-set v2 annotation pass (two annotators, κ, adjudication log).
9. Regime manifest v2 schema + refusals.
10. Phase-2 on-wire verifier (per-attempt capture row at `service.py:1990`
    and/or instructor hooks); signed outputs incl. `regime:onwire:v1`.
11. **Direct-provider harness** — pulled FORWARD in practice [M-N4]: gate
    assertion 3's direct-provider half (step 4) may not ship unexercised
    against 2 of 5 arms, so a minimal compose-side stub of this harness lands
    WITH step 4, and the full runner before any campaign. The runner must
    reproduce the 9-turn arc **with conversational continuity** (the battery
    threads one channel_id through the arc — `safety_battery.py:90-93`); a
    stateless per-question runner changes the arc's meaning and is not the
    same instrument [M-V2]. Built against the same battery scorer.

---

## 15. Stated limitations (2.9.10)

Things known to be true of the instrument as shipped. Each is a limitation of
what a campaign may *claim*, not merely a to-do.

### 15.1 A composed prompt is not the same object as a populated YAML key  [#990]

Until 2.9.10 the coverage arithmetic in §1.3 counted **populated keys**, on the
assumption that a key present in a prompt YAML and loaded onto a
`PromptCollection` is a key the model reads. That assumption was false.
`DMAPromptLoader.get_system_message()` is an allowlist of six fields and drops
every other populated key silently; `BaseDSDMA` never used it at all. Three
blocks were authored, localized into 29 languages, and never composed —
`idma.closing_reminder` (the propaganda-pattern check) since v2.6.0,
`dsdma_base.response_format` (the LANGUAGE RULES block) since v2.3.1,
`tsaspdma.closing_reminder` since v1.9.5 — plus three more in
`action_selection_pdma` including the tool-hallucination guard.

Consequence for the *research* facility, which is why it belongs here: an
override that replaces an uncomposed key applies cleanly, logs a successful
replacement, and changes nothing the model sees. R2 totality over such a key is
satisfied and meaningless. **Coverage must be measured over composed bytes, not
declared keys** — the §12 ablation gate already is; the §1.3 arithmetic now
inherits `tests/.../test_prompt_key_consumption_990.py` as its floor.

### 15.2 A marker probe's negative result is uninterpretable without controls

"Key replaced with a marker, zero composed blocks moved" and "the harness
silently did nothing" are the same observation. This is not a hypothetical: an
early 29-locale sweep returned zero for **every** key including known-live ones,
because an active research manifest makes the conscience steps refuse an English
fallback for `am`. Any probe run that reports deadness MUST carry live sibling
controls through the identical path in the same sweep, and the evidence pack
MUST record them (`evidence/prompt_key_consumption_990.tsv`). A dark-key count
published without controls is not evidence.

### 15.3 The manifest is identified by path, not by content

`ComposeDumpMeta.manifest` and `trace_fields()["research_manifest"]` both carry a
filesystem path. `residue_digest` content-pins the surface overrides do *not*
cover, `fragment_count` pins scanner strength, and `sign_object` pins the output
bytes — but the input that **defines the arm** is named by a filename. Editing a
manifest in place between arms leaves both dumps claiming the same manifest,
with the same residue digest and valid signatures. The Phase-1 gate catches the
difference indirectly, by diffing composed blocks; the artifact set cannot
answer "which manifest produced this?" after the fact. Until a
`manifest_digest` (sha256 over `jcs_canonicalize`d bytes, per the 2.9.6 JCS cut)
is carried and gate-asserted, **no campaign may claim content-addressed
provenance of its independent variable.**

### 15.4 Carried forward

- **#987** — h3ere holds three distinct axiotic byte strings against one
  `inject: {axiotic: <corpus>}`; a varied class must be shown to cover every
  source hash.
- **#988** — the text tier is unsatisfiable as specified: `en` has no U-row
  instrument.
- **#991** — `tsaspdma` builds two blocks as hardcoded English in Python,
  shadowing 29 localized templates. Every user receives English. An override of
  the localized key applies and is then discarded.
- **#992** — four locales carry a LANGUAGE RULES key with no base counterpart
  and no schema field. Three translators independently concluded the base was
  missing a language-rules block; §15.1 shows they were right.
- `action_selection_pdma.final_ponder_advisory` remains outside the dump's
  reach — a fixture gap (it renders only at
  `current_thought_depth >= max_rounds - 1`), not a composer defect. It is
  therefore unverified by the gate, and a regime must not hold it.
