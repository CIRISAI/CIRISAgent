package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.nav.LocalIsCompactWindow
import ai.ciris.mobile.shared.viewmodels.BootstrapPhase
import ai.ciris.mobile.shared.viewmodels.NodeSwitcherViewModel
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
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Claim-Ownership screen — the last UI piece of the founder flow.
 *
 * The founder reaches a node and becomes its SYSTEM_ADMIN by entering the
 * node's **NodeCode** (`CIRIS-V1-…`, pasted or scanned) and the one-time
 * **claim PIN** the operator reads off the node's console. This screen is a
 * pure Compose consumer of the already-built [NodeSwitcherViewModel]: it does
 * NOT reinvent any of the connect/pin/claim logic. On submit it runs
 *
 *   connectByNodeCode(code)  →  (on PINNED)  →  claimAdmin(profile, pin, …)
 *
 * driving the existing `NodeBootstrapState` / `BootstrapPhase` machine. Step
 * progress (DECODING → PINNING → PINNED) and the claim result
 * (claimedRole == SYSTEM_ADMIN) are surfaced straight off the VM state.
 *
 * @param onClaimedAnother re-enters this screen fresh to claim a second node
 *        (founder flow claims node A then node B before consent objects).
 * @param onProceedToConsent navigates to the consent-objects card surface
 *        (the main Interact page) once at least one node is claimed.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ClaimNodeScreen(
    viewModel: NodeSwitcherViewModel,
    onBack: () -> Unit,
    onClaimedAnother: () -> Unit = {},
    onProceedToConsent: () -> Unit = {},
) {
    val bootstrap by viewModel.bootstrap.collectAsState()

    var codeInput by remember { mutableStateOf("") }
    var pinInput by remember { mutableStateOf("") }
    var displayNameInput by remember { mutableStateOf("") }
    // CIRISServer v0.4.3: who this node is being added to (self/family/community).
    // Default to "self" but make the founder pick before claiming.
    var cohortScope by remember { mutableStateOf("self") }

    // While the connect-or-claim pipeline is running we disable the button.
    val inFlight = bootstrap.inProgress || bootstrap.claimInProgress
    val pinned = bootstrap.pinnedProfile
    val claimed = bootstrap.isAdminClaimed

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("mobile.claim_node_title")) },
                navigationIcon = {
                    if (!LocalIsCompactWindow.current) {
                        IconButton(
                            onClick = onBack,
                            modifier = Modifier.testable("btn_claim_node_back"),
                        ) {
                            Icon(
                                imageVector = CIRISIcons.arrowBack,
                                contentDescription = localizedString("mobile.claim_node_back"),
                            )
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
        ) {
            Text(
                text = localizedString("mobile.claim_node_heading"),
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onBackground,
            )
            Spacer(Modifier.height(4.dp))
            Text(
                text = localizedString("mobile.claim_node_desc"),
                fontSize = 13.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Spacer(Modifier.height(20.dp))

            // ── NodeCode field (paste / QR forms; dashed CIRIS-V1-… accepted) ──
            OutlinedTextField(
                value = codeInput,
                onValueChange = { codeInput = it },
                label = { Text(localizedString("mobile.claim_node_code_label")) },
                placeholder = { Text("CIRIS-V1-...") },
                singleLine = false,
                enabled = !inFlight,
                modifier = Modifier
                    .fillMaxWidth()
                    .testable("field_claim_node_code"),
            )

            Spacer(Modifier.height(12.dp))

            // ── Claim PIN field (one-time PIN from the node's console) ─────────
            OutlinedTextField(
                value = pinInput,
                onValueChange = { pinInput = it },
                label = { Text(localizedString("mobile.claim_node_pin_label")) },
                placeholder = { Text("XXXX-XXXX") },
                singleLine = true,
                enabled = !inFlight,
                modifier = Modifier
                    .fillMaxWidth()
                    .testable("field_claim_node_pin"),
            )

            Spacer(Modifier.height(12.dp))

            // ── Display name bound to the founder's federation identity ────────
            OutlinedTextField(
                value = displayNameInput,
                onValueChange = { displayNameInput = it },
                label = { Text(localizedString("mobile.claim_node_displayname_label")) },
                placeholder = { Text(localizedString("mobile.claim_node_displayname_hint")) },
                singleLine = true,
                enabled = !inFlight,
                modifier = Modifier
                    .fillMaxWidth()
                    .testable("field_claim_node_displayname"),
            )

            Spacer(Modifier.height(16.dp))

            // ── Cohort-scope picker (CIRISServer v0.4.3) ──────────────────────
            // "Part of adding a node is specifying whether you are adding it to
            // yourself, your family, or a community." Required by the node or the
            // claim 400s. The selection rides inside the signed body.
            CohortScopeSelector(
                selected = cohortScope,
                onSelect = { cohortScope = it },
                enabled = !inFlight && !claimed,
            )

            Spacer(Modifier.height(20.dp))

            // ── Claim button: connectByNodeCode → (PINNED) → claimAdmin ───────
            Button(
                onClick = {
                    viewModel.clearBootstrap()
                    // Step 1: decode → connect → identity-pin. We observe the
                    // resulting PINNED profile below and chain the claim then.
                    viewModel.connectByNodeCode(codeInput.trim())
                },
                enabled = !inFlight && codeInput.isNotBlank() && pinInput.isNotBlank() && !claimed,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(48.dp)
                    .testableClickable("btn_claim_node_submit") {
                        viewModel.clearBootstrap()
                        viewModel.connectByNodeCode(codeInput.trim())
                    },
            ) {
                if (inFlight) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(18.dp),
                        strokeWidth = 2.dp,
                        color = Color.White,
                    )
                    Spacer(Modifier.width(10.dp))
                }
                Text(
                    text = when {
                        bootstrap.claimInProgress -> localizedString("mobile.claim_node_claiming")
                        bootstrap.inProgress -> localizedString("mobile.claim_node_connecting")
                        else -> localizedString("mobile.claim_node_button")
                    },
                )
            }

            // Once the node is identity-pinned, chain the admin claim. Driven
            // off VM state so it survives recomposition and never double-fires
            // (claimAdmin/connectByNodeCode both guard on their in-progress
            // flags). We trigger only on the PINNED→not-yet-claimed edge.
            androidx.compose.runtime.LaunchedEffect(
                bootstrap.phase,
                pinned?.id,
            ) {
                if (pinned != null &&
                    bootstrap.phase == BootstrapPhase.PINNED &&
                    !claimed &&
                    !bootstrap.claimInProgress &&
                    bootstrap.claimError == null
                ) {
                    viewModel.claimAdmin(
                        profile = pinned,
                        claimPin = pinInput.trim(),
                        cohortScope = cohortScope,
                    )
                }
            }

            Spacer(Modifier.height(20.dp))

            // ── Step progress: DECODING → connecting → PINNING → PINNED ───────
            StepProgress(bootstrap.phase, pinned != null, claimed)

            // ── Result / error surfaces ───────────────────────────────────────
            bootstrap.error?.let { err ->
                Spacer(Modifier.height(16.dp))
                ResultCard(
                    title = localizedString("mobile.claim_node_connect_failed"),
                    body = err,
                    success = false,
                )
            }

            if (claimed) {
                Spacer(Modifier.height(16.dp))
                val role = bootstrap.claimedRole.orEmpty()
                val nodeName = pinned?.name ?: pinned?.baseUrl ?: "node"
                ResultCard(
                    title = if (role.equals("SYSTEM_ADMIN", ignoreCase = true)) {
                        localizedString("mobile.claim_node_success_title")
                    } else {
                        localizedString("mobile.claim_node_claimed_title")
                    },
                    body = localizedString("mobile.claim_node_success_body")
                        .replace("{node}", nodeName)
                        .replace("{role}", role),
                    success = true,
                )

                Spacer(Modifier.height(16.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    OutlinedButton(
                        onClick = {
                            // Claim a second node (A then B). Reset the form +
                            // bootstrap so this screen is fresh for node B.
                            codeInput = ""
                            pinInput = ""
                            viewModel.clearBootstrap()
                            onClaimedAnother()
                        },
                        modifier = Modifier
                            .weight(1f)
                            .testableClickable("btn_claim_node_another") {},
                    ) {
                        Text(localizedString("mobile.claim_node_claim_another"))
                    }
                    Button(
                        onClick = {
                            viewModel.clearBootstrap()
                            onProceedToConsent()
                        },
                        modifier = Modifier
                            .weight(1f)
                            .testableClickable("btn_claim_node_to_consent") {},
                    ) {
                        Text(localizedString("mobile.claim_node_to_consent"))
                    }
                }
            } else if (bootstrap.claimError != null) {
                Spacer(Modifier.height(16.dp))
                ResultCard(
                    title = localizedString("mobile.claim_node_claim_failed"),
                    body = bootstrap.claimError!!,
                    success = false,
                )
            }
        }
    }
}

