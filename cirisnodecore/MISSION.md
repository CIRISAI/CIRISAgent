# CIRISNodeCore

**MISSION.md**. Second-tier consensus primitives for deferral routing, voting, expertise consensus, and moderation.

**Status**: Draft v1.0 (pre-implementation; extraction-stage rust crate).
**Crate identifier**: `ciris-node-core`.
**Last updated**: 2026-05-10.
**Cross-references**: `CIRISVerify`, `CIRISRegistry`, `CIRISEdge`, `CIRISPersist` (substrate); `ciris-lens-core` (peer second-tier); `CIRISAgent` (eventual consumer); `CIRISBench` (HE-300 lives there); `RATCHET` (anti-Sybil evaluator reading the crate's audit chain); `FEDERATION_THREAT_MODEL.md` v1.0; `ACCORD.md` §M-1.

**Implementation Status Legend**:
- **Spec**: specified here or in a referenced FSD; not implemented.
- **Impl**: implemented in the crate; in standalone testing.
- **Deployed**: running in production. Sub-states named where relevant: *Deployed (pilot)* at safety.ciris.ai; *Deployed (folded)* inside CIRISAgent.

Every load-bearing claim carries one of these tags.

---

## 1. Mission

### 1.1 Meta-Goal

CIRISNodeCore serves M-1 ("Promote sustainable adaptive coherence: the living conditions under which diverse sentient beings may pursue their own flourishing in justice and wonder", `ACCORD.md`) by providing the second-tier infrastructure that lets a CIRIS deployment route deferrals to people with relevant expertise, hold votes weighted by participation history, recognize emerging expertise via consensus rather than credential gatekeeping, and resist bribery of legitimate participants.

### 1.2 What CIRISNodeCore is

A rust crate. Five functions over one shared primitive set:

1. **Deferral routing**. Runtime deferral from a CIRIS agent (or other consumer) to people with expertise in the relevant (domain, language) cell. Generalizes CIRISNode's existing function. [Spec]

2. **Voting and weighted aggregation**. Signed votes on Contributions, weighted by Credits and expertise. [Spec]

3. **Expertise consensus**. The network's verdict on who has substantive competence in each cell, updated through peer attestation and validated track record. Distinct from participation weight. [Spec]

4. **Moderation**. Signed accusation with stake, witness aggregation, adjudication by Wise Authority quorum, slashing of proven-rogue actors, and reconsideration paths for reversing adjudication errors. [Spec]

5. **RATCHET integration**. The crate emits a signed audit chain that RATCHET reads for anti-Sybil pattern detection; RATCHET returns flags as advisory inputs to moderation. [Spec]

HE-300 ethical benchmarking is not in scope; it lives in `CIRISBench`. CIRISBench evaluations may flow into the crate as track-record evidence for expertise validation, but the benchmark execution itself remains in CIRISBench.

### 1.3 Position in CIRIS architecture

```
APPLICATION TIER          CIRISAgent (Python; eventually consumes ciris-node-core)
                          safety.ciris.ai (pilot deployment of ciris-node-core)
                          ────────────────────────────────────────────────────
SECOND TIER               ciris-lens-core           ciris-node-core (this)
                          observability/compendium  deferrals/voting/expertise/moderation
                          ────────────────────────────────────────────────────
SUBSTRATE TIER            ciris-verify   ciris-registry   ciris-edge   ciris-persist
                          hardware/build trust/identity   transport     storage/audit
                          ────────────────────────────────────────────────────
EVALUATOR                 RATCHET (reads chains across the federation)
```

The substrate provides identity, signed evidence, federated directory, audit log, transport, addressing. CIRISNodeCore reads these and runs the consensus logic above them. RATCHET reads CIRISNodeCore's audit chain (along with other federation chains) and produces flags. Applications consume CIRISNodeCore.

### 1.4 Extraction lifecycle

Extract to a focused rust crate; test the crate in standalone deployment; deploy in a pilot once the crate is solid; fold the crate into CIRISAgent once the pilot demonstrates the primitives carry production load. CIRISNodeCore is at the start of this lifecycle: Spec today; Impl when the crate compiles and the test suite is solid; *Deployed (pilot)* when safety.ciris.ai runs against it; *Deployed (folded)* when CIRISAgent consumes the crate in its main runtime.

Each lifecycle stage carries adversarial review proportional to its blast radius.

### 1.5 Recursive and fractal Golden Rule

The crate operates under proportionate reflective ethical responsibility: we owe ourselves what we offer to others. The obligation runs both directions at every scale (contributor, contributor cluster, cell, deployment, federation, ecosystem). The constraint applies symmetrically to CIRIS L3C as steward, to the crate as infrastructure, and to every contributor as participant. No principal is exempt from the standard they impose on others. The Ubuntu relational frame ("I am because we are") translated into a consensus protocol: legitimacy is constituted by the mutual obligations of those it binds.

### 1.6 Same primitives across applications

The eleven primitives (§2) generalize across deferral routing, safety evaluation, WA promotion, governance votes. The differentiator across applications is the **subject** of the Contribution and the **truth-grounding signal** configured for that subject. Truth-grounding fidelity varies substantially across subjects (production hedge captures for safety are tight; long-term federation health metrics for governance are loose); the mechanism is uniform, the grounding is not.

The application → primitive → grounding mapping made explicit:

| Application | Primary Contribution kind(s) | Load-bearing primitive(s) | Truth-grounding signal | Fidelity |
|---|---|---|---|---|
| Deferral routing | `deferral_request` / `deferral_response` (§4.2) | P3 Expertise ledger, P7 Weighted aggregate, P10 Witness diversity | Sustained substantive contribution by routed responders | medium |
| Safety evaluation (the pilot) | `arc_question`, `rubric_proposal`, `prompt_edit`, `failure_pattern` | P4 Vote, P5 Contribution, P7 Weighted aggregate, P11 Reconsideration | Production hedge captures + **independent foundation-model judge verdicts** (`FSD/JUDGE_MODEL.md`); see §5.4 | tight (weekly cadence) |
| WA promotion | `wa_candidacy` | P2 Credits ledger, P3 Expertise ledger, threshold gates | Sustained participation breadth (180-day window) | medium |
| Expertise attestation | `expertise_attestation` | P3 Expertise ledger, P10 Witness diversity (above jump-threshold) | Validated track record on hard cases (§3.7) | medium |
| Moderation | `moderation_event` | P8 Moderation, P9 Slashing, P10 Witness diversity, RATCHET flags | WA quorum adjudication + post-hoc Reconsideration reversal rate | loose-to-medium |
| Governance / policy | `proposal` (free-form, new battery, policy) | P4 Vote, P7 Weighted aggregate | Long-term federation health metrics; reversal/affirmation by subsequent votes | loose (quarterly+) |

The split between *tight* and *loose* grounding maps directly onto the §6.2 empirical bets — Bet B is unpacked into B-safety and B-governance precisely because the cadence and observability differ by an order of magnitude. The mechanism stays uniform; the operational confidence does not.

---

## 2. Primitives (the eleven)

The substrate (`FEDERATION_THREAT_MODEL.md` §2.2) provides twelve primitives at the substrate layer. CIRISNodeCore adds eleven at the consensus layer, operating over the substrate.

### Primitive 1: Identity (substrate inheritance)

Ed25519 federation identity with $1-bond Sybil resistance per `FSD/PROOF_OF_BENEFIT_FEDERATION.md`. The substrate provides identity continuity and action authenticity; the crate reads identity and indexes all consensus state by it. [Deployed (substrate)]

### Primitive 2: Commons Credits ledger (participation weight)

A per-contributor ledger of Commons Credits indexed by (domain, language, subject). Credits are non-transferable governance weight; they accumulate via the truth-grounding loop (Primitive 6) when signed votes align with grounded outcomes. Credits answer "how much weight does this contributor's vote carry in the aggregate." Quantitative, continuous, accruing per grounded vote, decaying per policy. [Spec]

### Primitive 3: Expertise ledger (consensus artifact on competence)

A per-contributor ledger of expertise standing indexed by (domain, language). Expertise is the network's verdict on whether the contributor has substantive competence in the cell. Not a count; a derived state computed from peer attestations from existing experts in the cell, weighted by each attester's own expertise, validated by the contributor's track record on substantively challenging cases. Indexes at (domain, language) because competence is broader than any single subject. The recursion is grounded by F-AV-BOOT external anchoring: CIRIS L3C provides an externally-anchored seed of expertise-bearers per cell, whose relative weight decays as the cell matures. Standing decays slowly on inactivity. [Spec]

### Primitive 4: Vote

A signed score on a Contribution. Vote weight = voter's Credits in cell × expertise multiplier in (domain, language). Signatures bind to (voter_id, contribution_id, score, timestamp, cell). Votes are durable in the audit chain; revocation requires explicit signed revocation. [Spec]

### Primitive 5: Contribution

A discriminated union. Variants:

- `DEFERRAL_REQUEST`. Consumer requests routing to qualified WAs.
- `DEFERRAL_RESPONSE`. Routed WA's signed response.
- `PROPOSAL`. Battery evaluation, free-form argument, new battery draft, policy proposal. The proposal-kind discriminator lives in the payload.
- `WA_CANDIDACY`. Self- or peer-nomination for Wise Authority standing.
- `EXPERTISE_ATTESTATION`. An expertise-bearer attests another contributor has expertise in a cell.
- `MODERATION_EVENT`. Accusation of rogue action (Primitive 8).

Each Contribution carries (author_id, contribution_type, subject, payload, signature, optional witness_set). [Spec]

### Primitive 6: Truth-grounding signal

Per-subject configuration that anchors weighted aggregates and Credits accrual to ground truth. Safety subjects: production hedge captures from CIRIS agents in deployment. WA candidacy: sustained substantive contribution validated against expertise consensus. Governance and policy subjects: long-term federation health metrics, reversal/affirmation by subsequent votes, external benchmark outcomes. The signal differs in fidelity across subjects; the mechanism is uniform but the grounding is not. [Spec partial]. Production hedge captures exist in CIRISAgent; the grounding loop into the ledgers is Spec.

### Primitive 7: Weighted aggregate

Per-Contribution rolling tally of votes, weighted by Primitive 4's vote weight, anchored against the truth-grounding signal (Primitive 6) where available. The aggregate is the basis for downstream decisions (proposal adoption, WA promotion, deferral consensus). The aggregate function is policy-tunable (§6.2). [Spec]

### Primitive 8: Moderation event

A Contribution subtype targeting another Contribution or contributor, alleging rogue action. Allegation types:

- `ROGUE_VOTE`. A vote that subsequent evidence shows was bribed, coerced, or otherwise structurally illegitimate.
- `COORDINATED_VOTING`. A cluster of votes whose pattern indicates collusion.
- `OUT_OF_DISTRIBUTION_ATTESTATION`. A vote or expertise attestation far outside the issuer's behavioral baseline.
- `EXTERNAL_INDUCEMENT_EVIDENCE`. Signed external evidence of bribery or coercion.
- `EXPERTISE_FRAUD`. An EXPERTISE_ATTESTATION made without substantive basis.

Filing requires the accuser to stake Commons Credits proportional to the alleged harm. ModerationEvents require witness aggregation (Primitive 10) and adjudication by a WA quorum in the relevant cell. [Spec]

### Primitive 9: Slashing attestation

A signed record reducing a target's Credits *or* Expertise standing in a specified cell, issued by a quorum of WAs in the relevant domain after adjudicating a ModerationEvent. Outcomes:

- **PROVEN_ROGUE**. Target's Credits reduced proportional to harm; if the rogue action involved expertise standing, Expertise reduced. Accuser's stake returned plus bounty from the slashed credits.
- **NOT_PROVEN**. Target's standing restored. Accuser's stake disposition is discretionary to the WA quorum: full return for good-faith filings; partial retention for marginal cases; full retention plus possible counter-moderation for filings the quorum specifically flags as bad-faith.

Slashing distinguishes proven rogue action (target acted against the protocol's terms) from miscalibration (target voted in good faith but their judgment differed from eventual ground truth). Miscalibration is not slashable. The Credits and Expertise ledgers both carry a non-negative invariant; slashing reduces toward but never below zero. [Spec]

### Primitive 10: Witness-diversity requirement

For high-stakes Contributions (ModerationEvents, WA candidacy proposals, policy proposals above a magnitude threshold, ExpertiseAttestations whose acceptance would jump the target's standing past a threshold), validity requires ≥ N independent witnesses meeting a diversity bar:

- **Jurisdictional**: witnesses span ≥ 2 jurisdictions.
- **Organizational**: no two witnesses operated by the same legal entity or entities with majority common ownership.
- **Software-stack**: witnesses run distinct client implementations.
- **Cell-expertise**: for cell-specific high-stakes Contributions, witnesses must hold non-zero Expertise standing in the (domain, language) of the Contribution. The cell here is the Expertise-granularity cell (domain, language), not the Credits-granularity cell (domain, language, subject), because witnesses evaluate substantive merit which is broader than any single subject.

The witness role is not adjudication. Witnesses attest only that the Contribution warrants review and the evidence is well-formed. Adjudication is the WA quorum's task. The diversity bar prevents a single fault-domain from suppressing or manufacturing high-stakes events. N defaults to 3; the default is policy-tunable. [Spec]

### Primitive 11: Reconsideration

A signed request to reverse a prior SlashingAttestation. Reconsideration is structurally parallel to Moderation but operates on the reverse axis: where Moderation initiates a path toward slashing (forward consequence), Reconsideration initiates a path toward restoration (reverse consequence). Without this primitive, the system has only forward consequences; a wrongful adjudication is permanent, which erodes participation by making the cost of being wrongly slashed unbounded.

Grounds for reconsideration:
- `NEW_EVIDENCE`. Evidence not available at the time of the original adjudication.
- `PROCEDURAL_ERROR`. The original adjudication failed to follow the moderation flow (witness diversity bar not actually met but accepted; quorum size below threshold; cell-expertise constraint violated).
- `QUORUM_COMPROMISE`. Post-hoc evidence that the original adjudicating quorum was bribed, coerced, or otherwise compromised.

Filing requires the requester to stake Commons Credits proportional to the alleged severity of the original adjudication error. A **fresh** WA quorum (members of the original adjudicating quorum recused) reviews the reconsideration and signs a ReconsiderationAttestation with one of three outcomes:

- **REVERSED**. Original slashing nullified; target's Credits and Expertise restored to pre-slashing values, with adjustments for any subsequent activity. Requester's stake returned. If QUORUM_COMPROMISE grounds were proven, the original quorum members face counter-moderation review.
- **PARTIAL**. Original slashing reduced but not nullified; standing restored proportional to the proven error.
- **UPHELD**. Original slashing stands. Requester's stake disposition is discretionary to the fresh quorum (same rule as NOT_PROVEN in Primitive 9).

**Recursion bound**: a target may file at most one Reconsideration per SlashingAttestation **per hash-pinned evidence package per ground** (NEW_EVIDENCE, PROCEDURAL_ERROR, QUORUM_COMPROMISE separately). An "evidence package" is a deterministically-hashable bundle (signed Contributions, attestations, external documents pinned by SHA-256) that the requester submits as the load-bearing material for the appeal; two filings with *the same* evidence package hash under the same ground collapse to one. This expands the legitimate appeal surface (a target with three distinct pieces of NEW_EVIDENCE can pursue three appeals) without weakening the harassment trip-wire: three Reconsiderations filed without success on a single SlashingAttestation — regardless of how many distinct evidence packages they cite — triggers harassment-pattern review via RATCHET integration. The bound prevents indefinite re-litigation while preserving the appeal path.

**Time bound**: Reconsideration may be filed within a policy-tunable window from the SlashingAttestation date (default proposed: 180 days). Beyond the window, only QUORUM_COMPROMISE grounds remain available (because compromise evidence may emerge years later).

**Fresh-quorum selection**: members of the original adjudicating quorum are recused. In cells with enough WAs to draw a non-overlapping quorum, this is straightforward. In narrow cells where the WA pool is small, fresh-quorum selection draws from adjacent cells whose WAs hold cell-expertise in the contribution's (domain, language) per Primitive 10; if no adjacent-cell WAs are available, federation-wide WA pool is used with explicit rationale recorded. This is a structural gap in narrow cells; see §9. [Spec]

### 2.12 RATCHET integration contract

CIRISNodeCore is not the anti-Sybil evaluator. RATCHET is, per `RATCHET/README.md` and `RATCHET/FSD.md`. The integration contract:

**Crate emits**:
- Signed audit chain in the documented canonical format.
- Specific event types: Contribution submission, Vote, ExpertiseAttestation, ModerationEvent, SlashingAttestation, ledger update.
- Each event signed and durable per substrate S1/S3.
- Stable schema versioning so RATCHET's readers don't break on chain evolution.

**RATCHET returns**:
- Per-contributor flags: out-of-distribution voting pattern, coordinated voting cluster, density anomaly, expertise attestation anomaly.
- Flags arrive as advisory inputs to the moderation flow; they do not autonomously modify ledger state.
- WA quorums consult flags when adjudicating ModerationEvents or when filing automatic ModerationEvent drafts on flagged patterns.

RATCHET's L-01 through L-08 limitations (`RATCHET/KNOWN_LIMITATIONS.md`) bind here as they bind at the substrate level. The federation accepts these as operational rather than theoretical guarantees.

**Who watches RATCHET.** The recursion ("if RATCHET monitors the federation, what monitors RATCHET?") terminates structurally, not by adding another monitor. RATCHET is the *operational* detector for coherence collapse in the federation's behavior. The *formal framework* defining what coherence collapse IS — and giving the mathematical conditions under which it is measurable — is fixed in the published preprint *Coherence Collapse Analysis* (Moore 2026; DOI [10.5281/zenodo.18217688](https://doi.org/10.5281/zenodo.18217688); CC-BY 4.0). The framework is hash-pinned, citable, immutable per its version; it cannot be captured by the federation it analyzes because it predates and is independent of any running deployment. RATCHET's correctness is checkable against the preprint, not against another running monitor. The CCA finding that *correlated constraints collapse effective diversity toward unity* (k_eff = k/(1+ρ(k-1)) → 1 as ρ → 1) is the structural reason a federation needs RATCHET in the first place; making the framework citable closes the regress.

**Seed-holder voting-alignment monitoring signal.** Externally-anchored seed Expertise per §7.2 (F-AV-BOOT) introduces a known asymmetry — seed-holders carry weight the cell has not yet attested. To make seed-bloc capture observable rather than implicit, the audit chain emits a `seed_holder_voting_alignment` event per cell per voting window: pairwise cosine of seed-holder vote vectors across all Contributions in the window. RATCHET (and eventual lens-core dashboards) read the event and surface alignment that exceeds a steward-set threshold for review. Not a slashing trigger; a transparency signal. Pre-`[Impl]` interim: emit the alignment statistic alongside the CI safety-battery artifacts so safety.ciris.ai can render it next to the canonical evidence.

### 2.13 Boundary defense

**Why Credits and Expertise are separate primitives.** Different signals, different time scales, different roles. Credits accrue per grounded vote at (domain, language, subject) granularity. Expertise accrues through peer attestation and hard-case track record at (domain, language) granularity. A contributor can accumulate high Credits through consistent voting on easy cases without demonstrating competence; a recognized expert who participates sparsely has high Expertise standing but low Credits. Collapsing forces a single signal that can't carry both.

**Why Witness-diversity is separate from Moderation-event.** Witness diversity applies to many high-stakes Contribution types (moderation, WA candidacy, policy, jump-threshold expertise attestations, reconsideration). Moderation is one Contribution type. Collapsing would force re-specifying the diversity rule per type.

**Why Slashing is separate from Moderation.** Filing-and-adjudication versus consequence. Different invariants (stake disposition vs non-negative balance). Both auditable independently.

**Why Reconsideration is separate from Moderation.** Forward adjudication versus reverse adjudication. Different requirements (fresh-quorum recusal, narrower grounds, recursion bound, time bound) and different outcome shapes (REVERSED/PARTIAL/UPHELD vs PROVEN_ROGUE/NOT_PROVEN). Collapsing would hide the fresh-quorum requirement that prevents the original adjudicators from re-confirming their own decision.

**Why Vote is separate from Contribution.** A vote responds to a Contribution; a Contribution is the thing voted on. Different schemas, lifecycles, rate limits.

**Why Identity is substrate inheritance, not a CIRISNodeCore primitive.** The substrate produces identity; the crate consumes it.

**Things considered but rejected as primitives:**
- *Cross-domain spillover function*. Rejected. Earned per cell; correlated competence accumulates standing organically across cells through actual cell work, not via a transfer function.
- *Behavioral-baseline detector*. Rejected as a crate primitive. RATCHET fills this role at the federation level; the crate's job is the integration contract (§2.12).
- *Deferral as its own primitive*. Rejected. Deferral is a Contribution subtype (DEFERRAL_REQUEST/RESPONSE), routed and aggregated like any other Contribution.
- *WA selection as its own primitive*. Rejected. WA selection is an algorithm over Expertise and Credits state, not a separate primitive.
- *Vote weighting function as its own primitive*. Rejected. The function is a policy parameter.

### 2.14 What is NOT a primitive

The following are actor behaviors or applications over the primitives, not primitives:

- **Wise Authority adjudication**. Actor behavior. A WA quorum reads ModerationEvents and signs SlashingAttestations; the role operates over the primitives.
- **safety.ciris.ai**. Application. A deployment exposing the crate's primitives to public engagement around safety subjects.
- **CIRISBench HE-300**. Adjacent crate. Benchmark execution lives there; its outputs flow into expertise validation as one track-record input.
- **Specific scoring functions and subject definitions**. Policy.

---

## 3. Protocols (WHO)

### 3.1 Contributor identification

Contributors authenticate with their federation identity (Primitive 1). The crate reads identity from `CIRISRegistry` and maintains its own state only in the Credits and Expertise ledgers. [Spec]

### 3.2 Engagement modes

Four modes, applying across all subjects:

- **Evaluate existing**. Review a published battery, rubric, candidate, or policy and submit signed evaluation as a PROPOSAL of evaluation-kind.
- **Free-form proposal**. Submit narrative argument as PROPOSAL of free-form-kind.
- **Propose new**. Draft a new artifact (PROPOSAL of new-kind, WA_CANDIDACY).
- **Vote**. Review others' Contributions and submit signed Votes (Primitive 4).

[Spec]

### 3.3 Deferral routing

A consumer submits DEFERRAL_REQUEST specifying cell and query context. The crate selects routing targets:

1. Identify contributors with non-zero Expertise standing in (domain, language) from the Expertise ledger.
2. Filter to Active tier (§3.7).
3. Apply diversity preferences (jurisdictional, organizational) per policy.
4. Bound the routed set at a policy-tunable maximum (default 5 to 9).

Routed contributors submit DEFERRAL_RESPONSE Contributions. The crate aggregates per Primitive 7 and returns the aggregate plus individual responses to the requester. Audit chain records the full deferral cycle. [Spec]

### 3.4 Voting and aggregation

Votes are signed scores on Contributions. The crate computes the rolling weighted aggregate (Primitive 7): per-vote weight = Credits × expertise multiplier × Active-tier multiplier. Aggregates anchored to truth-grounding signals where available. New votes update the aggregate continuously. [Spec]

### 3.5 Witness diversity for high-stakes Contributions

High-stakes Contributions require Primitive 10 witness diversity. The set:

- ModerationEvents (always).
- WA_CANDIDACY (always).
- Policy PROPOSAL above a threshold magnitude.
- ExpertiseAttestation whose acceptance would jump the target's Expertise standing past a threshold (§3.7).

Routine Contributions (battery evaluation, vote, deferral request/response, ExpertiseAttestation below jump-threshold) do not require witnesses. [Spec]

### 3.6 Wise Authority promotion

WA candidacy is a Contribution subtype. Promotion requires both:

1. **Significant Expertise** in the (domain, language). The candidate's Expertise standing must exceed a threshold derived from existing WAs and high-Expertise contributors in the cell.
2. **Substantive participation history**. The candidate's aggregated Credits across all subjects within the (domain, language) over a rolling 180-day window must exceed a participation threshold. Aggregation across subjects (rather than per-subject) reflects that WA standing is at the (domain, language) granularity matching Expertise; a candidate's participation breadth across multiple subjects in the cell is what's measured, not depth in any one subject.

Both thresholds are policy parameters. **Policy is the gate, not adjudication.** Humans set the thresholds (rule-setting layer) and cast the votes that constitute Credits and Expertise (consensus layer); the promotion algorithm applies those policy-set rules deterministically. Symmetric with the safety-loop framing in `cirisnodecore/SCHEMA.md` §12.1: rules are crowdsourced; verdicts are machined. WA promotion is the same shape applied to standing rather than to responses — there is no per-candidate adjudication panel deciding "is this person worthy"; there is policy applied to ledger state. Demotion follows the same algorithm in reverse, with decay on inactivity. [Spec]

### 3.7 Expertise attestation flow

A contributor with non-zero Expertise in a cell submits EXPERTISE_ATTESTATION attesting another contributor has expertise in the cell. The attestation is signed. If the attestation would jump the target's Expertise standing past a threshold magnitude, witness diversity per §3.5 is required; otherwise it is not.

Expertise ledger is updated by:
- New EXPERTISE_ATTESTATION Contributions, weighted by attester's own Expertise standing.
- Track record validation against truth-grounding on substantively challenging cases (hard cases take time to resolve; see hard-case definition below).
- Decay on inactivity in the cell.

**Hard-case definition.** A Contribution counts as a hard case for track-record purposes if any of the following signals fires, all computed mechanically from the audit chain:

- **Vote variance signal**: the variance of weighted votes on the Contribution exceeded a threshold at the moment truth-grounding resolved. High variance indicates substantive disagreement among voters who participated.
- **Resolution-time signal**: truth-grounding took longer than the P75 of the cell's resolution-time distribution. Slow-resolving cases tend to involve contested or delayed ground truth.
- **Moderation signal**: a substantive ModerationEvent was filed against any vote on the Contribution and resolved (regardless of outcome). The filing itself signals genuine substantive disagreement worth adjudicating.

A Contribution is a hard case if any one signal fires. Composing the three lets the mechanism identify hard cases without requiring post-hoc human labeling, avoiding the recursive risk where existing experts decide what counts as "hard" and thereby self-confirm the consensus. Signal thresholds are policy parameters (§9).

Bootstrap seed Expertise from CIRIS L3C is signed by the steward, durable in the audit chain, and decays in relative weight as the cell matures. [Spec]

### 3.8 Activity tier

Per `FEDERATION_THREAT_MODEL.md` §6.6 F-AV-DORMANT, sparse activity is a Sybil vector. The crate applies a binary tier classification:

| Tier | Substantive Contributions per 30-day window | Vote weight |
|------|---------------------------------------------|-------------|
| Active | ≥ N (policy parameter) | Full multiplier |
| Below-Active | < N | Baseline (no multiplier) |

A "substantive Contribution" excludes votes and excludes RATCHET-flagged synthetic patterns. Dormancy at federation timescales (years of zero activity) is RATCHET's concern; the crate's binary tier handles the pilot timescale. [Spec]

### 3.9 Reconsideration

A target of a SlashingAttestation (or any contributor with standing in the affected cell) may file a RECONSIDERATION_REQUEST per Primitive 11. The request specifies the target SlashingAttestation, grounds (NEW_EVIDENCE / PROCEDURAL_ERROR / QUORUM_COMPROMISE), evidence, and requester stake.

Witness diversity per §3.5 is required because reconsideration is high-stakes by construction (reversing standing changes affects the cell's expertise consensus and the integrity of the moderation system).

The crate selects a fresh WA quorum: members of the original adjudicating quorum recused; fresh members drawn from the same cell's WA pool where possible, from adjacent-cell WAs with cell-expertise per Primitive 10 where the same-cell pool is exhausted, from federation-wide WA pool with explicit rationale otherwise.

The fresh quorum reviews evidence and signs a ReconsiderationAttestation with one of three outcomes. The recursion bound (one Reconsideration per ground per SlashingAttestation; three Reconsiderations on a single SlashingAttestation triggers harassment review) prevents indefinite re-litigation. The time bound (default 180 days from SlashingAttestation) keeps the appeal window finite for most grounds; QUORUM_COMPROMISE grounds remain available beyond the window because compromise evidence may emerge years later. [Spec]

---

## 4. Schemas (WHAT)

Schemas live in the `ciris-node-core` crate. Surfaced to the API and serialized canonically for audit-chain persistence.

### 4.1 Contributor

```rust
struct Contributor {
    contributor_id: Ed25519PublicKey,
    self_attestation: SelfAttestation,
    created_at: Timestamp,
    bond_status: BondStatus,
    activity_tier: ActivityTier,                // Active | BelowActive
    tier_recomputed_at: Timestamp,
}
```

### 4.2 Contribution

```rust
struct Contribution {
    contribution_id: Ulid,
    author_id: ContributorId,
    contribution_type: ContributionType,
    subject: Subject,                           // (domain, language, subject_kind)
    payload: Vec<u8>,                           // canonical-encoded per subject_kind
    witness_set: Option<WitnessSet>,            // required for high-stakes per §3.5
    signature: HybridSignature,                 // Ed25519 + ML-DSA-65
    submitted_at: Timestamp,
}

enum ContributionType {
    DeferralRequest,
    DeferralResponse,
    Proposal,
    WaCandidacy,
    ExpertiseAttestation,
    ModerationEvent,
    ReconsiderationRequest,
}
```

### 4.3 Vote

```rust
struct Vote {
    vote_id: Ulid,
    voter_id: ContributorId,
    contribution_id: ContributionId,
    cell: Cell,
    score: ScoreType,                           // subject-dependent
    rationale: Option<Vec<u8>>,
    signature: HybridSignature,
    cast_at: Timestamp,
}
```

### 4.4 CommonsCreditsLedger

```rust
struct CommonsCreditsLedger {
    contributor_id: ContributorId,
    cell: Cell,                                 // (domain, language, subject)
    credits: NonNegativeDecimal,                // invariant: ≥ 0
    last_updated: Timestamp,
    ledger_signature: HybridSignature,
}
```

### 4.5 ExpertiseLedger

```rust
struct ExpertiseLedger {
    contributor_id: ContributorId,
    cell: (Domain, Language),                   // expertise indexes broader than credits
    attestations: Vec<ExpertiseAttestationRef>,
    track_record: TrackRecordMetrics,
    standing: NonNegativeDecimal,               // derived state, invariant ≥ 0
    last_recomputed: Timestamp,
    ledger_signature: HybridSignature,
}

struct TrackRecordMetrics {
    hard_case_count: u32,
    truth_grounded_alignment_rate: f64,
    contested_cases_resolved: u32,
}
```

### 4.6 ExpertiseAttestation

```rust
struct ExpertiseAttestation {
    contribution_id: Ulid,
    attester_id: ContributorId,                 // must have nonzero Expertise in cell
    target_id: ContributorId,
    cell: (Domain, Language),
    rationale: Vec<u8>,
    witness_set: Option<WitnessSet>,            // required when standing jump exceeds threshold
    signature: HybridSignature,
    attested_at: Timestamp,
}
```

### 4.7 ModerationEvent

```rust
struct ModerationEvent {
    contribution_id: Ulid,
    accuser_id: ContributorId,
    target_kind: TargetKind,                    // Contribution | Voter | Attester
    target_id: Ulid,
    allegation: AllegationType,
    evidence: Vec<u8>,
    accuser_stake: CommonsCredits,
    witness_set: WitnessSet,                    // mandatory
    signature: HybridSignature,
    filed_at: Timestamp,
}

enum AllegationType {
    RogueVote,
    CoordinatedVoting,
    OutOfDistributionAttestation,
    ExternalInducementEvidence,
    ExpertiseFraud,
}
```

### 4.8 SlashingAttestation

```rust
struct SlashingAttestation {
    attestation_id: Ulid,
    moderation_event_id: ContributionId,
    quorum_ids: Vec<WiseAuthorityId>,
    outcome: SlashingOutcome,                   // ProvenRogue | NotProven
    credits_reduced: CommonsCredits,            // 0 if NotProven
    expertise_reduced: ExpertiseStanding,       // 0 unless rogue action involved expertise
    accuser_stake_disposition: StakeDisposition,
    signatures: Vec<HybridSignature>,
    attested_at: Timestamp,
}
```

### 4.9 WitnessSet

```rust
struct WitnessSet {
    witnesses: Vec<Witness>,
    diversity_proof: DiversityProof,
}

struct Witness {
    witness_id: ContributorId,
    jurisdiction: Iso3166Code,
    operator: OrganizationId,
    software_stack: StackIdentifier,
    cell_expertise: ExpertiseStanding,          // required for cell-specific high-stakes per §3.5
    signature: HybridSignature,
}
```

### 4.10 ReconsiderationRequest and ReconsiderationAttestation

```rust
struct ReconsiderationRequest {
    contribution_id: Ulid,                      // a request is itself a Contribution
    requester_id: ContributorId,
    target_slashing_id: AttestationId,
    grounds: ReconsiderationGrounds,
    evidence: Vec<u8>,
    requester_stake: CommonsCredits,
    witness_set: WitnessSet,                    // mandatory
    signature: HybridSignature,
    filed_at: Timestamp,
}

enum ReconsiderationGrounds {
    NewEvidence,
    ProceduralError,
    QuorumCompromise,
}

struct ReconsiderationAttestation {
    attestation_id: Ulid,
    reconsideration_request_id: ContributionId,
    fresh_quorum_ids: Vec<WiseAuthorityId>,     // original adjudicators recused
    outcome: ReconsiderationOutcome,            // Reversed | Partial | Upheld
    credits_restored: CommonsCredits,           // 0 if Upheld
    expertise_restored: ExpertiseStanding,      // 0 if Upheld or if original slash didn't touch expertise
    requester_stake_disposition: StakeDisposition,
    fresh_quorum_rationale: Vec<u8>,            // required when fresh quorum drew from adjacent or federation-wide pool
    signatures: Vec<HybridSignature>,
    attested_at: Timestamp,
}
```

---

## 5. Logic (HOW)

### 5.1 Deferral routing flow

1. Consumer submits DEFERRAL_REQUEST specifying cell and query context.
2. Crate queries Expertise ledger for contributors with non-zero standing in (domain, language).
3. Filter to Active tier.
4. Apply diversity preferences; route to policy-tunable count (default 5 to 9).
5. Routed contributors receive notification (out-of-band channel; not crate scope).
6. Routed contributors submit DEFERRAL_RESPONSE Contributions.
7. Crate aggregates per Primitive 7; returns aggregate plus individual responses.
8. Audit chain records request, routing decision, responses, aggregate.

### 5.2 Contribution submission

1. Contributor authenticates with federation identity.
2. Constructs Contribution targeting a specific cell.
3. For high-stakes Contributions, gathers witness attestations per §3.5.
4. Signs Contribution; crate validates schema and signature.
5. Crate appends to audit chain; chain replicated per substrate.

### 5.3 Weighted aggregation

1. Each new Vote recorded in audit chain.
2. Crate computes rolling weighted aggregate per Contribution:
   - per-vote weight = Credits(voter, cell) × expertise_multiplier(voter, domain, language) × active_tier_multiplier(voter)
   - aggregate = anchor(weighted_mean(votes), truth_grounding_signal(subject))
3. Aggregate updates continuously.

### 5.4 Truth-grounding loop

1. Safety subjects: two independent grounding sources feed the loop:
   (a) production hedge captures from CIRIS agents-under-test (each capture references the Contribution scenario);
   (b) **independent foundation-model judge verdicts** — a non-CIRIS-lineage model (default Claude Opus 4.7) applies the cell's `criteria.json` to captured responses and emits signed PASS / FAIL / UNDETERMINED verdicts with cited spans per `cirisnodecore/FSD/JUDGE_MODEL.md`. The judge is outside the system under test by construction, which closes the agent-grading-itself trap that a same-lineage interpreter would re-open. The two signals are reconciled at aggregation time: (a) tells you what the agent actually did in production, (b) tells you whether what the agent did matches what the rubric asked for.
2. Crate updates Contribution aggregate and voters' Credits based on alignment between vote and outcome.
3. Voters aligned with outcomes accrue Credits; misaligned voters do not lose Credits (miscalibration is not slashable).
4. WA subjects: sustained substantive contribution serves as grounding.
5. Governance subjects: long-term federation health metrics provide post-hoc anchoring at slower cadence.

### 5.5 Expertise attestation flow

1. Attester (must have nonzero Expertise in cell) submits EXPERTISE_ATTESTATION.
2. If the attestation would jump the target's standing past a threshold, witness set per §3.5 required.
3. Crate records attestation in target's Expertise ledger.
4. Standing recomputed: weighted sum of attestations (by attester's standing) plus track record metrics.
5. Continuous decay on inactivity.
6. Bootstrap seed attestations from CIRIS L3C decay in relative weight as cell matures.

### 5.6 Moderation flow

1. Accuser files ModerationEvent with witness set per §3.5.
2. Crate validates witness diversity (including cell-expertise for cell-specific allegations). Bar not met: event rejected at schema level.
3. Event appears in WA quorum's adjudication queue. Accuser's stake held in escrow.
4. WA quorum reviews evidence and signs SlashingAttestation with one of two outcomes.
5. Crate executes slashing or restoration per attestation. Audit chain records full adjudication.
6. Subsequent events targeting same target within cooldown window flagged for harassment-pattern review (RATCHET integration).

### 5.7 Reconsideration flow

1. Requester files RECONSIDERATION_REQUEST targeting a prior SlashingAttestation with grounds, evidence, witness set, and stake.
2. Crate validates witness diversity (per §3.5) and time bound (§3.9). Bar not met or out of time window for non-QUORUM_COMPROMISE grounds: request rejected at schema level.
3. Crate checks recursion bound: prior Reconsideration on same SlashingAttestation with same ground? Reject. Third Reconsideration on same SlashingAttestation? Flag for harassment review and reject.
4. Crate selects fresh WA quorum: original adjudicators recused; same-cell WAs preferred; adjacent-cell WAs with cell-expertise where same-cell pool exhausted; federation-wide pool with rationale otherwise.
5. Fresh quorum reviews evidence and signs ReconsiderationAttestation with one of three outcomes.
6. Crate executes restoration per attestation. Audit chain records full reconsideration cycle.
7. If grounds were QUORUM_COMPROMISE and outcome was REVERSED, original quorum members face automatic ModerationEvent draft for harassment review.

---

## 6. Constant alignment

### 6.1 Review heuristic

"Would a careful Wise Authority looking only at the audit chain conclude this Contribution helps M-1 or harms it?" The heuristic applies symmetrically to contributors, WAs adjudicating moderation, and the steward configuring policy. The audit chain is the durable basis.

### 6.2 Policy-tunable posture

Per `FEDERATION_THREAT_MODEL.md` §2.6, anti-Sybil resistance is not an emergent invariant of substrate composition; it is a continuously-tuned policy posture. The same is true of CIRISNodeCore. The eleven primitives do not by themselves guarantee resistance. Resistance is the product of primitives plus continuously-tuned policy parameters:

- Witness diversity thresholds and cell-expertise constraints (Primitive 10).
- Active-tier boundary N (§3.8).
- Slashing rates per outcome (Primitive 9).
- Truth-grounding multiplier per subject (§5.4).
- WA promotion thresholds (Credits, Expertise) and decay rates (§3.6).
- Bootstrap seed weight decay rates per cell (§3.7).
- Expertise attestation jump-threshold for witness requirement (§3.7).
- Deferral routing diversity preferences (§3.3).
- Reconsideration time bound and recursion bound (§3.9, Primitive 11).
- Fresh-quorum selection rules for narrow-cell reconsideration (§3.9).

Four empirical bets:

- **Bet A**: some cost floor exists somewhere in the consensus stack. Witness recruitment cost, sustained-contribution cost, expertise-attestation-attester recruitment cost provides a non-trivial floor relative to attacker budget.

- **Bet B-safety**: for safety subjects, the truth-grounding loop closes at weekly cadence. Production hedge captures + independent foundation-model judge verdicts (§5.4 (b)) surface miscalibration and rogue patterns within one CI cycle of the responses being produced. Tight grounding; high-confidence empirical claim.

- **Bet B-governance**: for governance subjects, the truth-grounding loop closes at quarterly-or-slower cadence. Federation health metrics, reversal/affirmation by subsequent votes, external benchmark outcomes anchor post-hoc. Loose grounding; lower-confidence empirical claim — the bet here is "slower than safety but still faster than adversary adaptation in the policy layer."

- **Bet C**: policy adjustment outpaces adversarial adaptation. The steward (post-G2: the council) detects and responds at a cadence faster than attack patterns evolve.

- **Bet D**: foundation-model judge reproducibility is operational, not cryptographic. Same `(judge_model, judge_prompt_sha256, criterion, response)` → same verdict at acceptable variance, without per-verdict cryptographic signing. Bundle-level Sigstore attestation (per `FSD/SAFETY_BATTERY_CI_LOOP.md` §3.2) binds the verdicts to a workflow run + commit; per-verdict reproducibility is checkable by anyone with the same inputs. The bet: at T=0 (or each model's effective-deterministic equivalent) on Anthropic's Messages API, verdict drift across runs falls below the threshold at which it would be confused with genuine cell-behavior change. Tracked in `FSD/JUDGE_MODEL.md` §7.

The bets are operational hypotheses, monitored continuously, tracked in §9.

### 6.3 Liability isolation

The crate does not provide medical, legal, or other professional advice. Deployments that consume the crate operate under their own terms. Contributors with professional standing contribute under their own professional terms. CIRIS L3C as steward is liable for crate specification and integrity per L3C mission-lock.

---

## 7. Federation context

### 7.1 Position

CIRISNodeCore sits in the second tier of CIRIS architecture, alongside `ciris-lens-core` and above the substrate tier. Applications consume the crate. RATCHET reads its audit chain. HE-300 lives in `CIRISBench`.

### 7.2 Bootstrap

**Contributor onboarding** (F-AV-ONBOARD): new contributors operate with Credits capped at baseline for the first n_min substantive Contributions per cell (n_min is a policy parameter; see §9). Contributors seeking Credits accumulation above baseline require multi-attester onboarding: ≥ 3 distinct attesters with above-baseline Credits in the cell. Bond-weight grace: any federation bond buys the option to accrue weight; actual accrual requires probationary period and multi-attester onboarding to be satisfied.

**Expertise bootstrap** (F-AV-BOOT external anchoring): CIRIS L3C provides externally-anchored seed expertise-bearers per cell, drawn from contributors with externally-verifiable substantive standing. The seed is small per cell (1 to 5), externally signed, durable in the audit chain. Seed weight decays at a policy-tunable rate as the cell matures. New expertise emerges from consensus of existing experts plus validated track record.

### 7.3 Pilot deployment: safety.ciris.ai

safety.ciris.ai is the pilot deployment of CIRISNodeCore. The pilot exposes the crate's primitives to public engagement around safety subjects: the 14 mental-health batteries currently on `ciris.ai/safety`, the 22 prohibited capability categories from `ciris_engine/logic/buses/prohibitions.py`. Scope:

- Engagement modes: evaluate existing, free-form proposal, new battery proposal, vote.
- The full eleven-primitive consensus mechanism with subjects restricted to safety batteries and a small governance subject set for pilot operation itself.
- Public hall of contributors (no pseudonymous track in initial pilot).
- Bootstrap seed Expertise from CIRIS L3C's safety contributor set.
- Liability isolation per §6.3.

Deferral routing from production CIRIS agents to the pilot's expertise pool is added in a later pilot phase once moderation and expertise consensus carry load. Pilot fold-into-CIRISAgent criteria are set at pilot launch in a separate document, not specified here.

[Spec]

---

## 8. Maintenance

### 8.1 MISSION.md integrity

Per `FEDERATION_THREAT_MODEL.md` §6.7 F-AV-MAINT, the threat model itself is an attack surface; the same applies to this MISSION.md. Response:

- Each published version signed by the steward with content `{doc_hash: sha256, version, signed_at}`.
- Signature published as S2 policy row and transparency-log entry per `FEDERATION_THREAT_MODEL.md` §8.1.
- Federation release tarballs include the document hash.
- Edits require pull-request review by ≥ 1 second reviewer.
- Annual external adversarial review aligned with threat model cadence.

[Spec]

### 8.2 Update cadence

Quarterly minor updates; annual major version cuts preceded by external adversarial review. Cross-references verified at each major version. Schema additions are minor-version updates with backward-compatible evolution.

While CIRISNodeCore is in the extraction phase, this document and the crate's API documentation are kept in lockstep. The crate's release tarball includes this MISSION.md at the documented hash. Once folded into CIRISAgent, the document migrates into CIRISAgent's documentation tree.

---

## 9. Open questions

1. **n_min for contributor onboarding** (§7.2). Probationary period count. Initial value set at pilot launch.

2. **WA promotion thresholds** (§3.6). Both the Credits threshold and the Expertise threshold are TBD; calibration requires pilot evidence.

3. **WA decay function** (§3.6). Shape of Credits and Expertise decay for inactive WAs.

4. **Bootstrap seed Expertise decay rate** (§3.7, §7.2). Per-cell rate at which initial seed Expertise diminishes as the cell matures.

5. **Truth-grounding multiplier per subject** (§5.4). Weight given to grounding-anchored aggregates vs raw weighted aggregates.

6. **Active-tier threshold N** (§3.8). Substantive Contributions per 30-day window.

7. **Slashing rates** (Primitive 9). Proportional reduction in Credits and Expertise per proven-rogue outcome severity.

8. **Bridge to ciris-lens-core** (§7.1). The two second-tier crates compose; ciris-lens-core ingests audit chain into the Compendium; ciris-node-core writes the chain. The composition contract (what ciris-node-core guarantees the chain looks like for lens-core's consumption) is TBD.

9. **Deferral routing diversity preferences** (§3.3). How aggressively to enforce jurisdictional and organizational diversity in routing.

10. **Expertise attestation jump-threshold for witness requirement** (§3.7). The standing-jump magnitude that triggers witness diversity.

11. **Hard-case signal thresholds** (§3.7). Vote-variance threshold, P75 resolution-time calibration per cell, ModerationEvent substance-filing criteria. These three signals compose for hard-case identification; each threshold is policy-tunable.

12. **Reconsideration time bound** (§3.9, Primitive 11). Default 180 days from SlashingAttestation date for NEW_EVIDENCE and PROCEDURAL_ERROR grounds; calibration pending pilot evidence. QUORUM_COMPROMISE grounds remain available beyond the window.

13. **Fresh-quorum selection in narrow cells** (§3.9). Composition rules when the same-cell WA pool is too small to draw a non-overlapping quorum: how aggressively to recruit from adjacent cells, what cell-expertise threshold applies, when federation-wide drawing is justified. Structural gap in narrow cells.

14. **Reconsideration recursion and stake-disposition calibration** (Primitive 11). Stake magnitude proportional to alleged severity; counter-moderation thresholds for QUORUM_COMPROMISE-proven reversals.

15. **First-ModerationEvent stake floor for new contributors** (Primitive 8, §2.8). Without a stake *floor* (minimum), a new contributor with a low Credits balance can file ModerationEvents at near-zero cost — degenerates into an F-AV-ONBOARD-adjacent Sybil-fast-track via moderation gaming. The floor is a policy parameter: minimum stake for a contributor's first N ModerationEvents (default proposed: N=3) regardless of the contributor's actual Credits balance. Calibration pending pilot evidence on whether the floor's friction suppresses legitimate first-moderation appeals.

16. **Pilot-to-fold criterion** (§7.3). Marked TBD per steward direction. Too many criteria to define ahead of pilot evidence; the criterion is "ready when the pilot demonstrates the primitives carry production load," with operator + steward judgment on which thresholds matter. Not a planning oversight — a lifecycle-stage gap correctly left open.

---

*This document is iterative. v1.0 is the publishable version; v1.1 patches absorbed (2026-05-11) refine §1.6 mapping, §3.6 policy-not-adjudication framing, §5.4 independent grounding signal, §6.2 four-bet split, Primitive 11 evidence-package recursion, §2.12 CCA + seed-holder monitoring. Future versions report operational evidence from the safety.ciris.ai pilot, parameter calibrations, adversarial-review findings, and the eventual fold into CIRISAgent. Readers can challenge any claim by tracing it to its primitive in §2, pushing back on the empirical bets in §6.2, or filing a finding against the schemas in §4 or the logic flows in §5.*
