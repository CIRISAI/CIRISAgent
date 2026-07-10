package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.safety.AgeBand
import ai.ciris.mobile.shared.models.safety.WatchlistClass
import ai.ciris.mobile.shared.models.safety.WatchlistMode
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.nav.LocalIsCompactWindow
import ai.ciris.mobile.shared.viewmodels.SafetyViewModel
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * **Child-safety / watchlist card** (CC 4.5.7).
 *
 * Two things, all driving the local node's `/v1/safety/` routes:
 *  1. **Protective posture** — `GET /v1/safety/status/{key_id}` shows this
 *     identity's age assurance + the honest framing (self-declared is
 *     unfalsifiable; misdeclaration routes to adjudication, never slashing).
 *  2. **Per-group watchlist** — for a group you hold `moderate` over, opt into a
 *     content watchlist. `GET /v1/safety/watchlist/{group}` lists current
 *     enables; `POST /v1/safety/watchlist` enables/disables one. The node admits
 *     IFF the signer holds `moderate` (CSAM also `takedown`); non-holders get
 *     403 surfaced here.
 *
 * **Load-bearing honest framing (prominent, kept TRUE from the server's wire):**
 *  - default OFF, opt-in, **per-group, NEVER global** (no fabric-wide watchlist).
 *  - **we do not scan private (self/family) content** — detection runs only at
 *    the share/publish seam.
 *  - CSAM hashes are operator-provisioned (never shipped); the NCMEC report is
 *    the operator's duty, not the fabric's.
 *
 * The app holds NO keys: every action is a localhost call; the node signs.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChildSafetyScreen(
    viewModel: SafetyViewModel,
    onBack: () -> Unit,
) {
    val state by viewModel.state.collectAsState()

    LaunchedEffect(Unit) { viewModel.probeIdentityAndStatus() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("mobile.child_safety_title")) },
                navigationIcon = {
                    if (!LocalIsCompactWindow.current) {
                        IconButton(onClick = onBack, modifier = Modifier.testable("btn_child_safety_back")) {
                            Icon(CIRISIcons.arrowBack, contentDescription = localizedString("mobile.back"))
                        }
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            // ── The load-bearing honesty banner (always visible, never buried) ──
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = MaterialTheme.colorScheme.primaryContainer,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    SectionHeader(CIRISIcons.shield, localizedString("mobile.child_safety_honesty_title"))
                    Text(localizedString("mobile.child_safety_honesty_pergroup"),
                        fontSize = 13.sp, color = MaterialTheme.colorScheme.onPrimaryContainer)
                    Spacer(Modifier.height(6.dp))
                    Text(localizedString("mobile.child_safety_honesty_noprivate"),
                        fontSize = 13.sp, color = MaterialTheme.colorScheme.onPrimaryContainer)
                    Spacer(Modifier.height(6.dp))
                    Text(localizedString("mobile.child_safety_honesty_hashes"),
                        fontSize = 13.sp, color = MaterialTheme.colorScheme.onPrimaryContainer)
                }
            }

            // ── Protective posture (age assurance + honesty) ──
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = MaterialTheme.colorScheme.surfaceVariant,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    SectionHeader(CIRISIcons.person, localizedString("mobile.child_safety_posture_section"))
                    if (state.statusLoading) {
                        CircularProgressIndicator(Modifier.width(20.dp).height(20.dp), strokeWidth = 2.dp)
                    } else {
                        val band = state.ageAssurance?.band
                        val posture = when (band) {
                            AgeBand.ADULT -> localizedString("mobile.child_safety_posture_adult")
                            AgeBand.MINOR -> localizedString("mobile.child_safety_posture_minor")
                            null -> localizedString("mobile.child_safety_posture_unknown")
                        }
                        Text(posture, fontSize = 14.sp, fontWeight = FontWeight.Medium,
                            color = MaterialTheme.colorScheme.onSurface)
                        state.statusHonesty?.let {
                            if (it.selfLevelUnfalsifiable) {
                                Text(localizedString("mobile.child_safety_posture_self_unfalsifiable"),
                                    fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    modifier = Modifier.padding(top = 6.dp))
                            }
                        }
                    }
                }
            }

            // ── Per-group watchlist (opt-in) ──
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = MaterialTheme.colorScheme.surfaceVariant,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    SectionHeader(CIRISIcons.lock, localizedString("mobile.child_safety_watchlist_section"))
                    Text(localizedString("mobile.child_safety_watchlist_intro"),
                        fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(bottom = 10.dp))

                    OutlinedTextField(
                        value = state.watchlistGroupKeyId,
                        onValueChange = viewModel::setWatchlistGroupKeyId,
                        label = { Text(localizedString("mobile.child_safety_group_label")) },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth().testable("input_watchlist_group"),
                    )
                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(
                        value = state.watchlistId,
                        onValueChange = viewModel::setWatchlistId,
                        label = { Text(localizedString("mobile.child_safety_watchlist_id_label")) },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth().testable("input_watchlist_id"),
                    )

                    // Class (CSAM vs other-content).
                    Spacer(Modifier.height(8.dp))
                    Text(localizedString("mobile.child_safety_class_label"),
                        fontSize = 12.sp, fontWeight = FontWeight.Medium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        RadioButton(
                            selected = state.watchlistClass == WatchlistClass.OTHER_CONTENT,
                            onClick = { viewModel.setWatchlistClass(WatchlistClass.OTHER_CONTENT) },
                            modifier = Modifier.testable("class_other"),
                        )
                        Text(localizedString("mobile.child_safety_class_other"),
                            fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurface)
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        RadioButton(
                            selected = state.watchlistClass == WatchlistClass.CSAM,
                            onClick = { viewModel.setWatchlistClass(WatchlistClass.CSAM) },
                            modifier = Modifier.testable("class_csam"),
                        )
                        Text(localizedString("mobile.child_safety_class_csam"),
                            fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurface)
                    }

                    // Mode (alert-only vs enforce).
                    Spacer(Modifier.height(8.dp))
                    Text(localizedString("mobile.child_safety_mode_label"),
                        fontSize = 12.sp, fontWeight = FontWeight.Medium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        RadioButton(
                            selected = state.watchlistMode == WatchlistMode.ALERT_ONLY,
                            onClick = { viewModel.setWatchlistMode(WatchlistMode.ALERT_ONLY) },
                            modifier = Modifier.testable("mode_alert"),
                        )
                        Text(localizedString("mobile.child_safety_mode_alert"),
                            fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurface)
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        RadioButton(
                            selected = state.watchlistMode == WatchlistMode.ENFORCE,
                            onClick = { viewModel.setWatchlistMode(WatchlistMode.ENFORCE) },
                            modifier = Modifier.testable("mode_enforce"),
                        )
                        Text(localizedString("mobile.child_safety_mode_enforce"),
                            fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurface)
                    }

                    Spacer(Modifier.height(12.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(
                            onClick = { viewModel.setWatchlistEnabled(true) },
                            enabled = !state.watchlistMutating,
                            modifier = Modifier.testable("btn_watchlist_enable"),
                        ) {
                            if (state.watchlistMutating) {
                                CircularProgressIndicator(Modifier.width(16.dp).height(16.dp), strokeWidth = 2.dp)
                                Spacer(Modifier.width(8.dp))
                            }
                            Text(localizedString("mobile.child_safety_enable"))
                        }
                        OutlinedButton(
                            onClick = { viewModel.setWatchlistEnabled(false) },
                            enabled = !state.watchlistMutating,
                            modifier = Modifier.testable("btn_watchlist_disable"),
                        ) { Text(localizedString("mobile.child_safety_disable")) }
                        OutlinedButton(
                            onClick = { viewModel.loadWatchlist() },
                            modifier = Modifier.testable("btn_watchlist_refresh"),
                        ) { Text(localizedString("mobile.child_safety_refresh")) }
                    }

                    // Current enables.
                    if (state.watchlistEnables.isNotEmpty()) {
                        Spacer(Modifier.height(12.dp))
                        Text(localizedString("mobile.child_safety_current_enables"),
                            fontSize = 12.sp, fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onSurface)
                        state.watchlistEnables.forEach { e ->
                            Text("• ${e.watchlistId} (${e.watchlistClass}, ${e.mode})",
                                fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant,
                                modifier = Modifier.padding(top = 2.dp))
                        }
                    }
                }
            }

            state.error?.let {
                Text(it, color = MaterialTheme.colorScheme.error, fontSize = 13.sp)
            }
            state.message?.let {
                Text(it, color = MaterialTheme.colorScheme.primary, fontSize = 13.sp)
            }
        }
    }
}
