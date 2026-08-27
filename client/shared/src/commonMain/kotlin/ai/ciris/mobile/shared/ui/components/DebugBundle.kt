package ai.ciris.mobile.shared.ui.components

import ai.ciris.mobile.shared.models.CLIENT_VERSION
import ai.ciris.mobile.shared.platform.DebugLogBuffer
import ai.ciris.mobile.shared.platform.getAppBuildNumber
import ai.ciris.mobile.shared.platform.getAppVersion
import ai.ciris.mobile.shared.platform.getCurrentTimestamp
import ai.ciris.mobile.shared.platform.getDeviceDebugInfo
import ai.ciris.mobile.shared.platform.getPlatform

/**
 * The ONE place that answers "what is this build, and what has it been doing".
 *
 * Three screens need it — login, startup, and interact — and each of them is a
 * screen a user reaches when something has already gone wrong, so each one had
 * every reason to grow its own slightly-different version. FailurePanel had
 * already grown the first one. This is that fetch, extracted, so a field report
 * from the login screen and one from the chat screen describe the same build in
 * the same words.
 *
 * Every accessor is wrapped: a diagnostic that throws while collecting
 * diagnostics is worse than one that reports "unknown" for a single row.
 */
object DebugBundle {

    /** Environment rows, in the order a reader wants them. */
    fun environment(): List<Pair<String, String>> = listOf(
        "client version" to CLIENT_VERSION,
        "app version" to safely { getAppVersion() },
        "build" to safely { getAppBuildNumber() },
        "platform" to safely { getPlatform().name },
        "device" to safely { getDeviceDebugInfo() },
        "captured" to safely { getCurrentTimestamp() },
    )

    /**
     * The full bundle: environment, then the in-memory log buffer.
     *
     * [extra] is for facts only the calling screen knows — the login screen's
     * token-exchange error, the interact screen's connection state. They ride
     * ABOVE the logs because they are usually the answer.
     */
    fun render(extra: Map<String, String> = emptyMap()): String = buildString {
        appendLine("CIRIS debug bundle")
        appendLine("==================")
        appendLine()
        for ((k, v) in environment()) appendLine("$k: $v")
        if (extra.isNotEmpty()) {
            appendLine()
            appendLine("Screen state")
            appendLine("------------")
            for ((k, v) in extra) appendLine("$k: $v")
        }
        appendLine()
        appendLine("Recent log buffer")
        appendLine("-----------------")
        val entries = safelyList { DebugLogBuffer.getFiltered() }
        if (entries.isEmpty()) {
            appendLine("(empty — the buffer is in-memory and clears on restart, so a")
            appendLine(" crash-and-relaunch loses it. The on-disk log survives.)")
        } else {
            for (e in entries) appendLine("[${e.level}] ${e.tag}: ${e.message}")
        }
    }

    /** Timestamped so two bundles from one user do not overwrite each other. */
    fun fileName(): String {
        val stamp = safely { getCurrentTimestamp() }
            .replace(":", "-").replace(" ", "_").take(24)
        return "ciris-debug-$stamp.txt"
    }

    private inline fun safely(block: () -> String): String =
        runCatching(block).getOrElse { "unknown" }

    private inline fun <T> safelyList(block: () -> List<T>): List<T> =
        runCatching(block).getOrElse { emptyList() }
}
