package ai.ciris.mobile.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Global agent runtime mode — drives federation transport substrate posture.
 *
 * Backend source of truth: `ciris_engine/schemas/runtime/agent_mode.py`.
 * Wire format: lowercase strings ("client", "proxy", "server").
 *
 * Modes:
 *  - **CLIENT** — agent connects out to a remote node, no local data store.
 *  - **PROXY** — default. Agent runs locally with proxy-only federation surface.
 *  - **SERVER** — full node. Requires >=256 GiB free disk on the data partition.
 */
@Serializable
enum class AgentMode {
    @SerialName("client")
    CLIENT,

    @SerialName("proxy")
    PROXY,

    @SerialName("server")
    SERVER,
    ;

    /** Backend wire serialization (lowercase). */
    val wire: String get() = when (this) {
        CLIENT -> "client"
        PROXY -> "proxy"
        SERVER -> "server"
    }

    companion object {
        /** Parse a backend mode string, defaulting to [PROXY] on miss. */
        fun fromWire(s: String?): AgentMode = when (s?.lowercase()) {
            "client" -> CLIENT
            "server" -> SERVER
            "proxy", null -> PROXY
            else -> PROXY
        }
    }
}

/**
 * Snapshot of agent-mode status from /v1/system/agent-mode.
 *
 * Mirrors backend `AgentModeStatus`. The disk fields drive the SERVER button's
 * eligibility gate.
 */
data class AgentModeStatus(
    val mode: AgentMode,
    val availableDiskBytes: Long,
    val serverMinimumDiskBytes: Long,
    val serverEligible: Boolean,
    val dataDir: String,
)

/**
 * Result of a PUT /v1/system/agent-mode attempt.
 *
 * The 400 INSUFFICIENT_DISK case is modeled as a typed failure rather than an
 * exception so the UI can render an actionable message inline with the mode
 * selector instead of bouncing to a generic snackbar.
 */
sealed class AgentModeChangeResult {
    data class Success(
        val status: AgentModeStatus,
        val requiresRestart: Boolean,
    ) : AgentModeChangeResult()

    data class InsufficientDisk(
        val availableBytes: Long,
        val requiredBytes: Long,
    ) : AgentModeChangeResult()

    data class Failure(val message: String) : AgentModeChangeResult()
}
