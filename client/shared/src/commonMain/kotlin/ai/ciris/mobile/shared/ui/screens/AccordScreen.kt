package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.federation.AccordEventDto
import ai.ciris.mobile.shared.models.federation.AccordFamilyDto
import ai.ciris.mobile.shared.models.federation.AccordHolderDto
import ai.ciris.mobile.shared.models.federation.AccordInvocationDto
import ai.ciris.mobile.shared.models.federation.CanonicalServerDto
import ai.ciris.mobile.shared.models.federation.CanonicalWithdrawalDto
import ai.ciris.mobile.shared.models.federation.CiKeyTargetInput
import ai.ciris.mobile.shared.models.federation.PendingCoscrubDto
import ai.ciris.mobile.shared.models.federation.genesisSeedDisplay
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
import ai.ciris.mobile.shared.ui.components.HolderSignInputs
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
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
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
    /** Batch-bless the substrate CI workers (default-populated one-click card). */
    data object BlessCiWorkers : AccordSheet
    /** Re-mint the EXISTING trust root into a portable genesis (FSD/MESH_GENESIS.md). */
    data object RemintTrustRoot : AccordSheet
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
                                    NewAttestationAction("bless_ci_workers", "mobile.accord_new_bless_ci_workers") {
                                        sheet = AccordSheet.BlessCiWorkers
                                    },
                                )
                                add(
                                    NewAttestationAction("remint_trust_root", "mobile.accord_new_remint_trust_root") {
                                        sheet = AccordSheet.RemintTrustRoot
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
        is AccordSheet.BlessCiWorkers -> BlessCiWorkersSheet(viewModel, holders, busy) { sheet = null }
        is AccordSheet.RemintTrustRoot -> RemintTrustRootSheet(viewModel, holders, busy) { sheet = null }
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
        AttOp.Supersede -> open(AccordSheet.AddCanonical(replace = server)) // replace = m-of-n co-scrub re-mint (same 2-of-3 family quorum as add)
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
    // quorum_needed is best-effort: 0 when the node can't resolve M. Pass the 0
    // through — the pill renders "?" rather than inventing a threshold.
    threshold = entry.quorumNeeded,
    dimension = localizedString("mobile.accord_coscrub_badge")
        .replace("{signed}", entry.distinctScrubCount.toString())
        .replace("{needed}", entry.quorumNeeded.takeIf { it > 0 }?.toString() ?: "?"),
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
    val canonicalServers by viewModel.canonicalServers.collectAsState()
    // Re-bless made easy: a fresh propose (replace == null) defaults its target to the
    // first canonical server (e.g. ciris-canonical-1) so re-blessing it — to add
    // `infra:serve` — is a confirm, not a retype. Blank when none loaded (prior behavior).
    val defaultCanonical = if (replace == null) canonicalServers.firstOrNull() else null
    // Replace = an m-of-n co-scrub re-mint of an existing canonical record: seed the resolved
    // target + current IP from the row (mirrors the old selectCanonicalForReplace). Propose
    // seeds the same IP from the defaulted canonical so the address survives the re-bless.
    val seededIp = remember(replace, defaultCanonical?.keyId) {
        (replace ?: defaultCanonical)?.transportHints?.firstOrNull { h -> h.kind == "ip" }?.destination.orEmpty()
    }
    LaunchedEffect(replace) {
        if (replace != null) {
            viewModel.selectCanonicalForReplace(replace)
            viewModel.clearCanonicalReplaceSeed()
        }
    }
    // Best-effort pre-fill of the defaulted canonical's hybrid pubkeys via the same
    // resolve wiring the target picker uses; fires once when the roster is loaded and
    // nothing is resolved yet, so a manual re-pick is never overridden.
    LaunchedEffect(defaultCanonical?.keyId) {
        val d = defaultCanonical
        if (d != null && target == null) {
            viewModel.resolveCanonicalTarget(d.keyId)
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
                // BOTH add and replace/update go through the m-of-n family-quorum
                // co-scrub (CIRISServer#174): propose is scrub #1; the partial gossips
                // to the next holder to cosign, conferring `canonical` iff
                // distinct_scrub_count >= the family quorum. Replace re-mints the SAME
                // key_id's record with the corrected address at the same 2-of-3 quorum —
                // NEVER a 1-of-N re-mint, which would produce a 1-scrub record that fails
                // the canonical admission gate on fresh installs (a worse break than a
                // stale address). The `replace` mode only pre-resolves the target + seeds
                // the current IP; the ceremony is identical.
                viewModel.proposeCanonical(
                    holderKeyId, usbPath, t.keyId, t.ed25519, t.mldsa, pin,
                    transport.ifBlank { null }, ip.ifBlank { null }, modulePath,
                )
            }
            onDismiss()
        },
        onDismiss = onDismiss,
    )
}

