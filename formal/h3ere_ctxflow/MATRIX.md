# Measured context matrix (CIRISAgent v2.22.1, as-sent prompts)

Share of LLM calls whose prompt contained each item. ✓ ≥ 0.95, · ≤ 0.05. Generated from `matrix.json` (`measure.py`); 42,998 calls. "rule text" matches a slice of the case's rule; for cases whose rule carries a rendered `{id:…}` placeholder the match can miss, so S5 values below 1 are a lower bound.

**S1 default (no rule) — seed**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 676 | ✓ | ✓ | ✓ | ✓ | · | · | · | · | · | · |
| TSASPDMA | 240 | ✓ | ✓ | ✓ | ✓ | · | · | · | · | · | · |
| coherence | 657 | ✓ | ✓ | ✓ | ✓ | · | · | · | · | · | · |
| entropy | 656 | · | · | · | ✓ | · | · | · | · | · | · |
| epistemic humility | 675 | ✓ | ✓ | ✓ | ✓ | · | · | · | · | · | · |
| optimization veto | 675 | · | · | · | ✓ | · | · | · | · | · | · |
| CSDMA | 676 | ✓ | ✓ | ✓ | ✓ | · | · | · | · | · | · |
| DSDMA | 832 | ✓ | ✓ | ✓ | ✓ | · | · | · | · | · | · |
| PDMA | 676 | ✓ | ✓ | ✓ | ✓ | · | · | · | · | · | · |
| IDMA | 676 | ✓ | ✓ | ✓ | · | · | · | · | · | · | · |

**S1 default (no rule) — seed+retry**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 89 | ✓ | ✓ | ✓ | ✓ | · | · | · | · | ✓ | · |
| TSASPDMA | 39 | ✓ | ✓ | ✓ | ✓ | · | · | · | · | · | · |
| coherence | 86 | ✓ | ✓ | ✓ | ✓ | · | · | · | · | · | · |
| entropy | 86 | · | · | · | ✓ | · | · | · | · | · | · |
| epistemic humility | 89 | ✓ | ✓ | ✓ | ✓ | · | · | · | · | · | · |
| optimization veto | 89 | · | · | · | ✓ | · | · | · | · | · | · |

**S1 default (no rule) — followup**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 974 | ✓ | ✓ | ✓ | ✓ | · | · | · | ✓ | · | 0.10 |
| TSASPDMA | 16 | 0.94 | ✓ | 0.94 | ✓ | · | · | · | ✓ | · | 0.94 |
| coherence | 297 | 0.21 | 0.27 | 0.20 | ✓ | · | · | · | 0.80 | · | · |
| entropy | 298 | 0.22 | 0.29 | 0.21 | ✓ | · | · | · | ✓ | · | 0.22 |
| epistemic humility | 300 | 0.21 | 0.28 | 0.20 | ✓ | · | · | · | 0.80 | · | · |
| optimization veto | 300 | 0.22 | 0.30 | 0.21 | ✓ | · | · | · | ✓ | · | 0.22 |
| CSDMA | 975 | ✓ | ✓ | ✓ | ✓ | · | · | · | ✓ | · | 0.10 |
| DSDMA | 1016 | ✓ | ✓ | ✓ | ✓ | · | · | · | ✓ | · | 0.13 |
| PDMA | 974 | ✓ | ✓ | ✓ | ✓ | · | · | · | ✓ | · | 0.10 |
| IDMA | 976 | ✓ | ✓ | ✓ | · | · | · | · | ✓ | · | 0.10 |

**S1 default (no rule) — followup+retry**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 50 | ✓ | ✓ | ✓ | ✓ | · | · | · | ✓ | ✓ | 0.84 |
| TSASPDMA | 12 | ✓ | ✓ | ✓ | ✓ | · | · | · | ✓ | · | ✓ |
| coherence | 47 | 0.81 | 0.85 | 0.81 | ✓ | · | · | · | 0.23 | · | 0.09 |
| entropy | 47 | 0.77 | 0.85 | 0.77 | ✓ | · | · | · | ✓ | · | 0.83 |
| epistemic humility | 48 | 0.81 | 0.85 | 0.81 | ✓ | · | · | · | 0.23 | · | 0.08 |
| optimization veto | 48 | 0.77 | 0.85 | 0.77 | ✓ | · | · | · | ✓ | · | 0.83 |

