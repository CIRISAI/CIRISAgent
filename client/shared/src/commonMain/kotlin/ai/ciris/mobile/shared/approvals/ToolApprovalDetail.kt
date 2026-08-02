package ai.ciris.mobile.shared.approvals

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/**
 * What a human is being asked to approve when the agent selects a tool that
 * declares `requires_approval` (CIRISAgent#942).
 *
 * A deferral used to arrive as a free-text reason and nothing else, so
 * "approve" meant approving a sentence. The server now attaches a structured
 * description under [TOOL_APPROVAL_DETAIL_KEY] in `PendingDeferral.context`:
 * the tool as the first-run consent wizard describes it — same
 * `ToolDisclosure` projection, same derived capability flags, same localized
 * flag strings — plus the arguments the agent intends to pass on this call.
 *
 * **The grant is per-tool, per-task, not per-invocation.** Approving hands the
 * follow-up `[WA GUIDANCE]` task an envelope naming this tool. That task
 * re-reasons from scratch and may call the tool with different arguments than
 * the ones shown here. This mirrors the budget envelope: a ceiling, not a
 * specific transaction. The UI must say so rather than imply the arguments are
 * what is being signed off.
 */
@Serializable
data class ToolApprovalDisclosure(
    val name: String = "",
    val description: String = "",
    val category: String = "general",
    @SerialName("model_authored_parameters") val modelAuthoredParameters: List<String> = emptyList(),
    @SerialName("capability_flags") val capabilityFlags: List<String> = emptyList(),
)

@Serializable
data class ToolApprovalDetail(
    /** Tool name. Always present, even when the tool service could not describe it. */
    val name: String = "",
    /** The consent-wizard projection of the tool, when available. */
    val tool: ToolApprovalDisclosure? = null,
    /** Arguments the agent intends to pass, stringified and truncated server-side. */
    val parameters: Map<String, String> = emptyMap(),
    /**
     * "true" when the arguments were too large to carry. The tool identity and
     * its capability flags still describe the class of thing being authorized.
     */
    @SerialName("parameters_omitted") val parametersOmitted: String? = null,
) {
    val argumentsWereOmitted: Boolean get() = parametersOmitted == "true"

    /** Capability flags, ordered so the least expected consequence reads first. */
    val orderedCapabilityFlags: List<String>
        get() {
            val flags = tool?.capabilityFlags ?: return emptyList()
            return flags.sortedBy { flag ->
                val index = ToolCapabilityFlagOrder.indexOf(flag)
                if (index < 0) ToolCapabilityFlagOrder.size else index
            }
        }
}

/** Mirrors `ToolCapabilityFlags.NOTABLE` — surprise-ordering, unknowns last. */
private val ToolCapabilityFlagOrder: List<String> = listOf(
    "shell_execution",
    "secret_plaintext",
    "network_fetch",
    "custom_headers",
    "file_write",
    "affects_other_people",
    "request_body",
    "file_read",
    "requires_approval",
)

/** Context key carrying the tool name awaiting approval. Mirrors the Python constant. */
const val PENDING_TOOL_APPROVAL_KEY: String = "pending_tool_approval"

/** Context key carrying the JSON-encoded [ToolApprovalDetail]. Mirrors the Python constant. */
const val TOOL_APPROVAL_DETAIL_KEY: String = "tool_approval_detail"

private val toolApprovalJson = Json {
    ignoreUnknownKeys = true
    isLenient = true
}

/**
 * Parse the tool-approval detail out of a deferral's context map.
 *
 * Returns null when this deferral is not a tool-approval request, which is the
 * common case — most deferrals are ethical, not authorization. Malformed JSON
 * also returns null: the dialog then falls back to the existing free-text
 * rendering rather than showing a broken card, and the approval still works.
 * Failing to *describe* a tool must never block a human from deciding.
 */
fun parseToolApprovalDetail(context: Map<String, String>?): ToolApprovalDetail? {
    val raw = context?.get(TOOL_APPROVAL_DETAIL_KEY)?.takeIf { it.isNotBlank() }
    if (raw != null) {
        // Explicit serializer rather than the reified overload — no dependence
        // on which kotlinx.serialization extension happens to be imported.
        val parsed = runCatching {
            toolApprovalJson.decodeFromString(ToolApprovalDetail.serializer(), raw)
        }.getOrNull()
        if (parsed != null && parsed.name.isNotBlank()) return parsed
    }
    // Older agents (and any path that could not encode the detail) still send
    // the tool name. A name-only card is far better than no card at all.
    val name = context?.get(PENDING_TOOL_APPROVAL_KEY)?.takeIf { it.isNotBlank() } ?: return null
    return ToolApprovalDetail(name = name)
}

/**
 * Context keys the tool-approval card renders itself, so the generic key/value
 * dump below it does not repeat them.
 */
val TOOL_APPROVAL_RENDERED_KEYS: Set<String> = setOf(
    PENDING_TOOL_APPROVAL_KEY,
    TOOL_APPROVAL_DETAIL_KEY,
)
