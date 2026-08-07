package ai.ciris.mobile.shared.models.surfaces

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

/**
 * **The commons surface** (CIRISServer#367, `src/commons_surface.rs`) — the
 * reverse-quorum plane a community polices itself with.
 *
 * ```text
 * GET  /v1/commons/standing      the fold's live answer about ONE action
 * POST /v1/commons/objections    1-of-N   raise the brake
 * POST /v1/commons/ballots       1 sig    answer what the stewards left open
 * POST /v1/commons/dismissals    m-of-n   lift a brake (dry_run -> co-sign -> submit)
 * ```
 *
 * # The asymmetry these types must not flatten
 *
 * > **1-of-N to protect, m-of-n to undo.**
 *
 * [CommonsStanding.objectionThreshold] is the price of RAISING and it is one.
 * [CommonsDismissalQuorum.required] is the price of LIFTING and it is the
 * cohort's own m-of-n. They are carried as two separate fields from two
 * separate responses because they are two separate prices — a client that
 * renders them as one "votes needed" number has destroyed the design.
 *
 * # Five of the eight standings are absences, and they are not zeroes
 *
 * `unreadable` / `action_unknown` / `cohort_unknown` / `not_governed` /
 * `quiet` all look like "nothing is stopping this action". Only `quiet` is a
 * statement about a plane that was actually READ. On the four unknown arms the
 * server sends [CommonsStanding.fold] and [CommonsStanding.escalation] as
 * `null` — deliberately not `0` — so this client must render "we could not
 * ask" differently from "nobody objected". They are opposite facts.
 */

// ═════════════════════════════════════════════════════════════════════════════
//  GET /v1/commons/standing
// ═════════════════════════════════════════════════════════════════════════════

/**
 * Persist's own fold over one action. Every number here is the substrate's;
 * the server computes no threshold and neither does this client.
 */
@Serializable
data class CommonsFold(
    /** `not_governed` | `window_open` | `stood` | `reversed`. */
    @SerialName("substrate_standing") val substrateStanding: String = "",
    /** The cohort's parsed protocol string, or `null` when not governed. */
    val policy: String? = null,
    /** DISTINCT in-window, live, roster-member objectors. */
    @SerialName("distinct_objectors") val distinctObjectors: Int = 0,
    /** The reversal threshold for the live roster (`0` when not governed). */
    val required: Int = 0,
    /** The live roster the threshold was derived from. */
    @SerialName("roster_size") val rosterSize: Int = 0,
    @SerialName("window_opens_at") val windowOpensAt: String = "",
    @SerialName("window_closes_at") val windowClosesAt: String = "",
    @SerialName("window_open") val windowOpen: Boolean = false,
    /** The fold names its evidence. */
    @SerialName("counted_objection_ids") val countedObjectionIds: List<String> = emptyList(),
    /** Objections excluded because a quorum-verified DISMISSAL named them. */
    @SerialName("dismissed_objection_ids") val dismissedObjectionIds: List<String> = emptyList(),
    /**
     * Objections excluded because the ESCALATED respondent pool overruled them.
     * Its own list, never merged with [dismissedObjectionIds]: the two
     * suppressions were bought at two different prices against two different
     * denominators.
     */
    @SerialName("escalated_dismissed_objection_ids")
    val escalatedDismissedObjectionIds: List<String> = emptyList(),
)

/**
 * One objection's steward / escalation record.
 *
 * [respondents] is the property CIRISPersist#591 exists for: past the steward
 * deadline the threshold counts the people who ANSWERED, not the roster. That
 * is what lets a quiet community still resolve — which is exactly when it is
 * most vulnerable — and [CommonsStanding.escalationRespondentFloor] is the
 * absolute floor no policy string can lower.
 */
