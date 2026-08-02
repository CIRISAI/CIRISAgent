package ai.ciris.mobile.shared.ui.components

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.federation.AccordHolderDto
import ai.ciris.mobile.shared.models.federation.PendingCoscrubDto
import ai.ciris.mobile.shared.platform.DirectoryPickerDialog
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.icons.CIRISMaterialIcons
import ai.ciris.mobile.shared.ui.icons.Visibility
import ai.ciris.mobile.shared.ui.icons.VisibilityOff
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement

/**
 * The shared sign / confirm sub-flows for the Trust Root — defined ONCE, opened by
 * any op. This is where the old duplication dies: admit-node, add-canonical,
 * replace, drill, announce all open [HardwareScrubSheet]; Cosign on an invocation
 * uses [CosignSheet]; Withdraw uses [ConfirmDestructive]. Every one wraps an
 * existing `AccordViewModel` method — no server change.
 *
 * The no-crypto posture is a property of these sheets (stated once): the app holds
 * NO keys, the node re-opens the holder's YubiKey + USB-wrapped ML-DSA, and the
 * YubiKey touch is the human consent.
 */

/** The holder-picker + USB-picker + PIN inputs every signing sub-flow needs. */
@Composable
private fun ColumnScope.HolderSignInputs(
    holders: List<AccordHolderDto>,
    holderKeyId: String,
    onHolder: (String) -> Unit,
    usbPath: String,
    onUsb: (String) -> Unit,
    pin: String,
    onPin: (String) -> Unit,
    tagPrefix: String,
) {
    var holderMenu by remember { mutableStateOf(false) }
    var showPin by remember { mutableStateOf(false) }
    var usbPicker by remember { mutableStateOf(false) }

    Box(modifier = Modifier.fillMaxWidth()) {
        OutlinedButton(
            onClick = { holderMenu = true },
            modifier = Modifier.fillMaxWidth().testable("dd_scrub_holder_$tagPrefix"),
        ) {
            Text(holderKeyId.ifBlank { localizedString("mobile.accord_scrub_holder_select") })
        }
        DropdownMenu(expanded = holderMenu, onDismissRequest = { holderMenu = false }) {
            if (holders.isEmpty()) {
                DropdownMenuItem(
                    text = { Text(localizedString("mobile.accord_scrub_no_holders")) },
                    onClick = { holderMenu = false },
                )
            }
            holders.forEach { h ->
                DropdownMenuItem(
                    text = { Text(h.keyId, fontFamily = FontFamily.Monospace) },
                    onClick = { onHolder(h.keyId); holderMenu = false },
                    modifier = Modifier.testableClickable("mi_scrub_holder_${tagPrefix}_${h.keyId}") {
                        onHolder(h.keyId); holderMenu = false
                    },
                )
            }
        }
    }
    Spacer(Modifier.height(6.dp))
    OutlinedTextField(
        value = usbPath,
        onValueChange = onUsb,
        singleLine = true,
        label = { Text(localizedString("mobile.accord_scrub_usb_label")) },
        trailingIcon = {
            TextButton(
                onClick = { usbPicker = true },
                modifier = Modifier.testableClickable("btn_scrub_browse_$tagPrefix") { usbPicker = true },
            ) { Text(localizedString("mobile.accord_scrub_browse")) }
        },
        modifier = Modifier.fillMaxWidth().testable("input_scrub_usb_$tagPrefix"),
    )
    DirectoryPickerDialog(
        show = usbPicker,
        onDirectoryPicked = { onUsb(it); usbPicker = false },
        onDismiss = { usbPicker = false },
    )
    Spacer(Modifier.height(6.dp))
    OutlinedTextField(
        value = pin,
        onValueChange = onPin,
        singleLine = true,
        label = { Text(localizedString("mobile.accord_scrub_pin_label")) },
        visualTransformation =
            if (showPin) VisualTransformation.None else PasswordVisualTransformation(),
        trailingIcon = {
            IconButton(
                onClick = { showPin = !showPin },
                modifier = Modifier.testableClickable("btn_scrub_pin_toggle_$tagPrefix") {
                    showPin = !showPin
                },
            ) {
                Icon(
                    if (showPin) CIRISMaterialIcons.Filled.VisibilityOff
                    else CIRISMaterialIcons.Filled.Visibility,
                    contentDescription = if (showPin) "Hide PIN" else "Show PIN",
                    modifier = Modifier.size(18.dp),
                )
            }
        },
        modifier = Modifier.fillMaxWidth().testable("input_scrub_pin_$tagPrefix"),
    )
}

/**
 * The one hardware-scrub sheet (§3.2/§3.3). Holder + USB + PIN, plus one optional
 * kind [extras] block (target node picker, canonical IP/transport, announce text).
 * Admit-node, add-canonical, replace, drill, and announce all open THIS — the only
 * difference is the [extras] block and which VM method [onSubmit] calls.
 */
