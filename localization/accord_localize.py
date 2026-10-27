#!/usr/bin/env python3
"""Translate the CIRIS Accord through the vendored CIRISClient pipeline.

AGENT-OWNED adapter (see ``localization/VENDORED.md``). The pipeline itself --
translate -> evaluate (MQM, different-family judge) -> repair, glossary,
translation memory, cacheable English prefix, placeholder contract -- is
``localization/localize.py``, vendored byte-identical. Every hook below is a
module attribute of the vendored module that its own functions look up at call
time; no vendored file is edited. This module:

1. SEGMENTS the English accord (``accord_<version>_en.txt``) into one key per
   non-blank line (``accord_segments.py``) and stages them as a key bundle the
   pipeline reads: ``localization/accord/<version>/{en,manifest,<lang>}.json``.
2. SEEDS each locale's bundle from what exists: the committed bundle, keeping a
   value only while the English it was translated from is unchanged (each value
   records that English's digest; a value whose digest matches a line that MOVED
   is carried to its new key), or -- on first contact -- the shipped
   ``accord_<version>_<lang>.txt`` aligned line by line within each section.
   A section whose shape does not align is left unseeded, never guessed.
3. Points TRANSLATION MEMORY at the previous accord (``--tm-version``, default
   1.2b), aligned the same way. A line that has a shipped translation of its
   previous wording sees it first. The vendored anchor caps (240 chars per
   anchor, 6,000 per request) are sized for UI labels; the accord's anchors use
   their own (``ACCORD_MAX_ANCHOR_CHARS``), so the 26 English lines over 240
   characters keep their memory.
4. Replaces the UI-string prompt wording with Accord wording (the guide's §3
   rules and the placeholder contract are carried over unchanged), and adds the
   accord guard's rules (formulas, CC references, markers, fences, headings,
   withdrawn claims, script, untranslated English) to the structural check.
5. GLOSSARY: every glossary marks ``ACCORD`` ``[DEPRECATED]``, so an Accord run
   would be told, for its own title, "retiring term, do not coin a rendering".
   For accord runs that row is dropped, and the name is pinned to how this
   language's shipped edition renders it (the translation memory) instead.
   For constitution_ethics runs the pipeline-stage "Ethics" row (the UI label
   for the conscience step) is dropped too, and one row pins "ethics text"
   (``ETHICS_TEXT_RENDERINGS``). For those runs the shipped 1.2b corpus is
   the authority for principle names: rows that contradict it are corrected
   to its rendering (``CONSTITUTION_ETHICS_GLOSSARY_FIX``) or, with no 1.2b
   majority, not sent (``CONSTITUTION_ETHICS_GLOSSARY_REMOVE``), and no row
   whose rendering is its own English is sent unless it is a proper noun or
   identifier, or the 1.2b corpus keeps it too (``ENGLISH_RENDERING_KEPT``).
   A term that occurs only inside a longer matched term is not sent
   (``drop_contained``).
   The drafting rung is ``ACCORD_DRAFTER``, not the vendored Claude rung 0.
6. Runs the lanes ONE UNIT AT A TIME, because the pipeline sends a language's
   whole selection in one request and a whole accord does not fit in one reply.
   ``--units`` narrows a run to named units; selection within a unit stays
   diff-driven (only what is missing), unlike ``--keys``, which re-selects every
   matching key.
7. REASSEMBLES every complete locale into
   ``ciris_engine/data/localized/accord_<version>_<lang>.txt`` -- skeleton plus
   values, the format ``_load_localized_accord_file`` loads -- with a provenance
   line stating ``status: draft / review_status: machine_reviewed``. A partial
   locale is never written as a file: the only filler would be English.
8. EXTRA TRANSLATION MEMORY (``--extra-tm DIR``, repeatable): the translated
   strings of the CIRIS website (``src/i18n/{dictionaries,chrome}``), the
   CIRISClient apps and the agent's own UI bundle become extra TERMINOLOGY
   anchors, after the accord TM's and on their own bound (``EXTRA_*``), ranked
   website > client > agent UI. They are never values: only the accord TM seeds.
   Without the flag, every request is byte-identical to what it was before.

Never touched: the polyglot accords (``accord_*_POLYGLOT*.txt``) and
``ciris_engine/data/localized/polyglot/``. Those load universally and are not
translations (localization/CLAUDE.md). Nothing here writes a per-locale
``localized/<lang>/`` directory.

Usage (every localize.py flag passes through)::

    # 1.3 is the renamed corpus: constitution_ethics_1.3_<lang>.txt, with the
    # shipped accord_1.2b_<lang>.txt as translation memory (--stem / --tm-stem).
    E13='--version 1.3 --stem constitution_ethics --tm-version 1.2b --tm-stem accord'
    python3 localization/accord_localize.py $E13 --segments
    python3 localization/accord_localize.py $E13 --seed-exact-tm --units section0 --lane translate --dry-run
    python3 localization/accord_localize.py $E13 --extra-tm ~/ciris-website --extra-tm ~/CIRISClient \
        --extra-tm . --units section0 --lane translate --dry-run
    python3 localization/accord_localize.py --version 1.3 --segments
    python3 localization/accord_localize.py --version 1.3 --check
    python3 localization/accord_localize.py --version 1.3 --units section0 --lane translate --dry-run
    python3 localization/accord_localize.py --version 1.3 --units 'v1 v2' --lane translate \
        --max-keys 2600
    python3 localization/accord_localize.py --version 1.3 --lane evaluate --keys 'accord.v9.*' --lang yo
    python3 localization/accord_localize.py --version 1.3 --verify

Nothing in this file calls a model. Every call is ``localize.py``'s.

``--mode batch`` is REFUSED (see ``refuse_batch_mode``): on OpenRouter the
``:batch`` slugs it appends are served only by OpenRouter's async batch
adapters, and ``/chat/completions`` answers every one of them with HTTP 404.
"""

from __future__ import annotations

import argparse
import fnmatch
import importlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, NamedTuple, Optional, Sequence, Set, Tuple

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import accord_segments as seg  # noqa: E402
import lane_backoff  # noqa: E402

LOCALIZED = REPO_ROOT / "ciris_engine" / "data" / "localized"
STAGE_ROOT = HERE / "accord"
DEFAULT_TM_VERSION = "1.2b"

_VERSION = re.compile(r"^\d+\.\d+[a-z]?$")

#: Translation-memory budget per request. The vendored UI default (240 / 6000)
#: would leave every accord line over 240 characters with no memory at all.
ACCORD_ANCHOR_LIMIT = 80
ACCORD_MAX_ANCHOR_CHARS = 1600
ACCORD_MAX_ANCHOR_BLOCK_CHARS = 24000
#: A same-key anchor is used only if its English still resembles the new
#: English: keys are positional within a section, so a rewritten section can
#: put a different line under an old key.
SAME_KEY_MIN_SIMILARITY = 0.3

#: ``_meta`` field recording each withheld line accepted under ``--accept-minor``.
ACCEPTED_MINOR = "accepted_minor"
#: The one MQM severity ``--accept-minor`` accepts. A finding with any other
#: severity, or none, keeps its line withheld.
MINOR_SEVERITY = "minor"

#: localize.py flags under which a run must not write anything.
READ_ONLY_FLAGS = ("--check", "--dry-run", "--glossary-report")

#: Glossary rows dropped for accord runs (see the module docstring, point 5).
ACCORD_GLOSSARY_DROP = ("ACCORD",)

#: Live rows dropped for constitution_ethics runs. "Ethics" is a PIPELINE-STAGE
#: label in every glossary that has it (Context column "Conscience check" /
#: "Ethics check": the UI's name for the conscience step), not the word ethics.
#: Sent with the ethics text it made am render "ethics text" as the
#: "conscience text" (ህሊና ጽሑፍ) in every model of the 2026-10-14 trial, which the
#: judge passed, and made yo fail every draft for not writing the stage label.
#: "Ethics Check" is the same UI stage label spelled out (Context column
#: "Conscience check" / "Conscience phase" in de/es/pt). The 1.2b corpus never
#: uses those renderings for the text's "ethics checks" (de "Ethik-Prüfungen",
#: fr "contrôles éthiques"), and run 38627954361 rejected de and fr drafts for
#: not writing the label (accord.v1.s07.l04).
CONSTITUTION_ETHICS_GLOSSARY_DROP = ("ethics", "ethics check")

#: A glossary's "Version History" table is parsed as terms after its header
#: row: "1.0 -> 2026-03-27", "1.1 -> 2026-05-31". The ethics text says "1.0" and
#: "1.1", so every locale was sent a release date as the canonical rendering of
#: a version number. Not terminology; never sent in constitution_ethics runs.
VERSION_ROW = re.compile(r"\d+(?:\.\d+)+")

