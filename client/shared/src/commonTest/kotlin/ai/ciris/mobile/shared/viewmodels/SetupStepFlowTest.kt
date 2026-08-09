package ai.ciris.mobile.shared.viewmodels

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * The wizard's step graph — three screens, and no way to declare a fourth that
 * nobody can reach.
 *
 * 2.9.13 declared eleven steps of which FIVE were never a `nextStep()` target:
 * PREFERENCES, OPTIONAL_FEATURES, QUICK_SETUP, NODE_AUTH, VERIFY_SETUP. That was
 * not a tidiness problem — the trace-consent checkbox lived on one of them, so
 * NO production node could ever express trace consent. An unreachable step is a
 * feature that silently does not exist, so [everyStepIsReachable] fails CI
 * rather than letting the next one ship.
 */
class SetupStepFlowTest {

    private val builds = listOf(true, false) // CIRISBuild.HAS_AGENT: agent, node client

    @Test
    fun everyStepIsReachable() {
        // Walk the graph from the entry step in every build configuration and
        // collect what is actually visitable.
        val reached = mutableSetOf(SetupStep.YOU)
        for (hasAgent in builds) {
            var step = SetupStep.YOU
            var guard = 0
            while (step != SetupStep.COMPLETE && guard++ < SetupStep.entries.size + 1) {
                step = nextSetupStep(step, hasAgent)
                reached += step
            }
        }
        val unreachable = SetupStep.entries.toSet() - reached
        assertTrue(
            unreachable.isEmpty(),
            "these steps are declared but no nextStep() path reaches them, so anything " +
                "on them cannot be used: $unreachable",
        )
    }

    @Test
    fun theAgentBuildVisitsAllThreeScreens() {
        assertEquals(SetupStep.JOIN_FEDERATION, nextSetupStep(SetupStep.YOU, hasAgent = true))
        assertEquals(SetupStep.AI, nextSetupStep(SetupStep.JOIN_FEDERATION, hasAgent = true))
        assertEquals(SetupStep.COMPLETE, nextSetupStep(SetupStep.AI, hasAgent = true))
    }

    @Test
    fun theNodeClientSkipsTheAiScreen() {
        // The node client has no brain to configure — but it must still pass
        // through the federation consent screen.
        assertEquals(SetupStep.JOIN_FEDERATION, nextSetupStep(SetupStep.YOU, hasAgent = false))
        assertEquals(SetupStep.COMPLETE, nextSetupStep(SetupStep.JOIN_FEDERATION, hasAgent = false))
    }

    @Test
    fun consentIsOnThePathInEveryBuild() {
        // The 0.3 regression in one assertion: the consent screen must not be
        // skippable by any build configuration.
        for (hasAgent in builds) {
            var step = SetupStep.YOU
            val path = mutableListOf(step)
            while (step != SetupStep.COMPLETE) {
                step = nextSetupStep(step, hasAgent)
                path += step
            }
            assertTrue(
                SetupStep.JOIN_FEDERATION in path,
                "hasAgent=$hasAgent never reaches the consent screen: $path",
            )
        }
    }

    @Test
    fun backMirrorsForwardExactly() {
        for (hasAgent in builds) {
            var step = SetupStep.YOU
            while (step != SetupStep.COMPLETE) {
                val forward = nextSetupStep(step, hasAgent)
                assertEquals(
                    step,
                    previousSetupStep(forward, hasAgent),
                    "back from $forward must return to $step (hasAgent=$hasAgent)",
                )
                step = forward
            }
        }
    }

    @Test
    fun theFirstStepHasNoBack() {
        for (hasAgent in builds) {
            assertEquals(SetupStep.YOU, previousSetupStep(SetupStep.YOU, hasAgent))
        }
    }

    @Test
    fun completeIsTerminal() {
        for (hasAgent in builds) {
            assertEquals(SetupStep.COMPLETE, nextSetupStep(SetupStep.COMPLETE, hasAgent))
        }
    }

    @Test
    fun theFinalStepIsTheOneBeforeComplete() {
        for (hasAgent in builds) {
            val finals = SetupStep.entries.filter { isFinalSetupStep(it, hasAgent) }
            assertEquals(1, finals.size, "exactly one step may be final (hasAgent=$hasAgent)")
            assertEquals(SetupStep.COMPLETE, nextSetupStep(finals.single(), hasAgent))
        }
    }

