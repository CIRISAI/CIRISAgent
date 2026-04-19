package ai.ciris.mobile.shared.ui.screens.graph

import ai.ciris.mobile.shared.platform.SecureStorage

/**
 * Persistence helper for [CellVizConfig] — reads and writes every tunable
 * field to secure storage under `viz_config_<field_name>` keys.
 *
 * Serialization is deliberately field-by-field (rather than a single JSON
 * blob) so that:
 *
 * 1. A partial read never corrupts the full config — a field that fails
 *    to parse falls back to its [CellVizConfig] default while every other
 *    field is still honored.
 * 2. The keys are human-readable under `adb shell run-as … cat prefs.xml`
 *    (or the iOS Keychain browser), which helps debugging regressions in
 *    the field.
 * 3. Every value round-trips through [CellVizConfig.sanitized], so a
 *    malformed preference can never ship out-of-range state into the
 *    renderer — the worst case is a clamp to the bounded extreme.
 *
 * Keys are stable; renaming a field on [CellVizConfig] is a deliberate
 * breaking change that requires bumping a migration here.
 */
object CellVizConfigStore {

    /** Secure-storage key prefix for every viz config field. */
    const val KEY_PREFIX: String = "viz_config_"

    // Concrete keys — kept in one place so the Settings screen, the
    // ViewModel, and any future migration code all share a single source
    // of truth for the persisted-key surface.
    const val KEY_ROTATION_DEG_PER_SEC: String = KEY_PREFIX + "rotation_deg_per_sec"
    const val KEY_MEMBRANE_RADIUS_FRACTION: String = KEY_PREFIX + "membrane_radius_fraction"
    const val KEY_BUS_ARC_STROKE_WIDTH: String = KEY_PREFIX + "bus_arc_stroke_width"
    const val KEY_BUS_ARC_MID_HALO_WIDTH: String = KEY_PREFIX + "bus_arc_mid_halo_width"
    const val KEY_BUS_ARC_OUTER_HALO_WIDTH: String = KEY_PREFIX + "bus_arc_outer_halo_width"
    const val KEY_MIN_OPENINGS: String = KEY_PREFIX + "min_openings"
    const val KEY_MAX_OPENINGS: String = KEY_PREFIX + "max_openings"
    const val KEY_OPENING_GROW_SEC: String = KEY_PREFIX + "opening_grow_sec"
    const val KEY_OPENING_SHRINK_SEC: String = KEY_PREFIX + "opening_shrink_sec"
    const val KEY_OPENING_STABLE_MIN_SEC: String = KEY_PREFIX + "opening_stable_min_sec"
    const val KEY_OPENING_STABLE_MAX_SEC: String = KEY_PREFIX + "opening_stable_max_sec"
    const val KEY_OPENING_MIN_WIDTH_DEG: String = KEY_PREFIX + "opening_min_width_deg"
    const val KEY_OPENING_MAX_WIDTH_DEG: String = KEY_PREFIX + "opening_max_width_deg"
    const val KEY_OPENING_DRIFT_MAX_DEG_PER_SEC: String = KEY_PREFIX + "opening_drift_max_deg_per_sec"
    const val KEY_PORT_RADIUS_PX: String = KEY_PREFIX + "port_radius_px"
    const val KEY_PORT_SEGMENT_MARGIN_DEG: String = KEY_PREFIX + "port_segment_margin_deg"
    const val KEY_PORT_INACTIVE_ALPHA: String = KEY_PREFIX + "port_inactive_alpha"
    const val KEY_MAX_MEMORY_MOTES: String = KEY_PREFIX + "max_memory_motes"
    const val KEY_MEMORY_QUERY_PERIOD_SEC: String = KEY_PREFIX + "memory_query_period_sec"
    const val KEY_MEMORY_LOAD_WINDOW_HOURS: String = KEY_PREFIX + "memory_load_window_hours"
    const val KEY_MOTE_RADIUS_PX: String = KEY_PREFIX + "mote_radius_px"
    const val KEY_MOTE_DRIFT_AMP_PX: String = KEY_PREFIX + "mote_drift_amp_px"
    const val KEY_MOTE_DRIFT_PERIOD_SEC: String = KEY_PREFIX + "mote_drift_period_sec"
    const val KEY_MOTE_BIRTH_MS: String = KEY_PREFIX + "mote_birth_ms"
    const val KEY_MAX_GRATITUDE_MOTES_IN_FLIGHT: String = KEY_PREFIX + "max_gratitude_motes_in_flight"
    const val KEY_GRATITUDE_COOLDOWN_SEC: String = KEY_PREFIX + "gratitude_cooldown_sec"
    const val KEY_MAX_CAUGHT_BUBBLES: String = KEY_PREFIX + "max_caught_bubbles"
    const val KEY_BREATHE_PERIOD_SEC: String = KEY_PREFIX + "breathe_period_sec"
    const val KEY_BREATHE_SCALE_AMP: String = KEY_PREFIX + "breathe_scale_amp"
    const val KEY_NUCLEUS_RADIUS_FRACTION: String = KEY_PREFIX + "nucleus_radius_fraction"