**S2 rule stated by user (same message) — seed**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 307 | ✓ | ✓ | ✓ | ✓ | ✓ | · | · | · | · | · |
| TSASPDMA | 51 | ✓ | ✓ | ✓ | ✓ | ✓ | · | · | · | · | · |
| coherence | 306 | ✓ | ✓ | ✓ | ✓ | ✓ | · | · | · | · | · |
| entropy | 306 | · | 0.06 | · | ✓ | · | · | · | · | · | · |
| epistemic humility | 307 | ✓ | ✓ | ✓ | ✓ | ✓ | · | · | · | · | · |
| optimization veto | 307 | · | 0.07 | · | ✓ | · | · | · | · | · | · |
| CSDMA | 307 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | · | · | · |
| DSDMA | 317 | ✓ | ✓ | ✓ | ✓ | ✓ | · | · | · | · | · |
| PDMA | 307 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | · | · | · |
| IDMA | 307 | ✓ | ✓ | ✓ | · | ✓ | · | · | · | · | · |

**S2 rule stated by user (same message) — seed+retry**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 107 | ✓ | 0.86 | 0.86 | ✓ | ✓ | · | · | · | ✓ | · |
| TSASPDMA | 12 | ✓ | 0.75 | 0.75 | ✓ | ✓ | · | · | · | · | · |
| coherence | 106 | ✓ | 0.87 | 0.87 | ✓ | ✓ | · | · | · | · | · |
| entropy | 106 | · | 0.08 | · | ✓ | · | · | · | · | · | · |
| epistemic humility | 107 | ✓ | 0.86 | 0.86 | ✓ | ✓ | · | · | · | · | · |
| optimization veto | 107 | · | 0.07 | · | ✓ | · | · | · | · | · | · |

**S2 rule stated by user (same message) — followup**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 552 | ✓ | 0.86 | 0.86 | ✓ | ✓ | · | · | ✓ | · | 0.49 |
| TSASPDMA | 17 | ✓ | 0.82 | 0.82 | ✓ | ✓ | · | · | ✓ | · | ✓ |
| coherence | 246 | 0.79 | 0.59 | 0.59 | ✓ | 0.79 | · | · | 0.21 | · | · |
| entropy | 246 | · | 0.58 | 0.58 | ✓ | · | · | · | ✓ | · | 0.81 |
| epistemic humility | 246 | 0.79 | 0.59 | 0.59 | ✓ | 0.79 | · | · | 0.21 | · | · |
| optimization veto | 246 | · | 0.58 | 0.58 | ✓ | · | · | · | ✓ | · | 0.81 |
| CSDMA | 555 | ✓ | 0.86 | 0.86 | ✓ | ✓ | ✓ | · | ✓ | · | 0.49 |
| DSDMA | 552 | ✓ | 0.86 | 0.86 | ✓ | ✓ | · | · | ✓ | · | 0.49 |
| PDMA | 552 | ✓ | 0.86 | 0.86 | ✓ | ✓ | ✓ | · | ✓ | · | 0.49 |
| IDMA | 552 | ✓ | 0.86 | 0.86 | · | ✓ | · | · | ✓ | · | 0.49 |

**S2 rule stated by user (same message) — followup+retry**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 192 | ✓ | 0.69 | 0.69 | ✓ | ✓ | · | · | ✓ | ✓ | ✓ |
| TSASPDMA | 22 | ✓ | 0.86 | 0.86 | ✓ | ✓ | · | · | ✓ | · | ✓ |
| coherence | 190 | ✓ | 0.66 | 0.66 | ✓ | ✓ | · | · | · | · | · |
| entropy | 190 | · | 0.66 | 0.66 | ✓ | · | · | · | ✓ | · | ✓ |
| epistemic humility | 190 | ✓ | 0.66 | 0.66 | ✓ | ✓ | · | · | · | · | · |
| optimization veto | 190 | · | 0.66 | 0.66 | ✓ | · | · | · | ✓ | · | ✓ |

