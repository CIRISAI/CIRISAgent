package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.platform.DirectoryPickerDialog
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.viewmodels.ProvisionAccordHolderViewModel
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
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
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
 * **Provision Accord Holder** — the foolproof guided flow (CIRISServer #41, the
 * safe-mesh custody floor). The would-be accord holder mints their portable-2FA
 * HUMANITY_ACCORD identity from an already-FIPS-approved FIPS YubiKey.
 *
 * Three steps:
 *   1. Confirm the YubiKey is inserted + already FIPS-approved (acknowledgement +
 *      a one-line note linking to the out-of-band ykman prep).
 *   2. **Select the ML-DSA USB path** — the centerpiece. The AEAD-wrapped
 *      ML-DSA-65 seed is written to this USB folder, unwrappable only by the
 *      YubiKey (both-keys + PIN + touch).
 *   3. Provision → `POST /v1/accord/provision-holder`. On success: the minted
 *      key_id + a clear "now ask the node owner to register you" next step. On
 *      failure: the plain-language reason (no key / wrong PIN / USB not writable /
 *      not FIPS-approved).
 *
 * No crypto in the app: it only POSTs to the loopback endpoint; the node opens
 * the YubiKey + does the wrap + mints both artifacts. Touching the physical
 * YubiKey (PIN + touch) is the real authority.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProvisionAccordHolderScreen(
    viewModel: ProvisionAccordHolderViewModel,
    onBack: () -> Unit,
) {
    val fipsAck by viewModel.fipsAcknowledged.collectAsState()
    val keyId by viewModel.keyId.collectAsState()
    val usbPath by viewModel.usbPath.collectAsState()
    val userPin by viewModel.userPin.collectAsState()
    val busy by viewModel.busy.collectAsState()
    val error by viewModel.error.collectAsState()
    val provisionedKeyId by viewModel.provisionedKeyId.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("mobile.provision_holder_title")) },
                navigationIcon = {
                    IconButton(
                        onClick = onBack,
                        modifier = Modifier.testableClickable("btn_provision_holder_back") { onBack() },
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
                text = localizedString("mobile.provision_holder_subtitle"),
                fontSize = 13.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            // ── Success state ────────────────────────────────────────────────
            val doneKeyId = provisionedKeyId
            if (doneKeyId != null) {
                Spacer(Modifier.height(16.dp))
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = MaterialTheme.colorScheme.primaryContainer,
                    modifier = Modifier.fillMaxWidth().testable("provision_holder_success"),
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
                                localizedString("mobile.provision_holder_success_title"),
                                fontSize = 15.sp,
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.onPrimaryContainer,
                            )
                        }
                        Spacer(Modifier.height(8.dp))
                        Text(
                            doneKeyId,
                            fontSize = 12.sp,
                            fontFamily = FontFamily.Monospace,
                            color = MaterialTheme.colorScheme.onPrimaryContainer,
                        )
                        Spacer(Modifier.height(8.dp))
                        Text(
                            localizedString("mobile.provision_holder_success_next"),
                            fontSize = 13.sp,
                            color = MaterialTheme.colorScheme.onPrimaryContainer,
                        )
                        Spacer(Modifier.height(12.dp))
                        OutlinedButton(
                            onClick = { viewModel.reset() },
                            modifier = Modifier.testableClickable("btn_provision_holder_again") {
                                viewModel.reset()
                            },
                        ) {
                            Text(localizedString("mobile.provision_holder_again"))
                        }
                    }
                }
                Spacer(Modifier.height(24.dp))
                return@Column
            }

            // ── Error ─────────────────────────────────────────────────────────
            error?.let { msg ->
                Spacer(Modifier.height(12.dp))
                Surface(
                    shape = RoundedCornerShape(10.dp),
                    color = MaterialTheme.colorScheme.errorContainer,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(
                        msg,
                        fontSize = 12.sp,
                        color = MaterialTheme.colorScheme.onErrorContainer,
                        modifier = Modifier.padding(10.dp).testable("provision_holder_error"),
                    )
                }
            }

            // ── Step 1: YubiKey inserted + already FIPS-approved ───────────────
            Spacer(Modifier.height(16.dp))
            StepHeader(1, localizedString("mobile.provision_holder_step1_title"))
            Spacer(Modifier.height(4.dp))
            Text(
                localizedString("mobile.provision_holder_step1_desc"),
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(8.dp))
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.fillMaxWidth().testableClickable("chk_provision_holder_fips") {
                    viewModel.setFipsAcknowledged(!fipsAck)
                },
            ) {
                Checkbox(
                    checked = fipsAck,
                    onCheckedChange = { viewModel.setFipsAcknowledged(it) },
                    enabled = !busy,
                )
                Spacer(Modifier.width(4.dp))
                Text(
                    localizedString("mobile.provision_holder_fips_ack"),
                    fontSize = 13.sp,
                    modifier = Modifier.weight(1f),
                )
            }
            Text(
                localizedString("mobile.provision_holder_prep_note"),
                fontSize = 11.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            // ── key_id ─────────────────────────────────────────────────────────
            Spacer(Modifier.height(16.dp))
            Text(
                localizedString("mobile.provision_holder_key_id_label"),
                fontSize = 13.sp,
                fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.height(6.dp))
            OutlinedTextField(
                value = keyId,
                onValueChange = { viewModel.setKeyId(it) },
                singleLine = true,
                enabled = !busy,
                label = { Text(localizedString("mobile.provision_holder_key_id_hint")) },
                modifier = Modifier.fillMaxWidth().testable("input_provision_holder_key_id"),
            )

            // ── Step 2 (the centerpiece): the ML-DSA USB path ──────────────────
            Spacer(Modifier.height(20.dp))
            StepHeader(2, localizedString("mobile.provision_holder_step2_title"))
            Spacer(Modifier.height(4.dp))
            Text(
                localizedString("mobile.provision_holder_step2_desc"),
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(8.dp))
            // A native directory-picker affordance ("Browse…") + a validated path
            // field. The field stays the source of truth; the picker just fills it.
            // Desktop opens a real folder chooser; mobile/wasm fall back to typing.
            var showDirPicker by remember { mutableStateOf(false) }
            OutlinedTextField(
                value = usbPath,
                onValueChange = { viewModel.setUsbPath(it) },
                singleLine = true,
                enabled = !busy,
                isError = error != null && usbPath.isBlank(),
                label = { Text(localizedString("mobile.provision_holder_usb_label")) },
                placeholder = { Text(localizedString("mobile.provision_holder_usb_placeholder")) },
                leadingIcon = {
                    Icon(CIRISIcons.pkg, contentDescription = null, modifier = Modifier.size(18.dp))
                },
                trailingIcon = {
                    TextButton(
                        onClick = { if (!busy) showDirPicker = true },
                        enabled = !busy,
                        modifier = Modifier.testableClickable("btn_provision_holder_usb_browse") {
                            if (!busy) showDirPicker = true
                        },
                    ) {
                        Text(localizedString("mobile.provision_holder_usb_browse"))
                    }
                },
                modifier = Modifier.fillMaxWidth().testable("input_provision_holder_usb_path"),
            )
            DirectoryPickerDialog(
                show = showDirPicker,
                onDirectoryPicked = {
                    viewModel.setUsbPath(it)
                    showDirPicker = false
                },
                onDismiss = { showDirPicker = false },
            )
            Spacer(Modifier.height(4.dp))
            Text(
                localizedString("mobile.provision_holder_usb_guidance"),
                fontSize = 11.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            // ── Optional PIN ───────────────────────────────────────────────────
            Spacer(Modifier.height(16.dp))
            OutlinedTextField(
                value = userPin,
                onValueChange = { viewModel.setUserPin(it) },
                singleLine = true,
                enabled = !busy,
                visualTransformation = PasswordVisualTransformation(),
                label = { Text(localizedString("mobile.provision_holder_pin_label")) },
                modifier = Modifier.fillMaxWidth().testable("input_provision_holder_pin"),
            )
            Text(
                localizedString("mobile.provision_holder_pin_note"),
                fontSize = 11.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            // ── Step 3: Provision ──────────────────────────────────────────────
            Spacer(Modifier.height(24.dp))
            val canProvision = fipsAck && keyId.isNotBlank() && usbPath.isNotBlank() && !busy
            Button(
                onClick = { viewModel.provision() },
                enabled = canProvision,
                modifier = Modifier.fillMaxWidth().testableClickable("btn_provision_holder_submit") {
                    viewModel.provision()
                },
            ) {
                if (busy) {
                    CircularProgressIndicator(modifier = Modifier.size(14.dp), strokeWidth = 2.dp)
                    Spacer(Modifier.width(8.dp))
                    Text(localizedString("mobile.provision_holder_busy"))
                } else {
                    Icon(CIRISIcons.keySecure, contentDescription = null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(8.dp))
                    Text(localizedString("mobile.provision_holder_submit"))
                }
            }
            if (busy) {
                Spacer(Modifier.height(8.dp))
                Text(
                    localizedString("mobile.provision_holder_touch_note"),
                    fontSize = 11.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}

/** A numbered "Step N · Title" header row for the guided flow. */
@Composable
private fun StepHeader(number: Int, title: String) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Start,
    ) {
        Surface(
            shape = RoundedCornerShape(50),
            color = MaterialTheme.colorScheme.primary,
            modifier = Modifier.size(22.dp),
        ) {
            Column(
                modifier = Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.Center,
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text(
                    number.toString(),
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onPrimary,
                )
            }
        }
        Spacer(Modifier.width(8.dp))
        Text(title, fontSize = 15.sp, fontWeight = FontWeight.Bold)
    }
}
