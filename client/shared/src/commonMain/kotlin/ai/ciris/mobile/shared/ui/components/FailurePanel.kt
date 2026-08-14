package ai.ciris.mobile.shared.ui.components

import ai.ciris.mobile.shared.models.CLIENT_VERSION
import ai.ciris.mobile.shared.platform.getAppBuildNumber
import ai.ciris.mobile.shared.platform.getAppVersion
import ai.ciris.mobile.shared.platform.getDeviceDebugInfo
import ai.ciris.mobile.shared.platform.getPlatform
import ai.ciris.mobile.shared.platform.openUrlInBrowser
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
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
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * **What kind of failure this is** — because the two need different words and
 * different buttons.
 *
 * Getting this wrong in either direction is its own bug: telling someone to
 * reinstall over a slow start throws away their setup, and telling someone to
 * keep waiting on an unrecoverable error wastes their evening.
 */
enum class FailureKind {
    /** Something did not finish in time. It may still finish. */
    Timeout,

    /**
     * Something refused for a reason that will pass — the node was not up yet,
     * the network blipped, a precondition has not happened *yet*. **Retrying the
     * same thing is the remedy.**
     *
     * This kind exists because its absence was a defect. Every claim failure was
     * rendered [Unrecoverable], including "claim PIN not captured" — whose own
     * message says the node can be claimed later — so the panel told operators
     * that retrying could not work and offered them a wipe-and-reinstall. That is
     * the same shape as an OAuth refusal that named a remedy which could not
     * work: withholding detail is fine, naming the WRONG remedy sends someone
     * down a path that is guaranteed to fail.
     */
    Recoverable,

    /** Something refused, and retrying the same thing will refuse again. */
    Unrecoverable,
}

/**
 * **The one panel every hard failure renders through** (CIRISServer#401).
 *
 * # Why this exists
 *
 * Failures were being reported in whatever style the local screen happened to
 * use. The first-run claim rejection rendered as 13sp secondary-coloured body
 * text — the same weight as a hint — under a spinner that kept turning, so an
 * operator watching a node fail to claim had no way to tell that anything had
 * gone wrong, let alone what to do. An iOS report of "cirisagent failed to
 * start" was the same shape at a different layer.
 *
 * A failure the user cannot see is a failure they will report as "it hung".
 *
 * # What it guarantees
 *
 * - **Visible.** Error container colour, large bold title, at the top of the
 *   content — not a caption under a spinner.
 * - **Actionable.** Every panel offers at least one thing to DO, and the actions
 *   differ by [FailureKind]: a timeout offers waiting and restarting; an
 *   unrecoverable error offers reporting and reinstalling.
 * - **Reportable without the user assembling anything.** [reportUrl] pre-fills
 *   the platform, both versions, the device debug string and the raw error into
 *   a GitHub issue body, with a repro-steps template left for the human. The
 *   details we can collect are the ones a human gets wrong or omits; the ones
 *   only they know are the ones we ask for.
 * - **Honest about the technical detail.** The raw error is shown verbatim in a
 *   monospace block rather than replaced by a friendly summary. The friendly
 *   sentence goes above it. Hiding the detail is what makes a report useless.
 */
