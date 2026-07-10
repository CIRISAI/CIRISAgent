package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.NodeProfile
import ai.ciris.mobile.shared.platform.DirectoryPickerDialog
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.nav.LocalIsCompactWindow
import ai.ciris.mobile.shared.ui.screens.graph.NodeGraphView
import ai.ciris.mobile.shared.viewmodels.BootstrapPhase
import ai.ciris.mobile.shared.viewmodels.ConsentObjectsState
import ai.ciris.mobile.shared.viewmodels.ConsentObjectsViewModel
import ai.ciris.mobile.shared.viewmodels.DelegationsViewModel
import ai.ciris.mobile.shared.viewmodels.NodeSwitcherViewModel
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.background
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
 * Manage Nodes (CRUD) — the management surface for every saved fabric node.
 *
 * In fabric terms there is no "server list" — the user participates in several
 * **nodes** (their local node, node A, node B, …). This screen is the CRUD over
 * the LIVE [NodeProfile]s held in memory by [NodeSwitcherViewModel] (read from the
 * local node's owned-nodes projection each session; not persisted — CIRISServer#125):
 *
 *  - **list** every node (name, URL, key_id, pinned status, active marker)
 *  - **add** a node by NodeCode (identity-pinned via
 *    [NodeSwitcherViewModel.connectByNodeCode]) or by raw URL
 *    ([NodeSwitcherViewModel.saveProfile])
 *  - **edit** — rename ([NodeSwitcherViewModel.renameProfile]) / retoken
 *    ([NodeSwitcherViewModel.retokenProfile])
 *  - **remove** ([NodeSwitcherViewModel.removeProfile])
 *  - **set-active / switch** ([NodeSwitcherViewModel.switchTo])
 *  - **claim ownership** → routes to [ClaimNodeScreen] via [onClaimNode]
 *
 * The app performs NO crypto here: adding by NodeCode only decodes + identity-pins
 * locally and persists the profile; the actual owner-binding claim is the local
 * node's job, reached through [onClaimNode].
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ManageNodesScreen(
    viewModel: NodeSwitcherViewModel,
    onBack: () -> Unit,
    /** Navigate to the claim-ownership flow (ClaimNodeScreen). */
    onClaimNode: () -> Unit,
    /** Navigate to the guided "Add Federation ID" catch-up flow (AddFederationIdScreen).
     *  Only surfaced when the logged-in owner has NO fed-ID. */
    onAddFederationId: () -> Unit = {},
    /** Delegations (owner → agent edges) — drives the graph's delegation/agent vertices. */
    delegationsViewModel: DelegationsViewModel? = null,
    /** consent:replication peering (node ↔ node) — drives the graph's consent edges. */
    consentObjectsViewModel: ConsentObjectsViewModel? = null,
    /** Shared API client — powers the live neural background behind the graph. */
    apiClient: CIRISApiClient? = null,
) {
    // graph ⇄ list toggle — defaults to GRAPH (the headline node-mesh view).
    var view by remember { mutableStateOf("graph") }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("mobile.manage_nodes_title")) },
                navigationIcon = {
                    if (!LocalIsCompactWindow.current) {
                        IconButton(
                            onClick = onBack,
                            modifier = Modifier.testable("btn_manage_nodes_back"),
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
                .padding(padding),
        ) {
            // ── Graph / List segmented selector ──────────────────────────────
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                ViewTab("Graph", view == "graph", "btn_nodes_view_graph") { view = "graph" }
                ViewTab("List", view == "list", "btn_nodes_view_list") { view = "list" }
            }

            if (view == "graph") {
                val profiles by viewModel.profiles.collectAsState()
                val activeId by viewModel.activeProfileId.collectAsState()
                val delegations = if (delegationsViewModel != null) {
                    delegationsViewModel.delegations.collectAsState().value
                } else {
                    emptyList()
                }
                val consent = if (consentObjectsViewModel != null) {
                    consentObjectsViewModel.state.collectAsState().value
                } else {
                    ConsentObjectsState()
                }
                NodeGraphView(
                    profiles = profiles,
                    activeProfileId = activeId,
                    delegations = delegations,
                    consent = consent,
                    apiClient = apiClient,
                    onSwitchNode = { viewModel.switchTo(it) },
                    onRemoveNode = { viewModel.removeProfile(it.id) },
                    modifier = Modifier
                        .weight(1f)
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp)
                        .padding(bottom = 16.dp),
                )
            } else {
                NodesListView(
                    viewModel = viewModel,
                    onClaimNode = onClaimNode,
                    onAddFederationId = onAddFederationId,
                    modifier = Modifier.weight(1f),
                )
            }
        }
    }
}