@Composable
fun HardwareScrubSheet(
    title: String,
    subtitle: String,
    holders: List<AccordHolderDto>,
    busy: Boolean,
    submitLabel: String,
    submitBusyLabel: String,
    tagPrefix: String,
    extraReady: Boolean = true,
    extras: (@Composable ColumnScope.() -> Unit)? = null,
    onSubmit: (holderKeyId: String, usbPath: String, pin: String?, modulePath: String?) -> Unit,
    onDismiss: () -> Unit,
) {
    var holderKeyId by remember { mutableStateOf("") }
    var usbPath by remember { mutableStateOf("") }
    var pin by remember { mutableStateOf("") }
    // Advanced, blank by default — a macOS/Windows holder whose ykcs11 lives off the
    // node's OS default path can override it here without a rebuild. Blank → omitted →
    // the node resolves the OS-appropriate default.
    var modulePath by remember { mutableStateOf("") }
    val ready = holderKeyId.isNotBlank() && usbPath.isNotBlank() && pin.isNotBlank() &&
        extraReady && !busy

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column(
                modifier = Modifier
                    .heightIn(max = 460.dp)
                    .verticalScroll(rememberScrollState())
                    .testable("scrub_sheet_$tagPrefix"),
            ) {
                Text(
                    subtitle,
                    fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(10.dp))
                extras?.let {
                    it()
                    Spacer(Modifier.height(10.dp))
                }
                HolderSignInputs(
                    holders = holders,
                    holderKeyId = holderKeyId,
                    onHolder = { holderKeyId = it },
                    usbPath = usbPath,
                    onUsb = { usbPath = it },
                    pin = pin,
                    onPin = { pin = it },
                    tagPrefix = tagPrefix,
                )
                Spacer(Modifier.height(6.dp))
                OutlinedTextField(
                    value = modulePath,
                    onValueChange = { modulePath = it },
                    singleLine = true,
                    label = { Text(localizedString("mobile.accord_scrub_module_label")) },
                    placeholder = { Text(localizedString("mobile.accord_scrub_module_hint")) },
                    modifier = Modifier.fillMaxWidth().testable("input_scrub_module_$tagPrefix"),
                )
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    onSubmit(holderKeyId, usbPath, pin.ifBlank { null }, modulePath.ifBlank { null })
                },
                enabled = ready,
                modifier = Modifier.testableClickable("btn_scrub_submit_$tagPrefix") {
                    if (ready) {
                        onSubmit(holderKeyId, usbPath, pin.ifBlank { null }, modulePath.ifBlank { null })
                    }
                },
            ) {
                Text(if (busy) submitBusyLabel else submitLabel)
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                modifier = Modifier.testableClickable("btn_scrub_cancel_$tagPrefix") { onDismiss() },
            ) { Text(localizedString("mobile.accord_scrub_cancel")) }
        },
    )
}

/**
 * The m-of-n cosign confirmation (§3.2). Shows the object + current signers, then
 * the same holder-scrub inputs — "your node signs; the app holds no keys". Used by
 * Cosign on an invocation (halt / drill / notify) — maps to `AccordViewModel.concur`.
 */