@Composable
fun FailurePanel(
    /** What failed, in the user's terms — e.g. "This node could not be claimed". */
    title: String,
    /** The raw technical error, verbatim. */
    detail: String,
    kind: FailureKind,
    /** Where it happened — used in the issue title, e.g. "first-run claim". */
    context: String,
    /** Offered only for [FailureKind.Timeout]. */
    onKeepWaiting: (() -> Unit)? = null,
    /** Offered only for [FailureKind.Recoverable] — the remedy for that kind. */
    onRetry: (() -> Unit)? = null,
    /** Offered for either kind when the host can actually restart. */
    onRestart: (() -> Unit)? = null,
    modifier: Modifier = Modifier,
) {
    Surface(
        shape = RoundedCornerShape(12.dp),
        color = MaterialTheme.colorScheme.errorContainer,
        modifier = modifier.fillMaxWidth().testable("failure_panel"),
    ) {
        // SELECTABLE. Compose `Text` is not selectable by default, so every error
        // this app has ever shown was un-copyable — the user had to RETYPE a
        // substrate rejection into a bug report, or photograph it. The pre-filled
        // issue button carries the text for the common path; this is for every
        // other path (pasting into chat, a terminal, a search).
        //
        // Wrapped at the panel, not at the detail block, so the title and guidance
        // copy too — someone quoting the error usually wants the sentence above it.
        androidx.compose.foundation.text.selection.SelectionContainer {
        Column(modifier = Modifier.fillMaxWidth().padding(20.dp)) {
            Text(
                text = title,
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onErrorContainer,
                modifier = Modifier.testable("failure_panel_title"),
            )
            Spacer(Modifier.height(10.dp))
            Text(
                text = when (kind) {
                    FailureKind.Timeout ->
                        "This is taking longer than expected. It may still finish — you can keep " +
                            "waiting, or restart the app. If it never completes, please open an " +
                            "issue so we can fix it."
                    FailureKind.Recoverable ->
                        "This didn't work just now, but it should work shortly — nothing is " +
                            "broken and nothing needs reinstalling. Try again in a moment. If it " +
                            "keeps failing, please open an issue so we can fix it."
                    FailureKind.Unrecoverable ->
                        "We're sorry — this error is not recoverable by retrying. Please open an " +
                            "issue on GitHub so we can fix it, or wipe and reinstall the app to " +
                            "start over."
                },
                fontSize = 15.sp,
                color = MaterialTheme.colorScheme.onErrorContainer,
                modifier = Modifier.testable("failure_panel_guidance"),
            )

            Spacer(Modifier.height(14.dp))
            Text(
                text = "Technical detail",
                fontSize = 12.sp,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onErrorContainer,
            )
            Spacer(Modifier.height(4.dp))
            // Verbatim, scrollable, monospace. A summarised error is a report we
            // cannot act on — and the person pasting it should be pasting OURS.
            //
            // 120.dp showed TWO LINES of a substrate rejection whose whole value is
            // the sentence at the end (the constraint, the issue number, what to do
            // about it). A scroll view the reader cannot tell is scrollable is a
            // truncation with extra steps — so this is tall enough to show a real
            // error, and the "Open a GitHub issue" button carries the full text
            // regardless of what is on screen.
            Surface(
                shape = RoundedCornerShape(6.dp),
                color = MaterialTheme.colorScheme.surface,
                modifier = Modifier.fillMaxWidth().heightIn(min = 180.dp, max = 320.dp),
            ) {
                Text(
                    text = detail,
                    fontSize = 11.sp,
                    fontFamily = FontFamily.Monospace,
                    color = MaterialTheme.colorScheme.onSurface,
                    modifier = Modifier
                        .padding(8.dp)
                        .verticalScroll(rememberScrollState())
                        .testable("failure_panel_detail"),
                )
            }

            Spacer(Modifier.height(16.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = { openUrlInBrowser(reportUrl(context, title, detail, kind)) },
                    modifier = Modifier.testableClickable("btn_failure_report") {
                        openUrlInBrowser(reportUrl(context, title, detail, kind))
                    },
                ) { Text("Open a GitHub issue") }

                if (kind == FailureKind.Recoverable && onRetry != null) {
                    OutlinedButton(
                        onClick = onRetry,
                        modifier = Modifier.testableClickable("btn_failure_retry") { onRetry() },
                    ) { Text("Try again") }
                }
                if (kind == FailureKind.Timeout && onKeepWaiting != null) {
                    OutlinedButton(
                        onClick = onKeepWaiting,
                        modifier = Modifier.testableClickable("btn_failure_keep_waiting") {
                            onKeepWaiting()
                        },
                    ) { Text("Keep waiting") }
                }
                if (onRestart != null) {
                    OutlinedButton(
                        onClick = onRestart,
                        modifier = Modifier.testableClickable("btn_failure_restart") { onRestart() },
                    ) { Text("Restart the app") }
                }
            }

            if (kind == FailureKind.Unrecoverable) {
                Spacer(Modifier.height(8.dp))
                Text(
                    text = "If reporting isn't an option, wiping and reinstalling the app will " +
                        "start you over from a clean state. You will need to set up again.",
                    fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onErrorContainer,
                )
            }
        }
        }
    }
}

/**
 * **How long to wait for a node to come back**, in seconds.
 *
 * 60s on ordinary hardware. The previous 240s was chosen as a safety net and
 * behaved as a punishment: four minutes of spinner is indistinguishable from a
 * hang, so the timeout that existed to produce a clear message instead produced
 * the longest possible ambiguity.
 *
 * Two things legitimately take longer, and both are DETECTED rather than
 * guessed at:
 *
 * - **Constrained devices.** `armeabi-v7a` / 32-bit ARM are fully supported and
 *   genuinely slower to bring a node up. They get 240s. Deciding this from the
 *   reported ABI rather than from a global default means the fast majority is
 *   not made to wait for the slow minority.
 * - **Declared maintenance.** When the node or agent says it is doing scheduled
 *   work — compaction into summaries, migrations — the wait extends and the UI
 *   shows what it is doing. A progress message is what makes a long wait
 *   tolerable; a spinner is not.
 *
 * `[OPEN]` the node does not yet expose a maintenance flag. The tiering below is
 * live for device class; the maintenance leg is wired and currently always reads
 * "not in maintenance" until that surface exists. Written this way on purpose —
 * the branch is here and honest about being unfed, rather than absent and
 * forgotten.
 */
