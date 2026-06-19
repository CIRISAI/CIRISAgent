package ai.ciris.mobile.shared.models.safety

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Wire models for the holistic **SAFETY** surface — the client-side mirror of
 * the `CIRISServer/src/safety/` Rust modules (v0.4.6). Every field here is matched 1:1 to the
 * server's serde request/response shapes; the comments cite the originating Rust.
 *
 * ARCHITECTURE: the app holds NO keys and performs NO crypto. Every safety
 * action is a plain localhost POST/GET/DELETE against THIS device's local node
 * (`http://127.0.0.1:8080`, [ai.ciris.mobile.shared.api.CIRISApiClient.LOCAL_NODE_URL]).
 * The node's substrate does all signing / admission. The app only drives it and
 * surfaces the result.
 *
 * Honesty discipline (kept TRUE on the wire, mirrored from the .rs docs):
 *  - `self`-level age assurance is unfalsifiable from inside the fabric;
 *    misdeclaration routes to adjudication, NEVER slashing.
 *  - the named-moderator existence invariant FAILS SECURE (no moderator ⇒ no
 *    group, ever — "better no group than an unmoderated one").
 *  - the watchlist is opt-in / per-group / NEVER global; it cannot reach private
 *    (self/family) content; CSAM hashes are operator-provisioned, never shipped.
 */

// ─── age-assurance (age.rs) ─────────────────────────────────────────────────

/**
 * The self-declared age band — `age.rs::AgeBand` (`#[serde(rename_all =
 * "snake_case")]` ⇒ wire tokens `minor` / `adult`).
 *
 * The onboarding "state your age range" selector resolves to one of these. The
 * protective default for an unknown/declined viewer is [MINOR] (gated OUT of
 * adult content).
 */
@Serializable
enum class AgeBand {
    @SerialName("minor")
    MINOR,

    @SerialName("adult")
    ADULT,
}

/**
 * The assurance LEVEL — `age.rs::AssuranceLevel`. Only [SELF_DECLARED] is wired
 * for the app: a subject CANNOT self-mint provider/government adulthood (the
 * server rejects a non-`self` level on the self-signed route with 400). The
 * higher rungs come from an out-of-fabric verifier and are read-only here.
 */
@Serializable
enum class AssuranceLevel {
    @SerialName("self")
    SELF_DECLARED,

    @SerialName("provider")
    PROVIDER,

    @SerialName("government")
    GOVERNMENT,
}

/** A resolved age assurance — `age.rs::AgeAssurance` (`{ band, level }`). */
@Serializable
data class AgeAssurance(
    val band: AgeBand,
    val level: AssuranceLevel,
)

/**
 * Request body for `POST /v1/safety/age-assurance` — `age.rs::SetAgeRequest`.
 *
 * `level` is optional and defaults to `self` server-side; we leave it null so
 * the node applies the self-declared default (the only level the app may set).
 */
@Serializable
data class SetAgeRequest(
    @SerialName("subject_key_id")
    val subjectKeyId: String,
    val band: AgeBand,
    val level: AssuranceLevel? = null,
)

/** Response of `POST /v1/safety/age-assurance` — `age.rs::SetAgeResponse`. */
@Serializable
data class SetAgeResponse(
    @SerialName("attestation_id")
    val attestationId: String,
    val dimension: String,
)

/**
 * Response of `GET /v1/safety/age-assurance/{key_id}` —
 * `age.rs::AgeStatusResponse`. `assurance` is null when NO assurance is on
 * record (the caller MUST treat null protectively).
 */
@Serializable
data class AgeStatusResponse(
    @SerialName("key_id")
    val keyId: String,
    val assurance: AgeAssurance? = null,
)

/**
 * Response of `GET /v1/safety/status/{key_id}` — the aggregate safety status
 * (`age.rs::safety_status`, an ad-hoc JSON object). The `honesty` block is kept
 * TRUE on the wire by the server and surfaced verbatim.
 */
@Serializable
data class SafetyStatusResponse(
    @SerialName("key_id")
    val keyId: String,
    @SerialName("age_assurance")
    val ageAssurance: AgeAssurance? = null,
    val honesty: SafetyHonesty? = null,
)

/** The honest-framing block inside [SafetyStatusResponse]. */
@Serializable
data class SafetyHonesty(
    @SerialName("self_level_unfalsifiable")
    val selfLevelUnfalsifiable: Boolean = true,
    @SerialName("misdeclaration_routes_to_adjudication")
    val misdeclarationRoutesToAdjudication: String? = null,
)

// ─── moderation (moderation.rs) ─────────────────────────────────────────────

/**
 * The duty a moderation action exercises — `moderation.rs::Duty`
 * (`#[serde(rename_all = "snake_case")]` ⇒ `moderate` / `takedown` / `review`).
 * These map 1:1 to persist's enforced delegation-scope tokens.
 */
@Serializable
enum class ModerationDuty {
    @SerialName("moderate")
    MODERATE,

    @SerialName("takedown")
    TAKEDOWN,

    @SerialName("review")
    REVIEW,
}

/**
 * Request body for `POST /v1/safety/moderation` — `moderation.rs::ModerationRequest`.
 *
 * `payload` is free-form (reason / evidence refs). We model it as an optional
 * string note carried under a `{"note": …}` object so the simplest report path
 * (a textual reason) round-trips without the app constructing arbitrary JSON.
 */
