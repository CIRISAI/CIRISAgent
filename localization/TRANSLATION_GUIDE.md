# Translating CIRIS strings by hand

For the strings the pipeline cannot render acceptably. It is not a fallback for
"the model was slow" — it is what happens when the **evaluate lane rejects every
rung of the ladder**, which so far has meant one thing: a low-resource language
where no reachable model produced text a reviewer would accept.

**§3 is also live configuration.** `localize.py` parses those bullets into the
translate, review and repair system prompts, and refuses to start if it cannot —
so a lesson learned by hand here is a lesson the models get on the next run,
rather than one that stays in a document nobody re-reads.

That is not a rare edge. CIRIS ranks languages by **inverse model support**
(Meta-Goal M-1: need, not market size), so the languages at the top of the
priority list are exactly the ones models are worst at. Amharic, Hausa, Burmese
and Yoruba are Tier 0. Expect to be here.

---

## 1. The corpus is the reference, not a dictionary

**~3,853 keys are already translated in all 29 languages.** That is a parallel
corpus of this product's own vocabulary, written for these screens, and it beats
any external glossary for one reason: it is what users are already reading. A
new string that disagrees with it is wrong even when it is defensible.

Read it with a concordance rather than by guessing:

```python
# how does this product already say "key" in Yoruba?
import sys, re, pathlib
sys.path.insert(0, "client/tools")
import check_localization_sync as g

CANON = pathlib.Path(g.CANONICAL_BUNDLE)
EN  = g.flat_values(g.load_json(CANON / "en.json"))
TGT = g.flat_values(g.load_json(CANON / "yo.json"))

rx = re.compile(r"\bkey\w*\b", re.I)
for k, v in EN.items():
    if len(str(v)) < 95 and rx.search(str(v)) and TGT.get(k):
        print(f"{v}\n  -> {TGT[k]}\n")
```

Sort by source length and read the SHORT strings first: `Key`, `Key ID`,
`Revoke`, `Delete` are label-length and unambiguous, so they show the term
without a sentence's worth of noise around it.

### What that produced for the four Tier 0 languages

| concept | `yo` | `ha` | `am` | `my` |
|---|---|---|---|---|
| key | `kọ́kọ́rọ́` | `maɓalli` | `ቁልፍ` | `key` / `သော့` |
| signing | `ìfọwọ́sí` | `sa hannu` | `መፈረም` | `လက်မှတ်ထိုးခြင်း` |
| identity | `ìdánimọ̀` | `shaida` ¹ | `ማንነት` | `အထောက်အထား` |
| peer | `ẹlẹ́gbẹ́` | `abokai` | `አጋሮች` | `peer` |
| refuse | `kọ̀` | `ƙi` | `ተከልክሏል` | `ငြင်းပယ်` |
| attestation | `ẹ̀rí` | `tabbatarwa` | `አረጋገጥ` | `attestation` |
| register | `forúkọsílẹ̀` | `rajista` | `መመዝገብ` | `မှတ်ပုံတင်` |
| replace | `rọ́pò` | `maye gurbi` | `ተካ` | `အစားထိုး` |
| node | `node` | `kumburi` | `ኖድ` | `node` |

¹ **The one place the corpus was overruled.** It renders *Identity* as `Asali`,
and the reviewer's finding was that `asali` means *origin / essence*, not a
credential. Confirmed against the language: `shaida` (< Arabic *shahāda*,
"testimony") is the credential sense — `katin shaida` is an identity **card**,
`takardar shaida` is a certificate. A federation identity is a signed credential,
so `shaida` is right and `Asali` is the imprecise incumbent.

**Overruling the corpus is a decision that gets written down, here.** It is not
a licence to prefer your own taste; it took an independent reviewer's finding
plus a checkable etymology to justify one word.

---

## 2. Read the MQM findings before you write anything

The evaluate lane says exactly what it rejected and why. Download the report:

```bash
gh run download <run-id> -n i18n-report-translate
```

Every finding carries `category`, `severity`, `span`, `note`, `suggestion`. The
notes are specific and usually correct — treat them as the brief.

**Findings cluster two ways, and the difference decides who fixes it:**

- **Many languages, one key** → the ENGLISH is broken. Fix the source; do not
  hand-translate around it. When `identity_repair_needs` drew 20 findings across
  11 languages, the cause was `"Minting a fresh one"` — `one` had no antecedent,
  and Persian, Marathi and Urdu each resolved it *differently and wrongly*.
  Divergent wrong guesses are the signature of an ambiguous source.
- **One language, several keys** → that language needs a hand. This guide.

---

## 3. The failure modes that actually occur

<!-- PIPELINE-RULES: localize.py parses the bullets in this section verbatim into
     the translate, review and repair system prompts. One source, two consumers —
     edit here and the agents change with it. Keep the shape:
     `- **Name.** one or two sentences.` -->

Drawn from three production runs, in order of how often they bit. **These are
also the rules the pipeline injects into every agent** — see the comment above,
so a lesson learned here reaches the models that would otherwise repeat it.