object StartupBudget {
    const val DEFAULT_SECONDS = 60
    const val CONSTRAINED_SECONDS = 240
    const val MAINTENANCE_SECONDS = 600

    /**
     * `true` for 32-bit ARM / x86 — slower to start and fully supported. Read
     * from the platform's own device string, which already reports the ABI.
     */
    fun isConstrainedDevice(): Boolean {
        val info = runCatching { getDeviceDebugInfo() }.getOrDefault("").lowercase()
        return info.contains("armeabi-v7a") ||
            info.contains("(32-bit)") ||
            info.contains("armv7")
    }

    /** The budget for this device, before any maintenance extension. */
    fun seconds(inMaintenance: Boolean = false): Int = when {
        inMaintenance -> MAINTENANCE_SECONDS
        isConstrainedDevice() -> CONSTRAINED_SECONDS
        else -> DEFAULT_SECONDS
    }
}

/** Where reports go. */
private const val ISSUE_BASE = "https://github.com/CIRISAI/CIRISServer/issues/new"

/**
 * A GitHub issue URL with everything we can collect already filled in.
 *
 * The split is deliberate: **we** supply the facts a human mistypes or omits —
 * platform, app version, client version, device string, the exact error — and we
 * ask them only for what they alone know: how they installed it and what they
 * did. A blank issue form gets a blank issue.
 */
private fun reportUrl(
    context: String,
    title: String,
    detail: String,
    kind: FailureKind,
): String {
    val kindLabel = if (kind == FailureKind.Timeout) "timeout" else "unrecoverable"
    val issueTitle = "[$kindLabel] $context: $title"
    val body = buildString {
        appendLine("## What happened")
        appendLine()
        appendLine(title)
        appendLine()
        appendLine("## Please add — only you can tell us these")
        appendLine()
        appendLine("**How did you install the app?** (PyPI wheel / release JAR / APK / TestFlight / built from source)")
        appendLine()
        appendLine("**Steps to reproduce:**")
        appendLine("1. ")
        appendLine("2. ")
        appendLine()
        appendLine("## Collected automatically")
        appendLine()
        appendLine("- context: `$context`")
        appendLine("- failure kind: `$kindLabel`")
        appendLine("- platform: `${runCatching { getPlatform().name }.getOrDefault("unknown")}`")
        appendLine("- app version: `${runCatching { getAppVersion() }.getOrDefault("unknown")}` " +
            "(build `${runCatching { getAppBuildNumber() }.getOrDefault("unknown")}`)")
        appendLine("- client version: `$CLIENT_VERSION`")
        appendLine("- device: `${runCatching { getDeviceDebugInfo() }.getOrDefault("unknown")}`")
        appendLine()
        appendLine("<details><summary>Error detail</summary>")
        appendLine()
        appendLine("```")
        appendLine(detail.take(4000))
        appendLine("```")
        appendLine()
        appendLine("</details>")
    }
    return "$ISSUE_BASE?title=${urlEncode(issueTitle)}&body=${urlEncode(body)}"
}

/**
 * Percent-encode for a query value.
 *
 * Hand-rolled because this is `commonMain` — there is no shared URL encoder
 * across JVM/iOS/wasm, and pulling one in for a single call site is worse than
 * twelve lines. Encodes everything outside the RFC-3986 unreserved set, so a
 * stack trace full of `{`, `"`, newlines and `+` survives intact rather than
 * arriving mangled in the issue body.
 */
private fun urlEncode(s: String): String {
    val unreserved = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.~"
    val out = StringBuilder(s.length * 3)
    for (b in s.encodeToByteArray()) {
        val c = b.toInt().toChar()
        if (unreserved.indexOf(c) >= 0) {
            out.append(c)
        } else {
            out.append('%').append(((b.toInt() shr 4) and 0xF).toString(16).uppercase())
                .append((b.toInt() and 0xF).toString(16).uppercase())
        }
    }
    return out.toString()
}