    @Test
    fun theStepGraphHasNoBranches() {
        // §7: one `when`, not two. The old isNodeFlow fork produced
        // byte-identical transitions on both sides — a duplicate pretending to
        // be a choice. The ONLY legitimate difference between builds is the AI
        // screen, so every other transition must agree.
        for (step in SetupStep.entries) {
            if (step == SetupStep.JOIN_FEDERATION) continue // the one real difference
            assertEquals(
                nextSetupStep(step, hasAgent = true),
                nextSetupStep(step, hasAgent = false),
                "$step must transition identically in both builds",
            )
        }
    }
}

/**
 * What blocks Next on each screen, and — as importantly — what does not.
 */
class SetupStepValidationTest {

    private fun filledOutYouScreen() = SetupFormState(
        currentStep = SetupStep.YOU,
        username = "founder",
        userPassword = "correct-horse",
        userPasswordConfirm = "correct-horse",
        federationIdentity = FederationIdentitySetupState(label = "eric-moore"),
    )

    @Test
    fun screenOneNeedsAFedIdNameAnAccountAndNothingElse() {
        assertTrue(filledOutYouScreen().canProceedFromCurrentStep())
    }

    @Test
    fun screenOneBlocksOnAMissingFedIdName() {
        val state = filledOutYouScreen().copy(federationIdentity = FederationIdentitySetupState())
        assertFalse(state.canProceedFromCurrentStep())
        assertTrue(state.getStepValidationError() != null)
    }

    @Test
    fun screenOneBlocksOnMismatchedPasswords() {
        val state = filledOutYouScreen().copy(userPasswordConfirm = "something-else")
        assertFalse(state.canProceedFromCurrentStep())
    }

    @Test
    fun screenOneDoesNotRequireAnAgeBand() {
        // Declining to state an age sets the protective default; it must not trap.
        assertTrue(filledOutYouScreen().copy(ageRange = AgeRangeSetupState()).canProceedFromCurrentStep())
    }

    @Test
    fun consentScreenNeverBlocks() {
        // Every toggle has a stated default and declining all of them is valid.
        val state = SetupFormState(
            currentStep = SetupStep.JOIN_FEDERATION,
            announceOwnership = false,
            accordMetricsConsent = false,
            traceAnalyze = false,
            shareLocationInTraces = false,
        )
        assertTrue(state.canProceedFromCurrentStep())
        assertEquals(null, state.getStepValidationError())
    }

    @Test
    fun theUntouchedAiDefaultDoesNotProceed() {
        // provider "OpenAI" with no key is the dead end §0.4 describes.
        val state = SetupFormState(currentStep = SetupStep.AI)
        assertFalse(state.canProceedFromCurrentStep())
        assertTrue(state.getStepValidationError() != null)
    }

    @Test
    fun keylessProvidersProceedWithoutAKey() {
        for (provider in listOf("local", "local_inference", "mobile_local", "localai")) {
            val state = SetupFormState(currentStep = SetupStep.AI, llmProvider = provider)
            assertTrue(state.canProceedFromCurrentStep(), "$provider must not require a key")
        }
    }

    @Test
    fun runWithoutAiIsACompleteAnswer() {
        val state = SetupFormState(currentStep = SetupStep.AI, runWithoutAi = true)
        assertTrue(state.canProceedFromCurrentStep())
        assertEquals(null, state.getStepValidationError())
    }

    @Test
    fun aiIsNotOffByDefault() {
        // §3 CRITICAL: an option, never a default.
        assertFalse(SetupFormState().runWithoutAi)
    }

    @Test
    fun announcingAndSharingAreOnByDefault() {
        // Announce is the floor for service; declining it silently unserves the
        // node, so it must not be the default. `analyze` is on but declinable.
        val fresh = SetupFormState()
        assertTrue(fresh.announceOwnership)
        assertTrue(fresh.accordMetricsConsent)
        assertTrue(fresh.traceAnalyze)
        assertFalse(fresh.shareLocationInTraces, "location is required:false and defaults off")
    }

    @Test
    fun theWizardStartsOnScreenOne() {
        assertEquals(SetupStep.YOU, SetupFormState().currentStep)
    }
}