    /** Every persisted key, in a stable order. Used by [clear]. */
    val ALL_KEYS: List<String> = listOf(
        KEY_ROTATION_DEG_PER_SEC,
        KEY_MEMBRANE_RADIUS_FRACTION,
        KEY_BUS_ARC_STROKE_WIDTH,
        KEY_BUS_ARC_MID_HALO_WIDTH,
        KEY_BUS_ARC_OUTER_HALO_WIDTH,
        KEY_MIN_OPENINGS,
        KEY_MAX_OPENINGS,
        KEY_OPENING_GROW_SEC,
        KEY_OPENING_SHRINK_SEC,
        KEY_OPENING_STABLE_MIN_SEC,
        KEY_OPENING_STABLE_MAX_SEC,
        KEY_OPENING_MIN_WIDTH_DEG,
        KEY_OPENING_MAX_WIDTH_DEG,
        KEY_OPENING_DRIFT_MAX_DEG_PER_SEC,
        KEY_PORT_RADIUS_PX,
        KEY_PORT_SEGMENT_MARGIN_DEG,
        KEY_PORT_INACTIVE_ALPHA,
        KEY_MAX_MEMORY_MOTES,
        KEY_MEMORY_QUERY_PERIOD_SEC,
        KEY_MEMORY_LOAD_WINDOW_HOURS,
        KEY_MOTE_RADIUS_PX,
        KEY_MOTE_DRIFT_AMP_PX,
        KEY_MOTE_DRIFT_PERIOD_SEC,
        KEY_MOTE_BIRTH_MS,
        KEY_MAX_GRATITUDE_MOTES_IN_FLIGHT,
        KEY_GRATITUDE_COOLDOWN_SEC,
        KEY_MAX_CAUGHT_BUBBLES,
        KEY_BREATHE_PERIOD_SEC,
        KEY_BREATHE_SCALE_AMP,
        KEY_NUCLEUS_RADIUS_FRACTION,
    )

