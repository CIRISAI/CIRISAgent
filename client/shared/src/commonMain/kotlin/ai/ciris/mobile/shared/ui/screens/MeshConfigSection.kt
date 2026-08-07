package ai.ciris.mobile.shared.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.surfaces.MeshConfigConsumption
import ai.ciris.mobile.shared.models.surfaces.MeshConfigHistory
import ai.ciris.mobile.shared.models.surfaces.MeshConfigRead
import ai.ciris.mobile.shared.models.surfaces.MeshConfigRegistryEntry
import ai.ciris.mobile.shared.models.surfaces.MeshConfigSetting
import ai.ciris.mobile.shared.models.surfaces.MeshConfigTtl
import ai.ciris.mobile.shared.models.surfaces.MeshConfigWriteResult
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.components.refusalText
import ai.ciris.mobile.shared.ui.components.surfaceText
import ai.ciris.mobile.shared.ui.theme.SemanticColors
import ai.ciris.mobile.shared.viewmodels.MeshConfigViewModel

/**
 * **The Mesh Configuration plane, rendered** (CIRISServer#346 / #365,
 * `src/mesh_config_surface.rs`).
 *
 * This sits inside the Config surface and is deliberately walled off from the
 * node's own configuration below it: the SELF config plane is what this node's
 * owner sets, the mesh-config plane is what a subscribed TRUST ROOT asks of it,
 * and the two never merge. A shared spelling is how two planes start looking
 * like one.
 *
 * # Why every value carries a label
 *
 * `effective: 10` is a false statement for three of the four consumption
 * states. Only `wired` means a loop in this build reads the number; `elsewhere`
 * means the consumer is in another component, `unbuilt` means no consumer
 * exists anywhere, and `unreachable` is the trap — a consumer EXISTS, this node
 * cannot reach it, so the value is accepted, folded, and still does not take
 * effect (and would not stop applying when its TTL lapsed, either).
 *
 * So the label renders BESIDE the number, never behind a tooltip, and the row
 * says "in force" or "not in force" in words. The difference between a knob
 * that works and one that only confirms is the single most useful thing this
 * screen can tell an operator.
 *
 * # Absence is not zero
 *
 * On the `unreadable` standing the server sends `settings: null` — not an empty
 * list, not zeros — and this renders the registry with NO values at all plus an
 * explicit "the values are unknown, not defaults" banner. A `0` because nobody
 * spoke and a `0` because nothing could be read must not look the same.
 */

// ═════════════════════════════════════════════════════════════════════════════
//  Consumption — the honest label
// ═════════════════════════════════════════════════════════════════════════════

/** The colour for one consumption state. `wired` is the only affirming one. */
@Composable
private fun consumptionColor(state: String): Color = when (state) {
    "wired" -> SemanticColors.Default.success
    "elsewhere" -> SemanticColors.Default.info
    // A consumer EXISTS and cannot be reached: the value is accepted and inert.
    // That is a hazard, not a neutral fact, so it reads as one.
    "unreachable" -> SemanticColors.Default.warning
    else -> MaterialTheme.colorScheme.onSurfaceVariant
}

/**
 * The label itself. Rendered beside the effective value on every row —
 * a pill carrying the substrate token verbatim, because the token is the fact.
 */
@Composable
private fun ConsumptionBadge(consumption: MeshConfigConsumption?, modifier: Modifier = Modifier) {
    val state = consumption?.state ?: ""
    if (state.isBlank()) return
    val color = consumptionColor(state)
    Surface(
        color = color.copy(alpha = 0.18f),
        shape = RoundedCornerShape(4.dp),
        modifier = modifier,
    ) {
        Text(
            text = state.uppercase(),
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp),
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Bold,
            color = color,
        )
    }
}

/**
 * The full consumption disclosure: the verdict in words, the substrate's own
 * localized sentence, and whatever the arm carries (accessor, owning component,
 * blocker, tracking issue). Never collapsed into a tooltip.
 */
