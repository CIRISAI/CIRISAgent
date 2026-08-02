package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.platform.TestAutomation
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.components.AnnounceDecisionCard
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.nav.LocalIsCompactWindow
import ai.ciris.mobile.shared.viewmodels.FederationIdentitySetupState
import ai.ciris.mobile.shared.viewmodels.NodeSwitcherViewModel
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
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
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * **Add Federation ID (catch-up flow)** — the guided path for an EXISTING logged-in
 * user whose node is owned the legacy way (a password/OAuth ROOT WA with NO fed-ID).
 *
 * These users must NOT redo account creation. They take the session-authed
 * `POST /v1/self/upgrade-owner` path (mint fed-ID + re-root the node on it, login
 * preserved) — NOT the first-run `claim-remote` path (which needs a one-time console
 * PIN that no longer exists on an already-claimed node). The whole flow is driven by
 * [NodeSwitcherViewModel.upgradeToFedId].
 *
 * Steps (single scrolling screen):
 *  1. A UNIQUE, non-generic fed-ID label (same validation as the first-run wizard —
 *     [FederationIdentitySetupState.REJECTED_GENERIC_LABELS] — to avoid the
 *     `ciris-client-user` identity collision). This names + keys the "one canonical
 *     you".
 *  2. The SAME first-class announce decision as first-run ([AnnounceDecisionCard]):
 *     announcing is what unlocks sending reasoning traces + joining communities. The
 *     trace opt-in is gated inside that card (only enabled when announce is ON).
 *  3. Confirm → run the upgrade (mint → re-root → optional announce → optional trace
 *     opt-in). On success the screen leaves via [onDone]; the success/soft-failure
 *     notice is surfaced by the node-management surface.
 *
 * The app performs NO crypto — the local node mints + signs everything.
 */
/**
 * Localized string with a hardcoded fallback for keys not yet in the manifest.
 * [localizedString] returns the KEY itself when a key is absent (not ""), so a
 * plain `.ifEmpty {}` wouldn't fall back — treat "blank OR equals the key" as
 * missing and render [fallback]. Lets this screen ship before en.json is updated.
 */
