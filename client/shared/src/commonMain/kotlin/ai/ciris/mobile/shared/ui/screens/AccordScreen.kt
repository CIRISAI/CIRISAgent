package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.federation.AccordEventDto
import ai.ciris.mobile.shared.models.federation.AccordFamilyDto
import ai.ciris.mobile.shared.models.federation.AccordHolderDto
import ai.ciris.mobile.shared.models.federation.AccordInvocationDto
import ai.ciris.mobile.shared.models.federation.CanonicalServerDto
import ai.ciris.mobile.shared.models.federation.CanonicalWithdrawalDto
import ai.ciris.mobile.shared.models.federation.PendingCoscrubDto
import ai.ciris.mobile.shared.platform.DirectoryPickerDialog
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.platform.writeTextFile
import ai.ciris.mobile.shared.ui.components.AttKind
import ai.ciris.mobile.shared.ui.components.AttOp
import ai.ciris.mobile.shared.ui.components.AttStatus
import ai.ciris.mobile.shared.ui.components.Attestation
import ai.ciris.mobile.shared.ui.components.AttestationCard
import ai.ciris.mobile.shared.ui.components.CanonicalCosignSheet
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.components.ConfirmDestructive
import ai.ciris.mobile.shared.ui.components.CosignSheet
import ai.ciris.mobile.shared.ui.components.HardwareScrubSheet
import ai.ciris.mobile.shared.ui.components.NewAttestationAction
import ai.ciris.mobile.shared.ui.components.NewAttestationMenu
import ai.ciris.mobile.shared.ui.components.ViewerAuthority
import ai.ciris.mobile.shared.viewmodels.AccordViewModel
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
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
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
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
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch

/**
 * **Trust Root** — the HUMANITY_ACCORD constitutional surface (CIRISServer #41),
 * recomposed as the canonical CEG-native mesh interface: every object is an
 * attestation, so every object renders as one [AttestationCard] with one uniform
 * op menu. The eight hand-rolled sections of the old screen collapse into four —
 * **The accord · Canonical servers · Pending co-signs · History** — a single
 * `[+ New]` affordance, and three shared sign/confirm sub-flows.
 *
 * This is a PURE client re-composition: no server change. Each op maps to an
 * existing `AccordViewModel` method — Cosign→`concur`, Supersede (replace)→
 * `selectCanonicalForReplace`+`addCanonicalServer`, Withdraw→`withdrawCanonical`,
 * the mint sheet→`admitNode`/`addCanonicalServer`, Drill→`initiateDrill`,
 * Announce→`initiateAnnounce`. The app holds no keys; the YubiKey touch is consent.
 */

