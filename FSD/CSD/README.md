# CIRIS Specification Documents — index

Standard: `FSD/CSD_STANDARD.md`. One row per CSD; the checker refuses a CSD not listed here.

| CSD | surface | flow | client floor | origin |
|---|---|---|---|---|
| [CSD-001](CSD-001-delegation-card.md) | Delegation card and screen (Family layer) | `delegation_card` | >=0.5.208 | CIRISClient#45 |
| [CSD-002](CSD-002-environment-card.md) | Environment page (Local Community layer) | `environment_card` | >=0.5.208 | CIRISClient#45 |
| [CSD-003](CSD-003-constitutional-card.md) | Constitutional screen and the Accord cards | `constitutional_card` | >=0.5.208 | CIRISClient#45 |
| [CSD-004](CSD-004-capacity-attestations.md) | Federation capacity attestations (Health & Reputation) | `capacity_attestations` | >=0.5.208 | CIRISClient#45 |

**Status on the pinned client (2026-09-08).** CIRISClient#45 is still open: none of
the tags these four flows assert exist in ciris-client 0.5.212 or on the client's
main. The gate runs the flows on every desktop leg anyway; each reaches its
starting screen through the sidebar and then reports **cannot start** at its first
`requires` (the JSON and the gallery carry it as a warning, not a red leg). The
moment a release carries #45, the same runs turn into real verdicts — nothing
needs re-wiring. The `client:` floors above are the DSL floor (scroll/wait/visible
contract), not a claim that #45 shipped in 0.5.208.
