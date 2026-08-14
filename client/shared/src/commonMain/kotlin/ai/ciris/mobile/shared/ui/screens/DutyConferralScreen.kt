package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.platform.DirectoryPickerDialog
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.components.HolderSignInputs
import ai.ciris.mobile.shared.ui.screens.YubiKeyStatusBanner
import ai.ciris.mobile.shared.viewmodels.DutyConferralViewModel
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
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * **Delegate moderation duty** — confer `slash` / `moderate` / `review` on another
 * self, and say in ONE control how far they may pass it on.
 *
 * The two axes of sub-delegation ("may they delegate at all?" and "how many further
 * hops?") are a single dropdown on purpose: they are one decision, and splitting
 * them into a switch plus a number is how a conferral ends up saying "may not
 * delegate, depth 3". Every option is on the menu — nothing is hidden behind an
 * "advanced" toggle, because the operator is choosing how far their own authority
 * travels.
 *
 * The conferral is a co-scrub: [DutyConferralViewModel.propose] mints scrub #1 and
 * the resulting opaque partial needs `quorum_needed` distinct holder scrubs before
 * it takes effect. The app holds NO keys — the LOCAL node opens the holder's
 * YubiKey + USB ML-DSA and signs.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DutyConferralScreen(
    viewModel: DutyConferralViewModel,
    onBack: () -> Unit,
) {
    val subjectKeyId by viewModel.subjectKeyId.collectAsState()
    val duties by viewModel.duties.collectAsState()
    val subDelegation by viewModel.subDelegation.collectAsState()
    val subDelegationDepth by viewModel.subDelegationDepth.collectAsState()
    val holderKeyId by viewModel.holderKeyId.collectAsState()
    val usbPath by viewModel.usbPath.collectAsState()
    val userPin by viewModel.userPin.collectAsState()
    val holders by viewModel.holders.collectAsState()
    val yubiKeyStatus by viewModel.yubiKeyStatus.collectAsState()
    val partial by viewModel.partial.collectAsState()
    val scrubCount by viewModel.scrubCount.collectAsState()
    val quorumNeeded by viewModel.quorumNeeded.collectAsState()
    val adopted by viewModel.adopted.collectAsState()
    val conferred by viewModel.conferred.collectAsState()
    val inProgress by viewModel.inProgress.collectAsState()
    val error by viewModel.error.collectAsState()

    // The conferring authority, read live from the node (never a client constant).
    val sourceFamilyKeyId by viewModel.sourceFamilyKeyId.collectAsState()
    val sourceFamilyName by viewModel.sourceFamilyName.collectAsState()
    val sourceConsensus by viewModel.sourceConsensus.collectAsState()
    val sourceEntrenched by viewModel.sourceEntrenched.collectAsState()
    val sourceSeats by viewModel.sourceSeats.collectAsState()
    val sourceError by viewModel.sourceError.collectAsState()

    LaunchedEffect(Unit) { viewModel.load() }

    var showUsbPicker by remember { mutableStateOf(false) }
    var depthExpanded by remember { mutableStateOf(false) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("duty.title")) },
                navigationIcon = {
                    IconButton(
                        onClick = onBack,
                        modifier = Modifier.testableClickable("btn_duty_back") { onBack() },
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
                localizedString("duty.subtitle"),
                fontSize = 13.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            // ── The error, first and loud ─────────────────────────────────────
            error?.let { msg ->
                Spacer(Modifier.height(12.dp))
                Surface(
                    shape = RoundedCornerShape(10.dp),
                    color = MaterialTheme.colorScheme.errorContainer,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(
                            CIRISIcons.warning,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.onErrorContainer,
                            modifier = Modifier.size(18.dp),
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(
                            msg,
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onErrorContainer,
                            modifier = Modifier.weight(1f).testable("duty_error"),
                        )
                    }
                }
            }

            // Token readiness FIRST — the ceremony cannot start without it, and
            // finding out from a failed signature wastes both holders' time.
            Spacer(Modifier.height(12.dp))
            YubiKeyStatusBanner(yubiKeyStatus) { viewModel.refreshYubiKeyStatus() }

            // ── WHO IS CONFERRING — the source of the authority ────────────────
            //
            // First on the card, before anything the operator fills in, because it
            // is the one fact they cannot change and the one that makes the rest
            // mean anything. Two holders are about to sign a constitutional act;
            // the card must say on whose behalf.
            Spacer(Modifier.height(12.dp))
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = MaterialTheme.colorScheme.surfaceVariant,
                modifier = Modifier.fillMaxWidth().testable("duty_source_card"),
            ) {
                Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
                    SectionHeader(CIRISIcons.shield, localizedString("duty.section_source"))
                    when {
                        // Could not ASK is not the same as "no accord" — say which.
                        sourceError != null -> Text(
                            localizedString("duty.source_unreadable", "error", sourceError ?: ""),
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.error,
                            modifier = Modifier.testable("duty_source_error"),
                        )
                        sourceFamilyKeyId == null -> Text(
                            localizedString("duty.source_loading"),
                            fontSize = 13.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        else -> {
                            Text(
                                sourceFamilyName ?: sourceFamilyKeyId.orEmpty(),
                                fontSize = 16.sp,
                                fontWeight = FontWeight.Bold,
                                modifier = Modifier.testable("duty_source_name"),
                            )
                            Text(
                                sourceFamilyKeyId.orEmpty(),
                                fontSize = 12.sp,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                modifier = Modifier.testable("duty_source_key_id"),
                            )
                            Spacer(Modifier.height(6.dp))
                            // The accord's own quorum string, verbatim.
                            Text(
                                localizedString(
                                    if (sourceEntrenched) "duty.source_quorum_entrenched"
                                    else "duty.source_quorum",
                                    "quorum",
                                    sourceConsensus.orEmpty(),
                                ),
                                fontSize = 13.sp,
                                modifier = Modifier.testable("duty_source_quorum"),
                            )
                            Spacer(Modifier.height(6.dp))
                            Text(
                                localizedString(
                                    "duty.source_seats",
                                    mapOf(
                                        "count" to sourceSeats.size.toString(),
                                        "seats" to sourceSeats.joinToString(", "),
                                    ),
                                ),
                                fontSize = 12.sp,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                modifier = Modifier.testable("duty_source_seats"),
                            )
                            Spacer(Modifier.height(8.dp))
                            Text(
                                localizedString("duty.source_explainer"),
                                fontSize = 12.sp,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }

            // ── The conferral ─────────────────────────────────────────────────
            Spacer(Modifier.height(12.dp))
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = MaterialTheme.colorScheme.surfaceVariant,
                modifier = Modifier.fillMaxWidth().testable("duty_conferral_card"),
            ) {
                Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
                    SectionHeader(CIRISIcons.shield, localizedString("duty.section_conferral"))

                    OutlinedTextField(
                        value = subjectKeyId,
                        onValueChange = { viewModel.setSubjectKeyId(it) },
                        singleLine = true,
                        enabled = !inProgress,
                        label = { Text(localizedString("duty.subject_label")) },
                        placeholder = { Text(localizedString("duty.subject_placeholder")) },
                        modifier = Modifier.fillMaxWidth().testable("input_duty_subject"),
                    )

                    // ── DUTIES — a SET, not a choice ──────────────────────────
                    //
                    // persist admits `scope` as an array with set-containment, so
                    // one grant carries as many duties as the accord means to give.
                    // A single-select dropdown here forced one ceremony per duty —
                    // two humans and two YubiKey touches to say something the wire
                    // could always have carried in one row.
                    Spacer(Modifier.height(12.dp))
                    Text(
                        localizedString("duty.verbs_label"),
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        localizedString("duty.verbs_help"),
                        fontSize = 11.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Spacer(Modifier.height(4.dp))
                    DutyConferralViewModel.ALL_DUTIES.forEach { verb ->
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier
                                .fillMaxWidth()
                                .testableClickable("chk_duty_$verb") {
                                    if (!inProgress) viewModel.toggleDuty(verb)
                                },
                        ) {
                            Checkbox(
                                checked = verb in duties,
                                onCheckedChange = { if (!inProgress) viewModel.toggleDuty(verb) },
                                enabled = !inProgress,
                                modifier = Modifier.testable("chk_duty_box_$verb"),
                            )
                            Text(
                                localizedString("duty.verb_$verb"),
                                fontSize = 12.sp,
                                modifier = Modifier.weight(1f),
                            )
                        }
                    }
                    if (duties.isEmpty()) {
                        Text(
                            localizedString("duty.verbs_none"),
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.error,
                            modifier = Modifier.testable("duty_verbs_none"),
                        )
                    }

                    // ── What the selection actually unlocks ───────────────────
                    //
                    // The scope names do not say what they DO. This maps the
                    // selection onto the enforcement ladder's own rungs, so the
                    // operator signs knowing which doors open — the difference
                    // between "grant slash" and "grant the authority to de-admit".
                    val rungs = ladderRungsFor(duties)
                    Spacer(Modifier.height(10.dp))
                    Text(
                        localizedString("duty.ladder_label"),
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    if (rungs.isEmpty()) {
                        Text(
                            localizedString("duty.ladder_none"),
                            fontSize = 12.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.testable("duty_ladder_none"),
                        )
                    } else {
                        rungs.forEach { rungKey ->
                            Text(
                                "• " + localizedString(rungKey),
                                fontSize = 12.sp,
                                modifier = Modifier.testable("duty_ladder_$rungKey"),
                            )
                        }
                        Spacer(Modifier.height(2.dp))
                        Text(
                            localizedString("duty.ladder_note"),
                            fontSize = 11.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }

                    // ── Delegation depth (both axes, one control) ─────────────
                    Spacer(Modifier.height(12.dp))
                    val selected = DEPTH_OPTIONS.firstOrNull {
                        it.subDelegation == subDelegation && it.depth == subDelegationDepth
                    } ?: DEPTH_OPTIONS.first()
                    ExposedDropdownMenuBox(
                        expanded = depthExpanded,
                        onExpandedChange = { depthExpanded = it },
                    ) {
                        OutlinedTextField(
                            value = localizedString(selected.labelKey),
                            onValueChange = {},
                            readOnly = true,
                            enabled = !inProgress,
                            label = { Text(localizedString("duty.depth_label")) },
                            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = depthExpanded) },
                            modifier = Modifier
                                .fillMaxWidth()
                                .menuAnchor()
                                .testableClickable("input_duty_depth") { depthExpanded = !depthExpanded },
                        )
                        ExposedDropdownMenu(
                            expanded = depthExpanded,
                            onDismissRequest = { depthExpanded = false },
                        ) {
                            DEPTH_OPTIONS.forEach { option ->
                                DropdownMenuItem(
                                    text = { Text(localizedString(option.labelKey)) },
                                    onClick = {
                                        viewModel.setDelegationDepth(option.subDelegation, option.depth)
                                        depthExpanded = false
                                    },
                                    modifier = Modifier.testableClickable(option.testTag) {
                                        viewModel.setDelegationDepth(option.subDelegation, option.depth)
                                        depthExpanded = false
                                    },
                                )
                            }
                        }
                    }
                    Spacer(Modifier.height(4.dp))
                    Text(
                        localizedString("duty.depth_help"),
                        fontSize = 11.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            // ── The signing holder ────────────────────────────────────────────
            Spacer(Modifier.height(16.dp))
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = MaterialTheme.colorScheme.surfaceVariant,
                modifier = Modifier.fillMaxWidth().testable("duty_holder_card"),
            ) {
                Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
                    SectionHeader(CIRISIcons.keySecure, localizedString("duty.section_holder"))
                    Text(
                        localizedString("duty.holder_desc"),
                        fontSize = 12.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Spacer(Modifier.height(8.dp))
                    // The SHARED holder inputs every accord ceremony uses:
                    // holder picked from the node's own registry, USB browsed, PIN
                    // masked with a reveal toggle.
                    //
                    // This card hand-rolled a free-text `key_id` box and a bare USB
                    // field, and had NO PIN AT ALL — so every propose reached the
                    // node with `pkcs11: null` and failed at the token
                    // (`accord.duty.holder_custody`). It could not have worked for
                    // anyone. Re-using the component is also what keeps the holder
                    // list honest: it is the node's registry, the same source the
                    // quorum is counted from, not a string the operator remembered.
                    HolderSignInputs(
                        holders = holders,
                        holderKeyId = holderKeyId,
                        onHolder = { viewModel.setHolderKeyId(it) },
                        usbPath = usbPath,
                        onUsb = { viewModel.setUsbPath(it) },
                        pin = userPin,
                        onPin = { viewModel.setUserPin(it) },
                        tagPrefix = "duty",
                    )
                }
            }

            // ── Propose / cosign ──────────────────────────────────────────────
            Spacer(Modifier.height(16.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Button(
                    onClick = { viewModel.propose() },
                    enabled = !inProgress,
                    modifier = Modifier.testableClickable("btn_duty_propose") { viewModel.propose() },
                ) {
                    Text(localizedString("duty.propose_button"))
                }
                Spacer(Modifier.width(8.dp))
                OutlinedButton(
                    onClick = { viewModel.cosign() },
                    enabled = !inProgress && partial != null,
                    modifier = Modifier.testableClickable("btn_duty_cosign") { viewModel.cosign() },
                ) {
                    Text(localizedString("duty.cosign_button"))
                }
                if (inProgress) {
                    Spacer(Modifier.width(8.dp))
                    CircularProgressIndicator(modifier = Modifier.size(14.dp), strokeWidth = 2.dp)
                }
            }

            // ── Co-scrub progress ─────────────────────────────────────────────
            Spacer(Modifier.height(16.dp))
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = if (adopted) {
                    MaterialTheme.colorScheme.secondaryContainer
                } else {
                    MaterialTheme.colorScheme.surfaceVariant
                },
                modifier = Modifier.fillMaxWidth().testable("duty_status_card"),
            ) {
                Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
                    SectionHeader(CIRISIcons.identityDiamond, localizedString("duty.section_status"))
                    if (partial == null && scrubCount == 0) {
                        Text(
                            localizedString("duty.not_started"),
                            fontSize = 12.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.testable("duty_not_started"),
                        )
                    } else {
                        Text(
                            localizedString(
                                "duty.signatures",
                                mapOf("have" to scrubCount.toString(), "need" to quorumNeeded.toString()),
                            ),
                            fontSize = 15.sp,
                            fontWeight = FontWeight.Bold,
                            fontFamily = FontFamily.Monospace,
                            modifier = Modifier.testable("duty_scrub_count"),
                        )
                        Spacer(Modifier.height(6.dp))
                        if (adopted) {
                            Text(
                                localizedString("duty.adopted"),
                                fontSize = 13.sp,
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.onSecondaryContainer,
                                modifier = Modifier.testable("duty_adopted"),
                            )
                            // The node's own one-line read-back of the grant — what
                            // was signed, not what the form implied.
                            conferred?.let { line ->
                                Spacer(Modifier.height(4.dp))
                                Text(
                                    line,
                                    fontSize = 12.sp,
                                    fontFamily = FontFamily.Monospace,
                                    color = MaterialTheme.colorScheme.onSecondaryContainer,
                                    modifier = Modifier.testable("duty_conferred"),
                                )
                            }
                        } else {
                            Text(
                                localizedString("duty.pending_hint"),
                                fontSize = 12.sp,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                modifier = Modifier.testable("duty_pending"),
                            )
                        }
                    }
                }
            }

            Spacer(Modifier.height(24.dp))
        }
    }
}

/**
 * **Which enforcement-ladder rungs a duty set unlocks** — the node's own table,
 * from `src/admin_ops.rs`:
 *
 * ```text
 * preview        read-only    (no duty required)
 * tier 0  annotate            scope: review
 * tier 1  throttle            scope: moderate    (+ un_throttle)
 * tier 2  quarantine          scope: moderate*   (+ un_quarantine)
 * tier 3  descend             scope: slash + QUORUM
 * tier 4  deadmit             scope: slash       (+ re_admit)
 * tier 4  refuse-writes       scope: slash       (+ accept_writes)
 * ```
 *
 * `*` tier 2 is the one documented disagreement: the FSD ladder says `moderate`,
 * persist's admission door says `slash`. The substrate wins, so tier 2 is listed
 * under `slash` here — showing it under `moderate` would promise a rung the gate
 * refuses, which is worse than not showing it.
 *
 * `consent_revocation` and `takedown` unlock NO ladder rung: they authorize
 * emitting (a revocation, a takedown notice), not enforcing. That is a real and
 * useful distinction for the operator to see at signing time, so those duties
 * contribute nothing here rather than being quietly folded in.
 */
private fun ladderRungsFor(duties: Set<String>): List<String> {
    val out = mutableListOf<String>()
    if (DutyConferralViewModel.DUTY_REVIEW in duties) out += "duty.ladder_t0"
    if (DutyConferralViewModel.DUTY_MODERATE in duties) out += "duty.ladder_t1"
    if (DutyConferralViewModel.DUTY_SLASH in duties) {
        out += "duty.ladder_t2"
        out += "duty.ladder_t3"
        out += "duty.ladder_t4"
    }
    return out
}

/**
 * One delegation-depth choice — the (sub_delegation, depth) PAIR the node wants,
 * never two independently-settable controls. `depth = null` with sub-delegation on
 * means "bounded only by the global rail (5)".
 */
private data class DepthOption(
    val labelKey: String,
    val subDelegation: Boolean,
    val depth: Int?,
    val testTag: String,
)

/** Every option, always on the menu — nothing hidden behind "advanced". */
private val DEPTH_OPTIONS = listOf(
    DepthOption("duty.depth_leaf", false, null, "menu_duty_depth_leaf"),
    DepthOption("duty.depth_1", true, 1, "menu_duty_depth_1"),
    DepthOption("duty.depth_2", true, 2, "menu_duty_depth_2"),
    DepthOption("duty.depth_3", true, 3, "menu_duty_depth_3"),
    DepthOption("duty.depth_4", true, 4, "menu_duty_depth_4"),
    DepthOption("duty.depth_5", true, 5, "menu_duty_depth_5"),
    DepthOption("duty.depth_unbounded", true, null, "menu_duty_depth_unbounded"),
)
