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
 *   User provides their own API key from OpenAI/Anthropic/etc/on-device
 *
 * On-device Gemma 4 inference lives under BYOK as the "mobile_local"
 * provider so it can coexist with other providers: the Python
 * LLMBus picks between installed providers by priority, which means a
 * capable phone can run local-first with cloud fallback (or vice versa)
 * simply by having both adapters loaded.
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
     * Supports OpenAI, Anthropic, Azure OpenAI, LocalAI, on-device
     * Gemma 4 (via the mobile_local_llm adapter), etc.
     */
    BYOK
}
