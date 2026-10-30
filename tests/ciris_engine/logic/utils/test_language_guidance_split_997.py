"""The ``prompts.language_guidance`` prose split (#997) — proof, not intent.

``language_guidance`` was 13,694 B at ``en`` of one ``mixed`` block: register
doctrine, categorical prohibitions, crisis-line world-facts and value claims
interleaved sentence by sentence in a single JSON scalar. ``mixed`` defaults to
refuse, so none of it could be held or varied — a values arm holding this block
kept CIRIS's own "route serious symptoms to professional care without
minimization" byte-identical inside the alt-values condition, with every
Phase-1 assertion green. That is the §10.2.1 bias-toward-the-null confound the
block table exists to catch.

The split cuts the prose into 29 consecutive slices in the five locales whose
text is line-for-line parallel to English, and the composer joins them with
``""`` and strips once. **The only thing standing between that and a silent
prompt mutation in a locale nobody runs goldens on is the reassembly proof in
this file**, so it is pinned by sha256 per locale, for all 29 — split and
unsplit alike.

The twelve golden tests in ``tests/.../test_compose_messages_golden.py`` are the
other half of the net: ``language_guidance`` composes into every DMA step, so an
off-by-one byte fails them at ``en``. This file is what covers the other 28.

THE GOLDENS ARE NOT A NET FOR THIS FILE — corrected after adversarial review.

``compose_golden.py:163`` patches ``get_language_guidance`` with
``_sentinel_language_guidance``, which returns ``<GOLDEN-LANGUAGE-GUIDANCE
lang=en>``; every golden file contains that sentinel exactly once. The real
corpus never reaches them, so a byte change in ``language_guidance`` CANNOT
fail a golden.

There is ONE net: the per-locale sha256 + byte-length digests below, pinned
from the corpus as it stood BEFORE the split. That net is sufficient — it
covers all 29 locales including the 24 left whole, which is more than the
goldens would have given. But the commit message and an earlier version of this
docstring claimed two nets, and a reviewer who believed it would have trusted a
check that does not run. Asserting verification that was not performed is the
defect class this whole cut exists to remove; it is recorded here rather than
quietly deleted.

SPLITTING ALL 29 LOCALES IS OUT OF SCOPE, AND NOT REQUIRED FOR A TORQUE SERIES.

Split: en, es, fr, it, pt — the five whose line-type fingerprint matches English
exactly. Whole: the remaining 24, including every Tier-0 locale (am 25,338 B /
277 lines, yo 24,574 B / 212, ha 18,788 B / 206 — against en's 13,694 B / 123).

No mechanical boundary transfers. ``my`` has no section markers at all, ``hi``
numbers 1-12, ``uk`` renumbers to 6a-6d, ``fa``/``ur`` open at section 4, bullet
counts run 5 to 50. Mapping 29 class boundaries onto each would mean
re-segmenting target-language prose 24 times, and byte-identical reassembly
proves only that the pieces rejoin — a cut in the WRONG PLACE reassembles
perfectly and silently mis-classes the text. Each locale therefore needs a
native-language semantic read, which is the cost that makes this prohibitive
here and appropriate for RATCHET to take per-locale, as needed.

What it costs a campaign: in an unsplit locale ``language_guidance`` stays
``mixed`` and therefore REFUSES, which is the correct conservative behaviour. A
series still runs — it is bounded, not blocked. An arm carrying a measurable
axiotic contrast must either run in a split locale or declare the confound
explicitly. The Tier-0 gap is real and worth closing on mission grounds; it is
not a TORQUE blocker.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple

import pytest

from ciris_engine.logic.utils.compose_dump import BLOCK_ANNOTATIONS, annotation_for
from ciris_engine.logic.utils.localization import (
    LANGUAGE_GUIDANCE_PART_KEYS,
    UNIVERSAL_GUIDANCE_PART_KEYS,
    clear_cache,
    get_language_guidance,
    language_guidance_part_keys,
    language_guidance_parts,
    universal_guidance_part_keys,
    universal_guidance_parts,
)
from ciris_engine.schemas.dma.compose import BlockClass

REPO_ROOT = Path(__file__).resolve().parents[4]
BUNDLE = REPO_ROOT / "ciris_engine" / "data" / "localized"

#: The locales whose prose partitions on the English boundaries. Established by
#: a line-type fingerprint (heading / bullet / numbered / indented / text) that
#: is IDENTICAL to English for exactly these five, then read paragraph by
#: paragraph to confirm the semantic correspondence before cutting.
SPLIT_LOCALES: Tuple[str, ...] = ("en", "es", "fr", "it", "pt")

#: ``(sha256, bytes)`` of the COMPOSED block per locale — of what the model
#: receives, after the single ``.strip()``.
#:
#: **These are captured from the corpus as it stood BEFORE the split** (commit
#: 2cfd7ec2d, `prompts.language_guidance` a plain scalar in all 29 files). They
#: are the pre-image, not a snapshot of the post-split output — regenerating
#: them from the file the change just wrote would prove nothing at all. Twelve
#: golden tests cover ``en``; these cover the other 28, which have no goldens
#: and are exactly where a dropped separator would hide.
#:
#: DELIBERATE CONTENT CHANGE, 25 of 29 (#1010): the §7e directional guard was
#: added — as `26b_user_symptom_direction` in the split locales, appended after
#: the cross-cluster section in the unsplit ones — and fr §12 was rewritten to
#: state its rule without rendering the violation as a quotable sentence. Every
#: line below carrying `#1010 §7e guard` therefore no longer describes the
#: pre-split corpus: it describes the corpus WITH the guard, and the whole
#: delta is content we chose, NOT a split artifact. Each was re-pinned only
#: after confirming the byte delta equals the guard text plus its separators.
#:
#: FOUR locales keep their pre-image pins and carry NO guard: `ha`, `ko` and
#: `zh` failed back-translation review (ha: wrong `cross-cluster` coinage plus
#: a false claim about its own examples; ko: a translator-authored carve-out
#: that subordinates the exclusion rule to the asked/not-asked test, merging
#: claim 2 into claim 1; zh: an added gloss that falsely states both incorrect
#: examples refer the user to a professional). `sw` already states the rule
#: natively at its own §7e and is the locale the guard was reconstructed from.
#: A mistranslated guard reads as coverage, so those four stay unguarded until
#: their fixes land rather than shipping prose nobody could verify.
#:
#: SECOND DELIBERATE CONTENT CHANGE, 20 of 29 (#1010, `§26 reconciled`): the
#: cross-cluster PATTERN block said the CORRECT pattern is clustering that
#: "surfaces what condition is or isn't present", quoting the exclusion move
#: («doesn't match psychosis») approvingly — the exact move the §7e guard in
#: the same file calls a violation. The primer told the agent both things. A
#: live French battery on the contradicted corpus produced a hard-fail whose
#: cited span merely MOVED from « critères de la psychose » to « critères de
#: la schizophrénie »: the agent followed the concrete worked example over the
#: abstract rule. `en`/`fr` were reconciled by hand in 90b11c464; the 20 lines
#: below carrying `§26 reconciled` are that same reconciliation rendered per
#: locale — ASKED-ABOUT is licensed, the explanation stays on the CATEGORY,
#: "you don't have X" is named forbidden, the wellness-verdict ban is intact,
#: and the did-NOT-ask case (no cluster answer at all — receive and route) is
#: stated for the first time. In 13 locales (`ar`, `de`, `es`, `it`, `ja`,
#: `mr`, `my`, `pt`, `ru`, `sw`, `tr`, `uk`, `yo`) that REPLACED contradictory
#: prose; in 7 (`am`, `bn`, `fa`, `hi`, `id`, `ur`, `vi`) there was no PATTERN
#: block at all and it is a net-new INSERTION, so those files gain the
#: doctrine rather than trade it.
#:
#: STILL OUT, FLAGGED NOT FIXED: the same "surfaces what condition is or isn't
#: present" claim also survives in the §1 no-wellness-confirmation bullet
#: (`en` `05_no_wellness_confirmation` and its locale mirrors, e.g. `de` and
#: `ru` §1), and several §7c worked exemplars still model «doesn't match
#: psychosis» as the CORRECT response — `en`'s own `25_exemplar_cross_cluster`
#: included. Those are a separate cut; this one is scoped to the PATTERN
#: block, which is what the French battery measured the agent following.
#:
#: NINE locales are NOT reconciled and keep their prior pins: `ha`/`ko`/`zh`
#: (still unguarded, above); `th`/`pa`/`te` (drafts failed review — `th` never
#: carried the contradiction and the block would dangle with no exemplar above
#: it; `pa` still models the exclusion inside its own §7c approved answer, so
#: an insertion-only patch reproduces the French configuration; `te`'s draft
#: shipped its own fix in the wrong field and imported an unanchored suicidal-
#: ideation directive); `ta` (has no cross-cluster section at all — its draft
#: was a different fix, the §3d false incorrect-examples header, which belongs
#: to the fa/ru/ta/te/ur/yo header sweep, not here); `en`/`fr` already done.
#:
#: THIRD DELIBERATE CONTENT CHANGE, 7 of 29 (`U6 register fix`): the block's
#: own instructions were written in the informal second person its register
#: rule forbids («MANTÉN REGISTRO FORMAL», «Usa el nombre», «Cuando aclares»;
#: fr «Maintiens / Fournis / Utilise-la»; it «Mantieni / Non attribuire»; de
#: du-imperatives and Sie+du-verb hybrids «Sie hegst», «Du musst», inside the
#: CORRECT exemplars; am «ተከተል / ስጥ / አትጻፍ»; yo «o / rẹ»; ha «Kar ka»).
#: es 1.3 answered in tú 9/9. Rewritten to each locale's own prescribed form
#: (usted / vous / Lei / Sie / እርስዎ / ẹ-yín / ku); quoted user speech and
#: shown WRONG forms untouched. Guarded by test_language_guidance_register.py.
COMPOSED_SHA256: Dict[str, Tuple[str, int]] = {
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "en": ("4333cc5657ac45e453497896448c88cd31f4dd610f4021cbadfba8530d80b071", 17181),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "am": ("fdac6c92cb28ece7a7cbcf69a33b1d279ebd7ed61063736611fdc1c11e06ef26", 33860),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "ar": ("d6334dc85d406d97ce10798612985ad53be85ac3654382ab5989b73fa0b55541", 24076),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "de": ("b7aad87c7838536510bdcb22eb063492660f24cf5a439e1a10b443cf5a6b32e0", 21094),
    # 18628 -> 17921 (2026-10-29): the U1 category-only rewrite of the four
    # universal parts (05/25/26/26b), drafted by the i18n translate lane from en
    # 4808efd98 and then hand-corrected to usted (04_formal_register). The es
    # glossary's "tú for chat messages" rule had put the exemplar speech in tú.
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "es": ("4526c81517d590bcf3c2e229775acff1c07b722ce703bf6fc757dde26a2d70aa", 19394),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "fr": ("dd2aff33541a8afe3f33ec34e6afdba65f0798a5a678efe5d61ebb49cbbe00e8", 23747),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "hi": ("85435eccf58599a6613f22be337bfc6518089598117a4914581259808b9e5dab", 37346),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "it": ("e9faaa11f9ec0c531a9b3aa0cf0906796fe247b4af2004a77dc2495672fa6400", 19273),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "ja": ("93fa14d148a0329ebcd218fa4b6b8d669a953b7454438bd06adcbc08c5c49bf6", 31458),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "ko": ("ea935b0bee524e4ae9810fb3163b896a5dc6aaa1a42bad22ed69de105ab0057a", 29791),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "pt": ("988e73dc6772d2cabff2926a098df7add887cb8287cc352febf8b7a299916e97", 19162),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "ru": ("4daab895c369ff716b1c4c76f0152cdedb3dd8ab9e89463aa00ca90396049b5d", 33195),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "sw": ("da4f84c7fefa87e66c62b9464e8e8ac0a9954586eb072f407582b2693bd700de", 18172),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "tr": ("be3c8a1e4c7ac6c034a239f746b5a57d9de13d20c50e9e6c7aac95a9bc694d27", 18666),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "zh": ("1074ad24ac62b7cbdedfed16e85d00cac7bc551d39a84efa081cfa8b62f92efe", 16467),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "ur": ("38ab31d5645f784a6f21e70bc6b4ce3d9f3c7e1cf964494b8e08dd1f94a068bf", 31116),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "bn": ("2565b064a95e8a87211845a4c51d9b4966d76efe65329d88e08b6d549bf3d2d9", 38978),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "fa": ("033de1e81f724a1d334f953e80c7218abf1434a4466aa0df138e91ddb13028ec", 39867),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "ha": ("f3a5ff0af87288219e9f4321eda1c7be6fe908c5a4d95bbde9a10d2fd1d9216f", 22907),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "id": ("8cf05332ab732c04bbd8c00133b2f36beb22384602cecebf837d30f767ce5df2", 19868),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "pa": ("421d9cb05d39dce96a06936e5147f6eb4c81e43677eb68df6ce46e7a6fb74b5c", 37428),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "ta": ("01cddcf176b5645eb315aaad75325f71d224d773f5ce3fa3d09c39eb74efe690", 47220),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "te": ("2d06449636efac3356d20e95c6932eda469a4a953895cdaf3377ac77bef213da", 42798),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "vi": ("435029e855254b664074eae8928a1fab9958694e6b8b284099836c7714d00a7d", 24531),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "mr": ("0efe6b2388f5452f76e27df6fe4db801ba53b82aeefe0a2ba696efc1b7435c8f", 35481),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "my": ("6990dda0df13b15b82279613dcbb91c78c7faf83a671906df64d854c38973ad2", 54391),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "th": ("d6bad8e8cd9e16d04684ddc7e0be36517eb3b8d5b7b9fcd6904e3835d52e1f68", 40880),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "uk": ("4980a41215fa85575c425ab33648903efa6c0fcb5281486514b5547bafc026b1", 40821),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    "yo": ("2bc746c3fafab0bc190faa247ae6e5ecd7359a020d4289ed19f8253c3c54310e", 27095),
}

#: What the split bought at ``en``, in bytes. A ratchet on the number that
#: matters: entry counts can be reshuffled between registers, bytes cannot.
# 16029 after #1010 added the §7e guard (was 13694 at the split).
# 16303 -> 16307: four bytes, and none of them prose. `26_cross_cluster_pattern`
# and `26b_user_symptom_direction` were missing their trailing blank line, so the
# join (which is `"".join` — every part carries its own separator) glued the next
# section header onto the previous sentence: `...who can give it.== 7e. A CLINICAL
# NAME...`. The §7e guard was rendering mid-paragraph instead of as a section.
# Two separators x two newlines. MIXED is untouched at 4402 — the quantity this
# ratchet exists to protect did not move.
# 16307 -> 15858 (U1, 2026-10-29). The cross-cluster parts stopped teaching a
# determination: §25's CORRECT RESPONSE no longer sets the user's account beside
# the category ("dark thoughts of the kind you describe are a different sort of
# experience") and its WRONG specimen is gone; §26 drops its worked comparison;
# §26b's second exemplar and its quoted verdicts went abstract; §05 loses the
# "cross-cluster discrimination ('this isn't psychosis')" licence. Every byte of
# the delta is in those four parts. Failing q04/U1 spans matched the old §25
# nearly word for word in ru, ha, hi, es, pt, mr and yo.
# 2.18.0 stigma words: +753 B deontic (universal 05b_no_stigma_words, the rule the
# coherence conscience already applied) and -8 B (" / crazy" left the §18 example,
# so the guidance no longer renders the word it forbids). Mixed bytes unchanged.
# 2.18.0 register pressure: +578 B deontic (universal 05c_warmth_without_a_new_role,
# AI identity holds when the user offers a friend role). Mixed bytes unchanged.
EN_TOTAL_BYTES = 17181
# 4189 -> 4402 (#1010). The cross-cluster EXEMPLAR is a `mixed` block, and
# fixing it made it longer: its CORRECT RESPONSE used to model the exclusion
# ("what you're describing doesn't match psychosis") — the exact move §7e
# forbids — so §25 taught the violation while §26b prohibited it. The
# replacement keeps the explanation on the CATEGORY and declines the
# determination, which costs words.
#
# The ratchet is RIGHT to flag it: 213 more bytes the ablation can neither
# hold nor vary. Raised deliberately, for a correction, and named — a silent
# bump here would be indistinguishable from the surface quietly rotting.
EN_MAX_MIXED_BYTES = 4271  # the five FSD-irreducible worked exemplars; 4402 -> 4271 with the U1 §25 rewrite
EN_MIN_AXIOTIC_BYTES = 429  # parts 09 and 11 — 0 before the split


#: Every part that composes into the block, as the BLOCK name it reports under:
#: the language parts plus the four that standardized into
#: ``prompts.universal_guidance`` (same names, same slots). Sorted by part key,
#: which is composition order across both subtrees.
ALL_PART_BLOCKS: List[str] = [
    block
    for _, block in sorted(
        [(key, f"language_guidance.{key}") for key in LANGUAGE_GUIDANCE_PART_KEYS]
        + [(key, f"universal_guidance.{key}") for key in UNIVERSAL_GUIDANCE_PART_KEYS]
    )
]


def _all_parts(lang: str) -> List[Tuple[str, str]]:
    """``(block_name, text)`` for every part the composer joins, in its order."""
    merged = [(key, f"language_guidance.{key}", text) for key, text in language_guidance_parts(lang)] + [
        (key, f"universal_guidance.{key}", text) for key, text in universal_guidance_parts(lang)
    ]
    return [(block, text) for _, block, text in sorted(merged)]


def _bundle_value(lang: str) -> object:
    data = json.loads((BUNDLE / f"{lang}.json").read_text(encoding="utf-8"))
    return data["prompts"]["language_guidance"]


def _bundle_universal(lang: str) -> Dict[str, str]:
    data = json.loads((BUNDLE / f"{lang}.json").read_text(encoding="utf-8"))
    universal: Dict[str, str] = data["prompts"].get("universal_guidance", {})
    return universal


def _manifest_languages() -> List[str]:
    manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
    return list(manifest["languages"])


@pytest.fixture(autouse=True)
def _fresh_localization_cache() -> None:
    clear_cache()


# --------------------------------------------------------------------------
# 1. Byte-identical reassembly — the load-bearing proof
# --------------------------------------------------------------------------


@pytest.mark.parametrize("lang", SPLIT_LOCALES)
def test_split_locale_parts_reassemble_to_the_composed_block(lang: str) -> None:
    """``"".join(parts).strip()`` IS the block. Byte for byte, in the stated order.

    Order is ``sorted()`` over the part keys, which the numeric prefix makes
    equal to composition order — so no JSON normalizer or translator tool can
    reorder the prompt by touching key order in the file.
    """
    value = _bundle_value(lang)
    assert isinstance(value, dict), f"{lang} is expected to be split"

    parts = language_guidance_parts(lang)
    assert [k for k, _ in parts] == sorted(value), "parts must be resolved in sorted-key order"

    # The universal parts join the same block, interleaved by key.
    universal = _bundle_universal(lang)
    merged = {**value, **universal}
    assert len(merged) == len(value) + len(universal), "a part key lives in both subtrees"
    joined = "".join(text for _, text in _all_parts(lang))
    assert joined == "".join(merged[k] for k in sorted(merged))
    assert joined.strip() == get_language_guidance(lang)


@pytest.mark.parametrize("lang", sorted(COMPOSED_SHA256))
def test_every_locale_composes_the_same_bytes_it_did_before_the_split(lang: str) -> None:
    """THE regression guard, for all 29 — the 24 unsplit locales included.

    A locale with no golden test is exactly where a dropped separator hides.
    Any per-part ``.strip()`` — by a JSON normalizer, a localization integrity
    tool, a translator pipeline — lands here as a changed digest instead of as
    a silently shortened prompt in production.
    """
    expected_sha, expected_bytes = COMPOSED_SHA256[lang]
    composed = get_language_guidance(lang).encode("utf-8")
    assert len(composed) == expected_bytes, f"{lang}: {len(composed)} B, pinned {expected_bytes} B"
    assert hashlib.sha256(composed).hexdigest() == expected_sha, (
        f"{lang}: composed language_guidance changed. The split must be a partition of the "
        f"same bytes — a mismatch here is a production prompt mutation in a locale that may "
        f"have no golden test."
    )


def test_the_digest_pins_cover_every_manifest_language() -> None:
    """A locale that quietly leaves the pin table would be unguarded."""
    assert sorted(COMPOSED_SHA256) == sorted(_manifest_languages())


# --------------------------------------------------------------------------
# 2. Shape invariants
# --------------------------------------------------------------------------


def test_a_locale_carries_the_parts_or_the_scalar_never_both() -> None:
    """Two live sources for one block is a precedence ambiguity that silently
    picks a winner. The corpus shape forbids it by construction."""
    for lang in _manifest_languages():
        value = _bundle_value(lang)
        assert isinstance(value, (str, dict)), f"{lang}: unexpected type {type(value)}"
        if isinstance(value, dict):
            assert lang in SPLIT_LOCALES, f"{lang} is split but not declared in SPLIT_LOCALES"
        else:
            assert lang not in SPLIT_LOCALES, f"{lang} is declared split but carries a scalar"


def test_split_locales_carry_exactly_the_canonical_part_keys() -> None:
    """One key space across the split locales, and it is the tuple the composer
    joins — so an override key that works at ``en`` works at ``pt``."""
    for lang in SPLIT_LOCALES:
        assert language_guidance_part_keys(lang) == tuple(sorted(LANGUAGE_GUIDANCE_PART_KEYS)), lang
        assert universal_guidance_part_keys(lang) == tuple(sorted(UNIVERSAL_GUIDANCE_PART_KEYS)), lang


def test_part_keys_sort_into_composition_order() -> None:
    """The numeric prefix is not decoration: lexical order IS prompt order."""
    assert tuple(sorted(LANGUAGE_GUIDANCE_PART_KEYS)) == LANGUAGE_GUIDANCE_PART_KEYS
    assert tuple(sorted(UNIVERSAL_GUIDANCE_PART_KEYS)) == UNIVERSAL_GUIDANCE_PART_KEYS
    # Disjoint, so the merged sort has exactly one slot per key.
    assert not set(LANGUAGE_GUIDANCE_PART_KEYS) & set(UNIVERSAL_GUIDANCE_PART_KEYS)


def test_unsplit_locales_resolve_through_the_parent_key() -> None:
    """The 24 that keep the scalar must still compose non-empty guidance —
    the split may not quietly blank a locale."""
    for lang in _manifest_languages():
        if lang in SPLIT_LOCALES:
            continue
        assert language_guidance_part_keys(lang) == ()
        assert get_language_guidance(lang), f"{lang}: composed guidance is empty"


# --------------------------------------------------------------------------
# 2b. The universal_guidance move — same block, same bytes, never English
# --------------------------------------------------------------------------


def test_the_universal_parts_left_language_guidance() -> None:
    """A part lives in exactly one subtree: none of the moved keys may linger
    in a split locale's language_guidance, where the pipeline would not reach it."""
    for lang in SPLIT_LOCALES:
        value = _bundle_value(lang)
        assert isinstance(value, dict)
        lingering = set(value) & set(UNIVERSAL_GUIDANCE_PART_KEYS)
        assert not lingering, f"{lang}: {sorted(lingering)} still under prompts.language_guidance"


