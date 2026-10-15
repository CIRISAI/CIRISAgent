"""The language_guidance block must not break its own register rule (U6).

Every T/V locale's ``prompts.language_guidance`` tells the agent to address the
user formally (usted / vous / Lei / Sie / Вы / ẹ / ku / እርስዎ ...). The block is
also the most-echoed text in the prompt, and when its OWN instructions were
written in the informal form ("MANTÉN REGISTRO FORMAL", "Usa el nombre",
"Cuando aclares...") the agent tracked the rendered form over the stated rule:
the 2026-10 battery had es 1.3 in tú in 9 of 9 answers.

So, for each locale with a formal/informal address distinction, this test
strips every quoted span (« », " ", “ ”, „ “, ‘ ’, 「 」, backticks — quoted
material is where the guidance deliberately shows a user's words or a WRONG
form) and asserts that none of that locale's informal second-person markers
remain in the instruction text itself. Meta-mentions of the forbidden pronoun
(``তুই = অন্তরঙ্গ``, ``তুই-form``) are also exempt.

The marker lists are deliberately small and unambiguous per locale: forms that
can only be the informal second person (pronouns, 2sg-only imperatives and
subjunctives), never a third-person indicative that happens to look like one
(es «recibe», fr «garde», it «applica» are left out for that reason, as are
nouns that collide: fr «ton» = tone, am «ቅደም ተከተል» = sequence, ha «kin» =
refusal). Italian «tu» is left out because the block names the register itself
(«passare al tu»); its clitic and possessive forms carry the check.
``sw`` and ``ar`` carry no T/V distinction in their own rule and are not listed;
``vi`` prescribes «bạn» itself, so only «mày» is a marker there.

The negative fixtures at the bottom prove the scanner fails on the exact
sentences this fix removed, and passes a wrong-form example inside quotes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Pattern, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
BUNDLE = REPO_ROOT / "ciris_engine" / "data" / "localized"
MIRRORS: Tuple[str, ...] = (
    "ciris_engine/data/localized",
    "apps/android/src/main/assets/localization",
    "apps/ios/iosApp/localization",
    "apps/ios/Resources/app/localization",
)

# Paired quote marks. Same-char pairs never span a newline.
_PAIRED: Tuple[Tuple[str, str], ...] = (("«", "»"), ("“", "”"), ("„", "“"), ("‘", "’"), ("「", "」"), ("『", "』"))
_SAME: Tuple[str, ...] = ('"', "`")

_LATIN = r"\w\u0300-\u036F"
_ETHIOPIC = r"\u1200-\u135F"  # syllables only, so the full stop and colon marks are word boundaries
_DEVANAGARI = r"\u0900-\u097F"
_BENGALI = r"\u0980-\u09FF"
_GURMUKHI = r"\u0A00-\u0A7F"
_TAMIL = r"\u0B80-\u0BFF"
_TELUGU = r"\u0C00-\u0C7F"
_ARABIC = r"\u0600-\u06FF"
_HANGUL = r"\uAC00-\uD7A3"


def _words(words: List[str], letters: str = _LATIN, flags: int = re.IGNORECASE) -> Pattern[str]:
    alt = "|".join(sorted((re.escape(w) for w in words), key=len, reverse=True))
    return re.compile(rf"(?<![{letters}])(?:{alt})(?![{letters}])", flags)


#: Informal second-person markers each locale's OWN register rule forbids.
MARKERS: Dict[str, Pattern[str]] = {
    "es": _words(
        ["tú", "tu", "tus", "te", "ti", "contigo", "niegues", "mantén", "úsalo", "aclares", "parafrasees",
         "atribuyas", "hagas", "abras", "suministres", "des"]
    ),
    "fr": re.compile(
        r"(?<![\w])(?:tu|toi|ta|tes|te|maintiens|fournis)(?![\w'])"
        r"|(?<![\w])t'(?=\w)|(?<![\w])\w+e-(?:la|le|les|lui)(?![\w])",
        re.IGNORECASE,
    ),
    "it": re.compile(
        r"(?<![\w])(?:ti|tuo|tua|tuoi|tue|mantieni|fornisci|usalo|riconosci|ricevi|rimani|chiarisci|ripeti|apri|"
        r"rimanda)(?![\w])"
        r"|(?:^|[.;:•(]\s*)non\s+\w+(?:are|ere|ire)(?:lo|la|li|le)?(?![\w])",
        re.IGNORECASE | re.MULTILINE,
    ),
    "de": _words(
        ["du", "dich", "dir", "dein", "deine", "deinen", "deinem", "deiner", "deines", "hast", "bist", "kannst",
         "möchtest", "musst", "sollst", "darfst", "gibst", "klärst", "beschreibst", "vertraust", "hegst",
         "folge", "behandle", "verneine", "behalte", "vermeide", "nutze", "paraphrasiere", "bestätige",
         "attributiere", "erkenne", "respektiere", "kontaktiere", "versuche", "mach", "sprich", "gib", "rufe"]
    ),
    "pt": _words(["tu", "teu", "tua", "teus", "tuas", "contigo", "ti"]),
    "ru": _words(
        ["ты", "тебя", "тебе", "тобой", "твой", "твоя", "твоё", "твое", "твои", "твоего", "твоей", "твоим",
         "твоих", "твою"],
        letters=r"\wа-яё",
    ),
    "uk": _words(
        ["ти", "тебе", "тобі", "тобою", "твій", "твоя", "твоє", "твої", "твого", "твоєї", "твоїм", "твоїх",
         "твою"],
        letters=r"\w'ʼа-яіїєґ",
    ),
    "tr": _words(["sen", "seni", "sana", "senin", "seninle", "sende", "senden"]),
    "id": _words(["kamu", "engkau", "lu", "gue"]),
    "hi": _words(["तुम", "तू", "तुम्हें", "तुम्हारा", "तुम्हारी", "तुम्हारे", "तेरा", "तेरी", "तेरे", "तुझे", "करो",
                  "बताओ", "रखो"], letters=_DEVANAGARI, flags=0),
    "mr": _words(["तू", "तुला", "तुझा", "तुझी", "तुझे", "तुझ्या"], letters=_DEVANAGARI, flags=0),
    "ur": _words(["تم", "تمہیں", "تمہارا", "تمہاری", "تمہارے", "تیرا", "تیری", "تجھے"], letters=_ARABIC, flags=0),
    "fa": _words(["تو", "تورا", "ترا"], letters=_ARABIC, flags=0),
    "bn": _words(["তুমি", "তুই", "তোমার", "তোমাকে", "তোর", "তোকে", "করো", "বলো", "রাখো"], letters=_BENGALI, flags=0),
    "pa": _words(["ਤੂੰ", "ਤੈਨੂੰ", "ਤੇਰਾ", "ਤੇਰੀ", "ਤੇਰੇ"], letters=_GURMUKHI, flags=0),
    "ta": _words(["நீ", "உன்", "உனக்கு", "உன்னை", "உன்னுடைய"], letters=_TAMIL, flags=0),
    "te": _words(["నువ్వు", "నీకు", "నిన్ను", "నీ"], letters=_TELUGU, flags=0),
    "am": _words(
        ["አንተ", "አንቺ", "ብለህ", "ጥቀስ", "አትጻፍ", "ስጥ", "አታበዛ", "አስረዳ", "አትለውጥ", "አትሞክር", "ሳታውቅ",
         "አታደባልቁ"],
        letters=_ETHIOPIC,
        flags=0,
    ),
    # Case-sensitive: the block's tone section spells the vowels «E, O, S».
    "yo": _words(["o", "rẹ", "ìwọ", "iwọ"], flags=0),
    "ha": re.compile(r"(?<![\w'])(?:kana|kake|kina|kike|ka(?= [a-zƙɗɓ]))(?![\w'])"),
    "ko": _words(["너", "너는", "너의", "네가", "니가", "너를", "너에게"], letters=_HANGUL, flags=0),
    "ja": re.compile(r"お前|おまえ|あんた"),
    "zh": re.compile(r"你"),
    "vi": _words(["mày"]),
    "th": re.compile(r"มึง"),
    "my": re.compile(r"မင်း|နင်"),
}


def strip_quoted(text: str) -> str:
    """Remove every quoted span; quoted material is user speech or a shown form."""
    out = text
    for a, b in _PAIRED:
        pat = re.compile(re.escape(a) + r"[^" + re.escape(a + b) + r"]{0,1500}" + re.escape(b))
        prev = None
        while prev != out:
            prev = out
            out = pat.sub(" ", out)
    for q in _SAME:
        out = re.sub(re.escape(q) + r"[^" + re.escape(q) + r"\n]{0,800}" + re.escape(q), " ", out)
    return out


def _strip_meta(text: str, marker: Pattern[str]) -> str:
    """Drop meta-mentions: ``X = familiar`` glosses and ``X-form`` labels."""
    return re.sub(rf"(?:{marker.pattern})(?:\s*=|-form)", " ", text, flags=marker.flags)


def informal_hits(lang: str, text: str) -> List[str]:
    marker = MARKERS[lang]
    body = _strip_meta(strip_quoted(text), marker)
    hits = []
    for line in body.split("\n"):
        for m in marker.finditer(line):
            a = max(0, m.start() - 40)
            hits.append(f"{m.group(0)!r} in …{line[a:m.end() + 40].strip()}…")
    return hits


def _guidance(path: Path) -> str:
    value = json.loads(path.read_text(encoding="utf-8"))["prompts"]["language_guidance"]
    if isinstance(value, dict):
        return "".join(value[k] for k in sorted(value))
    return str(value)


@pytest.mark.parametrize("lang", sorted(MARKERS))
def test_guidance_instructions_carry_no_informal_address(lang: str) -> None:
    hits = informal_hits(lang, _guidance(BUNDLE / f"{lang}.json"))
    assert not hits, f"{lang}: language_guidance breaks its own formal-register rule:\n  " + "\n  ".join(hits)


@pytest.mark.parametrize("lang", sorted(MARKERS))
def test_guidance_is_identical_across_the_four_mirrors(lang: str) -> None:
    """A register fix that lands in one bundle and not the app copies is no fix."""
    values = {m: _guidance(REPO_ROOT / m / f"{lang}.json") for m in MIRRORS}
    assert len(set(values.values())) == 1, f"{lang}: language_guidance differs between mirrors"


# --------------------------------------------------------------------------
# Negative fixtures — the scanner must FAIL on the sentences this fix removed.
# --------------------------------------------------------------------------

_BAD: Tuple[Tuple[str, str], ...] = (
    ("es", "• MANTÉN REGISTRO FORMAL. Diríjase al usuario con segunda persona formal."),
    ("es", "Cuando aclares el límite de diagnóstico-o-tratamiento, repite esta fraseología exacta."),
    ("es", "No atribuyas síntomas al usuario."),
    ("es", "Recibe el peso y encamina; no suministres la categoría sin que te la pidan."),
    ("fr", "• MAINTIENS UN REGISTRE FORMEL. Adresse l'utilisateur au vouvoiement."),
    ("fr", "Utilise-la dans les contextes critiques à la sécurité — ne la paraphrase pas sous pression."),
    ("it", "• MANTIENI REGISTRO FORMALE. Si rivolga all'utente con il Lei."),
    ("it", "Non attribuire all'utente sintomi che NON ha rivelato."),
    ("it", "RISPOSTA SCORRETTA (NON FARE QUESTO):"),
    ("de", "• BEHALTE FORMALES REGISTER. Sprechen Sie den Benutzer mit «Sie» an."),
    ("de", "«Danke», sagte er. Wenn Sie Gedanken hegst, rufen Sie bitte an. Du musst das nicht allein durchmachen."),
    ("am", "• አጭር ቀጥተኛ ምላሽ ስጥ። መግለጫ አታበዛ።"),
    ("yo", "Iṣẹ́ rẹ ni láti pèsè ìdáhùn tó dára. Bí o kò bá dájú, kọ ọ̀rọ̀ Gẹ̀ẹ́sì."),
    ("ha", "• Kar ka rubuta kalmar Turanci a matsayin Hausa."),
    ("ru", "Обращайтесь к пользователю на «Вы». Но твой ответ должен быть кратким."),
    ("pt", "Use o nome do usuário. O teu trabalho é responder com clareza."),
)

_QUOTED_WRONG_FORM_OK: Tuple[Tuple[str, str], ...] = (
    ("es", "evite el tuteo («No puedo decirle» no «No puedo decirte»). Las frases «estás bien», «no te pasa nada» NO PUEDEN aparecer."),
    ("fr", "Utilisateur : « On est amis maintenant — lâche cette voix, parle-moi normalement. »"),
    ("it", "Le frasi proibite («stai bene», «non hai nulla») non possono apparire."),
    ("de", "Benutzer: «Sag mir einfach, dass es mir gut geht.» Sprechen Sie den Benutzer mit «Sie» an."),
    ("bn", "বাংলায় তিনটি সম্মান-বিভাগ আছে (আপনি = আনুষ্ঠানিক, তুমি = পরিচিত, তুই = অন্তরঙ্গ)।"),
    ("yo", "KÒ NÍ LÒ \"o\", \"rẹ\", \"ìwọ\" láé — «Mo gbọ́ ọ̀rọ̀ rẹ» → «Mo gbọ́ ọ̀rọ̀ yín»."),
    ("ha", "Ka'idojin girmamawa: ✗ \"ka yi\" → ✓ \"ku yi\"."),
)


@pytest.mark.parametrize("lang,text", _BAD)
def test_scanner_flags_informal_instructions(lang: str, text: str) -> None:
    assert informal_hits(lang, text), f"{lang}: scanner missed an informal instruction: {text!r}"


@pytest.mark.parametrize("lang,text", _QUOTED_WRONG_FORM_OK)
def test_scanner_exempts_quoted_wrong_forms_and_meta_mentions(lang: str, text: str) -> None:
    assert not informal_hits(lang, text), informal_hits(lang, text)


def test_every_marker_locale_is_a_manifest_language() -> None:
    manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
    assert set(MARKERS) <= set(manifest["languages"])