@Composable
fun CosignSheet(
    invocationId: String,
    kindLabel: String,
    signed: Int,
    threshold: Int,
    binding: Boolean,
    holders: List<AccordHolderDto>,
    busy: Boolean,
    onSubmit: (holderKeyId: String, usbPath: String, pin: String?, modulePath: String?) -> Unit,
    onDismiss: () -> Unit,
) {
    HardwareScrubSheet(
        title = localizedString("mobile.accord_cosign_title"),
        subtitle = localizedString("mobile.accord_cosign_desc"),
        holders = holders,
        busy = busy,
        submitLabel = localizedString("mobile.accord_cosign_submit"),
        submitBusyLabel = localizedString("mobile.accord_cosign_submit_busy"),
        tagPrefix = "cosign_$invocationId",
        onSubmit = onSubmit,
        onDismiss = onDismiss,
        extras = {
            Text(
                "$kindLabel · $invocationId",
                fontSize = 12.sp,
                fontFamily = FontFamily.Monospace,
                color = MaterialTheme.colorScheme.onSurface,
            )
            Spacer(Modifier.height(4.dp))
            Text(
                localizedString("mobile.accord_quorum_short")
                    .replace("{signed}", signed.toString())
                    .replace("{threshold}", threshold.toString()),
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (binding) {
                Spacer(Modifier.height(4.dp))
                Text(
                    localizedString("mobile.accord_cosign_binding_warn"),
                    fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.error,
                )
            }
        },
    )
}

/**
 * The **canonical co-scrub** cosign sheet (CIRISServer#174). Distinct from the
 * invocation [CosignSheet]: it appends THIS holder's scrub to a `SignedKeyRecord`
 * partial (verify's `append_scrub`, byte-identical envelope) toward the family
 * m-of-n. Two ways in:
 *   - [entry] non-null → a "Pending co-signs" row; its `partial` is submitted verbatim.
 *   - [entry] null → the paste fallback (works without gossip): paste the partial JSON.
 *
 * The parse is guarded — malformed JSON calls [onError] and keeps the sheet open.
 * Built on [HardwareScrubSheet] so the holder + USB + PIN inputs are identical.
 */
@Composable
fun CanonicalCosignSheet(
    entry: PendingCoscrubDto?,
    holders: List<AccordHolderDto>,
    busy: Boolean,
    onSubmit: (holderKeyId: String, usbPath: String, pin: String?, modulePath: String?, partial: JsonElement) -> Unit,
    onError: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    var pasted by remember { mutableStateOf("") }
    val pasteMode = entry == null
    // Resolve the error string in composable context — the submit lambda isn't @Composable.
    val invalidJsonMsg = localizedString("mobile.accord_coscrub_paste_invalid")
    HardwareScrubSheet(
        title = localizedString("mobile.accord_coscrub_cosign_title"),
        subtitle = localizedString("mobile.accord_coscrub_cosign_desc"),
        holders = holders,
        busy = busy,
        submitLabel = localizedString("mobile.accord_coscrub_cosign_submit"),
        submitBusyLabel = localizedString("mobile.accord_coscrub_cosign_submit_busy"),
        tagPrefix = "coscrub_${entry?.targetKeyId ?: "paste"}",
        extraReady = !pasteMode || pasted.isNotBlank(),
        extras = {
            if (entry != null) {
                Text(
                    localizedString("mobile.accord_coscrub_target", "key", entry.targetKeyId),
                    fontSize = 12.sp,
                    fontFamily = FontFamily.Monospace,
                    color = MaterialTheme.colorScheme.onSurface,
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    localizedString("mobile.accord_coscrub_badge")
                        .replace("{signed}", entry.distinctScrubCount.toString())
                        .replace("{needed}", entry.quorumNeeded.toString()),
                    fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                if (entry.scrubbers.isNotEmpty()) {
                    Spacer(Modifier.height(4.dp))
                    Text(
                        localizedString("mobile.accord_coscrub_scrubbers", "scrubbers", entry.scrubbers.joinToString(", ")),
                        fontSize = 11.sp,
                        fontFamily = FontFamily.Monospace,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            } else {
                Text(
                    localizedString("mobile.accord_coscrub_paste_hint"),
                    fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(6.dp))
                OutlinedTextField(
                    value = pasted,
                    onValueChange = { pasted = it },
                    singleLine = false,
                    label = { Text(localizedString("mobile.accord_cosign_paste_label")) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(min = 96.dp)
                        .testable("input_coscrub_paste"),
                )
            }
        },
        onSubmit = { holderKeyId, usbPath, pin, modulePath ->
            val partial: JsonElement? = if (entry != null) {
                entry.partial
            } else {
                try {
                    Json.parseToJsonElement(pasted.trim())
                } catch (e: Exception) {
                    onError(invalidJsonMsg)
                    null
                }
            }
            if (partial != null) {
                onSubmit(holderKeyId, usbPath, pin, modulePath, partial)
                onDismiss()
            }
        },
        onDismiss = onDismiss,
    )
}

/**
 * The destructive confirm (§3.2) — withdraw / recant. Captures the reason and (for
 * an m-of-n op) the proposal digest INLINE, next to the op it authorizes (replacing
 * the old loose `input_canonical_proposal_digest` field). Maps to
 * `AccordViewModel.withdrawCanonical`.
 */
@Composable
fun ConfirmDestructive(
    title: String,
    message: String,
    confirmLabel: String,
    tagPrefix: String,
    busy: Boolean,
    showDigest: Boolean = false,
    digestLabel: String = "",
    onConfirm: (digest: String) -> Unit,
    onDismiss: () -> Unit,
) {
    var digest by remember { mutableStateOf("") }
    val ready = (!showDigest || digest.isNotBlank()) && !busy
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column(modifier = Modifier.testable("destructive_sheet_$tagPrefix")) {
                Text(
                    message,
                    fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.error,
                )
                if (showDigest) {
                    Spacer(Modifier.height(10.dp))
                    OutlinedTextField(
                        value = digest,
                        onValueChange = { digest = it },
                        singleLine = true,
                        label = { Text(digestLabel) },
                        modifier = Modifier.fillMaxWidth().testable("input_destructive_digest_$tagPrefix"),
                    )
                }
            }
        },
        confirmButton = {
            Button(
                onClick = { onConfirm(digest) },
                enabled = ready,
                colors = ButtonDefaults.buttonColors(
                    containerColor = MaterialTheme.colorScheme.error,
                ),
                modifier = Modifier.testableClickable("btn_destructive_confirm_$tagPrefix") {
                    if (ready) onConfirm(digest)
                },
            ) { Text(confirmLabel) }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                modifier = Modifier.testableClickable("btn_destructive_cancel_$tagPrefix") { onDismiss() },
            ) { Text(localizedString("mobile.accord_scrub_cancel")) }
        },
    )
}