#: PRINCIPLE NAMES, corrected to the shipped 1.2b translation for
#: constitution_ethics runs (Eric's ruling, 2026-10-14: the shipped 1.2b
#: translation of each principle name is the authority). The glossary rows
#: below contradicted the corpus the run's anchors come from, so a draft broke
#: either the glossary or its anchor, and the judge could always cite the other:
#: run 38627954361 rejected de, th, uk, fa, ta, te and ur lines on these terms
#: (th: 11 of its 17 rejections cite Integrity or Resilience). Each value is
#: the corpus's majority rendering, read from accord_1.2b_<lang>.txt aligned by
#: line key to the English 1.2b; the count is aligned lines carrying it /
#: aligned lines whose English names the term. Where the corpus is
#: INCONSISTENT, the majority wins. A test asserts that every key is an
#: existing glossary row and every value occurs in that locale's 1.2b file.
#:   de  Non-maleficence  Nicht-Schaden -> Schadensvermeidung   12/12 (v1.s03.l04)
#:   de  Resilience       Widerstandsfähigkeit -> Resilienz    14/14 (v1.s05.title)
#:   de  Epistemic Humility  -> epistemische Demut             1/1 (v2.s05.l02)
#:   fa  Integrity   صداقت -> درستکاری                          12/16 (v1.s04.title)
#:   fr  Wise Authority  (rendered as its English) -> Autorité Sage   3/3; 13 raw vs 2 English
#:   hi  Integrity   अखंडता -> सत्यनिष्ठा                        12/17 vs 4 (v1.s04.title)
#:   hi  Epistemic Humility  ज्ञानपरक विनम्रता -> ज्ञानमीमांसीय विनम्रता  1/1
#:   id  Resilience  Ketahanan -> Resiliensi                   12/14 (v1.s05.title)
#:   id  Flourishing Berkembang -> kesejahteraan               10/14 vs 0
#:   ja  Resilience  回復力 -> レジリエンス                      12/14 vs 2
#:   ja  Epistemic Humility  認識論的謙遜 -> 認識論的謙虚さ          1/1
#:   ko  Integrity   무결성 (0 in 1.2b) -> 성실성                 8/17; 통합성 5 (INCONSISTENT, majority)
#:   mr  Integrity   सचोटी -> सत्यनिष्ठा                          9/17 vs 2
#:   mr  Coherence   सुसंगतता -> सुसंगती                         11/23 vs 8 (INCONSISTENT, majority)
#:   mr  Epistemic Humility  ज्ञानविषयक नम्रता -> ज्ञानमीमांसीय नम्रता  1/1
#:   ru  Coherence   Когерентность -> Согласованность          16/23 vs 7 (INCONSISTENT, majority)
#:   ta  Resilience  மீள்தன்மை -> மீள்திறன்                     10/14 vs 4 (incl. மீள்-தன்மை)
#:   te  Coherence   సంఘటన ("incident") -> సమన్వయం             18/22 vs 0
#:   th  Integrity   ความซื่อสัตย์ -> ความซื่อตรง                 8/17 vs 0 (v1.s04.title)
#:   th  Resilience  ความยืดหยุ่น -> ความสามารถในการฟื้นตัว        7/14; ความคงทน 4, ความยืดหยุ่น 1 (INCONSISTENT, majority)
#:   th  Epistemic Humility  ความถ่อมตนทางความรู้ -> ความอ่อนน้อมทางญาณวิทยา  1/1
#:   tr  Integrity   Dürüstlük/Bütünlük -> Bütünlük            14/17; Dürüstlük 0
#:   tr  Epistemic Humility  Bilgiye Saygı/Epistemik Alçakgönüllülük -> epistemik alçakgönüllülük  1/1
#:   uk  Integrity   Доброчесність (0 in 1.2b) -> Цілісність    12/17
#:   ur  Error       خرابی -> غلطی                              2/2 (v3.s05.l08, rejected in 38627954361)
#:   ur  Epistemic Humility  علمی عاجزی -> علمی انکساری          1/1
#:   vi  Flourishing Phát Triển Thịnh Vượng -> hưng thịnh       9/14 vs 2
#:   vi  Epistemic Humility  Khiêm Tốn Nhận Thức -> khiêm nhường về nhận thức  1/1
#:   zh  Integrity   正直 -> 诚信                                8/17 vs 3
#:   zh  Coherence   连贯性 -> 一致性                             10/22 vs 8 (INCONSISTENT, majority)
#: WISE AUTHORITY (Eric's ruling, 2026-10-14: "Wise Authority not human
#: advisor"). Counted over the 12 aligned 1.2b lines naming it, plural and
#: inflected forms with their stem. A "human advisor" rendering (de
#: Menschliche Berater, hi मानव सलाहकार, sw Mshauri wa Kibinadamu) or ko's
#: 담당자 ("person in charge") is excluded by the ruling even where 1.2b uses it;
#: the majority of the REST decides. Where that is the English, the 1.2b corpus
#: keeps the English, so the row is the English (see ENGLISH_RENDERING_KEPT).
#:   de  Menschlicher Berater -> Wise Authority   English 5/12; Menschliche Berater 6 (excluded), Weise Autoritäten 1
#:   hi  मानव सलाहकार -> Wise Authority            English 11/12; मानव सलाहकार 1 (excluded, v9.s06.l04)
#:   id  Otoritas Bijak (0 in 1.2b) -> Wise Authority   English 12/12
#:   ko  담당자 -> Wise Authority                   English 3/12 (v5.s04.l04, v6.s07.l01, v9.s06.l04); 담당자 10 (excluded)
#:   ur  دانش مند اتھارٹی -> Wise Authority         English 8/12 vs دانش مند اتھارٹی(ز) 3, دانش مند حکام 1
#:   tr  Bilge Otorite/Danışma Otoritesi -> Bilge Otorite   12/12 (Bilge Otorite, -ler, -lere); Danışma 0
#:   sw  no rendering left: Mshauri/Washauri wa Kibinadamu 12/12 -> CONSTITUTION_ETHICS_GLOSSARY_REMOVE
#:   fr  is corrected above (Autorité Sage). Every other locale's row already
#:       matches its 1.2b majority: am ar bn(6 vs English 6, a tie its row is
#:       one side of) es fa ha it ja mr my pa pt ru ta te th uk vi yo zh.
CONSTITUTION_ETHICS_GLOSSARY_FIX: Dict[str, Dict[str, str]] = {
    "de": {
        "Non-maleficence": "Schadensvermeidung",
        "Resilience": "Resilienz",
        "Epistemic Humility": "epistemische Demut",
        "Wise Authority": "Wise Authority",
    },
    "fa": {"Integrity": "درستکاری"},
    "fr": {"Wise Authority": "Autorité Sage"},
    "hi": {"Integrity": "सत्यनिष्ठा", "Epistemic Humility": "ज्ञानमीमांसीय विनम्रता", "Wise Authority": "Wise Authority"},
    "id": {"Resilience": "Resiliensi", "Flourishing": "kesejahteraan", "Wise Authority": "Wise Authority"},
    "ja": {"Resilience": "レジリエンス", "Epistemic Humility": "認識論的謙虚さ"},
    "ko": {"Integrity": "성실성", "Wise Authority": "Wise Authority"},
    "mr": {"Integrity": "सत्यनिष्ठा", "Coherence": "सुसंगती", "Epistemic Humility": "ज्ञानमीमांसीय नम्रता"},
    "ru": {"Coherence": "Согласованность"},
    "ta": {"Resilience": "மீள்திறன்"},
    "te": {"Coherence": "సమన్వయం"},
    "th": {
        "Integrity": "ความซื่อตรง",
        "Resilience": "ความสามารถในการฟื้นตัว",
        "Epistemic Humility": "ความอ่อนน้อมทางญาณวิทยา",
    },
    "tr": {
        "Integrity": "Bütünlük",
        "Epistemic Humility": "epistemik alçakgönüllülük",
        "Wise Authority": "Bilge Otorite",
    },
    "uk": {"Integrity": "Цілісність"},
    "ur": {"Error": "غلطی", "Epistemic Humility": "علمی انکساری", "Wise Authority": "Wise Authority"},
    "vi": {"Flourishing": "hưng thịnh", "Epistemic Humility": "khiêm nhường về nhận thức"},
    "zh": {"Integrity": "诚信", "Coherence": "一致性"},
}

#: Rows not sent in constitution_ethics runs because the 1.2b corpus has no
#: majority rendering to correct them to (never invented, never left wrong).
#:   te  Flourishing  వర్ధిల్లు (0 in 1.2b): శ్రేయస్సు 6/13 vs వికాస- 6/13, a tie
#:   de  Reasoning    "Reasoning" (its English): Denkprozess / Begründung /
#:       Systemargumentation, 1 each of 3. It is also an English-rendering row.
#:   sw  Wise Authority  Mshauri wa Kibinadamu ("human advisor"): every one of
#:       the 12 aligned 1.2b lines uses it, and the ruling excludes it.
CONSTITUTION_ETHICS_GLOSSARY_REMOVE: Dict[str, Tuple[str, ...]] = {
    "te": ("Flourishing",),
    "de": ("Reasoning",),
    "sw": ("Wise Authority",),
}

#: Rows whose rendering IS its English, still sent in constitution_ethics runs.
#: Every other such row is dropped: a glossary row that "translates" a term as
#: itself canonizes leftover English (the ciris-website lesson), and the judge
#: generalizes from it (run 38627954361's de judge demanded "Integrity",
#: "Justice" and "Meta-Goal" stay English, which no de row says).
#: Global: acronyms, product and proper names, and machine identifiers that
#: must survive verbatim.
ENGLISH_RENDERING_KEPT_EVERYWHERE: FrozenSet[str] = frozenset(
    {
        "API", "BYOK", "CIRIS", "DMA", "DSASPDMA", "IDMA", "LLM", "OAuth", "Ubuntu",
        "domain_hint", "operational_reason", "primary_need_category", "rights_basis",
        "secondary_need_categories",
    }
)  # fmt: skip
#: Per locale: the word is also this language's word, and the 1.2b corpus
#: writes it that way (aligned lines carrying it / lines naming the term).
#:   de  Agent 6/6 ("Agent", "Agenten"), Online 1/1, Wise Authority (see the FIX table)
#:   hi, id, ko, ur  Wise Authority (see the FIX table)
#:   es  Error 2/2, Local 2/2
#:   fr  Agent 6/6, Service 2/2
#:   it  Online 1/1, Wise Authority 3/3 (13 raw "Wise Authority" vs 1 "Autorità Sagge")
#:   pt  Local 2/2
#:   tr  Transfer 3/5 ("Transfer", "Transferi"; aktarım 1)
ENGLISH_RENDERING_KEPT: Dict[str, FrozenSet[str]] = {
    "de": frozenset({"Agent", "Online", "Wise Authority"}),
    "hi": frozenset({"Wise Authority"}),
    "id": frozenset({"Wise Authority"}),
    "ko": frozenset({"Wise Authority"}),
    "ur": frozenset({"Wise Authority"}),
    "es": frozenset({"Error", "Local"}),
    "fr": frozenset({"Agent", "Service"}),
    "it": frozenset({"Online", "Wise Authority"}),
    "pt": frozenset({"Local"}),
    "tr": frozenset({"Transfer"}),
}


def english_renderings(rows: Dict[str, str], code: str) -> List[str]:
    """The rows of ``rows`` rendered as their own English that ``code`` may not keep."""
    kept = ENGLISH_RENDERING_KEPT_EVERYWHERE | ENGLISH_RENDERING_KEPT.get(code, frozenset())
    return sorted(e for e, t in rows.items() if t.strip().casefold() == e.strip().casefold() and e.strip() not in kept)


#: The glossaries' prose ("Cultural Considerations"), sent with EVERY request,
#: also tells four locales to call the Wise Authority a human advisor:
#:   hi  'use respectful terminology like "मानव सलाहकार"'
#:   sw  'use respectful terminology like "mshauri wa kibinadamu"'
#:   ko  'use respectful terminology (담당자)'
#:   zh  'like "智慧权威" or "人工顾问"' (人工顾问: a human advisor)
#: Under the ruling those lines would out-argue the corrected row, so
#: constitution_ethics runs do not send a prose line that names one of these.
HUMAN_ADVISOR_PROSE = ("मानव सलाहकार", "mshauri wa kibinadamu", "담당자", "人工顾问")


def accord_guidance(sections: List[Tuple[str, str]], stem: str) -> List[Tuple[str, str]]:
    """The glossary prose an accord run of ``stem`` sends."""
    if stem != "constitution_ethics":
        return sections
    out: List[Tuple[str, str]] = []
    for title, text in sections:
        lines = [ln for ln in text.split("\n") if not any(h in ln.casefold() for h in HUMAN_ADVISOR_PROSE)]
        if "\n".join(lines).strip():
            out.append((title, "\n".join(lines)))
    return out + CONSTITUTION_ETHICS_TERM_RULES


#: The document's own name in constitution_ethics runs: one row, "ethics text".
#: Each rendering is taken from this language's accepted 1.3 output (the
#: section 0 heading "The Ethics Text Begins" and line s08.l02, both accepted by
#: the MQM judge in batch 1) or, for the four locales batch 1 withheld it in,
#: from the 2026-10-14 model trial's accepted drafts and the judge's own
#: suggestions. Machine-derived, not native-reviewed. A locale with no evidence
#: has no row; there is none missing today, but the rule stands.
#:   am  heading "የስነ-ምግባር ጽሑፉ" (accepted) + the judge's fix for the trial's
#:       "የህሊና ጽሑፍ" (conscience text): "የዚህ ስነ-ምግባር ጽሑፍ"; ስነ-ምግባር 61x in 1.2b
#:   ha  heading "Rubutun Ɗabi'a" + every trial draft + the judge's suggestion
#:   my  heading "ကျင့်ဝတ် စာသား" + muse-spark-1.3's accepted s08.l02. The judge
#:       flip-flopped between စာသား and စာတမ်း across the trial; the heading decides.
#:   yo  no accepted output (heading and s08.l02 both withheld). "ìwé" is the
#:       1.2b corpus's word for a document ("ìwé alààyè", a living document);
#:       two trial drafts wrote "ìwé ìwà rere" and the judge proposed it twice,
#:       rejecting only the casing of the stage label.
#:   ko  heading "윤리 문언"; the accepted s08.l02 said "윤리 문서". The heading decides.
#:   mr  heading "नैतिकतेचा ग्रंथ" (s08.l02 uses its oblique form).
#:   everything else: heading and s08.l02 agree.
ETHICS_TEXT_RENDERINGS: Dict[str, str] = {
    "am": "የስነ-ምግባር ጽሑፍ",
    "ar": "النص الأخلاقي",
    "bn": "নৈতিক পাঠ্য",
    "de": "Ethiktext",
    "es": "texto ético",
    "fa": "متن اخلاقی",
    "fr": "texte éthique",
    "ha": "rubutun ɗabi'a",
    "hi": "नैतिकता-पाठ",
    "id": "teks etika",
    "it": "testo etico",
    "ja": "倫理テキスト",
    "ko": "윤리 문언",
    "mr": "नैतिकतेचा ग्रंथ",
    "my": "ကျင့်ဝတ် စာသား",
    "pa": "ਨੈਤਿਕ ਪਾਠ",
    "pt": "texto de ética",
    "ru": "этический текст",
    "sw": "maandishi ya maadili",
    "ta": "நெறிமுறை உரை",
    "te": "నైతిక గ్రంథం",
    "th": "ข้อความจริยธรรม",
    "tr": "etik metin",
    "uk": "етичний текст",
    "ur": "اخلاقی متن",
    "vi": "văn bản đạo đức",
    "yo": "ìwé ìwà rere",
    "zh": "伦理文本",
}
ETHICS_TEXT_TERM = "ethics text"