@Composable
private fun ConsumptionDetail(consumption: MeshConfigConsumption?) {
    if (consumption == null) return
    val wired = consumption.state == "wired"
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(
            text = if (wired) {
                localizedString("surfaces.mesh_config.in_force")
            } else {
                localizedString("surfaces.mesh_config.not_in_force")
            },
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.SemiBold,
            color = consumptionColor(consumption.state),
        )
        val sentence = surfaceText(consumption.message)
        if (sentence.isNotBlank()) {
            Text(
                text = sentence,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        consumption.site?.let { KeyValueLine(localizedString("surfaces.mesh_config.consumption_site"), it, mono = true) }
        consumption.effect?.let { KeyValueLine(localizedString("surfaces.mesh_config.consumption_effect"), it) }
        consumption.owner?.let { KeyValueLine(localizedString("surfaces.mesh_config.consumption_owner"), it) }
        // Raw source text naming symbols in another repo — never paraphrased.
        consumption.blocker?.let {
            KeyValueLine(localizedString("surfaces.mesh_config.consumption_blocker"), it, mono = true)
        }
        consumption.trackedBy?.let { KeyValueLine(localizedString("surfaces.mesh_config.consumption_tracked_by"), it) }
    }
}

// ═════════════════════════════════════════════════════════════════════════════
//  Small shared pieces
// ═════════════════════════════════════════════════════════════════════════════

@Composable
private fun KeyValueLine(label: String, value: String, mono: Boolean = false) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(
            text = "$label:",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            text = value,
            style = MaterialTheme.typography.labelSmall,
            fontFamily = if (mono) FontFamily.Monospace else FontFamily.Default,
            color = MaterialTheme.colorScheme.onSurface,
        )
    }
}

/**
 * A countdown, assembled from localized unit fragments rather than an English
 * sentence. `remaining_seconds` is the datum; the words around it are the
 * reader's.
 */
@Composable
private fun formatRemaining(seconds: Long): String {
    if (seconds <= 0) return localizedString("surfaces.mesh_config.ttl_expired")
    val d = seconds / 86_400
    val h = (seconds % 86_400) / 3_600
    val m = (seconds % 3_600) / 60
    val s = seconds % 60
    val parts = mutableListOf<String>()
    if (d > 0) parts += localizedString("surfaces.common.duration_days", "n", d.toString())
    if (h > 0) parts += localizedString("surfaces.common.duration_hours", "n", h.toString())
    if (m > 0 && d == 0L) parts += localizedString("surfaces.common.duration_minutes", "n", m.toString())
    if (parts.isEmpty()) parts += localizedString("surfaces.common.duration_seconds", "n", s.toString())
    return parts.joinToString(" ")
}

/**
 * The TTL, as three distinct facts: unbounded / expired / running. A relief
 * that lapses with nobody filing anything is a FEATURE, and the countdown is
 * how an operator watches that happen.
 */
