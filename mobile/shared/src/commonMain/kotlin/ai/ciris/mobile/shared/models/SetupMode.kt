package ai.ciris.mobile.shared.models

import kotlinx.serialization.Serializable

/**
 * Setup mode determines how LLM access is configured.
 *
 * Source: android/app/src/main/java/ai/ciris/mobile/setup/SetupViewModel.kt:35-38
 *
 * - CIRIS_PROXY: Free AI via CIRIS hosted proxy (requires Google OAuth)
 *   Uses Google ID token with llm01.ciris-services-* proxy
 *
 * - BYOK: Bring Your Own Key
 *   User provides their own API key from OpenAI/Anthropic/etc
 *
 * - LOCAL_ON_DEVICE: Run Gemma 4 via the `mobile_local_llm` adapter
 *   directly on the phone. Only offered in the wizard when the
 *   [ai.ciris.mobile.shared.platform.probeLocalInferenceCapability]
 *   probe reports a capable device. On iOS this option is shown
 *   as "coming soon" until an adequate LiteRT-LM model ships.
 */
@Serializable
enum class SetupMode {
    /**
     * Free AI via CIRIS proxy - requires Google OAuth.
     * Google ID token is used to access llm01.ciris-services-* proxy.
     */
    CIRIS_PROXY,

    /**
     * Bring Your Own Key - user provides their own LLM API key.
     * Supports OpenAI, Anthropic, Azure OpenAI, LocalAI, etc.
     */
    BYOK,

    /**
     * On-device inference via the Mobile Local LLM adapter.
     * Only available on phones whose capability probe returns a
     * CAPABLE_E2B or CAPABLE_E4B tier. Selecting this mode sets
     * `CIRIS_MOBILE_LOCAL_LLM_ENABLED=true` so the Python runtime
     * spawns the on-device inference server on next restart.
     */
    LOCAL_ON_DEVICE
}
