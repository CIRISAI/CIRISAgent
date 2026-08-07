package ai.ciris.mobile.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * `GET /v1/node/state` — the composed operator surface (CIRISServer#356 /
 * #369 / #370, `src/operator_surface.rs`).
 *
 * **The one rule this file exists to keep.** The server separates its zeroes by
 * TOKEN, not merely by band: "we could not ask the corpus" (`unreadable`) and
 * "the corpus holds nothing" (`never_admitted`) and "it holds traces, none
 * recent" (`dark`) are three different facts that a naive client collapses into
 * one empty state. `FSD/RCA_INGEST_REJECTION_2026-08-05.md` is what that
 * collapse costs: the trace plane was dead for 71 hours and every layer was
 * individually right, because nothing turned "nothing is arriving" into a
 * signal a human saw.
 *
 * So: **no field here is nullable-because-convenient.** A standing token is kept
 * as its raw wire string AND parsed into a closed enum, and a token this client
 * does not recognise parses to `null` rather than to a healthy default — a
 * client one version behind the server must render "this reading is newer than
 * this app", never green.
 *
 * Every operator-facing string arrives as an [OperatorMessage] `{id, text}`
 * pair. The `id` resolves through the localization bundle (all 200 server ids
 * ship translated); `text` is the English source, used only as a marked
 * fallback. Never render a hardcoded English sentence of our own in its place.
 */

// ─────────────────────────────────────────────────────────────────────────────
// The localizable pair.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * A localizable server string: a stable [id] plus its English source [text].
 *
 * Resolve [id] through the localization bundle first; fall back to [text] only
 * when the bundle has no entry (which is the server being ahead of the app).
 */
@Serializable
data class OperatorMessage(
    val id: String = "",
    val text: String = "",
)

/** One composed source, present or unavailable-with-a-reason. */
@Serializable
data class OperatorSource(
    @SerialName("produced_by")
    val producedBy: String = "",
    /** `false` means this source contributed NOTHING — not that it read clean. */
    val present: Boolean = false,
    val unavailable: OperatorMessage? = null,
    /** The error text that stopped the read, when there was one. */
    val detail: String? = null,
)

/** The four sources the surface composes, each with its own presence flag. */
@Serializable
data class OperatorSources(
    @SerialName("node_state")
    val nodeState: OperatorSource? = null,
    @SerialName("edge_metrics")
    val edgeMetrics: OperatorSource? = null,
    @SerialName("trace_corpus")
    val traceCorpus: OperatorSource? = null,
    @SerialName("ingest_refusals")
    val ingestRefusals: OperatorSource? = null,
)

// ─────────────────────────────────────────────────────────────────────────────
// Bands. persist's own vocabulary, carried verbatim.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * persist's [`StateBand`], carried verbatim from the wire.
 *
 * `UNKNOWN` is **not** a shade of green. An uncomputed signal is a signal that
 * could not be computed, and the UI must give it its own colour and its own
 * words — the whole surface exists because a healthy-looking absence is what
 * hid a dead plane for two days.
 */
enum class OperatorBand(val wire: String) {
    GREEN("green"),
    YELLOW("yellow"),
    RED("red"),
    UNKNOWN("unknown"),
    ;

    companion object {
        /**
         * Parse a wire token. An UNRECOGNISED token yields `null`, never a
         * healthy default: a server newer than this app must read as "this app
         * cannot interpret this", not as "fine".
         */
        fun of(wire: String?): OperatorBand? = entries.firstOrNull { it.wire == wire }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// CIRISServer#369 — the trace plane.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * The trace-plane standing — **four distinct zeroes plus two live readings**,
 * and none of them may share a rendering.
 *
 * - [UNREADABLE] — could not ask the corpus.
 * - [NEVER_ADMITTED] — asked; it holds nothing at all.
 * - [FUTURE_DATED] — the newest trace is stamped in the producer's future.
 * - [DARK] — it holds traces and none is recent. **The 2026-08-05 condition.**
 */
enum class TracePlaneStanding(val wire: String) {
    UNREADABLE("unreadable"),
    NEVER_ADMITTED("never_admitted"),
    FUTURE_DATED("future_dated"),
    LIVE("live"),
    QUIET("quiet"),
    DARK("dark"),
    ;

    companion object {
        /** Unrecognised token ⇒ `null` (render as unrecognised, never green). */
        fun of(wire: String?): TracePlaneStanding? = entries.firstOrNull { it.wire == wire }
    }
}

/** The band edges, carried WITH the band so a reader never has to leave the payload. */
@Serializable
data class TracePlaneBands(
    @SerialName("green_max_hours")
    val greenMaxHours: Long = 0,
    @SerialName("yellow_max_hours")
    val yellowMaxHours: Long = 0,
    @SerialName("future_tolerance_minutes")
    val futureToleranceMinutes: Long = 0,
)

/**
 * **Is the trace plane alive** — the reading whose absence cost 71 hours.
 *
 * [lastAdmittedAt] is `MAX(trace_events.ts)`: the producer's own broadcast
 * clock, not a server-side admission instant. That limit rides in [note] and
 * must be rendered, not dropped.
 */
@Serializable
data class TracePlaneReading(
    /** persist's band vocabulary, verbatim. */
    val band: String = "unknown",
    /** The token — `unreadable` / `never_admitted` / `future_dated` / `live` / `quiet` / `dark`. */
    val standing: String = "unreadable",
    val explains: OperatorMessage? = null,
    val source: String? = null,
    val note: OperatorMessage? = null,
    val bands: TracePlaneBands? = null,
    /** RFC 3339, or `null` on an empty corpus. Absent entirely when unreadable. */
    @SerialName("last_admitted_at")
    val lastAdmittedAt: String? = null,
    /** Age of [lastAdmittedAt] at the server's read instant. `null` when there is none. */
    @SerialName("age_seconds")
    val ageSeconds: Long? = null,
    /** `COUNT(*)` over the corpus — what makes `never_admitted` checkable. */
    val rows: Long? = null,
    val unavailable: OperatorMessage? = null,
    val detail: String? = null,
) {
    val parsedBand: OperatorBand? get() = OperatorBand.of(band)
    val parsedStanding: TracePlaneStanding? get() = TracePlaneStanding.of(standing)
}

// ─────────────────────────────────────────────────────────────────────────────
// CIRISServer#370 — the ingest refusal rate.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * The ingest standing — the INVERSE reading. A large number of individually
 * CORRECT refusals is still a fault report: [STUCK_PRODUCER] means every
 * refusal was right and somebody upstream cannot self-correct.
 *
 * [UNATTRIBUTED] is its own token because `distinct_signers == 0` trivially
 * satisfies "a small stable identity set" — collapsing it would name a stuck
 * producer that does not exist.
 */
enum class IngestStanding(val wire: String) {
    UNREADABLE("unreadable"),
    NOT_EXERCISED("not_exercised"),
    CLEAN("clean"),
    UNATTRIBUTED("unattributed"),
    BACKGROUND("background"),
    STUCK_PRODUCER("stuck_producer"),
    ;

    companion object {
        /** Unrecognised token ⇒ `null` (render as unrecognised, never green). */
        fun of(wire: String?): IngestStanding? = entries.firstOrNull { it.wire == wire }
    }
}

/** One refused signer and its count in the window — who to go fix. */
@Serializable
data class IngestTopSigner(
    @SerialName("signer_id")
    val signerId: String = "",
    val refusals: Long = 0,
)

/** The thresholds the standing was decided against, carried with it. */
@Serializable
data class IngestThresholds(
    @SerialName("sustained_min_refusals_in_window")
    val sustainedMinRefusalsInWindow: Long = 0,
    @SerialName("stable_signer_max")
    val stableSignerMax: Long = 0,
    @SerialName("top_signers_cap")
    val topSignersCap: Long = 0,
)

/** **Is the admission gate working overtime** — and WHO is being refused. */
@Serializable
data class IngestReading(
    val band: String = "unknown",
    /** `unreadable` / `not_exercised` / `clean` / `unattributed` / `background` / `stuck_producer`. */
    val standing: String = "unreadable",
    val explains: OperatorMessage? = null,
    val source: String? = null,
    /** HTTP-path-only scope limit. Render it: a clean reading is not a whole-node claim. */
    val note: OperatorMessage? = null,
    val thresholds: IngestThresholds? = null,
    @SerialName("observed_since")
    val observedSince: String? = null,
    @SerialName("window_seconds")
    val windowSeconds: Long? = null,
    @SerialName("refusals_in_window")
    val refusalsInWindow: Long? = null,
    @SerialName("refusals_per_hour")
    val refusalsPerHour: Double? = null,
    /** The load-bearing dimension: two identities is a stuck client, eight thousand is a probe. */
    @SerialName("distinct_signers")
    val distinctSigners: Long? = null,
    @SerialName("unattributed_in_window")
    val unattributedInWindow: Long? = null,
    @SerialName("top_signers")
    val topSigners: List<IngestTopSigner> = emptyList(),
    @SerialName("by_kind")
    val byKind: Map<String, Long> = emptyMap(),
    @SerialName("accepted_total")
    val acceptedTotal: Long? = null,
    @SerialName("refused_total")
    val refusedTotal: Long? = null,
    /** `true` ⇒ every window count above is a FLOOR. Say so; silence is worse. */
    @SerialName("window_truncated")
    val windowTruncated: Boolean = false,
    val unavailable: OperatorMessage? = null,
) {
    val parsedBand: OperatorBand? get() = OperatorBand.of(band)
    val parsedStanding: IngestStanding? get() = IngestStanding.of(standing)
}

// ─────────────────────────────────────────────────────────────────────────────
// The edge halves — carried at reading granularity, same distinct-zero rule.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * The serve half (`carriage`) and the apply half (`receive`), rendered at the
 * granularity that matters: band + token + sentence. Their zeroes divide the
 * same way — `unreadable` / `not_exercised` / a real clean reading — so they
 * share one DTO and one row renderer.
 */
@Serializable
data class EdgeHalfReading(
    val band: String = "unknown",
    /**
     * carriage: `unreadable`/`not_exercised`/`idle`/`moving`/`withholding`.
     * receive: `unreadable`/`not_exercised`/`idle`/`converged`/`applying`/`refusing`.
     *
     * The receive half carried a single `clean` arm until CIRISEdge#457 gave it
     * an accepted-applies counter; `idle` (nothing was offered to us),
     * `converged` (offered, all already held) and `applying` (offered, admitted
     * here) were one token and one sentence before that.
     */
    val standing: String = "unreadable",
    val explains: OperatorMessage? = null,
    val note: OperatorMessage? = null,
    val unavailable: OperatorMessage? = null,
    @SerialName("withholds_total")
    val withholdsTotal: Long? = null,
    @SerialName("served_total")
    val servedTotal: Long? = null,
    @SerialName("rounds_total")
    val roundsTotal: Long? = null,
    @SerialName("apply_refusals_total")
    val applyRefusalsTotal: Long? = null,
    /** CIRISEdge#457 — rows admitted here that changed local state. */
    @SerialName("applied_total")
    val appliedTotal: Long? = null,
    /** CIRISEdge#457 — offered rows this node already held. Not a failure and
     *  not an apply: its own fact, on its own axis. */
    @SerialName("duplicate_total")
    val duplicateTotal: Long? = null,
    /**
     * The denominator the three receive counts divide up: every offered row that
     * reached an apply decision. Undecodable bytes reach no decision and the
     * substrate counts them nowhere, so they are absent from this rather than
     * folded into it — the `note` beside the reading says so on the wire.
     */
    @SerialName("decided_total")
    val decidedTotal: Long? = null,
) {
    val parsedBand: OperatorBand? get() = OperatorBand.of(band)
}

/** One persist signal, given a token and a sentence. The band is persist's. */
@Serializable
data class NodeExplain(
    /** e.g. `trust_root`, `trust_root.drill`, `key_statements`, `consent_sla`. */
    val signal: String = "",
    /** The narrowed token — two tokens may share one band on purpose. */
    val token: String = "",
    val band: String = "unknown",
    val message: OperatorMessage? = null,
) {
    val parsedBand: OperatorBand? get() = OperatorBand.of(band)
}

// ─────────────────────────────────────────────────────────────────────────────
// The composed payload.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * The whole `GET /v1/node/state` body (inside its `{"data": …}` envelope).
 *
 * [unknown] is load-bearing: a red roll-up outranks an unknown, so without the
 * per-signal unknown list a signal that could not be computed VANISHES behind a
 * red headline. Render the list whenever it is non-empty, whatever [band] says.
 */
@Serializable
data class NodeOperatorState(
    @SerialName("as_of")
    val asOf: String = "",
    /** The locale every [OperatorMessage.text] fallback is written in. */
    @SerialName("source_locale")
    val sourceLocale: String = "en",
    /** The roll-up band across every half. */
    val band: String = "unknown",
    val headline: OperatorMessage? = null,
    /** Every signal that could not be computed, named individually. */
    val unknown: List<String> = emptyList(),
    @SerialName("composed_from")
    val composedFrom: List<String> = emptyList(),
    val sources: OperatorSources? = null,
    @SerialName("node_explains")
    val nodeExplains: List<NodeExplain>? = null,
    val carriage: EdgeHalfReading? = null,
    val receive: EdgeHalfReading? = null,
    /** CIRISServer#369 — the one thing this node exists to do, watched. */
    @SerialName("trace_plane")
    val tracePlane: TracePlaneReading? = null,
    /** CIRISServer#370 — a rate of CORRECT refusals, read as the fault report it is. */
    val ingest: IngestReading? = null,
) {
    val parsedBand: OperatorBand? get() = OperatorBand.of(band)
}

// ─────────────────────────────────────────────────────────────────────────────
// The FIFTH state — the one the payload cannot carry.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * The outcome of one `GET /v1/node/state` read.
 *
 * `red` is a REAL READING FROM A REACHABLE NODE. "We never got an answer" is a
 * different fact and gets its own arm here, because rendering an unreachable
 * node as red (or as an empty green) is the same collapse the surface itself
 * forbids — one axis, two questions, one wrong answer.
 *
 * Six arms, deliberately:
 * - [Loading] — the read is in flight; nothing is yet known.
 * - [Unreachable] — no answer at all: transport, DNS, refused connection.
 * - [Refused] — the node answered and DECLINED (401/403/owner-unbound). The
 *   node is up; this session may not read it. Not a health reading either.
 * - [NotOffered] — the node answered 404: it serves no operator surface at all,
 *   which is an older build, not a permission problem and not ill health.
 * - [Malformed] — the node answered with a body this client could not parse.
 * - [Present] — a real reading. Only here does [NodeOperatorState.band] mean
 *   anything.
 */
sealed interface NodeStateReadout {
    /** No read has completed yet. Not a zero, and not a band. */
    data object Loading : NodeStateReadout

    /** The node never answered. Distinct from every band, `red` included. */
    data class Unreachable(val detail: String) : NodeStateReadout

    /** The node answered and refused this caller. Up, but not readable by us. */
    data class Refused(val status: Int, val detail: String) : NodeStateReadout

    /**
     * The node answered `404`: it mounts no operator surface. Kept apart from
     * [Refused] because "you may not read this" and "there is nothing here to
     * read" send an operator to two different places — the second is a version
     * gap, and the node may be perfectly healthy behind it.
     */
    data object NotOffered : NodeStateReadout

    /** The node answered with a body this client could not decode. */
    data class Malformed(val detail: String) : NodeStateReadout

    /** A real reading from a reachable node. */
    data class Present(val state: NodeOperatorState) : NodeStateReadout
}
