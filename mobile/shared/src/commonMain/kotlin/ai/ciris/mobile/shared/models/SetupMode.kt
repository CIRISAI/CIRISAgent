package ai.ciris.mobile.shared.models

import kotlinx.serialization.Serializable

/**
 * Setup mode determines how LLM access is configured.
 *
 * Source: android/app/src/main/java/ai/ciris/mobile/setup/SetupViewModel.kt:35-38
 *
 * - CIRIS_PROXY: Free AI via CIRIS hosted proxy (requires Google OAuth)
 *   Uses Google ID token with llm.ciris.ai proxy
 *
 * - BYOK: Bring Your Own Key
 *   User provides their own API key from OpenAI/Anthropic/etc
 */
@Serializable
enum class SetupMode {
    /**
     * Free AI via CIRIS proxy - requires Google OAuth.
     * Google ID token is used to access llm.ciris.ai proxy.
     */
    CIRIS_PROXY,

    /**
     * Bring Your Own Key - user provides their own LLM API key.
     * Supports OpenAI, Anthropic, Azure OpenAI, LocalAI, etc.
     */
    BYOK
}
