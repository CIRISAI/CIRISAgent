package ai.ciris.mobile.shared.models

import kotlinx.datetime.Instant
import kotlinx.serialization.Serializable

@Serializable
data class ChatMessage(
    val id: String,
    val text: String,
    val type: MessageType,
    val timestamp: Instant,
    val reasoning: String? = null,
    val attachmentCount: Int = 0,
    val attachmentNames: List<String> = emptyList(),
    val hasImageAttachments: Boolean = false,
    val hasDocumentAttachments: Boolean = false,
    // Action details (populated when type == ACTION)
    val actionDetails: ActionDetails? = null
)

/**
 * The 10 CIRIS action types (verbs).
 * Uses ASCII symbols for cross-platform WASM/Skia compatibility.
 */
@Serializable
enum class ActionType(val symbol: String, val auditEventType: String, val displayName: String) {
    SPEAK("\u25B6", "speak", "Speak"),
    TOOL("\u2692", "tool", "Tool"),
    OBSERVE("\u25CB", "observe", "Observe"),
    MEMORIZE("\u2795", "memorize", "Memorize"),
    RECALL("\u2753", "recall", "Recall"),
    FORGET("\u2796", "forget", "Forget"),
    REJECT("\u2716", "reject", "Reject"),
    PONDER("\u22EF", "ponder", "Ponder"),
    DEFER("\u275A\u275A", "defer", "Defer"),
    TASK_COMPLETE("\u2714", "task_complete", "Task Complete");

    companion object {
        fun fromSymbol(symbol: String): ActionType? = entries.find { it.symbol == symbol }
        fun fromAuditEventType(eventType: String): ActionType? {
            val normalizedType = eventType.lowercase()
            return entries.find {
                normalizedType == it.auditEventType ||
                normalizedType == "handler_action_${it.auditEventType}" ||
                normalizedType.endsWith(it.auditEventType)
            }
        }
    }
}

/**
 * Details of a CIRIS action for display in the chat timeline.
 * Supports all 10 action types with type-specific details.
 */
@Serializable
data class ActionDetails(
    val actionType: ActionType,
    val outcome: String = "success",
    val auditEntryId: String? = null,
    // Common fields
    val description: String? = null,
    // Tool-specific
    val toolName: String? = null,
    val toolAdapter: String? = null,
    val toolParameters: Map<String, String> = emptyMap(),
    val toolResult: String? = null,
    // Memory-specific (memorize, recall, forget)
    val memoryKey: String? = null,
    val memoryContent: String? = null,
    // Defer-specific
    val deferReason: String? = null,
    val deferTarget: String? = null,
    // Speak-specific (content is in description)
    // Reject-specific
    val rejectReason: String? = null,
    // Ponder-specific
    val ponderTopic: String? = null,
    val ponderQuestions: List<String> = emptyList()
)

@Serializable
enum class MessageType {
    USER,
    AGENT,
    SYSTEM,
    ERROR,
    ACTION  // Represents any of the 10 CIRIS action types
}

@Serializable
data class InteractRequest(
    val message: String,
    val channel_id: String = "mobile_app"
)

@Serializable
data class InteractResponse(
    val response: String,
    val reasoning: String? = null,
    val message_id: String
)
