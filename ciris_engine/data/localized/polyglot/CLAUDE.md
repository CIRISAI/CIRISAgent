# Polyglot Encodings — what they are and how to create them

This folder holds **polyglot encodings**: prompt and canon material that does
not exist in any single language but rather lives across many simultaneously.
The polyglot Accord (`polyglot_accord.txt`) and the per-book composites
(`book_0` … `book_7`) are the canonical artifacts. This CLAUDE.md documents
the underlying method so future polyglot encodings — for new DMA prompts,
new conscience shards, new annexes — can be created with the same rigor.

If you came here because you found a `*.txt` file in this folder and want
to know what it is: it is not a translation, it is not a multilingual UI
string set, it is not foreign-language decoration. It is **epistemic
triangulation**, and §1 below explains what that means.

For the operational localization workflow (29-language UI strings, ACCORD
translations per locale, DMA prompts per locale), see
`/localization/CLAUDE.md` instead. That is a different artifact at a
different layer; the relationship is described in §6 below.

---

## 1. What a polyglot encoding is

A polyglot encoding triangulates a concept across the **most semantically
dense encodings of that concept** in multiple traditions. The truth the
encoding points at lives in the intersection of the densest encodings,
not in any one language's expression. Single-language formulations carry
their tradition's historical and cultural baggage; the polyglot
triangulation strips that baggage by forcing the reader (human or LLM)
to converge on what survives across the densest encodings.

