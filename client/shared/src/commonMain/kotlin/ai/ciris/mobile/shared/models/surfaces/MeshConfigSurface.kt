package ai.ciris.mobile.shared.models.surfaces

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

/**
 * **The Mesh Configuration surface** (CIRISServer#346 / #365, `src/mesh_config_surface.rs`).
 *
 * ```text
 * GET  /v1/mesh-config           effective values + provenance + TTLs + the registry
 * GET  /v1/mesh-config/history   every mesh-config row this node holds
 * POST /v1/mesh-config/durable   the durable path (supports dry_run)
 * POST /v1/mesh-config/relief    the emergency relief path (ttl_hours mandatory)
 * ```
 *
 * Two properties of the wire are load-bearing and are preserved verbatim here
 * rather than normalised away:
 *
 * 1. **`consumption` travels with every effective value.** `effective: 10` is a
 *    TRUE statement only next to `wired`; beside `elsewhere` / `unbuilt` /
 *    `unreachable` it is a knob that confirms rather than one that works. The
 *    label is a first-class field on both the registry and the settings, and the
 *    UI is required to render it beside the number.
 * 2. **Absence is not zero.** [MeshConfigRead.settings] and
 *    [MeshConfigRead.roots] are `null` — not empty — exactly when the plane
 *    could not be read, and the `standing` token says which of the five facts
 *    produced "everything at baseline". A non-null empty list and a null are
 *    different answers and must not collapse into one.
 */

// ═════════════════════════════════════════════════════════════════════════════
//  Consumption — the honest label (CIRISServer#365)
// ═════════════════════════════════════════════════════════════════════════════

/**
 * **Does anything in this build actually read this key?**
 *
 * Four states, from `src/mesh_config_effect.rs::Consumption`:
 *
 * | [state]       | what the effective value means                                        |
 * |---------------|-----------------------------------------------------------------------|
 * | `wired`       | a loop in THIS build reads it — the value is in force                  |
 * | `elsewhere`   | the consumer lives in another component (edge); this node cannot say   |
 * | `unbuilt`     | no consumer exists anywhere — the row is accepted and inert            |
 * | `unreachable` | a consumer EXISTS and this node cannot reach it: accepted, folded, and |
 * |               | STILL not in effect — and it would not stop applying at TTL expiry either |
 *
 * Only `wired` sets [MeshConfigSetting.consumed].
 */
@Serializable
data class MeshConfigConsumption(
    /** `wired` | `elsewhere` | `unbuilt` | `unreachable`. */
    val state: String = "",
    /** `mesh_config.consumption.{state}` — the sentence, localizable. */
    val message: SurfaceMessage? = null,
    /** `wired` only — the accessor a consumer reads through. */
    val site: String? = null,
    /** `wired` only — where the effect lands. */
    val effect: String? = null,
    /** `elsewhere` / `unreachable` — the component that owns the consumer. */
    val owner: String? = null,
    /**
     * `unreachable` only — what must change before the value can be honoured.
     * Raw source text naming Rust symbols in another repo: NOT localizable and
     * never paraphrased (the server says so explicitly).
     */
    val blocker: String? = null,
    /** The issue tracking the gap, for every non-`wired` arm. */
    @SerialName("tracked_by") val trackedBy: String? = null,
)

// ═════════════════════════════════════════════════════════════════════════════
//  TTL — data plus a message id, never a pre-baked sentence
// ═════════════════════════════════════════════════════════════════════════════

/**
 * A TTL, counting down. Three arms because "no TTL", "expired" and "running"
 * are three facts and a `null` would collapse the first two: [bounded] `false`
 * is "applies until superseded", [expired] `true` is "the fold already drops
 * it".
 *
 * [remainingSeconds] IS the countdown — a relief that lapses with nobody filing
 * anything is a feature, and this is how an operator watches it happen.
 */
@Serializable
data class MeshConfigTtl(
    val bounded: Boolean = false,
    @SerialName("expires_at") val expiresAt: String? = null,
    @SerialName("remaining_seconds") val remainingSeconds: Long? = null,
    val expired: Boolean? = null,
    val message: SurfaceMessage? = null,
)

// ═════════════════════════════════════════════════════════════════════════════
//  The registry — persist's closed key set, projected
// ═════════════════════════════════════════════════════════════════════════════

/** One registered key, with every fact persist's `MeshConfigKeySpec` carries. */
@Serializable
data class MeshConfigRegistryEntry(
    val key: String = "",
    /** The envelope dimension (`paths::DIMENSION` — the wire spells it `dimension`). */
    val dimension: String? = null,
    /** Which direction means MORE flow — roots may only tighten beneath consent. */
    val polarity: String = "",
    val unit: String = "",
    val min: Long = 0,
    val max: Long = 0,
    @SerialName("owner_default") val ownerDefault: Long = 0,
    /** The processor that reads this key… */
    val consumer: String = "",
    /** …and the specific knob within it. */
    val knob: String = "",
    /** `true` ONLY on the `wired` arm. */
    val consumed: Boolean = false,
    val consumption: MeshConfigConsumption? = null,
)

