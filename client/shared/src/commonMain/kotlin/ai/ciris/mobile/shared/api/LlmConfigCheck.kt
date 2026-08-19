package ai.ciris.mobile.shared.api

import ai.ciris.mobile.shared.viewmodels.ModelInfo

/**
 * ONE way to ask "is this LLM configuration actually going to work?".
 *
 * CIRISAgent#1062 and its follow-ups. Two screens configure an LLM provider —
 * the setup wizard and LLM settings — and they did NOT do the same thing. The
 * wizard called `validateLlmConfiguration` (does the key authenticate?) and then
 * `listModels`. Settings called only `listModels`. So a user could open Settings,
 * look at a provider whose key had been revoked, see a model dropdown, and get no
 * indication whatsoever that nothing there would work.
 *
 * That is not hypothetical. A user ran for days against a Groq key returning
 * `401 Invalid API Key`, with both his providers additionally pointed at models
 * Groq does not serve (`gpt-4o-mini` and the literal string `default`). Three
 * independent things were wrong and no screen showed the state of any of them.
 *
 * So the check reports those three facts SEPARATELY, because they fail
 * separately and they need different fixes:
 *
 *   key    — does the credential authenticate at all?      -> rotate it
 *   models — did the provider give us a LIVE list?          -> connectivity/permissions
 *   model  — is the SELECTED model in that live list?       -> pick another one
 *
 * A single "valid / invalid" verdict cannot express "your key is fine but that
 * model does not exist there", which is exactly one of the two failures above.
 */

/** State of one checkable fact, for rendering as an icon next to its field. */
enum class CheckState {
    /** Not checked yet — no key entered, or nothing asked for. */
    UNKNOWN,

    /** In flight. */
    CHECKING,

    /** Confirmed good by the provider. */
    OK,

    /** Confirmed bad by the provider — actionable, with a reason. */
    FAILED,

    /**
     * Works, but not on evidence from the provider — e.g. models came from
     * cached static data rather than a live query. Never render this as OK:
     * presenting cached data as the provider's catalogue is what let a user
     * select a model his provider had never heard of.
     */
    DEGRADED,
}

/**
 * The answer, with a reason for anything that is not OK.
 *
 * Every non-OK state carries its own message so the UI never has to invent one.
 * The provider's own words ("Invalid API Key", "The model `default` does not
 * exist") are far better than anything we would write.
 */
data class LlmConfigCheck(
    val key: CheckState = CheckState.UNKNOWN,
    val keyMessage: String? = null,
    val models: CheckState = CheckState.UNKNOWN,
    val modelsMessage: String? = null,
    val selectedModel: CheckState = CheckState.UNKNOWN,
    val selectedModelMessage: String? = null,
    val availableModels: List<ModelInfo> = emptyList(),
) {
    /** True only when every checked fact is good. Degraded is NOT usable. */
    val usable: Boolean
        get() = key == CheckState.OK &&
            models == CheckState.OK &&
            (selectedModel == CheckState.OK || selectedModel == CheckState.UNKNOWN)

    /** The first thing the user should fix, or null when nothing is wrong. */
    val firstProblem: String?
        get() = when {
            key == CheckState.FAILED -> keyMessage ?: "The API key was rejected."
            models == CheckState.FAILED -> modelsMessage ?: "Could not list models."
            selectedModel == CheckState.FAILED ->
                selectedModelMessage ?: "The selected model is not available from this provider."
            models == CheckState.DEGRADED -> modelsMessage ?: "Showing cached models, not this provider's."
            else -> null
        }

    companion object {
        /** Everything in flight — render spinners rather than stale verdicts. */
        fun checking(): LlmConfigCheck = LlmConfigCheck(
            key = CheckState.CHECKING,
            models = CheckState.CHECKING,
            selectedModel = CheckState.CHECKING,
        )
    }
}

/**
 * Run the whole check against a provider's real endpoint.
 *
 * Both the wizard and LLM settings call THIS, so they cannot drift apart again.
 * Ordered deliberately: the key is checked first, and a rejected key
 * short-circuits, because "list models" against a bad credential returns a
 * confusing secondary error that buries the real one.
 */
suspend fun CIRISApiClient.checkLlmConfig(
    provider: String,
    apiKey: String,
    baseUrl: String? = null,
    selectedModel: String? = null,
): LlmConfigCheck {
    // A local server is handed a dummy key on purpose, so an empty key is only
    // a problem for a remote provider.
    val needsKey = provider != "local" && provider != "local_ondevice"
    if (needsKey && apiKey.isBlank()) {
        return LlmConfigCheck(
            key = CheckState.UNKNOWN,
            keyMessage = "Enter an API key to check this provider.",
        )
    }

    val validation = try {
        validateLlmConfiguration(provider = provider, apiKey = apiKey, baseUrl = baseUrl, model = selectedModel)
    } catch (e: Exception) {
        return LlmConfigCheck(
            key = CheckState.FAILED,
            keyMessage = e.message ?: "Could not reach the provider.",
        )
    }

    if (!validation.valid) {
        // Stop here on purpose. Listing models with a rejected credential
        // produces a second, less informative error that hides the first.
        return LlmConfigCheck(
            key = CheckState.FAILED,
            keyMessage = validation.error ?: validation.message,
        )
    }

    val listed = try {
        listModels(provider = provider, apiKey = apiKey, baseUrl = baseUrl)
    } catch (e: Exception) {
        return LlmConfigCheck(
            key = CheckState.OK,
            keyMessage = validation.message,
            models = CheckState.FAILED,
            modelsMessage = e.message ?: "Could not list models.",
        )
    }

    val modelsState = when {
        listed.isLive && listed.models.isNotEmpty() -> CheckState.OK
        listed.models.isEmpty() -> CheckState.FAILED
        else -> CheckState.DEGRADED
    }

    // Only judge the selected model against a LIVE list. Marking it missing
    // because a cached list lacks it would be a false accusation.
    val selectedState = when {
        selectedModel.isNullOrBlank() -> CheckState.UNKNOWN
        modelsState != CheckState.OK -> CheckState.UNKNOWN
        listed.models.any { it.id == selectedModel } -> CheckState.OK
        else -> CheckState.FAILED
    }

    return LlmConfigCheck(
        key = CheckState.OK,
        keyMessage = validation.message,
        models = modelsState,
        modelsMessage = listed.error,
        selectedModel = selectedState,
        selectedModelMessage = if (selectedState == CheckState.FAILED) {
            "\"$selectedModel\" is not offered by this provider. Pick one from the list."
        } else {
            null
        },
        availableModels = listed.models,
    )
}
