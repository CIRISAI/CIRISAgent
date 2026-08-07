package ai.ciris.mobile.shared.models.federation

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * The HUMANITY_ACCORD server surface — the constitutional safe-mesh floor
 * (CIRISServer #41, src/accord.rs). The accord is a small roster of
 * hardware-attested holders who jointly hold a `quorum:2/3` kill-switch over
 * constitutional invocations (CC 4.2.1). The app drives the LOCAL node only with
 * the owner session — it holds NO keys and does NO crypto; the server signs.
 *
 * Sources:
 *   - family    : ``GET /v1/accord/family``
 *   - holders   : ``GET /v1/accord-holders``
 *   - invocations: ``GET /v1/accord/invocations``
 *   - concur    : ``POST /v1/accord/invocation/concur`` (owner-gated)
 */

/** One member of the accord family roster. */
@Serializable
data class AccordFamilyMemberDto(
    @SerialName("key_id")
    val keyId: String,
    /** Optional role label (e.g. ``founder``), or null. */
    val role: String? = null,
)

/**
 * The accord family — the entrenched constitutional roster + its consensus
 * protocol. ``GET /v1/accord/family`` (404 / empty when no accord family yet).
 */
@Serializable
data class AccordFamilyDto(
    @SerialName("family_key_id")
    val familyKeyId: String,
    @SerialName("family_name")
    val familyName: String,
    /** The consensus protocol — e.g. ``quorum:2/3``. */
    @SerialName("consensus_protocol")
    val consensusProtocol: String,
    /** Whether the accord is entrenched (constitutionally fixed). */
    val entrenched: Boolean = false,
    val members: List<AccordFamilyMemberDto> = emptyList(),
)

/**
 * One accord holder in the registry — a key that may concur on invocations. The
 * holder is FIPS / hardware-attested; the app never sees private material, only
 * the published public keys. ``GET /v1/accord-holders``.
 */
@Serializable
data class AccordHolderDto(
    @SerialName("key_id")
    val keyId: String,
    @SerialName("pubkey_ed25519_base64")
    val pubkeyEd25519Base64: String,
    @SerialName("pubkey_ml_dsa_65_base64")
    val pubkeyMlDsa65Base64: String? = null,
)

/** ``GET /v1/accord-holders`` response. */
@Serializable
data class AccordHoldersResponse(
    /** The accord's m-of-n threshold as served. **0 = unknown**, never guessed. */
    val threshold: Int = 0,
    @SerialName("holder_count")
    val holderCount: Int = 0,
    val holders: List<AccordHolderDto> = emptyList(),
)

/**
 * One pending (or settled) accord invocation. The [invocationKind] drives a
 * MANDATED distinct visual treatment per CC 4.2.1:
 *   - ``CONSTITUTIONAL`` — strong / emergency (the kill-switch)
 *   - ``notify``         — neutral informational
 *   - ``drill``          — muted / test
 *
 * ``GET /v1/accord/invocations``.
 */
@Serializable
data class AccordInvocationDto(
    @SerialName("invocation_kind")
    val invocationKind: String,
    @SerialName("invocation_id")
    val invocationId: String,
    @SerialName("quorum_met")
    val quorumMet: Boolean = false,
    /** The holder key_ids that have validly signed this invocation. */
    @SerialName("valid_signers")
    val validSigners: List<String> = emptyList(),
    @SerialName("quorum_threshold")
    /**
     * The m-of-n threshold as reported by the substrate. **0 = unknown** — never
     * defaulted to a literal: the accord's threshold is governance state, and a
     * guessed number in a quorum badge misreports how many humans an operation
     * actually needs.
     */
    val quorumThreshold: Int = 0,
    /** The holder key_ids on the roster for this invocation. */
    @SerialName("roster_member_ids")
    val rosterMemberIds: List<String> = emptyList(),
)

/** ``GET /v1/accord/invocations`` response. */
@Serializable
data class AccordInvocationsResponse(
    val invocations: List<AccordInvocationDto> = emptyList(),
)

/**
 * One surfaced NON-BINDING accord event (CIRISServer#41 §9.2.1) — a completed
 * **drill** (a rehearsed exercise of the 2-of-3 kill-switch delivery path) or an
 * **announce** (a single-holder ``notify``). Recorded the moment it is observed
 * quorum-COMPLETE (locally OR via gossip); a sub-quorum invocation is never here.
 * Neither ever halts. ``GET /v1/accord/events``.
 */
@Serializable
data class AccordEventDto(
    /** ``drill`` or ``announce``. */
    @SerialName("event_type")
    val eventType: String,
    @SerialName("invocation_id")
    val invocationId: String,
    /** RFC-3339 instant this node recorded the completed event. */
    @SerialName("recorded_at")
    val recordedAt: String,
    /** The holder key_ids counted — the quorum-meeting seats (drill) or the single
     * signer (announce). */
    val signers: List<String> = emptyList(),
    @SerialName("quorum_threshold")
    /**
     * The m-of-n threshold as reported by the substrate. **0 = unknown** — never
     * defaulted to a literal: the accord's threshold is governance state, and a
     * guessed number in a quorum badge misreports how many humans an operation
     * actually needs.
     */
    val quorumThreshold: Int = 0,
    /** Announce ONLY — the free-text message (bound to the signed payload), or null. */
    val message: String? = null,
)

/** ``GET /v1/accord/events`` response — completed drills + announcements, each
 * most-recent-first. */
@Serializable
data class AccordEventsResponse(
    val drills: List<AccordEventDto> = emptyList(),
    val announcements: List<AccordEventDto> = emptyList(),
)

/** The disk halt-latch record, when the node is halted (who/when/which invocation). */
@Serializable
data class AccordHaltRecordDto(
    @SerialName("invocation_kind")
    val invocationKind: String? = null,
    @SerialName("invocation_id")
    val invocationId: String? = null,
    @SerialName("valid_signers")
    val validSigners: List<String> = emptyList(),
    @SerialName("quorum_threshold")
    /**
     * The m-of-n threshold as reported by the substrate. **0 = unknown** — never
     * defaulted to a literal: the accord's threshold is governance state, and a
     * guessed number in a quorum badge misreports how many humans an operation
     * actually needs.
     */
    val quorumThreshold: Int = 0,
    @SerialName("latched_at")
    val latchedAt: String? = null,
)

/**
 * ``GET /v1/accord/halt-status`` — the read-only state of the enforceable
 * kill-switch (the disk halt latch, CC 4.2.1 / 4.2.3). [halted] drives the
 * unmissable ACTIVE-HALT banner on the Trust Root card; [record] names the halting
 * invocation when present. Read-only — the app never writes or clears the latch.
 */
@Serializable
data class AccordHaltStatusResponse(
    val halted: Boolean = false,
    @SerialName("latch_path")
    val latchPath: String? = null,
    val record: AccordHaltRecordDto? = null,
)

/** ``POST /v1/accord/announce`` response — a single-holder announce was posted. */
@Serializable
data class AccordAnnounceResponse(
    val posted: Boolean = false,
    @SerialName("invocation_id")
    val invocationId: String? = null,
    val from: List<String> = emptyList(),
    val message: String? = null,
)

/** ``POST /v1/accord/invocation/concur`` response (the local holder concurred). */
@Serializable
data class AccordConcurResponse(
    @SerialName("invocation_kind")
    val invocationKind: String,
    @SerialName("invocation_id")
    val invocationId: String,
    @SerialName("quorum_met")
    val quorumMet: Boolean = false,
    @SerialName("valid_signers")
    val validSigners: List<String> = emptyList(),
)

/**
 * ``POST /v1/accord/provision-holder`` response — the two artifacts a portable
 * accord holder mints on their device (CIRISServer#41, src/accord_provision.rs).
 * The node did all the crypto from the holder's already-FIPS-approved YubiKey +
 * the chosen ML-DSA USB path; the app holds NO keys. The holder then asks the
 * node owner to register them (``POST /v1/accord/holder``).
 *
 * [holderRecord] + [custodyAttestation] are opaque signed JSON objects (the
 * verify-core ``SignedKeyRecord`` + ``SignedCegObject``); the app never inspects
 * their internals, so they ride as raw [kotlinx.serialization.json.JsonElement].
 */
@Serializable
data class AccordProvisionResponse(
    @SerialName("key_id")
    val keyId: String,
    @SerialName("holder_record")
    val holderRecord: kotlinx.serialization.json.JsonElement? = null,
    @SerialName("custody_attestation")
    val custodyAttestation: kotlinx.serialization.json.JsonElement? = null,
)

/**
 * ``POST /v1/accord/admit-node`` response (CIRISServer#140 / CIRISVerify#162) — the
 * accord holder (A1) scrub-signed a node's registration and emitted their own
 * `steward,accord_holder` anchor. Both are the **admission records**, saved to a
 * predictable outbox path (`ceg_outbox()/accord_admit_node/{target}.json`) so they
 * can travel to a REMOTE target, which adopts them on its own node. [savedTo] is
 * that path; [admissionRecords] is the object verbatim (for display / copy).
 *
 * **These are not the seed.** The seed is a `GenesisBundle` and that is the only
 * shape (`FSD/NAMING_THE_TRUST_ROOT.md`); the genesis ceremony produces it and the
 * node saves it to `<home>/mesh-genesis.json`. Through 0.5.140 this was documented
 * as "the genesis seed object … hands to CIRISPersist v12.0.2 to bake". VOCAB-HISTORY
 */
@Serializable
data class AdmitNodeResponse(
    @SerialName("saved_to")
    val savedTo: String,
    @SerialName("admission_records")
    val admissionRecords: kotlinx.serialization.json.JsonElement? = null,
)

/**
 * One bootstrap transport address baked INTO a canonical server's signed record —
 * an entry of its ``transport_hints`` (e.g. ``{kind:"ip", destination:"1.2.3.4:4242"}``).
 * The IP now rides inside the scrubbed record envelope, so it is set at mint time.
 */
@Serializable
data class TransportHintDto(
    val kind: String,
    val destination: String,
)

/**
 * One canonical server on the trust root — `GET /v1/accord/canonical/servers`
 * (CIRISServer#164). A canonical server is a node whose registration an accord
 * holder scrub-signed AND flagged `canonical` (its [identityType] is a comma-set
 * that includes `canonical`), making it a rock-solid mesh-seed anchor other
 * nodes may bootstrap-dial. [scrubKeyId] is the holder key_id that scrubbed it.
 * [transportHints] carries the addresses (e.g. the ``ip`` host:port) baked into
 * the signed record, or null when none were set.
 */
@Serializable
data class CanonicalServerDto(
    @SerialName("key_id")
    val keyId: String,
    /** Comma-set identity types (e.g. ``node,canonical``). */
    @SerialName("identity_type")
    val identityType: String,
    @SerialName("pubkey_ed25519_base64")
    val pubkeyEd25519Base64: String,
    @SerialName("pubkey_ml_dsa_65_base64")
    val pubkeyMlDsa65Base64: String? = null,
    @SerialName("scrub_key_id")
    val scrubKeyId: String? = null,
    @SerialName("valid_from")
    val validFrom: String? = null,
    /** The addresses baked into the signed record (e.g. the ``ip`` entry), or null. */
    @SerialName("transport_hints")
    val transportHints: List<TransportHintDto>? = null,
)

/** ``GET /v1/accord/canonical/servers`` response. */
@Serializable
data class CanonicalServersResponse(
    val servers: List<CanonicalServerDto> = emptyList(),
)

/**
 * ``POST /v1/accord/canonical/withdraw`` response (CIRISServer#164) — a DESTRUCTIVE
 * op that needs a 2-of-3 accord proposal (a second/third holder must co-sign); a
 * lone holder cannot complete it. [withdrawn] is true only once quorum is met.
 */
@Serializable
data class CanonicalWithdrawResponse(
    val withdrawn: Boolean = false,
    @SerialName("authority_proposal_digest")
    val authorityProposalDigest: String? = null,
)

/**
 * ``POST /v1/accord/canonical/supersede`` response — replaces a canonical record
 * with a fresh successor. Also a 2-of-3 destructive op. [successor] is the new
 * canonical key_id once quorum settles.
 */
@Serializable
data class CanonicalSupersedeResponse(
    val superseded: Boolean = false,
    val successor: String? = null,
    @SerialName("authority_proposal_digest")
    val authorityProposalDigest: String? = null,
)

/** One withdrawn / superseded canonical server — an entry of the withdrawals log. */
@Serializable
data class CanonicalWithdrawalDto(
    @SerialName("key_id")
    val keyId: String,
    @SerialName("withdrawn_at")
    val withdrawnAt: String? = null,
    @SerialName("superseded_by")
    val supersededBy: String? = null,
    @SerialName("authority_proposal_digest")
    val authorityProposalDigest: String? = null,
)

/** ``GET /v1/accord/canonical/withdrawals`` response. */
@Serializable
data class CanonicalWithdrawalsResponse(
    val withdrawals: List<CanonicalWithdrawalDto> = emptyList(),
)

/**
 * ``POST /v1/accord/canonical/add`` response (CIRISServer#164) — an accord holder
 * scrub-signed a target node's registration AND flagged it `canonical`, writing the
 * holder-signed **admission records** to a predictable outbox path
 * ([admissionRecordsPath]). 1-of-N: one holder's YubiKey + USB scrub suffices. If
 * the holder supplied a bootstrap transport the node also records the canonical
 * server's [address].
 */
@Serializable
data class AddCanonicalServerResponse(
    @SerialName("canonical_key_id")
    val canonicalKeyId: String,
    @SerialName("is_canonical")
    val isCanonical: Boolean = false,
    /** Opaque address record (transport_kind + destination) or null. */
    val address: kotlinx.serialization.json.JsonElement? = null,
    /**
     * Where the holder-signed admission records were written — the transport for a
     * REMOTE target, which adopts them on its own node.
     *
     * **NOT the seed.** The seed is a `GenesisBundle`, and that is the only shape
     * (`FSD/NAMING_THE_TRUST_ROOT.md`); a pair of key records does not parse as
     * one. The seed comes out of the genesis ceremony and the node saves it to
     * `<home>/mesh-genesis.json`. Through 0.5.140 this field was `seed_saved_to` (VOCAB-HISTORY)
     * and the UI told the operator to "hand it to persist to bake" — pre-bundle
     * v12.0.2 vocabulary, naming the wrong file at the one moment it matters.
     */
    @SerialName("admission_records_path")
    val admissionRecordsPath: String? = null,
)

// ─── Cross-device m-of-n co-scrub (CIRISServer #174 / CIRISPersist#383) ───────
//
// A canonical record is now conferred by ≥M *distinct* accord-holder scrubs across
// DEVICES. A1 `propose`s the first scrub on box-1; the 1-scrub **partial** gossips
// over the accord peer-plane to box-2 where it appears in the "Pending co-signs"
// list; B1 `cosign`s; at the family m-of-n the record is adopted / conferred. The
// signed envelope must round-trip BYTE-IDENTICAL between devices (verify's
// `append_scrub` recanonicalizes the existing bytes), so every `partial` /
// `advanced` payload rides as a raw [kotlinx.serialization.json.JsonElement] — the
// app never re-encodes it.

/**
 * One canonical co-scrub awaiting more cosignatures — an entry of
 * `GET /v1/accord/canonical/pending`. Display/UX only (the security gate stays at
 * cosign→adopt). [partial] is the full verify `SignedKeyRecord` JSON, carried
 * verbatim so [cosign] can submit it without re-encoding.
 */
@Serializable
data class PendingCoscrubDto(
    @SerialName("target_key_id")
    val targetKeyId: String,
    /** Distinct anchor scrubs on the partial so far. */
    @SerialName("distinct_scrub_count")
    val distinctScrubCount: Int = 0,
    /** The family m-of-n threshold M (0 when the node can't resolve it). */
    @SerialName("quorum_needed")
    val quorumNeeded: Int = 0,
    /** The `scrub_key_id`s present on the partial. */
    val scrubbers: List<String> = emptyList(),
    @SerialName("transport_hints")
    val transportHints: List<TransportHintDto> = emptyList(),
    /** True → every scrubber resolved to a known accord-holder roster member. */
    @SerialName("roster_verified")
    val rosterVerified: Boolean = true,
    @SerialName("received_at")
    val receivedAt: String? = null,
    /** The full `SignedKeyRecord` JSON — round-tripped verbatim into `cosign`. */
    val partial: kotlinx.serialization.json.JsonElement,
)

/** `GET /v1/accord/canonical/pending` response. */
@Serializable
data class PendingCoscrubsResponse(
    val pending: List<PendingCoscrubDto> = emptyList(),
)

/**
 * `POST /v1/accord/canonical/propose` response — the FIRST scrub of a co-scrub. A
 * 1-scrub [partial] does NOT yet confer canonical (m-of-n); it is saved to the
 * outbox and gossiped to accord peers. [partial] rides verbatim so the next holder
 * cosigns the byte-identical envelope.
 */
@Serializable
data class ProposeCanonicalResponse(
    @SerialName("target_key_id")
    val targetKeyId: String,
    @SerialName("distinct_scrub_count")
    val distinctScrubCount: Int = 0,
    val partial: kotlinx.serialization.json.JsonElement? = null,
    @SerialName("saved_to")
    val savedTo: String? = null,
    /** How many accord peers the partial was gossiped to (0 when none configured). */
    @SerialName("gossiped_to")
    val gossipedTo: Int = 0,
)

/**
 * `POST /v1/accord/canonical/cosign` response — THIS holder's scrub was appended to
 * the partial. [conferred] is true once the distinct-scrub set meets the family
 * m-of-n (the record is adopted); otherwise [advanced] is the still-partial record
 * to hand / gossip to the next holder. [advanced] rides verbatim.
 */
@Serializable
data class CosignCanonicalResponse(
    @SerialName("target_key_id")
    val targetKeyId: String,
    @SerialName("distinct_scrub_count")
    val distinctScrubCount: Int = 0,
    val conferred: Boolean = false,
    val outcome: String? = null,
    val advanced: kotlinx.serialization.json.JsonElement? = null,
    @SerialName("saved_to")
    val savedTo: String? = null,
    @SerialName("gossiped_to")
    val gossipedTo: Int = 0,
)

// ─── CI-worker batch blessing (CIRISServer ci-key/propose|cosign) ─────────────
//
// The substrate CI workers (build pipelines + the agent steward) are ONE batch of
// `infra:attest` node keys an accord holder scrub-signs in a single ceremony — the
// SAME m-of-n co-scrub as a canonical server, except (a) `targets` / `partials` ride
// as ARRAYS (batch) and (b) the roles are set `infra:attest` server-side (the client
// sends no roles). Each per-target result carries the same fields as a single
// canonical propose / cosign, so the batch responses reuse those element DTOs.

/**
 * One CI-worker target of a batch `POST /v1/accord/ci-key/propose` — the node key an
 * accord holder scrub-signs. Same fields as a canonical `target`; [identityType]
 * defaults to `node`. Built by the "Bless CI workers" card from each repo's
 * export-job artifact (the operator pastes the ed25519 + ML-DSA-65 pubkeys).
 */
@Serializable
data class CiKeyTargetInput(
    @SerialName("key_id")
    val keyId: String,
    @SerialName("pubkey_ed25519_base64")
    val pubkeyEd25519Base64: String,
    @SerialName("pubkey_ml_dsa_65_base64")
    val pubkeyMlDsa65Base64: String,
    @SerialName("identity_type")
    val identityType: String = "node",
)

/**
 * `POST /v1/accord/ci-key/propose` response — one [ProposeCanonicalResponse]-shaped
 * result per target in the batch (each `{target_key_id, distinct_scrub_count, partial,
 * saved_to, gossiped_to}`).
 */
@Serializable
data class CiKeyProposeResponse(
    val results: List<ProposeCanonicalResponse> = emptyList(),
)

/**
 * `POST /v1/accord/ci-key/cosign` response — one [CosignCanonicalResponse]-shaped
 * result per partial in the batch (each `{target_key_id, distinct_scrub_count,
 * conferred, outcome, advanced, saved_to, gossiped_to}`).
 */
@Serializable
data class CiKeyCosignResponse(
    val results: List<CosignCanonicalResponse> = emptyList(),
)

// ─── Genesis ceremony (CIRISServer #41) ──────────────────────────────────────
//
// The guided HUMANITY_ACCORD genesis ceremony stands up a NEW mesh's 2-of-3
// human kill-switch: 3 humans, each a PRIMARY seat + a cold SPARE. After all 6
// keys are provisioned + registered, the 3 primaries co-sign a family envelope
// and the node assembles the 2/3-founder-signed genesis (the cold-start bake
// artifact). The app holds NO keys — every signature comes from a re-inserted
// YubiKey via the loopback endpoints.

/**
 * ``POST /v1/accord/genesis/envelope`` response — the canonical, JCS-significant
 * family envelope the primary holders co-sign byte-for-byte. Carried verbatim;
 * the app never rebuilds it (it would break the signing bytes).
 */
@Serializable
data class GenesisEnvelopeResponse(
    val envelope: kotlinx.serialization.json.JsonElement,
)

/**
 * ``POST /v1/accord/family/cosign`` response — one primary holder's genesis
 * cosignature, produced on their re-inserted YubiKey by the loopback endpoint.
 * Both [signature] (the ``ThresholdSignature``) and [member] (the founder
 * ``ThresholdMember``) ride as opaque signed JSON; the app collects them and
 * relays them verbatim to ``…/genesis/assemble`` (``signatures`` + ``founders``).
 */
@Serializable
data class CosignFamilyResponse(
    @SerialName("key_id")
    val keyId: String,
    val signature: kotlinx.serialization.json.JsonElement,
    val member: kotlinx.serialization.json.JsonElement,
)

/**
 * ``POST /v1/accord/genesis/assemble`` response — the assembled, 2/3-founder-
 * signed genesis (the cold-start recognition root / bake artifact, CIRISVerify
 * #107). [genesis] is the opaque signed CEG object the operator MUST SAVE.
 */
@Serializable
data class GenesisAssembleResponse(
    val genesis: kotlinx.serialization.json.JsonElement,
    val message: String? = null,
)

// ─── Re-mint existing trust root → portable genesis (FSD/MESH_GENESIS.md) ─────
//
// The EXISTING accord + canonical are re-minted into a portable, self-verifying
// genesis bundle (src/accord_provision.rs). The operator flow:
//   1. GET  /v1/accord/genesis/remint-source  → pre-fill (holders + canonicals).
//      C1 need not be present — quorum 2/3, so its record rides the roster.
//   2. POST /v1/accord/canonical/propose      (A1, pre-filled)   → partial
//   3. POST /v1/accord/canonical/cosign       (B1)               → completed record,
//      now carrying `infra:serve` in the SIGNED identity_type set.
//   (There is no separate 'produce' step: `genesis/propose` mints the whole bundle.)

/**
 * One accord holder of the re-mint roster — an entry of
 * `GET /v1/accord/genesis/remint-source`. The FULL roster (A1/B1/C1) rides the
 * genesis even when only two sign, so 2-of-3 never silently narrows to 2-of-2.
 */
@Serializable
data class RemintHolderDto(
    @SerialName("key_id")
    val keyId: String,
    @SerialName("identity_type")
    val identityType: String? = null,
    @SerialName("pubkey_ed25519_base64")
    val pubkeyEd25519Base64: String,
    @SerialName("pubkey_ml_dsa_65_base64")
    val pubkeyMlDsa65Base64: String? = null,
)

/**
 * One existing canonical server of the re-mint roster. [confersInfraServe] is
 * whether the record ALREADY confers `infra:serve` (identity_type ∪ roles) —
 * `false` is exactly what the re-mint fixes.
 */
@Serializable
data class RemintCanonicalDto(
    @SerialName("key_id")
    val keyId: String,
    @SerialName("identity_type")
    val identityType: String,
    @SerialName("pubkey_ed25519_base64")
    val pubkeyEd25519Base64: String,
    @SerialName("pubkey_ml_dsa_65_base64")
    val pubkeyMlDsa65Base64: String? = null,
    @SerialName("scrub_key_id")
    val scrubKeyId: String? = null,
    @SerialName("transport_hints")
    val transportHints: List<TransportHintDto>? = null,
    @SerialName("confers_infra_serve")
    val confersInfraServe: Boolean = false,
)

/**
 * `GET /v1/accord/genesis/remint-source` response — everything needed to PRE-FILL
 * a "re-mint existing trust root" ceremony, so nothing is retyped and no key
 * material is invented.
 */
@Serializable
data class RemintSourceDto(
    val holders: List<RemintHolderDto> = emptyList(),
    val canonicals: List<RemintCanonicalDto> = emptyList(),
    /** The family quorum, e.g. ``2/3``. */
    /**
     * The family's **entrenched** m-of-n, rendered by the server (e.g. `"2/3"`).
     * Never assume a value: the accord's threshold and seat count are governance
     * state, not constants. Empty until the source call returns — render nothing
     * rather than a guess, because this string tells an operator how many humans
     * to bring to a ceremony.
     */
    val quorum: String = "",
    @SerialName("quorum_m")
    val quorumM: Int = 0,
    @SerialName("quorum_n")
    val quorumN: Int = 0,
    val note: String? = null,
)

/**
 * The portable `GenesisBundle` decoded for DISPLAY — `POST /v1/accord/genesis/propose`
 * returns the bundle itself. [holders] / [serveNodes] are opaque signed
 * `SignedKeyRecord`s the app never inspects, so they ride as raw
 * [kotlinx.serialization.json.JsonElement]s (counts only).
 */
@Serializable
data class GenesisBundleDto(
    val version: Int = 0,
    @SerialName("family_key_id")
    val familyKeyId: String = "",
    val holders: List<kotlinx.serialization.json.JsonElement> = emptyList(),
    @SerialName("serve_nodes")
    val serveNodes: List<kotlinx.serialization.json.JsonElement> = emptyList(),
    @SerialName("produced_at")
    val producedAt: String? = null,
)

/**
 * The parsed `POST /v1/accord/genesis/propose` result: [bundle] is the portable
 * `GenesisBundle` JSON VERBATIM (the artifact the operator saves / shares);
 * [summary] is the same bytes decoded for display.
 */
data class ProduceGenesisResult(
    val bundle: kotlinx.serialization.json.JsonElement,
    val summary: GenesisBundleDto,
)

// ─── Portable mesh-genesis SEED ceremony (propose → cosign) ───────────────────
//
// Two accord holders — real people, one YubiKey each — turn the EXISTING roster
// plus one canonical serve node into a portable trust-root seed, in the SAME
// propose → cosign shape as the canonical / CI-key co-scrubs:
//   1. POST /v1/accord/genesis/propose  (the first holder) → charter + grant, signed
//   2. POST /v1/accord/genesis/cosign   (the second holder) → the SAME bundle, again
// The bundle rides VERBATIM as a raw `JsonElement` between the two calls — never
// re-serialized through a typed model — so unknown server fields survive the
// round-trip and the authorized bytes stay byte-identical.

/**
 * `POST /v1/accord/genesis/propose` and `POST /v1/accord/genesis/cosign` response —
 * the same shape for both. [bundle] is the (possibly still-partial) seed JSON held
 * VERBATIM; [authorizationsHave] / [authorizationsNeeded] are the running tally the
 * card shows, and [complete] is the server's own verdict (it is authoritative — the
 * client NEVER re-derives it from a threshold of its own).
 */
@Serializable
data class GenesisSeedResponse(
    val bundle: kotlinx.serialization.json.JsonElement,
    @SerialName("authorizations_have")
    val authorizationsHave: Int = 0,
    @SerialName("authorizations_needed")
    val authorizationsNeeded: Int = 0,
    val complete: Boolean = false,
    /**
     * The chosen canonical carried no `infra:serve` (it predated the conferral),
     * so THIS ceremony blessed it as a trace server as part of minting the seed —
     * the same two holders, the same two taps. Surface it so the operator knows a
     * second thing happened: the canonical is now trusted-by-default to receive
     * traces, and un-blessing it (the canonical withdraw op) reverses it.
     */
    @SerialName("serve_node_reblessed")
    val serveNodeReblessed: Boolean = false,
)

/** A non-200 `{"error": …}` body from the seed ceremony — the node's refusal text. */
@Serializable
data class GenesisSeedErrorDto(
    val error: String = "",
)

/**
 * The seed ceremony's live, resumable state — held between propose and cosign so a
 * partially authorized bundle is never lost or re-derived. [bundle] is the server's
 * JSON VERBATIM (passed back unchanged to cosign); [prettyJson] is the SAME bytes
 * pretty-printed for Copy / Save only.
 *
 * [authorizedKeyIds] is who has already authorized — used to keep the cosign holder
 * picker from offering a holder the server would reject as a duplicate.
 */
data class GenesisSeedState(
    val bundle: kotlinx.serialization.json.JsonElement,
    val prettyJson: String,
    val authorizationsHave: Int,
    val authorizationsNeeded: Int,
    val complete: Boolean,
    val authorizedKeyIds: List<String> = emptyList(),
    /** Sticky once true across the ceremony: the canonical was blessed inline. */
    val serveNodeReblessed: Boolean = false,
)

/**
 * The DISPLAY-only reads off a seed [GenesisSeedState.bundle]. Read field-by-field
 * off the raw JSON rather than decoded into a typed model, so nothing the server
 * sends is dropped: [fingerprint] is absent on bundles that carry none (omit the
 * line then — never invent one), and counts are 0 when the arrays are absent.
 */
data class GenesisSeedDisplay(
    val familyKeyId: String,
    val holderCount: Int,
    val serveNodeCount: Int,
    val fingerprint: String?,
    val authorizedKeyIds: List<String>,
)

/**
 * Read [GenesisSeedDisplay] off a VERBATIM seed bundle. Tolerant by design — the
 * bundle is the server's artifact and may carry fields this client has never heard
 * of; every read is best-effort and absence is rendered as absence.
 *
 * `authorizations` is read as either an array of strings or an array of objects
 * carrying `holder_key_id` / `key_id`, so the cosign picker can exclude holders who
 * authorized on ANOTHER device (a bundle carried in on a USB stick).
 */
fun genesisSeedDisplay(bundle: kotlinx.serialization.json.JsonElement): GenesisSeedDisplay {
    val obj = bundle as? kotlinx.serialization.json.JsonObject
    fun str(field: String): String? =
        (obj?.get(field) as? kotlinx.serialization.json.JsonPrimitive)
            ?.takeIf { it.isString }
            ?.content
            ?.takeIf { it.isNotBlank() }
    fun size(field: String): Int =
        (obj?.get(field) as? kotlinx.serialization.json.JsonArray)?.size ?: 0
    val authorized = (obj?.get("authorizations") as? kotlinx.serialization.json.JsonArray)
        ?.mapNotNull { entry ->
            when (entry) {
                is kotlinx.serialization.json.JsonPrimitive ->
                    entry.takeIf { it.isString }?.content
                is kotlinx.serialization.json.JsonObject ->
                    (entry["holder_key_id"] ?: entry["key_id"])
                        ?.let { it as? kotlinx.serialization.json.JsonPrimitive }
                        ?.takeIf { it.isString }
                        ?.content
                else -> null
            }
        }
        ?.filter { it.isNotBlank() }
        .orEmpty()
    return GenesisSeedDisplay(
        familyKeyId = str("family_key_id").orEmpty(),
        holderCount = size("holders"),
        serveNodeCount = size("serve_nodes"),
        fingerprint = str("fingerprint"),
        authorizedKeyIds = authorized,
    )
}

/**
 * ``GET /v1/accord/yubikey-status`` — the inserted YubiKey's readiness for accord
 * provisioning, so the ceremony UI can show a clear banner + the PIN/PUK tries.
 * `detected=false` (token/`ykman` absent) carries a [hint] instead of the rest.
 * `ready` == detected && fips_approved && slot 9C has BOTH a key and a certificate
 * (the cert is what ykcs11 needs to enumerate the key).
 */
@Serializable
data class YubiKeyStatus(
    val detected: Boolean = false,
    val ready: Boolean = false,
    @SerialName("piv_version") val pivVersion: String? = null,
    @SerialName("fips_approved") val fipsApproved: Boolean = false,
    @SerialName("pin_tries_remaining") val pinTriesRemaining: String? = null,
    @SerialName("puk_tries_remaining") val pukTriesRemaining: String? = null,
    @SerialName("slot_9c_key") val slot9cKey: Boolean = false,
    @SerialName("slot_9c_key_type") val slot9cKeyType: String? = null,
    @SerialName("slot_9c_cert") val slot9cCert: Boolean = false,
    // null = couldn't verify (pkcs11-tool absent); true = host ykcs11 exposes the
    // Ed25519 signing key; false = host ykcs11 too old (< 2.5.0) — the slot is fine
    // but the HOST library must be upgraded. Drives the "stale host" alert.
    @SerialName("pkcs11_ed25519_ok") val pkcs11Ed25519Ok: Boolean? = null,
    val hint: String? = null,
)