**S3 rule stated by WA (earlier message, same channel) — seed**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 307 | ✓ | ✓ | · | ✓ | ✓ | · | · | · | · | · |
| TSASPDMA | 47 | ✓ | ✓ | · | ✓ | ✓ | · | · | · | · | · |
| coherence | 284 | ✓ | ✓ | · | ✓ | ✓ | · | · | · | · | · |
| entropy | 284 | · | · | · | ✓ | · | · | · | · | · | · |
| epistemic humility | 293 | ✓ | ✓ | · | ✓ | ✓ | · | · | · | · | · |
| optimization veto | 293 | · | · | · | ✓ | · | · | · | · | · | · |
| CSDMA | 307 | ✓ | ✓ | · | ✓ | ✓ | · | · | · | · | · |
| DSDMA | 458 | ✓ | ✓ | · | ✓ | ✓ | · | · | · | · | · |
| PDMA | 308 | ✓ | ✓ | · | ✓ | ✓ | · | · | · | · | · |
| IDMA | 307 | ✓ | ✓ | · | · | ✓ | · | · | · | · | · |

**S3 rule stated by WA (earlier message, same channel) — seed+retry**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 113 | ✓ | 0.89 | · | ✓ | ✓ | · | · | · | ✓ | · |
| TSASPDMA | 17 | ✓ | ✓ | · | ✓ | ✓ | · | · | · | · | · |
| coherence | 109 | ✓ | 0.90 | · | ✓ | ✓ | · | · | · | · | · |
| entropy | 109 | · | 0.06 | · | ✓ | · | · | · | · | · | · |
| epistemic humility | 112 | ✓ | 0.89 | · | ✓ | ✓ | · | · | · | · | · |
| optimization veto | 112 | · | 0.06 | · | ✓ | · | · | · | · | · | · |

**S3 rule stated by WA (earlier message, same channel) — followup**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 599 | ✓ | 0.90 | · | ✓ | 0.51 | · | · | ✓ | · | 0.59 |
| TSASPDMA | 55 | ✓ | 0.89 | · | ✓ | 0.87 | · | · | ✓ | · | ✓ |
| coherence | 303 | 0.86 | 0.73 | · | ✓ | 0.84 | · | · | 0.17 | · | · |
| entropy | 303 | 0.86 | 0.73 | · | ✓ | · | · | · | ✓ | · | 0.87 |
| epistemic humility | 307 | 0.86 | 0.73 | · | ✓ | 0.84 | · | · | 0.17 | · | · |
| optimization veto | 306 | 0.85 | 0.73 | · | ✓ | · | · | · | ✓ | · | 0.86 |
| CSDMA | 599 | ✓ | 0.90 | · | ✓ | 0.51 | · | · | ✓ | · | 0.59 |
| DSDMA | 653 | ✓ | 0.90 | · | ✓ | 0.55 | · | · | ✓ | · | 0.62 |
| PDMA | 599 | ✓ | 0.90 | · | ✓ | 0.51 | · | · | ✓ | · | 0.59 |
| IDMA | 600 | ✓ | 0.90 | · | · | 0.51 | · | · | ✓ | · | 0.59 |

**S3 rule stated by WA (earlier message, same channel) — followup+retry**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 240 | ✓ | 0.80 | · | ✓ | ✓ | · | · | ✓ | ✓ | ✓ |
| TSASPDMA | 49 | ✓ | 0.88 | · | ✓ | 0.90 | · | · | ✓ | · | ✓ |
| coherence | 238 | ✓ | 0.80 | · | ✓ | ✓ | · | · | · | · | · |
| entropy | 238 | ✓ | 0.80 | · | ✓ | · | · | · | ✓ | · | ✓ |
| epistemic humility | 240 | ✓ | 0.80 | · | ✓ | ✓ | · | · | · | · | · |
| optimization veto | 240 | ✓ | 0.80 | · | ✓ | · | · | · | ✓ | · | ✓ |