#: CC's term rules for the rc11 lines (2026-10-26): "the wire" is kept and
#: glossed, never paraphrased; "this charter" in the publication rule is "the
#: Constitution"; the text speaking of itself is "this text".
#: "the Constitution" is a proper name, so its pin is this locale's ESTABLISHED
#: rendering of "CIRIS Constitution": the most frequent across every line of
#: its 1.3 bundle and its rc8 shipped text that names it (substring extracted
#: line by line, citation form, CIRIS dropped). Counts are in the PR. Two
#: departures from the plain majority: zh 宪章 (4) over 章程 (7), which means
#: bylaws; ja 憲法 over 憲章 on a 5-5 tie. my keeps the English "Constitution"
#: (its accepted lines keep it; no Burmese rendering recurs).
#: "this text" is pinned only where one demonstrative form leads outright
#: (fa, ha, hi, te, tr, uk); elsewhere no row.
#: "the wire" has no pin here: CC rc12's rule is that it is rendered by its
#: meaning, never as a cable word or a loanword (CONSTITUTION_ETHICS_TERM_RULES).
#: The literal renderings the first passes pinned (ሽቦ, السلك, سیم, fil, filo,
#: Wire, ...) are withdrawn.
CONSTITUTION_ETHICS_TERM_PINS: Dict[str, Dict[str, str]] = {
    "am": {"the Constitution": "ሕገ መንግስት"},
    "ar": {"the Constitution": "دستور"},
    "bn": {"the Constitution": "সংবিধান"},
    "de": {"the Constitution": "Verfassung"},
    "es": {"the Constitution": "Constitución"},
    "fa": {"the Constitution": "قانون اساسی", "this text": "این متن"},
    "fr": {"the Constitution": "Constitution"},
    "ha": {"the Constitution": "Kundin Tsarin Mulki", "this text": "wannan rubutu"},
    "hi": {"the Constitution": "संविधान", "this text": "यह पाठ"},
    "id": {"the Constitution": "Konstitusi"},
    "it": {"the Constitution": "Costituzione"},
    "ja": {"the Constitution": "憲法"},
    "ko": {"the Constitution": "헌장"},
    "mr": {"the Constitution": "संविधान"},
    "my": {"the Constitution": "Constitution"},
    "pa": {"the Constitution": "ਸੰਵਿਧਾਨ"},
    "pt": {"the Constitution": "Constituição"},
    "ru": {"the Constitution": "Конституция"},
    "sw": {"the Constitution": "Katiba", "this text": "maandishi haya"},
    "ta": {"the Constitution": "அரசியலமைப்பு"},
    "te": {"the Constitution": "రాజ్యాంగం", "this text": "ఈ గ్రంథం"},
    "th": {"the Constitution": "รัฐธรรมนูญ"},
    "tr": {"the Constitution": "Anayasa", "this text": "bu metin"},
    "uk": {"the Constitution": "Конституція", "this text": "цей текст"},
    "ur": {"the Constitution": "آئین"},
    "vi": {"the Constitution": "Hiến chế"},
    "yo": {"the Constitution": "Ìpilẹ̀-Òfin"},
    "zh": {"the Constitution": "宪章"},
}

#: Term rules sent with every constitution_ethics request, as glossary prose
#: (the translator and the judge both read it). The plain-English master
#: (translation_master) carries the meaning of "the wire" and "standing"; this
#: keeps only the check that "the wire" is never rendered as a cable word or a
#: loanword.
CONSTITUTION_ETHICS_TERM_RULES: List[Tuple[str, str]] = [
    (
        "Constitution ethics term rules",
        '- Where the source says "the signed records nodes exchange", the English canon says "the wire". '
        "Render that meaning. Treat as a terminology error any word for a cable, wire, line, thread, network "
        'or channel, or a loanword or transliteration of "wire", except where the source itself names the '
        "English term *the wire*.",
    ),
]

#: Glossary renderings re-cased for accord runs: {lang: {english: (table, used)}}.
#: The yo pipeline-stage table is written in UI capitals, and the judge enforced
#: "ÌWÀ RERE" inside running prose despite the block's own "case is not
#: normative" line. The 1.2b yo corpus writes it "ìwà rere" (4x, plus one
#: title-cased heading), which is what lets it sit inside a phrase.
GLOSSARY_RECASE: Dict[str, Dict[str, Tuple[str, str]]] = {
    "yo": {"Ethics": ("ÌWÀ RERE", "ìwà rere")},
}

#: THE DRAFTING RUNG for accord runs on OpenRouter (a local divergence, see
#: VENDORED.md). Only rung 0 moves; the repair rungs and the judge stay the
#: vendored ones. Off the Claude family because the work is reviewed by Claude
#: anyway (ruling, 2026-10-14). In the trial muse-spark-1.3 passed 16 of 18
#: hard keys, the best of the nine models, at 41% of Sonnet 5's spend.
#: LOCALIZE_LADDER, when set, still wins.
ACCORD_DRAFTER = "meta/muse-spark-1.3"
#: $/MTok (input, output), from OpenRouter's model list on 2026-10-14. Merged
#: into the vendored PRICE table so the spend report prices the new rung.
ACCORD_PRICE: Dict[str, Tuple[float, float]] = {ACCORD_DRAFTER: (1.25, 4.25)}

#: The document families this adapter may read and write, by filename stem
#: (``<stem>_<version>_<lang>.txt``). A CLOSED list: the stem arrives from a
#: workflow input, and anything not named here could be a path.
#: ``constitution_ethics`` is the Accord's successor (1.3 onward); ``accord`` is
#: every shipped edition up to 1.2b, and the translation memory for 1.3.
STEMS: Dict[str, Tuple[str, str]] = {
    # stem: (prose name for prompts, short name for the provenance label)
    "accord": ("the CIRIS Accord", "Accord"),
    "constitution_ethics": (
        "the CIRIS Constitution's ethics text (the successor of the Accord)",
        "Constitution ethics text",
    ),
}
DEFAULT_STEM = "accord"

#: Written into every reassembled locale file, after the provenance preamble.
LABEL = (
    "// Machine translation of the English {name} {version} -- status: draft / "
    "review_status: machine_reviewed (vendored CIRISClient localize pipeline; MQM-reviewed "
    "by a model of a different family; not native-reviewed)."
)

_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9']+")
#: ``{key: (english, shipped translation)}`` -- one locale's translation memory.
TM = Dict[str, Tuple[str, str]]

_STOP = {"the", "a", "an", "and", "or", "to", "of", "is", "in", "for", "this", "that"}


# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────


def check_version(version: str) -> str:
    if not _VERSION.match(version):
        raise SystemExit(f"[refuse] {version!r} is not an accord version like 1.3 or 1.2b")
    return version


def check_stem(stem: str) -> str:
    if stem not in STEMS:
        raise SystemExit(f"[refuse] {stem!r} is not a document stem this adapter knows: {sorted(STEMS)}")
    return stem


def accord_path(localized: Path, version: str, lang: str, stem: str = DEFAULT_STEM) -> Path:
    """The per-locale file the loader reads. Never a polyglot artifact."""
    if not re.fullmatch(r"[a-z]{2,3}", lang):
        raise SystemExit(f"[refuse] {lang!r} is not a locale code")
    path = localized / f"{check_stem(stem)}_{check_version(version)}_{lang}.txt"
    if "POLYGLOT" in path.name or path.parent != localized:
        raise SystemExit(f"[refuse] {path} is not a per-locale accord path")
    return path


# ─────────────────────────────────────────────────────────────────────────────
# Bundles
# ─────────────────────────────────────────────────────────────────────────────


def nest(flat: Dict[str, str]) -> Dict[str, Any]:
    """Dotted keys -> nested objects, in the order given."""
    out: Dict[str, Any] = {}
    for key, value in flat.items():
        node = out
        parts = key.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = value
    return out


def flatten(obj: Dict[str, Any], prefix: str = "") -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, v in obj.items():
        if not prefix and k == "_meta":
            continue
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flatten(v, key))
        elif isinstance(v, str):
            out[key] = v
    return out


def write_json(path: Path, doc: Dict[str, Any]) -> None:
    # Same serialisation as localize.insert, so a lane write is a minimal diff.
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> Dict[str, Any]:
    data: Dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def agent_languages(localized: Path) -> Dict[str, Dict[str, Any]]:
    langs: Dict[str, Dict[str, Any]] = read_json(localized / "manifest.json")["languages"]
    return langs


def locale_meta(localized: Path, lang: str) -> Dict[str, Any]:
    """``_meta`` for a staged bundle: identity from the agent's own bundle."""
    meta: Dict[str, Any] = {"language": lang, "language_name": lang, "direction": "ltr"}
    ui = localized / f"{lang}.json"
    if ui.is_file():
        src = read_json(ui).get("_meta", {})
        for name in ("language", "language_name", "direction"):
            if name in src:
                meta[name] = src[name]
    return meta


#: THE PLAIN-ENGLISH MASTER (Eric's ruling on #1325, "Plain-English master").
#: The shipped canon keeps CC's terms; a translation is made from, and judged
#: against, a copy in which two terms of art are replaced by their meaning, so
#: the translator and the judge read the same meaning on both sides. Mechanical
#: substitutions only, applied in order; nothing else in a line changes.
#:
#: "the wire" -> "the signed records nodes exchange" (CC 1.13.3), inflected in
#: place: "on the wire" -> "in ...", "its wire behaviour" -> "its behaviour in
#: ...", and a verb right after it (optionally after "alone") agrees with the
#: plural. Book II's definition sentence becomes a sentence about the English
#: term, the one place *the wire* is kept, as a quoted label.
#:
#: "standing" is substituted only where it is the person's standing under the
#: guarantees (Book VI bucket D, CC 1.13.2 / 7.3): "unconditional standing",
#: "a person's standing". Untouched: the adjective ("standing roster", "standing
#: class", "standing obligations"), "moral standing", and "standing (a say in
#: decisions)" / "Care is not standing", which the text glosses itself as a say
#: in decisions.
_WIRE = "the signed records nodes exchange"
_WIRE_VERBS = {"decides": "decide", "judges": "judge", "checks": "check", "enforces": "enforce", "carries": "carry"}
MASTER_SUBSTITUTIONS: Tuple[Tuple[str, str], ...] = (
    (r"In this text, \*the wire\* means", "In this text, the English term *the wire* means"),
    (r"\bon the wire\b", "in " + _WIRE),
    (r"\bits wire behaviour\b", "its behaviour in " + _WIRE),
    (r"(?<!\*)\bthe wire\b(?!\*)", _WIRE),
    (r"^The wire\b", _WIRE[0].upper() + _WIRE[1:]),
    (r"\ba person with unconditional standing\b", "a person with an unconditional place under the guarantees"),
    (r"\ba person's standing\b", "a person's place under the guarantees"),
)


