package ai.ciris.mobile.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * **The graded enforcement ladder** — the wire shapes of `src/admin_ops.rs`
 * (CIRISServer#346 / #361 / #375), tiers 0–4.
 *
 * ```text
 * POST /v1/admin/preview          read-only  -> row set + counts + SELECTION HASH
 * POST /v1/admin/annotate         tier 0     scope: review
 * POST /v1/admin/throttle         tier 1     scope: moderate     (+ un-throttle)
 * POST /v1/admin/quarantine       tier 2     scope: slash        (+ un-quarantine)
 * POST /v1/admin/descend          tier 3     scope: slash + QUORUM   IRREVERSIBLE
 * POST /v1/admin/deadmit          tier 4     scope: slash        (+ re-admit)
 * POST /v1/admin/refuse-writes    tier 4     scope: slash        (+ accept-writes)
 * ```
 *
 * Two properties of that module the client has to carry rather than re-invent:
 *
 *  1. **Preview-hash commit.** Every mutating call presents the hash a preview
 *     returned, over the SAME selection; a mismatch is refused with
 *     `preview_hash_mismatch`. So the client must submit the selection it
 *     PREVIEWED, never the one currently in the form — see
 *     [AdminLadderCommitRequest] and the view-model that fills it.
 *  2. **`{delegation_id, reason}` are mandatory** in every tombstone. The route
 *     refuses without them so the operator gets a localizable reason instead of
 *     a substrate error.
 *
 * Every human-readable string arrives as an [AdminMessage] `{id, text}` pair —
 * `id` resolves through the localization bundle, `text` is the English source
 * and is only the fallback. Never render a server sentence as if it were the
 * only copy.
 */

/**
 * One localizable server string. `id` is wire-stable and already carried in the
 * client's bundle for all 29 languages; `text` is the English source the server
 * shipped with the response.
 */
@Serializable
data class AdminMessage(
    val id: String,
    val text: String,
)

/**
 * The operator's selection — every field is an `AttestationFilter` predicate the
 * server pushes into the QUERY. It is also, byte-for-byte, part of the selection
 * hash preimage: changing ANY field here changes the hash, so a changed
 * selection invalidates an outstanding preview by construction.
 *
 * `limit` is clamped server-side to 2000 (`MAX_PREVIEW_LIMIT`); omitted means
 * the server's default of 500.
 */
@Serializable
data class AdminSelectionDto(
    @SerialName("attesting_key_id")
    val attestingKeyId: String? = null,
    @SerialName("attested_key_id")
    val attestedKeyId: String? = null,
    @SerialName("attestation_type")
    val attestationType: String? = null,
    @SerialName("dimension_prefixes")
    val dimensionPrefixes: List<String> = emptyList(),
    @SerialName("dimension_exact")
    val dimensionExact: String? = null,
    @SerialName("subject_key_id")
    val subjectKeyId: String? = null,
    /** Half-open `[after, before)` lower bound on `asserted_at`, RFC3339. */
    val after: String? = null,
    /** Upper bound, RFC3339. Omitted means unbounded above. */
    val before: String? = null,
    val limit: Long? = null,
) {
    /** True when no predicate at all is set — the server refuses this as "the whole corpus". */
    val isUnpredicated: Boolean
        get() = attestingKeyId.isNullOrBlank() &&
            attestedKeyId.isNullOrBlank() &&
            attestationType.isNullOrBlank() &&
            dimensionPrefixes.isEmpty() &&
            dimensionExact.isNullOrBlank() &&
            subjectKeyId.isNullOrBlank() &&
            after.isNullOrBlank() &&
            before.isNullOrBlank()
}

/** One previewed row, projected to what an operator ratifies. */
@Serializable
data class AdminPreviewRow(
    @SerialName("attestation_id")
    val attestationId: String,
    @SerialName("attesting_key_id")
    val attestingKeyId: String,
    @SerialName("attested_key_id")
    val attestedKeyId: String,
    @SerialName("attestation_type")
    val attestationType: String,
    val dimension: String? = null,
    @SerialName("asserted_at")
    val assertedAt: String,
    @SerialName("cohort_scope")
    val cohortScope: String,
)

/**
 * The blast-radius counts. `per_attester` is only emitted by
 * `POST /v1/admin/preview`; the commit responses carry the same object without
 * it, which is why it defaults to empty rather than being required.
 */
@Serializable
data class AdminPreviewCounts(
    val rows: Int = 0,
    val targets: Int = 0,
    @SerialName("per_attester")
    val perAttester: Map<String, Int> = emptyMap(),
    /** The page filled to the limit: a commit would act on a PAGE, not the set. */
    val truncated: Boolean = false,
)

/**
 * `POST /v1/admin/preview` — exactly what a commit will act on, plus the hash
 * the commit must present.
 *
 * [windowEnforced] is MEASURED by the server, not declared: `substrate` means
 * the time window bound in the query, `application` means this node had to
 * narrow the page itself (and then [windowNote] is present), `none` means no
 * window was asked for.
 */
@Serializable
data class AdminPreviewResponse(
    @SerialName("selection_hash")
    val selectionHash: String,
    val counts: AdminPreviewCounts = AdminPreviewCounts(),
    @SerialName("window_enforced")
    val windowEnforced: String = WINDOW_NONE,
    val targets: List<String> = emptyList(),
    val rows: List<AdminPreviewRow> = emptyList(),
    @SerialName("window_note")
    val windowNote: AdminMessage? = null,
    val note: AdminMessage? = null,
    @SerialName("source_locale")
    val sourceLocale: String? = null,
) {
    companion object {
        const val WINDOW_NONE = "none"
        const val WINDOW_SUBSTRATE = "substrate"
        const val WINDOW_APPLICATION = "application"
    }
}

/**
 * The body EVERY mutating route takes. The op-specific extras are flattened
 * into the same object by the server (`#[serde(flatten)] commit: Commit`), so
 * this one request type is the whole ladder's request shape:
 *
 *  - [communityId] — quarantine / un-quarantine only. Required there.
 *  - [quorumDelegationIds] — descend only. The OTHER authorities; the server
 *    counts distinct ROOTS, not distinct ids.
 *  - [after] — deadmit only. The history bound (`Revocation::revoked_after`),
 *    deliberately NOT the selection's `after`: it bounds what is revoked
 *    without re-scoping the preview, so it does not change the selection hash.
 */
@Serializable
data class AdminLadderCommitRequest(
    val selection: AdminSelectionDto,
    @SerialName("selection_hash")
    val selectionHash: String,
    @SerialName("delegation_id")
    val delegationId: String,
    val reason: String,
    @SerialName("community_id")
    val communityId: String? = null,
    @SerialName("quorum_delegation_ids")
    val quorumDelegationIds: List<String> = emptyList(),
    val after: String? = null,
)

/**
 * **Does this node refuse that key's writes right now — and is that knowable?**
 * Three values because there are three facts: `refused`, `admitted`, and
 * `unreadable` (the corpus could not be read). `unreadable` is NOT `admitted`
 * and must never be rendered as one.
 */
@Serializable
data class AdminStandingDto(
    val standing: String,
    val message: AdminMessage? = null,
) {
    companion object {
        const val REFUSED = "refused"
        const val ADMITTED = "admitted"
        const val UNREADABLE = "unreadable"
    }
}

/** One `{deadmission_id, withdraws_id | error}` entry from `accept-writes`. */
@Serializable
data class AdminWithdrawal(
    @SerialName("deadmission_id")
    val deadmissionId: String? = null,
    @SerialName("withdraws_id")
    val withdrawsId: String? = null,
    val error: String? = null,
)

/**
 * Tier 3's payload leg. `performed=false` with `refusal="bounded_descent_unsupported"`
 * is the server refusing to drive an unbounded eviction from a time-bounded
 * judgement — a refusal that protects history, not a failure.
 */
@Serializable
data class AdminPayloadDescent(
    val performed: Boolean = false,
    val refusal: String? = null,
    val message: AdminMessage? = null,
    val error: String? = null,
    /** The substrate's own eviction report; shape owned by persist. */
    val report: JsonElement? = null,
)

/**
 * One target's outcome. The ladder's routes emit four related shapes into this
 * one union — `recorded`/`failed` entries (judgement ops), `results` entries
 * (quarantine, descend, deadmit) and the write-door results — so every
 * op-specific field is optional and named exactly as the server names it.
 *
 * `outcome` vocabulary by route:
 *  - quarantine: `admitted` | `skipped` | `refused` | `error`
 *  - deadmit:    `revoked` | `error`
 *  - refuse-writes: `refused` | `already_refused` | `error`
 *  - accept-writes: `accepted` | `not_refused` | `error`
 *  - annotate / throttle / un-throttle / re-admit: absent (presence in
 *    `recorded` vs `failed` is the outcome)
 */
@Serializable
data class AdminOpTargetResult(
    @SerialName("target_key_id")
    val targetKeyId: String,
    val outcome: String? = null,
    @SerialName("event_id")
    val eventId: String? = null,
    @SerialName("event_error")
    val eventError: String? = null,
    @SerialName("marker_id")
    val markerId: String? = null,
    @SerialName("revocation_id")
    val revocationId: String? = null,
    @SerialName("deadmission_id")
    val deadmissionId: String? = null,
    /** Quarantine's skip reason, or the substrate's own refusal token. */
    val reason: String? = null,
    /** The folded quarantine state a skip reports. */
    val state: String? = null,
    val error: String? = null,
    val message: AdminMessage? = null,
    @SerialName("standing_before")
    val standingBefore: AdminStandingDto? = null,
    @SerialName("standing_after")
    val standingAfter: AdminStandingDto? = null,
    @SerialName("payload_descent")
    val payloadDescent: AdminPayloadDescent? = null,
    val withdrew: List<AdminWithdrawal> = emptyList(),
    val errors: List<AdminWithdrawal> = emptyList(),
)

/** Tier 3's quorum report: distinct authority ROOTS, each independently re-walked. */
@Serializable
data class AdminQuorumDto(
    val required: Int = 0,
    @SerialName("distinct_roots")
    val distinctRoots: Int = 0,
    val roots: List<String> = emptyList(),
    @SerialName("delegation_ids")
    val delegationIds: List<String> = emptyList(),
)

/** How far a reversal op actually reaches: `substrate` | `symmetric` | `evidence_only`. */
@Serializable
data class AdminReversalReach(
    val reach: String,
    val note: AdminMessage? = null,
)

/**
 * A committed ladder op.
 *
 * **`reversal` carries TWO different shapes on the wire and this is deliberate
 * on the server's side, so it is typed as raw JSON here rather than guessed at:**
 * the judgement/quarantine routes emit `{reach, note:{id,text}}`
 * ([reversalReach]) while `refuse-writes` emits a bare `{id,text}`
 * ([reversalMessage]). Decoding it as either one alone silently drops the other.
 */
@Serializable
data class AdminOpResponse(
    val op: String,
    val tier: Int = 0,
    @SerialName("required_scope")
    val requiredScope: String? = null,
    @SerialName("selection_hash")
    val selectionHash: String? = null,
    @SerialName("source_locale")
    val sourceLocale: String? = null,
    val counts: AdminPreviewCounts? = null,
    /** Judgement ops: one entry per target whose tombstone landed. */
    val recorded: List<AdminOpTargetResult> = emptyList(),
    /** Judgement ops: one entry per target whose tombstone did NOT land. */
    val failed: List<AdminOpTargetResult> = emptyList(),
    /** Quarantine / descend / deadmit / write-door: per-target outcomes. */
    val results: List<AdminOpTargetResult> = emptyList(),
    @SerialName("community_id")
    val communityId: String? = null,
    val quorum: AdminQuorumDto? = null,
    /** Tier 3: the judgement carried a time bound, so the payload leg was refused. */
    val bounded: Boolean? = null,
    val after: String? = null,
    @SerialName("revoked_after")
    val revokedAfter: String? = null,
    /** AV-77 gate axis: `armed` | `dormant` | `foreign_identity`. */
    @SerialName("deadmission_gate")
    val deadmissionGate: String? = null,
    /** What the op reaches. */
    val enforcement: AdminMessage? = null,
    /** Tier 3 only, and it says "irreversible" out loud. */
    val irreversible: AdminMessage? = null,
    /** What the op does NOT reach — stated so an operator stops inferring more. */
    @SerialName("not_reached")
    val notReached: AdminMessage? = null,
    val reversal: JsonElement? = null,
) {
    /** `{reach, note}` — the judgement / quarantine routes. Null for the write door. */
    val reversalReach: AdminReversalReach?
        get() {
            val obj = reversal as? JsonObject ?: return null
            val reach = (obj["reach"] as? JsonPrimitive)?.contentOrNullSafe() ?: return null
            val note = obj["note"] as? JsonObject
            return AdminReversalReach(
                reach = reach,
                note = note?.toAdminMessage(),
            )
        }

    /** A bare `{id, text}` — `refuse-writes`. Null for the shapes that carry `reach`. */
    val reversalMessage: AdminMessage?
        get() {
            val obj = reversal as? JsonObject ?: return null
            if (obj.containsKey("reach")) return null
            return obj.toAdminMessage()
        }

    companion object {
        const val GATE_ARMED = "armed"
        const val GATE_DORMANT = "dormant"
        const val GATE_FOREIGN_IDENTITY = "foreign_identity"
    }
}

/**
 * A refusal, in the ONE response contract every route on this module shares.
 * [refusal] is the stable program token to branch on; [message] is the
 * localizable pair to render.
 */
@Serializable
data class AdminRefusal(
    val refused: Boolean = true,
    val refusal: String = "",
    @SerialName("source_locale")
    val sourceLocale: String? = null,
    val message: AdminMessage? = null,
    /** `quorum_insufficient` only. */
    @SerialName("quorum_required")
    val quorumRequired: Int? = null,
    @SerialName("quorum_distinct_roots")
    val quorumDistinctRoots: Int? = null,
    /** `preview_hash_mismatch` only — with the preview that IS current. */
    @SerialName("presented_selection_hash")
    val presentedSelectionHash: String? = null,
    @SerialName("current_selection_hash")
    val currentSelectionHash: String? = null,
    val current: AdminPreviewResponse? = null,
) {
    companion object {
        const val PREVIEW_HASH_MISMATCH = "preview_hash_mismatch"
        const val QUORUM_INSUFFICIENT = "quorum_insufficient"
        const val ATTRIBUTION_ABSENT = "attribution_absent"
        const val SELECTION_UNPREDICATED = "selection_unpredicated"
        const val DEADMISSION_GATE_DORMANT = "deadmission_gate_dormant"
    }
}

/**
 * `POST /v1/admin/preview` outcome. A refusal is DATA, not an exception: its
 * text is the product, and losing it would leave the operator with a spinner.
 */
sealed class AdminPreviewOutcome {
    data class Ok(val preview: AdminPreviewResponse) : AdminPreviewOutcome()
    data class Refused(val status: Int, val refusal: AdminRefusal) : AdminPreviewOutcome()
}

/** A mutating ladder call's outcome, same reasoning as [AdminPreviewOutcome]. */
sealed class AdminOpOutcome {
    data class Ok(val response: AdminOpResponse) : AdminOpOutcome()
    data class Refused(val status: Int, val refusal: AdminRefusal) : AdminOpOutcome()
}

/**
 * The three persist-side delegation scopes the ladder's rungs take.
 *
 * Top-level rather than in [AdminLadderOp]'s companion because an enum's ENTRIES
 * are initialized before its companion object is, so an entry cannot read a
 * constant that lives there. The companion re-exports them for callers.
 */
private const val LADDER_SCOPE_REVIEW = "review"
private const val LADDER_SCOPE_MODERATE = "moderate"
private const val LADDER_SCOPE_SLASH = "slash"

/**
 * **The ladder, as one closed set.** Route strings live HERE and nowhere else,
 * so a UI cannot send tier 4 down tier 0's door.
 *
 * [enforcementMessageId] / [notReachedMessageId] / [reversalMessageId] are the
 * server's OWN message ids — the same ids its responses carry. The confirmation
 * flow resolves them from the bundle BEFORE the act, so the operator reads the
 * op's stated limits while they can still decline, and reads the identical
 * sentence in the response afterwards.
 */
enum class AdminLadderOp(
    val route: String,
    val tier: Int,
    /** The persist-side delegation scope the named delegation must itself carry. */
    val requiredScope: String,
    val labelMessageId: String,
    val enforcementMessageId: String,
    val notReachedMessageId: String? = null,
    val reversalMessageId: String? = null,
    /** Quarantine's marker is filed under a community's authority. */
    val requiresCommunityId: Boolean = false,
    /** Tier 3 takes a quorum of DISTINCT authority roots, not one chain. */
    val requiresQuorum: Boolean = false,
    /** Tier 4's revocation accepts a history bound that does not re-scope the preview. */
    val acceptsRevokedAfter: Boolean = false,
    /** There is no un-descend. */
    val irreversible: Boolean = false,
) {
    ANNOTATE(
        route = "/v1/admin/annotate",
        tier = 0,
        requiredScope = LADDER_SCOPE_REVIEW,
        labelMessageId = "moderation.ladder.op.annotate",
        enforcementMessageId = "admin.enforcement.annotate",
    ),
    THROTTLE(
        route = "/v1/admin/throttle",
        tier = 1,
        requiredScope = LADDER_SCOPE_MODERATE,
        labelMessageId = "moderation.ladder.op.throttle",
        enforcementMessageId = "admin.enforcement.throttle",
    ),
    UN_THROTTLE(
        route = "/v1/admin/un-throttle",
        tier = 1,
        requiredScope = LADDER_SCOPE_MODERATE,
        labelMessageId = "moderation.ladder.op.un_throttle",
        enforcementMessageId = "admin.enforcement.throttle",
        reversalMessageId = "admin.reversal.symmetric",
    ),
    QUARANTINE(
        route = "/v1/admin/quarantine",
        tier = 2,
        requiredScope = LADDER_SCOPE_SLASH,
        labelMessageId = "moderation.ladder.op.quarantine",
        enforcementMessageId = "admin.enforcement.quarantine",
        requiresCommunityId = true,
    ),
    UN_QUARANTINE(
        route = "/v1/admin/un-quarantine",
        tier = 2,
        requiredScope = LADDER_SCOPE_SLASH,
        labelMessageId = "moderation.ladder.op.un_quarantine",
        enforcementMessageId = "admin.enforcement.quarantine",
        reversalMessageId = "admin.reversal.substrate",
        requiresCommunityId = true,
    ),
    DESCEND(
        route = "/v1/admin/descend",
        tier = 3,
        requiredScope = LADDER_SCOPE_SLASH,
        labelMessageId = "moderation.ladder.op.descend",
        enforcementMessageId = "admin.enforcement.descend",
        notReachedMessageId = "admin.descend.not_reached",
        requiresQuorum = true,
        irreversible = true,
    ),
    DEADMIT(
        route = "/v1/admin/deadmit",
        tier = 4,
        requiredScope = LADDER_SCOPE_SLASH,
        labelMessageId = "moderation.ladder.op.deadmit",
        enforcementMessageId = "admin.enforcement.deadmit",
        acceptsRevokedAfter = true,
    ),
    RE_ADMIT(
        route = "/v1/admin/re-admit",
        tier = 4,
        requiredScope = LADDER_SCOPE_SLASH,
        labelMessageId = "moderation.ladder.op.re_admit",
        enforcementMessageId = "admin.enforcement.re_admit",
        reversalMessageId = "admin.reversal.evidence_only",
    ),
    REFUSE_WRITES(
        route = "/v1/admin/refuse-writes",
        tier = 4,
        requiredScope = LADDER_SCOPE_SLASH,
        labelMessageId = "moderation.ladder.op.refuse_writes",
        enforcementMessageId = "admin.enforcement.refuse_writes",
        notReachedMessageId = "admin.refuse_writes.not_reached",
        reversalMessageId = "admin.refuse_writes.reversal",
    ),
    ACCEPT_WRITES(
        route = "/v1/admin/accept-writes",
        tier = 4,
        requiredScope = LADDER_SCOPE_SLASH,
        labelMessageId = "moderation.ladder.op.accept_writes",
        enforcementMessageId = "admin.enforcement.accept_writes",
        notReachedMessageId = "admin.accept_writes.not_reached",
    ),
    ;

    companion object {
        const val SCOPE_REVIEW = LADDER_SCOPE_REVIEW
        const val SCOPE_MODERATE = LADDER_SCOPE_MODERATE
        const val SCOPE_SLASH = LADDER_SCOPE_SLASH

        /** Tier 3's floor: distinct authority ROOTS (`DESCEND_QUORUM_MIN`). */
        const val DESCEND_QUORUM_MIN = 2
    }
}

/** `JsonNull` reads back as the literal `"null"`; that is absence, not content. */
private fun JsonPrimitive.contentOrNullSafe(): String? =
    if (isString) content else content.takeIf { it != "null" }

private fun JsonObject.toAdminMessage(): AdminMessage? {
    val id = (this["id"] as? JsonPrimitive)?.contentOrNullSafe() ?: return null
    val text = (this["text"] as? JsonPrimitive)?.contentOrNullSafe() ?: return null
    return AdminMessage(id = id, text = text)
}