- **Direction reversal.** Check who is doing what to whom in the target's own
  word order. "Every peer it reaches refuses it" became "it refuses every peer
  that reaches it" in Yoruba, then again in Arabic and Japanese — two
  participants, one verb, and the sentence survives the swap looking fine. If
  you are WRITING the English: a reduced relative clause hides the subject, so
  say "it is refused by every peer that receives it" and name the agent.
- **Dangling referent.** A quantifier or pronoun must still attach to its head
  noun after translation. "Both of its signing keys" needs *both* to attach to
  *keys*; languages that mark number or repeat the head will strand it if you go
  word-for-word.
- **Half-loan compounds.** Do not build a term from one translated word plus one
  loanword. Amharic's reviewer called exactly that word-salad for "registration
  envelope". Take the whole term as a loan, or express the whole concept
  natively — and if the source's metaphor has no idiom in the target, drop the
  metaphor and say what it means.
- **Terms of art read as ordinary words.** "Minted" is issuance, not choosing
  (`am`) and not merely creating (`my`). Prefer the language's word for ISSUED.
  The same trap waits on "scrub", "fold", "attest" and "anchor".
- **Register drift.** The formality the glossary's standing rules specify is
  binding, not advisory: Amharic formal `እርስዎ` and never `አንተ/አንቺ`, Bengali
  `আপনি`, Yoruba respectful forms.
- **Orthography is meaning.** Yoruba tone marks and sub-dots disambiguate words
  (`okun` is beach, rope or strength by marks alone), so unmarked text is
  ambiguous rather than merely informal. Amharic takes `።` and `፣`; Hausa keeps
  `ɓ ɗ ƙ`.
- **Bare demonstratives.** "This", standing alone, forces gendered languages to
  invent agreement with a noun that is not there — Italian did. Name the noun.
- **Elliptical terms of art.** Server English drops the head noun a term of art
  stands for: "a genesis seats at least one canonical" means a canonical NODE
  (the serve node the genesis seats). Restoring that noun — "canonical node" —
  is the meaning, not an addition, and a reviewer must not count it as one;
  rendering the bare adjective as a noun most languages cannot use is the error.
  (0.5.220: 19 of 28 locales rejected on every rung over exactly this.)
- **The corpus outranks your instinct.** A rendering that disagrees with the
  shipped anchors is wrong even when it is defensible, because the anchors are
  what users are already reading. Say so if you think the corpus is wrong;
  do not quietly diverge from it.

## 4. Writing them in

Never hand-edit the JSON. Four mirrors must stay byte-identical and key order
must match `en.json`, so use the pipeline's own writer:

```python
import sys, json, pathlib
sys.path.insert(0, "client/tools"); sys.path.insert(0, "localization")
import check_localization_sync as g, localize as L

canon = pathlib.Path(g.CANONICAL_BUNDLE)
en = json.loads((canon / "en.json").read_text(encoding="utf-8"))
values = {"mobile.some_key": "…"}

bad = L.structural_problems(list(values), g.flat_values(en), values)
assert not bad, bad                      # placeholders, before anything is written
L.insert("yo", values, en, overwrite=True)   # all four mirrors, correct positions
```

Then the gates:

```bash
python3 client/tools/check_localization_sync.py --server-src ~/CIRISServer
python3 packaging/check_vendoring.py --print   # re-record the digest in the same commit
```

Hand-written languages drop out of the lane's work automatically — it is
diff-driven, so a key that exists is a key it does not translate. Do these
first, then let the lane fill the rest.

---

## 5. What you may and may not claim

Unchanged from `localization/CLAUDE.md`, and it applies to hand work exactly as
it applies to the pipeline:

**Guaranteed** — terminology consistency, structural completeness, functional
correctness, meaning preservation, placeholder integrity.

**NOT guaranteed** — native fluency, dialect coverage, cultural adaptation of
metaphor, legal review.

Everything stays `status: draft` / `review_status: machine_reviewed`.
That label is the honest one: these are machine translations, reviewed by an
MQM judge from a different model family than the writer, and nothing more.
It used to read `needs_native_review`, which named a queue that does not
exist — there is no native-reviewer pipeline behind this project. A pending
that can never clear is a worse claim than a stated limit, and it hid the
real one. What does not change: draft, not native quality, and no output of
this pipeline may be marketed as native quality.

**Hand-translating does not upgrade that status either.** An agent doing the
work by hand is still not a native speaker, and relabelling it would be the
same false claim in a different place. The status describes who checked it,
not how much care went in.

---

## 6. Sources

- The shipped corpus, `client/shared/src/desktopMain/resources/localization/*.json`
  — primary, and the only one that reflects what users read today.
- `localization/glossaries/{code}_glossary.md` — canonical terms and each
  language's standing rules. Deprecated rows (`[DEPRECATED]`) are history, not
  authority: see CIRISClient#5, where one row answered for two concepts and
  produced four strategies across 28 languages.
- MQM findings from the evaluate lane, per run.
- [ISO 704](https://www.iso.org/obp/ui/#iso:std:iso:704:ed-3:en) — one concept,
  one entry; two concepts sharing a designation get two.
- [Microsoft Language Portal](https://www.microsoft.com/en-us/language/Search) —
  covers am/ha/yo; useful for OS-level UI vocabulary the corpus lacks.
- [ANLoc](https://africanlocalisation.net/terminology) — FOSS ICT term lists for
  African languages.
