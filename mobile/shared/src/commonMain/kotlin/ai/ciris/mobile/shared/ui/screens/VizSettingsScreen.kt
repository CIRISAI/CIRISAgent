package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.screens.graph.CellVizConfig
import ai.ciris.mobile.shared.ui.theme.CIRISColors
import ai.ciris.mobile.shared.viewmodels.SettingsViewModel
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.roundToInt
import kotlin.math.roundToLong

/**
 * Visualization Settings screen — step 11 of FSD/CELL_VIZ_REDESIGN.md.
 *
 * Exposes every tunable on [CellVizConfig] as a user-editable slider
 * (float) or stepper (int). Every control's min/max mirrors the
 * `coerceIn(...)` bound on the matching field in
 * [CellVizConfig.sanitized] — the sliders and the renderer share a
 * single source of truth for what's in range, and a malformed preference
 * file can never ship invalid state.
 *
 * All edits persist through [SettingsViewModel.updateCellVizConfig] to
 * secure storage under `viz_config_*` keys and are reloaded at app start.
 * "Reset to defaults" wipes those keys and restores [CellVizConfig] built-in
 * values.
 *
 * Visual language mirrors [SettingsScreen] — `Card(surfaceVariant)`
 * sections with titleMedium headers in the brand primary colour, slider
 * accents tinted SignetTeal / AccentCyan from [CIRISColors].
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VizSettingsScreen(
    viewModel: SettingsViewModel,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val config by viewModel.cellVizConfig.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Visualization") },
                navigationIcon = {
                    IconButton(
                        onClick = onBack,
                        modifier = Modifier.testableClickable("btn_back") { onBack() },
                    ) {
                        Icon(
                            imageVector = Icons.Filled.ArrowBack,
                            contentDescription = "Back",
                        )
                    }
                },
            )
        },
    ) { paddingValues ->
        Column(
            modifier = modifier
                .fillMaxSize()
                .padding(paddingValues)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            HeaderBlurb()

            // ----- Rotation & rhythm ----------------------------------
            SectionCard(title = "Rotation & rhythm") {
                FloatSliderRow(
                    tag = "viz_settings_rotationDegPerSec",
                    label = "Rotation speed",
                    value = config.rotationDegPerSec,
                    min = 0f,
                    max = 45f,
                    unit = "°/sec",
                    decimals = 1,
                ) { viewModel.updateCellVizConfig(config.copy(rotationDegPerSec = it)) }

                FloatSliderRow(
                    tag = "viz_settings_breathePeriodSec",
                    label = "Breathing period",
                    value = config.breathePeriodSec,
                    min = 2f,
                    max = 30f,
                    unit = "s",
                    decimals = 1,
                ) { viewModel.updateCellVizConfig(config.copy(breathePeriodSec = it)) }

                FloatSliderRow(
                    tag = "viz_settings_breatheScaleAmp",
                    label = "Breathing amplitude",
                    value = config.breatheScaleAmp,
                    min = 0f,
                    max = 0.06f,
                    unit = "",
                    decimals = 3,
                ) { viewModel.updateCellVizConfig(config.copy(breatheScaleAmp = it)) }
            }

            // ----- Membrane & openings --------------------------------
            SectionCard(title = "Membrane & openings") {
                FloatSliderRow(
                    tag = "viz_settings_membraneRadiusFraction",
                    label = "Membrane radius fraction",
                    value = config.membraneRadiusFraction,
                    min = 0.15f,
                    max = 0.48f,
                    unit = "",
                    decimals = 2,
                ) { viewModel.updateCellVizConfig(config.copy(membraneRadiusFraction = it)) }

                IntStepperRow(
                    tag = "viz_settings_minOpenings",
                    label = "Min openings",
                    value = config.minOpenings,
                    min = 0,
                    max = 8,
                ) { viewModel.updateCellVizConfig(config.copy(minOpenings = it)) }

                IntStepperRow(
                    tag = "viz_settings_maxOpenings",
                    label = "Max openings",
                    value = config.maxOpenings,
                    min = 0,
                    max = 8,
                ) { viewModel.updateCellVizConfig(config.copy(maxOpenings = it)) }

                FloatSliderRow(
                    tag = "viz_settings_openingGrowSec",
                    label = "Opening grow time",
                    value = config.openingGrowSec,
                    min = 0.1f,
                    max = 5f,
                    unit = "s",
                    decimals = 2,
                ) { viewModel.updateCellVizConfig(config.copy(openingGrowSec = it)) }

                FloatSliderRow(
                    tag = "viz_settings_openingShrinkSec",
                    label = "Opening shrink time",
                    value = config.openingShrinkSec,
                    min = 0.1f,
                    max = 5f,
                    unit = "s",
                    decimals = 2,
                ) { viewModel.updateCellVizConfig(config.copy(openingShrinkSec = it)) }

                FloatSliderRow(
                    tag = "viz_settings_openingStableMinSec",
                    label = "Opening stable min",
                    value = config.openingStableMinSec,
                    min = 0.2f,
                    max = 20f,
                    unit = "s",
                    decimals = 2,
                ) { viewModel.updateCellVizConfig(config.copy(openingStableMinSec = it)) }

                FloatSliderRow(
                    tag = "viz_settings_openingStableMaxSec",
                    label = "Opening stable max",
                    value = config.openingStableMaxSec,
                    min = 0.2f,
                    max = 30f,
                    unit = "s",
                    decimals = 2,
                ) { viewModel.updateCellVizConfig(config.copy(openingStableMaxSec = it)) }

                FloatSliderRow(
                    tag = "viz_settings_openingMinWidthDeg",
                    label = "Opening min width",
                    value = config.openingMinWidthDeg,
                    min = 1f,
                    max = 45f,
                    unit = "°",
                    decimals = 1,
                ) { viewModel.updateCellVizConfig(config.copy(openingMinWidthDeg = it)) }

                FloatSliderRow(
                    tag = "viz_settings_openingMaxWidthDeg",
                    label = "Opening max width",
                    value = config.openingMaxWidthDeg,
                    min = 1f,
                    max = 45f,
                    unit = "°",
                    decimals = 1,
                ) { viewModel.updateCellVizConfig(config.copy(openingMaxWidthDeg = it)) }

                FloatSliderRow(
                    tag = "viz_settings_openingDriftMaxDegPerSec",
                    label = "Opening drift speed",
                    value = config.openingDriftMaxDegPerSec,
                    min = 0f,
                    max = 10f,
                    unit = "°/sec",
                    decimals = 2,
                ) { viewModel.updateCellVizConfig(config.copy(openingDriftMaxDegPerSec = it)) }
            }

            // ----- Adapter ports --------------------------------------
            SectionCard(title = "Adapter ports") {
                FloatSliderRow(
                    tag = "viz_settings_portRadiusPx",
                    label = "Port radius",
                    value = config.portRadiusPx,
                    min = 6f,
                    max = 30f,
                    unit = "px",
                    decimals = 1,
                ) { viewModel.updateCellVizConfig(config.copy(portRadiusPx = it)) }

                FloatSliderRow(
                    tag = "viz_settings_portSegmentMarginDeg",
                    label = "Port segment margin",
                    value = config.portSegmentMarginDeg,
                    min = 0f,
                    max = 20f,
                    unit = "°",
                    decimals = 1,
                ) { viewModel.updateCellVizConfig(config.copy(portSegmentMarginDeg = it)) }

                FloatSliderRow(
                    tag = "viz_settings_portInactiveAlpha",
                    label = "Inactive-port alpha",
                    value = config.portInactiveAlpha,
                    min = 0.1f,
                    max = 1f,
                    unit = "",
                    decimals = 2,
                ) { viewModel.updateCellVizConfig(config.copy(portInactiveAlpha = it)) }
            }

            // ----- Memory & performance -------------------------------
            SectionCard(title = "Memory & performance") {
                IntStepperRow(
                    tag = "viz_settings_maxMemoryMotes",
                    label = "Max memory motes",
                    value = config.maxMemoryMotes,
                    min = 0,
                    max = 500,
                    step = 10,
                ) { viewModel.updateCellVizConfig(config.copy(maxMemoryMotes = it)) }

                FloatSliderRow(
                    tag = "viz_settings_moteRadiusPx",
                    label = "Mote radius",
                    value = config.moteRadiusPx,
                    min = 0.5f,
                    max = 12f,
                    unit = "px",
                    decimals = 1,
                ) { viewModel.updateCellVizConfig(config.copy(moteRadiusPx = it)) }

                FloatSliderRow(
                    tag = "viz_settings_moteDriftAmpPx",
                    label = "Mote drift amplitude",
                    value = config.moteDriftAmpPx,
                    min = 0f,
                    max = 20f,
                    unit = "px",
                    decimals = 1,
                ) { viewModel.updateCellVizConfig(config.copy(moteDriftAmpPx = it)) }

                FloatSliderRow(
                    tag = "viz_settings_moteDriftPeriodSec",
                    label = "Mote drift period",
                    value = config.moteDriftPeriodSec,
                    min = 2f,
                    max = 60f,
                    unit = "s",
                    decimals = 1,
                ) { viewModel.updateCellVizConfig(config.copy(moteDriftPeriodSec = it)) }

                LongStepperRow(
                    tag = "viz_settings_moteBirthMs",
                    label = "Mote birth duration",
                    value = config.moteBirthMs,
                    min = 0L,
                    max = 6000L,
                    step = 100L,
                    unit = "ms",
                ) { viewModel.updateCellVizConfig(config.copy(moteBirthMs = it)) }

                IntStepperRow(
                    tag = "viz_settings_memoryLoadWindowHours",
                    label = "Memory load window",
                    value = config.memoryLoadWindowHours,
                    min = 1,
                    max = 168,
                    unit = "h",
                ) { viewModel.updateCellVizConfig(config.copy(memoryLoadWindowHours = it)) }
            }

            // ----- Nucleus --------------------------------------------
            SectionCard(title = "Nucleus") {
                FloatSliderRow(
                    tag = "viz_settings_nucleusRadiusFraction",
                    label = "Nucleus radius fraction",
                    value = config.nucleusRadiusFraction,
                    min = 0.10f,
                    max = 0.60f,
                    unit = "",
                    decimals = 2,
                ) { viewModel.updateCellVizConfig(config.copy(nucleusRadiusFraction = it)) }
            }

            // ----- Reset ----------------------------------------------
            Button(
                onClick = { viewModel.resetCellVizConfig() },
                colors = ButtonDefaults.buttonColors(
                    containerColor = CIRISColors.SignetTeal,
                    contentColor = MaterialTheme.colorScheme.onPrimary,
                ),
                modifier = Modifier
                    .fillMaxWidth()
                    .testableClickable("viz_settings_reset") { viewModel.resetCellVizConfig() },
            ) {
                Icon(
                    imageVector = Icons.Filled.Refresh,
                    contentDescription = null,
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text("Reset to defaults")
            }

            Spacer(modifier = Modifier.height(24.dp))
        }
    }
}

/**
 * Blurb at the top of the screen explaining scope and the "why can't I
 * change bus colors" question. Anchored in plan §2.8.
 */
