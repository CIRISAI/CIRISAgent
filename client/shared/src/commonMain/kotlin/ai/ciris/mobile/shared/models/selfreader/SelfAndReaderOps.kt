package ai.ciris.mobile.shared.models.selfreader

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Tier S (self-directed) + tier R (per-reader) wire types — the two rungs of
 * `CIRISServer/src/admin_ops.rs` that do not act on anyone else.
 *
 * Field-for-field against the server's own JSON builders:
 * `self_fold_json` / `self_standing` / `self_act_route` (tier S) and
 * `reader_fold_json` / `reader_decision_route` (tier R).
 *
 * Two rules this file exists to keep, both of which the server states in its own
 * responses:
 *
 * 1. **Three tier-S axes, never folded together.** `load_shed`, `accepting` and
 *    `legal_compulsion` are three standings. "This node chose to stop" and "this
 *    node was made to stop" are the same observable with opposite meanings, so
 *    [SelfCommitRequest.compelledBy] rides on the compulsion declaration ALONE —
 *    the API surface gives the other five acts no parameter to carry it.
 * 2. **Three of the four standings are zeroes and none of them is the others.**
 *    [SelfStanding.NEVER_DECLARED], [SelfStanding.LIFTED] and
 *    [SelfStanding.UNREADABLE] must never render alike, and an unrecognised
 *    token ([SelfStanding.UNKNOWN]) is a fourth non-fact — never silently a
 *    clean one.
 */

// ─── Shared ──────────────────────────────────────────────────────────────────

/**
 * One server message: a stable `id` to resolve through the localization bundle
 * plus the English source `text` to fall back to. Every id this rung emits is
 * already translated into 29 languages; the `text` is the last resort, never
 * the first choice.
 */
@Serializable
data class AdminMessage(
    val id: String = "",
    val text: String = "",
)

/** The one refusal shape every admin_ops route uses (`refusal()` / `err()`). */
@Serializable
data class AdminRefusalDto(
    val refused: Boolean = true,
    /** Stable program token: `session_absent`, `node_unowned`, … */
    val refusal: String? = null,
    @SerialName("source_locale") val sourceLocale: String = "en",
    val message: AdminMessage? = null,
)

/** `reversal_json` — `{reach, note}`. */
@Serializable
data class AdminReversalDto(
    val reach: String = "",
    val note: AdminMessage? = null,
)

// ─── Tier S — self-directed ──────────────────────────────────────────────────

/** The three axes, as the server's `SelfAct::axis()` spells them. */
object SelfAxis {
    const val LOAD_SHED = "load_shed"
    const val ACCEPTING = "accepting"
    const val LEGAL_COMPULSION = "legal_compulsion"

    /** Declaration order — the server's `SelfAct::ALL`. */
    val ALL = listOf(LOAD_SHED, ACCEPTING, LEGAL_COMPULSION)
}

/**
 * `SelfStanding::token()` — four values, three of them zeroes that mean
 * different things.
 */
enum class SelfStanding(val wire: String) {
    /** Declared, not lifted. */
    IN_FORCE("in_force"),

    /** Declared and then lifted. NOT the same fact as never having declared. */
    LIFTED("lifted"),

    /** No act on this axis was ever recorded here. */
    NEVER_DECLARED("never_declared"),

    /** The ledger read failed: this node does not know. NOT "nothing in force". */
    UNREADABLE("unreadable"),

    /** A token this client does not recognise. Also NOT "nothing in force". */
    UNKNOWN("");

    /** Is this axis actively declared? Only [IN_FORCE] answers yes — the three
     *  non-facts are non-facts, and none of them is a "no". */
    val isInForce: Boolean get() = this == IN_FORCE

    /** Is this a standing this node could actually read? */
    val isKnown: Boolean get() = this != UNREADABLE && this != UNKNOWN

    companion object {
        fun fromWire(token: String?): SelfStanding =
            entries.firstOrNull { it.wire.isNotEmpty() && it.wire == token } ?: UNKNOWN
    }
}

/** `self_fold_json` — one axis's folded standing plus its evidence. */
@Serializable
data class SelfAxisCounts(
    val declarations: Int = 0,
    val lifts: Int = 0,
)

@Serializable
data class SelfAxisStandingDto(
    val axis: String = "",
    /** Raw token; read [standing] rather than comparing strings. */
    val standing: String = "",
    val message: AdminMessage? = null,
    /** RFC3339 instant the governing act took effect; null for both non-facts. */
    val since: String? = null,
    @SerialName("event_id") val eventId: String? = null,
    @SerialName("delegation_id") val delegationId: String? = null,
    val reason: String? = null,
    val counts: SelfAxisCounts = SelfAxisCounts(),
) {
    val standingValue: SelfStanding get() = SelfStanding.fromWire(standing)
}