/** One default-populated substrate CI worker row in the "Bless CI workers" card. */
private data class CiWorkerDefault(val keyId: String, val ed25519: String)

/**
 * The five substrate CI workers, pre-filled for a one-click batch bless. Each ed25519
 * pubkey is the repo's published build-key half (44-char base64); the 2604-char
 * ML-DSA-65 half is NOT embedded — the operator pastes it from each repo's export-job
 * artifact. `ciris-server-build-v1` has a pending export job, so both halves start blank.
 */
private val CI_WORKER_DEFAULTS = listOf(
    CiWorkerDefault("ciris-verify-build-pipeline", "W8LfgUYjZz4h8r5hcoDv09cG0xKj9ZKuPYZP45sOS9E="),
    CiWorkerDefault("ciris-persist-build-v1", "TS2WwSTQAqQ8k+8MhIp7Kb9W6DF+Eyknv7++YZZ5FQk="),
    CiWorkerDefault("agent-steward-2026", "Tynw+BfXmHV4N0jM/Vbr/Ogm1Ts9YZLD5vlYpwfNw1w="),
    CiWorkerDefault("ciris-edge-build-v1", "NapSP3umS+EIfiXqqW8g6WGxgDIwx8o9sgTE+JGWYDg="),
    CiWorkerDefault("ciris-server-build-v1", ""),
)

/**
 * **Bless CI workers** — batch-propose the substrate CI worker keys (build pipelines +
 * the agent steward) as `infra:attest` co-scrubs in ONE holder ceremony. Built on
 * [HardwareScrubSheet]; the [extras] block default-populates all five rows so it is a
 * one-click card — the operator pastes each repo's ML-DSA-65 pubkey (and the pending
 * `ciris-server-build-v1` ed25519) from its export-job artifact. Submit blesses every
 * row with BOTH pubkeys filled via `AccordViewModel.proposeCiKeys`.
 */