@Composable
private fun HeaderBlurb() {
    Surface(
        shape = RoundedCornerShape(8.dp),
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(
                text = "Cell visualization tuning",
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Medium,
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = "These controls tune how loud or subtle the cell viz is. " +
                    "Bus colors, bus angles, and architectural elements are not " +
                    "adjustable — they are the CIRIS acronym made visible.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/**
 * Styled section container — one per config group. Matches
 * [SettingsScreen]'s "titleMedium primary + Card(surfaceVariant)" idiom.
 */
@Composable
private fun SectionCard(title: String, content: @Composable () -> Unit) {
    Column {
        Text(
            text = title,
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.primary,
        )
        Spacer(modifier = Modifier.height(8.dp))
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surfaceVariant,
            ),
        ) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                content()
            }
        }
    }
}

/**
 * Float slider row. Renders: label + current value, then a Material3
 * Slider coloured with the CIRIS accent. [decimals] controls display
 * precision; the underlying float is not re-quantised — the sanitiser
 * clamps, it does not snap.
 */
@Composable
private fun FloatSliderRow(
    tag: String,
    label: String,
    value: Float,
    min: Float,
    max: Float,
    unit: String,
    decimals: Int,
    onChange: (Float) -> Unit,
) {
    Column {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = label,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium,
            )
            Text(
                text = formatFloat(value, decimals) + (if (unit.isNotEmpty()) " $unit" else ""),
                style = MaterialTheme.typography.bodySmall,
                fontFamily = FontFamily.Monospace,
                color = CIRISColors.AccentCyan,
            )
        }
        Slider(
            value = value,
            onValueChange = onChange,
            valueRange = min..max,
            colors = SliderDefaults.colors(
                thumbColor = CIRISColors.SignetTeal,
                activeTrackColor = CIRISColors.SignetTeal,
                inactiveTrackColor = CIRISColors.SignetTeal.copy(alpha = 0.3f),
            ),
            modifier = Modifier
                .fillMaxWidth()
                .testable(tag),
        )
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(
                text = formatFloat(min, decimals),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
            )
            Text(
                text = formatFloat(max, decimals),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
            )
        }
    }
}

