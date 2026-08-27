package ai.ciris.mobile.shared.ui.components

import ai.ciris.mobile.shared.platform.copyToClipboard
import ai.ciris.mobile.shared.platform.isDebugExportAvailable
import ai.ciris.mobile.shared.platform.saveDebugBundle
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableWithHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * "Get the logs off this device" — the same block on every screen that can strand
 * a user.
 *
 * There are three such screens and they are the three where a user can do
 * nothing else: a login whose token exchange 503s, a startup that never
 * completes, and a chat that shows Disconnected and neither answers nor errors.
 * A field report from any of them was previously a screenshot; this makes it a
 * file.
 *
 * ONE implementation, three call sites, on purpose. The version/environment
 * fetch behind it ([DebugBundle.environment]) was already growing a second copy
 * in FailurePanel — a bundle from login and a bundle from chat describing the
 * same build differently is how a support thread wastes its first two replies.
 *
 * Both routes out are offered because both fail differently: saving needs
 * writable storage, copying needs a clipboard service, and on the platforms
 * where one is unavailable it is usually not the same one.
 */
@Composable
fun DebugLogsBlock(
    /** Facts only the calling screen knows — the error it is displaying, its
     *  connection state. Rendered above the log buffer, because on these screens
     *  it is usually the answer. */
    extra: Map<String, String> = emptyMap(),
    /** Shown collapsed by default everywhere except where a screen has nothing
     *  else to offer. */
    initiallyExpanded: Boolean = false,
    modifier: Modifier = Modifier,
) {
    // Desktop and mobile only. On web there is nothing to export — the node is
    // remote and the log buffer is deliberately not populated there — and under
    // CIRIS-Manager the operator owns the logs by a better route, on a
    // deployment where the person at the UI is not necessarily entitled to the
    // node's diagnostics. Rendering nothing beats rendering an empty bundle that
    // looks like diagnostics which ran and found nothing.
    if (!isDebugExportAvailable()) return

    var expanded by remember { mutableStateOf(initiallyExpanded) }
    var result by remember { mutableStateOf<String?>(null) }

    Column(modifier = modifier.fillMaxWidth()) {
        // testableWithHandler, not testable: `testable` only TAGS the element.
        // The tag showed up in /tree and the button looked automatable, but the
        // test server had no action to invoke, so a driven click did nothing
        // while a human click worked. `testableClickable` would be wrong the
        // other way — it adds its own clickable on top of the Button's.
        OutlinedButton(
            onClick = { expanded = !expanded },
            modifier = Modifier
                .fillMaxWidth()
                .testableWithHandler("btn_debug_logs_toggle") { expanded = !expanded },
        ) {
            Text(
                text = if (expanded) "Hide diagnostics" else "Click here to download logs",
                fontSize = 13.sp,
                fontWeight = FontWeight.Medium,
            )
        }

        if (!expanded) return@Column

        Spacer(Modifier.height(8.dp))

        Surface(
            shape = RoundedCornerShape(8.dp),
            color = MaterialTheme.colorScheme.surfaceVariant,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Column(Modifier.padding(12.dp)) {
                // Environment first: it is three lines, it is what we ask for
                // every time, and it is legible in a screenshot if the file
                // never makes it out.
                for ((k, v) in DebugBundle.environment()) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        Text(
                            text = "$k:",
                            fontSize = 11.sp,
                            fontWeight = FontWeight.SemiBold,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Text(
                            text = v,
                            fontSize = 11.sp,
                            fontFamily = FontFamily.Monospace,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }

                Spacer(Modifier.height(10.dp))

                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    // Named lambda so the button and the test handler invoke
                    // the SAME code path — a test that drives a parallel copy
                    // proves nothing about the button.
                    val doSave = {
                        val bundle = DebugBundle.render(extra)
                        val path = saveDebugBundle(DebugBundle.fileName(), bundle)
                        // Name the path, or say plainly that nothing was written.
                        // "Saved" with no location is a dead end for whoever has
                        // to find the file.
                        result = path?.let { "Saved to:\n$it" }
                            ?: "Could not write a file here. Use Copy instead."
                    }
                    OutlinedButton(
                        onClick = doSave,
                        modifier = Modifier
                            .weight(1f)
                            .testableWithHandler("btn_debug_download") { doSave() },
                    ) { Text("Download", fontSize = 12.sp) }

                    val doCopy = {
                        val bundle = DebugBundle.render(extra)
                        result = if (copyToClipboard(bundle)) {
                            "Copied to clipboard — paste it into the report."
                        } else {
                            "Clipboard unavailable. Select the text below."
                        }
                    }
                    OutlinedButton(
                        onClick = doCopy,
                        modifier = Modifier
                            .weight(1f)
                            .testableWithHandler("btn_debug_copy") { doCopy() },
                    ) { Text("Copy", fontSize = 12.sp) }
                }

                result?.let {
                    Spacer(Modifier.height(8.dp))
                    Text(
                        text = it,
                        fontSize = 11.sp,
                        fontFamily = FontFamily.Monospace,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }

                // Always rendered, not only on failure: on web neither route
                // works, and selectable text is then the only way out.
                Spacer(Modifier.height(10.dp))
                Surface(
                    shape = RoundedCornerShape(6.dp),
                    color = MaterialTheme.colorScheme.surface,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(
                        text = DebugBundle.render(extra),
                        fontSize = 9.sp,
                        fontFamily = FontFamily.Monospace,
                        color = MaterialTheme.colorScheme.onSurface,
                        modifier = Modifier
                            .heightIn(max = 220.dp)
                            .verticalScroll(rememberScrollState())
                            .padding(8.dp)
                            .testable("txt_debug_bundle"),
                    )
                }
            }
        }
    }
}