@Composable
private fun BlessCiWorkersSheet(
    viewModel: AccordViewModel,
    holders: List<AccordHolderDto>,
    busy: Boolean,
    onDismiss: () -> Unit,
) {
    // One editable pubkey pair per default row (kept out of the submit lambda's closure
    // by reading .value); ed25519 pre-fills the published build-key half, ML-DSA is blank.
    val edStates = remember { CI_WORKER_DEFAULTS.map { mutableStateOf(it.ed25519) } }
    val mlStates = remember { CI_WORKER_DEFAULTS.map { mutableStateOf("") } }
    val anyReady = CI_WORKER_DEFAULTS.indices.any {
        edStates[it].value.isNotBlank() && mlStates[it].value.isNotBlank()
    }
    HardwareScrubSheet(
        title = localizedString("mobile.accord_bless_ci_title"),
        subtitle = localizedString("mobile.accord_bless_ci_desc"),
        holders = holders,
        busy = busy,
        submitLabel = localizedString("mobile.accord_bless_ci_submit"),
        submitBusyLabel = localizedString("mobile.accord_bless_ci_submit_busy"),
        tagPrefix = "bless_ci",
        extraReady = anyReady,
        extras = {
            CI_WORKER_DEFAULTS.forEachIndexed { i, w ->
                Text(
                    w.keyId,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold,
                    fontFamily = FontFamily.Monospace,
                    color = MaterialTheme.colorScheme.onSurface,
                    modifier = Modifier.testable("bless_ci_key_${w.keyId}"),
                )
                Spacer(Modifier.height(4.dp))
                OutlinedTextField(
                    value = edStates[i].value,
                    onValueChange = { edStates[i].value = it },
                    singleLine = true,
                    label = { Text(localizedString("mobile.accord_bless_ci_ed25519_label")) },
                    modifier = Modifier.fillMaxWidth().testable("input_ci_ed25519_${w.keyId}"),
                )
                Spacer(Modifier.height(4.dp))
                OutlinedTextField(
                    value = mlStates[i].value,
                    onValueChange = { mlStates[i].value = it },
                    singleLine = false,
                    label = { Text(localizedString("mobile.accord_bless_ci_mldsa_label")) },
                    modifier = Modifier.fillMaxWidth().testable("input_ci_mldsa_${w.keyId}"),
                )
                Spacer(Modifier.height(12.dp))
            }
        },
        onSubmit = { holderKeyId, usbPath, pin, modulePath ->
            val targets = CI_WORKER_DEFAULTS.mapIndexedNotNull { i, w ->
                val ed = edStates[i].value.trim()
                val ml = mlStates[i].value.trim()
                if (ed.isNotBlank() && ml.isNotBlank()) {
                    CiKeyTargetInput(
                        keyId = w.keyId,
                        pubkeyEd25519Base64 = ed,
                        pubkeyMlDsa65Base64 = ml,
                        identityType = "node",
                    )
                } else {
                    null
                }
            }
            viewModel.proposeCiKeys(holderKeyId, usbPath, pin, targets, modulePath)
            onDismiss()
        },
        onDismiss = onDismiss,
    )
}

/**
 * **Portable mesh-genesis seed** — the seed ceremony (FSD/MESH_GENESIS.md). Two
 * accord holders (real people, one YubiKey each) turn the EXISTING roster plus one
 * canonical serve node into a portable trust-root seed, pre-filled from
 * `GET /v1/accord/genesis/remint-source` so nothing is retyped and no key material —
 * and no quorum number — is invented. Three steps, one sheet:
 *   1. **Review** — the roster, the serve node, the address, and the server's own
 *      quorum. Nothing is signed; this is where a human checks what the seed carries.
 *   2. **Propose** — the FIRST holder mints and signs the charter + grant
 *      (`AccordViewModel.proposeGenesis`). The returned bundle is HELD VERBATIM.
 *   3. **Cosign** — the SECOND holder authorizes the SAME bundle
 *      (`AccordViewModel.cosignGenesis`), repeated until the server says `complete`.
 * Then the seed is offered Save (`mesh-genesis.json`) / Copy, with its fingerprint
 * to compare out of band before anyone attaches it.
 *
 * Multi-step with two DIFFERENT people signing, so it embeds [HolderSignInputs]
 * directly — twice, one set of hardware inputs per holder — rather than
 * [HardwareScrubSheet]'s single submit. The ceremony state lives in the ViewModel,
 * so closing and reopening the sheet resumes a half-authorized seed.
 */