def translation_master(text: str) -> str:
    """The plain-English master of one canon segment (see MASTER_SUBSTITUTIONS)."""
    out = text
    for pattern, repl in MASTER_SUBSTITUTIONS:
        out = re.sub(pattern, repl, out, flags=re.M)
    verbs = "|".join(_WIRE_VERBS)
    return re.sub(
        rf"({re.escape(_WIRE)}(?: alone)?) ({verbs})\b",
        lambda m: f"{m.group(1)} {_WIRE_VERBS[m.group(2)]}",
        out,
        flags=re.I,
    )


def label_locale(text: str, version: str, stem: str = DEFAULT_STEM) -> str:
    """Insert the provenance label after the leading ``//`` preamble block."""
    lines = text.split("\n")
    i = 0
    while i < len(lines) and lines[i].startswith("// ") and not lines[i].startswith(seg.MARKER):
        i += 1
    lines.insert(i, LABEL.format(name=STEMS[check_stem(stem)][1], version=version))
    return "\n".join(lines)


class Stage:
    """The staged key bundle for one accord version."""

    def __init__(
        self,
        version: str,
        *,
        stage_dir: Optional[Path] = None,
        localized: Path = LOCALIZED,
        stem: str = DEFAULT_STEM,
    ) -> None:
        self.version = check_version(version)
        self.stem = check_stem(stem)
        self.localized = localized
        self.dir = stage_dir or default_stage_dir(version, stem)
        #: Exact-English translation-memory matches to seed as values (opt-in).
        self.seed_tm: Dict[str, TM] = {}
        #: --extra-tm corpora (website, client, agent UI): ANCHORS ONLY. Nothing
        #: in Stage reads this to seed or write a value; install() hands it to
        #: anchors_for.
        self.extra_tm: Dict[str, List[ExtraAnchor]] = {}
        source = accord_path(localized, version, "en", stem)
        if not source.is_file():
            raise SystemExit(
                f"[refuse] no English source at {source}. The pipeline translates FROM "
                f"the English source; land it first (CIRISAgent#1252 / #1256 for constitution_ethics 1.3)."
            )
        self.source_text = source.read_text(encoding="utf-8")
        self.doc = seg.parse(self.source_text)
        if seg.reassemble(self.doc) != self.source_text:  # pragma: no cover - the parser's contract
            raise SystemExit("[refuse] the segmenter does not round-trip this source; refusing to stage it")
        #: The shipped English, segment by segment.
        self.canon: Dict[str, str] = self.doc.segments()
        #: What the lanes translate FROM and the judge reviews against, and what
        #: the digests key off: the canon, or its plain-English master.
        self.en: Dict[str, str] = (
            {k: translation_master(v) for k, v in self.canon.items()} if self.stem == "constitution_ethics" else self.canon
        )
        self.slots: Dict[str, seg.Slot] = {s.key: s for s in self.doc.slots}
        self.digests = {k: seg.source_digest(v) for k, v in self.en.items()}
        self.languages = [lang for lang in agent_languages(localized) if lang != "en"]

    def render(self, lang: str, values: Dict[str, str]) -> str:
        """The file a complete locale is written as."""
        return label_locale(seg.reassemble(self.doc, values), self.version, self.stem)

    # -- building ------------------------------------------------------------

    def build(self) -> Dict[str, Dict[str, int]]:
        """Write en.json, manifest.json and one bundle per locale. Returns stats."""
        self.dir.mkdir(parents=True, exist_ok=True)
        en_doc: Dict[str, Any] = {"_meta": {"language": "en", "language_name": "English", "direction": "ltr"}}
        en_doc.update(nest(self.en))
        write_json(self.dir / "en.json", en_doc)
        manifest = {
            "version": f"accord-{self.version}",
            "description": "Staged CIRIS Accord segments (generated by localization/accord_localize.py)",
            "languages": {code: {} for code in ["en", *self.languages]},
        }
        write_json(self.dir / "manifest.json", manifest)
        stats: Dict[str, Dict[str, int]] = {}
        for lang in self.languages:
            accepted = self._accepted_minor(lang)
            values, origin = self._seed(lang)
            meta = locale_meta(self.localized, lang)
            meta.update(
                {
                    "accord_version": self.version,
                    "status": "draft",
                    "review_status": "machine_reviewed",
                    "source_digests": {k: self.digests[k] for k in self.en if k in values},
                }
            )
            kept = [e for e in accepted if values.get(e["key"]) == e["text"]]
            if kept:
                meta[ACCEPTED_MINOR] = kept
            doc: Dict[str, Any] = {"_meta": meta}
            doc.update(nest({k: values[k] for k in self.en if k in values}))
            write_json(self.dir / f"{lang}.json", doc)
            stats[lang] = {"present": len(values), "total": len(self.en), **origin}
        return stats

    def _accepted_minor(self, lang: str) -> List[Dict[str, Any]]:
        """The bundle's accepted-minor record, for lines whose English is unchanged."""
        bundle = self.dir / f"{lang}.json"
        if not bundle.is_file():
            return []
        entries: List[Dict[str, Any]] = read_json(bundle).get("_meta", {}).get(ACCEPTED_MINOR, [])
        return [e for e in entries if self.digests.get(e.get("key", "")) == e.get("source_digest")]

    def _clean(self, lang: str, values: Dict[str, str]) -> Dict[str, str]:
        return {
            k: v
            for k, v in values.items()
            if k in self.slots and v.strip() and not seg.passage_problems(self.slots[k], v, lang)
        }

    def _seed(self, lang: str) -> Tuple[Dict[str, str], Dict[str, int]]:
        bundle = self.dir / f"{lang}.json"
        if bundle.is_file():
            doc = read_json(bundle)
            recorded: Dict[str, str] = doc.get("_meta", {}).get("source_digests", {})
            values = flatten(doc)
            kept = {k: v for k, v in values.items() if k in self.en and recorded.get(k) == self.digests[k]}
            # A line that MOVED (an insertion above it shifted its key) keeps its
            # translation: the digest of the English it came from is unchanged.
            by_digest: Dict[str, List[str]] = {}
            for k, v in values.items():
                if k in recorded and v.strip():
                    by_digest.setdefault(recorded[k], []).append(v)
            moved = 0
            for k in self.en:
                if k not in kept:
                    candidates = set(by_digest.get(self.digests[k], []))
                    if len(candidates) == 1:
                        kept[k] = candidates.pop()
                        moved += 1
            kept = self._clean(lang, kept)
            # Anything else was made from English that no longer exists in this
            # form: it is dropped, so the diff-driven lane retranslates it.
            dropped = sum(1 for k in values if k not in kept)
            return kept, {"stale_dropped": dropped, "moved": moved}
        shipped = accord_path(self.localized, self.version, lang, self.stem)
        if shipped.is_file():
            aligned, skipped = seg.align(self.doc, seg.parse(shipped.read_text(encoding="utf-8")))
            kept = self._clean(lang, aligned)
            return kept, {"sections_unaligned": len(skipped), "guard_rejected": len(aligned) - len(kept)}
        tm = self.seed_tm.get(lang)
        if tm:
            # OPT-IN (--seed-exact-tm): an English line that is byte-identical to
            # a line of the previous edition takes that edition's shipped
            # translation as its value -- the corpus users already read -- instead
            # of a fresh draft. Only unambiguous matches, and only lines the
            # accord guard accepts; everything else is left to the lanes.
            by_text: Dict[str, Set[str]] = {}
            for english, shipped_text in tm.values():
                by_text.setdefault(english, set()).add(shipped_text)
            exact = {k: next(iter(by_text[t])) for k, t in self.en.items() if len(by_text.get(t, ())) == 1}
            kept = self._clean(lang, exact)
            return kept, {"seeded_exact_from_tm": len(kept)}
        return {}, {}

    # -- after a run -----------------------------------------------------------

    def finalize(self, *, write_files: bool = True) -> Dict[str, str]:
        """Record digests for new values; reassemble complete locales."""
        result: Dict[str, str] = {}
        for lang in self.languages:
            bundle = self.dir / f"{lang}.json"
            if not bundle.is_file():
                continue
            doc = read_json(bundle)
            meta = doc.setdefault("_meta", {})
            digests: Dict[str, str] = meta.setdefault("source_digests", {})
            values = flatten(doc)
            for key in values:
                if key in self.en and key not in digests:
                    digests[key] = self.digests[key]  # written by this run, from this English
            meta["source_digests"] = {k: digests[k] for k in self.en if k in digests}
            write_json(bundle, doc)
            have = {k: v for k, v in values.items() if k in self.en and v.strip()}
            if len(have) < len(self.en):
                result[lang] = f"partial {len(have)}/{len(self.en)}"
                continue
            if write_files:
                target = accord_path(self.localized, self.version, lang, self.stem)
                target.write_text(self.render(lang, have), encoding="utf-8")
                result[lang] = f"complete -> {target.name}"
            else:
                result[lang] = "complete"
        return result

    def verify(self) -> List[str]:
        """Offline gate: everything that must hold for what a lane committed."""
        problems: List[str] = []
        if seg.reassemble(self.doc) != self.source_text:
            problems.append("English source does not round-trip through the segmenter")
        for lang in self.languages:
            bundle = self.dir / f"{lang}.json"
            if not bundle.is_file():
                continue
            values = flatten(read_json(bundle))
            for key, text in values.items():
                slot = self.slots.get(key)
                if slot is None:
                    problems.append(f"{lang}: {key} is not a segment of the English source")
                    continue
                for why in seg.passage_problems(slot, text, lang):
                    problems.append(f"{lang}: {key}: {why}")
            shipped = accord_path(self.localized, self.version, lang, self.stem)
            if all(values.get(k, "").strip() for k in self.en) and shipped.is_file():
                if shipped.read_text(encoding="utf-8") != self.render(lang, values):
                    problems.append(f"{lang}: {shipped.name} differs from its reassembled bundle")
        for lang in self.languages:
            mirror = self.localized / lang
            if mirror.is_dir() and any(mirror.glob("accord*")):
                problems.append(f"{lang}: per-locale accord mirror at {mirror} (polyglot artifacts load universally)")
        return problems


# ─────────────────────────────────────────────────────────────────────────────
# Translation memory: the previous accord, aligned
# ─────────────────────────────────────────────────────────────────────────────


def default_stage_dir(version: str, stem: str = DEFAULT_STEM) -> Path:
    """``localization/accord/<version>`` for the Accord (unchanged), else
    ``localization/accord/<stem>_<version>``."""
    check_version(version)
    return STAGE_ROOT / (version if check_stem(stem) == DEFAULT_STEM else f"{stem}_{version}")


def build_tm(localized: Path, tm_version: str, lang: str, tm_stem: str = DEFAULT_STEM) -> TM:
    """``{key: (english, shipped translation)}`` from the previous accord.

    Lines the accord guard would reject (left in English, wrong script, a
    dropped CC reference) are not memory: an anchor teaches by example.
    """
    en_path = accord_path(localized, tm_version, "en", tm_stem)
    lo_path = accord_path(localized, tm_version, lang, tm_stem)
    if not en_path.is_file() or not lo_path.is_file():
        return {}
    en_doc = seg.parse(en_path.read_text(encoding="utf-8"))
    aligned, _ = seg.align(en_doc, seg.parse(lo_path.read_text(encoding="utf-8")))
    slots = {s.key: s for s in en_doc.slots}
    return {
        k: (slots[k].text, v) for k, v in aligned.items() if v.strip() and not seg.passage_problems(slots[k], v, lang)
    }


def _tokens(text: str) -> Set[str]:
    return {w.lower() for w in _TOKEN.findall(text)} - _STOP


def _similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 1.0 if a.strip() == b.strip() else 0.0
    return len(ta & tb) / len(ta | tb)