/**
 * Cohort-scope picker — "Add this node to: Yourself / Your family / A community".
 *
 * A simple radio group (least-churn, follows the screen's existing flat Compose
 * style). The chosen value (`self` | `family` | `community`) is what
 * [NodeSwitcherViewModel.claimAdmin] places in the signed claim body's
 * `cohort_scope`, which CIRISServer v0.4.3 requires.
 */
@Composable
private fun CohortScopeSelector(
    selected: String,
    onSelect: (String) -> Unit,
    enabled: Boolean,
) {
    // value → label-key (localized; fallback-to-key is fine).
    val options = listOf(
        "self" to "mobile.claim_node_cohort_self",
        "family" to "mobile.claim_node_cohort_family",
        "community" to "mobile.claim_node_cohort_community",
    )
    Column(modifier = Modifier.fillMaxWidth()) {
        Text(
            text = localizedString("mobile.claim_node_cohort_label"),
            fontSize = 13.sp,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onBackground,
        )
        Spacer(Modifier.height(6.dp))
        options.forEach { (value, labelKey) ->
            val isSel = value == selected
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 2.dp)
                    .testableClickable("radio_cohort_$value") {
                        if (enabled) onSelect(value)
                    },
            ) {
                RadioButton(
                    selected = isSel,
                    onClick = { if (enabled) onSelect(value) },
                    enabled = enabled,
                )
                Spacer(Modifier.width(4.dp))
                Text(
                    text = localizedString(labelKey),
                    fontSize = 14.sp,
                    color = if (enabled) {
                        MaterialTheme.colorScheme.onSurface
                    } else {
                        MaterialTheme.colorScheme.onSurfaceVariant
                    },
                )
            }
        }
        Spacer(Modifier.height(4.dp))
        Text(
            text = localizedString("mobile.claim_node_cohort_note"),
            fontSize = 11.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

/** Compact ordered step list reflecting the bootstrap phase + claim. */
@Composable
private fun StepProgress(
    phase: BootstrapPhase,
    pinned: Boolean,
    claimed: Boolean,
) {
    // Ordinal of the highest reached step (0..4).
    val reached = when {
        claimed -> 4
        pinned || phase == BootstrapPhase.PINNED -> 3
        phase == BootstrapPhase.PINNING -> 2
        phase == BootstrapPhase.DECODING -> 1
        phase == BootstrapPhase.NEED_URL -> 1
        else -> 0
    }
    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant,
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            StepRow(localizedString("mobile.claim_node_step_decode"), reached >= 1)
            StepRow(localizedString("mobile.claim_node_step_connect"), reached >= 2)
            StepRow(localizedString("mobile.claim_node_step_pin"), reached >= 3)
            StepRow(localizedString("mobile.claim_node_step_claim"), reached >= 4)
        }
    }
}

@Composable
private fun StepRow(label: String, done: Boolean) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier.padding(vertical = 2.dp),
    ) {
        Text(
            text = if (done) "✓" else "•",
            fontSize = 13.sp,
            fontWeight = FontWeight.Bold,
            color = if (done) {
                MaterialTheme.colorScheme.primary
            } else {
                MaterialTheme.colorScheme.onSurfaceVariant
            },
            modifier = Modifier.width(20.dp),
        )
        Text(
            text = label,
            fontSize = 12.sp,
            color = if (done) {
                MaterialTheme.colorScheme.onSurface
            } else {
                MaterialTheme.colorScheme.onSurfaceVariant
            },
        )
    }
}

@Composable
private fun ResultCard(title: String, body: String, success: Boolean) {
    val accent = if (success) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error
    Surface(
        color = accent.copy(alpha = 0.10f),
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(
                text = title,
                fontSize = 14.sp,
                fontWeight = FontWeight.Bold,
                color = accent,
            )
            Spacer(Modifier.height(4.dp))
            Text(
                text = body,
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.onSurface,
            )
        }
    }
}
