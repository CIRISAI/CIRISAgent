package ai.ciris.mobile.shared.models.federation

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

/**
 * Wire models for **conferring a moderation duty on another self** — the
 * co-scrubbed "you may act on my behalf, and here is how far you may pass it on"
 * conferral.
 *
 * Two loopback + owner-gated routes on the LOCAL node:
 *   POST /v1/accord/duty/propose → [DutyProposeRequest]  / [DutyConferralResponse]
 *   POST /v1/accord/duty/cosign  → [DutyCosignRequest]   / [DutyConferralResponse]
 *
 * The shape is the accord co-scrub shape: `propose` produces a 1-scrub **partial**
 * that does NOT yet confer the duty; each holder `cosign`s the BYTE-IDENTICAL
 * envelope until `scrub_count == quorum_needed`, at which point `adopted` flips
 * true. [DutyConferralResponse.partial] therefore rides as a raw
 * [JsonElement] and is round-tripped VERBATIM into the next `cosign` — the app
 * never re-encodes a signed envelope and never models its internals.
 *
 * ARCHITECTURE: the app holds NO keys and performs NO crypto. It passes the
 * holder's `key_id` + the ML-DSA USB path (and an opaque `pkcs11` blob when the
 * caller has one); the node opens the hardware and signs.
 */

/**
 * The signing accord holder. [pkcs11] is opaque to the client — whatever knobs the
 * node understands (`user_pin` / `piv_slot` / `module_path`) ride through
 * untouched, and the field is omitted entirely when there are none.
 */
@Serializable
data class DutyHolder(
    /** The holder's seal alias — the identity its YubiKey + USB ML-DSA opens. */
    @SerialName("key_id")
    val keyId: String,
    /** The folder holding the USB-wrapped ML-DSA half of the holder's hybrid key. */
    @SerialName("mldsa_usb_path")
    val mldsaUsbPath: String,
    /** Opaque PKCS#11 knobs — passed through verbatim; omitted when absent. */
    val pkcs11: JsonElement? = null,
)

/**
 * Body of `POST /v1/accord/duty/propose` — the FIRST scrub of the conferral.
 *
 * [subDelegation] answers "may the subject pass this duty on?" and
 * [subDelegationDepth] bounds how many further hops it may travel. `null` depth
 * means "bounded only by the global rail" (5). Both are ALWAYS serialized (no
 * kotlinx default elision) so the node never has to guess which axis was meant.
 */
@Serializable
data class DutyProposeRequest(
    val holder: DutyHolder,
    /** The self the duty is conferred ON. */
    @SerialName("subject_key_id")
    val subjectKeyId: String,
    /**
     * The duties this grant carries — a SET. persist admits `scope` as a bare
     * string OR a JSON array with set-containment, so one grant can carry several
     * duties; the earlier single `duty: String` was a narrowing invented on this
     * side. All five the substrate defines are conferrable: `consent_revocation`,
     * `moderate`, `takedown`, `review`, `slash`.
     */
    val duties: List<String>,
    /** May the subject pass the duty on at all? */
    @SerialName("sub_delegation")
    val subDelegation: Boolean,
    /** Further hops allowed; `null` = bounded only by the global rail (5). */
    @SerialName("sub_delegation_depth")
    val subDelegationDepth: Int?,
)

/**
 * Body of `POST /v1/accord/duty/cosign` — appends THIS holder's scrub to
 * [partial]. [partial] MUST be the verbatim blob a prior `propose` / `cosign`
 * returned; it is submitted UNCHANGED so the signed bytes still canonicalize.
 */
@Serializable
data class DutyCosignRequest(
    val holder: DutyHolder,
    /** The opaque partial, round-tripped byte-for-byte. */
    val partial: JsonElement,
)

/**
 * Response of BOTH duty routes. [adopted] is true only once [scrubCount] meets
 * [quorumNeeded] — until then [partial] is the thing to hand to the next holder.
 */
@Serializable
data class DutyConferralResponse(
    /** The opaque partial — hand it to the next holder's `cosign` unchanged. */
    val partial: JsonElement? = null,
    /** Distinct holder scrubs on the partial so far. */
    @SerialName("scrub_count")
    val scrubCount: Int = 0,
    /** The family m-of-n threshold M. */
    @SerialName("quorum_needed")
    val quorumNeeded: Int = 0,
    /** True once the conferral is adopted (quorum met) — the duty is conferred. */
    val adopted: Boolean = false,
    /**
     * Present only when [adopted] — what the grant now says, in one line, so the
     * operator reads back what they signed instead of inferring it.
     */
    val conferred: String? = null,
)
