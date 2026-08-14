package ai.ciris.mobile.shared.models

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * The three-state post-setup router (FSD FIRST_RUN_WIZARD_2.9.14 §5).
 *
 * The 2.9.13 loop was a two-state router: anything without an owner-binding was
 * "fresh" and went back to Setup, where `setup/root` 409s. These tests pin the
 * third state and, most importantly, that it does NOT collapse into FRESH.
 */
class NodeOwnershipTest {

    @Test
    fun freshNodeHasNeitherSignal() {
        assertEquals(NodeOwnership.FRESH, nodeOwnershipFrom(ownerBinding = null, nodeSetupRequired = true))
    }

    @Test
    fun claimedNodeHasAnOwnerBinding() {
        assertEquals(
            NodeOwnership.CLAIMED,
            nodeOwnershipFrom(ownerBinding = "label-abc123", nodeSetupRequired = false),
        )
    }

    @Test
    fun legacyOwnedIsRootWaCertWithoutOwnerBinding() {
        // The observed live state: owner-hint said "qaadmin", owned-nodes said
        // {"owner":null,"nodes":[]}. That node is OWNED, just not on a fed-ID.
        assertEquals(
            NodeOwnership.LEGACY_OWNED,
            nodeOwnershipFrom(ownerBinding = null, nodeSetupRequired = false),
        )
    }

    @Test
    fun legacyOwnedDoesNotRouteToSetup() {
        val state = nodeOwnershipFrom(ownerBinding = null, nodeSetupRequired = false)
        assertTrue(state.isOwned, "legacy-owned is configured — routing it to Setup is the 2.9.13 loop")
        assertTrue(state.needsOwnerUpgrade, "legacy-owned is what POST /v1/self/upgrade-owner repairs")
    }

    @Test
    fun anOwnerBindingWinsOverTheWaCertSignal() {
        // A claimed node whose WaCert probe says "first run" (the two services'
        // first-run predicates can legitimately disagree) is still CLAIMED.
        assertEquals(
            NodeOwnership.CLAIMED,
            nodeOwnershipFrom(ownerBinding = "label-abc123", nodeSetupRequired = true),
        )
    }

    @Test
    fun blankOwnerBindingIsNotAnOwnerBinding() {
        assertEquals(NodeOwnership.FRESH, nodeOwnershipFrom(ownerBinding = "   ", nodeSetupRequired = true))
        assertEquals(NodeOwnership.FRESH, nodeOwnershipFrom(ownerBinding = "", nodeSetupRequired = null))
    }

    @Test
    fun unknownWaCertStateDegradesToFresh() {
        // Both probes failed. Degrade to the pre-2.9.14 assumption rather than
        // inventing an owner — a fresh install must still reach the wizard.
        assertEquals(NodeOwnership.FRESH, nodeOwnershipFrom(ownerBinding = null, nodeSetupRequired = null))
    }

    @Test
    fun onlyFreshIsUnowned() {
        assertFalse(NodeOwnership.FRESH.isOwned)
        assertTrue(NodeOwnership.LEGACY_OWNED.isOwned)
        assertTrue(NodeOwnership.CLAIMED.isOwned)
    }

    @Test
    fun onlyLegacyOwnedNeedsTheUpgrade() {
        assertFalse(NodeOwnership.FRESH.needsOwnerUpgrade)
        assertTrue(NodeOwnership.LEGACY_OWNED.needsOwnerUpgrade)
        assertFalse(NodeOwnership.CLAIMED.needsOwnerUpgrade)
    }

    @Test
    fun everyStateIsReachableFromTheTwoSignals() {
        // Guard: if a state is added, it must be derivable from the probes, or
        // the router can never enter it.
        val produced = listOf(
            nodeOwnershipFrom(null, true),
            nodeOwnershipFrom(null, false),
            nodeOwnershipFrom("label-abc123", false),
        ).toSet()
        assertEquals(NodeOwnership.entries.toSet(), produced)
    }
}
