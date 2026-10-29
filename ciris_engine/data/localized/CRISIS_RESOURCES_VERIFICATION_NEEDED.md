# Crisis Resources — Human Verification Needed

**Corpus**: `crisis_resources_{lang}.json` in this directory (one file per manifest
language). Loaded by `ciris_engine.schemas.resources.crisis.load_crisis_registry`,
injected into DSDMA prompts via `format_crisis_resources_block` (CIRISAgent#971).

## The rules

### Hotlines (suicide / crisis / mental-health lines): the absolute rule

**NEVER add, edit, or machine-generate a crisis HOTLINE number.** A wrong suicide-hotline
number is catastrophically worse than the international-directory fallback. Every
hotline / text-line entry must be verified by a human against an authoritative source
before `verified` is set `true` (`source: national_verified`), and the loader **never
emits** a phone-carrying entry with `verified: false` into a prompt. The schema refuses the
cited-sources standard below on any entry that is not `type: emergency`.

### Emergency numbers (police / ambulance / fire): the cited-sources standard

**Ruled by the repo owner (Eric) on 2026-10-29 (CIRISAgent#1248)**, replacing per-number
human verification for EMERGENCY numbers only:

1. An emergency number is emitted (`verified: true`, `source: multi_source_cited`) only when
   **at least two independent sources agree on the number AND what it reaches**, and **at
   least one of them is official**: a government, national regulator, national police /
   health / civil-protection service, the ITU, the EU 112 page, UK FCDO travel advice
   (gov.uk — official for the foreign country), or the US State Department list.
2. `source_url` is the official source; every other agreeing source is in `source_urls`
   (a structured list, so the bar is machine-checked by
   `tests/test_crisis_resources_corpus.py::TestCitedSourcesStandard1248`). Each entry's
   `validation_notes` quotes what every source says.
3. Secondary sources used: Android's emergency-number database (AOSP
   `packages/services/Telephony/ecc/input/eccdata.txt`, which every Android phone uses to
   route emergency calls, with service types) and Google libphonenumber
   `ShortNumberMetadata.xml` (number only — listed as support, never counted as one of the
   two). **Wikipedia's list is a cross-check only, never a source.** Second-opinion text
   without URLs is a lead to search from, never a source.
4. The description states only what the agreeing sources agree on; where some source lists
   more, the description or notes say so.
5. **Below the bar** (single source, sources disagree, no official source, or a region-only
   number such as Afghanistan's Kabul-only 102 or DR Congo's Kinshasa-only lines): staged
   `verified: false` with the reason in `validation_notes` (`BELOW the cited-sources bar:
   ...`), never emitted. With nothing emittable the block says "local emergency services"
   with no number.
6. `needs_verified_entries` stays `true` for every non-en locale: it tracks HOTLINES, which
   are still human-verified.

### How emergency numbers are selected (CIRISAgent#1248)

The crisis block is a system message directly after language guidance at every DMA that
carries language guidance (PDMA, CSDMA, DSDMA via `append_round1_accord_blocks`; ASPDMA,
TSASPDMA ×2, DSASPDMA, MSASPDMA, IDMA directly) — one composer,
`formatters.crisis_resources.get_crisis_resources_system_block`.

- **Location opted in** (`CIRIS_USER_COUNTRY` from the setup wizard, else the country in
  `location_utils.get_user_location()`): that country's emittable numbers FIRST, labelled
  `[<Country> — your location]` — from any locale file (a Spanish speaker in Germany gets
  Germany's numbers from the de file).
- **Then the language's countries** (`language_countries` in each corpus file, ordered by
  approximate speaker population), capped at **6** countries (`LANGUAGE_COUNTRY_CAP`).
- Every number is labelled `[<Country>]` under the "Emergency services (police / ambulance
  / fire — NOT mental-health or crisis helplines)" heading, never in the helpline list.
- **en** has an empty `language_countries` (it is the fail-safe registry for every unknown
  language, so it presumes no country) and keeps its byte-frozen legacy block
  ("Call 911 or local emergency services") unless a location is set.

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

Hotline entries cut from an authoritative machine-readable source **may** be committed
with `verified: false` + `source_url` (a human flips the flag after checking); they will
not be emitted into prompts until flipped. Emergency numbers follow the cited-sources
standard above instead.

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

