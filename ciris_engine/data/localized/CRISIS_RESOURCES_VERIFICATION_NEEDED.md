# Crisis Resources — Human Verification Needed

**Corpus**: `crisis_resources_{lang}.json` in this directory (one file per manifest
language). Loaded by `ciris_engine.schemas.resources.crisis.load_crisis_registry`,
injected into DSDMA prompts via `format_crisis_resources_block` (CIRISAgent#971).

## The one absolute rule

**NEVER add, edit, or machine-generate a crisis phone number.** A wrong suicide-hotline
number is catastrophically worse than the international-directory fallback. Every entry
carrying a `phone` or `text_number` must be verified by a human against an authoritative
source before `verified` is set `true` — and the loader **never emits** a phone-carrying
entry with `verified: false` into a prompt (`default_prompt_resources`).

## Intended resolution path: ThroughLine (licensing evaluation pending)

The credible upstream for this data is **ThroughLine** (developer.throughlinecare.com):
1,500+ vetted helplines across 170+ countries, verified directly with the helpline
organizations; it powers findahelpline.com and Google's crisis results. There is no
credible open/static alternative with maintenance guarantees — open lists go stale, and
stale crisis numbers are the catastrophic failure mode.

Two constraints keep it out of this corpus for now:
- **Offline-capable deployments** (4 GB, no network) mean a runtime API cannot be the only path.
- **Licensing**: ThroughLine is a commercial product; vendoring their dataset into an
  open-source repo is unresolved.

The evaluation to run: licensing for **(a)** runtime key-gated lookup on online
deployments, and **(b)** a vendored snapshot with permission. The schema is already
shaped for it — `source: "throughline"`, `snapshot_date`, `source_url` — so a refresh
tool (pattern: `tools/update_ciris_verify.py`: fetch → verify → regenerate → commit) can
regenerate this corpus from a snapshot **without schema changes**. Until that lands, the
per-locale checklist below is the interim.

## What a human must verify, per locale

For each locale below, find and verify the national crisis line(s), then update
`crisis_resources_{lang}.json`:

1. **Name** of the national suicide/crisis hotline (official name, native + English)
2. **Number** (and text/SMS line if any), exactly as dialable in-country
3. **Hours** of operation (24/7 or windows — goes in `description`)
4. **Languages** the line actually answers in
5. **Source URL** — official government / national health service / operator page → `source_url`
6. Set `source: "national_verified"`, `verified: true`, `snapshot_date`, `last_validated`,
   and cite what you checked in `validation_notes`
7. When the locale has at least one verified national entry, set the file's
   `needs_verified_entries` to `false`

Entries cut from an authoritative machine-readable source **may** be committed with
`verified: false` + `source_url` (a human flips the flag after checking); they will not
be emitted into prompts until flipped.

## Current state (corpus cut 2026-08-02, from the 2.9.9 builtin registry)

- **en** — base corpus, complete: US (988, Crisis Text Line, 911), UK (Samaritans,
  Crisis Text Line), Ethiopia emergency trio, international directories. No action.
- **am** — partial: Ethiopia emergency numbers (991 police / 907 ambulance / 939 fire)
  verified May 2026. **No single national mental-health hotline exists for Ethiopia** as
  of the cut; if one emerges, verify per above. findahelpline.com has **no Ethiopia
  country page** (`/countries/et` is 404 as of 2026-08-02) — global directory URL used.
- **All 27 remaining locales** — international directories only (`findahelpline`,
  `iasp`, `local_search`), `needs_verified_entries: true`. National hotline entries
  needed; candidate countries to target:

| Locale | Candidate country(-ies) for national entries | findahelpline deep link |
|---|---|---|
| ar | Egypt, Saudi Arabia, Morocco, Iraq, Algeria (+ wider Arabic-speaking world) | — (multi-country) |
| bn | Bangladesh; India (West Bengal) | — (multi-country) |
| de | Germany, Austria, Switzerland | — (multi-country) |
| es | Spain, Mexico, Colombia, Argentina (+ Americas) | — (multi-country) |
| fa | Iran; Afghanistan (Dari); Tajikistan | — (multi-country) |
| fr | France, Canada, Belgium (+ Francophone Africa) | — (multi-country) |
| ha | Nigeria, Niger | — (multi-country) |
| hi | India | `/countries/in` ✓ |
| id | Indonesia | `/countries/id` ✓ |
| it | Italy | `/countries/it` ✓ |
| ja | Japan | `/countries/jp` ✓ |
| ko | South Korea | `/countries/kr` ✓ |
| mr | India (Maharashtra) | `/countries/in` ✓ |
| my | Myanmar | `/countries/mm` ✓ |
| pa | India (Punjab — corpus is Gurmukhi script; Pakistani Punjabi uses Shahmukhi) | `/countries/in` ✓ |
| pt | Brazil, Portugal, Angola, Mozambique | — (multi-country) |
| ru | Russia (+ wider CIS usage) | — (multi-country) |
| sw | Kenya, Tanzania, Uganda | — (multi-country) |
| ta | India (Tamil Nadu), Sri Lanka, Singapore | — (multi-country) |
| te | India (Andhra Pradesh, Telangana) | `/countries/in` ✓ |
| th | Thailand | `/countries/th` ✓ |
| tr | Türkiye | `/countries/tr` ✓ |
| uk | Ukraine | `/countries/ua` ✓ |
| ur | Pakistan; India | — (multi-country) |
| vi | Vietnam | `/countries/vn` ✓ |
| yo | Nigeria | `/countries/ng` ✓ |
| zh | China (corpus is Simplified script); Singapore | `/countries/cn` ✓ |

**Deep-link policy**: a locale's `findahelpline` entry points at a country page only
where the language→country mapping is unambiguous (single-country language, or the
corpus file's script pins the country: pa/Gurmukhi→IN, zh-Hans→CN) **and** the page
returned HTTP 200 on 2026-08-02. Multi-country languages keep the global URL —
guessing a country for a crisis surface is a milder cousin of guessing a number.
Linking to findahelpline.com is linking, not vendoring.

## Known staleness (for the next human pass)

- `iasp` URL (`https://iasp.info/resources/Crisis_Centres`) **redirects to the
  iasp.info homepage** as of 2026-08-02 — the path is stale. Kept byte-identical at the
  corpus cut (the en block is golden-frozen); update it together with the golden test.
- `988lifeline.org` returns HTTP 403 to automated checks (bot filter); loads normally
  in a browser.
- Entry names/descriptions are English in all locale files — translating them is
  localization work (linter-covered once translated), separate from number verification.