@Serializable
data class CommonsEscalationRecord(
    @SerialName("objection_id") val objectionId: String = "",
    /** `awaiting` | `upheld` | `silent` | `overruled` | `no_duty_holders` | `not_adopted`. */
    val steward: String = "",
    @SerialName("steward_message") val stewardMessage: SurfaceMessage? = null,
    /** persist's own `escalates()` predicate — never re-derived here. */
    @SerialName("escalation_open") val escalationOpen: Boolean = false,
    /** `unresolved` | `upheld` | `dismissed` | `not_escalated`. */
    val outcome: String = "",
    @SerialName("outcome_message") val outcomeMessage: SurfaceMessage? = null,
    /** The live appointed-moderator count, AFTER recusal. */
    @SerialName("duty_holders") val dutyHolders: Int = 0,
    @SerialName("steward_ruling_required") val stewardRulingRequired: Int = 0,
    /** **The escalated denominator** — who answered, not who is on the roster. */
    val respondents: Int = 0,
    /** What the escalated undo costs against [respondents]. */
    val required: Int = 0,
    @SerialName("uphold_ballots") val upholdBallots: Int = 0,
    @SerialName("overrule_ballots") val overruleBallots: Int = 0,
    /** One governing ballot per respondent — the evidence for the counts. */
    @SerialName("counted_ballot_ids") val countedBallotIds: List<String> = emptyList(),
)

/**
 * The escalation axis — a SEPARATE axis from the standing, because persist
 * keeps it separate: this answers *did the people carrying the duty answer?*
 * and the standing answers *does the action stand?*.
 *
 * Four [standing] arms, three of them zeroes with different causes:
 * `not_adopted` / `nothing_to_escalate` / `awaiting` / `open`.
 */
@Serializable
data class CommonsEscalation(
    val standing: String = "",
    @SerialName("standing_message") val standingMessage: SurfaceMessage? = null,
    /** When the appointed moderators' answer was due, or `null` if no tier. */
    @SerialName("steward_deadline") val stewardDeadline: String? = null,
    val objections: List<CommonsEscalationRecord> = emptyList(),
)

/** The four envelope dimensions this plane's rows are filed under. */
@Serializable
data class CommonsDimensions(
    val objection: String = "",
    val dismissal: String = "",
    val uphold: String = "",
    val overrule: String = "",
)

/**
 * `GET /v1/commons/standing` — the fold's live answer about ONE action.
 *
 * Eight [standing] tokens. `unreadable` (503) / `action_unknown` (404) /
 * `cohort_unknown` (404) arrive on NON-2XX statuses carrying a full body, so
 * the client must read the body on those statuses rather than treat them as
 * transport failures: they are answers, not errors.
 */
@Serializable
data class CommonsStanding(
    @SerialName("source_locale") val sourceLocale: String = "en",
    @SerialName("generated_at") val generatedAt: String = "",
    val cohort: String = "",
    @SerialName("cohort_key_id") val cohortKeyId: String = "",
    @SerialName("action_id") val actionId: String = "",
    /**
     * `unreadable` | `action_unknown` | `cohort_unknown` | `not_governed` |
     * `quiet` | `objected` | `stood` | `reversed`.
     */
    val standing: String = "",
    @SerialName("standing_message") val standingMessage: SurfaceMessage? = null,
    /** **The price of raising a brake. It is one.** Named on every response. */
    @SerialName("objection_threshold") val objectionThreshold: Int = 0,
    /** The absolute floor the escalated undo can never fall below. */
    @SerialName("escalation_respondent_floor") val escalationRespondentFloor: Int = 0,
    @SerialName("asymmetry_message") val asymmetryMessage: SurfaceMessage? = null,
    val dimensions: CommonsDimensions? = null,
    @SerialName("action_author") val actionAuthor: String? = null,
    @SerialName("action_asserted_at") val actionAssertedAt: String? = null,
    /** `null` on every absence arm — the counts are UNKNOWN, not zero. */
    val fold: CommonsFold? = null,
    /** `null` on every absence arm — likewise. */
    val escalation: CommonsEscalation? = null,
    val error: String? = null,
    val refused: Boolean = false,
    val refusal: String? = null,
    /** Present on the gate-refusal shape only. */
    val message: SurfaceMessage? = null,
)