@Composable
private fun RemintTrustRootSheet(
    viewModel: AccordViewModel,
    holders: List<AccordHolderDto>,
    busy: Boolean,
    onDismiss: () -> Unit,
) {
    val source by viewModel.remintSource.collectAsState()
    val seed by viewModel.genesisSeed.collectAsState()
    val clipboard = LocalClipboardManager.current
    val saveScope = rememberCoroutineScope()

    // On open: pull the pre-fill roster (holders + canonicals + the server's quorum).
    LaunchedEffect(Unit) { viewModel.loadRemintSource() }

    // Where the ceremony is. Resumable: reopening on a half-authorized seed lands on
    // the cosign step rather than making the operator walk the review again.
    var step by remember {
        mutableStateOf(if (viewModel.genesisSeed.value != null) REMINT_STEP_COSIGN else REMINT_STEP_REVIEW)
    }
    // Propose lands the first authorization → advance to cosign.
    LaunchedEffect(seed) {
        if (seed != null && step == REMINT_STEP_PROPOSE) step = REMINT_STEP_COSIGN
    }

    // Canonical selector — DEFAULTS to the first canonical (canonical-server-1).
    var selectedKeyId by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(source) {
        if (selectedKeyId == null) selectedKeyId = source?.canonicals?.firstOrNull()?.keyId
    }
    val selected = source?.canonicals?.firstOrNull { it.keyId == selectedKeyId }

    // The ip hint baked into the selected canonical's record — seeded, editable.
    var ip by remember(selected?.keyId) {
        mutableStateOf(selected?.transportHints?.firstOrNull { it.kind == "ip" }?.destination.orEmpty())
    }

    // The ceremony roster: the re-mint source's holders when it has them (that IS the
    // roster the seed carries), else the node's accord roster.
    val ceremonyHolders = remember(source, holders) {
        val fromSource = source?.holders.orEmpty().map {
            AccordHolderDto(
                keyId = it.keyId,
                pubkeyEd25519Base64 = it.pubkeyEd25519Base64,
                pubkeyMlDsa65Base64 = it.pubkeyMlDsa65Base64,
            )
        }
        fromSource.ifEmpty { holders }
    }

    // TWO holders, TWO YubiKeys, TWO PINs — never one set of inputs reused, so the
    // second person never inherits the first person's PIN in a field.
    var proposeHolder by remember { mutableStateOf("") }
    var proposeUsb by remember { mutableStateOf("") }
    var proposePin by remember { mutableStateOf("") }
    var proposeModule by remember { mutableStateOf("") }
    LaunchedEffect(ceremonyHolders) {
        if (proposeHolder.isBlank()) proposeHolder = ceremonyHolders.firstOrNull()?.keyId.orEmpty()
    }
    var cosignHolder by remember { mutableStateOf("") }
    var cosignUsb by remember { mutableStateOf("") }
    var cosignPin by remember { mutableStateOf("") }
    var cosignModule by remember { mutableStateOf("") }

    // The server rejects a holder who already authorized this bundle — so don't offer
    // one. What remains defaults the picker to the next un-signed holder.
    val remainingHolders = ceremonyHolders.filter { it.keyId !in seed?.authorizedKeyIds.orEmpty() }
    LaunchedEffect(remainingHolders) {
        if (cosignHolder.isBlank() || cosignHolder !in remainingHolders.map { h -> h.keyId }) {
            cosignHolder = remainingHolders.firstOrNull()?.keyId.orEmpty()
        }
    }

    var canonicalMenu by remember { mutableStateOf(false) }
    var bundleSaveDir by remember { mutableStateOf<String?>(null) }

    val complete = seed?.complete == true
    val display = seed?.let { genesisSeedDisplay(it.bundle) }

    val reviewReady = selected != null
    val proposeReady = proposeHolder.isNotBlank() && proposeUsb.isNotBlank() &&
        proposePin.isNotBlank() && selected != null && !busy
    val cosignReady = cosignHolder.isNotBlank() && cosignUsb.isNotBlank() &&
        cosignPin.isNotBlank() && seed != null && !busy

    val doPropose = {
        selected?.let { sel ->
            viewModel.proposeGenesis(
                proposeHolder, proposeUsb, proposePin.ifBlank { null },
                sel.keyId, ip.ifBlank { null }, proposeModule.ifBlank { null },
            )
        }
        Unit
    }
    val doCosign = {
        viewModel.cosignGenesis(
            cosignHolder, cosignUsb, cosignPin.ifBlank { null }, cosignModule.ifBlank { null },
        )
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(localizedString("mobile.accord_remint_title")) },
        text = {
            Column(
                modifier = Modifier
                    .heightIn(max = 460.dp)
                    .verticalScroll(rememberScrollState())
                    .testable("sheet_remint_trust_root"),
            ) {
                Text(
                    localizedString("mobile.accord_remint_desc"),
                    fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(6.dp))
                Text(
                    if (complete) {
                        localizedString("mobile.accord_remint_step_done")
                    } else {
                        localizedString(
                            "mobile.accord_remint_step_of",
                            mapOf("step" to step.toString(), "total" to REMINT_STEP_COUNT.toString()),
                        )
                    },
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSurface,
                    modifier = Modifier.testable("remint_step_indicator"),
                )
                Spacer(Modifier.height(10.dp))

                when {
                    // ── Done — the authorized, portable seed ──
                    complete -> {
                        Text(
                            localizedString("mobile.accord_remint_done_title"),
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onSurface,
                            modifier = Modifier.testable("remint_done_title"),
                        )
                        Text(
                            localizedString("mobile.accord_remint_done_desc"),
                            fontSize = 11.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Spacer(Modifier.height(8.dp))
                        seed?.let { s ->
                            Text(
                                remintTallyText(s.authorizationsHave, s.authorizationsNeeded),
                                fontSize = 11.sp,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                modifier = Modifier.testable("remint_auth_tally"),
                            )
                            if (s.serveNodeReblessed) {
                                Spacer(Modifier.height(6.dp))
                                Text(
                                    localizedString("mobile.accord_remint_reblessed_note"),
                                    fontSize = 11.sp,
                                    color = MaterialTheme.colorScheme.primary,
                                    modifier = Modifier.testable("remint_reblessed_note"),
                                )
                            }
                        }
                        display?.let { d ->
                            Spacer(Modifier.height(6.dp))
                            Text(
                                localizedString("mobile.accord_remint_done_family", "key", d.familyKeyId),
                                fontSize = 11.sp,
                                fontFamily = FontFamily.Monospace,
                                color = MaterialTheme.colorScheme.onSurface,
                                modifier = Modifier.testable("remint_done_family"),
                            )
                            Text(
                                localizedString(
                                    "mobile.accord_remint_done_holders",
                                    "count",
                                    d.holderCount.toString(),
                                ),
                                fontSize = 11.sp,
                                color = MaterialTheme.colorScheme.onSurface,
                                modifier = Modifier.testable("remint_done_holders"),
                            )
                            Text(
                                localizedString(
                                    "mobile.accord_remint_done_serve_nodes",
                                    "count",
                                    d.serveNodeCount.toString(),
                                ),
                                fontSize = 11.sp,
                                color = MaterialTheme.colorScheme.onSurface,
                                modifier = Modifier.testable("remint_done_serve_nodes"),
                            )
                            // Only when the bundle actually carries one — never invented.
                            d.fingerprint?.let { fp ->
                                Spacer(Modifier.height(6.dp))
                                Text(
                                    localizedString("mobile.accord_remint_done_fingerprint", "fingerprint", fp),
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Bold,
                                    fontFamily = FontFamily.Monospace,
                                    color = MaterialTheme.colorScheme.onSurface,
                                    modifier = Modifier.testable("remint_done_fingerprint"),
                                )
                                Text(
                                    localizedString("mobile.accord_remint_done_fingerprint_caption"),
                                    fontSize = 11.sp,
                                    color = MaterialTheme.colorScheme.error,
                                    modifier = Modifier.testable("remint_done_fingerprint_caption"),
                                )
                            }
                        }
                        Spacer(Modifier.height(10.dp))
                        Text(
                            localizedString("mobile.accord_remint_bundle_ready"),
                            fontSize = 11.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.testable("remint_bundle_ready"),
                        )
                        seed?.prettyJson?.let { json ->
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                TextButton(
                                    onClick = { clipboard.setText(AnnotatedString(json)) },
                                    modifier = Modifier.testableClickable("btn_remint_copy_bundle") {
                                        clipboard.setText(AnnotatedString(json))
                                    },
                                ) { Text(localizedString("mobile.accord_op_copy")) }
                                TextButton(
                                    onClick = { bundleSaveDir = "" },
                                    modifier = Modifier.testableClickable("btn_remint_save_bundle") {
                                        bundleSaveDir = ""
                                    },
                                ) { Text(localizedString("mobile.accord_remint_save_bundle")) }
                            }
                        }
                        // Deliberately NOT automatic: an authorized seed is only
                        // dropped when a human says so, never by closing the sheet.
                        TextButton(
                            onClick = {
                                viewModel.clearGenesisSeed()
                                step = REMINT_STEP_REVIEW
                            },
                            modifier = Modifier.testableClickable("btn_remint_start_over") {
                                viewModel.clearGenesisSeed()
                                step = REMINT_STEP_REVIEW
                            },
                        ) { Text(localizedString("mobile.accord_remint_start_over_btn")) }
                    }

                    // ── Step 1 — Review ──
                    step == REMINT_STEP_REVIEW -> {
                        Text(
                            localizedString("mobile.accord_remint_review_title"),
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onSurface,
                        )
                        Text(
                            localizedString("mobile.accord_remint_seed_scope"),
                            fontSize = 11.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Spacer(Modifier.height(10.dp))

                        // The holder roster (read-only; the FULL roster rides the seed).
                        Text(
                            localizedString("mobile.accord_remint_roster_title"),
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onSurface,
                        )
                        Spacer(Modifier.height(4.dp))
                        val roster = source?.holders.orEmpty()
                        if (roster.isEmpty()) {
                            Text(
                                localizedString("mobile.accord_remint_roster_empty"),
                                fontSize = 11.sp,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                modifier = Modifier.testable("remint_roster_empty"),
                            )
                        } else {
                            roster.forEach { h ->
                                Text(
                                    "${h.keyId}  ${truncatedPubkey(h.pubkeyEd25519Base64)}",
                                    fontSize = 11.sp,
                                    fontFamily = FontFamily.Monospace,
                                    color = MaterialTheme.colorScheme.onSurface,
                                    modifier = Modifier.testable("remint_holder_${h.keyId}"),
                                )
                            }
                        }
                        Spacer(Modifier.height(4.dp))
                        // The quorum as the SERVER renders it — "?" when it hasn't said.
                        Text(
                            localizedString(
                                "mobile.accord_remint_quorum_line",
                                mapOf(
                                    "m" to remintQuorumPart(source?.quorumM),
                                    "n" to remintQuorumPart(source?.quorumN),
                                ),
                            ),
                            fontSize = 11.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.testable("remint_quorum_line"),
                        )
                        Spacer(Modifier.height(10.dp))

                        // The canonical serve node the seed will carry.
                        Box(modifier = Modifier.fillMaxWidth()) {
                            OutlinedButton(
                                onClick = { canonicalMenu = true },
                                modifier = Modifier.fillMaxWidth().testable("dd_remint_canonical"),
                            ) {
                                Text(selected?.keyId ?: localizedString("mobile.accord_remint_canonical_select"))
                            }
                            DropdownMenu(
                                expanded = canonicalMenu,
                                onDismissRequest = { canonicalMenu = false },
                            ) {
                                val canonicals = source?.canonicals.orEmpty()
                                if (canonicals.isEmpty()) {
                                    DropdownMenuItem(
                                        text = { Text(localizedString("mobile.accord_remint_no_canonicals")) },
                                        onClick = { canonicalMenu = false },
                                    )
                                }
                                canonicals.forEach { c ->
                                    DropdownMenuItem(
                                        text = { Text(c.keyId, fontFamily = FontFamily.Monospace) },
                                        onClick = { selectedKeyId = c.keyId; canonicalMenu = false },
                                        modifier = Modifier.testableClickable("remint_canonical_${c.keyId}") {
                                            selectedKeyId = c.keyId; canonicalMenu = false
                                        },
                                    )
                                }
                            }
                        }
                        selected?.let { sel ->
                            Spacer(Modifier.height(4.dp))
                            // The serve badge — `false` is exactly what this seed fixes.
                            Text(
                                localizedString(
                                    if (sel.confersInfraServe) "mobile.accord_remint_serve_ok"
                                    else "mobile.accord_remint_serve_missing",
                                ),
                                fontSize = 11.sp,
                                color = if (sel.confersInfraServe) MaterialTheme.colorScheme.onSurfaceVariant
                                else MaterialTheme.colorScheme.error,
                                modifier = Modifier.testable("remint_serve_state_${sel.keyId}"),
                            )
                        }
                        Spacer(Modifier.height(6.dp))
                        OutlinedTextField(
                            value = ip,
                            onValueChange = { ip = it },
                            singleLine = true,
                            label = { Text(localizedString("mobile.accord_canonical_ip_label")) },
                            modifier = Modifier.fillMaxWidth().testable("input_remint_ip"),
                        )
                        Spacer(Modifier.height(10.dp))
                        Button(
                            onClick = { step = REMINT_STEP_PROPOSE },
                            enabled = reviewReady,
                            modifier = Modifier.fillMaxWidth().testableClickable("btn_remint_continue") {
                                if (reviewReady) step = REMINT_STEP_PROPOSE
                            },
                        ) { Text(localizedString("mobile.accord_remint_continue_btn")) }
                    }

                    // ── Step 2 — Propose (the first holder) ──
                    step == REMINT_STEP_PROPOSE -> {
                        Text(
                            localizedString("mobile.accord_remint_propose_title"),
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onSurface,
                        )
                        Text(
                            localizedString("mobile.accord_remint_propose_desc"),
                            fontSize = 11.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Spacer(Modifier.height(4.dp))
                        Text(
                            localizedString(
                                "mobile.accord_remint_serve_node_line",
                                "key",
                                selected?.keyId.orEmpty(),
                            ),
                            fontSize = 11.sp,
                            fontFamily = FontFamily.Monospace,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.testable("remint_propose_serve_node"),
                        )
                        Spacer(Modifier.height(10.dp))
                        HolderSignInputs(
                            holders = ceremonyHolders,
                            holderKeyId = proposeHolder,
                            onHolder = { proposeHolder = it },
                            usbPath = proposeUsb,
                            onUsb = { proposeUsb = it },
                            pin = proposePin,
                            onPin = { proposePin = it },
                            tagPrefix = "remint_propose",
                        )
                        Spacer(Modifier.height(6.dp))
                        OutlinedTextField(
                            value = proposeModule,
                            onValueChange = { proposeModule = it },
                            singleLine = true,
                            label = { Text(localizedString("mobile.accord_scrub_module_label")) },
                            placeholder = { Text(localizedString("mobile.accord_scrub_module_hint")) },
                            modifier = Modifier.fillMaxWidth().testable("input_scrub_module_remint_propose"),
                        )
                        Spacer(Modifier.height(10.dp))
                        Button(
                            onClick = doPropose,
                            enabled = proposeReady,
                            modifier = Modifier.fillMaxWidth().testableClickable("btn_remint_propose") {
                                if (proposeReady) doPropose()
                            },
                        ) {
                            Text(
                                if (busy) localizedString("mobile.accord_remint_propose_btn_busy")
                                else localizedString("mobile.accord_remint_propose_btn"),
                            )
                        }
                        Spacer(Modifier.height(4.dp))
                        TextButton(
                            onClick = { step = REMINT_STEP_REVIEW },
                            modifier = Modifier.fillMaxWidth().testableClickable("btn_remint_back_review") {
                                step = REMINT_STEP_REVIEW
                            },
                        ) { Text(localizedString("mobile.accord_remint_back_btn")) }
                    }

                    // ── Step 3 — Cosign (the second holder) ──
                    else -> {
                        Text(
                            localizedString("mobile.accord_remint_cosign_title"),
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onSurface,
                        )
                        Text(
                            localizedString("mobile.accord_remint_cosign_desc"),
                            fontSize = 11.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Spacer(Modifier.height(6.dp))
                        seed?.let { s ->
                            Text(
                                remintTallyText(s.authorizationsHave, s.authorizationsNeeded),
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.onSurface,
                                modifier = Modifier.testable("remint_auth_tally"),
                            )
                        }
                        Spacer(Modifier.height(10.dp))
                        if (remainingHolders.isEmpty()) {
                            Text(
                                localizedString("mobile.accord_remint_cosign_all_signed"),
                                fontSize = 11.sp,
                                color = MaterialTheme.colorScheme.error,
                                modifier = Modifier.testable("remint_cosign_all_signed"),
                            )
                        } else {
                            HolderSignInputs(
                                holders = remainingHolders,
                                holderKeyId = cosignHolder,
                                onHolder = { cosignHolder = it },
                                usbPath = cosignUsb,
                                onUsb = { cosignUsb = it },
                                pin = cosignPin,
                                onPin = { cosignPin = it },
                                tagPrefix = "remint_cosign",
                            )
                            Spacer(Modifier.height(6.dp))
                            OutlinedTextField(
                                value = cosignModule,
                                onValueChange = { cosignModule = it },
                                singleLine = true,
                                label = { Text(localizedString("mobile.accord_scrub_module_label")) },
                                placeholder = { Text(localizedString("mobile.accord_scrub_module_hint")) },
                                modifier = Modifier.fillMaxWidth().testable("input_scrub_module_remint_cosign"),
                            )
                            Spacer(Modifier.height(10.dp))
                            Button(
                                onClick = doCosign,
                                enabled = cosignReady,
                                modifier = Modifier.fillMaxWidth().testableClickable("btn_remint_cosign") {
                                    if (cosignReady) doCosign()
                                },
                            ) {
                                Text(
                                    if (busy) localizedString("mobile.accord_remint_cosign_btn_busy")
                                    else localizedString("mobile.accord_remint_cosign_btn"),
                                )
                            }
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = onDismiss,
                modifier = Modifier.testableClickable("btn_remint_close") { onDismiss() },
            ) { Text(localizedString("mobile.accord_remint_close_btn")) }
        },
    )

    // Save flow: pick a folder, then write the portable seed into it (mirrors the
    // screen's co-scrub partial save).
    DirectoryPickerDialog(
        show = bundleSaveDir == "",
        onDirectoryPicked = { dir ->
            bundleSaveDir = null
            val json = seed?.prettyJson
            if (json != null) {
                saveScope.launch {
                    val ok = writeTextFile(dir, "mesh-genesis.json", json)
                    viewModel.setExternalNotice(
                        if (ok) "Saved the genesis seed to $dir."
                        else "Couldn't save to $dir (this platform may not support file writes).",
                        error = !ok,
                    )
                }
            }
        },
        onDismiss = { bundleSaveDir = null },
    )
}

/** The seed ceremony's steps: review → propose → cosign. */
private const val REMINT_STEP_REVIEW = 1
private const val REMINT_STEP_PROPOSE = 2
private const val REMINT_STEP_COSIGN = 3
private const val REMINT_STEP_COUNT = 3

/**
 * One half of the quorum as the SERVER rendered it — `?` when the node hasn't said
 * (0 = UNKNOWN). NEVER a guessed number: this tells an operator how many humans to
 * bring to a ceremony, and a wrong guess is worse than an honest "?".
 */
private fun remintQuorumPart(value: Int?): String =
    value?.takeIf { it > 0 }?.toString() ?: "?"

/** `key_id` plus a truncated pubkey — enough to recognize a holder, not to retype one. */
private fun truncatedPubkey(pubkey: String?): String {
    val key = pubkey.orEmpty()
    return if (key.length <= 16) key else key.take(16) + "…"
}

/** The running authorization tally, `?` for a count the server hasn't stated. */
@Composable
private fun remintTallyText(have: Int, needed: Int): String = localizedString(
    "mobile.accord_remint_auth_tally",
    mapOf(
        "have" to have.toString(),
        "needed" to remintQuorumPart(needed),
    ),
)

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