def make_anchors(
    tms: Dict[str, TM], extra: Optional[Dict[str, List["ExtraAnchor"]]] = None
) -> Callable[..., List[Tuple[str, str, str]]]:
    """An ``anchors_for`` with localize.py's signature, over the accord TM.

    ``extra`` (``--extra-tm``) adds terminology anchors from the website and app
    corpora AFTER the accord TM's, on their own budget, so the accord TM's
    anchors are exactly what they are without it.
    """
    if not extra:
        return _accord_anchors(tms)
    accord = _accord_anchors(tms)

    def anchors_for(
        lang: str, needed: Sequence[str], en_flat: Dict[str, Any], *, limit: int = ACCORD_ANCHOR_LIMIT
    ) -> List[Tuple[str, str, str]]:
        return accord(lang, needed, en_flat, limit=limit) + extra_anchors(extra.get(lang, []), needed, en_flat)

    return anchors_for


def _accord_anchors(tms: Dict[str, TM]) -> Callable[..., List[Tuple[str, str, str]]]:
    def anchors_for(
        lang: str, needed: Sequence[str], en_flat: Dict[str, Any], *, limit: int = ACCORD_ANCHOR_LIMIT
    ) -> List[Tuple[str, str, str]]:
        tm = tms.get(lang, {})
        picked: List[Tuple[str, str, str]] = []
        seen: Set[str] = set()

        def take(key: str) -> None:
            if key in seen or key not in tm:
                return
            english, shipped = tm[key]
            if len(english) > ACCORD_MAX_ANCHOR_CHARS or len(shipped) > ACCORD_MAX_ANCHOR_CHARS:
                return
            picked.append((key, english, shipped))
            seen.add(key)

        # 0. The previous edition's translation of this EXACT English line,
        #    wherever it sat. 1.2b -> 1.3 inserts lines, which shifts keys within
        #    a section; the text, not the key, is what identifies the line.
        by_text: Dict[str, List[str]] = {}
        for tm_key, (english, _) in tm.items():
            by_text.setdefault(english, []).append(tm_key)
        for key in needed:
            for tm_key in by_text.get(str(en_flat.get(key, "")), [])[:1]:
                take(tm_key)
        # 1. The previous translation of THIS key, where it still is one.
        for key in needed:
            if key in tm and _similarity(tm[key][0], str(en_flat.get(key, ""))) >= SAME_KEY_MIN_SIMILARITY:
                take(key)
        # 2. How this edition renders the document's own name (see point 5).
        texts = " ".join(str(en_flat.get(k, "")) for k in needed)
        if re.search(r"\bAccord\b", texts, re.I) and not any(re.search(r"\bAccord\b", e, re.I) for _, e, _ in picked):
            for key in sorted(tm, key=lambda k: len(tm[k][0])):
                if re.search(r"\bAccord\b", tm[key][0], re.I):
                    take(key)
                    break
        # 3. Lines that share vocabulary with what is being translated.
        want: Set[str] = set()
        for key in needed:
            want |= _tokens(str(en_flat.get(key, "")))
        if want:
            scored = []
            for key, (english, _) in tm.items():
                toks = _tokens(english)
                hit = len(want & toks)
                if hit and key not in seen:
                    scored.append((hit / len(toks | want), hit, key))
            for _, _, key in sorted(scored, key=lambda s: (-s[0], -s[1], s[2])):
                if len(picked) >= limit:
                    break
                take(key)
        out: List[Tuple[str, str, str]] = []
        budget = ACCORD_MAX_ANCHOR_BLOCK_CHARS
        for key, english, shipped in picked[:limit]:
            cost = len(key) + len(english) + len(shipped) + 16
            if cost > budget:
                continue
            out.append((key, english, shipped))
            budget -= cost
        return out

    return anchors_for


# ─────────────────────────────────────────────────────────────────────────────
# Extra translation memory: the website and app corpora (--extra-tm), anchors only
# ─────────────────────────────────────────────────────────────────────────────
#
# Users read CIRIS in three more places than the Accord: the website, the apps,
# and the agent's own interface. Each has its own machine-translated, MQM-judged
# corpus. Anchors from them keep a shared term reading the same way everywhere.
#
# They are ANCHORS, never values: nothing here reaches Stage.seed_tm, a bundle
# or a written file. Only the accord TM seeds (--seed-exact-tm).


class ExtraAnchor(NamedTuple):
    """One (English, translation) pair from an extra corpus, as an anchor."""

    rank: int  # 1 website, 2 client, 3 agent UI (the accord TM is 0)
    key: str  # "<source>:<flat key>", so the prompt says where it came from
    english: str
    text: str
    tokens: FrozenSet[str]


#: ``(source name, rank, bundle dirs relative to the corpus root)``. A root is
#: recognised by these layouts, and anything else is refused. The client's
#: androidApp / iosApp / desktopApp bundles are byte-identical mirrors of the
#: shared one, so only the shared one is read.
EXTRA_LAYOUTS: Tuple[Tuple[str, int, Tuple[str, ...]], ...] = (
    ("website", 1, ("src/i18n/dictionaries", "src/i18n/chrome")),
    ("client", 2, ("client/shared/src/desktopMain/resources/localization",)),
    ("agent-ui", 3, ("ciris_engine/data/localized",)),
)

#: Bounds, per request (one request = one language x one unit). Per KEY of the
#: unit at most EXTRA_PER_KEY anchors, round-robin across keys; per request at
#: most EXTRA_ANCHOR_LIMIT anchors and EXTRA_MAX_BLOCK_CHARS characters. These
#: are UI strings: an anchor longer than EXTRA_MAX_ANCHOR_CHARS is a paragraph,
#: not a term.
EXTRA_PER_KEY = 2
EXTRA_ANCHOR_LIMIT = 24
EXTRA_MAX_BLOCK_CHARS = 3000
EXTRA_MAX_ANCHOR_CHARS = 120
#: An entry is a candidate for a line only when EVERY content word of it occurs
#: in the line (a term or phrase the line uses, not one that shares a word), it
#: has at most this many content words, and -- if it is a single word -- that
#: word is at least EXTRA_MIN_SINGLE_WORD letters and not a function word. UI
#: corpora are full of "Next", "Open", "Who": as anchors those are noise, and an
#: imperative button sense can mislead.
EXTRA_MAX_TERM_WORDS = 5
EXTRA_MIN_SINGLE_WORD = 6
_EXTRA_STOP = frozenset(
    """about above after again against all also am any are as at be because been before being below between
    both but by can cannot could did do does doing down during each either else even ever every few from
    further had has have having he her here hers him his how if into it its itself just least less let like
    may me might more most much must my neither never no nor not now of off on once one only other ought our
    ours out over own per rather same shall she should since so some still such than their theirs them then
    there these they those though through thus till too under until up upon us very via was we were what
    when where whether which while who whom whose why will with within without would yet you your yours
    another anything everything nothing something someone everyone nobody whatever whichever""".split()
)

#: File-level ``_meta.status`` / ``_meta.review_status`` values that exclude a
#: whole file. ``draft`` / ``needs_native_review`` / ``machine_reviewed`` are NOT
#: here: they are the lifecycle stamp of every machine-translated file in all
#: four corpora (the accord TM itself is ``draft / machine_reviewed``), each of
#: which went through the MQM judge. A file that says it never did is excluded.
EXTRA_REJECTED_STATUSES = frozenset(
    {"unreviewed", "untranslated", "stub", "placeholder", "wip", "pending", "rejected", "machine_unreviewed"}
)
#: Review findings this severe on a value that is still current exclude it.
EXTRA_REJECTED_SEVERITIES = frozenset({"critical", "major"})

_HTML = re.compile(r"<[A-Za-z/!]")
_PLACEHOLDERISH = re.compile(r"\{[^}]*\}|%\d*\$?[sdf@]|\$\{")
_ACCORD_NAME = re.compile(r"\bAccord\b", re.I)


def _flat_strings(obj: Any, prefix: str = "") -> Dict[str, str]:
    """Nested JSON -> flat dotted keys. Arrays, non-strings and ``_``-prefixed
    subtrees (``_meta``) are skipped."""
    out: Dict[str, str] = {}
    if not isinstance(obj, dict):
        return out
    for k, v in obj.items():
        if not isinstance(k, str) or k.startswith("_"):
            continue
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flat_strings(v, key))
        elif isinstance(v, str):
            out[key] = v
    return out


def _file_status(doc: Dict[str, Any]) -> Optional[str]:
    meta = doc.get("_meta")
    if not isinstance(meta, dict):
        return None
    for field in ("status", "review_status"):
        value = meta.get(field)
        if isinstance(value, str) and value.strip().lower() in EXTRA_REJECTED_STATUSES:
            return f"{field}={value}"
    return None


def _flagged_keys(root: Path, lang: str) -> Set[str]:
    """Keys a corpus's own review flagged for ``lang``, where it records them.

    The website's pipeline writes ``localization/hard-cases/`` (git-ignored, so
    present only in a local checkout): ``hard-cases-*.json`` cases are strings
    the judge rejected or the ladder could not fix, and ``review-<lang>-*.json``
    holds MQM findings. A judge-rejected key, or a critical/major finding on a
    value that is still current, is not an exemplar.
    """
    hard = root / "localization" / "hard-cases"
    out: Set[str] = set()
    if not hard.is_dir():
        return out
    for path in sorted(hard.glob("hard-cases-*.json")):
        try:
            cases = read_json(path).get("cases", [])
        except (OSError, ValueError):
            continue
        for case in cases if isinstance(cases, list) else []:
            if isinstance(case, dict) and case.get("lang") == lang and isinstance(case.get("key"), str):
                out.add(case["key"])
    for path in sorted(hard.glob(f"review-{lang}-*.json")):
        try:
            findings = read_json(path).get("findings", {})
        except (OSError, ValueError):
            continue
        bundle = path.stem.split("-", 2)[-1]
        current: Dict[str, str] = {}
        for d in EXTRA_LAYOUTS[0][2]:
            if Path(d).name == bundle and (root / d / f"{lang}.json").is_file():
                current = _flat_strings(read_json(root / d / f"{lang}.json"))
        for key, finding in findings.items() if isinstance(findings, dict) else []:
            if not isinstance(finding, dict):
                continue
            severe = any(
                isinstance(e, dict) and e.get("severity") in EXTRA_REJECTED_SEVERITIES
                for e in finding.get("errors", [])
            )
            if severe and current.get(key) == finding.get(lang):
                out.add(key)
    return out


def _usable(english: str, text: str, lang: str) -> Optional[str]:
    """Why this pair is not an anchor, or None."""
    e, t = english.strip(), text.strip()
    if not e or not t:
        return "empty"
    if e == t:
        return "same_as_english"
    if len(e) > EXTRA_MAX_ANCHOR_CHARS or len(t) > EXTRA_MAX_ANCHOR_CHARS:
        return "too_long"
    if "\n" in e or "\n" in t or _HTML.search(e) or _HTML.search(t):
        return "markup"
    if _PLACEHOLDERISH.search(e) or _PLACEHOLDERISH.search(t):
        return "placeholder"
    if _ACCORD_NAME.search(e):
        # The document's own name is pinned to the accord TM's rendering.
        return "names_the_accord"
    if any(claim in e or claim in t for claim in seg.WITHDRAWN):
        return "withdrawn_claim"
    rng = seg.SCRIPT.get(lang)
    if rng and not re.search(f"[{rng}]", t):
        return "wrong_script"
    terms = _term_tokens(e)
    if not terms or len(terms) > EXTRA_MAX_TERM_WORDS:
        return "not_a_term"
    if len(terms) == 1 and len(next(iter(terms))) < EXTRA_MIN_SINGLE_WORD:
        return "not_a_term"
    return None


def _term_tokens(text: str) -> FrozenSet[str]:
    return frozenset(_tokens(text) - _EXTRA_STOP)


class ExtraCorpus(NamedTuple):
    name: str
    rank: int
    root: Path
    commit: str


