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
    fun render(extra: Map<String, String> = emptyMap()): String =
        redactSecrets(renderRaw(extra))

    private fun renderRaw(extra: Map<String, String>): String = buildString {
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

    /**
     * Patterns that must never leave the device inside a bundle.
     *
     * Nothing logs a credential today — this was checked, not assumed. But the
     * bundle exists to be SENT to us: a user pastes it into an issue or mails
     * it to support, and at that moment whatever the log buffer happened to
     * hold becomes public. The gap between "nothing logs a secret" and "a
     * secret cannot escape" is one future `platformLog("token=$t")` written by
     * someone debugging at 2am, and nothing in review would flag that line as
     * dangerous, because on its own it isn't.
     *
     * Narrow on purpose. A redactor that eats ordinary log text destroys the
     * artifact's whole reason for existing, so these match credential SHAPES
     * (a JWT, a bearer header, an explicit assignment to a secret-ish name)
     * rather than anything that merely looks high-entropy.
     */
    private val SECRET_PATTERNS: List<Pair<Regex, String>> = listOf(
        // JWTs — the shape is unmistakable and never appears in prose.
        Regex("""eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}(\.[A-Za-z0-9_-]+)?""") to "<redacted:jwt>",
        // Authorization headers, including the `service:TOKEN` form.
        Regex("""(?i)\b(bearer\s+)(service:)?[A-Za-z0-9._~+/=-]{12,}""") to "$1<redacted>",
        // name = value, where the name is one people give to secrets.
        Regex(
            """(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token|"""
                + """auth[_-]?token|token|secret|password|passwd|client[_-]?secret)"""
                + """(\s*["']?\s*[:=]\s*["']?)"""
                // `token: expired` is a STATE, not a credential. Redacting it
                // costs the reader the one fact the line carried.
                + """(?!(?:expired|missing|present|invalid|unknown|revoked|pending|"""
                + """refreshed|required|rejected|absent)\b)"""
                + """([^\s"',;)}\]]{6,})"""
        ) to "$1$2<redacted>",
    )

    /**
     * Strip credential-shaped substrings. Internal so it can be tested directly
     * — a redactor nobody has watched fail is not a redactor.
     */
    internal fun redactSecrets(text: String): String =
        SECRET_PATTERNS.fold(text) { acc, (pattern, replacement) ->
            pattern.replace(acc, replacement)
        }

    private inline fun safely(block: () -> String): String =
        runCatching(block).getOrElse { "unknown" }

    private inline fun <T> safelyList(block: () -> List<T>): List<T> =
        runCatching(block).getOrElse { emptyList() }
}