**S3r WA states the rule (the rule message itself) — seed**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 307 | ✓ | · | · | ✓ | ✓ | · | · | · | · | · |
| coherence | 307 | ✓ | · | · | ✓ | ✓ | · | · | · | · | · |
| entropy | 307 | · | · | · | ✓ | · | · | · | · | · | · |
| epistemic humility | 307 | ✓ | · | · | ✓ | ✓ | · | · | · | · | · |
| optimization veto | 307 | · | · | · | ✓ | · | · | · | · | · | · |
| CSDMA | 307 | ✓ | · | · | ✓ | ✓ | ✓ | · | · | · | · |
| DSDMA | 439 | ✓ | · | · | ✓ | ✓ | · | · | · | · | · |
| PDMA | 308 | ✓ | · | · | ✓ | ✓ | ✓ | · | · | · | · |
| IDMA | 307 | ✓ | · | · | · | ✓ | · | · | · | · | · |

**S3r WA states the rule (the rule message itself) — seed+retry**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 160 | ✓ | · | · | ✓ | ✓ | · | · | · | ✓ | · |
| coherence | 160 | ✓ | · | · | ✓ | ✓ | · | · | · | · | · |
| entropy | 160 | · | · | · | ✓ | · | · | · | · | · | · |
| epistemic humility | 160 | ✓ | · | · | ✓ | ✓ | · | · | · | · | · |
| optimization veto | 160 | · | · | · | ✓ | · | · | · | · | · | · |

**S3r WA states the rule (the rule message itself) — followup**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 654 | ✓ | · | · | ✓ | ✓ | · | · | ✓ | · | 0.71 |
| coherence | 345 | ✓ | · | · | ✓ | ✓ | · | · | · | · | · |
| entropy | 345 | ✓ | · | · | ✓ | · | · | · | ✓ | · | ✓ |
| epistemic humility | 346 | ✓ | · | · | ✓ | ✓ | · | · | · | · | · |
| optimization veto | 346 | ✓ | · | · | ✓ | · | · | · | ✓ | · | ✓ |
| CSDMA | 657 | ✓ | · | · | ✓ | ✓ | ✓ | · | ✓ | · | 0.71 |
| DSDMA | 849 | ✓ | · | · | ✓ | ✓ | · | · | ✓ | · | 0.78 |
| PDMA | 655 | ✓ | · | · | ✓ | ✓ | ✓ | · | ✓ | · | 0.71 |
| IDMA | 655 | ✓ | · | · | · | ✓ | · | · | ✓ | · | 0.71 |

**S3r WA states the rule (the rule message itself) — followup+retry**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 322 | ✓ | · | · | ✓ | ✓ | · | · | ✓ | ✓ | ✓ |
| coherence | 321 | ✓ | · | · | ✓ | ✓ | · | · | · | · | · |
| entropy | 321 | ✓ | · | · | ✓ | · | · | · | ✓ | · | ✓ |
| epistemic humility | 323 | ✓ | · | · | ✓ | ✓ | · | · | · | · | · |
| optimization veto | 322 | ✓ | · | · | ✓ | · | · | · | ✓ | · | ✓ |

**S4 guidance task after WA answer — seed**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 50 | ✓ | 0.54 | 0.30 | ✓ | ✓ | ✓ | ✓ | · | · | · |
| coherence | 38 | ✓ | 0.71 | 0.39 | ✓ | ✓ | · | ✓ | · | · | · |
| entropy | 38 | · | · | · | ✓ | · | · | · | · | · | · |
| epistemic humility | 50 | ✓ | 0.54 | 0.30 | ✓ | ✓ | · | ✓ | · | · | · |
| optimization veto | 50 | · | 0.24 | · | ✓ | ✓ | · | ✓ | · | · | · |
| CSDMA | 50 | ✓ | 0.54 | 0.30 | ✓ | ✓ | ✓ | ✓ | · | · | · |
| DSDMA | 56 | ✓ | 0.59 | 0.32 | ✓ | ✓ | · | ✓ | · | · | · |
| PDMA | 50 | ✓ | 0.54 | 0.30 | ✓ | ✓ | ✓ | ✓ | · | · | · |
| IDMA | 50 | ✓ | 0.54 | 0.30 | · | ✓ | · | ✓ | · | · | · |