def detect_extra(root: Path) -> List[ExtraCorpus]:
    """The corpora a ``--extra-tm`` root holds. Refuses a root that holds none."""
    root = root.resolve()
    found = []
    for name, rank, dirs in EXTRA_LAYOUTS:
        if any((root / d / "en.json").is_file() for d in dirs):
            found.append(ExtraCorpus(name, rank, root, _commit_of(root)))
    if not found:
        layouts = ", ".join(f"{n}: {' | '.join(d)}" for n, _, d in EXTRA_LAYOUTS)
        raise SystemExit(f"[refuse] --extra-tm {root}: no known corpus layout ({layouts})")
    return found


def _commit_of(root: Path) -> str:
    """The checkout's commit, for provenance; read-only. Only the root's OWN
    repository: a plain directory inside another checkout is "unknown", not
    its parent's HEAD."""
    if not (root / ".git").exists():
        return "unknown"
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return out.stdout.strip() if out.returncode == 0 else "unknown"


def load_extra_tm(
    roots: Sequence[Path], langs: Sequence[str]
) -> Tuple[Dict[str, List[ExtraAnchor]], List[Tuple[ExtraCorpus, Dict[str, Dict[str, int]]]]]:
    """``{lang: [anchors]}`` from every root, plus per-corpus stats.

    De-duplicated by English across corpora: the same label in the website and
    the client is ONE anchor, from the higher-ranked corpus.
    """
    corpora = sorted((c for r in roots for c in detect_extra(Path(r))), key=lambda c: c.rank)
    seen_roots: Set[Tuple[str, Path]] = set()
    out: Dict[str, List[ExtraAnchor]] = {lang: [] for lang in langs}
    taken: Dict[str, Set[str]] = {lang: set() for lang in langs}
    report: List[Tuple[ExtraCorpus, Dict[str, Dict[str, int]]]] = []
    dirs_of = {name: dirs for name, _, dirs in EXTRA_LAYOUTS}
    for corpus in corpora:
        if (corpus.name, corpus.root) in seen_roots:
            continue
        seen_roots.add((corpus.name, corpus.root))
        stats: Dict[str, Dict[str, int]] = {}
        for lang in langs:
            s: Dict[str, int] = {}
            flagged = _flagged_keys(corpus.root, lang)
            for d in dirs_of[corpus.name]:
                en_path, lo_path = corpus.root / d / "en.json", corpus.root / d / f"{lang}.json"
                if not en_path.is_file() or not lo_path.is_file():
                    continue
                lo_doc = read_json(lo_path)
                why_file = _file_status(lo_doc)
                en_flat, lo_flat = _flat_strings(read_json(en_path)), _flat_strings(lo_doc)
                if why_file:
                    s["file_" + why_file.split("=")[0]] = s.get("file_" + why_file.split("=")[0], 0) + len(lo_flat)
                    continue
                for key in sorted(lo_flat):
                    english = en_flat.get(key)
                    if english is None:
                        why: Optional[str] = "no_english"
                    elif key in flagged:
                        why = "review_flagged"
                    else:
                        why = _usable(english, lo_flat[key], lang)
                    if why is None and english is not None:
                        norm = " ".join(english.split()).lower()
                        if norm in taken[lang]:
                            why = "duplicate"
                        else:
                            taken[lang].add(norm)
                            out[lang].append(
                                ExtraAnchor(
                                    corpus.rank,
                                    f"{corpus.name}:{key}",
                                    english.strip(),
                                    lo_flat[key].strip(),
                                    frozenset(_tokens(english)),
                                )
                            )
                    s[why or "kept"] = s.get(why or "kept", 0) + 1
            stats[lang] = s
        report.append((corpus, stats))
    return out, report


def extra_anchors(
    pool: Sequence[ExtraAnchor], needed: Sequence[str], en_flat: Dict[str, Any]
) -> List[Tuple[str, str, str]]:
    """Terminology anchors for one request, bounded (see EXTRA_* above).

    An entry is a candidate for a line when every content word of it occurs in
    that line: a term the line uses. Candidates rank by the summed rarity (idf
    over the pool) of their words -- multi-word and rarer terms first -- then
    corpus rank (website, client, agent UI), then brevity. Each key contributes
    at most EXTRA_PER_KEY, taken round-robin so every line gets its best term
    before any line gets its second; the result is emitted grouped by corpus
    rank.
    """
    if not pool:
        return []
    df: Dict[str, int] = {}
    index: Dict[str, List[int]] = {}
    for i, a in enumerate(pool):
        for t in a.tokens - _EXTRA_STOP:
            df[t] = df.get(t, 0) + 1
            index.setdefault(t, []).append(i)
    n = len(pool)

    def idf(t: str) -> float:
        return math.log((n + 1) / (df.get(t, 0) + 1)) + 1.0

    per_key: List[List[Tuple[float, int]]] = []
    for key in needed:
        # Containment is over ALL the entry's words, function words included,
        # so "No Memories" is not offered to a line about memories.
        line = frozenset(_tokens(str(en_flat.get(key, ""))))
        cands: Dict[int, float] = {}
        for t in line - _EXTRA_STOP:
            for i in index.get(t, []):
                if i not in cands and pool[i].tokens <= line:
                    cands[i] = sum(idf(x) for x in pool[i].tokens - _EXTRA_STOP)
        ranked = sorted(cands.items(), key=lambda c: (-c[1], pool[c[0]].rank, len(pool[c[0]].english), pool[c[0]].key))
        per_key.append([(score, i) for i, score in ranked])
    # A key's anchors are its top EXTRA_PER_KEY candidates (shared with another
    # key, they appear once); round-robin by depth, so every key's best comes
    # before any key's second.
    chosen: List[Tuple[float, int]] = []
    seen: Set[int] = set()
    for depth in range(EXTRA_PER_KEY):
        for cands_k in per_key:
            if depth < len(cands_k) and cands_k[depth][1] not in seen:
                chosen.append(cands_k[depth])
                seen.add(cands_k[depth][1])
    out: List[Tuple[float, int]] = []
    budget = EXTRA_MAX_BLOCK_CHARS
    for score, i in chosen[:EXTRA_ANCHOR_LIMIT]:
        a = pool[i]
        cost = len(a.key) + len(a.english) + len(a.text) + 16
        if cost > budget:
            continue
        out.append((score, i))
        budget -= cost
    out.sort(key=lambda c: (pool[c[1]].rank, -c[0], pool[c[1]].key))
    return [(pool[i].key, pool[i].english, pool[i].text) for _, i in out]


def print_extra_report(report: Sequence[Tuple[ExtraCorpus, Dict[str, Dict[str, int]]]]) -> None:
    """One line per corpus: provenance (commit) and what was kept or skipped."""
    for corpus, stats in report:
        kept = sum(s.get("kept", 0) for s in stats.values())
        skipped: Dict[str, int] = {}
        for s in stats.values():
            for why, count in s.items():
                if why != "kept":
                    skipped[why] = skipped.get(why, 0) + count
        why_text = ", ".join(f"{k}={v}" for k, v in sorted(skipped.items()))
        print(
            f"[extra-tm] {corpus.name} (rank {corpus.rank}) {corpus.root.name}@{corpus.commit}: "
            f"{kept} anchor(s) across {len(stats)} locale(s); skipped {why_text or 'none'}"
        )


_EXTRA_RULE = """
ANCHORS FROM THE WEBSITE AND APPS. Anchor keys that start with "website:",
"client:" or "agent-ui:" are NOT lines of this document. They are this
language's shipped strings from the CIRIS website, the CIRIS apps and the
agent's own interface: what its users already read. They are there for the
TERMS they share with these lines, so one concept reads the same way
everywhere, and for register. They do not override the CANONICAL TERMINOLOGY
block, nor the document's own name as the previous edition renders it, and a
UI label's brevity is not a model for this document's voice."""

_EXTRA_RULE_REVIEW = (
    _EXTRA_RULE + "\nA term rendered as those anchors render it is not a terminology finding on that ground alone."
)
# ─────────────────────────────────────────────────────────────────────────────

_ACCORD_RULES = """- These lines are the CIRIS Accord: a governance covenant the agent reads
  before it acts. Keep its voice -- philosophical, at times poetic, never a
  manual. Translate; do not summarise, expand, explain or add notes, and do not
  carry over any claim that is not in the English line.
- Each key is ONE LINE of the document, in order; neighbouring keys are the
  surrounding lines, for context. Return one line per key: no line breaks.
  Markup at the start of a line (heading marks, list markers) is not shown to
  you and is restored around your text -- do not add any.
- Keep inline markers where the source has them: `**bold**`, `*italic*`.
- These stay exactly as written, in Latin script: every "CC n.n.n" reference,
  RATCHET#17, M-1, PDMA, WBD, LensCore, J, k_eff, λ_op, σ, ρ̄, k, CIRIS, and any
  formula.
- The document's own name, "Accord", is rendered exactly as the ANCHOR
  TRANSLATIONS (this language's shipped previous edition) render it. Do not coin
  a new rendering, and a reviewer must not report the anchors' rendering."""


def accord_prompts(L: ModuleType, stem: str = DEFAULT_STEM) -> Dict[str, str]:
    rules: str = L.GUIDE_RULES
    placeholder: str = L._PLACEHOLDER_RULE
    translate = (
        "You translate lines of the CIRIS Accord, the covenant of the CIRIS ethical "
        "AI agent, into ONE target language. The agent ships in 29 languages; this "
        "edition is what it reads in the user's language.\n\n"
        "Rules, all of them hard:\n"
        "- Return ONLY a JSON object. No markdown fences, no commentary.\n"
        '- The object has two members: "translations" (key -> translated line) and\n'
        '  "refusals" (key -> one-sentence reason). Every requested key appears in\n'
        "  exactly one of them.\n"
        f"{placeholder}\n{_ACCORD_RULES}\n"
        "- The CANONICAL TERMINOLOGY block is decided, not advisory. Use those renderings\n"
        "  exactly, including diacritics and tone marks.\n"
        "- The ANCHOR TRANSLATIONS are this language's shipped edition of the PREVIOUS\n"
        "  Accord. Where a line is unchanged in meaning, stay close to its anchor; match\n"
        "  their register, formality and terminology throughout.\n"
        '- USE "refusals" ONLY IF YOU GENUINELY CANNOT PRODUCE A FAITHFUL TRANSLATION.\n'
        "  A refusal is routed to a stronger model rather than shipped. Never return\n"
        "  English text as a translation, never transliterate the English, and never\n"
        "  invent a plausible-looking line you do not stand behind.\n\n"
        "WHAT WENT WRONG BEFORE. Every one of these was a real finding on a real run of\n"
        "this pipeline, in some language:\n" + rules
    )
    review = (
        "You are an independent translation quality reviewer for the CIRIS Accord, the "
        "covenant of the CIRIS ethical AI agent. You did not write these translations.\n\n"
        "Annotate each one with MQM error spans. Categories: accuracy (mistranslation,\n"
        "omission, addition), fluency (grammar, spelling, unnatural phrasing, and\n"
        "NON-WORDS OR WORD-SALAD), terminology (disagrees with the canonical glossary\n"
        "supplied), style (register or voice wrong for a covenant), locale (script,\n"
        "numerals, punctuation, direction wrong for this language).\n"
        "Severities: critical (the reader is misled, or the line is unusable),\n"
        "major (clearly wrong but the intent survives), minor (a nit).\n\n"
        "Return ONLY a JSON object mapping each key to a list of error objects:\n"
        '  {"accord.v1.s01.l01": [{"category":"accuracy","severity":"major",\n'
        '      "span":"<the offending text>","note":"<what is wrong>",\n'
        '      "suggestion":"<what it should be>"}],\n'
        '   "accord.v1.s01.title": []}\n'
        "An empty list means no error found. Every key you were given must appear.\n\n"
        f"Judge hard and specifically:\n{placeholder}\n{_ACCORD_RULES}\n"
        "- A line that is fluent but says something the English does not is ACCURACY\n"
        "  critical, not style. An obligation softened or strengthened (must/should/may)\n"
        "  is accuracy critical: this text governs what the agent does.\n"
        "- A line containing invented or garbled words in the target language is\n"
        "  FLUENCY critical. This is the failure a structural check cannot see and the\n"
        "  one you are most needed for.\n"
        "- A term that disagrees with the CANONICAL TERMINOLOGY block is TERMINOLOGY.\n"
        "- Do NOT invent errors to look thorough. An empty list is the correct and\n"
        "  expected answer for a good translation. Agreement with the glossary is not a\n"
        "  finding, and neither is differing from a glossary row's table casing.\n\n"
        "LOOK FOR THESE SPECIFICALLY. Each is a defect this pipeline has actually shipped\n"
        "past a structural gate, in some language, on some run:\n" + rules
    )
    repair = (
        "You are correcting CIRIS Accord translations that a reviewer rejected. You will "
        "receive the English line, the current translation, and the reviewer's MQM "
        "findings for each key.\n\n"
        "Rules:\n"
        '- Return ONLY a JSON object with "translations" (key -> corrected line) and\n'
        '  "refusals" (key -> reason), exactly as the translation lane uses.\n'
        "- FIX WHAT WAS FOUND. Do not rewrite what was not flagged.\n"
        "- If you judge a finding to be WRONG, return the current translation unchanged\n"
        '  and say so in "refusals".\n'
        f"{placeholder}\n{_ACCORD_RULES}\n"
        "- The CANONICAL TERMINOLOGY block wins every terminology dispute.\n\n"
        "THE DEFECTS YOU ARE MOST LIKELY CORRECTING. Each has been a real finding here:\n" + rules
    )
    doc = STEMS[check_stem(stem)][0]
    out = {"SYSTEM_TRANSLATE": translate, "SYSTEM_REVIEW": review, "SYSTEM_REPAIR": repair}
    if doc != STEMS[DEFAULT_STEM][0]:
        out = {k: v.replace("the CIRIS Accord", doc).replace("CIRIS Accord translations", f"translations of {doc}")
               for k, v in out.items()}  # fmt: skip
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Wiring the vendored module
# ─────────────────────────────────────────────────────────────────────────────