@Composable
private fun l10nOr(key: String, fallback: String): String {
    val v = localizedString(key)
    return if (v.isBlank() || v == key) fallback else v
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AddFederationIdScreen(
    viewModel: NodeSwitcherViewModel,
    onBack: () -> Unit,
    /** Navigate away after a successful upgrade (typically back to Manage Nodes). */
    onDone: () -> Unit,
) {
    val inProgress by viewModel.upgradeInProgress.collectAsState()
    val error by viewModel.error.collectAsState()

    var label by remember { mutableStateOf("") }
    var announce by remember { mutableStateOf(false) }
    var traceOptIn by remember { mutableStateOf(false) }
    var submitted by remember { mutableStateOf(false) }

    // Label validation mirrors the first-run wizard: a name is REQUIRED and must not
    // be a generic default (those collide identities across devices).
    val labelTrimmed = label.trim()
    val labelIsGeneric = labelTrimmed.lowercase() in
        FederationIdentitySetupState.REJECTED_GENERIC_LABELS
    val labelHasError = labelTrimmed.isEmpty() || labelIsGeneric
    val canConfirm = !labelHasError && !inProgress

    // Test automation: route /input requests into the label field (the pattern
    // SetupScreen/LoginScreen/InteractScreen use — without this, /input on
    // input_fed_label "succeeds" but the Compose state never updates).
    val textInputRequest by TestAutomation.textInputRequests.collectAsState()
    LaunchedEffect(textInputRequest) {
        textInputRequest?.let { request ->
            if (request.testTag == "input_fed_label") {
                label = if (request.clearFirst) request.text else label + request.text
                TestAutomation.clearTextInputRequest()
            }
        }
    }

    // Leave on a clean completion; re-arm for retry if the upgrade errored.
    LaunchedEffect(submitted, inProgress, error) {
        if (submitted && !inProgress) {
            if (error == null) {
                onDone()
            } else {
                submitted = false
            }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(l10nOr("mobile.add_fedid_title", "Add Federation ID"))
                },
                navigationIcon = {
                    if (!LocalIsCompactWindow.current) {
                        IconButton(
                            onClick = onBack,
                            modifier = Modifier.testableClickable("btn_add_fedid_back") { onBack() },
                        ) {
                            Icon(
                                imageVector = CIRISIcons.arrowBack,
                                contentDescription = localizedString("mobile.common_back"),
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
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text(
                text = l10nOr(
                    "mobile.add_fedid_intro",
                    "You're signed in already — this adds a federation ID to your existing " +
                        "account without re-creating it. Your login is preserved.",
                ),
                fontSize = 13.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            // ── Step 1: unique, non-generic fed-ID label ─────────────────────
            Text(
                text = l10nOr("mobile.add_fedid_label_heading", "Name your federation ID"),
                fontSize = 15.sp,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.onSurface,
            )
            OutlinedTextField(
                value = label,
                onValueChange = { label = it },
                label = {
                    Text(localizedString("mobile.setup_fedid_label").ifEmpty { "Federation ID name" })
                },
                placeholder = {
                    Text(
                        localizedString("mobile.setup_fedid_label_hint")
                            .ifEmpty { "e.g. firstname-lastname-v1" }
                    )
                },
                singleLine = true,
                isError = labelHasError,
                enabled = !inProgress,
                modifier = Modifier
                    .fillMaxWidth()
                    .testable("input_fed_label"),
            )
            Text(
                text = when {
                    labelTrimmed.isEmpty() ->
                        localizedString("mobile.setup_fedid_label_required")
                            .ifEmpty { "A unique name is required." }
                    labelIsGeneric ->
                        localizedString("mobile.setup_fedid_label_generic")
                            .ifEmpty { "That name is too generic — choose a unique one." }
                    else ->
                        localizedString("mobile.setup_fedid_label_ok").ifEmpty { "Looks good." }
                },
                color = if (labelHasError) {
                    MaterialTheme.colorScheme.error
                } else {
                    MaterialTheme.colorScheme.primary
                },
                fontSize = 12.sp,
            )

            // ── Step 2: the first-class announce decision (reused) ───────────
            // Turning announce OFF also clears the trace opt-in so state stays
            // consistent (un-announced nodes never federate their traces).
            AnnounceDecisionCard(
                announce = announce,
                onAnnounceChange = { on ->
                    announce = on
                    if (!on) traceOptIn = false
                },
                traceOptIn = traceOptIn,
                onTraceOptInChange = { traceOptIn = it },
            )

            // ── Errors ───────────────────────────────────────────────────────
            error?.let { msg ->
                Surface(
                    color = MaterialTheme.colorScheme.errorContainer,
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(
                        text = msg,
                        fontSize = 12.sp,
                        color = MaterialTheme.colorScheme.onErrorContainer,
                        modifier = Modifier.padding(10.dp),
                    )
                }
            }

            // ── Step 3: confirm ──────────────────────────────────────────────
            // Shared by the Button and the test-automation click registry
            // (testableClickable), mirroring the SetupScreen btn_next pattern.
            val onConfirm = {
                if (canConfirm) {
                    submitted = true
                    viewModel.upgradeToFedId(
                        label = labelTrimmed,
                        announce = announce,
                        traceOptIn = traceOptIn,
                    )
                }
            }
            Button(
                onClick = onConfirm,
                enabled = canConfirm,
                modifier = Modifier
                    .fillMaxWidth()
                    .testableClickable("btn_add_fedid_confirm") { onConfirm() },
            ) {
                if (inProgress) {
                    CircularProgressIndicator(modifier = Modifier.size(16.dp), strokeWidth = 2.dp)
                    Spacer(Modifier.width(8.dp))
                }
                Text(l10nOr("mobile.add_fedid_confirm", "Add Federation ID"))
            }
        }
    }
}