/**
 * Integer stepper row. Shows label, -/value/+ buttons, and min/max hint.
 * Used for `Int` fields where a Slider's floating-point semantics would
 * feel wrong (integer counts, window sizes, etc.).
 */
@Composable
private fun IntStepperRow(
    tag: String,
    label: String,
    value: Int,
    min: Int,
    max: Int,
    step: Int = 1,
    unit: String = "",
    onChange: (Int) -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .testable(tag),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.padding(end = 12.dp)) {
            Text(
                text = label,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium,
            )
            Text(
                text = "$min..$max" + (if (unit.isNotEmpty()) " $unit" else ""),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
            )
        }
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            StepperButton(
                tag = "${tag}_minus",
                label = "-",
                enabled = value > min,
            ) { onChange((value - step).coerceAtLeast(min)) }
            Text(
                text = "$value" + (if (unit.isNotEmpty()) " $unit" else ""),
                style = MaterialTheme.typography.bodyLarge,
                fontFamily = FontFamily.Monospace,
                fontWeight = FontWeight.Bold,
                color = CIRISColors.AccentCyan,
                modifier = Modifier.width(72.dp),
            )
            StepperButton(
                tag = "${tag}_plus",
                label = "+",
                enabled = value < max,
            ) { onChange((value + step).coerceAtMost(max)) }
        }
    }
}

