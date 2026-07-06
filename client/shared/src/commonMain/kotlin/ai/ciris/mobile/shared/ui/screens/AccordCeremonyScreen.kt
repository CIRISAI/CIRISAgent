package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.viewmodels.AccordCeremonyViewModel
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
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.TextButton
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.text.input.PasswordVisualTransformation
import ai.ciris.mobile.shared.models.federation.YubiKeyStatus
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * **Genesis ceremony** — the guided HUMANITY_ACCORD genesis wizard (CIRISServer
 * #41, the safe-mesh kill-switch floor). A foolproof multi-key flow so any founder
 * trio can stand up a NEW mesh's 2-of-3 human kill-switch without error.
 *
 * Phases (driven by [AccordCeremonyViewModel.Phase]):
 *   - INTRO     — the requirements (6 FIPS YubiKeys, 6 USB keys, 3 humans) + what
 *                 this creates (the 2-of-3 HUMAN accord-holder kill-switch; NOT a
 *                 node/mesh setup).
 *   - PROVISION — one key at a time (A1 → A2 → B1 → B2 → C1 → C2): collect the
 *                 holder's name + key_id + ML-DSA USB path, provision the YubiKey,
 *                 then register. Primaries are SEATs, spares are VAULT.
 *   - COSIGN    — each of the 3 PRIMARIES re-inserts + cosigns the family envelope.
 *   - DONE      — the assembled genesis (bake artifact) + the SAVE step.
 *
 * The app holds NO keys + does NO crypto: it only POSTs to the loopback endpoints;
 * the re-inserted YubiKey (PIN + touch) does all signing.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AccordCeremonyScreen(
    viewModel: AccordCeremonyViewModel,
    onBack: () -> Unit,
) {
    val phase by viewModel.phase.collectAsState()
    val busy by viewModel.busy.collectAsState()
    val error by viewModel.error.collectAsState()
    val notice by viewModel.notice.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("mobile.accord_ceremony_title")) },
                navigationIcon = {
                    IconButton(
                        onClick = onBack,
                        modifier = Modifier.testableClickable("btn_accord_ceremony_back") { onBack() },
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

            notice?.let { msg ->
                MessageCard(msg, MaterialTheme.colorScheme.secondaryContainer,
                    MaterialTheme.colorScheme.onSecondaryContainer, "accord_ceremony_notice")
            }
            error?.let { msg ->
                MessageCard(msg, MaterialTheme.colorScheme.errorContainer,
                    MaterialTheme.colorScheme.onErrorContainer, "accord_ceremony_error")
            }

            when (phase) {
                AccordCeremonyViewModel.Phase.INTRO -> IntroPhase(viewModel, busy)
                AccordCeremonyViewModel.Phase.PROVISION -> ProvisionPhase(viewModel, busy, error)
                AccordCeremonyViewModel.Phase.COSIGN -> CosignPhase(viewModel, busy, error)
                AccordCeremonyViewModel.Phase.DONE -> DonePhase(viewModel)
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun MessageCard(msg: String, container: androidx.compose.ui.graphics.Color, on: androidx.compose.ui.graphics.Color, tag: String) {
    Spacer(Modifier.height(8.dp))
    Surface(
        shape = RoundedCornerShape(10.dp),
        color = container,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(msg, fontSize = 12.sp, color = on, modifier = Modifier.padding(10.dp).testable(tag))
    }
}

// ── INTRO ─────────────────────────────────────────────────────────────────────

@Composable
private fun IntroPhase(viewModel: AccordCeremonyViewModel, busy: Boolean) {
    Spacer(Modifier.height(8.dp))
    Text(
        localizedString("mobile.accord_ceremony_intro_headline"),
        fontSize = 18.sp,
        fontWeight = FontWeight.Bold,
    )
    Spacer(Modifier.height(12.dp))
    Surface(
        shape = RoundedCornerShape(12.dp),
        color = MaterialTheme.colorScheme.primaryContainer,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.fillMaxWidth().padding(14.dp)) {
            Text(
                localizedString("mobile.accord_ceremony_intro_requirements"),
                fontSize = 15.sp,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onPrimaryContainer,
            )
        }
    }
    Spacer(Modifier.height(12.dp))
    Text(
        localizedString("mobile.accord_ceremony_intro_explainer"),
        fontSize = 13.sp,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    Spacer(Modifier.height(8.dp))
    Text(
        localizedString("mobile.accord_ceremony_intro_scope_note"),
        fontSize = 12.sp,
        fontWeight = FontWeight.Bold,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    Spacer(Modifier.height(20.dp))
    Button(
        onClick = { viewModel.begin() },
        enabled = !busy,
        modifier = Modifier.fillMaxWidth().testableClickable("btn_accord_ceremony_begin") { viewModel.begin() },
    ) {
        Icon(CIRISIcons.shield, contentDescription = null, modifier = Modifier.size(18.dp))
        Spacer(Modifier.width(8.dp))
        Text(localizedString("mobile.accord_ceremony_begin"))
    }
}

// ── PROVISION (one key at a time) ───────────────────────────────────────────────

@Composable
private fun ProvisionPhase(viewModel: AccordCeremonyViewModel, busy: Boolean, error: String?) {
    val slotIndex by viewModel.currentSlotIndex.collectAsState()
    val provisioned by viewModel.provisioned.collectAsState()
    val holderName by viewModel.holderName.collectAsState()
    val keyId by viewModel.keyId.collectAsState()
    val usbPath by viewModel.usbPath.collectAsState()
    val userPin by viewModel.userPin.collectAsState()
    val yubiKeyStatus by viewModel.yubiKeyStatus.collectAsState()
    LaunchedEffect(Unit) { viewModel.refreshYubiKeyStatus() }

    val slot = AccordCeremonyViewModel.KEY_SLOTS[slotIndex]
    val tierLabelKey = if (slot.primary) "mobile.accord_ceremony_tier_seat" else "mobile.accord_ceremony_tier_vault"

    Spacer(Modifier.height(8.dp))
    YubiKeyStatusBanner(yubiKeyStatus) { viewModel.refreshYubiKeyStatus() }
    Spacer(Modifier.height(8.dp))
    Text(
        localizedString("mobile.accord_ceremony_progress")
            .replace("{done}", provisioned.size.toString())
            .replace("{total}", AccordCeremonyViewModel.KEY_SLOTS.size.toString()),
        fontSize = 12.sp,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )

    // Roster-so-far chips (SEAT / VAULT).
    if (provisioned.isNotEmpty()) {
        Spacer(Modifier.height(8.dp))
        provisioned.forEach { p ->
            SlotRow(p.slot.label, p.holderName, p.slot.primary, done = true)
        }
    }

    Spacer(Modifier.height(16.dp))
    Row(verticalAlignment = Alignment.CenterVertically) {
        Surface(
            shape = RoundedCornerShape(8.dp),
            color = if (slot.primary) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.tertiary,
        ) {
            Text(
                slot.label,
                fontSize = 15.sp,
                fontWeight = FontWeight.Bold,
                fontFamily = FontFamily.Monospace,
                color = if (slot.primary) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onTertiary,
                modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
            )
        }
        Spacer(Modifier.width(8.dp))
        Text(
            localizedString(tierLabelKey),
            fontSize = 13.sp,
            fontWeight = FontWeight.Bold,
        )
    }
    Spacer(Modifier.height(4.dp))
    Text(
        localizedString(
            if (slot.primary) "mobile.accord_ceremony_seat_desc" else "mobile.accord_ceremony_vault_desc",
        ),
        fontSize = 12.sp,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )

    Spacer(Modifier.height(16.dp))
    OutlinedTextField(
        value = holderName,
        onValueChange = { viewModel.setHolderName(it) },
        singleLine = true,
        enabled = !busy,
        label = { Text(localizedString("mobile.accord_ceremony_holder_name_label")) },
        modifier = Modifier.fillMaxWidth().testable("input_ceremony_holder_name"),
    )
    Spacer(Modifier.height(10.dp))
    OutlinedTextField(
        value = keyId,
        onValueChange = { viewModel.setKeyId(it) },
        singleLine = true,
        enabled = !busy,
        label = { Text(localizedString("mobile.accord_ceremony_key_id_label")) },
        modifier = Modifier.fillMaxWidth().testable("input_ceremony_key_id"),
    )
    Spacer(Modifier.height(10.dp))
    OutlinedTextField(
        value = usbPath,
        onValueChange = { viewModel.setUsbPath(it) },
        singleLine = true,
        enabled = !busy,
        isError = error != null && usbPath.isBlank(),
        label = { Text(localizedString("mobile.accord_ceremony_usb_label")) },
        placeholder = { Text(localizedString("mobile.accord_ceremony_usb_placeholder")) },
        leadingIcon = { Icon(CIRISIcons.pkg, contentDescription = null, modifier = Modifier.size(18.dp)) },
        modifier = Modifier.fillMaxWidth().testable("input_ceremony_usb_path"),
    )
    Spacer(Modifier.height(10.dp))
    OutlinedTextField(
        value = userPin,
        onValueChange = { viewModel.setUserPin(it) },
        singleLine = true,
        enabled = !busy,
        visualTransformation = PasswordVisualTransformation(),
        label = { Text(localizedString("mobile.accord_ceremony_pin_label")) },
        modifier = Modifier.fillMaxWidth().testable("input_ceremony_pin"),
    )
    Text(
        localizedString("mobile.accord_ceremony_insert_note"),
        fontSize = 11.sp,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )

    Spacer(Modifier.height(20.dp))
    val canProvision = holderName.isNotBlank() && keyId.isNotBlank() && usbPath.isNotBlank() && !busy
    Button(
        onClick = { viewModel.provisionCurrent() },
        enabled = canProvision,
        modifier = Modifier.fillMaxWidth().testableClickable("btn_ceremony_provision") { viewModel.provisionCurrent() },
    ) {
        if (busy) {
            CircularProgressIndicator(modifier = Modifier.size(14.dp), strokeWidth = 2.dp)
            Spacer(Modifier.width(8.dp))
            Text(localizedString("mobile.accord_ceremony_provisioning"))
        } else {
            Icon(CIRISIcons.keySecure, contentDescription = null, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(8.dp))
            Text(
                localizedString("mobile.accord_ceremony_provision_key").replace("{slot}", slot.label),
            )
        }
    }
    if (busy) {
        Spacer(Modifier.height(12.dp))
        TouchYubiKeyPrompt()
    }
}

// ── COSIGN (3 primaries) ─────────────────────────────────────────────────────

@Composable
private fun CosignPhase(viewModel: AccordCeremonyViewModel, busy: Boolean, error: String?) {
    val cosignIndex by viewModel.currentCosignIndex.collectAsState()
    val cosigns by viewModel.cosigns.collectAsState()
    val cosignUsb by viewModel.cosignUsbPath.collectAsState()
    val cosignPin by viewModel.cosignUserPin.collectAsState()

    val primaries = viewModel.primaries()
    val allSigned = cosigns.size >= primaries.size

    Spacer(Modifier.height(8.dp))
    Text(
        localizedString("mobile.accord_ceremony_cosign_headline"),
        fontSize = 16.sp,
        fontWeight = FontWeight.Bold,
    )
    Spacer(Modifier.height(4.dp))
    Text(
        localizedString("mobile.accord_ceremony_cosign_desc"),
        fontSize = 12.sp,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )

    // Cosign progress chips.
    Spacer(Modifier.height(12.dp))
    primaries.forEachIndexed { i, p ->
        val signed = i < cosigns.size
        SlotRow(p.slot.label, p.holderName, primary = true, done = signed)
    }

    // The current primary's cosign form (until all are signed).
    if (!allSigned && cosignIndex < primaries.size) {
        val cur = primaries[cosignIndex]
        Spacer(Modifier.height(16.dp))
        Text(
            localizedString("mobile.accord_ceremony_cosign_now")
                .replace("{slot}", cur.slot.label)
                .replace("{name}", cur.holderName),
            fontSize = 14.sp,
            fontWeight = FontWeight.Bold,
        )
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(
            value = cosignUsb,
            onValueChange = { viewModel.setCosignUsbPath(it) },
            singleLine = true,
            enabled = !busy,
            isError = error != null && cosignUsb.isBlank(),
            label = { Text(localizedString("mobile.accord_ceremony_cosign_usb_label")) },
            placeholder = { Text(localizedString("mobile.accord_ceremony_usb_placeholder")) },
            leadingIcon = { Icon(CIRISIcons.pkg, contentDescription = null, modifier = Modifier.size(18.dp)) },
            modifier = Modifier.fillMaxWidth().testable("input_ceremony_cosign_usb"),
        )
        Spacer(Modifier.height(10.dp))
        OutlinedTextField(
            value = cosignPin,
            onValueChange = { viewModel.setCosignUserPin(it) },
            singleLine = true,
            enabled = !busy,
            visualTransformation = PasswordVisualTransformation(),
            label = { Text(localizedString("mobile.accord_ceremony_pin_label")) },
            modifier = Modifier.fillMaxWidth().testable("input_ceremony_cosign_pin"),
        )
        Spacer(Modifier.height(16.dp))
        Button(
            onClick = { viewModel.cosignCurrent() },
            enabled = cosignUsb.isNotBlank() && !busy,
            modifier = Modifier.fillMaxWidth().testableClickable("btn_ceremony_cosign") { viewModel.cosignCurrent() },
        ) {
            if (busy) {
                CircularProgressIndicator(modifier = Modifier.size(14.dp), strokeWidth = 2.dp)
                Spacer(Modifier.width(8.dp))
                Text(localizedString("mobile.accord_ceremony_cosigning"))
            } else {
                Icon(CIRISIcons.keySecure, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
                Text(localizedString("mobile.accord_ceremony_cosign_btn").replace("{slot}", cur.slot.label))
            }
        }
        if (busy) {
            Spacer(Modifier.height(12.dp))
            TouchYubiKeyPrompt()
        }
    }

    // Assemble — offered once ≥2 cosignatures are collected (genesis is 2-of-3).
    if (viewModel.canAssemble() || cosigns.size >= 2) {
        Spacer(Modifier.height(20.dp))
        Text(
            localizedString("mobile.accord_ceremony_assemble_ready")
                .replace("{count}", cosigns.size.toString()),
            fontSize = 12.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(8.dp))
        Button(
            onClick = { viewModel.assemble() },
            enabled = viewModel.canAssemble(),
            modifier = Modifier.fillMaxWidth().testableClickable("btn_ceremony_assemble") { viewModel.assemble() },
        ) {
            if (busy) {
                CircularProgressIndicator(modifier = Modifier.size(14.dp), strokeWidth = 2.dp)
                Spacer(Modifier.width(8.dp))
            } else {
                Icon(CIRISIcons.shield, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
            }
            Text(localizedString("mobile.accord_ceremony_assemble"))
        }
    }
}

// ── DONE (the bake artifact) ────────────────────────────────────────────────

@Composable
private fun DonePhase(viewModel: AccordCeremonyViewModel) {
    Spacer(Modifier.height(12.dp))
    Surface(
        shape = RoundedCornerShape(12.dp),
        color = MaterialTheme.colorScheme.primaryContainer,
        modifier = Modifier.fillMaxWidth().testable("accord_ceremony_success"),
    ) {
        Column(modifier = Modifier.fillMaxWidth().padding(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    CIRISIcons.check,
                    contentDescription = null,
                    modifier = Modifier.size(20.dp),
                    tint = MaterialTheme.colorScheme.onPrimaryContainer,
                )
                Spacer(Modifier.width(8.dp))
                Text(
                    localizedString("mobile.accord_ceremony_done_title"),
                    fontSize = 15.sp,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onPrimaryContainer,
                )
            }
            Spacer(Modifier.height(8.dp))
            Text(
                localizedString("mobile.accord_ceremony_save_genesis"),
                fontSize = 13.sp,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onPrimaryContainer,
            )
        }
    }

    Spacer(Modifier.height(16.dp))
    Text(
        localizedString("mobile.accord_ceremony_genesis_label"),
        fontSize = 13.sp,
        fontWeight = FontWeight.Bold,
    )
    Spacer(Modifier.height(6.dp))
    Surface(
        shape = RoundedCornerShape(10.dp),
        color = MaterialTheme.colorScheme.surfaceVariant,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(
            viewModel.genesisJson(),
            fontSize = 10.sp,
            fontFamily = FontFamily.Monospace,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(10.dp).testable("accord_ceremony_genesis_json"),
        )
    }
    Spacer(Modifier.height(8.dp))
    Text(
        localizedString("mobile.accord_ceremony_save_note"),
        fontSize = 11.sp,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

/** A roster row: the slot label + holder name + SEAT/VAULT chip + a done check. */
@Composable
private fun SlotRow(label: String, holderName: String, primary: Boolean, done: Boolean) {
    Surface(
        shape = RoundedCornerShape(10.dp),
        color = MaterialTheme.colorScheme.surfaceVariant,
        modifier = Modifier.fillMaxWidth().padding(bottom = 6.dp).testable("row_ceremony_slot_$label"),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                label,
                fontSize = 13.sp,
                fontWeight = FontWeight.Bold,
                fontFamily = FontFamily.Monospace,
                modifier = Modifier.width(36.dp),
            )
            Text(holderName, fontSize = 13.sp, modifier = Modifier.weight(1f))
            Surface(
                shape = RoundedCornerShape(6.dp),
                color = if (primary) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.tertiaryContainer,
            ) {
                Text(
                    localizedString(if (primary) "mobile.accord_ceremony_tier_seat" else "mobile.accord_ceremony_tier_vault"),
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Bold,
                    color = if (primary) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onTertiaryContainer,
                    modifier = Modifier.padding(horizontal = 6.dp, vertical = 3.dp),
                )
            }
            if (done) {
                Spacer(Modifier.width(8.dp))
                Icon(
                    CIRISIcons.check,
                    contentDescription = "Done",
                    modifier = Modifier.size(16.dp),
                    tint = MaterialTheme.colorScheme.primary,
                )
            }
        }
    }
}


// ── YubiKey readiness banner + the "touch now" prompt (0.5.33) ────────────────

/**
 * "YUBI DETECTED — FIPS COMPLIANT — 9C PROVISIONED — READY TO PROCEED" — the at-a-
 * glance YubiKey readiness banner (green when ready, error-tinted when something is
 * missing) + PIN/PUK tries remaining + a Re-check button. Driven by
 * [AccordCeremonyViewModel.yubiKeyStatus] (GET /v1/accord/yubikey-status).
 */
@Composable
private fun YubiKeyStatusBanner(status: YubiKeyStatus?, onRefresh: () -> Unit) {
    val detected = status?.detected == true
    val ready = status?.ready == true
    val bg = when {
        ready -> MaterialTheme.colorScheme.primaryContainer
        detected -> MaterialTheme.colorScheme.errorContainer
        else -> MaterialTheme.colorScheme.surfaceVariant
    }
    Surface(shape = RoundedCornerShape(10.dp), color = bg, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    if (ready) CIRISIcons.shield else CIRISIcons.keySecure,
                    contentDescription = null,
                    modifier = Modifier.size(18.dp),
                )
                Spacer(Modifier.width(8.dp))
                Text(
                    text = when {
                        status == null -> "CHECKING YUBIKEY…"
                        !detected -> "NO YUBIKEY DETECTED"
                        else -> buildString {
                            append("YUBI DETECTED")
                            append(if (status.fipsApproved) " — FIPS COMPLIANT" else " — NOT FIPS")
                            append(
                                when {
                                    status.slot9cKey && status.slot9cCert -> " — 9C PROVISIONED"
                                    status.slot9cKey -> " — 9C KEY (no cert)"
                                    else -> " — 9C EMPTY"
                                }
                            )
                            when {
                                ready -> append(" — READY TO PROCEED")
                                status.pkcs11Ed25519Ok == false -> append(" — ⚠ HOST PKCS#11 TOO OLD")
                            }
                        }
                    },
                    fontWeight = FontWeight.Bold,
                    fontSize = 13.sp,
                    fontFamily = FontFamily.Monospace,
                    modifier = Modifier.weight(1f),
                )
                TextButton(onClick = onRefresh) { Text("Re-check") }
            }
            status?.takeIf { it.detected }?.let { s ->
                Spacer(Modifier.height(4.dp))
                Text(
                    "PIN tries: ${s.pinTriesRemaining ?: "?"}    PUK tries: ${s.pukTriesRemaining ?: "?"}    " +
                        "key: ${s.slot9cKeyType ?: "—"}",
                    fontSize = 11.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            // Stale-HOST alert: the slot is perfect but the host's ykcs11 is too old
            // for Ed25519 — make this loud and actionable (it is NOT a YubiKey fault).
            if (status?.pkcs11Ed25519Ok == false) {
                Spacer(Modifier.height(6.dp))
                Text(
                    "⚠ STALE HOST LIBRARY — UPGRADE REQUIRED",
                    fontWeight = FontWeight.Bold,
                    fontSize = 12.sp,
                    fontFamily = FontFamily.Monospace,
                    color = MaterialTheme.colorScheme.error,
                )
            }
            status?.hint?.takeIf { !ready }?.let {
                Spacer(Modifier.height(2.dp))
                Text(
                    it,
                    fontSize = 11.sp,
                    fontWeight = if (status.pkcs11Ed25519Ok == false) FontWeight.Medium else FontWeight.Normal,
                    color = MaterialTheme.colorScheme.error,
                )
            }
        }
    }
}

/** The prominent "touch your YubiKey now" prompt shown while a provision/cosign is
 *  in-flight (the token blocks on a physical touch to authorize the signature). */
@Composable
private fun TouchYubiKeyPrompt() {
    Surface(
        shape = RoundedCornerShape(10.dp),
        color = MaterialTheme.colorScheme.tertiaryContainer,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(12.dp)) {
            Icon(CIRISIcons.keySecure, contentDescription = null, modifier = Modifier.size(22.dp))
            Spacer(Modifier.width(10.dp))
            Column {
                Text(
                    "👆 Touch your YubiKey now",
                    fontWeight = FontWeight.Bold,
                    fontSize = 14.sp,
                    color = MaterialTheme.colorScheme.onTertiaryContainer,
                )
                Text(
                    "The token is waiting for your physical touch to authorize this operation.",
                    fontSize = 11.sp,
                    color = MaterialTheme.colorScheme.onTertiaryContainer,
                )
            }
        }
    }
}