@Serializable
data class ModerationRequest(
    @SerialName("signer_key_id")
    val signerKeyId: String,
    @SerialName("community_key_id")
    val communityKeyId: String,
    val duty: ModerationDuty,
    /** The `moderation:{allegation_type}` token (e.g. `csam`, `harassment`,
     *  `age_assurance_misdeclaration`). Free-vocab server-side. */
    @SerialName("allegation_type")
    val allegationType: String,
    @SerialName("target_key_ids")
    val targetKeyIds: List<String> = emptyList(),
    val payload: ModerationPayload? = null,
)

/** Free-form action payload — a textual reason is the common report path. */
@Serializable
data class ModerationPayload(
    val note: String? = null,
)

/** Response of `POST /v1/safety/moderation` — `moderation.rs::ModerationResponse`. */
@Serializable
data class ModerationResponse(
    @SerialName("attestation_id")
    val attestationId: String,
    val duty: ModerationDuty,
)

// ─── named-moderator existence invariant (named.rs) ─────────────────────────

/**
 * The existence-gate verdict for a community — `named.rs::ExistenceVerdict`,
 * an internally-tagged enum (`#[serde(tag = "verdict", rename_all =
 * "snake_case")]`). The variant is in [verdict]; the variant-specific fields
 * are flattened alongside it (all nullable so one model covers all three arms):
 *
 *  - `operate`     → [moderatorPresent] = true.
 *  - `auto_promote`→ [candidateKeyId] + [hardCase] set.
 *  - `quiesce`     → [hardCase] set (FAIL SECURE — the group must not federate).
 */
@Serializable
data class ExistenceVerdict(
    val verdict: String,
    @SerialName("moderator_present")
    val moderatorPresent: Boolean? = null,
    @SerialName("candidate_key_id")
    val candidateKeyId: String? = null,
    @SerialName("hard_case")
    val hardCase: String? = null,
)

/**
 * Response of `GET /v1/safety/named-moderator/{community_key_id}` —
 * `named.rs::named_status` (an ad-hoc JSON object). `fails_secure` is always
 * true on the wire and surfaced verbatim (the load-bearing honest framing).
 */
@Serializable
data class NamedModeratorResponse(
    @SerialName("community_key_id")
    val communityKeyId: String,
    val existence: ExistenceVerdict,
    @SerialName("fails_secure")
    val failsSecure: Boolean = true,
)

// ─── watchlist (watchlist.rs) ───────────────────────────────────────────────

/** CSAM vs other-content — `watchlist.rs::WatchlistClass`. */
@Serializable
enum class WatchlistClass {
    @SerialName("csam")
    CSAM,

    @SerialName("other_content")
    OTHER_CONTENT,
}

/** AlertOnly (shadow) vs Enforce — `watchlist.rs::WatchlistMode`. */
@Serializable
enum class WatchlistMode {
    @SerialName("alert_only")
    ALERT_ONLY,

    @SerialName("enforce")
    ENFORCE,
}

/**
 * A watchlist enable/disable — `watchlist.rs::WatchlistEnable`. The POST route
 * flattens this alongside a `signer_key_id` (`#[serde(flatten)]`), so the wire
 * body is `{ signer_key_id, group_key_id, watchlist_id, class, enabled, mode,
 * route_to_moderator? }`. [WatchlistRequest] models that flattened body.
 */
@Serializable
data class WatchlistEnable(
    @SerialName("group_key_id")
    val groupKeyId: String,
    @SerialName("watchlist_id")
    val watchlistId: String,
    @SerialName("class")
    val watchlistClass: WatchlistClass,
    val enabled: Boolean,
    val mode: WatchlistMode,
    @SerialName("route_to_moderator")
    val routeToModerator: String? = null,
)

/**
 * The flattened request body for `POST /v1/safety/watchlist` — mirrors
 * `watchlist.rs::watchlist`'s inline `Req { signer_key_id, #[flatten] enable }`.
 */
@Serializable
data class WatchlistRequest(
    @SerialName("signer_key_id")
    val signerKeyId: String,
    @SerialName("group_key_id")
    val groupKeyId: String,
    @SerialName("watchlist_id")
    val watchlistId: String,
    @SerialName("class")
    val watchlistClass: WatchlistClass,
    val enabled: Boolean,
    val mode: WatchlistMode,
    @SerialName("route_to_moderator")
    val routeToModerator: String? = null,
)

/** Response of `POST /v1/safety/watchlist` — `watchlist.rs::WatchlistResponse`. */
@Serializable
data class WatchlistResponse(
    @SerialName("attestation_id")
    val attestationId: String,
    val enabled: Boolean,
    val dimension: String,
)

/**
 * Response of `GET /v1/safety/watchlist/{group_key_id}` —
 * `watchlist.rs::list_enables` (an ad-hoc JSON object). The `honesty` block is
 * kept TRUE on the wire and surfaced verbatim (per-group/never-global, cannot
 * reach private content, hashes operator-provisioned, NCMEC report is the
 * operator's duty).
 */
@Serializable
data class WatchlistListResponse(
    @SerialName("group_key_id")
    val groupKeyId: String,
    val enables: List<WatchlistEnable> = emptyList(),
    val honesty: WatchlistHonesty? = null,
)

/** The honest-framing block inside [WatchlistListResponse]. */
@Serializable
data class WatchlistHonesty(
    @SerialName("per_group_never_global")
    val perGroupNeverGlobal: Boolean = true,
    @SerialName("cannot_reach_self_family_private_content")
    val cannotReachSelfFamilyPrivateContent: Boolean = true,
    @SerialName("hashes_operator_provisioned")
    val hashesOperatorProvisioned: Boolean = true,
    @SerialName("ncmec_report_is_operator_duty")
    val ncmecReportIsOperatorDuty: Boolean = true,
)