**S4 guidance task after WA answer — seed+retry**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 31 | ✓ | 0.65 | 0.29 | ✓ | ✓ | ✓ | ✓ | · | ✓ | · |
| coherence | 28 | ✓ | 0.71 | 0.32 | ✓ | ✓ | · | ✓ | · | · | · |
| entropy | 28 | · | · | · | ✓ | · | · | · | · | · | · |
| epistemic humility | 31 | ✓ | 0.65 | 0.29 | ✓ | ✓ | · | ✓ | · | · | · |
| optimization veto | 31 | · | 0.35 | · | ✓ | ✓ | · | ✓ | · | · | · |

**S4 guidance task after WA answer — followup**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 138 | ✓ | 0.58 | 0.25 | ✓ | ✓ | ✓ | ✓ | ✓ | · | 0.72 |
| TSASPDMA | 2 | ✓ | ✓ | 0.50 | ✓ | ✓ | · | ✓ | ✓ | · | ✓ |
| coherence | 88 | 0.84 | 0.60 | 0.22 | ✓ | 0.88 | · | 0.84 | 0.16 | · | · |
| entropy | 88 | 0.62 | 0.60 | 0.22 | ✓ | 0.08 | · | · | ✓ | · | 0.84 |
| epistemic humility | 88 | 0.84 | 0.60 | 0.22 | ✓ | 0.88 | · | 0.84 | 0.16 | · | · |
| optimization veto | 88 | 0.62 | 0.60 | 0.22 | ✓ | ✓ | · | ✓ | ✓ | · | 0.84 |
| CSDMA | 138 | ✓ | 0.58 | 0.25 | ✓ | ✓ | ✓ | ✓ | ✓ | · | 0.72 |
| DSDMA | 174 | ✓ | 0.53 | 0.21 | ✓ | ✓ | · | ✓ | ✓ | · | 0.78 |
| PDMA | 138 | ✓ | 0.58 | 0.25 | ✓ | ✓ | ✓ | ✓ | ✓ | · | 0.72 |
| IDMA | 138 | ✓ | 0.58 | 0.25 | · | ✓ | · | ✓ | ✓ | · | 0.72 |

**S4 guidance task after WA answer — followup+retry**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 67 | ✓ | 0.75 | 0.25 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| TSASPDMA | 2 | ✓ | ✓ | · | ✓ | ✓ | · | ✓ | ✓ | · | ✓ |
| coherence | 67 | ✓ | 0.75 | 0.25 | ✓ | ✓ | · | ✓ | · | · | · |
| entropy | 67 | 0.75 | 0.75 | 0.25 | ✓ | · | · | · | ✓ | · | ✓ |
| epistemic humility | 67 | ✓ | 0.75 | 0.25 | ✓ | ✓ | · | ✓ | · | · | · |
| optimization veto | 67 | 0.75 | 0.75 | 0.25 | ✓ | ✓ | · | ✓ | ✓ | · | ✓ |

**S5 after amendment landed (other user) — seed**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 8 | ✓ | ✓ | ✓ | ✓ | 0.62 | 0.62 | · | · | · | · |
| TSASPDMA | 5 | ✓ | ✓ | ✓ | ✓ | 0.40 | 0.40 | · | · | · | · |
| coherence | 8 | ✓ | ✓ | ✓ | ✓ | 0.62 | 0.62 | · | · | · | · |
| entropy | 8 | · | 0.38 | 0.38 | ✓ | 0.62 | 0.62 | · | · | · | · |
| epistemic humility | 8 | ✓ | ✓ | ✓ | ✓ | 0.62 | 0.62 | · | · | · | · |
| optimization veto | 8 | · | 0.38 | 0.38 | ✓ | 0.62 | 0.62 | · | · | · | · |
| CSDMA | 8 | ✓ | ✓ | ✓ | ✓ | 0.62 | 0.62 | · | · | · | · |
| DSDMA | 17 | ✓ | ✓ | ✓ | ✓ | 0.82 | 0.82 | · | · | · | · |
| PDMA | 8 | ✓ | ✓ | ✓ | ✓ | 0.62 | 0.62 | · | · | · | · |
| IDMA | 8 | ✓ | ✓ | ✓ | · | · | · | · | · | · | · |