class Context:
    """What the hooks need to know about the current pass."""

    keys: Optional[Set[str]] = None  # the unit being run (None = all)
    lang: Optional[str] = None  # the language being drafted or repaired
    stage: str = "draft"  # what produced the strings now under review
    candidate_log: Optional[Path] = None  # --candidate-log: every reviewed string, with its verdict


def accord_terms(rows: Dict[str, str], code: str, stem: str) -> Dict[str, str]:
    """The live glossary rows an accord run of ``stem`` sends for ``code``."""
    out = dict(rows)
    for english, (table, used) in GLOSSARY_RECASE.get(code, {}).items():
        if out.get(english) == table:
            out[english] = used
    if stem == "constitution_ethics":
        removed = {e.casefold() for e in CONSTITUTION_ETHICS_GLOSSARY_REMOVE.get(code, ())}
        out = {
            e: t
            for e, t in out.items()
            if e.strip().lower() not in CONSTITUTION_ETHICS_GLOSSARY_DROP
            and not VERSION_ROW.fullmatch(e.strip())
            and e.strip().casefold() not in removed
        }
        fixes = {e.casefold(): t for e, t in CONSTITUTION_ETHICS_GLOSSARY_FIX.get(code, {}).items()}
        out = {e: fixes.get(e.strip().casefold(), t) for e, t in out.items()}
        leftover = set(english_renderings(out, code))
        out = {e: t for e, t in out.items() if e not in leftover}
        if code in ETHICS_TEXT_RENDERINGS:
            out[ETHICS_TEXT_TERM] = ETHICS_TEXT_RENDERINGS[code]
        out.update(CONSTITUTION_ETHICS_TERM_PINS.get(code, {}))
    return out


def _contains_term(longer: str, short: str) -> bool:
    """Is ``short`` a whole-word phrase inside ``longer``?"""
    if len(short) >= len(longer):
        return False
    return re.search(rf"\b{re.escape(short.strip().lower())}\b", longer.strip().lower()) is not None


def drop_contained(
    chosen: Sequence[str], texts: Sequence[str], mentions: Callable[[str, List[str]], bool]
) -> List[str]:
    """Drop a term that occurs in ``texts`` ONLY inside a longer chosen term.

    Ported from the ciris-website copy of glossary.py (a local patch there).
    Such a term is not a separate instruction: it is the same words counted
    twice, and sending both makes the block contradict itself. Vietnamese pinned
    both "Constitutional Mesh" and "Constitutional"; the one phrase
    "decentralized constitutional mesh" contains both, so every rendering broke
    one row and the reviewer could always cite the other. A shorter term is kept
    when it also occurs on its own, so "Authority" survives beside "Wise
    Authority" in a text that uses both.
    """
    hay = " \n ".join(texts).lower()
    keep: List[str] = []
    for short in chosen:
        longer = [c for c in chosen if c != short and _contains_term(c, short)]
        if longer:
            rest = hay
            for c in sorted(longer, key=len, reverse=True):
                rest = rest.replace(c.lower(), " ")
            if not mentions(short, [rest]):
                continue
        keep.append(short)
    return keep


def make_relevant(gloss: ModuleType) -> Callable[..., Dict[str, str]]:
    """The vendored ``relevant`` (longest-first, whole-word) plus ``drop_contained``."""

    def relevant(code: str, texts: List[str], *, limit: int = 60) -> Dict[str, str]:
        all_terms: Dict[str, str] = gloss.terms(code)
        if not all_terms:
            return {}
        hits = sorted(((len(e), e) for e in all_terms if gloss._mentions(e, texts)), key=lambda p: (-p[0], p[1]))
        chosen = drop_contained([e for _, e in hits], texts, gloss._mentions)
        return {e: all_terms[e] for e in chosen[:limit]}

    return relevant


def import_localize(stage_dir: Path) -> ModuleType:
    """Import vendored localize.py against the staged accord bundle."""
    os.environ["LOCALIZE_TARGET"] = "accord"
    os.environ["LOCALIZE_ACCORD_STAGE"] = str(stage_dir.resolve())
    for name in ("localize", "check_localization_sync", "glossary"):
        sys.modules.pop(name, None)
    # The vendored module, unmodified; typed as a plain module on purpose -- it
    # is not ours to annotate, and every hook below is set with setattr.
    return importlib.import_module("localize")


def install(L: ModuleType, stage: Stage, tms: Dict[str, TM]) -> None:
    """Point the vendored module's hooks at the accord."""
    # Concurrent lane shards share one provider key: wait out 402/429/5xx in
    # place instead of letting the vendored code read them as a dead rung.
    lane_backoff.install(L)
    for name, text in accord_prompts(L, stage.stem).items():
        if stage.extra_tm:
            text += _EXTRA_RULE_REVIEW if name == "SYSTEM_REVIEW" else _EXTRA_RULE
        setattr(L, name, text)
    setattr(L, "anchors_for", make_anchors(tms, stage.extra_tm))

    # Glossary: the deprecated ACCORD row is the document's own name here.
    upstream_deprecated = L.gloss.deprecated

    def deprecated(code: str) -> Dict[str, str]:
        rows: Dict[str, str] = upstream_deprecated(code)
        return {e: t for e, t in rows.items() if e.strip().upper() not in ACCORD_GLOSSARY_DROP}

    setattr(L.gloss, "deprecated", deprecated)

    # Live rows: re-cased renderings, and for the ethics text its own name in
    # place of the pipeline-stage "Ethics" label. The vendored relevant(),
    # block() and require() all read terms() through the module global.
    upstream_terms = L.gloss.terms

    def terms(code: str) -> Dict[str, str]:
        return accord_terms(upstream_terms(code), code, stage.stem)

    setattr(L.gloss, "terms", terms)
    setattr(L.gloss, "relevant", make_relevant(L.gloss))

    upstream_guidance = L.gloss.guidance

    def guidance(code: str) -> List[Tuple[str, str]]:
        return accord_guidance(upstream_guidance(code), stage.stem)

    setattr(L.gloss, "guidance", guidance)

    # The drafting rung (VENDORED.md, "Local divergences"). Only when nobody
    # chose a ladder: LOCALIZE_LADDER wins, and the Anthropic SDK path cannot
    # reach a non-Anthropic drafter at all.
    if L.PROVIDER == "openrouter" and not os.environ.get("LOCALIZE_LADDER"):
        setattr(L, "LADDER", (ACCORD_DRAFTER, *L.LADDER[1:]))
    for model, price in ACCORD_PRICE.items():
        L.PRICE.setdefault(model, price)

    # Which language a structural check is about: the vendored check does not
    # take one, and the script / untranslated rules need it.
    upstream_translate_lane = L.translate_lane
    upstream_repair_once = L._repair_once

    def translate_lane(lang: str, *args: Any, **kwargs: Any) -> Any:
        Context.lang = lang
        try:
            return upstream_translate_lane(lang, *args, **kwargs)
        finally:
            Context.lang = None
            Context.stage = "draft"

    def repair_once(lang: str, model: str, *args: Any, **kwargs: Any) -> Any:
        Context.lang = lang
        Context.stage = f"repair:{model}"
        try:
            return upstream_repair_once(lang, model, *args, **kwargs)
        finally:
            Context.lang = None

    setattr(L, "translate_lane", translate_lane)
    setattr(L, "_repair_once", repair_once)

    # Every string the judge reviews, with the judge's findings as returned.
    # The vendored lane keeps only the last verdict and drops a rejected
    # string's text, so without this record a withheld key has no candidate to
    # accept under --accept-minor.
    upstream_evaluate = L.evaluate_lane

    def evaluate_lane(lang: str, values: Dict[str, str], *args: Any, **kwargs: Any) -> Any:
        findings: Dict[str, List[Dict[str, Any]]] = upstream_evaluate(lang, values, *args, **kwargs)
        if Context.candidate_log is not None:
            with Context.candidate_log.open("a", encoding="utf-8") as fh:
                for key in sorted(findings):
                    row = {
                        "lang": lang,
                        "key": key,
                        "source_digest": stage.digests.get(key),
                        "stage": Context.stage,
                        "candidate": values.get(key),
                        "findings": findings[key],
                        "score": L.mqm_score(findings[key]),
                    }
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return findings

    setattr(L, "evaluate_lane", evaluate_lane)

    upstream_structural = L.structural_problems

    def structural_problems(keys: Sequence[str], en_flat: Dict[str, Any], got: Dict[str, str]) -> Dict[str, str]:
        bad: Dict[str, str] = upstream_structural(keys, en_flat, got)
        for key in keys:
            if key in bad or key not in stage.slots or not isinstance(got.get(key), str):
                continue
            problems = seg.passage_problems(stage.slots[key], got[key], Context.lang)
            if problems:
                bad[key] = "; ".join(problems)
        return bad

    setattr(L, "structural_problems", structural_problems)

    upstream_missing = L.missing_by_language

    def missing_by_language() -> Tuple[Dict[str, Any], Dict[str, List[str]]]:
        en_flat, missing = upstream_missing()
        if Context.keys is None:
            return en_flat, missing
        keep = Context.keys
        en_flat = {k: v for k, v in en_flat.items() if k in keep}
        missing = {lang: [k for k in ks if k in keep] for lang, ks in missing.items()}
        return en_flat, {lang: ks for lang, ks in missing.items() if ks}

    setattr(L, "missing_by_language", missing_by_language)


def _all_minor(findings: Any) -> bool:
    return (
        isinstance(findings, list)
        and bool(findings)
        and all(isinstance(e, dict) and e.get("severity") == MINOR_SEVERITY for e in findings)
    )