/** One segmented selector button. Selected = filled-tonal, unselected = outlined. */
@Composable
private fun RowScope.ViewTab(
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

/**
 * The LIST half of the toggle — the original Manage Nodes CRUD surface, intact.
 */
@Composable
private fun NodesListView(
    viewModel: NodeSwitcherViewModel,
    onClaimNode: () -> Unit,
    onAddFederationId: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val profiles by viewModel.profiles.collectAsState()
    val activeId by viewModel.activeProfileId.collectAsState()
    val isSwitching by viewModel.isSwitching.collectAsState()
    val error by viewModel.error.collectAsState()
    val notice by viewModel.notice.collectAsState()
    val bootstrap by viewModel.bootstrap.collectAsState()

    // USB node-list save/restore folder pickers (private/offline sneakernet).
    var showSaveUsbPicker by remember { mutableStateOf(false) }
    var showRestoreUsbPicker by remember { mutableStateOf(false) }

    // Add-by-* panel state.
    var showAddByCode by remember { mutableStateOf(false) }
    var showAddByUrl by remember { mutableStateOf(false) }
    var codeInput by remember { mutableStateOf("") }
    var codeUrlOverride by remember { mutableStateOf("") }
    var urlName by remember { mutableStateOf("") }
    var urlInput by remember { mutableStateOf("") }

    // Per-row edit state — id of the profile currently being edited (rename).
    var editingId by remember { mutableStateOf<String?>(null) }
    var editName by remember { mutableStateOf("") }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(16.dp)
            .verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            text = localizedString("mobile.manage_nodes_subtitle"),
            fontSize = 13.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        error?.let { msg ->
                Surface(
                    color = MaterialTheme.colorScheme.errorContainer,
                    shape = RoundedCornerShape(6.dp),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Row(
                        modifier = Modifier.padding(10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            text = msg,
                            fontSize = 12.sp,
                            color = MaterialTheme.colorScheme.onErrorContainer,
                            modifier = Modifier.weight(1f),
                        )
                        TextButton(onClick = { viewModel.clearError() }) {
                            Text(localizedString("mobile.common_close"))
                        }
                    }
                }
            }

        notice?.let { msg ->
            Surface(
                color = MaterialTheme.colorScheme.tertiaryContainer,
                shape = RoundedCornerShape(6.dp),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Row(
                    modifier = Modifier.padding(10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        text = msg,
                        fontSize = 12.sp,
                        color = MaterialTheme.colorScheme.onTertiaryContainer,
                        modifier = Modifier.weight(1f),
                    )
                    TextButton(onClick = { viewModel.clearNotice() }) {
                        Text(localizedString("mobile.common_close"))
                    }
                }
            }
        }

            // ── Node list ────────────────────────────────────────────────────
            if (profiles.isEmpty()) {
                Text(
                    text = localizedString("mobile.manage_nodes_empty"),
                    fontSize = 13.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            } else {
                profiles.forEach { profile ->
                    NodeRow(
                        profile = profile,
                        isActive = profile.id == activeId,
                        isSwitching = isSwitching,
                        isEditing = editingId == profile.id,
                        editName = editName,
                        onEditNameChange = { editName = it },
                        onStartEdit = {
                            editingId = profile.id
                            editName = profile.name
                        },
                        onCancelEdit = { editingId = null },
                        onSaveEdit = {
                            viewModel.renameProfile(profile.id, editName)
                            editingId = null
                        },
                        onSwitch = { viewModel.switchTo(profile) },
                        onRemove = { viewModel.removeProfile(profile.id) },
                    )
                }
            }

            Spacer(Modifier.height(4.dp))

            // ── Add actions ──────────────────────────────────────────────────
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(
                    onClick = {
                        showAddByCode = !showAddByCode
                        showAddByUrl = false
                        viewModel.clearBootstrap()
                    },
                    modifier = Modifier.testable("btn_add_node_by_code"),
                ) {
                    Icon(CIRISIcons.add, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(6.dp))
                    Text(localizedString("mobile.manage_nodes_add_by_code"))
                }
                OutlinedButton(
                    onClick = {
                        showAddByUrl = !showAddByUrl
                        showAddByCode = false
                    },
                    modifier = Modifier.testable("btn_add_node_by_url"),
                ) {
                    Text(localizedString("mobile.manage_nodes_add_by_url"))
                }
            }

            if (showAddByCode) {
                Surface(
                    color = MaterialTheme.colorScheme.surfaceVariant,
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(
                            localizedString("mobile.manage_nodes_add_by_code"),
                            fontWeight = FontWeight.SemiBold,
                            fontSize = 13.sp,
                        )
                        OutlinedTextField(
                            value = codeInput,
                            onValueChange = { codeInput = it },
                            label = { Text(localizedString("mobile.manage_nodes_node_code")) },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth().testable("field_add_node_code"),
                        )
                        // Shown when the code carries no transport hint.
                        if (bootstrap.phase == BootstrapPhase.NEED_URL) {
                            OutlinedTextField(
                                value = codeUrlOverride,
                                onValueChange = { codeUrlOverride = it },
                                label = { Text(localizedString("mobile.manage_nodes_node_url")) },
                                singleLine = true,
                                modifier = Modifier.fillMaxWidth().testable("field_add_node_code_url"),
                            )
                        }
                        bootstrap.error?.let {
                            Text(it, color = MaterialTheme.colorScheme.error, fontSize = 12.sp)
                        }
                        bootstrap.pinnedProfile?.let { pinned ->
                            Text(
                                localizedString("mobile.manage_nodes_pinned_ok") + " ${pinned.name}",
                                color = MaterialTheme.colorScheme.primary,
                                fontSize = 12.sp,
                            )
                        }
                        Button(
                            onClick = {
                                viewModel.connectByNodeCode(
                                    code = codeInput.trim(),
                                    overrideUrl = codeUrlOverride.trim().takeIf { it.isNotBlank() },
                                )
                            },
                            enabled = codeInput.isNotBlank() && !bootstrap.inProgress,
                            modifier = Modifier.testable("btn_add_node_code_connect"),
                        ) {
                            if (bootstrap.inProgress) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(16.dp),
                                    strokeWidth = 2.dp,
                                )
                            } else {
                                Text(localizedString("mobile.manage_nodes_connect_pin"))
                            }
                        }
                    }
                }
            }

            if (showAddByUrl) {
                Surface(
                    color = MaterialTheme.colorScheme.surfaceVariant,
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(
                            localizedString("mobile.manage_nodes_add_by_url"),
                            fontWeight = FontWeight.SemiBold,
                            fontSize = 13.sp,
                        )
                        Text(
                            localizedString("mobile.manage_nodes_add_by_url_note"),
                            fontSize = 11.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        OutlinedTextField(
                            value = urlName,
                            onValueChange = { urlName = it },
                            label = { Text(localizedString("mobile.manage_nodes_name")) },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth().testable("field_add_node_name"),
                        )
                        OutlinedTextField(
                            value = urlInput,
                            onValueChange = { urlInput = it },
                            label = { Text(localizedString("mobile.manage_nodes_node_url")) },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth().testable("field_add_node_url"),
                        )
                        Button(
                            onClick = {
                                viewModel.saveProfile(name = urlName, baseUrl = urlInput)
                                urlName = ""
                                urlInput = ""
                                showAddByUrl = false
                            },
                            enabled = urlInput.isNotBlank(),
                            modifier = Modifier.testable("btn_add_node_url_save"),
                        ) {
                            Text(localizedString("mobile.manage_nodes_save"))
                        }
                    }
                }
            }

            Spacer(Modifier.height(8.dp))

            // ── Claim ownership affordance ───────────────────────────────────
            Button(
                onClick = onClaimNode,
                modifier = Modifier.fillMaxWidth().testableClickable("btn_manage_nodes_claim") { onClaimNode() },
            ) {
                Icon(CIRISIcons.keySecure, contentDescription = null, modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(8.dp))
                Text(localizedString("mobile.manage_nodes_claim"))
            }
            Text(
                text = localizedString("mobile.manage_nodes_claim_note"),
                fontSize = 11.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Spacer(Modifier.height(12.dp))

            // ── Add Federation ID (WAs-need-fed-IDs migration, catch-up flow) ─
            // For a node owned the legacy way (a password/OAuth WA with NO fed-ID):
            // route to the GUIDED AddFederationIdScreen (name → announce decision →
            // confirm) instead of a bare one-tap mint. Shown ONLY when the logged-in
            // owner has no fed-ID (ownerHasFedId == false); hidden once they have one
            // (true) or when it can't be determined (null — fail-closed).
            val ownerHasFedId by viewModel.ownerHasFedId.collectAsState()
            if (ownerHasFedId == false) {
                OutlinedButton(
                    onClick = onAddFederationId,
                    modifier = Modifier.fillMaxWidth().testableClickable("btn_add_federation_id") { onAddFederationId() },
                ) {
                    Icon(CIRISIcons.keySecure, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(8.dp))
                    Text(localizedString("mobile.manage_nodes_upgrade_fed_id"))
                }
                Text(
                    text = localizedString("mobile.manage_nodes_upgrade_fed_id_note"),
                    fontSize = 11.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )

                Spacer(Modifier.height(12.dp))
            }

            // ── Carry your nodes to another device (USB sneakernet) ──────────
            // Private/offline owners don't announce, so owned-node bindings never
            // self-replicate to their other devices. Save the node list to a USB
            // folder here and restore it on the other device — no federation
            // announce required.
            Text(
                text = localizedString("mobile.manage_nodes_usb_title"),
                fontWeight = FontWeight.SemiBold,
                fontSize = 13.sp,
            )
            Text(
                text = localizedString("mobile.manage_nodes_usb_note"),
                fontSize = 11.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(
                    onClick = { showSaveUsbPicker = true },
                    modifier = Modifier.weight(1f).testable("btn_nodes_save_usb"),
                ) {
                    Text(localizedString("mobile.manage_nodes_save_usb"))
                }
                OutlinedButton(
                    onClick = { showRestoreUsbPicker = true },
                    modifier = Modifier.weight(1f).testable("btn_nodes_restore_usb"),
                ) {
                    Text(localizedString("mobile.manage_nodes_restore_usb"))
                }
            }
        }

    DirectoryPickerDialog(
        show = showSaveUsbPicker,
        onDirectoryPicked = { dir ->
            showSaveUsbPicker = false
            if (dir.isNotBlank()) viewModel.saveNodeListToUsb(dir)
        },
        onDismiss = { showSaveUsbPicker = false },
    )
    DirectoryPickerDialog(
        show = showRestoreUsbPicker,
        onDirectoryPicked = { dir ->
            showRestoreUsbPicker = false
            if (dir.isNotBlank()) viewModel.restoreNodeListFromUsb(dir)
        },
        onDismiss = { showRestoreUsbPicker = false },
    )
}