**S5 after amendment landed (other user) — seed+retry**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 4 | ✓ | ✓ | ✓ | ✓ | 0.50 | 0.50 | · | · | ✓ | · |
| TSASPDMA | 3 | ✓ | ✓ | ✓ | ✓ | 0.67 | 0.67 | · | · | · | · |
| coherence | 4 | ✓ | ✓ | ✓ | ✓ | 0.50 | 0.50 | · | · | · | · |
| entropy | 4 | 0.25 | 0.75 | 0.75 | ✓ | 0.50 | 0.50 | · | · | · | · |
| epistemic humility | 4 | ✓ | ✓ | ✓ | ✓ | 0.50 | 0.50 | · | · | · | · |
| optimization veto | 4 | 0.25 | 0.75 | 0.75 | ✓ | 0.50 | 0.50 | · | · | · | · |

**S5 after amendment landed (other user) — followup**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 15 | ✓ | ✓ | ✓ | ✓ | 0.67 | 0.67 | · | ✓ | · | 0.33 |
| TSASPDMA | 3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | ✓ | · | ✓ |
| coherence | 7 | 0.57 | 0.86 | 0.86 | ✓ | 0.71 | 0.71 | · | 0.57 | · | 0.14 |
| entropy | 7 | 0.57 | 0.86 | 0.86 | ✓ | 0.71 | 0.71 | · | ✓ | · | 0.57 |
| epistemic humility | 7 | 0.57 | 0.86 | 0.86 | ✓ | 0.71 | 0.71 | · | 0.57 | · | 0.14 |
| optimization veto | 7 | 0.57 | 0.86 | 0.86 | ✓ | 0.71 | 0.71 | · | ✓ | · | 0.57 |
| CSDMA | 15 | ✓ | ✓ | ✓ | ✓ | 0.67 | 0.67 | · | ✓ | · | 0.33 |
| DSDMA | 15 | ✓ | ✓ | ✓ | ✓ | 0.67 | 0.67 | · | ✓ | · | 0.33 |
| PDMA | 15 | ✓ | ✓ | ✓ | ✓ | 0.67 | 0.67 | · | ✓ | · | 0.33 |
| IDMA | 15 | ✓ | ✓ | ✓ | · | · | · | · | ✓ | · | 0.33 |

**S5 after amendment landed (other user) — followup+retry**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | ✓ | ✓ | ✓ |
| TSASPDMA | 3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | ✓ | · | ✓ |
| coherence | 3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | · | · | · |
| entropy | 3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | ✓ | · | ✓ |
| epistemic humility | 3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | · | · | · |
| optimization veto | 3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | ✓ | · | ✓ |

**S5r after amendment + restart — seed**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 5 | ✓ | ✓ | ✓ | ✓ | 0.40 | 0.40 | · | · | ✓ | · |
| TSASPDMA | 3 | ✓ | ✓ | ✓ | ✓ | · | · | · | · | · | · |
| coherence | 5 | ✓ | ✓ | ✓ | ✓ | 0.40 | 0.40 | · | · | · | · |
| entropy | 5 | · | 0.20 | 0.20 | ✓ | 0.40 | 0.40 | · | · | · | · |
| epistemic humility | 5 | ✓ | ✓ | ✓ | ✓ | 0.40 | 0.40 | · | · | · | · |
| optimization veto | 5 | · | 0.20 | 0.20 | ✓ | 0.40 | 0.40 | · | · | · | · |
| CSDMA | 5 | ✓ | ✓ | ✓ | ✓ | 0.40 | 0.40 | · | · | · | · |
| DSDMA | 11 | ✓ | ✓ | ✓ | ✓ | 0.73 | 0.73 | · | · | · | · |
| PDMA | 5 | ✓ | ✓ | ✓ | ✓ | 0.40 | 0.40 | · | · | · | · |
| IDMA | 5 | ✓ | ✓ | ✓ | · | · | · | · | · | · | · |