@Composable
private fun TtlLine(ttl: MeshConfigTtl?) {
    if (ttl == null) return
    val expired = ttl.expired == true
    val color = when {
        !ttl.bounded -> MaterialTheme.colorScheme.onSurfaceVariant
        expired -> MaterialTheme.colorScheme.onSurfaceVariant
        else -> SemanticColors.Default.warning
    }
    val head = when {
        !ttl.bounded -> localizedString("surfaces.mesh_config.ttl_unbounded")
        expired -> localizedString("surfaces.mesh_config.ttl_expired")
        else -> localizedString("surfaces.mesh_config.ttl_remaining") +
            " " + formatRemaining(ttl.remainingSeconds ?: 0L)
    }
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = localizedString("surfaces.mesh_config.ttl") + ":",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(text = head, style = MaterialTheme.typography.labelMedium, color = color, fontWeight = FontWeight.Medium)
            ttl.expiresAt?.let {
                Text(
                    text = it,
                    style = MaterialTheme.typography.labelSmall,
                    fontFamily = FontFamily.Monospace,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        val sentence = surfaceText(ttl.message)
        if (sentence.isNotBlank()) {
            Text(
                text = sentence,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/** A standing token + the substrate's own localized explanation of it. */
@Composable
private fun StandingBanner(token: String, message: String, hazard: Boolean) {
    val color = if (hazard) SemanticColors.Default.warning else MaterialTheme.colorScheme.primary
    Surface(
        color = color.copy(alpha = 0.12f),
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(
                text = token.uppercase(),
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.Bold,
                color = color,
            )
            if (message.isNotBlank()) {
                Text(text = message, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

// ═════════════════════════════════════════════════════════════════════════════
//  The section
// ═════════════════════════════════════════════════════════════════════════════

/**
 * The whole mesh-config plane as one card, for embedding at the head of the
 * Config screen.
 */
@Composable
fun MeshConfigSection(
    viewModel: MeshConfigViewModel,
    modifier: Modifier = Modifier,
) {
    val read by viewModel.read.collectAsState()
    val history by viewModel.history.collectAsState()
    val loading by viewModel.loading.collectAsState()
    val busy by viewModel.busy.collectAsState()
    val error by viewModel.error.collectAsState()
    val writeResult by viewModel.writeResult.collectAsState()

    var expanded by remember { mutableStateOf(true) }
    var showHistory by remember { mutableStateOf(false) }
    var showWriteDialog by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) { viewModel.refresh() }

    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
    ) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            // ── Header ──────────────────────────────────────────────────────
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .testableClickable("item_mesh_config_header") { expanded = !expanded },
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = if (expanded) CIRISIcons.arrowDown else CIRISIcons.arrowRight,
                        contentDescription = null,
                    )
                    Column {
                        Text(
                            text = localizedString("surfaces.mesh_config.title"),
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                        )
                        Text(
                            text = localizedString("surfaces.mesh_config.subtitle"),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                IconButton(
                    onClick = { viewModel.refresh() },
                    enabled = !loading,
                    modifier = Modifier.testableClickable("btn_mesh_config_refresh") { viewModel.refresh() },
                ) {
                    Icon(CIRISIcons.refresh, contentDescription = localizedString("mobile.common_refresh"))
                }
            }

            AnimatedVisibility(visible = expanded) {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    if (loading && read == null) {
                        Box(Modifier.fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) {
                            CircularProgressIndicator()
                        }
                    }
                    error?.let {
                        Text(
                            text = it,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.error,
                        )
                    }
                    read?.let { r -> MeshConfigBody(r) }

                    // ── Write paths ─────────────────────────────────────────
                    read?.let { r ->
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(
                                onClick = { showWriteDialog = true },
                                enabled = !busy,
                                modifier = Modifier.testableClickable("btn_mesh_config_write") { showWriteDialog = true },
                            ) {
                                Text(localizedString("surfaces.mesh_config.write_title"))
                            }
                            TextButton(
                                onClick = {
                                    showHistory = !showHistory
                                    if (showHistory) viewModel.loadHistory()
                                },
                                modifier = Modifier.testableClickable("btn_mesh_config_history") {
                                    showHistory = !showHistory
                                    if (showHistory) viewModel.loadHistory()
                                },
                            ) {
                                Text(
                                    if (showHistory) {
                                        localizedString("surfaces.mesh_config.hide_history")
                                    } else {
                                        localizedString("surfaces.mesh_config.show_history")
                                    },
                                )
                            }
                        }
                        writeResult?.let { WriteResultCard(it) { viewModel.clearWriteResult() } }
                        AnimatedVisibility(visible = showHistory) {
                            history?.let { MeshConfigHistoryBlock(it) }
                        }
                        if (showWriteDialog) {
                            MeshConfigWriteDialog(
                                registry = r.registry,
                                maxTtlHours = r.emergency?.maxTtlHours ?: 0,
                                busy = busy,
                                onDismiss = { showWriteDialog = false },
                                onDurable = { key, v, root, del, grounds, ratifies, dry ->
                                    viewModel.submitDurable(key, v, root, del, grounds, ratifies, dry)
                                    if (!dry) showWriteDialog = false
                                },
                                onRelief = { key, v, root, del, grounds, ttl ->
                                    viewModel.submitRelief(key, v, root, del, grounds, ttl)
                                    showWriteDialog = false
                                },
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun MeshConfigBody(read: MeshConfigRead) {
    // A gate refusal arrives on the same shape with no standing at all.
    if (read.refused) {
        StandingBanner(
            token = read.refusal ?: "refused",
            message = refusalText("mesh_config", read.refusal, read.message),
            hazard = true,
        )
        return
    }

    val unreadable = read.standing == "unreadable"
    StandingBanner(
        token = read.standing,
        message = surfaceText(read.standingMessage),
        hazard = unreadable || read.unreadableRoots.isNotEmpty(),
    )
    read.error?.let {
        Text(text = it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
    }

    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        read.nodeKeyId?.let { KeyValueLine(localizedString("surfaces.mesh_config.node"), it, mono = true) }
        KeyValueLine(
            localizedString("surfaces.mesh_config.roots"),
            read.roots?.size?.toString() ?: localizedString("surfaces.common.unknown"),
        )
        read.rowsHeld?.let { KeyValueLine(localizedString("surfaces.mesh_config.rows_held"), it.toString()) }
        read.emergency?.let {
            KeyValueLine(
                localizedString("surfaces.mesh_config.emergency_bound"),
                "${it.maxTtlHours} " + localizedString("surfaces.mesh_config.hours"),
            )
        }
    }
    read.roots?.forEach { root ->
        Text(text = root, style = MaterialTheme.typography.labelSmall, fontFamily = FontFamily.Monospace)
    }

    if (read.unreadableRoots.isNotEmpty()) {
        Surface(
            color = SemanticColors.Default.warning.copy(alpha = 0.12f),
            shape = RoundedCornerShape(8.dp),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Column(Modifier.padding(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(
                    text = localizedString("surfaces.mesh_config.unreadable_roots"),
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold,
                    color = SemanticColors.Default.warning,
                )
                read.unreadableRoots.forEach {
                    Text(
                        text = "${it.rootRef} — ${it.error}",
                        style = MaterialTheme.typography.labelSmall,
                        fontFamily = FontFamily.Monospace,
                    )
                }
            }
        }
    }

    surfaceText(read.durability).takeIf { it.isNotBlank() }?.let {
        Text(text = it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }

    val settings = read.settings
    if (settings == null) {
        // THE distinct zero. No values are shown at all, because none were read.
        Surface(
            color = MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.4f),
            shape = RoundedCornerShape(8.dp),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(
                text = localizedString("surfaces.mesh_config.unknown_values"),
                modifier = Modifier.padding(12.dp),
                style = MaterialTheme.typography.bodySmall,
                fontWeight = FontWeight.SemiBold,
            )
        }
        // The registry still describes WHICH keys exist and whether anything in
        // this build would read them — facts that do not depend on the plane.
        Text(
            text = localizedString("surfaces.mesh_config.registry"),
            style = MaterialTheme.typography.titleSmall,
            fontWeight = FontWeight.Bold,
        )
        read.registry.forEach { entry -> RegistryOnlyRow(entry) }
    } else {
        val byKey = read.registry.associateBy { it.key }
        settings.forEach { setting -> SettingRow(setting, byKey[setting.key]) }
    }
}

/**
 * One key with an effective value — **the number and its label, together.**
 */
@Composable
private fun SettingRow(setting: MeshConfigSetting, spec: MeshConfigRegistryEntry?) {
    var open by remember { mutableStateOf(false) }
    val wired = setting.consumption?.state == "wired"
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f),
        ),
    ) {
        Column(
            Modifier
                .fillMaxWidth()
                .testableClickable("item_mesh_config_key_${setting.key}") { open = !open }
                .padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = setting.key,
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Medium,
                    fontFamily = FontFamily.Monospace,
                )
                ConsumptionBadge(setting.consumption)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = localizedString("surfaces.mesh_config.effective") + " " + setting.effective,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    // Muted unless something in this build actually reads it.
                    color = if (wired) {
                        MaterialTheme.colorScheme.onSurface
                    } else {
                        MaterialTheme.colorScheme.onSurfaceVariant
                    },
                )
                Text(
                    text = setting.unit,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                if (setting.relieved) {
                    Text(
                        text = localizedString("surfaces.mesh_config.baseline") + " " + setting.baseline,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            ConsumptionDetail(setting.consumption)
            TtlLine(setting.ttl)

            AnimatedVisibility(visible = open) {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    KeyValueLine(localizedString("surfaces.mesh_config.baseline"), setting.baseline.toString())
                    KeyValueLine(localizedString("surfaces.mesh_config.consumer"), setting.consumer)
                    KeyValueLine(localizedString("surfaces.mesh_config.knob"), setting.knob)
                    spec?.let {
                        KeyValueLine(localizedString("surfaces.mesh_config.domain"), "${it.min} … ${it.max}")
                        KeyValueLine("polarity", it.polarity)
                    }
                    setting.provenance?.let { p ->
                        Text(
                            text = localizedString("surfaces.mesh_config.provenance") + ": " + p.source,
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.SemiBold,
                        )
                        surfaceText(p.message).takeIf { it.isNotBlank() }?.let {
                            Text(
                                text = it,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        p.decidedByRoot?.let { KeyValueLine("root", it, mono = true) }
                        p.decidedBy?.let { KeyValueLine("author", it, mono = true) }
                        p.rowId?.let { KeyValueLine("row_id", it, mono = true) }
                        p.delegationId?.let { KeyValueLine("delegation_id", it, mono = true) }
                        p.form?.let { KeyValueLine("form", it) }
                        p.grounds?.let { KeyValueLine(localizedString("surfaces.mesh_config.grounds"), it) }
                    }
                    if (setting.perRoot.isNotEmpty()) {
                        Text(
                            text = localizedString("surfaces.mesh_config.per_root"),
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.SemiBold,
                        )
                        setting.perRoot.forEach { rv ->
                            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Text(
                                        text = rv.rootRef,
                                        style = MaterialTheme.typography.labelSmall,
                                        fontFamily = FontFamily.Monospace,
                                    )
                                    Text(
                                        text = localizedString("surfaces.mesh_config.asked") +
                                            " ${rv.asked} → ${rv.effective}",
                                        style = MaterialTheme.typography.labelSmall,
                                    )
                                    if (rv.clamped) {
                                        Text(
                                            text = localizedString("surfaces.mesh_config.clamped"),
                                            style = MaterialTheme.typography.labelSmall,
                                            fontWeight = FontWeight.Bold,
                                            color = SemanticColors.Default.warning,
                                        )
                                    }
                                }
                                TtlLine(rv.ttl)
                            }
                        }
                    }
                    if (setting.clampedRoots.isNotEmpty()) {
                        KeyValueLine(
                            localizedString("surfaces.mesh_config.clamped_roots"),
                            setting.clampedRoots.joinToString(", "),
                            mono = true,
                        )
                    }
                }
            }
        }
    }
}

/**
 * A registry entry with NO value beside it — what the plane looks like when it
 * could not be read. The key, its domain and whether anything would consume it
 * are still true; the value is simply not claimed.
 */
@Composable
private fun RegistryOnlyRow(entry: MeshConfigRegistryEntry) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f),
        ),
    ) {
        Column(Modifier.fillMaxWidth().padding(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = entry.key,
                    style = MaterialTheme.typography.bodySmall,
                    fontFamily = FontFamily.Monospace,
                )
                ConsumptionBadge(entry.consumption)
            }
            KeyValueLine(localizedString("surfaces.mesh_config.domain"), "${entry.min} … ${entry.max}")
            KeyValueLine(localizedString("surfaces.mesh_config.consumer"), entry.consumer)
            ConsumptionDetail(entry.consumption)
        }
    }
}

// ═════════════════════════════════════════════════════════════════════════════
//  History
// ═════════════════════════════════════════════════════════════════════════════

@Composable
private fun MeshConfigHistoryBlock(history: MeshConfigHistory) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        StandingBanner(
            token = history.standing,
            message = surfaceText(history.standingMessage),
            hazard = history.standing == "unreadable" || history.standing == "partial",
        )
        val rows = history.rows
        if (rows == null) {
            Text(
                text = localizedString("surfaces.mesh_config.unknown_values"),
                style = MaterialTheme.typography.bodySmall,
                fontWeight = FontWeight.SemiBold,
            )
            return@Column
        }
        history.total?.let {
            Text(
                text = localizedString(
                    "surfaces.mesh_config.history_total",
                    mapOf("shown" to rows.size.toString(), "total" to it.toString()),
                ),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        surfaceText(history.truncationMessage).takeIf { it.isNotBlank() }?.let {
            Text(text = it, style = MaterialTheme.typography.bodySmall)
        }
        rows.forEach { row ->
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.35f),
                ),
            ) {
                Column(Modifier.fillMaxWidth().padding(10.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            text = row.key ?: (row.dimension ?: ""),
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.Bold,
                            fontFamily = FontFamily.Monospace,
                        )
                        row.value?.let { Text(text = it.toString(), style = MaterialTheme.typography.labelMedium) }
                        row.form?.let {
                            Text(
                                text = it,
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        // Counted and binding are two DIFFERENT facts.
                        if (row.counted) {
                            Text(
                                text = localizedString("surfaces.mesh_config.history_counted"),
                                style = MaterialTheme.typography.labelSmall,
                                color = SemanticColors.Default.info,
                            )
                        }
                        if (row.binding) {
                            Text(
                                text = localizedString("surfaces.mesh_config.history_binding"),
                                style = MaterialTheme.typography.labelSmall,
                                fontWeight = FontWeight.Bold,
                                color = SemanticColors.Default.success,
                            )
                        }
                    }
                    row.rootRef?.let { KeyValueLine("root_ref", it, mono = true) }
                    KeyValueLine(localizedString("surfaces.mesh_config.author"), row.author, mono = true)
                    row.delegationId?.let { KeyValueLine(localizedString("surfaces.mesh_config.delegation"), it, mono = true) }
                    row.ratifiesRowId?.let { KeyValueLine(localizedString("surfaces.mesh_config.ratifies"), it, mono = true) }
                    KeyValueLine(localizedString("surfaces.mesh_config.scrubs"), row.scrubs.toString())
                    row.grounds?.let { KeyValueLine(localizedString("surfaces.mesh_config.grounds"), it) }
                    Text(
                        text = row.assertedAt,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    TtlLine(row.ttl)
                }
            }
        }
    }
}

// ═════════════════════════════════════════════════════════════════════════════
//  Writes
// ═════════════════════════════════════════════════════════════════════════════

@Composable
private fun WriteResultCard(result: MeshConfigWriteResult, onDismiss: () -> Unit) {
    val color = when {
        result.refused -> MaterialTheme.colorScheme.error
        result.dryRun -> SemanticColors.Default.info
        else -> SemanticColors.Default.success
    }
    Surface(
        color = color.copy(alpha = 0.12f),
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = when {
                        result.refused -> localizedString("surfaces.mesh_config.refused")
                        result.dryRun -> localizedString("surfaces.mesh_config.write_dry_run")
                        else -> localizedString("surfaces.mesh_config.admitted")
                    },
                    style = MaterialTheme.typography.labelLarge,
                    fontWeight = FontWeight.Bold,
                    color = color,
                )
                TextButton(
                    onClick = onDismiss,
                    modifier = Modifier.testableClickable("btn_mesh_config_clear_result") { onDismiss() },
                ) {
                    Text(localizedString("mobile.common_close"))
                }
            }
            Text(
                text = refusalText("mesh_config", result.refusal, result.message),
                style = MaterialTheme.typography.bodySmall,
            )
            result.payloadSha256?.let {
                KeyValueLine(localizedString("surfaces.mesh_config.payload_sha256"), it, mono = true)
            }
            result.attestationId?.let { KeyValueLine("attestation_id", it, mono = true) }
            TtlLine(result.ttl)
        }
    }
}