// ═════════════════════════════════════════════════════════════════════════════
//  One resolved setting
// ═════════════════════════════════════════════════════════════════════════════

/**
 * **Where one key's current value came from.** Three arms, because a key at its
 * baseline because nobody spoke and a key at its baseline because a root asked
 * for exactly that value are different provenance:
 * `baseline_unspoken` / `baseline_not_moved` / `root`.
 */
@Serializable
data class MeshConfigProvenance(
    val source: String = "",
    val message: SurfaceMessage? = null,
    @SerialName("decided_by_root") val decidedByRoot: String? = null,
    @SerialName("row_id") val rowId: String? = null,
    @SerialName("decided_by") val decidedBy: String? = null,
    @SerialName("delegation_id") val delegationId: String? = null,
    /** `durable` | `emergency`. */
    val form: String? = null,
    val grounds: String? = null,
)

/**
 * One root's answer for one key — including the roots that lost and the roots
 * that were CLAMPED. [asked] is reported raw on purpose: auditing a hostile root
 * means seeing what it asked for, not only what it got.
 */
@Serializable
data class MeshConfigRootValue(
    @SerialName("root_ref") val rootRef: String = "",
    val asked: Long = 0,
    val effective: Long = 0,
    /** `true` iff this root tried to expand past the owner's consent. */
    val clamped: Boolean = false,
    @SerialName("row_id") val rowId: String = "",
    val form: String = "",
    val ttl: MeshConfigTtl? = null,
)

/** The resolved setting for one key: what the node runs, and how it got there. */
@Serializable
data class MeshConfigSetting(
    val key: String = "",
    val unit: String = "",
    val polarity: String = "",
    val consumer: String = "",
    val knob: String = "",
    /** What the node's OWNER consented to — the ceiling. */
    val baseline: Long = 0,
    /** What the fold resolved. Never means more flow than [baseline]. */
    val effective: Long = 0,
    /** `true` iff some root moved this key off the baseline. */
    val relieved: Boolean = false,
    /** Whether anything in THIS build reads [effective]. See [consumption]. */
    val consumed: Boolean = false,
    val consumption: MeshConfigConsumption? = null,
    val provenance: MeshConfigProvenance? = null,
    val ttl: MeshConfigTtl? = null,
    @SerialName("per_root") val perRoot: List<MeshConfigRootValue> = emptyList(),
    @SerialName("clamped_roots") val clampedRoots: List<String> = emptyList(),
)

// ═════════════════════════════════════════════════════════════════════════════
//  GET /v1/mesh-config
// ═════════════════════════════════════════════════════════════════════════════

/** A subscribed trust root whose rows could not be listed, with the reason. */
@Serializable
data class MeshConfigUnreadableRoot(
    @SerialName("root_ref") val rootRef: String = "",
    val error: String = "",
)

/** The emergency-relief bound, READ from the substrate so a form can bound its input. */
@Serializable
data class MeshConfigEmergencyBound(
    @SerialName("max_ttl_hours") val maxTtlHours: Long = 0,
    val message: SurfaceMessage? = null,
)

/** One entry of this node's own consent baseline. */
@Serializable
data class MeshConfigBaselineEntry(
    val key: String = "",
    val value: Long = 0,
)

/**
 * `GET /v1/mesh-config`.
 *
 * The five [standing] tokens are five different facts that all look like
 * "everything at baseline": `unreadable` / `no_subscription` / `no_rows_held` /
 * `none_binding` / `configured`. On `unreadable` the server sends
 * `settings: null` and `roots: null` — never zeros — and attaches [error].
 *
 * The gate refusals (401/403/503 before the plane is read) arrive on the SAME
 * shape with [refused] set and no [standing]; [refusal] carries the token.
 */
@Serializable
data class MeshConfigRead(
    @SerialName("source_locale") val sourceLocale: String = "en",
    @SerialName("namespace_family") val namespaceFamily: String = "",
    @SerialName("dimension_prefix") val dimensionPrefix: String = "",
    @SerialName("generated_at") val generatedAt: String = "",
    val standing: String = "",
    @SerialName("standing_message") val standingMessage: SurfaceMessage? = null,
    val registry: List<MeshConfigRegistryEntry> = emptyList(),
    val emergency: MeshConfigEmergencyBound? = null,
    val durability: SurfaceMessage? = null,
    /** `null` = the plane could not be read. Empty = read cleanly, no roots. */
    val roots: List<String>? = null,
    @SerialName("unreadable_roots") val unreadableRoots: List<MeshConfigUnreadableRoot> = emptyList(),
    @SerialName("node_key_id") val nodeKeyId: String? = null,
    @SerialName("rows_held") val rowsHeld: Int? = null,
    /** `null` = unknown, NOT "nothing set". */
    val settings: List<MeshConfigSetting>? = null,
    val baseline: List<MeshConfigBaselineEntry> = emptyList(),
    val error: String? = null,
    val refused: Boolean = false,
    val refusal: String? = null,
    /** Present on the refusal shape only. */
    val message: SurfaceMessage? = null,
)