/** `GET /v1/admin/self` — the three standings, side by side. */
@Serializable
data class SelfStandingResponse(
    @SerialName("source_locale") val sourceLocale: String = "en",
    val tier: String = "S",
    @SerialName("node_key_id") val nodeKeyId: String = "",
    /** Keyed by axis token. */
    val standings: Map<String, SelfAxisStandingDto> = emptyMap(),
    val partition: AdminMessage? = null,
    @SerialName("distinct_zeroes") val distinctZeroes: AdminMessage? = null,
    /** Present only on the 503 half: axis token → the read error. */
    @SerialName("unreadable_axes") val unreadableAxes: Map<String, String>? = null,
) {
    /** The axis rows in the server's declaration order, with a
     *  never-rendered-as-clean placeholder for anything absent. */
    fun axes(): List<SelfAxisStandingDto> = SelfAxis.ALL.map { axis ->
        standings[axis] ?: SelfAxisStandingDto(axis = axis, standing = SelfStanding.UNKNOWN.wire)
    }
}

/** The body of every tier S act (`SelfCommit`). */
@Serializable
data class SelfCommitRequest(
    @SerialName("delegation_id") val delegationId: String,
    val reason: String,
    /**
     * Optional, and read by the compulsion declaration ONLY. Its absence is not
     * a defect: an operator under a gag order may be unable to name the
     * authority compelling them, and refusing to record the act without it would
     * mean the most constrained operator is the one who cannot leave a trace.
     */
    @SerialName("compelled_by") val compelledBy: String? = null,
)

/** The response of any of the six tier S acts (`self_act_route`). */
@Serializable
data class SelfActResponse(
    val op: String = "",
    val tier: String = "S",
    val axis: String = "",
    @SerialName("source_locale") val sourceLocale: String = "en",
    @SerialName("required_scope") val requiredScope: String? = null,
    @SerialName("delegation_id") val delegationId: String? = null,
    @SerialName("event_id") val eventId: String? = null,
    val standing: SelfAxisStandingDto? = null,
    /** What the act reaches — which, on this rung, is the record and nothing more. */
    val enforcement: AdminMessage? = null,
    val partition: AdminMessage? = null,
    /** Lifts only. */
    val reversal: AdminReversalDto? = null,
    /** Lifts only. */
    val lift: AdminMessage? = null,
)

/**
 * What one tier S read produced. The unreachable case is first-class: tier S is
 * the only rung available under partition, so "could not reach this node" is
 * exactly the answer an operator needs — and it is never a clean standing.
 */
sealed class SelfStandingOutcome {
    /**
     * @param partiallyUnreadable the server answered 503 with at least one axis
     *   it could not read. The body still carries every standing, and the
     *   unreadable ones are [SelfStanding.UNREADABLE].
     */
    data class Read(
        val response: SelfStandingResponse,
        val partiallyUnreadable: Boolean,
    ) : SelfStandingOutcome()

    /** The gate refused (401/403) or the substrate was unavailable (5xx). */
    data class Refused(val refusal: AdminRefusalDto, val httpStatus: Int) : SelfStandingOutcome()

    /** The node itself could not be reached. Says nothing about any standing. */
    data class Unreachable(val detail: String) : SelfStandingOutcome()
}

/** What one tier S act produced. */
sealed class SelfActOutcome {
    data class Recorded(val response: SelfActResponse) : SelfActOutcome()

    data class Refused(val refusal: AdminRefusalDto, val httpStatus: Int) : SelfActOutcome()

    data class Unreachable(val detail: String) : SelfActOutcome()
}

// ─── Tier R — subject-side / per-reader ──────────────────────────────────────

/**
 * `ReaderDecision::token()` — what THIS reader does with one judgement.
 *
 * [DECLINED] is a **normal outcome**, not an error: an issued judgement is
 * advisory to each reader, and refusing one is the property the rung exists for.
 * Two readers with different policies reaching different, both-valid states from
 * the same judgement is the design working.
 */
enum class ReaderDecision(val wire: String) {
    HONOURED_EXPLICIT("honoured_explicit"),
    HONOURED_BY_SUBSCRIPTION("honoured_by_subscription"),

    /** Not honoured, and NOBODY decided that — distinct from a decline. */
    UNDECIDED_UNSUBSCRIBED("undecided_unsubscribed"),

    /** This reader refused it. A first-class outcome. */
    DECLINED("declined"),

    UNKNOWN("");

    val honoured: Boolean
        get() = this == HONOURED_EXPLICIT || this == HONOURED_BY_SUBSCRIPTION

    /** Was this state chosen by this reader, or merely defaulted into? */
    val isDeliberate: Boolean
        get() = this == HONOURED_EXPLICIT || this == DECLINED

    companion object {
        fun fromWire(token: String?): ReaderDecision =
            entries.firstOrNull { it.wire.isNotEmpty() && it.wire == token } ?: UNKNOWN
    }
}

/** `ReaderStanding::token()` — same three-way discipline, per read. */
enum class ReaderStanding(val wire: String) {
    DECIDED("decided"),

    /** This node holds no judgement about that subject. */
    NO_JUDGEMENTS_HELD("no_judgements_held"),

    /** The read failed. NOT "no judgements" and NOT "nothing withheld". */
    UNREADABLE("unreadable"),

    UNKNOWN("");

    val isKnown: Boolean get() = this != UNREADABLE && this != UNKNOWN

    companion object {
        fun fromWire(token: String?): ReaderStanding =
            entries.firstOrNull { it.wire.isNotEmpty() && it.wire == token } ?: UNKNOWN
    }
}