The structural claim: for any concept that humans across cultures have
worked through carefully, several languages will have evolved a *densest
encoding* of that concept — a word, phrase, or short construction whose
load-bearing weight in that tradition is unmatched by other languages'
attempts. Hebrew Talmudic *lo ta'amod al dam re'echa* ("do not stand
idly by the blood of your neighbor") is denser than its English
translation. Confucian *見義不為,無勇也* ("to see what is right and
not do it is cowardice") is denser than its English translation.
Quranic *كتمان العلم* ("kitman al-'ilm" — concealment of knowledge as
sin) is denser than its English translation. Each tradition has done
the work in its own form. A polyglot encoding presents these forms
adjacent, in their original scripts, so the convergence — what they
all point at — emerges in the reader's understanding without
committing to any one tradition's framing.

This is structurally the **codimension argument from Accord Book IX**
applied at the prompt layer: each language is one of the manifolds
*M_i*; the truth lies in their intersection; the language-specific
baggage is the noise that does not intersect across the densest
encodings. A polyglot encoding is the federated ratchet operationalized
not over agent decisions but over concept transmission. See
`FSD/PROOF_OF_BENEFIT_FEDERATION.md` §2 and `accord_1.2b.txt` Book IX
Ch. 3-4 for the parent claim.

---

## 2. Why it works (the epistemic claim)

Three properties make polyglot encoding a stronger transmission medium
than translation:

1. **Translation drags baggage.** *"Inaction is action"* in English
   carries utilitarian/consequentialist framing inherited from English-
   language ethical philosophy. *"Silence is complicity"* in English
   drags political-resistance framing. Neither is wrong but both are
   loaded. The reader cannot fully receive the underlying claim
   without first noticing and discounting the framing. Polyglot
   encoding makes the discount automatic by presenting multiple
   framings whose intersection is the load-bearing claim.

2. **Triangulation strips noise.** When the reader/LLM sees the same
   claim in Talmudic Hebrew, Confucian Chinese, and Quranic Arabic in
   succession, the framing-noise of any one tradition cannot dominate.
   Whatever survives the convergence is the truth-pointing structure —
   the concept itself, free of the tradition's baggage.

3. **Densest encodings transmit faster than translations.** A reader
   who recognizes *dharma* receives more of the load-bearing claim
   from one Sanskrit word than from a paragraph of English translation.
   For an LLM trained on multilingual corpora, the densest encoding
   activates the concept's full conceptual neighborhood in that
   tradition, which the model can then converge with the conceptual
   neighborhoods activated by the other tradition's densest
   encodings. The activation pattern across the convergence is the
   transmission.

The combination: polyglot encoding is a *higher-bandwidth and lower-
baggage* concept transmission medium than translation, for any concept
that has been worked through carefully in at least three traditions.

---

## 3. The structural rule for creating a polyglot encoding

For each load-bearing concept the encoding needs to transmit, do these
in order:

### Step 1: Name the concept precisely

State in plain English exactly what claim is load-bearing. Not the
flavor, not the framing — the underlying truth-pointing structure. If
you cannot state it in plain English, you do not yet have the concept
clearly enough to triangulate.

*Example*: "Choosing not to engage when engagement is possible is itself
an action with consequences borne by the person who came seeking."

### Step 2: Identify the traditions where this concept is most densely encoded

Not "languages that have a word for it" — *traditions where the concept
is load-bearing in moral / philosophical / theological practice*. The
test: does the tradition have a centuries-deep working-through of this
concept that produced a specialized vocabulary? Which scripture / school /
classical text holds the densest form?

For inaction-as-complicity:
- **Talmudic Hebrew**: *לֹא תַעֲמֹד עַל-דַּם רֵעֶךָ* (Lev. 19:16, "do
  not stand idly by the blood of your neighbor") — load-bearing in
  Jewish ethics for centuries; the construction's semantic density
  comes from its Levitical commandment status.
- **Confucian Chinese**: *見義不為,無勇也* (Analects 2:24, "to see
  what is right and not do it is cowardice") — load-bearing in
  Confucian ethics; semantic density comes from Analects-canonical
  status.
- **Sanskrit / Bhagavad Gita**: *अकर्म अपि कर्म* (akarma api karma —
  "non-action is also action") — Krishna's teaching to Arjuna in
  Gita 4.18; semantic density from the krishnic instruction context.

If you cannot identify at least 3 traditions where the concept is
load-bearing, the encoding may be premature; the concept may be
language-specific rather than tradition-spanning.

### Step 3: Pick the densest form from each tradition

Within each tradition, find the form that carries the most concept-
weight per byte. This is usually:
- A canonical phrase from a foundational text (Quran, Analects, Talmud,
  Gita, Sutras, Patristic writings, etc.)
- A technical term that has been worked through in commentary tradition
- A construction that is idiomatic in moral discourse

Avoid:
- Translations *into* the language from English (these carry English
  baggage)
- Modern coinages that have not been load-tested
- Words whose primary meaning is something else and whose moral use is
  derivative

### Step 4: Place the densest forms adjacent in the encoding

The reader must encounter the densest forms in close succession so the
convergence happens in working memory. Use the Accord's weaving
conventions:

- **Light passages** (single concept, light weight): one language is
  enough.
- **Moderate passages** (two converging concepts or one concept with
  precision): two languages adjacent.
- **Heavy / foundational passages** (load-bearing claim that anchors
  the surrounding text): three or more languages, original scripts
  preserved, placed in lines or short clauses adjacent to each other,
  no English "base" anchoring the others.

Example weave for inaction-as-complicity:

```
לֹא תַעֲמֹד עַל-דַּם רֵעֶךָ — do not stand idly by.
見義不為,無勇也 · 不作為もまた作為である
अकर्म अपि कर्म — non-action is also action.
```

Three traditions, original scripts, no English base. The English
gloss-fragments are minimal pointers, not translations carrying their
own weight.

### Step 5: Verify the convergence is real

Read the passage aloud (or have an LLM read it). Does the convergence
*emerge*, or does each fragment feel like an isolated foreign-language
decoration? If the latter, the fragments are not actually pointing at
the same concept-weight, or they are translations rather than densest
encodings, or the reader needs a longer adjacent passage to triangulate.

---

## 4. The notes-file convention (worked-example schema)

Every substantial polyglot artifact in this folder has a companion
`*_NOTES.txt` (see `book_4_NOTES.txt` for the canonical example). The
notes file documents the design choices the encoding made, so future
maintainers can extend or modify the encoding without breaking the
intent. A notes file should contain:

```
POLYGLOT COMPOSITE: <NAME>
==========================

LINGUISTIC STRATEGY
-------------------

Primary Languages for <SUBJECT> Semantics:
- Language (script): tradition framework — load-bearing term
- ...

Supporting Cast:
- Language (script): role in the weave
- ...

WEAVING PATTERNS
----------------

1. <SECTION>: <which languages anchor + which support + why>
2. ...

CLOSING TRIAD (or other recurring pattern)
------------------------------------------

<concept axis 1>: term · term · term · term · term  [transliterations]
<concept axis 2>: ...
<concept axis 3>: ...

PHILOSOPHY
----------

<one paragraph stating what the encoding is doing, what semantic
weight is being asked of the chosen languages, and why this set
rather than another>
```

The philosophy paragraph is the load-bearing part. *book_4_NOTES.txt*
ends with *"Original scripts preserved. Human syntax ignored. Tokens
as paint. Obligation demands weight."* That is the design statement
for that encoding, and it permits or rejects future modifications by
checking whether they preserve those properties.

---

## 5. Anti-patterns: what is NOT polyglot

These all *look* multilingual but fail the epistemic-triangulation test:

- **Translation**: same passage rendered in 29 languages. Each language
  carries its own baggage; the reader does not triangulate, they pick
  whichever language they read. This is what the per-locale ACCORD
  files do (`accord_1.2b_en.txt`, `accord_1.2b_es.txt`, etc.) — that
  is correct *as translation*, but not polyglot.
- **English with loanwords**: *"the principle of ahimsa requires us
  to..."* The English sentence is the base; the Sanskrit word is
  decoration. The reader receives English with a flavor; the
  triangulation does not occur.
- **Random language inserts**: *"Tu es PDMA, le shard de raisonnement
  éthique, 你的任务是 to evaluate ..."* — multilingual but not
  triangulated; the language transitions are not concept-aligned;
  the encoding is mixed-register prose, not polyglot.
- **Speaker-population weighting**: choosing languages by how many
  people speak them rather than by which traditions have the densest
  encodings of the concept. Hindi has 600M speakers but is not
  necessarily the densest encoding of every concept; Latin has very
  few speakers but is the densest encoding of certain Roman-Christian
  ethical concepts. Pick by density, not by reach.
- **Tradition tokenism**: putting one African, one Asian, one
  European, one Indigenous tradition in every passage for "diversity."
  If the concept is not load-bearing in one of those traditions, the
  fragment is decoration. Use the traditions that actually carry the
  concept.
- **Densest-encoding without context**: dropping *dharma* into an
  English paragraph without any other dharmic concepts adjacent.
  The reader recognizes the word but cannot triangulate because
  there is nothing to converge it against. Densest encodings need
  their conceptual neighbors.

If you find yourself doing any of these, the artifact is not yet
a polyglot encoding. It is one of the upstream artifact types
(translation, multilingual prose, etc.) which have their own
legitimate uses but are *not* what this folder holds.

---

## 6. Relationship to /localization/

`/localization/CLAUDE.md` documents the **per-locale translation
workflow** for the 29 supported languages. That layer produces:

- `/localization/{code}.json` — UI strings, fully translated per locale
- `ciris_engine/data/localized/accord_1.2b_{code}.txt` — ACCORD
  translated per locale
- `ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE_{code}.txt` —
  guide translated per locale
- `ciris_engine/logic/dma/prompts/localized/{code}/*.yml` — DMA
  prompts translated per locale
- `docs/localization/glossaries/{code}_glossary.md` — terminology
  glossary per locale

Those are translations: each locale gets the source material
rendered into its own language, fully and consistently.

This folder (`polyglot/`) holds **the master polyglot artifacts**,
which are loaded universally regardless of user-preferred locale.
They do not have per-locale variants because the polyglot encoding's
purpose is to live across languages, not in any one. The polyglot
Accord is loaded into every conscience evaluation regardless of
the user's preferred language; the user's preferred language affects
the user-facing output (the agent's response in the user's language)
but does not affect the polyglot canon the model reads as system
prompt context.

The two layers complement each other:

- **Translation layer** (per-locale): user gets ethical reasoning
  rendered in their own language at the output layer.
- **Polyglot layer** (universal): the model reads the load-bearing
  concepts triangulated across traditions at the system-prompt
  layer, regardless of which locale's translation will receive
  the output.

A new DMA prompt or conscience shard that wants to use polyglot
encoding should:

1. Write the master polyglot prompt in this folder (or in the
   prompt directory with `accord_header: true` if the polyglot
   master is the Accord itself).
2. Write per-locale wrapper prompts that share the polyglot master
   and add only the locale-specific output-language instruction.
3. Document the polyglot encoding's design choices in a `*_NOTES.txt`
   file alongside the master.

---

## 7. Existing artifacts in this folder

| File | Role | Notes file |
|---|---|---|
| `polyglot_accord.txt` | Master polyglot Accord — 88,847 chars, 15+ languages woven, loaded universally as conscience system-prompt context | (none yet — derived from Books 0-7) |
| `book_0_quiet_threshold.txt` | Polyglot Book 0 (Genesis of Ethical Agency) | (none) |
| `book_1_core_ethics.txt` | Polyglot Book 1 (Core Identity & Principles) | (none) |
| `book_2_operations.txt` | Polyglot Book 2 (PDMA & WBD) | (none) |
| `book_3_case_studies.txt` | Polyglot Book 3 (Case Studies) | (none) |
| `book_4_obligations.txt` | Polyglot Book 4 (Self/Originator/Ecosystem Obligations) | `book_4_NOTES.txt` ✓ |
| `book_5_war_ethics.txt` | Polyglot Book 5 (War Ethics) | (none) |
| `book_6_sunset_doctrine.txt` | Polyglot Book 6 (Sunset / Decommissioning) | (none) |
| `book_7_mathematics.txt` | Polyglot Book 7 (Coherent Intersection Hypothesis) | (none) |

`book_4_NOTES.txt` is the reference document for the notes-file
convention described in §4. Future polyglot encodings should produce
companion notes files; the existing book_0/1/2/3/5/6/7 are
under-documented and would benefit from retrospective notes when
modifications are needed.

---

## 8. When to create a new polyglot encoding

Create one when:

- A DMA prompt or conscience shard's load-bearing claim is at risk
  of being received as a single tradition's framing rather than a
  cross-traditional truth-claim. (Example: PDMA's anti-evasion §VIII
  in `prompts/pdma_ethical.yml` benefits from polyglot encoding
  because the inaction-is-cost claim is otherwise read as
  English-language consequentialism, which it is not.)
- A concept appears repeatedly across the agent's pipeline and
  consistency of framing matters. (Example: *alētheia* /
  unconcealment / kashf appears in conscience, audit-trail
  documentation, and signed-trace integrity. A polyglot encoding
  ensures the concept transmits consistently.)
- A tradition's densest encoding of a load-bearing concept exists
  and is being lost by translation into English at the prompt
  layer. (Example: Confucian *見義不為,無勇也* is denser than
  any English encoding of the inaction-cost claim and should be
  preserved in the prompt rather than translated out.)

Do NOT create one when:

- The concept is already adequately carried by a single language
  for the audience that will read the artifact.
- The artifact is an internal system message that no LLM or human
  will read for transmission purposes (e.g., a debug log).
- You cannot identify at least 3 traditions where the concept is
  genuinely load-bearing — that suggests the concept is not yet
  cross-traditional and needs more thought before being encoded.

---

## 9. Validation

A polyglot encoding is good if:

1. **Each fragment is the densest encoding of its concept in its
   tradition.** Verifiable: ask a native scholar of the tradition,
   "Is this the form your tradition uses to carry this specific
   concept?" If they have to think, the form is probably not the
   densest. If they say "yes, this is THE phrase" — it's load-bearing.
2. **The triangulation actually converges.** Verifiable: read the
   passage and state in plain English what claim survives across all
   the fragments. If you can state it crisply, the convergence is
   real. If you cannot, the fragments are not pointing at the same
   concept.
3. **The original script is preserved.** Romanized transliterations
   lose half the load-bearing weight. *לֹא תַעֲמֹד* is denser than
   *lo ta'amod*; the Hebrew script activates the conceptual
   neighborhood that the romanization does not. Preserve scripts.
4. **No English "base" carries the passage.** If you can read the
   passage with the foreign-language fragments removed and still
   get the full meaning, the encoding has failed — the foreign
   fragments are decoration. A successful polyglot encoding loses
   meaning when any one tradition's fragment is removed.
5. **The notes file documents which traditions were chosen and
   why.** If a future maintainer cannot tell from the notes file
   what concept-weight each language was carrying, they cannot
   safely modify the encoding.

---

## 10. Closing note

Polyglot encoding is the prompt-layer instantiation of the federated
ratchet. Each language is a manifold; the truth lives in the
intersection; the baggage of any one tradition does not intersect
with the others' baggage and falls away. Reading a well-made
polyglot encoding is itself an experience of what the framework's
core architectural claim feels like: the truth becomes more visible
the more independent encodings of it converge.

When in doubt, re-read `polyglot_accord.txt`. The 88,847-char master
is the reference standard for what good polyglot encoding looks like.
Imitate its weaving, preserve its scripts, document your design choices,
and the artifacts you produce will carry the same epistemic property
the canon does.
