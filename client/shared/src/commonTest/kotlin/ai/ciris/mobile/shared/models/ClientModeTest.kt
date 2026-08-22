package ai.ciris.mobile.shared.models

import kotlin.test.Test
import kotlin.test.assertEquals

/**
 * **A half-started brain is not an agent** (CIRISAgent#1075).
 *
 * [clientModeFrom] is the ONE node-vs-agent gate. Everything that must not call
 * an AGENT-only endpoint keys off it — the shared API client is handed the
 * result so every poller stops at once.
 *
 * It used to read a non-null `cognitive_state` as proof of an agent. A brain
 * with no config starts 10 of its 22 services to serve the setup wizard and
 * reports `cognitive_state = "SETUP"` throughout, so the client ran the full
 * AGENT UI against a runtime with no telemetry, no audit and no LLM bus. On a
 * live macOS install that produced a 503 per poll, every 3 seconds, with a Java
 * stack trace each time — including on `addLlmProvider`, so the user could not
 * configure their way out of it.
 *
 * The first attempted fix keyed on `serviceCount == 0` and was INERT: the count
 * comes from the `services` map in `/v1/system/health`, which during first-run
 * holds the 10 that ARE running. These cases pin the real signal — the brain's
 * own answer about whether it is configured — so that mistake cannot return.
 */
class ClientModeTest {

    @Test
    fun setup_state_brain_with_no_config_is_NODE_not_AGENT() {
        assertEquals(
            ClientMode.NODE,
            clientModeFrom(cognitiveState = "SETUP", serviceCount = 10, brainUnconfigured = true),
            "a brain running its 10 first-run services has no telemetry, audit or LLM bus — " +
                "running the AGENT UI against it is what produced the 503 storm",
        )
    }

    @Test
    fun service_count_alone_must_not_decide_it() {
        // The exact shape of the inert fix: SETUP, but the wizard's services are
        // up, so any check of the form `serviceCount == 0` never fires.
        assertEquals(
            ClientMode.NODE,
            clientModeFrom("SETUP", serviceCount = 10, brainUnconfigured = true),
            "first-run reports a NON-ZERO service count; a gate keyed on zero is dead code",
        )
    }

    @Test
    fun a_configured_agent_in_SETUP_is_still_an_AGENT() {
        // Mid-boot on a configured install: cognitive_state is SETUP but the brain
        // HAS config, so it is a real agent coming up and must not be demoted.
        assertEquals(
            ClientMode.AGENT,
            clientModeFrom("SETUP", serviceCount = 22, brainUnconfigured = false),
            "SETUP alone must not demote a configured agent — only the brain's own " +
                "'I am not configured' may",
        )
    }

    @Test
    fun a_working_agent_is_an_AGENT() {
        assertEquals(ClientMode.AGENT, clientModeFrom("WORK", serviceCount = 22))
        assertEquals(ClientMode.AGENT, clientModeFrom("DREAM", serviceCount = 22))
    }

    @Test
    fun a_bare_node_is_a_NODE() {
        // The canonical node health envelope: role fabric-node, no cognitive_state,
        // empty service map.
        assertEquals(ClientMode.NODE, clientModeFrom(cognitiveState = null, serviceCount = 0))
    }

    @Test
    fun a_service_map_alone_still_proves_an_agent() {
        // An agent that reports services but no cognitive_state stays AGENT — this
        // path predates the fix and must not regress.
        assertEquals(ClientMode.AGENT, clientModeFrom(cognitiveState = null, serviceCount = 22))
    }

    @Test
    fun an_unreachable_setup_probe_does_not_downgrade_a_real_agent() {
        // The call site defaults brainUnconfigured to false when the probe fails,
        // so a transient setup-status outage must never demote a live agent to
        // NODE and blank its UI.
        assertEquals(
            ClientMode.AGENT,
            clientModeFrom("WORK", serviceCount = 22, brainUnconfigured = false),
        )
    }

    // ── The runtime declares what it is (CIRISAgent#1111) ──────────────────
    //
    // Every case above infers agent-ness from symptoms. A bare node in a home
    // that carries a brain reports role="fabric-node" with no cognitive_state
    // and no services, and the client correctly renders the node surface — but
    // an AGENT must never be reduced to that surface just because its health
    // envelope happened to omit the fields the inference reads.

    @Test
    fun a_runtime_that_declares_agent_is_an_AGENT() {
        assertEquals(
            ClientMode.AGENT,
            clientModeFrom(cognitiveState = null, serviceCount = 0, role = ROLE_AGENT),
            "the declaration beats the inference — an agent that answered role=agent is an " +
                "agent even if this particular envelope carried no cognitive_state or services",
        )
    }

    @Test
    fun a_fabric_node_stays_a_NODE() {
        assertEquals(
            ClientMode.NODE,
            clientModeFrom(cognitiveState = null, serviceCount = 0, role = ROLE_FABRIC_NODE),
            "a bare node declares fabric-node and must keep the node surface",
        )
    }

    @Test
    fun the_declaration_does_not_beat_the_unconfigured_brain_gate() {
        // An agent that still needs its wizard honestly answers role="agent".
        // #1075 must still win: its 10 first-run services are the wizard's.
        assertEquals(
            ClientMode.NODE,
            clientModeFrom("SETUP", serviceCount = 10, brainUnconfigured = true, role = ROLE_AGENT),
            "role is checked AFTER brainUnconfigured — a half-started brain is not an agent " +
                "surface no matter what it calls itself",
        )
    }

    @Test
    fun absent_role_falls_back_to_the_existing_inference() {
        assertEquals(
            ClientMode.AGENT,
            clientModeFrom("WORK", serviceCount = 22, role = null),
            "an older node/agent that sends no role must behave exactly as before",
        )
        assertEquals(
            ClientMode.NODE,
            clientModeFrom(null, serviceCount = 0, role = null),
            "and a roleless bare node still reads as NODE",
        )
    }
}
