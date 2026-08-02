package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.platform.TestAutomation
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.icons.CIRISMaterialIcons
import ai.ciris.mobile.shared.ui.icons.ContentCopy
import ai.ciris.mobile.shared.viewmodels.DelegationsViewModel
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * **Delegations** — authorize an agent or another person to act on your behalf.
 *
 * Organized as three clear flows (the same shape Consent uses):
 *  - **Offer a code** (OUTGOING) — you generate a one-time offer code / PIN to hand
 *    to an agent or person so they can act for you.
 *  - **Approve a code** (INCOMING) — someone gives you a request code; you review +
 *    approve it (the human-consent gate).
 *  - **Manage** (CRUD) — the active delegations, with a revoke control.
 *
 * The app drives the LOCAL node only with your owner session — it holds no keys.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DelegationsScreen(
    viewModel: DelegationsViewModel,
    onBack: () -> Unit,
    /** Navigate to the Contacts picker so the user can choose a known fed-ID. */
    onOpenContacts: (() -> Unit)? = null,
    /**
     * When the user picks an identity in the Contacts picker and returns here,
     * this is the selected key_id. Delegations reads it and fills [existingKeyId].
     * The caller should clear this after it's been consumed (by passing null again).
     */
    pickedIdentityKeyId: String? = null,
    /** Called after [pickedIdentityKeyId] has been consumed so the caller can clear it. */
    onPickedIdentityConsumed: (() -> Unit)? = null,
) {
    val delegations by viewModel.delegations.collectAsState()
    val loading by viewModel.loading.collectAsState()
    val busy by viewModel.busy.collectAsState()
    val error by viewModel.error.collectAsState()
    val notice by viewModel.notice.collectAsState()
    val lastCreated by viewModel.lastCreated.collectAsState()
    var userCode by remember { mutableStateOf("") }
    var delegateLabel by remember { mutableStateOf("") }
    // mode: "create" = mint a fresh agent fed-ID; "existing" = bind a known key_id.
    var delegateMode by remember { mutableStateOf("create") }
    var existingKeyId by remember { mutableStateOf("") }
    // ── Constraints the owner attaches to the grant (all optional) ────────────
    // goal = free-text intent; restrictActions toggles the allow-list (off = every
    // owner verb permitted; on = only the selected verbs, none = read-only); deny
    // always wins. Empty across the board = an unconstrained, full-authority grant.
    var delegationGoal by remember { mutableStateOf("") }
    var restrictActions by remember { mutableStateOf(false) }
    var allowVerbs by remember { mutableStateOf(setOf<String>()) }
    var denyVerbs by remember { mutableStateOf(setOf<String>()) }
    // The constraints last submitted with an offer — drives the characteristics
    // fallback display when the node doesn't echo a `delegation` object.
    var lastConstraints by remember {
        mutableStateOf<ai.ciris.mobile.shared.models.federation.DelegationConstraints?>(null)
    }
    // Approve-side constraints (TIGHTEN-ONLY — narrows the agent's requested grant).
    var approveGoal by remember { mutableStateOf("") }
    var approveRestrict by remember { mutableStateOf(false) }
    var approveAllow by remember { mutableStateOf(setOf<String>()) }
    var approveDeny by remember { mutableStateOf(setOf<String>()) }
    // The active pane: "offer" (outgoing) | "incoming" (approve) | "manage" (CRUD).
    var pane by remember { mutableStateOf("offer") }

    // Load the active delegations when the screen is shown — by now the owner is logged in
    // and the bearer is set (the VM intentionally does NOT fetch at init, which runs
    // pre-login → 401). This is the page's load + the post-login retry. (#117.)
    LaunchedEffect(Unit) {
        viewModel.refresh()
    }

    // Test automation: let the UI-automation server's /input drive this screen's
    // text fields (they're `testable()` = position-only, so without this collector
    // /input silently no-ops and createDelegation bails on an empty label). Mirrors
    // LoginScreen/SetupScreen.
    val textInputRequest by TestAutomation.textInputRequests.collectAsState()
    LaunchedEffect(textInputRequest) {
        textInputRequest?.let { request ->
            when (request.testTag) {
                "input_delegation_label" -> {
                    delegateLabel = if (request.clearFirst) request.text else delegateLabel + request.text
                    TestAutomation.clearTextInputRequest()
                }
                "input_delegation_key_id" -> {
                    existingKeyId = if (request.clearFirst) request.text else existingKeyId + request.text
                    TestAutomation.clearTextInputRequest()
                }
                "input_delegation_code" -> {
                    userCode = if (request.clearFirst) request.text else userCode + request.text
                    TestAutomation.clearTextInputRequest()
                }
            }
        }
    }

    // When the Contacts picker returns a selection, fill the key_id field + jump to
    // the Offer pane in "existing fed-ID" mode.
    LaunchedEffect(pickedIdentityKeyId) {
        if (!pickedIdentityKeyId.isNullOrBlank()) {
            existingKeyId = pickedIdentityKeyId
            // Auto-populate the label from the chosen identity — derive the human label
            // from its key_id (strip the trailing `-<fp>`, e.g. `lapbuntu2-claude-mrqmyy…`
            // → `lapbuntu2-claude`). In existing mode the label is a display echo, not a
            // mint input, so reflecting the picked identity beats forcing a re-type. (#134.)
            delegateLabel = pickedIdentityKeyId.substringBeforeLast('-').ifBlank { pickedIdentityKeyId }
            delegateMode = "existing"
            pane = "offer"
            onPickedIdentityConsumed?.invoke()
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("mobile.delegations_title")) },
                navigationIcon = {
                    IconButton(
                        onClick = onBack,
                        modifier = Modifier.testableClickable("btn_delegations_back") { onBack() },
                    ) {
                        Icon(CIRISIcons.arrowBack, contentDescription = "Back")
                    }
                },
            )
        },
    ) { pad ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(pad)
                .padding(horizontal = 16.dp)
                .verticalScroll(rememberScrollState()),
        ) {
            Spacer(Modifier.height(8.dp))
            Text(
                text = "Delegate to an agent or person",
                fontSize = 16.sp,
                fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.height(2.dp))
            Text(
                text = "Authorize an agent or another person's fed-ID to act on your behalf — " +
                    "offer them a code, approve a code they gave you, or manage what's active.",
                fontSize = 13.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            // ── Delegate vs Steward explainer (CC 0.5.1) ─────────────────────
            // Two DIFFERENT relationships the user must not conflate:
            //  • Delegate → TO an agent or trusted person (a duty/agency) — THIS page.
            //  • Steward  → OF a node / community / child (accountable responsibility)
            //    — managed under Nodes, not here.
            Spacer(Modifier.height(12.dp))
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = MaterialTheme.colorScheme.surfaceVariant,
                modifier = Modifier.fillMaxWidth().testable("delegations_relationship_explainer"),
            ) {
                Column(modifier = Modifier.fillMaxWidth().padding(12.dp)) {
                    Text(
                        "Two different relationships",
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    Spacer(Modifier.height(8.dp))
                    RelationshipRow(
                        icon = CIRISIcons.robot,
                        title = "Delegate → to an agent or person",
                        body = "You hand a duty / agency TO someone (an agent or a trusted person) " +
                            "so they can act for you. That's what this page does.",
                    )
                    Spacer(Modifier.height(8.dp))
                    RelationshipRow(
                        icon = CIRISIcons.nodeBox,
                        title = "Steward → of a node, community, or child",
                        body = "You are the accountable, responsible party FOR a node / community / " +
                            "child — never an owner OF one. Manage those under Nodes, not here.",
                    )
                }
            }

            // ── Messages (always visible across panes) ───────────────────────
            notice?.let { msg ->
                Spacer(Modifier.height(8.dp))
                Surface(
                    shape = RoundedCornerShape(10.dp),
                    color = MaterialTheme.colorScheme.secondaryContainer,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(
                        msg,
                        fontSize = 12.sp,
                        color = MaterialTheme.colorScheme.onSecondaryContainer,
                        modifier = Modifier.padding(10.dp).testable("delegations_notice"),
                    )
                }
            }
            error?.let { msg ->
                Spacer(Modifier.height(8.dp))
                Surface(
                    shape = RoundedCornerShape(10.dp),
                    color = MaterialTheme.colorScheme.errorContainer,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(
                        msg,
                        fontSize = 12.sp,
                        color = MaterialTheme.colorScheme.onErrorContainer,
                        modifier = Modifier.padding(10.dp).testable("delegations_error"),
                    )
                }
            }

            // ── 3-pane selector: Offer (out) · Approve (in) · Manage (CRUD) ──
            Spacer(Modifier.height(14.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                PaneTab("Offer a code", pane == "offer", "btn_delegation_pane_offer") { pane = "offer" }
                PaneTab("Approve a code", pane == "incoming", "btn_delegation_pane_incoming") { pane = "incoming" }
                PaneTab("Manage", pane == "manage", "btn_delegation_pane_manage") { pane = "manage" }
            }

            Spacer(Modifier.height(16.dp))
            when (pane) {
                "offer" -> OfferPane(
                    busy = busy,
                    nodeBaseUrl = viewModel.nodeBaseUrl,
                    delegateLabel = delegateLabel,
                    onLabelChange = { delegateLabel = it },
                    delegateMode = delegateMode,
                    onModeChange = { delegateMode = it },
                    existingKeyId = existingKeyId,
                    onExistingKeyIdChange = { existingKeyId = it },
                    onOpenContacts = onOpenContacts,
                    goal = delegationGoal,
                    onGoalChange = { delegationGoal = it },
                    restrictActions = restrictActions,
                    onRestrictActionsChange = { restrictActions = it },
                    allowVerbs = allowVerbs,
                    onToggleAllow = { verb ->
                        allowVerbs = if (verb in allowVerbs) allowVerbs - verb else allowVerbs + verb
                    },
                    denyVerbs = denyVerbs,
                    onToggleDeny = { verb ->
                        denyVerbs = if (verb in denyVerbs) denyVerbs - verb else denyVerbs + verb
                    },
                    lastCreated = lastCreated,
                    lastConstraints = lastConstraints,
                    onCreate = {
                        val constraints = ai.ciris.mobile.shared.models.federation.DelegationConstraints(
                            actionsAllow = if (restrictActions) allowVerbs.toList() else null,
                            actionsDeny = denyVerbs.toList(),
                            goal = delegationGoal.trim().ifBlank { null },
                        )
                        lastConstraints = constraints.takeIf { !it.isUnconstrained() }
                        viewModel.createDelegation(delegateLabel, delegateMode, existingKeyId, constraints)
                    },
                    onClearCreated = {
                        viewModel.clearLastCreated()
                        delegateLabel = ""
                        existingKeyId = ""
                        delegationGoal = ""
                        restrictActions = false
                        allowVerbs = emptySet()
                        denyVerbs = emptySet()
                        lastConstraints = null
                    },
                )
                "incoming" -> IncomingPane(
                    busy = busy,
                    userCode = userCode,
                    onUserCodeChange = { userCode = it },
                    goal = approveGoal,
                    onGoalChange = { approveGoal = it },
                    restrictActions = approveRestrict,
                    onRestrictActionsChange = { approveRestrict = it },
                    allowVerbs = approveAllow,
                    onToggleAllow = { verb ->
                        approveAllow = if (verb in approveAllow) approveAllow - verb else approveAllow + verb
                    },
                    denyVerbs = approveDeny,
                    onToggleDeny = { verb ->
                        approveDeny = if (verb in approveDeny) approveDeny - verb else approveDeny + verb
                    },
                    onApprove = {
                        val constraints = ai.ciris.mobile.shared.models.federation.DelegationConstraints(
                            actionsAllow = if (approveRestrict) approveAllow.toList() else null,
                            actionsDeny = approveDeny.toList(),
                            goal = approveGoal.trim().ifBlank { null },
                        )
                        viewModel.approve(userCode, constraints.takeIf { !it.isUnconstrained() })
                        userCode = ""
                        approveGoal = ""
                        approveRestrict = false
                        approveAllow = emptySet()
                        approveDeny = emptySet()
                    },
                )
                else -> ManagePane(
                    loading = loading,
                    busy = busy,
                    delegations = delegations,
                    onRevoke = { viewModel.revoke(it) },
                )
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}

/** One row of the Delegate-vs-Steward explainer: glyph + bold title + body. */
@Composable
private fun RelationshipRow(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    title: String,
    body: String,
) {
    Row(verticalAlignment = Alignment.Top) {
        Icon(
            icon,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.primary,
            modifier = Modifier.size(20.dp),
        )
        Spacer(Modifier.width(10.dp))
        Column {
            Text(title, fontSize = 13.sp, fontWeight = FontWeight.Bold)
            Text(
                body,
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/** One segmented selector button. Selected = filled-tonal, unselected = outlined. */
@Composable
private fun RowScope.PaneTab(
    label: String,
    selected: Boolean,
    testTag: String,
    onClick: () -> Unit,
) {
    if (selected) {
        FilledTonalButton(
            onClick = onClick,
            modifier = Modifier.weight(1f).testableClickable(testTag) { onClick() },
        ) {
            Text(label, fontSize = 12.sp, fontWeight = FontWeight.Bold)
        }
    } else {
        OutlinedButton(
            onClick = onClick,
            modifier = Modifier.weight(1f).testableClickable(testTag) { onClick() },
        ) {
            Text(label, fontSize = 12.sp)
        }
    }
}

/** OUTGOING — generate an offer code / PIN to hand to an agent or person. */
@Composable
private fun OfferPane(
    busy: Boolean,
    nodeBaseUrl: String,
    delegateLabel: String,
    onLabelChange: (String) -> Unit,
    delegateMode: String,
    onModeChange: (String) -> Unit,
    existingKeyId: String,
    onExistingKeyIdChange: (String) -> Unit,
    onOpenContacts: (() -> Unit)?,
    goal: String,
    onGoalChange: (String) -> Unit,
    restrictActions: Boolean,
    onRestrictActionsChange: (Boolean) -> Unit,
    allowVerbs: Set<String>,
    onToggleAllow: (String) -> Unit,
    denyVerbs: Set<String>,
    onToggleDeny: (String) -> Unit,
    lastCreated: ai.ciris.mobile.shared.models.federation.CreateDelegationResponse?,
    lastConstraints: ai.ciris.mobile.shared.models.federation.DelegationConstraints?,
    onCreate: () -> Unit,
    onClearCreated: () -> Unit,
) {
    Column(modifier = Modifier.fillMaxWidth()) {
        Text(
            "Generate an offer code",
            fontSize = 15.sp,
            fontWeight = FontWeight.Bold,
        )
        Spacer(Modifier.height(4.dp))
        Text(
            "Authorize an agent or person to act on your behalf. You'll get a claim URL + PIN to hand to them.",
            fontSize = 12.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(
            value = delegateLabel,
            onValueChange = onLabelChange,
            singleLine = true,
            enabled = !busy,
            label = { Text("Label (e.g. my-laptop-agent)") },
            modifier = Modifier.fillMaxWidth().testable("input_delegation_label"),
        )
        Spacer(Modifier.height(8.dp))
        // Mode choice — create a new fed-ID vs use an existing one.
        Row(verticalAlignment = Alignment.CenterVertically) {
            OutlinedButton(
                onClick = { onModeChange("create") },
                enabled = !busy,
                modifier = Modifier.testableClickable("btn_delegation_mode_create") { onModeChange("create") },
            ) {
                Text(
                    "New fed-ID",
                    fontWeight = if (delegateMode == "create") FontWeight.Bold else FontWeight.Normal,
                )
            }
            Spacer(Modifier.width(8.dp))
            OutlinedButton(
                onClick = { onModeChange("existing") },
                enabled = !busy,
                modifier = Modifier.testableClickable("btn_delegation_mode_existing") { onModeChange("existing") },
            ) {
                Text(
                    "Existing fed-ID",
                    fontWeight = if (delegateMode == "existing") FontWeight.Bold else FontWeight.Normal,
                )
            }
        }
        if (delegateMode == "existing") {
            Spacer(Modifier.height(8.dp))
            if (onOpenContacts != null) {
                OutlinedButton(
                    onClick = onOpenContacts,
                    enabled = !busy,
                    modifier = Modifier.fillMaxWidth().testableClickable("btn_delegation_choose_identity") { onOpenContacts() },
                ) {
                    Icon(CIRISIcons.person, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(6.dp))
                    Text(
                        if (existingKeyId.isBlank()) "Choose from Contacts"
                        else "Change identity (${existingKeyId.take(12)}…)",
                    )
                }
                Spacer(Modifier.height(6.dp))
            }
            OutlinedTextField(
                value = existingKeyId,
                onValueChange = onExistingKeyIdChange,
                singleLine = true,
                enabled = !busy,
                label = {
                    Text(if (onOpenContacts != null) "Or paste a key_id manually" else "Existing fed-ID key_id")
                },
                modifier = Modifier.fillMaxWidth().testable("input_delegation_key_id"),
            )
        }
        Spacer(Modifier.height(12.dp))
        ConstraintsEditor(
            busy = busy,
            goal = goal,
            onGoalChange = onGoalChange,
            restrictActions = restrictActions,
            onRestrictActionsChange = onRestrictActionsChange,
            allowVerbs = allowVerbs,
            onToggleAllow = onToggleAllow,
            denyVerbs = denyVerbs,
            onToggleDeny = onToggleDeny,
            testTagPrefix = "offer",
        )
        Spacer(Modifier.height(8.dp))
        Button(
            onClick = onCreate,
            // Gate on the input the active mode actually needs: an existing key is a
            // complete identity on its own (the label is a redundant echo there), so
            // requiring a typed label was needless friction. (#134.)
            enabled = !busy && when (delegateMode) {
                "existing" -> existingKeyId.isNotBlank()
                else -> delegateLabel.isNotBlank()
            },
            modifier = Modifier.fillMaxWidth().testableClickable("btn_delegation_create") { onCreate() },
        ) {
            if (busy) {
                CircularProgressIndicator(modifier = Modifier.size(14.dp), strokeWidth = 2.dp)
                Spacer(Modifier.width(8.dp))
            }
            Text("Generate offer code")
        }

        // ── Created result — the URL + PIN to hand over ──────────────────────
        lastCreated?.let { created ->
            Spacer(Modifier.height(12.dp))
            val clipboard = LocalClipboardManager.current
            val scope = rememberCoroutineScope()
            var copiedAll by remember { mutableStateOf(false) }
            // The host:port the agent dials — the claim URL the node returns is
            // relative, so we surface the node's base URL (scheme stripped).
            val host = nodeBaseUrl.substringAfter("://").trimEnd('/')
            // The ONE formatted block "Copy all" hands over (labeled + newline-
            // separated); the same text drivable by drag-select over [offer_block].
            val offerText = buildDelegationOfferText(created, host, lastConstraints)
            val onCopyAll = {
                clipboard.setText(AnnotatedString(offerText))
                copiedAll = true
                scope.launch {
                    delay(1500)
                    copiedAll = false
                }
            }
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = MaterialTheme.colorScheme.primaryContainer,
                modifier = Modifier.fillMaxWidth().testable("delegation_created_card"),
            ) {
                Column(modifier = Modifier.fillMaxWidth().padding(14.dp)) {
                    Text(
                        "Hand this to the agent or person",
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onPrimaryContainer,
                    )
                    Spacer(Modifier.height(8.dp))
                    // The WHOLE offer is ONE selectable region — drag-select grabs
                    // the entire block in a single gesture (no nested
                    // SelectionContainers: CopyableValue renders text + a per-field
                    // copy icon only, it does NOT wrap its own SelectionContainer).
                    // Per-field copy icons + this block-level selection coexist.
                    SelectionContainer(modifier = Modifier.testable("offer_block")) {
                        Column(modifier = Modifier.fillMaxWidth()) {
                            CopyableValue(
                                label = "Host",
                                value = host,
                                valueFontSize = 13.sp,
                                testTag = "delegation_created_host",
                                copyTestTag = "btn_copy_delegation_host",
                            )
                            Spacer(Modifier.height(8.dp))
                            CopyableValue(
                                label = "PIN",
                                value = created.pin,
                                valueFontSize = 32.sp,
                                testTag = "delegation_created_pin",
                                copyTestTag = "btn_copy_delegation_pin",
                            )
                            Spacer(Modifier.height(8.dp))
                            CopyableValue(
                                label = "Claim URL",
                                value = created.claimUrl,
                                valueFontSize = 13.sp,
                                testTag = "delegation_created_url",
                                copyTestTag = "btn_copy_delegation_url",
                            )
                            Spacer(Modifier.height(8.dp))
                            CopyableValue(
                                label = "Client",
                                value = created.clientId,
                                valueFontSize = 12.sp,
                                testTag = "delegation_created_client_id",
                                copyTestTag = "btn_copy_delegation_client_id",
                            )
                            Spacer(Modifier.height(6.dp))
                            Text(
                                "Hand this URL + PIN over; it expires in ${created.expiresIn / 60} minutes.",
                                fontSize = 12.sp,
                                color = MaterialTheme.colorScheme.onPrimaryContainer,
                            )
                            // What this delegation permits — driven by the node-echoed
                            // characteristics when present, else the constraints just set.
                            GrantCharacteristicsDisplay(
                                characteristics = created.delegation,
                                fallback = lastConstraints,
                            )
                        }
                    }
                    Spacer(Modifier.height(10.dp))
                    // Copy the ENTIRE offer as one formatted block — saves the user
                    // copying the host + URL + PIN + client one field at a time.
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        FilledTonalButton(
                            onClick = { onCopyAll() },
                            modifier = Modifier.testableClickable("btn_offer_copy_all") { onCopyAll() },
                        ) {
                            Icon(
                                imageVector = CIRISMaterialIcons.Filled.ContentCopy,
                                contentDescription = null,
                                modifier = Modifier.size(16.dp),
                            )
                            Spacer(Modifier.width(6.dp))
                            Text(localizedString("mobile.delegations_copy_all"))
                        }
                        if (copiedAll) {
                            Spacer(Modifier.width(8.dp))
                            Text(
                                localizedString("mobile.delegations_copy_all_done"),
                                fontSize = 11.sp,
                                color = MaterialTheme.colorScheme.onPrimaryContainer,
                                modifier = Modifier.testable("offer_copy_all_copied"),
                            )
                        }
                    }
                    Spacer(Modifier.height(10.dp))
                    Button(
                        onClick = onClearCreated,
                        modifier = Modifier.testableClickable("btn_delegation_created_done") { onClearCreated() },
                    ) {
                        Text("Done")
                    }
                }
            }
        }
    }
}

/**
 * A labeled value the user must hand over — one-tap copyable with a brief "Copied"
 * confirmation. Tinted for the primaryContainer card it sits in (the created-offer
 * surface). The value Text is NOT wrapped in its own [SelectionContainer]: the
 * caller wraps the whole offer block in ONE SelectionContainer (drag-select the
 * entire offer), and nested SelectionContainers are illegal in Compose.
 */
@Composable
private fun CopyableValue(
    label: String,
    value: String,
    valueFontSize: TextUnit,
    testTag: String,
    copyTestTag: String,
) {
    val clipboard = LocalClipboardManager.current
    val scope = rememberCoroutineScope()
    var copied by remember { mutableStateOf(false) }
    val onCopy = {
        clipboard.setText(AnnotatedString(value))
        copied = true
        scope.launch {
            delay(1500)
            copied = false
        }
    }
    Text(label, fontSize = 11.sp, color = MaterialTheme.colorScheme.onPrimaryContainer)
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(
            value,
            fontSize = valueFontSize,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onPrimaryContainer,
            modifier = Modifier.weight(1f).testable(testTag),
        )
        IconButton(
            onClick = { onCopy() },
            modifier = Modifier.testableClickable(copyTestTag) { onCopy() },
        ) {
            Icon(
                imageVector = CIRISMaterialIcons.Filled.ContentCopy,
                contentDescription = "Copy $label",
                tint = MaterialTheme.colorScheme.onPrimaryContainer,
                modifier = Modifier.size(18.dp),
            )
        }
    }
    if (copied) {
        Text(
            "Copied",
            fontSize = 11.sp,
            color = MaterialTheme.colorScheme.onPrimaryContainer,
            modifier = Modifier.testable("${testTag}_copied"),
        )
    }
}

/**
 * Format the whole delegation offer as ONE labeled, newline-separated block — the
 * payload the "Copy all" button puts on the clipboard. [host] is host:port (scheme
 * already stripped). The permits (goal / allowed / denied / expiry) mirror
 * [GrantCharacteristicsDisplay]: the node-echoed characteristics when present, else
 * the [fallback] constraints the owner just submitted.
 */
private fun buildDelegationOfferText(
    created: ai.ciris.mobile.shared.models.federation.CreateDelegationResponse,
    host: String,
    fallback: ai.ciris.mobile.shared.models.federation.DelegationConstraints?,
): String {
    val catalog = ai.ciris.mobile.shared.models.federation.CapabilityCatalog
    val ch = created.delegation
    val goal = ch?.purpose ?: fallback?.goal
    val allow = ch?.actionsAllow ?: fallback?.actionsAllow
    val deny = (ch?.actionsDeny?.takeIf { it.isNotEmpty() })
        ?: fallback?.actionsDeny?.takeIf { it.isNotEmpty() }
    val expiresIn = ch?.expiresIn ?: created.expiresIn.takeIf { it > 0 }
    return buildString {
        appendLine("CIRIS delegation offer")
        appendLine("Host:      $host")
        appendLine("Claim URL: ${created.claimUrl}")
        appendLine("PIN:       ${created.pin}")
        append("Client:    ${created.clientId}")
        if (!goal.isNullOrBlank()) append("\nGoal:      $goal")
        val allowedText = when {
            allow == null -> "all actions"
            allow.isEmpty() -> "read-only (no actions)"
            else -> allow.joinToString(", ") { catalog.labelFor(it) }
        }
        append("\nAllowed:   $allowedText")
        if (!deny.isNullOrEmpty()) {
            append("\nDenied:    ${deny.joinToString(", ") { catalog.labelFor(it) }}")
        }
        if (expiresIn != null && expiresIn > 0) append("\nExpires:   ${expiresIn / 60} min")
    }
}

/**
 * Collapsible **Constraints** editor — lets the owner NARROW a delegation grant:
 * a free-text goal, an optional allow-list (multi-select verb chips; empty =
 * read-only), and an optional deny-list (always wins). Everything unset = an
 * unconstrained, full-authority grant. Shared by the Offer (issue) and Approve
 * (tighten-only) flows via [testTagPrefix].
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ConstraintsEditor(
    busy: Boolean,
    goal: String,
    onGoalChange: (String) -> Unit,
    restrictActions: Boolean,
    onRestrictActionsChange: (Boolean) -> Unit,
    allowVerbs: Set<String>,
    onToggleAllow: (String) -> Unit,
    denyVerbs: Set<String>,
    onToggleDeny: (String) -> Unit,
    testTagPrefix: String,
) {
    var expanded by remember { mutableStateOf(false) }
    val catalog = ai.ciris.mobile.shared.models.federation.CapabilityCatalog
    val anySet = restrictActions || denyVerbs.isNotEmpty() || goal.isNotBlank()
    Surface(
        shape = RoundedCornerShape(12.dp),
        color = MaterialTheme.colorScheme.surfaceVariant,
        modifier = Modifier.fillMaxWidth().testable("${testTagPrefix}_constraints_section"),
    ) {
        Column(modifier = Modifier.fillMaxWidth().padding(12.dp)) {
            // Header — tap to expand/collapse.
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .fillMaxWidth()
                    .testableClickable("btn_${testTagPrefix}_constraints_toggle") { expanded = !expanded },
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        localizedString("mobile.delegations_constraints_title"),
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        localizedString(
                            if (anySet) "mobile.delegations_constraints_set"
                            else "mobile.delegations_constraints_unset",
                        ),
                        fontSize = 11.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Text(if (expanded) "▾" else "▸", fontSize = 16.sp)
            }

            if (expanded) {
                Spacer(Modifier.height(8.dp))
                Text(
                    localizedString("mobile.delegations_constraints_desc"),
                    fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(
                    value = goal,
                    onValueChange = onGoalChange,
                    enabled = !busy,
                    label = { Text(localizedString("mobile.delegations_goal_label")) },
                    modifier = Modifier.fillMaxWidth().testable("input_${testTagPrefix}_goal"),
                )
                Spacer(Modifier.height(12.dp))

                // Allow-list toggle + chips.
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            localizedString("mobile.delegations_restrict_actions"),
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Bold,
                        )
                        Text(
                            localizedString("mobile.delegations_restrict_actions_desc"),
                            fontSize = 11.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    Switch(
                        checked = restrictActions,
                        onCheckedChange = onRestrictActionsChange,
                        enabled = !busy,
                        modifier = Modifier.testableClickable("switch_${testTagPrefix}_restrict") {
                            onRestrictActionsChange(!restrictActions)
                        },
                    )
                }
                if (restrictActions) {
                    Spacer(Modifier.height(8.dp))
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        catalog.selectable.forEach { v ->
                            FilterChip(
                                selected = v.verb in allowVerbs,
                                onClick = { onToggleAllow(v.verb) },
                                enabled = !busy,
                                label = { Text(v.label, fontSize = 12.sp) },
                                modifier = Modifier.testableClickable(
                                    "chip_${testTagPrefix}_allow_${v.verb}",
                                ) { onToggleAllow(v.verb) },
                            )
                        }
                    }
                    if (allowVerbs.isEmpty()) {
                        Spacer(Modifier.height(4.dp))
                        Text(
                            localizedString("mobile.delegations_read_only_hint"),
                            fontSize = 11.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }

                // Deny-list chips (always override allow).
                Spacer(Modifier.height(12.dp))
                Text(
                    localizedString("mobile.delegations_deny_label"),
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Bold,
                )
                Spacer(Modifier.height(6.dp))
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    catalog.selectable.forEach { v ->
                        FilterChip(
                            selected = v.verb in denyVerbs,
                            onClick = { onToggleDeny(v.verb) },
                            enabled = !busy,
                            label = { Text(v.label, fontSize = 12.sp) },
                            modifier = Modifier.testableClickable(
                                "chip_${testTagPrefix}_deny_${v.verb}",
                            ) { onToggleDeny(v.verb) },
                        )
                    }
                }

                Spacer(Modifier.height(10.dp))
                Text(
                    localizedString("mobile.delegations_never_delegated"),
                    fontSize = 11.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.testable("${testTagPrefix}_never_delegated_note"),
                )
            }
        }
    }
}

/**
 * **What this delegation permits** — a read-only transparency block driven by the
 * node-echoed [characteristics] (the `delegation` object / `x-ciris-delegation`
 * header), falling back to the [fallback] constraints the owner just submitted
 * when the node doesn't echo them. Sits inside the primaryContainer created-card.
 */
@Composable
private fun GrantCharacteristicsDisplay(
    characteristics: ai.ciris.mobile.shared.models.federation.GrantCharacteristics?,
    fallback: ai.ciris.mobile.shared.models.federation.DelegationConstraints?,
) {
    val catalog = ai.ciris.mobile.shared.models.federation.CapabilityCatalog
    val goal = characteristics?.purpose ?: fallback?.goal
    val allow = characteristics?.actionsAllow ?: fallback?.actionsAllow
    val deny = (characteristics?.actionsDeny?.takeIf { it.isNotEmpty() })
        ?: fallback?.actionsDeny?.takeIf { it.isNotEmpty() }
    val expiresIn = characteristics?.expiresIn

    Spacer(Modifier.height(10.dp))
    Text(
        localizedString("mobile.delegations_permits_title"),
        fontSize = 12.sp,
        fontWeight = FontWeight.Bold,
        color = MaterialTheme.colorScheme.onPrimaryContainer,
        modifier = Modifier.testable("delegation_permits_title"),
    )
    Spacer(Modifier.height(4.dp))
    if (!goal.isNullOrBlank()) {
        PermitRow(localizedString("mobile.delegations_permits_goal"), goal)
    }
    val allowedText = when {
        allow == null -> localizedString("mobile.delegations_permits_all_actions")
        allow.isEmpty() -> localizedString("mobile.delegations_permits_read_only")
        else -> allow.joinToString(", ") { catalog.labelFor(it) }
    }
    PermitRow(localizedString("mobile.delegations_permits_allowed"), allowedText)
    if (!deny.isNullOrEmpty()) {
        PermitRow(
            localizedString("mobile.delegations_permits_denied"),
            deny.joinToString(", ") { catalog.labelFor(it) },
        )
    }
    if (expiresIn != null && expiresIn > 0) {
        PermitRow(localizedString("mobile.delegations_permits_expiry"), "${expiresIn / 60} min")
    }
    // The actor is copyable when the node echoes real characteristics.
    characteristics?.actor?.takeIf { it.isNotBlank() }?.let { actor ->
        Spacer(Modifier.height(6.dp))
        CopyableValue(
            label = localizedString("mobile.delegations_permits_actor"),
            value = actor,
            valueFontSize = 12.sp,
            testTag = "delegation_permits_actor",
            copyTestTag = "btn_copy_delegation_actor",
        )
    }
}

/** One label:value row tinted for the primaryContainer created-card. */
@Composable
private fun PermitRow(label: String, value: String) {
    Row(modifier = Modifier.fillMaxWidth().padding(vertical = 1.dp)) {
        Text(
            "$label: ",
            fontSize = 11.sp,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onPrimaryContainer,
        )
        Text(
            value,
            fontSize = 11.sp,
            color = MaterialTheme.colorScheme.onPrimaryContainer,
            modifier = Modifier.weight(1f),
        )
    }
}

/** INCOMING — view + approve a request code someone gave you. */
@Composable
private fun IncomingPane(
    busy: Boolean,
    userCode: String,
    onUserCodeChange: (String) -> Unit,
    goal: String,
    onGoalChange: (String) -> Unit,
    restrictActions: Boolean,
    onRestrictActionsChange: (Boolean) -> Unit,
    allowVerbs: Set<String>,
    onToggleAllow: (String) -> Unit,
    denyVerbs: Set<String>,
    onToggleDeny: (String) -> Unit,
    onApprove: () -> Unit,
) {
    Column(modifier = Modifier.fillMaxWidth()) {
        Text(
            localizedString("mobile.delegations_add_title"),
            fontSize = 15.sp,
            fontWeight = FontWeight.Bold,
        )
        Spacer(Modifier.height(4.dp))
        Text(
            localizedString("mobile.delegations_add_desc"),
            fontSize = 12.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(
            value = userCode,
            onValueChange = onUserCodeChange,
            singleLine = true,
            enabled = !busy,
            label = { Text(localizedString("mobile.delegations_code_label")) },
            modifier = Modifier.fillMaxWidth().testable("input_delegation_code"),
        )
        Spacer(Modifier.height(12.dp))
        // Approving can only NARROW the agent's requested grant (tighten-only).
        Text(
            localizedString("mobile.delegations_tighten_note"),
            fontSize = 12.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(8.dp))
        ConstraintsEditor(
            busy = busy,
            goal = goal,
            onGoalChange = onGoalChange,
            restrictActions = restrictActions,
            onRestrictActionsChange = onRestrictActionsChange,
            allowVerbs = allowVerbs,
            onToggleAllow = onToggleAllow,
            denyVerbs = denyVerbs,
            onToggleDeny = onToggleDeny,
            testTagPrefix = "approve",
        )
        Spacer(Modifier.height(8.dp))
        Button(
            onClick = onApprove,
            enabled = !busy && userCode.isNotBlank(),
            modifier = Modifier.fillMaxWidth().testableClickable("btn_delegation_approve") { onApprove() },
        ) {
            if (busy) {
                CircularProgressIndicator(modifier = Modifier.size(14.dp), strokeWidth = 2.dp)
                Spacer(Modifier.width(8.dp))
            }
            Text(localizedString("mobile.delegations_approve"))
        }
    }
}

/** MANAGE — the active delegations (CRUD: list + revoke). */
@Composable
private fun ManagePane(
    loading: Boolean,
    busy: Boolean,
    delegations: List<ai.ciris.mobile.shared.models.federation.DelegationDto>,
    onRevoke: (String) -> Unit,
) {
    Column(modifier = Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                localizedString("mobile.delegations_active_title"),
                fontSize = 15.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.weight(1f),
            )
            if (loading) {
                CircularProgressIndicator(modifier = Modifier.size(14.dp), strokeWidth = 2.dp)
            }
        }
        Spacer(Modifier.height(8.dp))

        if (delegations.isEmpty() && !loading) {
            Text(
                localizedString("mobile.delegations_empty"),
                fontSize = 13.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        } else {
            delegations.forEach { d ->
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = MaterialTheme.colorScheme.surfaceVariant,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 8.dp)
                        .testable("row_delegation_${d.clientId}"),
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(d.clientId, fontSize = 14.sp, fontWeight = FontWeight.Bold)
                            Text(
                                d.scope,
                                fontSize = 12.sp,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        OutlinedButton(
                            onClick = { onRevoke(d.clientId) },
                            enabled = !busy,
                            modifier = Modifier.testableClickable("btn_revoke_${d.clientId}") { onRevoke(d.clientId) },
                        ) {
                            Text(localizedString("mobile.delegations_revoke"))
                        }
                    }
                }
            }
        }
    }
}
