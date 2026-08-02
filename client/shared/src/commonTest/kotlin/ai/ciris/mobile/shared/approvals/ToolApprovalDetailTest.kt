package ai.ciris.mobile.shared.approvals

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The approval card must describe what is being approved (CIRISAgent#942), and
 * must never be the reason a human cannot decide. These tests pin both halves.
 */
class ToolApprovalDetailTest {

    private val realPayload = """
        {"name":"shell_command",
         "parameters":{"command":"rm -rf /tmp/x"},
         "tool":{"name":"shell_command",
                 "description":"Run a shell command on this device",
                 "category":"system",
                 "model_authored_parameters":["command"],
                 "capability_flags":["requires_approval","shell_execution"]}}
    """.trimIndent()

    @Test
    fun parsesTheServerPayload() {
        val detail = parseToolApprovalDetail(mapOf(TOOL_APPROVAL_DETAIL_KEY to realPayload))
        assertNotNull(detail)
        assertEquals("shell_command", detail.name)
        assertEquals("Run a shell command on this device", detail.tool?.description)
        assertEquals("rm -rf /tmp/x", detail.parameters["command"])
        assertTrue(detail.tool!!.capabilityFlags.contains("shell_execution"))
    }

    @Test
    fun ordersFlagsBySurpriseNotAlphabetically() {
        val detail = parseToolApprovalDetail(mapOf(TOOL_APPROVAL_DETAIL_KEY to realPayload))
        assertNotNull(detail)
        // shell_execution is the least expected consequence, so it reads first,
        // even though "requires_approval" sorts earlier alphabetically and
        // arrives first in the payload.
        assertEquals(listOf("shell_execution", "requires_approval"), detail.orderedCapabilityFlags)
    }

    @Test
    fun unknownFlagFromNewerServerIsKeptNotDropped() {
        val payload = """{"name":"t","tool":{"capability_flags":["launches_missiles","file_read"]}}"""
        val detail = parseToolApprovalDetail(mapOf(TOOL_APPROVAL_DETAIL_KEY to payload))
        assertNotNull(detail)
        // Known flag first, unknown last — but present. Dropping it would hide a
        // consequence from the person authorizing it.
        assertEquals(listOf("file_read", "launches_missiles"), detail.orderedCapabilityFlags)
    }

    @Test
    fun malformedJsonFallsBackToTheToolNameRatherThanBlockingTheDecision() {
        val detail = parseToolApprovalDetail(
            mapOf(
                TOOL_APPROVAL_DETAIL_KEY to "{not json",
                PENDING_TOOL_APPROVAL_KEY to "send_money",
            )
        )
        assertNotNull(detail)
        assertEquals("send_money", detail.name)
        assertNull(detail.tool)
    }

    @Test
    fun olderAgentSendingOnlyTheToolNameStillRendersACard() {
        val detail = parseToolApprovalDetail(mapOf(PENDING_TOOL_APPROVAL_KEY to "send_money"))
        assertNotNull(detail)
        assertEquals("send_money", detail.name)
    }

    @Test
    fun ordinaryDeferralsAreNotToolApprovals() {
        assertNull(parseToolApprovalDetail(null))
        assertNull(parseToolApprovalDetail(emptyMap()))
        assertNull(parseToolApprovalDetail(mapOf("task_description" to "something ethical")))
    }

    @Test
    fun omittedArgumentsAreSurfaced() {
        val payload = """{"name":"send_money","parameters_omitted":"true"}"""
        val detail = parseToolApprovalDetail(mapOf(TOOL_APPROVAL_DETAIL_KEY to payload))
        assertNotNull(detail)
        assertTrue(detail.argumentsWereOmitted)
        assertTrue(detail.parameters.isEmpty())
    }

    @Test
    fun renderedKeysAreNotRepeatedInTheGenericContextDump() {
        assertTrue(TOOL_APPROVAL_RENDERED_KEYS.contains(TOOL_APPROVAL_DETAIL_KEY))
        assertTrue(TOOL_APPROVAL_RENDERED_KEYS.contains(PENDING_TOOL_APPROVAL_KEY))
    }
}