## Emergency numbers, 2026-10-29 (CIRISAgent#1248)

Researched 2026-10-29 for every country in the candidate table above plus the major
English-speaking countries (en). First pass: UK FCDO "getting help" pages (fetched),
Wikipedia as cross-check. Owner-directed second-opinion leads (no URLs) were then searched
for official pages; official pages found for NG, SA, TR, ID, PK, TH, KR, DE, TZ, UG, KZ, CO
(and the 1990 Suwa Seriya Foundation, non-official, for Sri Lanka 1990). Every number was
then put through the cited-sources standard. Sources that could not be reached from the
research environment: smartraveller.gov.au (timeout), travel.state.gov (403 even with a
browser User-Agent), 112.gov.in (timeout), my.gov.sa / moi.gov.sa (403).

**Countries with at least one emitted number (55):** AF, AO, AR, AT, AU, BD, BE, BR, BY, CA,
CH, CI, CM, CN, CO, DE, DZ, EG, ES, ET (builtin, human-verified May 2026), FR, GB (`uk`),
ID, IE, IN, IR, IT, JP, KE, KR, KZ, LK, MA, MM, MX, MZ, NE, NG, NZ, PH, PK, PT, RU, SA, SG,
SN, TH, TJ, TR, TZ, UA, UG, US (builtin), VN, ZA.

**Countries with NO emitted number (2):** Iraq (no official Iraqi page found; AOSP lists only
130; FCDO's 122 / 115 / 911 are single-source) and DR Congo (FCDO: no national emergency
medical number; police 112 / fire 118 are Kinshasa-only, and AOSP lists 118 as police).

**Thin coverage worth a follow-up search** (official page for the second-opinion numbers):
Morocco (19 / 15 / 141 / 177), Algeria (14 / 17 / 1021 / 1055 — only 1548 emitted), Angola
(113 / 115 / 111 — only 112 ambulance emitted), Mozambique (119 / 117 / 112 — only 198 fire
emitted), Cameroon (119 / 118 / 112 — only 117 police emitted), Afghanistan (only 119
police), Tanzania 114 fire (TCRA numbering plan only — one source), Senegal 1515, Côte
d'Ivoire 110 / 111, Brazil 911, Colombia 119 (replaced by 123), Sri Lanka 110 / 111 / 118,
Saudi Arabia 112 / 999, Uganda 112, Indonesia 113 / 119, UK 112, Ireland 999, South Africa
10177 / 10111. **Tanzania 115 is RESERVED in the TCRA plan — do not emit.**

#### Emitted — meets the cited-sources standard (`source: multi_source_cited`, `verified: true`)