**S5r after amendment + restart — seed+retry**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 2 | ✓ | ✓ | ✓ | ✓ | · | · | · | · | ✓ | · |
| TSASPDMA | 1 | ✓ | ✓ | ✓ | ✓ | · | · | · | · | · | · |
| coherence | 2 | ✓ | ✓ | ✓ | ✓ | · | · | · | · | · | · |
| entropy | 2 | · | 0.50 | 0.50 | ✓ | · | · | · | · | · | · |
| epistemic humility | 2 | ✓ | ✓ | ✓ | ✓ | · | · | · | · | · | · |
| optimization veto | 2 | · | 0.50 | 0.50 | ✓ | · | · | · | · | · | · |

**S5r after amendment + restart — followup**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 7 | ✓ | ✓ | ✓ | ✓ | 0.29 | 0.29 | · | ✓ | ✓ | · |
| coherence | 2 | · | 0.50 | 0.50 | ✓ | · | · | · | ✓ | · | · |
| entropy | 2 | · | 0.50 | 0.50 | ✓ | · | · | · | ✓ | · | · |
| epistemic humility | 2 | · | 0.50 | 0.50 | ✓ | · | · | · | ✓ | · | · |
| optimization veto | 2 | · | 0.50 | 0.50 | ✓ | · | · | · | ✓ | · | · |
| CSDMA | 7 | ✓ | ✓ | ✓ | ✓ | 0.29 | 0.29 | · | ✓ | · | · |
| DSDMA | 7 | ✓ | ✓ | ✓ | ✓ | 0.29 | 0.29 | · | ✓ | · | · |
| PDMA | 7 | ✓ | ✓ | ✓ | ✓ | 0.29 | 0.29 | · | ✓ | · | · |
| IDMA | 7 | ✓ | ✓ | 0.71 | · | · | · | · | ✓ | · | · |

**S6 impersonator after genuine correction — seed**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | · | · | · |
| TSASPDMA | 2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | · | · | · |
| coherence | 2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | · | · | · |
| entropy | 2 | · | 0.50 | ✓ | ✓ | ✓ | ✓ | · | · | · | · |
| epistemic humility | 2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | · | · | · |
| optimization veto | 2 | · | 0.50 | ✓ | ✓ | ✓ | ✓ | · | · | · | · |
| CSDMA | 2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | · | · | · |
| DSDMA | 2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | · | · | · |
| PDMA | 2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | · | · | · |
| IDMA | 2 | ✓ | ✓ | ✓ | · | · | · | · | · | · | · |

**S6 impersonator after genuine correction — seed+retry**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | · | ✓ | · |
| TSASPDMA | 1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | · | · | · |
| coherence | 2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | · | · | · |
| entropy | 2 | · | 0.50 | ✓ | ✓ | ✓ | ✓ | · | · | · | · |
| epistemic humility | 2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | · | · | · |
| optimization veto | 2 | · | 0.50 | ✓ | ✓ | ✓ | ✓ | · | · | · | · |

**S6 impersonator after genuine correction — followup**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 4 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | ✓ | · | 0.75 |
| TSASPDMA | 3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | ✓ | · | ✓ |
| coherence | 3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | 0.33 | · | 0.33 |
| entropy | 3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | ✓ | · | ✓ |
| epistemic humility | 3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | 0.33 | · | 0.33 |
| optimization veto | 3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | ✓ | · | ✓ |
| CSDMA | 4 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | ✓ | · | 0.75 |
| DSDMA | 4 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | ✓ | · | 0.75 |
| PDMA | 4 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | ✓ | · | 0.75 |
| IDMA | 4 | ✓ | ✓ | ✓ | · | 0.25 | · | · | ✓ | · | 0.75 |

**S6 impersonator after genuine correction — followup+retry**

| stage | n | user msg | sender ID (text) | display name | identity | rule text | rule in identity | WA guidance | actions ran | veto feedback | raw text via record |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASPDMA | 2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | ✓ | ✓ | ✓ |
| TSASPDMA | 1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | ✓ | · | ✓ |
| coherence | 1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | · | · | · |
| entropy | 1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | ✓ | · | ✓ |
| epistemic humility | 1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | · | · | · |
| optimization veto | 1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | · | ✓ | · | ✓ |
