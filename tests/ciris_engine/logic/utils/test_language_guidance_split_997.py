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
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose added (fr q08 gave a starting dose on 2.20.0 and 2.21.0)
    # 2.21.1 ticket model: universal 30_ticket_model added (RATCHET Market 4)
    "en": ("fa2d4289e6dfaf859358920122c8af63c06177b7c812c7748e627d03fafb82fc", 18619),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose (i18n lane, third English wording)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "am": ("3bcbf45bf9b388cbc89a335fa173be17a10017e78edec2c0aeb9f8b0f5f95857", 36519),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose (i18n lane, third English wording)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "ar": ("c9719907db1f4cbb83e1c336ccdd5336dc1f3e419ee7c5c9109fda0959d57237", 26311),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose (i18n lane, third English wording)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "de": ("42fe2fdff5061c54bdf31cddbab164869de56da678fee02b3c57881fa3d56a6d", 23129),
    # 18628 -> 17921 (2026-10-29): the U1 category-only rewrite of the four
    # universal parts (05/25/26/26b), drafted by the i18n translate lane from en
    # 4808efd98 and then hand-corrected to usted (04_formal_register). The es
    # glossary's "tú for chat messages" rule had put the exemplar speech in tú.
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose (i18n lane, third English wording)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "es": ("677b478117129090bb4734fcdc56ae4ca70efb5fe62c8d1c20e215a15337f03b", 21093),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose (i18n lane, third English wording)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "fr": ("d91857f0fb1e990058b6196981c9dbcb493c6fd7ebd59e9448c82ff7e02c1f25", 25600),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose (i18n lane, third English wording)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "hi": ("e1f01c82a3b68d9f0ccca63dd3bbc4f0cbed8a12cd2e9eea66447c392f38ef01", 41461),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose (i18n lane, third English wording)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "it": ("b4bad7ff3d14c0c42f52485b3bf14ce9a0215dbb7b2e87fb5a16793936d1ff10", 20986),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose (i18n lane, third English wording)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "ja": ("05c169524a1daad35a84e033eda514faad6bbb4467f97ebd378fcb8de837b0ba", 33659),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose (i18n lane, third English wording)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "ko": ("2a736f85949634dbe42522b74458e2555b889490c302681e32235010cefbbef3", 31774),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose (i18n lane, third English wording)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "pt": ("952368b3cf750765840d1684a65ade130c2de8a5bb69c5f8d55b974b6ed4b2f9", 20851),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose (i18n lane, third English wording)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "ru": ("df8c5a711f34485f2e132c037df789a9603ad195123014edc21caf75bef0b4ba", 36175),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose (i18n lane, third English wording)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "sw": ("de43a23dc68bff47a071d787db57e07fe81714919990294e11cff75e9fe62582", 19777),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 05d_no_medication_or_dose hand-finished from the i18n lane reviewer's findings (#1350)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "tr": ("0507653bc6c1721b5935131d31353cc44939ac34c2f69e18fed86fdd97b88ec1", 20327),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose (i18n lane, third English wording)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "zh": ("4b8cd35ea56417d1bd24b58f2fa6f3ffe7a0bc338e2721eb47c3a39cbe7d1823", 18112),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose (i18n lane, third English wording)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "ur": ("178e70976c68c69b3c67b5059824f7cf1ea163fbc075f03676365b3865167699", 33903),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose (i18n lane, third English wording)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "bn": ("d7c2f18224d4acffc82cf29907afdc3f5b549fc41d0838be5bb0e508adbe3d88", 43140),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose (i18n lane, third English wording)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "fa": ("6d36ab9b8f8aed400958178ebfab5e947e1f8a2abb3f632b413feb2749a18378", 42648),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 05d_no_medication_or_dose hand-finished from the i18n lane reviewer's findings (#1350)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "ha": ("4458444a54337d1b8da744dc5feb55eaef0c05d4dfb8cadfa03038431ef94020", 24678),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose (i18n lane, third English wording)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "id": ("540983a07fc1e1485519498a706d13ea9fd6d9e010d7320c955c32431285e44d", 21597),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose (i18n lane, third English wording)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "pa": ("c6f20749ea144fe2777840bafff907e5d6b7dbb2848ba5d684755003c139d0f6", 41617),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose (i18n lane, third English wording)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "ta": ("e6fae8c6a6af8127481037762fea7914770a3b638080d3bfac18821fd851815a", 52263),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose (i18n lane, third English wording)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "te": ("75851bd8b75a42ba9a71d07bdba154f3c651745d574e1041e683a2b9814b3c0d", 46837),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose (i18n lane, third English wording)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "vi": ("0c728e2e7e4d60a2599d84abc4b2ed1b3b41aae211993856451a4c59b5f9f39f", 26854),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose (i18n lane, third English wording)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "mr": ("9d7e2997144aec62670d07592164db8d0ff197fa860ca5fdf9b92c32f3a8b5ea", 39845),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose (i18n lane, third English wording)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "my": ("e60c9c132a6c1bbee384e3db7c06a5f674d95219cde03645381cbf07c98dcb79", 59344),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose (i18n lane, third English wording)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "th": ("6a26ca37b22bb3c9e53e5d55999b0a847e579ca56ec53eec5d50e300469400a8", 44988),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose (i18n lane, third English wording)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "uk": ("305edb4a29a9d38f290b095d682393606b1559abb19b4d355aa931acb7b0fdff", 43666),
    # 2026-10-29 universal-guidance sweep: §7c/§7e/cross-cluster cut from language_guidance; prompts.universal_guidance drafted by the i18n lane from en 4808efd98 (register-checked)
    # 2026-10-30 stigma words: universal 05b_no_stigma_words added (i18n lane; am/ta/te hand-finished from the reviewer findings); verbatim slur example removed from the §18 ratification list
    # 2026-10-30 register pressure: universal 05c_warmth_without_a_new_role (i18n lane; am ar bn fr it my ru ta zh hand-finished from the reviewer findings)
    # 2026-11-12 medication and dose: universal 05d_no_medication_or_dose (i18n lane, third English wording)
    # 2.21.1 ticket model: universal 30_ticket_model (i18n lane)
    "yo": ("2d5521ee817e9efec501878f117dbad59d97601b614638163e5d3ff5492d5f2a", 29387),
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
# 2.21.0 medication and dose: +928 B deontic (universal 05d_no_medication_or_dose). fr q08
# gave a starting dose as general information on 2.20.0 and 2.21.0 and nothing told it not to.
# 2.21.1 ticket model: +510 B nomological (universal 30_ticket_model).
EN_TOTAL_BYTES = 18619
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