/**
 * The two write paths in one dialog. Neither one clamps or pre-checks a
 * substrate rule: the key list is the server's registry, the emergency bound is
 * shown so the field can be bounded, and the actual refusal is the substrate's.
 */
@Composable
private fun MeshConfigWriteDialog(
    registry: List<MeshConfigRegistryEntry>,
    maxTtlHours: Long,
    busy: Boolean,
    onDismiss: () -> Unit,
    onDurable: (String, Long, String, String, String, String?, Boolean) -> Unit,
    onRelief: (String, Long, String, String, String, Long) -> Unit,
) {
    var key by remember { mutableStateOf(registry.firstOrNull()?.key ?: "") }
    var keyMenuOpen by remember { mutableStateOf(false) }
    var value by remember { mutableStateOf("") }
    var rootRef by remember { mutableStateOf("") }
    var delegationId by remember { mutableStateOf("") }
    var grounds by remember { mutableStateOf("") }
    var ratifies by remember { mutableStateOf("") }
    var emergency by remember { mutableStateOf(false) }
    var ttlHours by remember { mutableStateOf("") }

    val parsedValue = value.trim().toLongOrNull()
    val parsedTtl = ttlHours.trim().toLongOrNull()
    val baseReady = key.isNotBlank() && parsedValue != null && rootRef.isNotBlank() &&
        delegationId.isNotBlank() && grounds.isNotBlank()

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(localizedString("surfaces.mesh_config.write_title")) },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Box {
                    OutlinedButton(
                        onClick = { keyMenuOpen = true },
                        modifier = Modifier
                            .fillMaxWidth()
                            .testableClickable("btn_mesh_config_key_picker") { keyMenuOpen = true },
                    ) {
                        Text(if (key.isBlank()) localizedString("surfaces.mesh_config.write_key") else key)
                    }
                    DropdownMenu(expanded = keyMenuOpen, onDismissRequest = { keyMenuOpen = false }) {
                        registry.forEach { entry ->
                            DropdownMenuItem(
                                text = {
                                    Row(
                                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                                        verticalAlignment = Alignment.CenterVertically,
                                    ) {
                                        Text(entry.key)
                                        // The label follows the key into the
                                        // picker: choosing an `unbuilt` knob
                                        // should never feel like choosing a
                                        // `wired` one.
                                        ConsumptionBadge(entry.consumption)
                                    }
                                },
                                onClick = {
                                    key = entry.key
                                    keyMenuOpen = false
                                },
                            )
                        }
                    }
                }
                registry.firstOrNull { it.key == key }?.let { spec ->
                    KeyValueLine(localizedString("surfaces.mesh_config.domain"), "${spec.min} … ${spec.max}")
                    ConsumptionDetail(spec.consumption)
                }
                OutlinedTextField(
                    value = value,
                    onValueChange = { value = it },
                    label = { Text(localizedString("surfaces.mesh_config.write_value")) },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth().testable("input_mesh_config_value"),
                )
                OutlinedTextField(
                    value = rootRef,
                    onValueChange = { rootRef = it },
                    label = { Text(localizedString("surfaces.mesh_config.write_root")) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth().testable("input_mesh_config_root"),
                )
                OutlinedTextField(
                    value = delegationId,
                    onValueChange = { delegationId = it },
                    label = { Text(localizedString("surfaces.mesh_config.write_delegation")) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth().testable("input_mesh_config_delegation"),
                )
                OutlinedTextField(
                    value = grounds,
                    onValueChange = { grounds = it },
                    label = { Text(localizedString("surfaces.mesh_config.write_grounds")) },
                    minLines = 2,
                    modifier = Modifier.fillMaxWidth().testable("input_mesh_config_grounds"),
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(
                        selected = !emergency,
                        onClick = { emergency = false },
                        label = { Text(localizedString("surfaces.mesh_config.form_durable")) },
                        modifier = Modifier.testableClickable("chip_mesh_config_durable") { emergency = false },
                    )
                    FilterChip(
                        selected = emergency,
                        onClick = { emergency = true },
                        label = { Text(localizedString("surfaces.mesh_config.form_emergency")) },
                        modifier = Modifier.testableClickable("chip_mesh_config_emergency") { emergency = true },
                    )
                }
                if (emergency) {
                    OutlinedTextField(
                        value = ttlHours,
                        onValueChange = { ttlHours = it },
                        label = {
                            Text(
                                localizedString("surfaces.mesh_config.write_ttl") +
                                    " (≤ $maxTtlHours)",
                            )
                        },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth().testable("input_mesh_config_ttl"),
                    )
                } else {
                    OutlinedTextField(
                        value = ratifies,
                        onValueChange = { ratifies = it },
                        label = { Text(localizedString("surfaces.mesh_config.write_ratifies")) },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth().testable("input_mesh_config_ratifies"),
                    )
                }
            }
        },
        confirmButton = {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (!emergency) {
                    TextButton(
                        onClick = {
                            onDurable(key, parsedValue ?: 0L, rootRef.trim(), delegationId.trim(), grounds.trim(), ratifies.trim().ifBlank { null }, true)
                        },
                        enabled = baseReady && !busy,
                        modifier = Modifier.testableClickable("btn_mesh_config_dry_run") {},
                    ) {
                        Text(localizedString("surfaces.mesh_config.write_dry_run"))
                    }
                }
                TextButton(
                    onClick = {
                        if (emergency) {
                            onRelief(key, parsedValue ?: 0L, rootRef.trim(), delegationId.trim(), grounds.trim(), parsedTtl ?: 0L)
                        } else {
                            onDurable(key, parsedValue ?: 0L, rootRef.trim(), delegationId.trim(), grounds.trim(), ratifies.trim().ifBlank { null }, false)
                        }
                    },
                    enabled = baseReady && !busy && (!emergency || parsedTtl != null),
                    modifier = Modifier.testableClickable("btn_mesh_config_submit") {},
                ) {
                    Text(
                        if (emergency) {
                            localizedString("surfaces.mesh_config.write_relief")
                        } else {
                            localizedString("surfaces.mesh_config.write_durable")
                        },
                    )
                }
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                modifier = Modifier.testableClickable("btn_mesh_config_write_cancel") { onDismiss() },
            ) {
                Text(localizedString("mobile.common_cancel"))
            }
        },
    )
}
