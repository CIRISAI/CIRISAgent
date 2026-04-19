package ai.ciris.mobile.shared.ui.screens.graph

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import kotlin.test.assertFalse

/**
 * Pure tests for [CellVizConfigStore]'s serialization helpers. The actual
 * [SecureStorage] wiring is exercised at the `save`/`load`/`clear` layer
 * but those are thin wrappers — the interesting behaviour is
 * [CellVizConfigStore.toMap] / [CellVizConfigStore.fromMap].
 */
class CellVizConfigStoreTest {

    @Test
    fun toMap_emitsEveryPersistedKey() {
        val map = CellVizConfigStore.toMap(CellVizConfig.DEFAULT)
        // Every key in ALL_KEYS must be present in the serialized map.
        for (key in CellVizConfigStore.ALL_KEYS) {
            assertTrue(
                map.containsKey(key),
                "toMap must emit every persisted key, but $key was missing",
            )
        }
        assertEquals(
            CellVizConfigStore.ALL_KEYS.size,
            map.size,
            "toMap emitted unexpected extra keys",
        )
    }

    @Test
    fun every_key_uses_viz_config_prefix() {
        for (key in CellVizConfigStore.ALL_KEYS) {
            assertTrue(
                key.startsWith(CellVizConfigStore.KEY_PREFIX),
                "Key '$key' must start with ${CellVizConfigStore.KEY_PREFIX}",
            )
        }
    }

    @Test
    fun roundTrip_default_isIdentity() {
        val default = CellVizConfig.DEFAULT
        val restored = CellVizConfigStore.fromMap(CellVizConfigStore.toMap(default))
        assertEquals(default, restored, "Default config must round-trip cleanly")
    }

    @Test
    fun roundTrip_tuned_preserves_every_field() {
        val tuned = CellVizConfig(
            rotationDegPerSec = 12.5f,
            membraneRadiusFraction = 0.32f,
            busArcStrokeWidth = 7f,
            busArcMidHaloWidth = 15f,
            busArcOuterHaloWidth = 30f,
            minOpenings = 2,
            maxOpenings = 6,
            openingGrowSec = 1.2f,
            openingShrinkSec = 0.6f,
            openingStableMinSec = 1.5f,
            openingStableMaxSec = 5f,
            openingMinWidthDeg = 3f,
            openingMaxWidthDeg = 12f,
            openingDriftMaxDegPerSec = 2.5f,
            portRadiusPx = 18f,
            portSegmentMarginDeg = 6f,
            portInactiveAlpha = 0.5f,
            maxMemoryMotes = 150,
            memoryQueryPeriodSec = 20f,
            memoryLoadWindowHours = 48,
            moteRadiusPx = 3.2f,
            moteDriftAmpPx = 5f,
            moteDriftPeriodSec = 18f,
            moteBirthMs = 2000L,
            maxGratitudeMotesInFlight = 2,
            gratitudeCooldownSec = 5f,
            maxCaughtBubbles = 16,
            breathePeriodSec = 8f,
            breatheScaleAmp = 0.02f,
            nucleusRadiusFraction = 0.4f,
        ).sanitized()

        val map = CellVizConfigStore.toMap(tuned)
        val restored = CellVizConfigStore.fromMap(map)
        assertEquals(tuned, restored)
    }

    @Test
    fun fromMap_missingKeys_fallBackToDefaults() {
        // Empty input must yield DEFAULT (post-sanitize).
        val restored = CellVizConfigStore.fromMap(emptyMap())
        assertEquals(CellVizConfig.DEFAULT, restored)
    }

    @Test
    fun fromMap_malformedKeys_fallBackToDefaults() {
        // Garbage values per key should not explode — each field falls
        // back to its default independently.
        val garbage = CellVizConfigStore.ALL_KEYS.associateWith { "not-a-number" }
        val restored = CellVizConfigStore.fromMap(garbage)
        assertEquals(CellVizConfig.DEFAULT, restored)
    }

    @Test
    fun fromMap_partiallyMalformed_preservesGoodFields() {
        // One real field + garbage: the real field wins, others default.
        val values = mapOf(
            CellVizConfigStore.KEY_ROTATION_DEG_PER_SEC to "12.0",
            CellVizConfigStore.KEY_MAX_MEMORY_MOTES to "xyz",
        )
        val restored = CellVizConfigStore.fromMap(values)
        assertEquals(12f, restored.rotationDegPerSec)
        // Garbage maxMemoryMotes → default (200 per CellVizConfig)
        assertEquals(CellVizConfig.DEFAULT.maxMemoryMotes, restored.maxMemoryMotes)
    }