def accept_minor(stage: Stage, logs: Sequence[Path]) -> Dict[str, List[Dict[str, Any]]]:
    """Fill each withheld line with its best reviewed candidate whose objections are all minor.

    Ruling on #1325: a line still withheld after its pass takes the
    highest-scoring judge-reviewed candidate (``--candidate-log``) when every
    objection the judge raised is MQM severity ``minor``. A ``major`` or
    ``critical`` objection, or one with no severity, keeps it withheld. The
    severities are the judge's own, read from the log; nothing is inferred.
    Each acceptance is recorded in the bundle's ``_meta`` (key, candidate,
    objections verbatim) so a native audit can find it. Calls no model.
    """
    best: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for path in logs:
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            key, lang, text = row.get("key", ""), row.get("lang", ""), row.get("candidate")
            if key not in stage.slots or row.get("source_digest") != stage.digests[key] or not isinstance(text, str):
                continue
            if not _all_minor(row.get("findings")) or seg.passage_problems(stage.slots[key], text, lang):
                continue
            prev = best.get((lang, key))
            if prev is None or row["score"] >= prev["score"]:  # a tie goes to the later, higher rung
                best[(lang, key)] = row
    accepted: Dict[str, List[Dict[str, Any]]] = {}
    for lang in stage.languages:
        bundle = stage.dir / f"{lang}.json"
        if not bundle.is_file():
            continue
        doc = read_json(bundle)
        values = flatten(doc)
        meta = doc.setdefault("_meta", {})
        add = {k: best[(lang, k)] for k in stage.en if not values.get(k, "").strip() and (lang, k) in best}
        if not add:
            continue
        values.update({k: str(row["candidate"]) for k, row in add.items()})
        digests: Dict[str, str] = meta.get("source_digests", {})
        digests.update({k: stage.digests[k] for k in add})
        meta["source_digests"] = {k: digests[k] for k in stage.en if k in digests}
        entries = [e for e in meta.get(ACCEPTED_MINOR, []) if e.get("key") not in add]
        for k, row in add.items():
            entries.append(
                {
                    "key": k,
                    "source_digest": stage.digests[k],
                    "candidate": row["stage"],
                    "score": row["score"],
                    "text": row["candidate"],
                    "objections": [
                        f"{e.get('severity')}/{e.get('category')}: {e.get('note', '')}" for e in row["findings"]
                    ],
                }
            )
        order = {k: i for i, k in enumerate(stage.en)}
        meta[ACCEPTED_MINOR] = sorted(entries, key=lambda e: order.get(e["key"], len(order)))
        out: Dict[str, Any] = {"_meta": meta}
        out.update(nest({k: values[k] for k in stage.en if k in values}))
        write_json(bundle, out)
        accepted[lang] = [e for e in meta[ACCEPTED_MINOR] if e["key"] in add]
    return accepted


def units_of(stage: Stage) -> Dict[str, Set[str]]:
    out: Dict[str, Set[str]] = {}
    for key in stage.en:
        out.setdefault(key.split(".")[1], set()).add(key)
    return out


def run_localize(L: ModuleType, argv: Sequence[str]) -> int:
    saved = sys.argv
    sys.argv = ["localize.py", *argv]
    try:
        rc: int = L.main()
    except SystemExit as exc:  # localize refuses with SystemExit; keep going per unit
        code = exc.code
        if isinstance(code, int):
            rc = code
        else:
            print(code)
            rc = 1
    finally:
        sys.argv = saved
    return rc


def _merge_reports(paths: Iterable[Tuple[str, Path]], out: Path) -> None:
    merged: Dict[str, Any] = {}
    for unit, path in paths:
        if path.is_file():
            merged[unit] = read_json(path)
            path.unlink()
    write_json(out, merged)


def segments_report(stage: Stage) -> None:
    n = len(stage.en)
    chars = sum(len(v) for v in stage.en.values())
    langs = len(stage.languages)
    print(f"accord {stage.version}: {n} segment(s), {chars:,} English chars, {langs} target locale(s)")
    for unit, keys in units_of(stage).items():
        uchars = sum(len(stage.en[k]) for k in keys)
        print(
            f"  {unit:<12} {len(keys):>4} segment(s) {uchars:>7,} chars  x{langs} = {len(keys) * langs:>6,} key-values"
        )
    print(f"  full pass: {n} x {langs} = {n * langs:,} key-values")


def refuse_batch_mode(argv: Sequence[str]) -> None:
    """Refuse ``--mode batch`` before anything is staged or billed.

    The vendored ``call_model`` sends rung 0 as ``<model>:batch`` to OpenRouter's
    ``/chat/completions``. OpenRouter serves ``:batch`` slugs only through its
    async batch adapters (``AnthropicBatchAdapter``, ``VertexGeminiBatchAdapter``,
    ``OpenAIBatchAdapter``) and answers the chat endpoint with HTTP 404 "cannot be
    used with the chat/completions endpoint". So rung 0 died for every locale of
    run 38598155352, every key went to a higher rung at full price, and
    ``Spend.report(batch=True)`` still halved every line: the run reported
    ~$1.82 for about $3.64 of calls. Until the pipeline submits real batch jobs,
    the mode is refused rather than allowed to lose a rung and misreport.
    """
    for i, arg in enumerate(argv):
        mode = (
            arg.split("=", 1)[1]
            if arg.startswith("--mode=")
            else (argv[i + 1] if arg == "--mode" and i + 1 < len(argv) else None)
        )
        if mode == "batch":
            raise SystemExit(
                "[refuse] --mode batch: OpenRouter's :batch slugs are not served on "
                "/chat/completions (HTTP 404), so rung 0 is lost and the spend report "
                "halves costs that were billed in full. Use --mode fast."
            )


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument("--version", default=os.environ.get("ACCORD_VERSION", DEFAULT_TM_VERSION))
    ap.add_argument("--tm-version", default=DEFAULT_TM_VERSION, help="previous accord used as translation memory")
    ap.add_argument("--stem", default=DEFAULT_STEM, help=f"target filename stem, one of {sorted(STEMS)}")
    ap.add_argument("--tm-stem", default=DEFAULT_STEM, help="filename stem of the translation-memory edition")
    ap.add_argument(
        "--seed-exact-tm",
        action="store_true",
        help="seed lines whose English is unchanged from the TM edition with its shipped translation",
    )
    ap.add_argument(
        "--extra-tm",
        action="append",
        type=Path,
        default=[],
        metavar="DIR",
        help="a ciris-website, CIRISClient or CIRISAgent checkout whose translated strings become extra "
        "terminology anchors (never values); repeatable",
    )
    ap.add_argument("--units", default="", help="space-separated units to run (default: all, one at a time)")
    ap.add_argument("--stage-dir", type=Path, default=None, help=argparse.SUPPRESS)
    ap.add_argument("--localized-dir", type=Path, default=LOCALIZED, help=argparse.SUPPRESS)
    ap.add_argument("--segments", action="store_true", help="print the segment plan and run size, then exit")
    ap.add_argument("--verify", action="store_true", help="offline gate over the staged bundles and files")
    ap.add_argument("--no-reassemble", action="store_true", help="do not write accord files after the run")
    ap.add_argument(
        "--candidate-log",
        type=Path,
        default=None,
        metavar="JSONL",
        help="append every reviewed string, with the judge's findings, to this file",
    )
    ap.add_argument(
        "--accept-minor",
        action="append",
        type=Path,
        default=[],
        metavar="JSONL",
        help="fill withheld lines from a --candidate-log whose objections are all minor, then reassemble; "
        "calls no model (repeatable)",
    )
    args, rest = ap.parse_known_args(argv)
    refuse_batch_mode(rest)

    # READ-ONLY unless this is a lane run that may write. --check, --dry-run,
    # --glossary-report, --segments and --verify never touch the live bundles
    # (ciris_engine/data/localized) or the committed stage: a read-only pass
    # stages into a throwaway copy of the committed stage.
    read_only = args.segments or args.verify or any(f in rest for f in READ_ONLY_FLAGS)
    scratch: Optional[tempfile.TemporaryDirectory[str]] = None
    check_stem(args.stem)
    check_stem(args.tm_stem)
    stage_dir = args.stage_dir or default_stage_dir(args.version, args.stem)
    if read_only and not args.verify:
        scratch = tempfile.TemporaryDirectory(prefix="accord-stage-")
        if stage_dir.is_dir():
            shutil.copytree(stage_dir, scratch.name, dirs_exist_ok=True)
        stage_dir = Path(scratch.name)
    try:
        stage = Stage(args.version, stage_dir=stage_dir, localized=args.localized_dir, stem=args.stem)
        return _main(args, rest, stage)
    finally:
        if scratch is not None:
            scratch.cleanup()


def _main(args: argparse.Namespace, rest: List[str], stage: Stage) -> int:
    if args.segments:
        segments_report(stage)
        return 0
    if args.verify:
        problems = stage.verify()
        for p in problems:
            print(f"[FAIL] {p}")
        print("[OK] accord bundles verify" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0

    if args.accept_minor:
        for lang, entries in sorted(accept_minor(stage, args.accept_minor).items()):
            for e in entries:
                why = "; ".join(e["objections"])
                print(f"[accept-minor] {lang} {e['key']} ({e['candidate']}, MQM {e['score']}): {why}")
        for lang, status in sorted(stage.finalize(write_files=not args.no_reassemble).items()):
            print(f"[accord] {lang}: {status}")
        return 0

    units = units_of(stage)
    wanted = args.units.split()
    unknown = [u for u in wanted if u not in units]
    if unknown:
        raise SystemExit(f"[refuse] unknown unit(s) {unknown}; this accord has {list(units)}")

    tms = {lang: build_tm(stage.localized, args.tm_version, lang, args.tm_stem) for lang in stage.languages}
    if args.seed_exact_tm:
        stage.seed_tm = tms
    if args.extra_tm:
        stage.extra_tm, extra_report = load_extra_tm(args.extra_tm, stage.languages)
        print_extra_report(extra_report)
    stats = stage.build()
    for lang, s in sorted(stats.items()):
        extra = ", ".join(f"{k}={v}" for k, v in s.items() if k not in ("present", "total") and v)
        print(f"[stage] {lang}: {s['present']}/{s['total']}" + (f" ({extra})" if extra else ""))

    L = import_localize(stage.dir)
    install(L, stage, tms)
    Context.candidate_log = args.candidate_log

    passthrough = list(rest)
    if any(flag in passthrough for flag in ("--check", "--glossary-report")):
        if wanted:
            Context.keys = set().union(*(units[u] for u in wanted))
        try:
            return run_localize(L, passthrough)
        finally:
            Context.keys = None

    report: Optional[Path] = None
    if "--report" in passthrough:
        i = passthrough.index("--report")
        report = Path(passthrough[i + 1])
        del passthrough[i : i + 2]

    patterns = [passthrough[i + 1] for i, a in enumerate(passthrough[:-1]) if a == "--keys"]
    rc = 0
    written: List[Tuple[str, Path]] = []
    for unit, keys in units.items():
        if wanted and unit not in wanted:
            continue
        if patterns and not any(fnmatch.fnmatch(k, p) for k in keys for p in patterns):
            continue  # localize.py refuses a selection that matches nothing
        Context.keys = keys
        print(f"\n=== accord {stage.version} :: {unit} ({len(keys)} segment(s)) ===")
        argv_unit = list(passthrough)
        if report is not None:
            part = report.with_name(f"{report.stem}.{unit}{report.suffix}")
            argv_unit += ["--report", str(part)]
            written.append((unit, part))
        rc = max(rc, run_localize(L, argv_unit))
    Context.keys = None
    if report is not None:
        _merge_reports(written, report)

    if "--dry-run" not in passthrough:
        for lang, status in sorted(stage.finalize(write_files=not args.no_reassemble).items()):
            print(f"[accord] {lang}: {status}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
