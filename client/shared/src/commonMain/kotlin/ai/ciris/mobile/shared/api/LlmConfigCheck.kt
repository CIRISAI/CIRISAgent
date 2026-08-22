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
 *
 * ORDERING — and why it is not simply "validate then list":
 *
 * `validateLlmConfiguration` (POST /v1/setup/validate-llm) REFUSES a probe that
 * names no model: since CIRISAgent#1078 ("a credential probe must not assume a
 * model") it returns `valid=false, "No model selected"` when `model` is empty.
 * That is correct for the pipeline probe, but it means validate cannot be the
 * key gate on a FRESH setup — no model is chosen until the dropdown loads, and
 * the dropdown loads from `listModels`, so gating listing behind a validate that
 * demands a model is an unbreakable chicken-and-egg (CIRISAgent#1062 follow-up:
 * the wizard showed "No model selected" and never populated the dropdown).
 *
 * So the gate depends on whether we already have a model to name:
 *   - model in hand  -> validate it first (it may be a model the provider does
 *     not serve, and validate surfaces that precisely); a rejected key still
 *     short-circuits so its error is not buried by a secondary listing error.
 *   - no model yet   -> SKIP validate and let `listModels` be the credential
 *     check. Listing hits the same provider with the same key, so a live list is
 *     itself proof the key authenticates; a thrown error is the real key/reach
 *     failure, reported as such.
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

    val hasModel = !selectedModel.isNullOrBlank()

    // Explicit credential probe ONLY when a model is already named — otherwise
    // #1078 refuses it and we would report a false key failure (see above).
    var validationMessage: String? = null
    if (hasModel) {
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
        validationMessage = validation.message
    }

    val listed = try {
        listModels(provider = provider, apiKey = apiKey, baseUrl = baseUrl)
    } catch (e: Exception) {
        // With a model already validated the key is known good, so a listing
        // error is purely a models failure. Without one, listing WAS the key
        // check, so its failure is the key's.
        return LlmConfigCheck(
            key = if (hasModel) CheckState.OK else CheckState.FAILED,
            keyMessage = if (hasModel) validationMessage else (e.message ?: "The API key was rejected or the provider is unreachable."),
            models = if (hasModel) CheckState.FAILED else CheckState.UNKNOWN,
            modelsMessage = if (hasModel) (e.message ?: "Could not list models.") else null,
        )
    }

    val modelsState = when {
        listed.isLive && listed.models.isNotEmpty() -> CheckState.OK
        listed.models.isEmpty() -> CheckState.FAILED
        else -> CheckState.DEGRADED
    }

    // On the no-model path a LIVE list is proof the key authenticates; a
    // non-live/empty list can't distinguish a bad key from a provider hiccup, so
    // leave the key UNKNOWN and let the models row carry the detail.
    val keyState = when {
        hasModel -> CheckState.OK
        modelsState == CheckState.OK -> CheckState.OK
        else -> CheckState.UNKNOWN
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
        key = keyState,
        keyMessage = validationMessage,
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