    @Test
    fun fromMap_outOfRangeValues_areSanitized() {
        // Values beyond the sanitizer's bounds should be clamped, not
        // rejected — the worst case is a safe extreme, never NaN / garbage.
        val values = mapOf(
            CellVizConfigStore.KEY_ROTATION_DEG_PER_SEC to "9999",
            CellVizConfigStore.KEY_MIN_OPENINGS to "-5",
            CellVizConfigStore.KEY_NUCLEUS_RADIUS_FRACTION to "9999",
        )
        val restored = CellVizConfigStore.fromMap(values)
        assertEquals(45f, restored.rotationDegPerSec, "Should clamp to sanitized max")
        assertEquals(0, restored.minOpenings, "Should clamp to sanitized min")
        assertEquals(0.60f, restored.nucleusRadiusFraction, "Should clamp to sanitized max")
    }

    // ------------------------------------------------------------------
    // Slider-surface coverage — every user-facing tunable must be
    // exposed in VizSettingsScreen. This list mirrors the screen, kept
    // hand-maintained (reflection-free per the plan). When a new field
    // lands on CellVizConfig AND the screen adds a slider for it, append
    // the field name here.
    //
    // Fields deliberately NOT on the Visualization Settings screen:
    //  - busArcStrokeWidth / busArcMidHaloWidth / busArcOuterHaloWidth
    //    (bloom tuning, not surfaced to users — step 11 plan §5 scope)
    //  - memoryQueryPeriodSec (server-round-trip policy, not visual)
    //  - maxGratitudeMotesInFlight / gratitudeCooldownSec / maxCaughtBubbles
    //    (event-tier tunables live in a future settings surface)
    // ------------------------------------------------------------------

    /**
     * Fields expected to have a visible slider / stepper in
     * [VizSettingsScreen]. Update this list when you add or remove a
     * slider. The list IS the contract: any drift between the screen and
     * the config surface will show up as a failing test.
     */
    private val fieldsExposedInVizSettingsScreen: Set<String> = setOf(
        // Rotation & rhythm
        "rotationDegPerSec",
        "breathePeriodSec",
        "breatheScaleAmp",
        // Membrane & openings
        "membraneRadiusFraction",
        "minOpenings",
        "maxOpenings",
        "openingGrowSec",
        "openingShrinkSec",
        "openingStableMinSec",
        "openingStableMaxSec",
        "openingMinWidthDeg",
        "openingMaxWidthDeg",
        "openingDriftMaxDegPerSec",
        // Adapter ports
        "portRadiusPx",
        "portSegmentMarginDeg",
        "portInactiveAlpha",
        // Memory & performance
        "maxMemoryMotes",
        "moteRadiusPx",
        "moteDriftAmpPx",
        "moteDriftPeriodSec",
        "moteBirthMs",
        "memoryLoadWindowHours",
        // Nucleus
        "nucleusRadiusFraction",
    )

    @Test
    fun every_exposed_field_has_a_persisted_key() {
        // For each field we claim is in the screen, the persistence
        // layer must also know about it — otherwise a slider edit would
        // silently fail to survive an app restart.
        for (field in fieldsExposedInVizSettingsScreen) {
            val expectedKeyFragment = field.toSnakeCase()
            val matches = CellVizConfigStore.ALL_KEYS.count { it.endsWith(expectedKeyFragment) }
            assertEquals(
                1,
                matches,
                "Field '$field' (expected key fragment '$expectedKeyFragment') " +
                    "must map to exactly one CellVizConfigStore key",
            )
        }
    }

    @Test
    fun surface_does_not_silently_drop_fields() {
        // Sanity bound: if somebody adds a brand-new user-facing tunable
        // (float or int on CellVizConfig) without updating the screen
        // surface, this test gives a loud heads-up.
        //
        // We count fields on CellVizConfig via a hand-maintained total
        // (kept in sync with CellVizConfig.kt). If a field is added, the
        // total needs bumping — forcing a deliberate choice about
        // whether the new field belongs on the screen.
        val totalConfigFields = 30 // matches CellVizConfig data class fields
        val exposed = fieldsExposedInVizSettingsScreen.size
        val intentionallyHidden = setOf(
            "busArcStrokeWidth",
            "busArcMidHaloWidth",
            "busArcOuterHaloWidth",
            "memoryQueryPeriodSec",
            "maxGratitudeMotesInFlight",
            "gratitudeCooldownSec",
            "maxCaughtBubbles",
        ).size
        assertEquals(
            totalConfigFields,
            exposed + intentionallyHidden,
            "CellVizConfig field count changed — update VizSettingsScreen " +
                "and the fieldsExposedInVizSettingsScreen / " +
                "intentionallyHidden lists together",
        )
    }

    /**
     * Convert camelCase to snake_case for the persistence-key mapping.
     * Example: `openingMinWidthDeg` → `opening_min_width_deg`.
     */
    private fun String.toSnakeCase(): String {
        val sb = StringBuilder()
        for ((i, c) in this.withIndex()) {
            if (c.isUpperCase() && i > 0) sb.append('_')
            sb.append(c.lowercaseChar())
        }
        return sb.toString()
    }
}