// ═════════════════════════════════════════════════════════════════════════════
//  GET /v1/mesh-config/history
// ═════════════════════════════════════════════════════════════════════════════

/**
 * One held mesh-config row.
 *
 * [counted] and [binding] are read off persist's fold and are two DIFFERENT
 * facts: `counted` = the fold used this row as its answer for that (root, key)
 * at this instant; `binding` = that answer also won across roots. A row can be
 * counted and not binding — its root spoke and a tighter root won.
 */
@Serializable
data class MeshConfigHistoryRow(
    @SerialName("attestation_id") val attestationId: String = "",
    val dimension: String? = null,
    /** `null` = a row on this plane whose key is NOT in the closed registry. */
    val key: String? = null,
    val value: Long? = null,
    @SerialName("root_ref") val rootRef: String? = null,
    val form: String? = null,
    val author: String = "",
    @SerialName("delegation_id") val delegationId: String? = null,
    @SerialName("ratifies_row_id") val ratifiesRowId: String? = null,
    val grounds: String? = null,
    @SerialName("asserted_at") val assertedAt: String = "",
    val scrubs: Int = 0,
    val ttl: MeshConfigTtl? = null,
    val counted: Boolean = false,
    val binding: Boolean = false,
)

/**
 * `GET /v1/mesh-config/history`. Five [standing] tokens again, and `partial` is
 * its own arm: some roots read, some did not, so the rows below are REAL and the
 * set is INCOMPLETE.
 */
@Serializable
data class MeshConfigHistory(
    @SerialName("source_locale") val sourceLocale: String = "en",
    @SerialName("generated_at") val generatedAt: String = "",
    val standing: String = "",
    @SerialName("standing_message") val standingMessage: SurfaceMessage? = null,
    val roots: List<String> = emptyList(),
    @SerialName("unreadable_roots") val unreadableRoots: List<MeshConfigUnreadableRoot> = emptyList(),
    val total: Int? = null,
    val truncated: Boolean = false,
    /** `null` = nothing could be read. */
    val rows: List<MeshConfigHistoryRow>? = null,
    @SerialName("truncation_message") val truncationMessage: SurfaceMessage? = null,
    val error: String? = null,
    val refused: Boolean = false,
    val refusal: String? = null,
    val message: SurfaceMessage? = null,
)

// ═════════════════════════════════════════════════════════════════════════════
//  The two write paths
// ═════════════════════════════════════════════════════════════════════════════

/**
 * `POST /v1/mesh-config/relief` — the emergency path. `ttl_hours` is NOT
 * optional: relief that does not expire is not relief. The BOUND is the
 * substrate's ([MeshConfigEmergencyBound.maxTtlHours], refused `ttl_too_long`),
 * so this client bounds its input and clamps nothing.
 */
@Serializable
data class MeshConfigReliefRequest(
    val key: String,
    val value: Long,
    @SerialName("root_ref") val rootRef: String,
    @SerialName("delegation_id") val delegationId: String,
    val grounds: String,
    @SerialName("ttl_hours") val ttlHours: Long,
)

/** `POST /v1/mesh-config/durable` — the durable path. */
@Serializable
data class MeshConfigDurableRequest(
    val key: String,
    val value: Long,
    @SerialName("root_ref") val rootRef: String,
    @SerialName("delegation_id") val delegationId: String,
    val grounds: String,
    /** The emergency row this makes permanent, when there is one. */
    @SerialName("ratifies_row_id") val ratifiesRowId: String? = null,
    /** Return the canonical bytes WITHOUT signing or submitting. */
    @SerialName("dry_run") val dryRun: Boolean = false,
)

/**
 * The answer from either write path, and from a `dry_run`.
 *
 * Exactly one of [admitted] / [refused] is set on a real submission; [refusal]
 * is persist's own token (`mesh_config.refusal.{token}` is the message id) and
 * this client decides nothing about it.
 */
@Serializable
data class MeshConfigWriteResult(
    @SerialName("source_locale") val sourceLocale: String = "en",
    @SerialName("dry_run") val dryRun: Boolean = false,
    val form: String? = null,
    val key: String? = null,
    val value: Long? = null,
    @SerialName("root_ref") val rootRef: String? = null,
    @SerialName("attestation_id") val attestationId: String? = null,
    /** The exact bytes a co-signer must sign. */
    @SerialName("payload_sha256") val payloadSha256: String? = null,
    val envelope: JsonElement? = null,
    val ttl: MeshConfigTtl? = null,
    val admitted: Boolean = false,
    val refused: Boolean = false,
    val refusal: String? = null,
    val message: SurfaceMessage? = null,
)