/** One judgement this node holds, with what this reader does about it. */
@Serializable
data class ReaderJudgementDto(
    @SerialName("judgement_id") val judgementId: String = "",
    @SerialName("signer_key_id") val signerKeyId: String = "",
    val dimension: String? = null,
    @SerialName("asserted_at") val assertedAt: String? = null,
    val decision: String = "",
    val honoured: Boolean = false,
    val message: AdminMessage? = null,
) {
    val decisionValue: ReaderDecision get() = ReaderDecision.fromWire(decision)
}

/** This reader's subscription set. */
@Serializable
data class ReaderSubscriptionDto(
    val roots: List<String> = emptyList(),
    val count: Int = 0,
)

@Serializable
data class ReaderCountsDto(
    @SerialName("judgements_held") val judgementsHeld: Int = 0,
)

/** persist's own `QuarantineFold`, as the server serializes it. */
@Serializable
data class QuarantineFoldDto(
    @SerialName("key_id") val keyId: String = "",
    /** `not_quarantined` | `withheld` | `released`. */
    val state: String = "",
    @SerialName("marker_id") val markerId: String? = null,
    @SerialName("decided_by") val decidedBy: String? = null,
    @SerialName("delegation_id") val delegationId: String? = null,
    @SerialName("effective_at") val effectiveAt: String? = null,
    val grounds: String? = null,
    @SerialName("marker_ids") val markerIds: List<String> = emptyList(),
)

/** `POST /v1/admin/reader/fold` — what THIS reader makes of what it holds. */
@Serializable
data class ReaderFoldResponse(
    @SerialName("source_locale") val sourceLocale: String = "en",
    val tier: String = "R",
    @SerialName("subject_key_id") val subjectKeyId: String = "",
    val standing: String = "",
    val message: AdminMessage? = null,
    val subscription: ReaderSubscriptionDto = ReaderSubscriptionDto(),
    val counts: ReaderCountsDto = ReaderCountsDto(),
    val judgements: List<ReaderJudgementDto> = emptyList(),
    /** This reader's policy over the honoured subset. */
    @SerialName("reader_fold") val readerFold: QuarantineFoldDto? = null,
    /** What this node's serve paths do today, over everything held. */
    @SerialName("node_fold") val nodeFold: QuarantineFoldDto? = null,
    val diverges: Boolean = false,
    val advisory: AdminMessage? = null,
    /** 503 half only. */
    val refusal: String? = null,
    /** 503 half only: the read error. */
    val error: String? = null,
) {
    val standingValue: ReaderStanding get() = ReaderStanding.fromWire(standing)
}

/** The body of a reader decision (`ReaderCommit`). */
@Serializable
data class ReaderCommitRequest(
    @SerialName("judgement_id") val judgementId: String,
    @SerialName("delegation_id") val delegationId: String,
    val reason: String,
)

@Serializable
data class ReaderFoldRequest(
    @SerialName("subject_key_id") val subjectKeyId: String,
)

/**
 * `POST /v1/admin/reader/{honour,decline}` — the SAME shape and the same status
 * for both, because a decline is not an error path. `refused` is stated in the
 * payload precisely so a client branching on shape rather than on 2xx cannot
 * read a decline as a failure.
 */
@Serializable
data class ReaderDecisionResponse(
    val op: String = "",
    val tier: String = "R",
    @SerialName("source_locale") val sourceLocale: String = "en",
    @SerialName("required_scope") val requiredScope: String? = null,
    @SerialName("judgement_id") val judgementId: String = "",
    @SerialName("subject_key_id") val subjectKeyId: String = "",
    @SerialName("delegation_id") val delegationId: String? = null,
    @SerialName("event_id") val eventId: String? = null,
    /** `honoured` | `declined` — both are successes. */
    val outcome: String = "",
    val refused: Boolean = false,
    val message: AdminMessage? = null,
    /** The state this decision produced, through the fold route's own read. */
    val standing: ReaderFoldResponse? = null,
) {
    val declined: Boolean get() = outcome == "declined"
}

/** What one tier R read produced. */
sealed class ReaderFoldOutcome {
    data class Read(val response: ReaderFoldResponse) : ReaderFoldOutcome()

    /**
     * The 503 half: this reader could not read its own state. The body still
     * carries [ReaderStanding.UNREADABLE], and it is neither "no judgements"
     * nor "nothing withheld".
     */
    data class Unreadable(val response: ReaderFoldResponse) : ReaderFoldOutcome()

    data class Refused(val refusal: AdminRefusalDto, val httpStatus: Int) : ReaderFoldOutcome()

    data class Unreachable(val detail: String) : ReaderFoldOutcome()
}

/** What one reader decision produced. A decline lands in [Recorded]. */
sealed class ReaderDecisionOutcome {
    data class Recorded(val response: ReaderDecisionResponse) : ReaderDecisionOutcome()

    data class Refused(val refusal: AdminRefusalDto, val httpStatus: Int) : ReaderDecisionOutcome()

    data class Unreachable(val detail: String) : ReaderDecisionOutcome()
}