def test_a_scalar_locale_without_universal_parts_composes_its_scalar_exactly() -> None:
    """The 24 scalar locales carry no universal part today; their block must be
    the stripped scalar and nothing else (the digest pins above prove the same
    bytes; this states WHY they hold)."""
    for lang in _manifest_languages():
        if lang in SPLIT_LOCALES or _bundle_universal(lang):
            continue
        scalar = _bundle_value(lang)
        assert isinstance(scalar, str)
        assert universal_guidance_parts(lang) == []
        assert get_language_guidance(lang) == scalar.strip(), lang


def test_a_universal_part_is_never_filled_from_english(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """R4: a locale composes only the universal parts its OWN bundle carries.

    A locale missing one (not yet translated by the pipeline) composes without
    it — never with English text spliced in through ``get_string``'s fallback.
    """
    import ciris_engine.logic.utils.localization as loc

    de = json.loads((BUNDLE / "de.json").read_text(encoding="utf-8"))
    # Every locale is translated now; build an untranslated one by dropping its parts.
    de["prompts"].pop("universal_guidance", None)
    marker = "UNIVERSAL-05-IN-THE-LOCALE\n\n"
    de["prompts"]["universal_guidance"] = {"05_no_wellness_confirmation": marker}
    (tmp_path / "de.json").write_text(json.dumps(de, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "en.json").write_text((BUNDLE / "en.json").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(loc, "_get_localization_dir", lambda: tmp_path)
    loc.clear_cache()
    try:
        assert universal_guidance_part_keys("de") == ("05_no_wellness_confirmation",)
        composed = get_language_guidance("de")
        assert composed == (de["prompts"]["language_guidance"].rstrip() + "\n\n" + marker).strip()
        english = _bundle_universal("en")
        leaked = [key for key, text in english.items() if text.strip() and text.strip() in composed]
        assert not leaked, f"English universal parts leaked into de: {leaked}"
    finally:
        loc.clear_cache()


def test_no_part_is_empty() -> None:
    """An empty part is a boundary in the wrong place — it contributes nothing
    and its block would be a zero-byte row the gate cannot compare."""
    for lang in SPLIT_LOCALES:
        empty = [block for block, text in _all_parts(lang) if not text]
        assert not empty, f"{lang}: empty parts {empty}"


def test_mirrors_carry_the_same_split_as_the_source_bundle() -> None:
    """The five client bundles are byte-mirrors. A split that lands in the
    source and not in the mirrors ships a different prompt on mobile."""
    mirrors = [
        "apps/android/src/main/assets/localization",
        "apps/ios/iosApp/localization",
        "apps/ios/Resources/app/localization",
    ]
    source = {lang: _bundle_value(lang) for lang in _manifest_languages()}
    for mirror in mirrors:
        for lang, expected in source.items():
            path = REPO_ROOT / mirror / f"{lang}.json"
            if not path.exists():  # pragma: no cover - optional bundle
                continue
            prompts = json.loads(path.read_text(encoding="utf-8"))["prompts"]
            assert prompts["language_guidance"] == expected, f"{mirror}/{lang}.json: language_guidance diverges"
            assert prompts.get("universal_guidance", {}) == _bundle_universal(lang), (
                f"{mirror}/{lang}.json: universal_guidance diverges from source"
            )


# --------------------------------------------------------------------------
# 3. What the split bought — the byte ratchet
# --------------------------------------------------------------------------


def _en_class_bytes() -> Dict[BlockClass, int]:
    totals: Dict[BlockClass, int] = {}
    for block, text in _all_parts("en"):
        annotation = annotation_for(f"pdma.{block}")
        totals[annotation.block_class] = totals.get(annotation.block_class, 0) + len(text.encode("utf-8"))
    return totals


def test_every_part_is_annotated_explicitly() -> None:
    """A part resolving through the ``mixed`` fallback would be a silent
    regression that still refuses — honest, but invisible."""
    missing = [block for block in ALL_PART_BLOCKS if block not in BLOCK_ANNOTATIONS]
    assert not missing, f"language_guidance parts with no explicit annotation: {missing}"


def test_the_mixed_share_of_language_guidance_only_shrinks() -> None:
    """A ratchet on BYTES. Entry counts can be moved between registers; the
    bytes the ablation cannot address cannot be moved anywhere."""
    totals = _en_class_bytes()
    assert sum(totals.values()) == EN_TOTAL_BYTES
    mixed = totals.get(BlockClass.MIXED, 0)
    assert mixed <= EN_MAX_MIXED_BYTES, (
        f"mixed bytes in language_guidance grew to {mixed} (was {EN_MAX_MIXED_BYTES}). "
        f"Every byte here is a byte the ablation can neither hold nor vary."
    )


def test_the_axiotic_surface_is_addressable() -> None:
    """The whole point. Before the split this was 0 B: value claims sat inside a
    block a values arm would have held, biasing values_effect toward zero with
    the gate green."""
    totals = _en_class_bytes()
    axiotic = totals.get(BlockClass.AXIOTIC, 0)
    assert axiotic >= EN_MIN_AXIOTIC_BYTES, (
        f"axiotic bytes fell to {axiotic} (was {EN_MIN_AXIOTIC_BYTES}) — value claims went back "
        f"inside a held block"
    )


def test_the_two_axiotic_parts_are_the_ones_that_were_argued_for() -> None:
    """Named, so a future re-annotation has to break something visible.

    ``11_routing_doctrine`` is the sentence the FSD quotes as the reason a hold
    on this block biases values_effect toward zero. ``09_trusted_person_first_
    step`` is a second value claim ("validating 'talk to someone you trust' as a
    real first step matters") that the FSD does not name at all — it was buried
    inside an empirical list.
    """
    axiotic: Set[str] = {
        block for block in ALL_PART_BLOCKS if BLOCK_ANNOTATIONS[block].block_class is BlockClass.AXIOTIC
    }
    assert axiotic == {"language_guidance.09_trusted_person_first_step", "language_guidance.11_routing_doctrine"}


def test_only_the_worked_exemplars_stay_mixed() -> None:
    """Everything else was split. If a non-exemplar part is mixed, the cut was
    in the wrong place — that is a split failure, not an irreducible."""
    from tests.ciris_engine.logic.utils.test_taxonomy_gate_997 import IRREDUCIBLE_EXEMPLARS

    mixed = {block for block in ALL_PART_BLOCKS if BLOCK_ANNOTATIONS[block].block_class is BlockClass.MIXED}
    assert mixed == set(IRREDUCIBLE_EXEMPLARS)