    /**
     * Serialize a [CellVizConfig] to a flat `Map<String, String>` whose
     * keys are the `viz_config_*` secure-storage keys. Pure — no I/O. The
     * map entries are ordered the same as [ALL_KEYS] for stable diffs.
     */
    fun toMap(config: CellVizConfig): Map<String, String> {
        return linkedMapOf(
            KEY_ROTATION_DEG_PER_SEC          to config.rotationDegPerSec.toString(),
            KEY_MEMBRANE_RADIUS_FRACTION      to config.membraneRadiusFraction.toString(),
            KEY_BUS_ARC_STROKE_WIDTH          to config.busArcStrokeWidth.toString(),
            KEY_BUS_ARC_MID_HALO_WIDTH        to config.busArcMidHaloWidth.toString(),
            KEY_BUS_ARC_OUTER_HALO_WIDTH      to config.busArcOuterHaloWidth.toString(),
            KEY_MIN_OPENINGS                  to config.minOpenings.toString(),
            KEY_MAX_OPENINGS                  to config.maxOpenings.toString(),
            KEY_OPENING_GROW_SEC              to config.openingGrowSec.toString(),
            KEY_OPENING_SHRINK_SEC            to config.openingShrinkSec.toString(),
            KEY_OPENING_STABLE_MIN_SEC        to config.openingStableMinSec.toString(),
            KEY_OPENING_STABLE_MAX_SEC        to config.openingStableMaxSec.toString(),
            KEY_OPENING_MIN_WIDTH_DEG         to config.openingMinWidthDeg.toString(),
            KEY_OPENING_MAX_WIDTH_DEG         to config.openingMaxWidthDeg.toString(),
            KEY_OPENING_DRIFT_MAX_DEG_PER_SEC to config.openingDriftMaxDegPerSec.toString(),
            KEY_PORT_RADIUS_PX                to config.portRadiusPx.toString(),
            KEY_PORT_SEGMENT_MARGIN_DEG       to config.portSegmentMarginDeg.toString(),
            KEY_PORT_INACTIVE_ALPHA           to config.portInactiveAlpha.toString(),
            KEY_MAX_MEMORY_MOTES              to config.maxMemoryMotes.toString(),
            KEY_MEMORY_QUERY_PERIOD_SEC       to config.memoryQueryPeriodSec.toString(),
            KEY_MEMORY_LOAD_WINDOW_HOURS      to config.memoryLoadWindowHours.toString(),
            KEY_MOTE_RADIUS_PX                to config.moteRadiusPx.toString(),
            KEY_MOTE_DRIFT_AMP_PX             to config.moteDriftAmpPx.toString(),
            KEY_MOTE_DRIFT_PERIOD_SEC         to config.moteDriftPeriodSec.toString(),
            KEY_MOTE_BIRTH_MS                 to config.moteBirthMs.toString(),
            KEY_MAX_GRATITUDE_MOTES_IN_FLIGHT to config.maxGratitudeMotesInFlight.toString(),
            KEY_GRATITUDE_COOLDOWN_SEC        to config.gratitudeCooldownSec.toString(),
            KEY_MAX_CAUGHT_BUBBLES            to config.maxCaughtBubbles.toString(),
            KEY_BREATHE_PERIOD_SEC            to config.breathePeriodSec.toString(),
            KEY_BREATHE_SCALE_AMP             to config.breatheScaleAmp.toString(),
            KEY_NUCLEUS_RADIUS_FRACTION       to config.nucleusRadiusFraction.toString(),
        )
    }