/** Which shared sub-flow is open, if any. */
private sealed interface AccordSheet {
    data object AdmitNode : AccordSheet
    data class AddCanonical(val replace: CanonicalServerDto?) : AccordSheet
    data object Drill : AccordSheet
    data object Halt : AccordSheet
    data object Announce : AccordSheet
    data class Cosign(val inv: AccordInvocationDto) : AccordSheet
    /** Cosign a canonical co-scrub (CIRISServer#174); [entry] null → paste fallback. */
    data class CoscrubCosign(val entry: PendingCoscrubDto?) : AccordSheet
    data class Withdraw(val server: CanonicalServerDto) : AccordSheet
    data class Details(val att: Attestation) : AccordSheet
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AccordScreen(
    viewModel: AccordViewModel,
    onBack: () -> Unit,
    /**
     * Open the guided genesis ceremony — reached from the `[+ New]` menu, enabled
     * only when no accord family exists yet (a founder trio stands up a NEW mesh's
     * 2-of-3 human kill-switch).
     */
    onStartCeremony: () -> Unit = {},
) {
    val family by viewModel.family.collectAsState()
    val holders by viewModel.holders.collectAsState()
    val invocations by viewModel.invocations.collectAsState()
    val haltStatus by viewModel.haltStatus.collectAsState()
    val drills by viewModel.drills.collectAsState()
    val announcements by viewModel.announcements.collectAsState()
    val canonicalServers by viewModel.canonicalServers.collectAsState()
    val canonicalWithdrawals by viewModel.canonicalWithdrawals.collectAsState()
    val pendingCoscrubs by viewModel.pendingCoscrubs.collectAsState()
    val loading by viewModel.loading.collectAsState()
    val busy by viewModel.busy.collectAsState()
    val error by viewModel.error.collectAsState()
    val notice by viewModel.notice.collectAsState()
    val lastCoscrubJson by viewModel.lastCoscrubJson.collectAsState()

    val viewer = ViewerAuthority(isHolder = holders.isNotEmpty())

    val clipboard = LocalClipboardManager.current
    val exportScope = rememberCoroutineScope()
    var sheet by remember { mutableStateOf<AccordSheet?>(null) }
    var newMenu by remember { mutableStateOf(false) }
    var saveDir by remember { mutableStateOf<String?>(null) }
    val scrollState = rememberScrollState()

    // Screen entry: refresh the canonical roster + the gossiped pending co-scrubs so a
    // partial that arrived over the accord peer-plane shows up without a manual refresh.
    LaunchedEffect(Unit) {
        viewModel.loadCanonicalServers()
        viewModel.loadPendingCoscrubs()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("mobile.accord_title")) },
                navigationIcon = {
                    IconButton(
                        onClick = onBack,
                        modifier = Modifier.testableClickable("btn_accord_back") { onBack() },
                    ) {
                        Icon(CIRISIcons.arrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    Box {
                        IconButton(
                            onClick = { newMenu = true },
                            modifier = Modifier.testableClickable("btn_accord_new") { newMenu = true },
                        ) {
                            Icon(CIRISIcons.add, contentDescription = localizedString("mobile.accord_new"))
                        }
                        NewAttestationMenu(
                            expanded = newMenu,
                            onDismiss = { newMenu = false },
                            actions = buildList {
                                add(
                                    NewAttestationAction("admit_node", "mobile.accord_new_admit_node") {
                                        sheet = AccordSheet.AdmitNode
                                    },
                                )
                                add(
                                    NewAttestationAction("add_canonical", "mobile.accord_new_add_canonical") {
                                        sheet = AccordSheet.AddCanonical(replace = null)
                                    },
                                )
                                add(
                                    NewAttestationAction("cosign_paste", "mobile.accord_new_cosign_paste") {
                                        sheet = AccordSheet.CoscrubCosign(entry = null)
                                    },
                                )
                                add(
                                    NewAttestationAction(
                                        "found_accord",
                                        "mobile.accord_new_found_accord",
                                        enabled = family == null,
                                    ) { onStartCeremony() },
                                )
                                add(
                                    NewAttestationAction("drill", "mobile.accord_new_drill") {
                                        sheet = AccordSheet.Drill
                                    },
                                )
                                add(
                                    NewAttestationAction("announce", "mobile.accord_new_announce") {
                                        sheet = AccordSheet.Announce
                                    },
                                )
                                // RAISE a halt: the initiating holder hardware-signs ONE
                                // (sub-quorum) signature — it does NOT latch; 2-of-3 concur
                                // does. Grave, so styled destructive, but safe to raise.
                                add(
                                    NewAttestationAction(
                                        "halt",
                                        "mobile.accord_new_halt",
                                        destructive = true,
                                    ) { sheet = AccordSheet.Halt },
                                )
                            },
                        )
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
                .verticalScroll(scrollState),
        ) {
            Spacer(Modifier.height(8.dp))
            Text(
                text = localizedString("mobile.accord_subtitle"),
                fontSize = 13.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            // ── Messages ─────────────────────────────────────────────────────
            notice?.let { msg -> Banner(msg, error = false, tag = "accord_notice") }
            error?.let { msg -> Banner(msg, error = true, tag = "accord_error") }

            // ── Co-scrub export (after Propose / Cosign) ─────────────────────
            //    Surface the returned partial so the operator can hand it to the next
            //    holder without pulling it off disk: Copy to clipboard, or Save to a
            //    chosen folder (desktop). Dismiss when done.
            lastCoscrubJson?.let { json ->
                CoscrubExportRow(
                    onCopy = { clipboard.setText(AnnotatedString(json)) },
                    onSave = { saveDir = "" },
                    onDismiss = { viewModel.clearLastCoscrubJson() },
                )
            }
            // Save flow: pick a folder, then write the partial JSON into it.
            DirectoryPickerDialog(
                show = saveDir == "",
                onDirectoryPicked = { dir ->
                    saveDir = null
                    val json = lastCoscrubJson
                    if (json != null) {
                        exportScope.launch {
                            val ok = writeTextFile(dir, "canonical-coscrub-partial.json", json)
                            viewModel.setExternalNotice(
                                if (ok) "Saved the co-scrub partial to $dir."
                                else "Couldn't save to $dir (this platform may not support file writes).",
                                error = !ok,
                            )
                        }
                    }
                },
                onDismiss = { saveDir = null },
            )

            // ── ACTIVE-HALT banner (§3.5). NOTE: kept screen-local (top of the
            //    Trust Root), not truly app-global — wiring a sticky banner above the
            //    nav host is a separate refactor. It is the most prominent thing here
            //    when the kill-switch is latched. Read-only; the app never clears it.
            if (haltStatus?.halted == true) {
                HaltBanner(haltStatus?.record)
            }

            // ── §1 The accord (family + holder roster) ───────────────────────
            SectionHeader(localizedString("mobile.accord_section_accord"), loading)
            val fam = family
            if (fam == null && !loading) {
                Text(
                    localizedString("mobile.accord_family_empty"),
                    fontSize = 13.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            } else if (fam != null) {
                val famAtt = familyAttestation(fam)
                AttestationCard(
                    att = famAtt,
                    viewer = viewer,
                    onOp = { op -> handleOp(op, famAtt) { sheet = it } },
                ) {
                    Text(
                        fam.familyName,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onSurface,
                    )
                }
            }
            if (holders.isEmpty() && !loading) {
                Text(
                    localizedString("mobile.accord_holders_empty"),
                    fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 6.dp),
                )
            } else {
                holders.forEach { h ->
                    val att = holderAttestation(h)
                    AttestationCard(att = att, viewer = viewer, onOp = { op -> handleOp(op, att) { sheet = it } })
                }
            }

            // ── §2 Canonical servers ─────────────────────────────────────────
            SectionHeader(localizedString("mobile.accord_section_canonical"), false)
            if (canonicalServers.isEmpty()) {
                Text(
                    localizedString("mobile.accord_canonical_empty"),
                    fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.testable("accord_canonical_empty"),
                )
            } else {
                canonicalServers.forEach { s ->
                    val att = canonicalAttestation(s)
                    val ip = s.transportHints?.firstOrNull { it.kind == "ip" }?.destination
                    AttestationCard(
                        att = att,
                        viewer = viewer,
                        onOp = { op -> handleOpCanonical(op, att, s) { sheet = it } },
                    ) {
                        Text(
                            localizedString(
                                "mobile.accord_canonical_current_ip",
                                "ip",
                                ip?.takeIf { it.isNotBlank() }
                                    ?: localizedString("mobile.accord_canonical_ip_none"),
                            ),
                            fontSize = 11.sp,
                            fontFamily = FontFamily.Monospace,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.testable("canonical_server_ip_${s.keyId}"),
                        )
                    }
                }
            }

            // ── §2b Pending co-signs (canonical co-scrubs, CIRISServer#174) ──
            //    Partials still short of the family m-of-n — minted locally by
            //    propose OR gossiped in from another holder's device. Cosign here.
            SectionHeader(localizedString("mobile.accord_section_coscrub"), loading)
            if (pendingCoscrubs.isEmpty() && !loading) {
                Text(
                    localizedString("mobile.accord_coscrub_empty"),
                    fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.testable("accord_coscrub_empty"),
                )
            } else {
                pendingCoscrubs.forEach { entry ->
                    val att = coscrubAttestation(entry)
                    AttestationCard(
                        att = att,
                        viewer = viewer,
                        onOp = { op ->
                            when (op) {
                                AttOp.Cosign -> sheet = AccordSheet.CoscrubCosign(entry)
                                AttOp.Copy -> {
                                    clipboard.setText(AnnotatedString(viewModel.exportPartial(entry.partial)))
                                    viewModel.setExternalNotice(
                                        "Copied the co-scrub partial for ${entry.targetKeyId} to the clipboard.",
                                    )
                                }
                                else -> handleOp(op, att) { sheet = it }
                            }
                        },
                    ) {
                        CoscrubSlot(entry)
                    }
                }
            }

            // ── §3 Pending co-signs (invocations: halt / drill / notify) ─────
            SectionHeader(localizedString("mobile.accord_section_pending"), false)
            if (invocations.isEmpty() && !loading) {
                Text(
                    localizedString("mobile.accord_pending_empty"),
                    fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            } else {
                invocations.forEach { inv ->
                    val att = invocationAttestation(inv)
                    AttestationCard(
                        att = att,
                        viewer = viewer,
                        onOp = { op ->
                            when (op) {
                                AttOp.Cosign -> sheet = AccordSheet.Cosign(inv)
                                else -> handleOp(op, att) { sheet = it }
                            }
                        },
                    ) {
                        InvocationBindingNote(inv)
                    }
                }
            }

            // ── §4 History (withdrawn / superseded + completed drills / announces) ──
            SectionHeader(localizedString("mobile.accord_section_history"), false)
            val hasHistory = canonicalWithdrawals.isNotEmpty() ||
                drills.isNotEmpty() || announcements.isNotEmpty()
            if (!hasHistory) {
                Text(
                    localizedString("mobile.accord_history_empty"),
                    fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.testable("accord_history_empty"),
                )
            } else {
                canonicalWithdrawals.forEach { w ->
                    val att = withdrawalAttestation(w)
                    AttestationCard(att = att, viewer = viewer, onOp = { op -> handleOp(op, att) { sheet = it } })
                }
                drills.forEach { ev ->
                    val att = eventAttestation(ev, isAnnounce = false)
                    AttestationCard(att = att, viewer = viewer, onOp = { op -> handleOp(op, att) { sheet = it } }) {
                        EventSlot(ev, isAnnounce = false)
                    }
                }
                announcements.forEach { ev ->
                    val att = eventAttestation(ev, isAnnounce = true)
                    AttestationCard(att = att, viewer = viewer, onOp = { op -> handleOp(op, att) { sheet = it } }) {
                        EventSlot(ev, isAnnounce = true)
                    }
                }
            }

            Spacer(Modifier.height(24.dp))
        }
    }

    // ── Shared sub-flows ─────────────────────────────────────────────────────
    when (val s = sheet) {
        null -> Unit
        is AccordSheet.AdmitNode -> AdmitNodeSheet(viewModel, holders, busy) { sheet = null }
        is AccordSheet.AddCanonical ->
            AddCanonicalSheet(viewModel, holders, busy, s.replace) { sheet = null }
        is AccordSheet.Drill -> DrillSheet(viewModel, holders, busy) { sheet = null }
        is AccordSheet.Halt -> HaltSheet(viewModel, holders, busy) { sheet = null }
        is AccordSheet.Announce -> AnnounceSheet(viewModel, holders, busy) { sheet = null }
        is AccordSheet.Cosign -> {
            val inv = s.inv
            CosignSheet(
                invocationId = inv.invocationId,
                kindLabel = invocationBadge(inv.invocationKind),
                signed = inv.validSigners.size,
                threshold = inv.quorumThreshold,
                binding = inv.invocationKind.uppercase() == "CONSTITUTIONAL",
                holders = holders,
                busy = busy,
                onSubmit = { holderKeyId, usbPath, pin, modulePath ->
                    viewModel.concur(inv.invocationKind, inv.invocationId, holderKeyId, usbPath, pin, modulePath)
                    sheet = null
                },
                onDismiss = { sheet = null },
            )
        }
        is AccordSheet.CoscrubCosign -> {
            CanonicalCosignSheet(
                entry = s.entry,
                holders = holders,
                busy = busy,
                onSubmit = { holderKeyId, usbPath, pin, modulePath, partial ->
                    viewModel.cosignCanonical(holderKeyId, usbPath, pin, partial, modulePath)
                },
                onError = { msg -> viewModel.showError(msg) },
                onDismiss = { sheet = null },
            )
        }
        is AccordSheet.Withdraw -> {
            val server = s.server
            ConfirmDestructive(
                title = localizedString("mobile.accord_confirm_withdraw_title"),
                message = localizedString("mobile.accord_canonical_destructive_note"),
                confirmLabel = localizedString("mobile.accord_op_withdraw"),
                tagPrefix = server.keyId,
                busy = busy,
                showDigest = true,
                digestLabel = localizedString("mobile.accord_canonical_proposal_digest_label"),
                onConfirm = { digest ->
                    viewModel.withdrawCanonical(server.keyId, digest)
                    sheet = null
                },
                onDismiss = { sheet = null },
            )
        }
        is AccordSheet.Details -> AttestationDetailsDialog(s.att) { sheet = null }
    }
}

// ── Op routing ───────────────────────────────────────────────────────────────

/** Route the uniform ops that don't need canonical-row context. */
private fun handleOp(op: AttOp, att: Attestation, open: (AccordSheet) -> Unit) {
    when (op) {
        AttOp.ViewDetails, AttOp.History, AttOp.Evidence -> open(AccordSheet.Details(att))
        // Cosign / Delegate / Supersede / Withdraw / Recant have no meaning here
        // (or are disabled in the menu) — details is the safe fallthrough.
        else -> open(AccordSheet.Details(att))
    }
}

/** Canonical rows carry the two real destructive/replace ops. */
private fun handleOpCanonical(
    op: AttOp,
    att: Attestation,
    server: CanonicalServerDto,
    open: (AccordSheet) -> Unit,
) {
    when (op) {
        AttOp.Supersede -> open(AccordSheet.AddCanonical(replace = server)) // replace = 1-of-N re-mint
        AttOp.Withdraw -> open(AccordSheet.Withdraw(server))
        else -> handleOp(op, att, open)
    }
}

// ── DTO → Attestation mappers ─────────────────────────────────────────────────

@Composable
private fun familyAttestation(fam: AccordFamilyDto): Attestation = Attestation(
    id = fam.familyKeyId,
    kind = AttKind.AccordFamily,
    status = if (fam.entrenched) AttStatus.Entrenched else AttStatus.Active,
    badge = localizedString("mobile.accord_badge_accord"),
    dimension = fam.consensusProtocol,
)

@Composable
private fun holderAttestation(h: AccordHolderDto): Attestation = Attestation(
    id = h.keyId,
    kind = AttKind.Holder,
    status = AttStatus.Active,
    badge = localizedString("mobile.accord_badge_holder"),
    threshold = 1,
    dimension = localizedString("mobile.accord_holder_attested"),
)

@Composable
private fun canonicalAttestation(s: CanonicalServerDto): Attestation = Attestation(
    id = s.keyId,
    kind = AttKind.Canonical,
    status = AttStatus.Active,
    badge = localizedString("mobile.accord_canonical_badge").uppercase(),
    threshold = 1,
    dimension = s.identityType,
    attesterKeyId = s.scrubKeyId,
    timestamp = s.validFrom,
)

@Composable
private fun coscrubAttestation(entry: PendingCoscrubDto): Attestation = Attestation(
    id = entry.targetKeyId,
    kind = AttKind.Coscrub,
    status = AttStatus.Pending,
    badge = localizedString("mobile.accord_canonical_badge").uppercase(),
    signed = entry.distinctScrubCount,
    // quorum_needed is best-effort (0 when the node can't resolve M) — fall back to 2.
    threshold = entry.quorumNeeded.takeIf { it > 0 } ?: 2,
    dimension = localizedString("mobile.accord_coscrub_badge")
        .replace("{signed}", entry.distinctScrubCount.toString())
        .replace("{needed}", (entry.quorumNeeded.takeIf { it > 0 } ?: 2).toString()),
    timestamp = entry.receivedAt,
    // These flooded in over the accord peer-plane (or were minted here by propose).
    arrivedViaGossip = true,
)

@Composable
private fun invocationAttestation(inv: AccordInvocationDto): Attestation = Attestation(
    id = inv.invocationId,
    kind = AttKind.Invocation,
    status = if (inv.quorumMet) AttStatus.Active else AttStatus.Pending,
    badge = invocationBadge(inv.invocationKind),
    styleKey = inv.invocationKind,
    signed = inv.validSigners.size,
    threshold = inv.quorumThreshold,
    dimension = "accord:invocation",
    // The mesh gossips these partials to every announced device (src/accord.rs).
    arrivedViaGossip = !inv.quorumMet,
)

@Composable
private fun withdrawalAttestation(w: CanonicalWithdrawalDto): Attestation = Attestation(
    id = w.keyId,
    kind = AttKind.Withdrawal,
    status = if (!w.supersededBy.isNullOrBlank()) AttStatus.Superseded else AttStatus.Withdrawn,
    badge = localizedString("mobile.accord_canonical_badge").uppercase(),
    supersededBy = w.supersededBy,
    timestamp = w.withdrawnAt,
)

@Composable
private fun eventAttestation(ev: AccordEventDto, isAnnounce: Boolean): Attestation = Attestation(
    id = ev.invocationId,
    kind = AttKind.Invocation,
    status = AttStatus.Active,
    badge = invocationBadge(if (isAnnounce) "NOTIFY" else "DRILL"),
    styleKey = if (isAnnounce) "NOTIFY" else "DRILL",
    signed = ev.signers.size,
    threshold = ev.quorumThreshold,
    timestamp = ev.recordedAt,
)

@Composable
private fun invocationBadge(kind: String): String = when (kind.uppercase()) {
    "CONSTITUTIONAL" -> localizedString("mobile.accord_kind_constitutional")
    "DRILL" -> localizedString("mobile.accord_kind_drill")
    else -> localizedString("mobile.accord_kind_notify")
}

// ── Sheets (each wraps an existing VM method) ─────────────────────────────────

@Composable
private fun AdmitNodeSheet(
    viewModel: AccordViewModel,
    holders: List<AccordHolderDto>,
    busy: Boolean,
    onDismiss: () -> Unit,
) {
    val ownedNodes by viewModel.ownedNodes.collectAsState()
    val target by viewModel.resolvedTarget.collectAsState()
    HardwareScrubSheet(
        title = localizedString("mobile.accord_new_admit_node"),
        subtitle = localizedString("mobile.accord_admit_desc"),
        holders = holders,
        busy = busy,
        submitLabel = localizedString("mobile.accord_admit_submit"),
        submitBusyLabel = localizedString("mobile.accord_admit_submit_busy"),
        tagPrefix = "admit",
        extraReady = target != null,
        extras = {
            TargetPicker(
                label = localizedString("mobile.accord_admit_target_select"),
                ownedNodes = ownedNodes,
                resolvedKeyId = target?.keyId,
                onResolve = { viewModel.resolveTargetNode(it) },
                tagPrefix = "admit",
            )
        },
        onSubmit = { holderKeyId, usbPath, pin, modulePath ->
            target?.let { t ->
                viewModel.admitNode(holderKeyId, usbPath, t.keyId, t.ed25519, t.mldsa, pin, modulePath)
            }
            onDismiss()
        },
        onDismiss = onDismiss,
    )
}

@Composable
private fun AddCanonicalSheet(
    viewModel: AccordViewModel,
    holders: List<AccordHolderDto>,
    busy: Boolean,
    replace: CanonicalServerDto?,
    onDismiss: () -> Unit,
) {
    val ownedNodes by viewModel.ownedNodes.collectAsState()
    val target by viewModel.canonicalResolvedTarget.collectAsState()
    // Replace = a 1-of-N re-mint of an existing canonical record: seed the resolved
    // target + current IP from the row (mirrors the old selectCanonicalForReplace).
    val seededIp = remember(replace) {
        replace?.transportHints?.firstOrNull { h -> h.kind == "ip" }?.destination.orEmpty() ?: ""
    }
    LaunchedEffect(replace) {
        if (replace != null) {
            viewModel.selectCanonicalForReplace(replace)
            viewModel.clearCanonicalReplaceSeed()
        }
    }
    var ip by remember { mutableStateOf(seededIp) }
    var transport by remember { mutableStateOf("ip") }
    HardwareScrubSheet(
        title = localizedString(
            if (replace != null) "mobile.accord_op_supersede" else "mobile.accord_new_add_canonical",
        ),
        subtitle = localizedString(
            if (replace != null) "mobile.accord_canonical_desc"
            else "mobile.accord_canonical_propose_desc",
        ),
        holders = holders,
        busy = busy,
        submitLabel = localizedString(
            if (replace != null) "mobile.accord_canonical_add_btn"
            else "mobile.accord_canonical_propose_btn",
        ),
        submitBusyLabel = localizedString(
            if (replace != null) "mobile.accord_canonical_add_btn_busy"
            else "mobile.accord_canonical_propose_btn_busy",
        ),
        tagPrefix = "canonical",
        extraReady = target != null,
        extras = {
            if (replace == null) {
                TargetPicker(
                    label = localizedString("mobile.accord_canonical_target_select"),
                    ownedNodes = ownedNodes,
                    resolvedKeyId = target?.keyId,
                    onResolve = { viewModel.resolveCanonicalTarget(it) },
                    tagPrefix = "canonical",
                )
            } else {
                Text(
                    localizedString("mobile.accord_canonical_target_resolved", "key", replace.keyId),
                    fontSize = 11.sp,
                    fontFamily = FontFamily.Monospace,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.testable("accord_canonical_target_resolved"),
                )
            }
            Spacer(Modifier.height(6.dp))
            OutlinedTextField(
                value = ip,
                onValueChange = { ip = it },
                singleLine = true,
                label = { Text(localizedString("mobile.accord_canonical_ip_label")) },
                modifier = Modifier.fillMaxWidth().testable("input_canonical_destination"),
            )
            Spacer(Modifier.height(6.dp))
            OutlinedTextField(
                value = transport,
                onValueChange = { transport = it },
                singleLine = true,
                label = { Text(localizedString("mobile.accord_canonical_transport_label")) },
                modifier = Modifier.fillMaxWidth().testable("input_canonical_transport_kind"),
            )
        },
        onSubmit = { holderKeyId, usbPath, pin, modulePath ->
            target?.let { t ->
                if (replace != null) {
                    // Replace / update = the shipped 1-of-N re-mint of a live record.
                    viewModel.addCanonicalServer(
                        holderKeyId, usbPath, t.keyId, t.ed25519, t.mldsa, pin,
                        transport.ifBlank { null }, ip.ifBlank { null }, modulePath,
                    )
                } else {
                    // A fresh canonical server is now m-of-n: propose is scrub #1; the
                    // partial gossips to the next holder to cosign (CIRISServer#174).
                    viewModel.proposeCanonical(
                        holderKeyId, usbPath, t.keyId, t.ed25519, t.mldsa, pin,
                        transport.ifBlank { null }, ip.ifBlank { null }, modulePath,
                    )
                }
            }
            onDismiss()
        },
        onDismiss = onDismiss,
    )
}

@Composable
private fun DrillSheet(
    viewModel: AccordViewModel,
    holders: List<AccordHolderDto>,
    busy: Boolean,
    onDismiss: () -> Unit,
) {
    var drillId by remember { mutableStateOf("") }
    HardwareScrubSheet(
        title = localizedString("mobile.accord_new_drill"),
        subtitle = localizedString("mobile.accord_drill_desc"),
        holders = holders,
        busy = busy,
        submitLabel = localizedString("mobile.accord_start_drill"),
        submitBusyLabel = localizedString("mobile.accord_start_drill"),
        tagPrefix = "drill",
        extraReady = drillId.isNotBlank(),
        extras = {
            OutlinedTextField(
                value = drillId,
                onValueChange = { drillId = it },
                singleLine = true,
                label = { Text(localizedString("mobile.accord_drill_id_label")) },
                modifier = Modifier.fillMaxWidth().testable("input_accord_drill_id"),
            )
        },
        onSubmit = { holderKeyId, usbPath, pin, modulePath ->
            viewModel.initiateDrill(drillId, holderKeyId, usbPath, pin, modulePath)
            onDismiss()
        },
        onDismiss = onDismiss,
    )
}

@Composable
private fun HaltSheet(
    viewModel: AccordViewModel,
    holders: List<AccordHolderDto>,
    busy: Boolean,
    onDismiss: () -> Unit,
) {
    // RAISE a 2-of-3 CONSTITUTIONAL halt. This holder's single signature is SUB-QUORUM —
    // it does NOT latch; it gossips and the other holders concur to 2-of-3, which latches.
    HardwareScrubSheet(
        title = localizedString("mobile.accord_new_halt"),
        subtitle = localizedString("mobile.accord_halt_raise_desc"),
        holders = holders,
        busy = busy,
        submitLabel = localizedString("mobile.accord_raise_halt"),
        submitBusyLabel = localizedString("mobile.accord_raise_halt"),
        tagPrefix = "halt",
        onSubmit = { holderKeyId, usbPath, pin, modulePath ->
            viewModel.initiateHalt(holderKeyId, usbPath, pin, modulePath)
            onDismiss()
        },
        onDismiss = onDismiss,
    )
}

@Composable
private fun AnnounceSheet(
    viewModel: AccordViewModel,
    holders: List<AccordHolderDto>,
    busy: Boolean,
    onDismiss: () -> Unit,
) {
    var message by remember { mutableStateOf("") }
    HardwareScrubSheet(
        title = localizedString("mobile.accord_new_announce"),
        subtitle = localizedString("mobile.accord_announce_desc"),
        holders = holders,
        busy = busy,
        submitLabel = localizedString("mobile.accord_post_announce"),
        submitBusyLabel = localizedString("mobile.accord_post_announce"),
        tagPrefix = "announce",
        extraReady = message.isNotBlank(),
        extras = {
            OutlinedTextField(
                value = message,
                onValueChange = { message = it },
                label = { Text(localizedString("mobile.accord_announce_label")) },
                modifier = Modifier.fillMaxWidth().testable("input_accord_announce"),
            )
        },
        onSubmit = { holderKeyId, usbPath, pin, modulePath ->
            viewModel.initiateAnnounce(message, holderKeyId, usbPath, pin, modulePath)
            onDismiss()
        },
        onDismiss = onDismiss,
    )
}

/** The owned-node picker + resolved indicator shared by admit / add-canonical. */
@Composable
private fun ColumnScope.TargetPicker(
    label: String,
    ownedNodes: List<String>,
    resolvedKeyId: String?,
    onResolve: (String) -> Unit,
    tagPrefix: String,
) {
    var menu by remember { mutableStateOf(false) }
    Box(modifier = Modifier.fillMaxWidth()) {
        OutlinedButton(
            onClick = { menu = true },
            modifier = Modifier.fillMaxWidth().testable("dd_target_$tagPrefix"),
        ) {
            Text(resolvedKeyId ?: label)
        }
        DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
            if (ownedNodes.isEmpty()) {
                DropdownMenuItem(
                    text = { Text(localizedString("mobile.accord_canonical_no_owned")) },
                    onClick = { menu = false },
                )
            }
            ownedNodes.forEach { n ->
                DropdownMenuItem(
                    text = { Text(n, fontFamily = FontFamily.Monospace) },
                    onClick = { onResolve(n); menu = false },
                    modifier = Modifier.testableClickable("mi_target_${tagPrefix}_$n") {
                        onResolve(n); menu = false
                    },
                )
            }
        }
    }
    resolvedKeyId?.let {
        Text(
            localizedString("mobile.accord_canonical_target_resolved", "key", it),
            fontSize = 11.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 4.dp).testable("accord_target_resolved_$tagPrefix"),
        )
    }
}

// ── Small shared pieces ───────────────────────────────────────────────────────

@Composable
private fun ColumnScope.SectionHeader(title: String, loading: Boolean) {
    Spacer(Modifier.height(20.dp))
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(title, fontSize = 15.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
        if (loading) {
            CircularProgressIndicator(modifier = Modifier.size(14.dp), strokeWidth = 2.dp)
        }
    }
    Spacer(Modifier.height(8.dp))
}

@Composable
private fun ColumnScope.Banner(msg: String, error: Boolean, tag: String) {
    Spacer(Modifier.height(8.dp))
    Surface(
        shape = RoundedCornerShape(10.dp),
        color = if (error) MaterialTheme.colorScheme.errorContainer
        else MaterialTheme.colorScheme.secondaryContainer,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(
            msg,
            fontSize = 12.sp,
            color = if (error) MaterialTheme.colorScheme.onErrorContainer
            else MaterialTheme.colorScheme.onSecondaryContainer,
            modifier = Modifier.padding(10.dp).testable(tag),
        )
    }
}

/**
 * The Copy / Save row surfaced after a Propose or Cosign returns a still-partial
 * co-scrub — hand the partial to the next holder without touching the filesystem.
 */
@Composable
private fun ColumnScope.CoscrubExportRow(
    onCopy: () -> Unit,
    onSave: () -> Unit,
    onDismiss: () -> Unit,
) {
    Spacer(Modifier.height(8.dp))
    Surface(
        shape = RoundedCornerShape(10.dp),
        color = MaterialTheme.colorScheme.secondaryContainer,
        modifier = Modifier.fillMaxWidth().testable("accord_coscrub_export"),
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth().padding(10.dp),
        ) {
            Text(
                localizedString("mobile.accord_coscrub_export_hint"),
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.onSecondaryContainer,
                modifier = Modifier.weight(1f),
            )
            TextButton(
                onClick = onCopy,
                modifier = Modifier.testableClickable("btn_coscrub_export_copy") { onCopy() },
            ) { Text(localizedString("mobile.accord_op_copy")) }
            TextButton(
                onClick = onSave,
                modifier = Modifier.testableClickable("btn_coscrub_export_save") { onSave() },
            ) { Text(localizedString("mobile.accord_coscrub_export_save")) }
            TextButton(
                onClick = onDismiss,
                modifier = Modifier.testableClickable("btn_coscrub_export_dismiss") { onDismiss() },
            ) { Text(localizedString("mobile.accord_scrub_cancel")) }
        }
    }
}

@Composable
private fun ColumnScope.HaltBanner(
    record: ai.ciris.mobile.shared.models.federation.AccordHaltRecordDto?,
) {
    Spacer(Modifier.height(12.dp))
    Surface(
        shape = RoundedCornerShape(12.dp),
        color = MaterialTheme.colorScheme.errorContainer,
        border = BorderStroke(2.dp, MaterialTheme.colorScheme.error),
        modifier = Modifier.fillMaxWidth().testable("accord_halt_banner"),
    ) {
        Column(modifier = Modifier.fillMaxWidth().padding(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    CIRISIcons.shield,
                    contentDescription = null,
                    modifier = Modifier.size(22.dp),
                    tint = MaterialTheme.colorScheme.error,
                )
                Spacer(Modifier.width(10.dp))
                Text(
                    localizedString("mobile.accord_halt_active_title"),
                    fontSize = 16.sp,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onErrorContainer,
                )
            }
            Spacer(Modifier.height(8.dp))
            Text(
                localizedString("mobile.accord_halt_active_desc"),
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.onErrorContainer,
            )
            record?.let { rec ->
                Spacer(Modifier.height(8.dp))
                rec.invocationId?.let { id ->
                    Text(
                        localizedString("mobile.accord_halt_invocation").replace("{id}", id),
                        fontSize = 11.sp,
                        fontFamily = FontFamily.Monospace,
                        color = MaterialTheme.colorScheme.onErrorContainer,
                    )
                }
                rec.latchedAt?.let { at ->
                    Text(
                        localizedString("mobile.accord_halt_latched_at").replace("{when}", at),
                        fontSize = 11.sp,
                        color = MaterialTheme.colorScheme.onErrorContainer,
                    )
                }
                if (rec.validSigners.isNotEmpty()) {
                    Text(
                        localizedString("mobile.accord_halt_signers")
                            .replace("{signers}", rec.validSigners.joinToString(", ")),
                        fontSize = 11.sp,
                        fontFamily = FontFamily.Monospace,
                        color = MaterialTheme.colorScheme.onErrorContainer,
                    )
                }
            }
        }
    }
}