/**
 * Long stepper row. Same UX as [IntStepperRow] but for `Long` fields
 * (currently just `moteBirthMs`). Kept as a separate composable rather
 * than funneling through Int to avoid Int.MAX_VALUE edge cases on
 * platforms where Long > 32 bits matters.
 */
@Composable
private fun LongStepperRow(
    tag: String,
    label: String,
    value: Long,
    min: Long,
    max: Long,
    step: Long,
    unit: String,
    onChange: (Long) -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .testable(tag),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.padding(end = 12.dp)) {
            Text(
                text = label,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium,
            )
            Text(
                text = "$min..$max $unit",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
            )
        }
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            StepperButton(
                tag = "${tag}_minus",
                label = "-",
                enabled = value > min,
            ) { onChange((value - step).coerceAtLeast(min)) }
            Text(
                text = "$value $unit",
                style = MaterialTheme.typography.bodyLarge,
                fontFamily = FontFamily.Monospace,
                fontWeight = FontWeight.Bold,
                color = CIRISColors.AccentCyan,
                modifier = Modifier.width(96.dp),
            )
            StepperButton(
                tag = "${tag}_plus",
                label = "+",
                enabled = value < max,
            ) { onChange((value + step).coerceAtMost(max)) }
        }
    }
}

@Composable
private fun StepperButton(
    tag: String,
    label: String,
    enabled: Boolean,
    onClick: () -> Unit,
) {
    Surface(
        shape = RoundedCornerShape(8.dp),
        color = if (enabled) CIRISColors.SignetTeal else CIRISColors.SignetTeal.copy(alpha = 0.3f),
        modifier = Modifier
            .size(36.dp)
            .testableClickable(tag) { if (enabled) onClick() },
    ) {
        Column(
            modifier = Modifier.fillMaxSize(),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = label,
                style = MaterialTheme.typography.titleLarge,
                fontSize = 18.sp,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onPrimary,
            )
        }
    }
}

/**
 * Kotlin-common portable float formatter — `%.2f` isn't available in
 * Kotlin/Native's commonMain. This matches the precision of the inline
 * value badge to the slider's [decimals] parameter.
 */
private fun formatFloat(value: Float, decimals: Int): String {
    if (decimals <= 0) return value.roundToInt().toString()
    var factor = 1f
    repeat(decimals) { factor *= 10f }
    val rounded = (value * factor).roundToLong()
    val whole = rounded / factor.toLong()
    val frac = (if (rounded < 0) -rounded else rounded) % factor.toLong()
    val fracStr = frac.toString().padStart(decimals, '0')
    val sign = if (value < 0 && whole == 0L) "-" else ""
    return "$sign$whole.$fracStr"
}