// ═════════════════════════════════════════════════════════════════════════════
//  The three write doors
// ═════════════════════════════════════════════════════════════════════════════

/**
 * `POST /v1/commons/objections` — **raise the brake. One member is enough.**
 *
 * [grounds] is MANDATORY and recorded, never interpreted: an objection raised
 * for no recorded reason is indistinguishable from one raised for a bad one.
 */
@Serializable
data class CommonsObjectionRequest(
    val cohort: String,
    @SerialName("cohort_key_id") val cohortKeyId: String,
    @SerialName("action_id") val actionId: String,
    val grounds: String,
)

/** `POST /v1/commons/ballots` — answer what the duty-holders left open. */
@Serializable
data class CommonsBallotRequest(
    val cohort: String,
    @SerialName("cohort_key_id") val cohortKeyId: String,
    @SerialName("action_id") val actionId: String,
    val grounds: String,
    @SerialName("objection_id") val objectionId: String,
    /** `true` — *this objection stands*; `false` — *it does not*. */
    val upholds: Boolean,
)

/**
 * One co-signature over the canonical dismissal envelope. The app holds no keys
 * — these are produced elsewhere, over the exact `payload_sha256` the dry run
 * hands back, and what they are worth is counted by the substrate.
 */
@Serializable
data class CommonsScrubSig(
    @SerialName("scrub_key_id") val scrubKeyId: String,
    @SerialName("scrub_signature_classical") val scrubSignatureClassical: String,
    @SerialName("scrub_signature_pqc") val scrubSignaturePqc: String? = null,
)

/**
 * `POST /v1/commons/dismissals` — **lift a brake. This one costs m-of-n.**
 *
 * [dryRun] is not a convenience: the m-of-n is unreachable without it. It
 * returns the canonical envelope and its `payload_sha256` WITHOUT signing or
 * submitting, so co-signers sign exactly the bytes the submission will carry.
 */
@Serializable
data class CommonsDismissalRequest(
    val cohort: String,
    @SerialName("cohort_key_id") val cohortKeyId: String,
    @SerialName("action_id") val actionId: String,
    val grounds: String,
    @SerialName("objection_id") val objectionId: String,
    @SerialName("additional_scrubs") val additionalScrubs: List<CommonsScrubSig> = emptyList(),
    @SerialName("dry_run") val dryRun: Boolean = false,
)

/** The m-of-n evidence, carried on BOTH arms: a refusal names its shortfall. */
@Serializable
data class CommonsDismissalQuorum(
    /** Distinct co-signers the substrate counted. */
    val counted: Int = 0,
    /** **What lifting costs** — the cohort's own m-of-n, re-derived every read. */
    val required: Int = 0,
    @SerialName("roster_size") val rosterSize: Int = 0,
)

/**
 * The answer from any of the three write doors, and from a dismissal `dry_run`.
 *
 * The substrate decides; this shape only carries what it said. [refusal] is
 * persist's own `ObjectionRefusalReason` token and `commons_surface.refusal.
 * {token}` is its message id.
 */
@Serializable
data class CommonsWriteResult(
    @SerialName("source_locale") val sourceLocale: String = "en",
    @SerialName("dry_run") val dryRun: Boolean = false,
    /** `POST /objections`. */
    @SerialName("objection_id") val objectionId: String? = null,
    @SerialName("action_id") val actionId: String? = null,
    val objector: String? = null,
    /** Echoed on the objection response: the price of raising. One. */
    val threshold: Int? = null,
    /** `POST /ballots`. */
    @SerialName("ballot_id") val ballotId: String? = null,
    val upholds: Boolean? = null,
    val voter: String? = null,
    /** `POST /dismissals`. */
    @SerialName("dismissal_id") val dismissalId: String? = null,
    @SerialName("payload_sha256") val payloadSha256: String? = null,
    val envelope: JsonElement? = null,
    val quorum: CommonsDismissalQuorum? = null,
    val admitted: Boolean = false,
    val refused: Boolean = false,
    val refusal: String? = null,
    val message: SurfaceMessage? = null,
)