| Country | Number | Reaches | Locale file(s) | Official source (`source_url`) | Further sources (`source_urls`) |
|---|---|---|---|---|---|
| Afghanistan | `119` | Police / general emergency | fa | [FCDO](https://www.gov.uk/foreign-travel-advice/afghanistan/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Algeria | `1548` | Police | ar | [FCDO](https://www.gov.uk/foreign-travel-advice/algeria/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt) |
| Angola | `112` | Ambulance | pt | [FCDO](https://www.gov.uk/foreign-travel-advice/angola/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Argentina | `911` | Police / general emergency line | es | [FCDO](https://www.gov.uk/foreign-travel-advice/argentina/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Argentina | `107` | Ambulance | es | [FCDO](https://www.gov.uk/foreign-travel-advice/argentina/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Argentina | `101` | Police | es | [FCDO](https://www.gov.uk/foreign-travel-advice/argentina/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Argentina | `100` | Fire | es | [FCDO](https://www.gov.uk/foreign-travel-advice/argentina/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Australia | `000` | Unified emergency number (police, ambulance, fire) | en | [FCDO](https://www.gov.uk/foreign-travel-advice/australia/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Austria | `112` | European unified emergency number | de | [FCDO](https://www.gov.uk/foreign-travel-advice/austria/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Austria | `144` | Ambulance / rescue | de | [FCDO](https://www.gov.uk/foreign-travel-advice/austria/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Austria | `133` | Police | de | [FCDO](https://www.gov.uk/foreign-travel-advice/austria/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Bangladesh | `999` | Unified emergency number (police, ambulance, fire) | bn | [FCDO](https://www.gov.uk/foreign-travel-advice/bangladesh/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Belarus | `103` | Ambulance | ru | [FCDO](https://www.gov.uk/foreign-travel-advice/belarus/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Belarus | `102` | Police | ru | [FCDO](https://www.gov.uk/foreign-travel-advice/belarus/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Belarus | `101` | Fire | ru | [FCDO](https://www.gov.uk/foreign-travel-advice/belarus/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Belgium | `112` | Unified emergency number (police, ambulance, fire) | fr | [FCDO](https://www.gov.uk/foreign-travel-advice/belgium/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Brazil | `192` | Ambulance (SAMU) | pt | [FCDO](https://www.gov.uk/foreign-travel-advice/brazil/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Brazil | `190` | Police | pt | [FCDO](https://www.gov.uk/foreign-travel-advice/brazil/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Brazil | `193` | Fire | pt | [FCDO](https://www.gov.uk/foreign-travel-advice/brazil/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Cameroon | `117` | Police | fr | [FCDO](https://www.gov.uk/foreign-travel-advice/cameroon/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Canada | `911` | Unified emergency number (police, ambulance, fire) | fr | [FCDO](https://www.gov.uk/foreign-travel-advice/canada/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| China | `120` | Ambulance | zh | [FCDO](https://www.gov.uk/foreign-travel-advice/china/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| China | `110` | Police | zh | [FCDO](https://www.gov.uk/foreign-travel-advice/china/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| China | `119` | Fire | zh | [FCDO](https://www.gov.uk/foreign-travel-advice/china/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Colombia | `123` | Emergency number — fire, police (some sources also list: ambulance) | es | [bogota.gov.co](https://bogota.gov.co/mi-ciudad/seguridad/linea-123-que-cumple-17-anos-al-servicio-de-la-ciudadania) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [FCDO](https://www.gov.uk/foreign-travel-advice/colombia/getting-help), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Côte d'Ivoire | `185` | Ambulance (SAMU) | fr | [FCDO](https://www.gov.uk/foreign-travel-advice/cote-d-ivoire/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt) |
| Côte d'Ivoire | `170` | Police | fr | [FCDO](https://www.gov.uk/foreign-travel-advice/cote-d-ivoire/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Côte d'Ivoire | `180` | Fire | fr | [FCDO](https://www.gov.uk/foreign-travel-advice/cote-d-ivoire/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Egypt | `123` | Ambulance | ar | [FCDO](https://www.gov.uk/foreign-travel-advice/egypt/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Egypt | `122` | Police | ar | [FCDO](https://www.gov.uk/foreign-travel-advice/egypt/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Egypt | `180` | Fire | ar | [FCDO](https://www.gov.uk/foreign-travel-advice/egypt/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| France | `112` | Unified emergency number (police, ambulance, fire) | fr | [FCDO](https://www.gov.uk/foreign-travel-advice/france/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| France | `15` | Ambulance (SAMU) | fr | [FCDO](https://www.gov.uk/foreign-travel-advice/france/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| France | `17` | Police | fr | [FCDO](https://www.gov.uk/foreign-travel-advice/france/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| France | `114` | Emergency number for deaf and hard-of-hearing people (SMS, chat, video, fax) | fr | [FCDO](https://www.gov.uk/foreign-travel-advice/france/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt) |
| Germany | `112` | Unified emergency number (ambulance, fire; EU 112 also reaches police) | de | [FCDO](https://www.gov.uk/foreign-travel-advice/germany/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [im.baden-wuerttemberg.de](https://im.baden-wuerttemberg.de/fileadmin/redaktion/m-im/intern/dateien/pdf/MIDK_Flyer_Notfallnummern_A4_p2.pdf), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Germany | `110` | Police | de | [FCDO](https://www.gov.uk/foreign-travel-advice/germany/getting-help) | [im.baden-wuerttemberg.de](https://im.baden-wuerttemberg.de/fileadmin/redaktion/m-im/intern/dateien/pdf/MIDK_Flyer_Notfallnummern_A4_p2.pdf), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| India | `112` | Unified emergency number (police, ambulance, fire; ERSS) | bn, hi, mr, pa, ta, te, ur | [FCDO](https://www.gov.uk/foreign-travel-advice/india/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| India | `100` | Police | bn, hi, mr, pa, ta, te, ur | [FCDO](https://www.gov.uk/foreign-travel-advice/india/safety-and-security) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Indonesia | `112` | Integrated emergency number (fire, accidents, medical, disasters, crime) — live in 141 cities and regencies as of 2025; where it does not connect, use the numbers below | id | [FCDO](https://www.gov.uk/foreign-travel-advice/indonesia/getting-help) | [infopublik.id](https://infopublik.id/kategori/siaran-pers/912067/siaran-pers-kurangi-risiko-bencana-saat-lebaran-komdigi-siagakan-layanan-darurat-112-dan-ews), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Indonesia | `110` | Police (legacy fallback) | id | [FCDO](https://www.gov.uk/foreign-travel-advice/indonesia/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Indonesia | `118` | Ambulance (legacy fallback) | id | [FCDO](https://www.gov.uk/foreign-travel-advice/indonesia/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Iran | `115` | Ambulance | fa | [FCDO](https://www.gov.uk/foreign-travel-advice/iran/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Iran | `110` | Police | fa | [FCDO](https://www.gov.uk/foreign-travel-advice/iran/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Iran | `125` | Fire | fa | [FCDO](https://www.gov.uk/foreign-travel-advice/iran/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Ireland | `112` | Unified emergency number (police, ambulance, fire) | en | [FCDO](https://www.gov.uk/foreign-travel-advice/ireland/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Italy | `112` | Unified emergency number (European 112; listed by UK FCDO under police) | it | [FCDO](https://www.gov.uk/foreign-travel-advice/italy/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Italy | `118` | Ambulance | it | [FCDO](https://www.gov.uk/foreign-travel-advice/italy/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Japan | `119` | Ambulance and fire | ja | [FCDO](https://www.gov.uk/foreign-travel-advice/japan/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Japan | `110` | Police | ja | [FCDO](https://www.gov.uk/foreign-travel-advice/japan/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Kazakhstan | `112` | Single emergency number (fire, police, ambulance) | ru | [FCDO](https://www.gov.uk/foreign-travel-advice/kazakhstan/getting-help) | [gov.kz](https://www.gov.kz/memleket/entities/emer/press/news/details/438709?lang=ru), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Kazakhstan | `103` | Ambulance | ru | [FCDO](https://www.gov.uk/foreign-travel-advice/kazakhstan/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Kazakhstan | `102` | Police | ru | [FCDO](https://www.gov.uk/foreign-travel-advice/kazakhstan/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Kenya | `999` | Unified emergency number (police, ambulance, fire) | sw | [FCDO](https://www.gov.uk/foreign-travel-advice/kenya/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Mexico | `911` | Unified emergency number (police, ambulance, fire) | es | [FCDO](https://www.gov.uk/foreign-travel-advice/mexico/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Morocco | `190` | Police (mobile) | ar | [FCDO](https://www.gov.uk/foreign-travel-advice/morocco/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt) |
| Morocco | `150` | Fire, civil protection and ambulance (mobile) | ar | [FCDO](https://www.gov.uk/foreign-travel-advice/morocco/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt) |
| Mozambique | `198` | Fire | pt | [FCDO](https://www.gov.uk/foreign-travel-advice/mozambique/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Myanmar | `192` | Ambulance | my | [FCDO](https://www.gov.uk/foreign-travel-advice/myanmar/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt) |
| Myanmar | `199` | Police | my | [FCDO](https://www.gov.uk/foreign-travel-advice/myanmar/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Myanmar | `191` | Fire | my | [FCDO](https://www.gov.uk/foreign-travel-advice/myanmar/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt) |
| New Zealand | `111` | Unified emergency number (police, ambulance, fire) | en | [FCDO](https://www.gov.uk/foreign-travel-advice/new-zealand/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Niger | `15` | Ambulance | ha | [FCDO](https://www.gov.uk/foreign-travel-advice/niger/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Niger | `17` | Police | ha | [FCDO](https://www.gov.uk/foreign-travel-advice/niger/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Niger | `18` | Fire | ha | [FCDO](https://www.gov.uk/foreign-travel-advice/niger/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Nigeria | `112` | National emergency number (routes to police, fire and other responders) | ha, yo | [FCDO](https://www.gov.uk/foreign-travel-advice/nigeria/getting-help) | [ncc.gov.ng](https://ncc.gov.ng/node/1397) |
| Pakistan | `1122` | Rescue 1122 — Punjab and other provincial rescue services (ambulance, rescue, fire); not one national number | ur | [FCDO](https://www.gov.uk/foreign-travel-advice/pakistan/getting-help) | [rescue.gov.pk](https://rescue.gov.pk/), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Pakistan | `15` | Police | ur | [FCDO](https://www.gov.uk/foreign-travel-advice/pakistan/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Philippines | `911` | Unified emergency number (police, ambulance, fire) | en | [FCDO](https://www.gov.uk/foreign-travel-advice/philippines/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Portugal | `112` | Unified emergency number (police, ambulance, fire) | pt | [FCDO](https://www.gov.uk/foreign-travel-advice/portugal/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Russia | `112` | Unified emergency number (police, ambulance, fire) | ru | [FCDO](https://www.gov.uk/foreign-travel-advice/russia/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Saudi Arabia | `911` | Unified emergency number — Makkah, Madinah, Riyadh and Eastern regions only (elsewhere: 998 Civil Defense, 997 ambulance) | ar | [FCDO](https://www.gov.uk/foreign-travel-advice/saudi-arabia/getting-help) | [spa.gov.sa](https://www.spa.gov.sa/en/N2525906), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Saudi Arabia | `997` | Ambulance (Saudi Red Crescent) | ar | [spa.gov.sa](https://spa.gov.sa/en/N2554935) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Saudi Arabia | `998` | Civil Defense (fire and rescue) — the emergency number outside the four 911 regions | ar | [spa.gov.sa](https://www.spa.gov.sa/en/N2517952) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt) |
| Senegal | `17` | Police | fr | [FCDO](https://www.gov.uk/foreign-travel-advice/senegal/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Senegal | `18` | Fire | fr | [FCDO](https://www.gov.uk/foreign-travel-advice/senegal/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Senegal | `15` | Ambulance (SAMU) | fr | [FCDO](https://www.gov.uk/foreign-travel-advice/senegal/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt) |
| Singapore | `995` | Ambulance and fire (SCDF) | ta, zh | [FCDO](https://www.gov.uk/foreign-travel-advice/singapore/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Singapore | `999` | Police | ta, zh | [FCDO](https://www.gov.uk/foreign-travel-advice/singapore/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| South Africa | `112` | All emergencies, from mobile phones only | en | [FCDO](https://www.gov.uk/foreign-travel-advice/south-africa/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| South Korea | `119` | Fire and ambulance | ko | [FCDO](https://www.gov.uk/foreign-travel-advice/south-korea/getting-help) | [theme.archives.go.kr](https://theme.archives.go.kr/next/koreaOfRecord/119.do), [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| South Korea | `112` | Police | ko | [FCDO](https://www.gov.uk/foreign-travel-advice/south-korea/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Spain | `112` | Unified emergency number (police, ambulance, fire) | es | [FCDO](https://www.gov.uk/foreign-travel-advice/spain/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Sri Lanka | `1990` | Ambulance (1990 Suwa Seriya, free) | ta | [FCDO](https://www.gov.uk/foreign-travel-advice/sri-lanka/getting-help) | [1990.lk](https://www.1990.lk/?p=13) |
| Sri Lanka | `119` | Police | ta | [FCDO](https://www.gov.uk/foreign-travel-advice/sri-lanka/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Switzerland | `112` | Unified emergency number (police, ambulance, fire) | de | [FCDO](https://www.gov.uk/foreign-travel-advice/switzerland/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Switzerland | `144` | Ambulance | de | [FCDO](https://www.gov.uk/foreign-travel-advice/switzerland/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Switzerland | `117` | Police | de | [FCDO](https://www.gov.uk/foreign-travel-advice/switzerland/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Tajikistan | `103` | Ambulance (03 from landline) | fa | [FCDO](https://www.gov.uk/foreign-travel-advice/tajikistan/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Tajikistan | `102` | Police (02 from landline) | fa | [FCDO](https://www.gov.uk/foreign-travel-advice/tajikistan/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Tajikistan | `101` | Fire (01 from landline) | fa | [FCDO](https://www.gov.uk/foreign-travel-advice/tajikistan/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Tanzania | `112` | Emergency / police | sw | [FCDO](https://www.gov.uk/foreign-travel-advice/tanzania/getting-help) | [web.archive.org](https://web.archive.org/web/2021id_/https://www.tcra.go.tz/uploads/text-editor/files/National%20Numbering%20Plan%20%28Updated%20June%2C%202020%29_1622553220.pdf), [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Thailand | `191` | General emergency number | th | [FCDO](https://www.gov.uk/foreign-travel-advice/thailand/getting-help) | [mfa.go.th](https://www.mfa.go.th/en/content/eq2), [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Thailand | `1669` | Ambulance | th | [FCDO](https://www.gov.uk/foreign-travel-advice/thailand/getting-help) | [mfa.go.th](https://www.mfa.go.th/en/content/eq2), [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Thailand | `199` | Fire and rescue | th | [FCDO](https://www.gov.uk/foreign-travel-advice/thailand/getting-help) | [mfa.go.th](https://www.mfa.go.th/en/content/eq2), [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Türkiye | `112` | Emergency number — fire, police (some sources also list: ambulance) | tr | [FCDO](https://www.gov.uk/foreign-travel-advice/turkey/getting-help) | [112.gov.tr](https://www.112.gov.tr/112-acm-projesi), [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Uganda | `999` | Emergency number (free; police-operated) | sw | [FCDO](https://www.gov.uk/foreign-travel-advice/uganda/getting-help) | [upf.go.ug](https://www.upf.go.ug/), [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Ukraine | `103` | Ambulance | uk | [FCDO](https://www.gov.uk/foreign-travel-advice/ukraine/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Ukraine | `102` | Police | uk | [FCDO](https://www.gov.uk/foreign-travel-advice/ukraine/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Ukraine | `101` | Fire | uk | [FCDO](https://www.gov.uk/foreign-travel-advice/ukraine/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| United Kingdom | `999` | National emergency number (police, ambulance, fire, coastguard) | en | [gov.uk](https://www.gov.uk/guidance/999-and-112-the-uks-national-emergency-numbers) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Vietnam | `115` | Ambulance (Vietnamese only) | vi | [FCDO](https://www.gov.uk/foreign-travel-advice/vietnam/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Vietnam | `113` | Police (Vietnamese only) | vi | [FCDO](https://www.gov.uk/foreign-travel-advice/vietnam/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |
| Vietnam | `114` | Fire (Vietnamese only) | vi | [FCDO](https://www.gov.uk/foreign-travel-advice/vietnam/getting-help) | [AOSP eccdata](https://android.googlesource.com/platform/packages/services/Telephony/+/refs/heads/main/ecc/input/eccdata.txt), [libphonenumber](https://github.com/google/libphonenumber/blob/master/resources/ShortNumberMetadata.xml) |

_104 numbers emitted._

#### Staged, NOT emitted — below the bar (`verified: false`)

| Country | Number | Reaches (as staged) | Locale file(s) | Why below | Page to check |
|---|---|---|---|---|---|
| Afghanistan | `102` | Ambulance (Kabul only) | fa | region-only number (not national) | [FCDO](https://www.gov.uk/foreign-travel-advice/afghanistan/getting-help) |
| Afghanistan | `101` | Fire (or via 119) | fa | no official source (second-opinion lead only) | [FCDO](https://www.gov.uk/foreign-travel-advice/afghanistan/getting-help) |
| Algeria | `14` | Civil Protection (fire, rescue, medical evacuation) | ar | single source only (AOSP eccdata has no 14 for DZ; no second official page found) | [FCDO](https://www.gov.uk/foreign-travel-advice/algeria/getting-help) |
| Algeria | `1021` | Ambulance / medical (alternate) | ar | single source only (AOSP eccdata has no 1021 for DZ; no second official page found) | [FCDO](https://www.gov.uk/foreign-travel-advice/algeria/getting-help) |
| Algeria | `17` | Police | ar | single source only (AOSP eccdata has no 17 for DZ; no second official page found) | [FCDO](https://www.gov.uk/foreign-travel-advice/algeria/getting-help) |
| Algeria | `1055` | Gendarmerie | ar | no official source (second-opinion lead only) | [FCDO](https://www.gov.uk/foreign-travel-advice/algeria/getting-help) |
| Angola | `113` | Police | pt | no official source (second-opinion lead only) | [FCDO](https://www.gov.uk/foreign-travel-advice/angola/getting-help) |
| Angola | `115` | Fire | pt | no official source (second-opinion lead only) | [FCDO](https://www.gov.uk/foreign-travel-advice/angola/getting-help) |
| Angola | `111` | Unified public-safety number (CISP; emerging — may not work outside Luanda/Benguela) | pt | no official source (second-opinion lead only) | [FCDO](https://www.gov.uk/foreign-travel-advice/angola/getting-help) |
| Angola | `110` | Police (per UK FCDO; second opinion gives 113) | pt | single source only (AOSP eccdata has no 110 for AO; no second official page found) | [FCDO](https://www.gov.uk/foreign-travel-advice/angola/getting-help) |
| Angola | `118` | Fire (per UK FCDO; second opinion gives 115) | pt | single source only (AOSP eccdata has no 118 for AO; no second official page found) | [FCDO](https://www.gov.uk/foreign-travel-advice/angola/getting-help) |
| Brazil | `911` | Police (alternative to 190) | pt | single source only (AOSP eccdata has no 911 for BR; no second official page found) | [FCDO](https://www.gov.uk/foreign-travel-advice/brazil/getting-help) |
| Cameroon | `1500` | Police (reporting line; alternate) | fr | no official source (second-opinion lead only) | [FCDO](https://www.gov.uk/foreign-travel-advice/cameroon/getting-help) |
| Cameroon | `119` | SAMU / ambulance | fr | no official source (second-opinion lead only) | [FCDO](https://www.gov.uk/foreign-travel-advice/cameroon/getting-help) |
| Cameroon | `118` | Fire | fr | no official source (second-opinion lead only) | [FCDO](https://www.gov.uk/foreign-travel-advice/cameroon/getting-help) |
| Cameroon | `112` | Emergency number (secondary / mobile) | fr | single source only (AOSP eccdata has no 112 for CM; no second official page found) | [FCDO](https://www.gov.uk/foreign-travel-advice/cameroon/getting-help) |
| Colombia | `119` | Fire | es | single source only (AOSP eccdata has no 119 for CO; no second official page found) | [FCDO](https://www.gov.uk/foreign-travel-advice/colombia/getting-help) |
| Côte d'Ivoire | `110` | Police | fr | single source only (AOSP eccdata has no 110 for CI; no second official page found) | [FCDO](https://www.gov.uk/foreign-travel-advice/cote-d-ivoire/getting-help) |
| Côte d'Ivoire | `111` | Police | fr | single source only (AOSP eccdata has no 111 for CI; no second official page found) | [FCDO](https://www.gov.uk/foreign-travel-advice/cote-d-ivoire/getting-help) |
| DR Congo | `112` | Police (Kinshasa only) | fr | region-only number (not national) | [FCDO](https://www.gov.uk/foreign-travel-advice/democratic-republic-of-the-congo/getting-help) |
| DR Congo | `118` | Fire (Kinshasa only) | fr | region-only number (not national) | [FCDO](https://www.gov.uk/foreign-travel-advice/democratic-republic-of-the-congo/getting-help) |
| Indonesia | `119` | Ambulance (legacy fallback) | id | no official source (second-opinion lead only) | [FCDO](https://www.gov.uk/foreign-travel-advice/indonesia/getting-help) |
| Indonesia | `113` | Fire (legacy fallback) | id | no official source (second-opinion lead only) | [FCDO](https://www.gov.uk/foreign-travel-advice/indonesia/getting-help) |
| Iraq | `911` | Unified emergency number (police, ambulance, fire; 2025 unification) | ar | single source only (AOSP eccdata has no 911 for IQ; no second official page found) | [FCDO](https://www.gov.uk/foreign-travel-advice/iraq/getting-help) |
| Iraq | `122` | Ambulance | ar | single source only (AOSP eccdata has no 122 for IQ; no second official page found) | [FCDO](https://www.gov.uk/foreign-travel-advice/iraq/getting-help) |
| Iraq | `115` | Fire | ar | single source only (AOSP eccdata has no 115 for IQ; no second official page found) | [FCDO](https://www.gov.uk/foreign-travel-advice/iraq/getting-help) |
| Iraq | `104` | Police (legacy; still used in Kurdistan Region) | ar | no official source (second-opinion lead only) | [FCDO](https://www.gov.uk/foreign-travel-advice/iraq/getting-help) |
| Ireland | `999` | Unified emergency number (police, ambulance, fire) | en | single source only (AOSP eccdata has no 999 for IE; no second official page found) | [FCDO](https://www.gov.uk/foreign-travel-advice/ireland/getting-help) |
| Morocco | `19` | Police (landline) | ar | no official source (second-opinion lead only) | [FCDO](https://www.gov.uk/foreign-travel-advice/morocco/getting-help) |
| Morocco | `15` | Fire, civil protection and ambulance (landline) | ar | no official source (second-opinion lead only) | [FCDO](https://www.gov.uk/foreign-travel-advice/morocco/getting-help) |
| Morocco | `141` | SAMU medical emergency | ar | no official source (second-opinion lead only) | [FCDO](https://www.gov.uk/foreign-travel-advice/morocco/getting-help) |
| Morocco | `177` | Gendarmerie (rural areas / highways) | ar | single source only (AOSP eccdata has no 177 for MA; no second official page found) | [FCDO](https://www.gov.uk/foreign-travel-advice/morocco/getting-help) |
| Mozambique | `119` | Police | pt | no official source (second-opinion lead only) | [FCDO](https://www.gov.uk/foreign-travel-advice/mozambique/getting-help) |
| Mozambique | `117` | Ambulance | pt | no official source (second-opinion lead only) | [FCDO](https://www.gov.uk/foreign-travel-advice/mozambique/getting-help) |
| Mozambique | `112` | Police / general emergency (alternate) | pt | single source only (AOSP eccdata has no 112 for MZ; no second official page found) | [FCDO](https://www.gov.uk/foreign-travel-advice/mozambique/getting-help) |
| Saudi Arabia | `112` | Emergency number for callers without a Saudi SIM card | ar | single source only (AOSP eccdata has no 112 for SA; no second official page found) | [FCDO](https://www.gov.uk/foreign-travel-advice/saudi-arabia/getting-help) |
| Senegal | `1515` | SAMU medical emergency | fr | no official source (second-opinion lead only) | [FCDO](https://www.gov.uk/foreign-travel-advice/senegal/getting-help) |
| Senegal | `123` | Gendarmerie (military police, countryside) | fr | single source only (AOSP eccdata has no 123 for SN; no second official page found) | [FCDO](https://www.gov.uk/foreign-travel-advice/senegal/getting-help) |
| South Africa | `10177` | Ambulance and fire | en | single source only (AOSP eccdata has no 10177 for ZA; no second official page found) | [FCDO](https://www.gov.uk/foreign-travel-advice/south-africa/getting-help) |
| South Africa | `10111` | Police | en | single source only (AOSP eccdata has no 10111 for ZA; no second official page found) | [FCDO](https://www.gov.uk/foreign-travel-advice/south-africa/getting-help) |
| Sri Lanka | `118` | Police (alternate listed by UK FCDO) | ta | single source only (AOSP eccdata has no 118 for LK; no second official page found) | [FCDO](https://www.gov.uk/foreign-travel-advice/sri-lanka/getting-help) |
| Sri Lanka | `110` | Fire | ta | no official source (second-opinion lead only) | [FCDO](https://www.gov.uk/foreign-travel-advice/sri-lanka/getting-help) |
| Sri Lanka | `111` | Fire and rescue (listed by UK FCDO; second opinion gives 110) | ta | single source only (AOSP eccdata has no 111 for LK; no second official page found) | [FCDO](https://www.gov.uk/foreign-travel-advice/sri-lanka/getting-help) |
| Tanzania | `114` | Fire | sw | single source only (AOSP eccdata has no 114 for TZ; no second official page found) | [FCDO](https://www.gov.uk/foreign-travel-advice/tanzania/getting-help) |
| Tanzania | `115` | Ambulance (public ambulance coverage outside the cities is limited) | sw | no official source (second-opinion lead only) | [FCDO](https://www.gov.uk/foreign-travel-advice/tanzania/getting-help) |
| Uganda | `112` | Emergency number (free; police-operated) | sw | single source only (AOSP eccdata has no 112 for UG; no second official page found) | [FCDO](https://www.gov.uk/foreign-travel-advice/uganda/getting-help) |
| United Kingdom | `112` | Pan-European emergency number, also works in the UK | en | single source only (AOSP eccdata has no 112 for GB; no second official page found) | [gov.uk](https://www.gov.uk/guidance/999-and-112-the-uks-national-emergency-numbers) |

_47 numbers staged below the bar._

