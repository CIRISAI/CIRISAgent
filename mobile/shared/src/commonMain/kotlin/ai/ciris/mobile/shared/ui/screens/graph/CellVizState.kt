package ai.ciris.mobile.shared.ui.screens.graph

/**
 * Live, CIRIS-acronym-backed state that drives the cell visualization's
 * ambient dials. This is user-facing only — the agent never reads its own
 * score (Goodhart / self-monitoring anxiety).
 *
 * Source of truth is the CIRISLens capacity scoring for the current agent
 * template, fetched via `/v1/my-data/capacity`. All five factor fields are
 * in `[0, 1]`; neutral = 1.0. When no data has arrived yet, callers should
 * pass [DEFAULT] so the cell renders "as if nothing is wrong."
 *
 * Why a pure data class + helpers: keeps visual-dial math testable from
 * `commonTest` without pulling in Compose. The Compose layer just reads
 * the derived dials and applies them.
 */
data class CellVizState(
    /** Core identity / Consistency — 1.0 = no contradictions, identity stable. */
    val c: Float = 1f,
    /** Integrity — 1.0 = all traces signed and chain-verified. */
    val iInt: Float = 1f,
    /** Resilience / Reliability — 1.0 = no drift from baseline behaviour. */
    val r: Float = 1f,
    /** Incompleteness / Incalibration — 1.0 = calibrated and defers when unsure. */
    val iInc: Float = 1f,
    /** Signalling gratitude / Steering — 1.0 = all ethical faculties passing. */
    val s: Float = 1f,
    /** Aggregate in [0, 1]. Convenient for coarse visual gates. */
    val compositeScore: Float = 1f,
    /** Fragility index from lens — higher = more fragile; unbounded but typically 0..5. */
    val fragilityIndex: Float = 1f,
    /** Category label from lens: high_capacity | healthy | moderate | high_fragility. */
    val category: String = "healthy",
    /** True when the viewmodel has never successfully fetched capacity yet. */
    val isPreFetch: Boolean = true,
    /**
     * Per-occurrence local capacity score in `[0, 1]`, computed on-device
     * from live service + LLM health signals the client already polls.
     * `null` = not yet available, render fleet only. Minimal, efficient,
     * and explicitly NOT a trust signal — trust = device attestation,
     * capacity = behavioural/coherence health. See §5a TODO in
     * CELL_VIZ_REDESIGN and the Coherence Collapse Analysis paper
     * (J = k_eff · (1 − ρ) · λ · σ).
     */
    val localScore: Float? = null,
) {
    /**
     * Clamp every factor into `[0, 1]`. Lens returns values in that range, but
     * we defend against upstream drift so the viz never receives out-of-range
     * values (breathing with negative amplitude, etc.).
     */
    fun sanitized(): CellVizState = copy(
        c = c.coerceIn(0f, 1f),
        iInt = iInt.coerceIn(0f, 1f),
        r = r.coerceIn(0f, 1f),
        iInc = iInc.coerceIn(0f, 1f),
        s = s.coerceIn(0f, 1f),
        compositeScore = compositeScore.coerceIn(0f, 1f),
        fragilityIndex = fragilityIndex.coerceAtLeast(0f),
        localScore = localScore?.coerceIn(0f, 1f),
    )

    companion object {
        /**
         * Neutral state shown before the first successful capacity fetch or
         * when the device is offline. The cell looks "as designed" — we do
         * NOT punish the user with a degraded viz just because we haven't
         * phoned home yet.
         */
        val DEFAULT: CellVizState = CellVizState()
    }
}

/**
 * Derived visual dials computed from a [CellVizState]. Each dial is in
 * `[0, 1]` and represents how strongly a specific visual primitive should
 * deviate from its neutral default.
 *
 * The mapping from CIRIS factor -> visual primitive is intentionally
 * one-to-one and loud enough to see, but still lives inside the envelope
 * defined by `CellVizConfig` (no dial can uncap a tunable beyond its bounds).
 */
