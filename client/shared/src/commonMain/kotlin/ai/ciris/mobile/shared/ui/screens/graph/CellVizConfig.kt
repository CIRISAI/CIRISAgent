package ai.ciris.mobile.shared.ui.screens.graph

/**
 * User-facing + developer-facing tuning surface for the cell viz.
 *
 * Every visual constant that a reasonable person might want to change
 * lives on this struct — rotation speed, port size, max-node counts,
 * breathing period, etc. Hot-path code reads from a single sanitized
 * instance; the UI-surfaced Settings screen (build-order step 11)
 * populates the same struct.
 *
 * All numeric fields are clamped to safe ranges by [sanitized]. A user
 * with a broken preferences file can't ship NaN or a negative radius
 * into the renderer — the worst they can do is land at the bounded
 * extreme.
 *
 * **What lives here**: every tunable. **What does NOT**: bus colours,
 * bus segment angles, port shape mapping, and the presence of openings
 * / gratitude / deferral ripple. Those are architectural commitments
 * from the plan (FSD/CELL_VIZ_REDESIGN.md §6) — config controls *how
 * loud or subtle* the viz is, not *what the viz is saying*.
 */
data class CellVizConfig(
    // ----- Rotation --------------------------------------------------------
    /** Degrees per second for the baseline rotation. 0 disables auto-rotation. */
    val rotationDegPerSec: Float = 6f,

    // ----- Membrane geometry -----------------------------------------------
    /**
     * Membrane radius as a fraction of `min(canvas width, canvas height)`.
     * 0.26 keeps the full circle inside the chat area even on landscape
     * layouts where the canvas is shorter than it is wide. Larger values
     * cause the top/bottom of the cell to clip behind surrounding UI
     * chrome (warning banner, input bar). Adjustable via Settings in
     * step 11.
     */
    val membraneRadiusFraction: Float = 0.26f,

    /** Stroke width of the bright inner stroke of each bus arc. */
    val busArcStrokeWidth: Float = 4.5f,

    /** Stroke width of the soft mid-halo stack in dark mode. */
    val busArcMidHaloWidth: Float = 10f,

    /** Stroke width of the outermost bloom halo in dark mode. */
    val busArcOuterHaloWidth: Float = 20f,

    // ----- Membrane openings (dynamic apertures) ---------------------------
    //
    // The membrane is never a closed ring. At any time, between [minOpenings]
    // and [maxOpenings] apertures are open somewhere around the cell — each
    // forms, drifts, and dissolves on its own timer. Renders Incompleteness
    // Awareness as continuous motion rather than a static broken pixel.

    /** Minimum number of openings present at any time. */
    val minOpenings: Int = 3,

    /** Maximum number of openings present at any time. */
    val maxOpenings: Int = 5,

    /** Seconds an opening takes to grow from 0° to its target width. */
    val openingGrowSec: Float = 0.8f,

    /** Seconds an opening takes to shrink from its target width back to 0°. */
    val openingShrinkSec: Float = 0.8f,

    /** Minimum time (seconds) an opening stays at its target width. */
    val openingStableMinSec: Float = 2.0f,

    /** Maximum time (seconds) an opening stays at its target width. */
    val openingStableMaxSec: Float = 4.0f,

    /** Minimum angular width (degrees) an opening reaches at full size. */
    val openingMinWidthDeg: Float = 4f,

    /** Maximum angular width (degrees) an opening reaches at full size. */
    val openingMaxWidthDeg: Float = 10f,

    /** Maximum drift speed (degrees/sec) an opening walks around the cell. */
    val openingDriftMaxDegPerSec: Float = 1.0f,

    // ----- Adapter ports ---------------------------------------------------
    /** Half-extent (in pixels) of an adapter port's shape. */
    val portRadiusPx: Float = 14f,

    /** Margin (in degrees) between a port and its bus segment boundary. */
    val portSegmentMarginDeg: Float = 8f,

    /** Alpha multiplier applied to inactive-adapter ports. */
    val portInactiveAlpha: Float = 0.35f,

    // ----- Cytoplasm motes (memory graph) ----------------------------------
    /** Maximum number of memory-graph motes rendered in cytoplasm. */
    val maxMemoryMotes: Int = 200,

    /**
     * Query period (seconds) for refreshing the memory-graph snapshot
     * that populates motes. Too-frequent queries harass the server;
     * too-infrequent queries make the cell feel stale.
     */
    val memoryQueryPeriodSec: Float = 15f,

    /**
     * Hours of recent graph history to load for motes.
     * 24 matches the legacy LiveGraphBackground behaviour — last
     * day's worth of activity.
     */
    val memoryLoadWindowHours: Int = 24,

    /** Base radius of a single cytoplasm mote in pixels. */
    val moteRadiusPx: Float = 2.4f,

    /**
     * Peak drift amplitude in pixels. Each mote oscillates with its
     * own phase/frequency within this envelope — small enough to feel
     * ambient, large enough to register as "alive".
     */
    val moteDriftAmpPx: Float = 3f,

    /**
     * Reference drift period in seconds. Individual motes pick slightly
     * different frequencies so they don't drift in lockstep.
     */
    val moteDriftPeriodSec: Float = 12f,

    /**
     * Birth animation duration (ms). New motes fade in with a soft
     * white halo pulse over this window.
     */
    val moteBirthMs: Long = 1500L,

    // ----- Events & bubbles (step 6 placeholders; already capped) ----------
    /** Max gratitude motes in flight at once (step 6). */
    val maxGratitudeMotesInFlight: Int = 1,

    /** Minimum seconds between gratitude-mote emissions (step 6). */
    val gratitudeCooldownSec: Float = 3f,

    /** Maximum in-flight floating "caught" event bubbles on the UI layer. */
    val maxCaughtBubbles: Int = 12,

    // ----- Breathing + nucleus --------------------------------------------
    /** Breathing period in seconds — active-presence rhythm. */
    val breathePeriodSec: Float = 6f,

    /**
     * Peak scale added on the breathe animation. 0.035 = 3.5% — clearly
     * perceptible without feeling like the cell is gasping. At 1.8% the
     * motion was too subtle for a casual observer to register that the
     * system is active.
     */
    val breatheScaleAmp: Float = 0.035f,

    /**
     * Nucleus outer radius as a fraction of the membrane radius.
     * 0.45 makes the pipeline area a meaningful, readable presence at
     * the cell's centre — large enough that the shells are perceptible
     * without competing with the membrane.
     */
    val nucleusRadiusFraction: Float = 0.45f,
) {
    /**
     * Return a copy with every value forced into a safe range. Call
     * this once per composition; every tunable is then known to be in
     * bounds for the rest of the rendering pass.
     *
     * Interdependent bounds: opening min ≤ max, stableMin ≤ stableMax,
     * widthMin ≤ widthMax. Each pair is sanitized together.
     */
    fun sanitized(): CellVizConfig {
        val sanitizedMin = minOpenings.coerceIn(0, 8)
        val sanitizedMax = maxOpenings.coerceIn(sanitizedMin, 8)
        val sanitizedStableMin = openingStableMinSec.coerceIn(0.2f, 20f)
        val sanitizedStableMax = openingStableMaxSec.coerceIn(sanitizedStableMin, 30f)
        val sanitizedWidthMin = openingMinWidthDeg.coerceIn(1f, 45f)
        val sanitizedWidthMax = openingMaxWidthDeg.coerceIn(sanitizedWidthMin, 45f)

        return copy(
            rotationDegPerSec         = rotationDegPerSec.coerceIn(0f, 45f),
            membraneRadiusFraction    = membraneRadiusFraction.coerceIn(0.15f, 0.48f),
            busArcStrokeWidth         = busArcStrokeWidth.coerceIn(1f, 12f),
            busArcMidHaloWidth        = busArcMidHaloWidth.coerceIn(2f, 24f),
            busArcOuterHaloWidth      = busArcOuterHaloWidth.coerceIn(4f, 48f),
            minOpenings               = sanitizedMin,
            maxOpenings               = sanitizedMax,
            openingGrowSec            = openingGrowSec.coerceIn(0.1f, 5f),
            openingShrinkSec          = openingShrinkSec.coerceIn(0.1f, 5f),
            openingStableMinSec       = sanitizedStableMin,
            openingStableMaxSec       = sanitizedStableMax,
            openingMinWidthDeg        = sanitizedWidthMin,
            openingMaxWidthDeg        = sanitizedWidthMax,
            openingDriftMaxDegPerSec  = openingDriftMaxDegPerSec.coerceIn(0f, 10f),
            portRadiusPx              = portRadiusPx.coerceIn(6f, 30f),
            portSegmentMarginDeg      = portSegmentMarginDeg.coerceIn(0f, 20f),
            portInactiveAlpha         = portInactiveAlpha.coerceIn(0.1f, 1f),
            maxMemoryMotes            = maxMemoryMotes.coerceIn(0, 500),
            memoryQueryPeriodSec      = memoryQueryPeriodSec.coerceIn(3f, 300f),
            memoryLoadWindowHours     = memoryLoadWindowHours.coerceIn(1, 168),
            moteRadiusPx              = moteRadiusPx.coerceIn(0.5f, 12f),
            moteDriftAmpPx            = moteDriftAmpPx.coerceIn(0f, 20f),
            moteDriftPeriodSec        = moteDriftPeriodSec.coerceIn(2f, 60f),
            moteBirthMs               = moteBirthMs.coerceIn(0L, 6000L),
            maxGratitudeMotesInFlight = maxGratitudeMotesInFlight.coerceIn(0, 4),
            gratitudeCooldownSec      = gratitudeCooldownSec.coerceIn(0.5f, 60f),
            maxCaughtBubbles          = maxCaughtBubbles.coerceIn(0, 32),
            breathePeriodSec          = breathePeriodSec.coerceIn(2f, 30f),
            breatheScaleAmp           = breatheScaleAmp.coerceIn(0f, 0.06f),
            nucleusRadiusFraction     = nucleusRadiusFraction.coerceIn(0.10f, 0.60f),
        )
    }

    companion object {
        /** Stable reference to the default, already-sanitized config. */
        val DEFAULT: CellVizConfig = CellVizConfig().sanitized()
    }
}