/** The one kind-specific slot for an invocation: its binding note. */
@Composable
private fun ColumnScope.InvocationBindingNote(inv: AccordInvocationDto) {
    val text = when (inv.invocationKind.uppercase()) {
        "CONSTITUTIONAL" -> localizedString("mobile.accord_binding_constitutional")
        "DRILL" -> localizedString("mobile.accord_binding_drill")
        else -> localizedString("mobile.accord_binding_notify")
    }
    Text(text, fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

/** The inline slot for a pending canonical co-scrub: its scrubbers + roster note. */
@Composable
private fun ColumnScope.CoscrubSlot(entry: PendingCoscrubDto) {
    if (entry.scrubbers.isNotEmpty()) {
        Text(
            localizedString("mobile.accord_coscrub_scrubbers", "scrubbers", entry.scrubbers.joinToString(", ")),
            fontSize = 11.sp,
            fontFamily = FontFamily.Monospace,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.testable("coscrub_scrubbers_${entry.targetKeyId}"),
        )
    }
    if (!entry.rosterVerified) {
        Spacer(Modifier.height(4.dp))
        Text(
            localizedString("mobile.accord_coscrub_unverified"),
            fontSize = 11.sp,
            color = MaterialTheme.colorScheme.error,
        )
    }
}

/** The inline slot for a completed drill / announcement event. */
@Composable
private fun ColumnScope.EventSlot(ev: AccordEventDto, isAnnounce: Boolean) {
    if (isAnnounce) {
        ev.message?.let { msg ->
            Text(msg, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurface)
            Spacer(Modifier.height(4.dp))
        }
    }
    if (ev.signers.isNotEmpty()) {
        Text(
            localizedString(
                if (isAnnounce) "mobile.accord_event_from" else "mobile.accord_event_signers",
            ).replace("{signers}", ev.signers.joinToString(", ")),
            fontSize = 11.sp,
            fontFamily = FontFamily.Monospace,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

/** The uniform View-details / History sheet folded into every card's `⋮`. */
@Composable
private fun AttestationDetailsDialog(att: Attestation, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(localizedString("mobile.accord_op_view_details")) },
        text = {
            Column(modifier = Modifier.testable("accord_details_${att.id}")) {
                DetailRow(localizedString("mobile.accord_detail_id"), att.id)
                DetailRow(localizedString("mobile.accord_detail_kind"), att.badge)
                DetailRow(localizedString("mobile.accord_detail_status"), att.status.name)
                att.dimension?.let { DetailRow(localizedString("mobile.accord_detail_dimension"), it) }
                att.attesterKeyId?.let { DetailRow(localizedString("mobile.accord_detail_attester"), it) }
                att.timestamp?.let { DetailRow(localizedString("mobile.accord_detail_when"), it) }
                att.supersededBy?.let { DetailRow(localizedString("mobile.accord_detail_superseded_by"), it) }
                if (att.threshold != null) {
                    DetailRow(
                        localizedString("mobile.accord_detail_quorum"),
                        "${att.signed ?: 0} / ${att.threshold}",
                    )
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = onDismiss,
                modifier = Modifier.testableClickable("btn_details_close_${att.id}") { onDismiss() },
            ) { Text(localizedString("mobile.accord_scrub_cancel")) }
        },
    )
}

@Composable
private fun DetailRow(label: String, value: String) {
    Row(modifier = Modifier.fillMaxWidth().padding(vertical = 3.dp)) {
        Text(
            label,
            fontSize = 12.sp,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.width(96.dp),
        )
        Text(
            value,
            fontSize = 12.sp,
            fontFamily = FontFamily.Monospace,
            color = MaterialTheme.colorScheme.onSurface,
        )
    }
}
