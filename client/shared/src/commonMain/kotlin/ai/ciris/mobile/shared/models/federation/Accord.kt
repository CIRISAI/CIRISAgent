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
    val threshold: Int = 2,
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
    val quorumThreshold: Int = 2,
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
    val quorumThreshold: Int = 2,
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
    val quorumThreshold: Int = 2,
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
 * `steward,accord_holder` anchor. Both are the **genesis seed object**, saved to a
 * predictable outbox path (`ceg_outbox()/accord_admit_node/{target}.json`) the
 * operator hands to CIRISPersist v12.0.2 to bake. `savedTo` is that path; `seed`
 * is the object verbatim (for display / copy).
 */
@Serializable
data class AdmitNodeResponse(
    @SerialName("saved_to")
    val savedTo: String,
    val seed: kotlinx.serialization.json.JsonElement? = null,
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
 * scrub-signed a target node's registration AND flagged it `canonical`, producing
 * the genesis **seed object** saved to a predictable outbox path ([seedSavedTo]).
 * 1-of-N: one holder's YubiKey + USB scrub suffices. If the holder supplied a
 * bootstrap transport the node also records the canonical server's [address].
 */
@Serializable
data class AddCanonicalServerResponse(
    @SerialName("canonical_key_id")
    val canonicalKeyId: String,
    @SerialName("is_canonical")
    val isCanonical: Boolean = false,
    /** Opaque address record (transport_kind + destination) or null. */
    val address: kotlinx.serialization.json.JsonElement? = null,
    @SerialName("seed_saved_to")
    val seedSavedTo: String? = null,
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