data class CellVizDials(
    /** Nucleus identity-term opacity multiplier. Low C -> dimmer core. */
    val nucleusOpacity: Float,
    /** Bus-arc stroke crispness (1.0 = sharp; < 1.0 = slight glow bleed). */
    val busCrispness: Float,
    /** Breathing rhythm steadiness. 1.0 = metronomic; low = jitter. */
    val breathSteadiness: Float,
    /** Opening count bias in `[0, 1]`. 1.0 = lean toward maxOpenings, 0.0 = lean toward min. */
    val openingBias: Float,
    /** Fraction of cytoplasm motes rendered in the "warm gratitude" palette. */
    val moteWarmth: Float,
) {
    companion object {
        /**
         * All dials neutral — what a high-capacity agent's cell looks like.
         * `openingBias = 1.0` because a healthy CIRIS agent defers
         * appropriately (I_inc = 1.0), which should read as maximum
         * permeability on the membrane.
         */
        val NEUTRAL: CellVizDials = CellVizDials(
            nucleusOpacity = 1f,
            busCrispness = 1f,
            breathSteadiness = 1f,
            openingBias = 1f,
            moteWarmth = 1f,
        )
    }
}

/**
 * Translate a [CellVizState] into [CellVizDials].
 *
 * Rationale for this mapping (§2.5 of the cell-viz plan): each CIRIS factor
 * should drive the *one* visual primitive that most directly carries its
 * semantic meaning — not a diffuse "overall health" effect that would be
 * indistinguishable from low contrast.
 *
 *  - C   -> nucleus opacity      (identity is the core; weak identity dims it)
 *  - I_int -> bus-arc crispness   (integrity = chain clarity)
 *  - R   -> breathing steadiness (drift reads as rhythm jitter)
 *  - I_inc -> opening bias       (humility = more openings, per FSD §2.5.1)
 *  - S   -> mote warmth          (gratitude motes in the drift, FSD §2.5.3)
 *
 * Floors prevent the cell from looking "broken" under low scores — even a
 * high-fragility agent should still render as a recognisable cell, just
 * with reduced vitality across these dials.
 */
/**
 * Compute a per-occurrence local capacity score in `[0, 1]` from the live
 * signals the client already polls. This is a deliberately minimal CCA
 * approximation (J = k_eff · (1 − ρ) · λ · σ) — we don't have ρ, λ, σ as
 * separate scalars at the mobile layer, so we use the two health fractions
 * as proxies for the scale + sustainability terms and constant 1.0 for
 * the others. It's "good enough" for a demo-worthy live dial; backend can
 * return a proper J later via `/v1/my-data/capacity?scope=local`.
 *
 * Inputs:
 *  - `serviceHealthFrac` in `[0, 1]` — fraction of core services healthy
 *    from `/v1/system/health` (proxies for k_eff).
 *  - `llmHealthFrac` in `[0, 1]` — fraction of LLM providers healthy with
 *    closed circuit breakers (proxies for σ, sustainability).
 *
 * Returns null when neither signal has arrived yet (so the badge renders
 * fleet-only rather than a spurious 0).
 *
 * Intentionally NOT a trust signal — trust is device attestation, this is
 * behavioural/coherence health. Same guardrail as fleet: never fed to the
 * agent's own context (Goodhart).
 */
fun computeLocalScore(
    serviceHealthFrac: Float?,
    llmHealthFrac: Float?,
): Float? {
    if (serviceHealthFrac == null && llmHealthFrac == null) return null
    val svc = (serviceHealthFrac ?: 1f).coerceIn(0f, 1f)
    val llm = (llmHealthFrac ?: 1f).coerceIn(0f, 1f)
    // 60/40 weighting: core services are the primary constraint fabric,
    // LLM providers are one sustainability channel. Both floor at modest
    // values so a single-provider agent doesn't read as "broken."
    return (0.6f * svc + 0.4f * llm).coerceIn(0f, 1f)
}

fun derivedDials(state: CellVizState): CellVizDials {
    val s = state.sanitized()

    // Nucleus opacity: floor at 0.55 so the core is always visible
    val nucleusOpacity = 0.55f + 0.45f * s.c

    // Bus crispness: floor at 0.70 — even fragile agents shouldn't look broken
    val busCrispness = 0.70f + 0.30f * s.iInt

    // Breath steadiness: floor at 0.40 — noticeable but not chaotic
    val breathSteadiness = 0.40f + 0.60f * s.r

    // Opening bias: direct passthrough. High I_inc (humility) = more openings.
    val openingBias = s.iInc

    // Mote warmth: floor at 0.20 — a cold cell still has some warmth
    val moteWarmth = 0.20f + 0.80f * s.s

    return CellVizDials(
        nucleusOpacity = nucleusOpacity,
        busCrispness = busCrispness,
        breathSteadiness = breathSteadiness,
        openingBias = openingBias,
        moteWarmth = moteWarmth,
    )
}