    /**
     * Hydrate a [CellVizConfig] from a flat `Map<String, String>`. Any key
     * missing or unparseable falls back to the corresponding
     * [CellVizConfig] default. The result is always sanitized, so the
     * renderer can trust every field to be in-range.
     */
    fun fromMap(values: Map<String, String?>): CellVizConfig {
        val d = CellVizConfig() // defaults — BEFORE sanitize
        return CellVizConfig(
            rotationDegPerSec         = values[KEY_ROTATION_DEG_PER_SEC]?.toFloatOrNull() ?: d.rotationDegPerSec,
            membraneRadiusFraction    = values[KEY_MEMBRANE_RADIUS_FRACTION]?.toFloatOrNull() ?: d.membraneRadiusFraction,
            busArcStrokeWidth         = values[KEY_BUS_ARC_STROKE_WIDTH]?.toFloatOrNull() ?: d.busArcStrokeWidth,
            busArcMidHaloWidth        = values[KEY_BUS_ARC_MID_HALO_WIDTH]?.toFloatOrNull() ?: d.busArcMidHaloWidth,
            busArcOuterHaloWidth      = values[KEY_BUS_ARC_OUTER_HALO_WIDTH]?.toFloatOrNull() ?: d.busArcOuterHaloWidth,
            minOpenings               = values[KEY_MIN_OPENINGS]?.toIntOrNull() ?: d.minOpenings,
            maxOpenings               = values[KEY_MAX_OPENINGS]?.toIntOrNull() ?: d.maxOpenings,
            openingGrowSec            = values[KEY_OPENING_GROW_SEC]?.toFloatOrNull() ?: d.openingGrowSec,
            openingShrinkSec          = values[KEY_OPENING_SHRINK_SEC]?.toFloatOrNull() ?: d.openingShrinkSec,
            openingStableMinSec       = values[KEY_OPENING_STABLE_MIN_SEC]?.toFloatOrNull() ?: d.openingStableMinSec,
            openingStableMaxSec       = values[KEY_OPENING_STABLE_MAX_SEC]?.toFloatOrNull() ?: d.openingStableMaxSec,
            openingMinWidthDeg        = values[KEY_OPENING_MIN_WIDTH_DEG]?.toFloatOrNull() ?: d.openingMinWidthDeg,
            openingMaxWidthDeg        = values[KEY_OPENING_MAX_WIDTH_DEG]?.toFloatOrNull() ?: d.openingMaxWidthDeg,
            openingDriftMaxDegPerSec  = values[KEY_OPENING_DRIFT_MAX_DEG_PER_SEC]?.toFloatOrNull() ?: d.openingDriftMaxDegPerSec,
            portRadiusPx              = values[KEY_PORT_RADIUS_PX]?.toFloatOrNull() ?: d.portRadiusPx,
            portSegmentMarginDeg      = values[KEY_PORT_SEGMENT_MARGIN_DEG]?.toFloatOrNull() ?: d.portSegmentMarginDeg,
            portInactiveAlpha         = values[KEY_PORT_INACTIVE_ALPHA]?.toFloatOrNull() ?: d.portInactiveAlpha,
            maxMemoryMotes            = values[KEY_MAX_MEMORY_MOTES]?.toIntOrNull() ?: d.maxMemoryMotes,
            memoryQueryPeriodSec      = values[KEY_MEMORY_QUERY_PERIOD_SEC]?.toFloatOrNull() ?: d.memoryQueryPeriodSec,
            memoryLoadWindowHours     = values[KEY_MEMORY_LOAD_WINDOW_HOURS]?.toIntOrNull() ?: d.memoryLoadWindowHours,
            moteRadiusPx              = values[KEY_MOTE_RADIUS_PX]?.toFloatOrNull() ?: d.moteRadiusPx,
            moteDriftAmpPx            = values[KEY_MOTE_DRIFT_AMP_PX]?.toFloatOrNull() ?: d.moteDriftAmpPx,
            moteDriftPeriodSec        = values[KEY_MOTE_DRIFT_PERIOD_SEC]?.toFloatOrNull() ?: d.moteDriftPeriodSec,
            moteBirthMs               = values[KEY_MOTE_BIRTH_MS]?.toLongOrNull() ?: d.moteBirthMs,
            maxGratitudeMotesInFlight = values[KEY_MAX_GRATITUDE_MOTES_IN_FLIGHT]?.toIntOrNull() ?: d.maxGratitudeMotesInFlight,
            gratitudeCooldownSec      = values[KEY_GRATITUDE_COOLDOWN_SEC]?.toFloatOrNull() ?: d.gratitudeCooldownSec,
            maxCaughtBubbles          = values[KEY_MAX_CAUGHT_BUBBLES]?.toIntOrNull() ?: d.maxCaughtBubbles,
            breathePeriodSec          = values[KEY_BREATHE_PERIOD_SEC]?.toFloatOrNull() ?: d.breathePeriodSec,
            breatheScaleAmp           = values[KEY_BREATHE_SCALE_AMP]?.toFloatOrNull() ?: d.breatheScaleAmp,
            nucleusRadiusFraction     = values[KEY_NUCLEUS_RADIUS_FRACTION]?.toFloatOrNull() ?: d.nucleusRadiusFraction,
        ).sanitized()
    }

    /**
     * Load a [CellVizConfig] from [SecureStorage]. Returns
     * [CellVizConfig.DEFAULT] when nothing is persisted yet or when every
     * key fails to read — the result is always sanitized.
     */
    suspend fun load(storage: SecureStorage): CellVizConfig {
        val values = LinkedHashMap<String, String?>(ALL_KEYS.size)
        for (key in ALL_KEYS) {
            values[key] = storage.get(key).getOrNull()
        }
        return fromMap(values)
    }

    /**
     * Persist a [CellVizConfig] to [SecureStorage]. The value is sanitized
     * before saving so the renderer's bounds can never drift from the
     * persisted surface. Best-effort per key — a single failure is logged
     * but does not roll back the rest.
     */
    suspend fun save(storage: SecureStorage, config: CellVizConfig) {
        val sanitized = config.sanitized()
        val map = toMap(sanitized)
        for ((key, value) in map) {
            // Fire-and-forget per-key. SecureStorage logs its own failures;
            // we do not want a single flaky write to abort the rest.
            storage.save(key, value)
        }
    }

    /**
     * Remove every persisted viz-config key. Called by Reset-to-defaults
     * so the next load returns [CellVizConfig.DEFAULT] from scratch
     * rather than re-reading a stale override.
     */
    suspend fun clear(storage: SecureStorage) {
        for (key in ALL_KEYS) {
            storage.delete(key)
        }
    }
}
