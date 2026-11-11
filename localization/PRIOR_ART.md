# The translation ratchet: what it rests on

CIRIS ships its prompts, ethics text and interface in 29 languages by machine
translation, and says so (`ciris.ai/crowdsourcing-alignment`: "CIRIS uses
machine translation extensively"). What stands between a model's draft and a
shipped string is the **ratchet**: translate, review by error span, repair,
gate deterministically, and never let a class of defect that reached zero come
back.

This note ties each part of that ratchet to work done elsewhere, and records
where the prior art says our version is weak. It was assembled from web
searches on 2026-11-11. Most sources were read as abstracts or search
summaries, not in full, so a claim here is a pointer to check, not a citation
to lean on.

## Part by part

| Our mechanism | Where it lives | Prior or convergent art | What the art warns about |
|---|---|---|---|
| **Review marks error spans with a category and severity**, not a score | evaluate lane (`localize.py`, `SYSTEM_REVIEW`) | MQM error analysis for MT: Freitag et al. 2021 [1]. LLMs as MQM annotators: AutoMQM (Fernandes et al. 2023) and GEMBA-MQM (Kocmi & Federmann 2023) [2] | LLM-marked spans overlap poorly with human ones; one summary of Lu et al. 2024 gives span precision near 9% for GEMBA-MQM [3]. A finding is a lead, not a verdict |
| **Repair fixes what was found, then is re-reviewed** | repair lane (`repair_until_clean`) | MQM-APE [3]: keep an error annotation only if post-editing it improves the translation | Same as above. It is why repair may return a value unchanged when it judges a finding wrong |
| **The reviewer is a different model family from the translator** | `LOCALIZE_REVIEW_MODEL` vs `LOCALIZE_LADDER` | Self-preference bias in LLM judges: Wataoka et al. 2024 [4]; an MT-specific EMNLP 2026 study [5]; M-GATE's three-provider judging [6] | The size varies by judge and direction, and is reported weaker out of English than into it [5]. A judge that lacks competence in the language is unreliable whatever its family [7] |
| **Each request carries this language's closest shipped text** | `anchors_for`; for prompts, `prompt_localize.make_anchors` | Fuzzy translation-memory matches as few-shot examples beat random examples and zero-shot: Moslem et al. 2023 [8]; token vs embedding retrieval compared in [9] | Models sometimes copy a fuzzy match unchanged. Anchors here are never written as values, and a sibling block that fails the structural check is not offered |
| **A value that would not render is refused, by code** | `prompt_problems`, `structural_problems`, `check_placeholders` | Format-string checks in translation platforms, e.g. Weblate's Python brace format check [10] | Weblate's check is opt-in per string. Ours is unconditional because a broken prompt is a broken agent, not a cosmetic defect |
| **Text left in the source language counts as untranslated** | `prompt_localize.locale_bundle`; the chain tests' 30% script ratio and 35% English-stopword ceilings | Wikipedia Content Translation blocks publishing at 95% unmodified machine translation, warns at 85%, and treats 60% copied source as a problem, with per-wiki overrides [11] | Thresholds are tuned per community there. Ours are one number for 28 languages |
| **A repaired class of defect cannot return; standing debt does not block** | `check_localization_integrity --fail-on`, `prompt_localize --verify --changed` | Lint ratchets with a baseline that may only shrink: Notion's ESLint ratcheting, `imbue-ai/ratchets`, and similar tools [12] | A static ratchet puts no pressure on existing debt. Some tools also fail when a count drops and the baseline was not lowered, to lock the gain in [12] |
| **Machine review is not native review** | lane commits label their values `status=draft` / `machine_reviewed`; an existing value is replaced only when `overwrite` is set (DMA prompt files carry no status field) | Professional translators with full context rank systems differently from crowd raters, who tolerate subtle errors [1] | See below |

## The theory behind it, and what it converges with

The working theory: every pass draws latent grammar and vocabulary out of the
models; each accepted improvement becomes context for the next pass and exposes
the next gap; the loop only improves if it keeps being made to face reality
(safety batteries, reports from deployments); and what survives is hardened so
it cannot be lost. The same shape is applied to ethics as the coherence
ratchet. Rows marked (m) are from memory and were not looked up for this note.

| Claim | Convergent work | What it adds or warns |
|---|---|---|
| A model knows more of a language than a single prompt elicits, and the right context draws it out | MTOB: an LLM translating Kalamang from a grammar book and word list in context [13]; fuzzy-match exemplars [8] | A follow-up found most of MTOB's gain came from the parallel examples in the book, not the grammar prose [14]. Examples pump better than explanations |
| Accepted outputs become the next pass's training signal | Bootstrapping and self-training (Yarowsky 1995) (m); iterative back-translation with filtering [15]; DSPy's bootstrapped demonstrations, kept only if they pass a metric [16]; Self-Refine, Voyager's verified skill library, STaR (m) | Every one of these keeps only what a check accepts. The loop is as good as the check: "the optimizer is only as good as your validation metric" |
| The loop must face reality or it degrades | Model collapse under recursive training, avoided when real data is accumulated alongside synthetic, not replaced by it [17] | Disputed at the margins [17], but the direction is agreed: a loop fed only its own output drifts. Native-speaker edits and deployment reports are the real data here |
| Gains must be made impossible to lose | Tomasello's ratchet effect in cumulative culture: invention is common, the stabilising ratchet is "the difficult feat" [18]; baseline ratchets in software [12]; regression tests (m) | Same name, same claim. The hard part is retention, not novelty |
| Ethics improves through accumulated earnest attempts tested against cases | Reflective equilibrium, and its recent application to LLM alignment [19]; common-law precedent and casuistry (m); Popper and Lakatos on conjecture tested against reality (m) | Reflective equilibrium requires revision in BOTH directions: cases revise principles too. The critique of constitution-style alignment in [19] is that principles rarely move |
| Measured against batteries | Evaluation-driven development (m) | Goodhart's and Campbell's laws (m): a battery that is optimised against stops measuring. #983 is this, already found in this repo |

What looks unusual here is the combination, not any part: one ratchet over
translation and ethics alike, with the hardening step deterministic and in CI,
and the stated plan to make native speakers and deployments the source of real
data rather than an afterthought.

## Where native speakers come in

`ciris.ai/crowdsourcing-alignment` is the human half. It lets a native speaker
open the actual per-locale files (strings, ethics text, guide, DMA prompts,
conscience prompts, glossary, safety battery) and propose an edit through a
pre-filled GitHub issue labelled `crowdsourcing-alignment` and `locale-<code>`,
asking whether the reporter is a native speaker and whether others reviewed
it. It states its own limits: machine-checkable criteria run in CI and hard
fails block a release for that locale; native-speaker review of the softer
cases "is not in place yet"; a federated flow with consensus and voting
(`rubric_proposal`, `arc_question`, `prompt_edit`) is planned in CIRISNodeCore.

That division matches the literature. Deterministic checks and span-level
machine review catch structure and gross meaning. They are weakest in exactly
the languages CIRIS prioritises (am, ha, yo), where a judge's own competence
is the limit [7]. The ratchet's job is to make sure a native speaker's time is
spent on judgment, not on finding a dropped placeholder.

## Gaps the art points to

1. **No burn-down on standing debt.** `--verify` lists 28 broken-placeholder
   fields in the DMA prompts and `--changed` rightly does not block on them, but
   nothing makes the number fall. A committed ceiling that may only be lowered
   [12] would.
2. **Reviewer competence is assumed, not measured, per language.** One
   reviewer model judges all 28. For the lowest-resource locales a second
   judge, or agreement between judges, would say when a clean review means
   little [6][7].
3. **Retrieval is lexical.** Anchors are picked by token overlap. Embedding
   retrieval is reported to do better [9]; whether it matters at this corpus
   size is untested.
4. **Accepted native edits are protected only by convention.** The lane does
   not replace an existing value unless `overwrite` is set, and the docs ask
   for exact keys with it, but nothing records that a value came from a native
   speaker or stops a broad overwrite from replacing it.
5. **The website page lists seven DMA prompts.** There are now nine
   (`rsaspdma.yml`, `fsaspdma.yml`); the page is in `CIRISAI/ciris-website`.

## Sources

1. Freitag et al., "Experts, Errors, and Context: A Large-Scale Study of Human Evaluation for Machine Translation", TACL 2021. <https://transacl.org/ojs/index.php/tacl/article/view/3203>
2. Kocmi & Federmann, "GEMBA-MQM: Detecting Translation Quality Error Spans with GPT-4", 2023. <https://arxiv.org/abs/2310.13988> (introduces itself against AutoMQM, Fernandes et al. 2023)
3. "MQM-APE: Toward High-Quality Error Annotation Predictors with Automatic Post-Editing in LLM Translation Evaluators", 2024. <https://arxiv.org/html/2409.14335v2>
4. Wataoka et al., "Self-Preference Bias in LLM-as-a-Judge", 2024. <https://arxiv.org/abs/2410.21819>
5. EMNLP 2026 main-conference paper on self-bias with machine translation as the testbed. <https://aclanthology.org/2026.emnlp-main.629.pdf>
6. "M-GATE: Multilingual Grammar, Accuracy in Translation, and Efficiency Benchmark for Large Language Models". <https://arxiv.org/pdf/2608.03803>
7. "Are LLM Evaluators Really Narcissists? Sanity Checking Self-Preference Evaluations", ICML 2026. <https://icml.cc/virtual/2026/poster/61230>
8. Moslem et al., "Adaptive Machine Translation with Large Language Models", 2023. <https://arxiv.org/abs/2301.13294>
9. EAMT 2026 paper comparing token-based fuzzy matching with embedding retrieval for few-shot selection. <https://aclanthology.org/2026.eamt-1.34.pdf>
10. Weblate documentation, "Checks and fixups" (Python brace format). <https://docs.weblate.org/en/weblate-5.13/admin/checks.html>
11. MediaWiki, "Help:Content translation/Translating/Translation quality", and the limit proposal. <https://www.mediawiki.org/wiki/Help:Content_translation/Translating/Translation_quality/sv>, <https://phabricator.wikimedia.org/T251887>
12. Notion, "How we evolved our code: Notion's ratcheting system using custom ESLint rules". <https://www.notion.com/fr/blog/how-we-evolved-our-code-notions-ratcheting-system-using-custom-eslint-rules>; `ratchets` (imbue-ai). <https://docs.rs/crate/ratchets/0.2.6>
13. Tanzer et al., "A Benchmark for Learning to Translate a New Language from One Grammar Book" (MTOB), ICLR 2024. <https://arxiv.org/abs/2309.16575>
14. Aycock et al., "Can LLMs Really Learn to Translate a Low-Resource Language from One Grammar Book?", 2024. <https://arxiv.org/html/2409.19151v2>
15. Imankulova et al., filtered pseudo-parallel corpora, WAT 2017. <https://aclanthology.org/W17-5704/>; Galiano-Jiménez et al., EAMT 2023. <https://aclanthology.org/2023.eamt-1.7.pdf>
16. DSPy, BootstrapFewShot. <https://dspy.ai/api/optimizers/BootstrapFewShot/>
17. Gerstgrasser et al., "Is Model Collapse Inevitable? Breaking the Curse of Recursion by Accumulating Real and Synthetic Data", 2024. <https://arxiv.org/abs/2404.01413>; follow-up "Collapse or Thrive?". <https://arxiv.org/html/2410.16713v1>
18. Tennie, Call & Tomasello, "Ratcheting up the ratchet: on the evolution of cumulative culture", Phil. Trans. R. Soc. B 2009. <https://pmc.ncbi.nlm.nih.gov/articles/PMC2865079>
19. Brophy, "Wide Reflective Equilibrium in LLM Alignment", 2025. <https://arxiv.org/abs/2506.00415>
