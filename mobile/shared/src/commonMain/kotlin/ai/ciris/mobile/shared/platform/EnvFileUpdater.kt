package ai.ciris.mobile.shared.platform

import ai.ciris.mobile.shared.config.CIRISConfig

/**
 * Platform-specific utility to read and update the .env file.
 *
 * This is needed for:
 * - Billing authentication - the Python agent reads CIRIS_BILLING_GOOGLE_ID_TOKEN
 * - Settings screen - detecting CIRIS proxy vs BYOK mode
 *
 * Logic extracted from:
 * - android/app/src/main/java/ai/ciris/mobile/auth/TokenRefreshManager.kt (lines 240-334)
 */
expect class EnvFileUpdater {
    /**
     * Update the .env file with a new Google ID token.
     *
     * Updates:
     * - CIRIS_BILLING_GOOGLE_ID_TOKEN (always, for billing)
     * - OPENAI_API_KEY (only if in CIRIS proxy mode, not BYOK)
     *
     * Also triggers Python config reload by writing .config_reload file.
     *
     * @param googleIdToken The fresh Google ID token
     * @return Result with true on success, exception on failure
     */
    suspend fun updateEnvWithToken(googleIdToken: String): Result<Boolean>

    /**
     * Trigger Python to reload its configuration.
     * Writes a timestamp to .config_reload file that Python watches.
     */
    fun triggerConfigReload()

    /**
     * Read LLM configuration from .env file.
     * Used by Settings screen to detect CIRIS proxy vs BYOK mode.
     *
     * @return EnvLlmConfig with parsed values, or null if .env not found
     */
    suspend fun readLlmConfig(): EnvLlmConfig?

    /**
     * Delete the .env file to trigger first-run setup on next app start.
     * Used by "Re-run Setup Wizard" feature.
     *
     * After calling this, the app should be restarted to trigger the setup wizard.
     *
     * @return Result with true on success, exception on failure
     */
    suspend fun deleteEnvFile(): Result<Boolean>
}

/**
 * LLM configuration read from .env file
 */
data class EnvLlmConfig(
    val provider: String,           // "openai", "anthropic", "other", "local"
    val baseUrl: String?,           // OPENAI_API_BASE value
    val model: String?,             // OPENAI_MODEL value
    val apiKeySet: Boolean,         // Whether OPENAI_API_KEY is set (non-empty)
    val isCirisProxy: Boolean       // Whether using CIRIS proxy (based on baseUrl)
)

/**
 * Factory function to create EnvFileUpdater instance
 */
expect fun createEnvFileUpdater(): EnvFileUpdater