@Composable
private fun NodeRow(
    profile: NodeProfile,
    isActive: Boolean,
    isSwitching: Boolean,
    isEditing: Boolean,
    editName: String,
    onEditNameChange: (String) -> Unit,
    onStartEdit: () -> Unit,
    onCancelEdit: () -> Unit,
    onSaveEdit: () -> Unit,
    onSwitch: () -> Unit,
    onRemove: () -> Unit,
) {
    Surface(
        color = if (isActive) MaterialTheme.colorScheme.primaryContainer
        else MaterialTheme.colorScheme.surfaceVariant,
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier.fillMaxWidth().testable("row_node_${profile.id}"),
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier
                        .size(8.dp)
                        .background(
                            color = if (isActive) MaterialTheme.colorScheme.primary
                            else MaterialTheme.colorScheme.outline,
                            shape = CircleShape,
                        ),
                )
                Spacer(Modifier.width(8.dp))
                if (isEditing) {
                    OutlinedTextField(
                        value = editName,
                        onValueChange = onEditNameChange,
                        singleLine = true,
                        modifier = Modifier.weight(1f).testable("field_edit_node_name"),
                    )
                } else {
                    Text(
                        text = profile.name + if (isActive) "  (" + localizedString("mobile.manage_nodes_active") + ")" else "",
                        fontWeight = FontWeight.SemiBold,
                        fontSize = 14.sp,
                        modifier = Modifier.weight(1f),
                    )
                }
            }

            Text(profile.baseUrl, fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)

            // key_id + pinned/auth status line.
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                profile.pinnedKeyId?.let {
                    Text(
                        text = "key_id: ${it.take(20)}…",
                        fontSize = 10.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                StatusChip(
                    label = if (profile.isPinned) localizedString("mobile.manage_nodes_pinned")
                    else localizedString("mobile.manage_nodes_unpinned"),
                    on = profile.isPinned,
                )
                StatusChip(
                    label = if (profile.isAuthenticated) localizedString("mobile.manage_nodes_authed")
                    else localizedString("mobile.manage_nodes_no_session"),
                    on = profile.isAuthenticated,
                )
            }

            // Action row.
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (isEditing) {
                    Button(onClick = onSaveEdit, modifier = Modifier.testable("btn_node_save_${profile.id}")) {
                        Text(localizedString("mobile.manage_nodes_save"))
                    }
                    OutlinedButton(onClick = onCancelEdit) {
                        Text(localizedString("mobile.common_cancel"))
                    }
                } else {
                    if (!isActive) {
                        OutlinedButton(
                            onClick = onSwitch,
                            enabled = !isSwitching,
                            modifier = Modifier.testable("btn_node_switch_${profile.id}"),
                        ) {
                            Text(localizedString("mobile.manage_nodes_set_active"))
                        }
                    }
                    OutlinedButton(
                        onClick = onStartEdit,
                        modifier = Modifier.testable("btn_node_edit_${profile.id}"),
                    ) {
                        Icon(CIRISIcons.edit, contentDescription = null, modifier = Modifier.size(14.dp))
                        Spacer(Modifier.width(4.dp))
                        Text(localizedString("mobile.manage_nodes_rename"))
                    }
                    OutlinedButton(
                        onClick = onRemove,
                        modifier = Modifier.testable("btn_node_remove_${profile.id}"),
                    ) {
                        Icon(CIRISIcons.delete, contentDescription = null, modifier = Modifier.size(14.dp))
                        Spacer(Modifier.width(4.dp))
                        Text(localizedString("mobile.manage_nodes_remove"))
                    }
                }
            }
        }
    }
}

@Composable
private fun StatusChip(label: String, on: Boolean) {
    Surface(
        color = if (on) MaterialTheme.colorScheme.tertiaryContainer
        else MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(4.dp),
    ) {
        Text(
            text = label,
            fontSize = 10.sp,
            color = if (on) MaterialTheme.colorScheme.onTertiaryContainer
            else MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
        )
    }
}
