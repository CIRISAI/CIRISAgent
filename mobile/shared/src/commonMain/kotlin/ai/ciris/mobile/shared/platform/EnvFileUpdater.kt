package ai.ciris.mobile.shared.platform

import ai.ciris.mobile.shared.config.CIRISConfig

/**
 * Platform-specific utility to update the .env file with Google ID tokens.
 *
 * This is needed for billing authentication - the Python agent reads
 * CIRIS_BILLING_GOOGLE_ID_TOKEN from .env to authenticate with the billing service.
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
}

/**
 * Factory function to create EnvFileUpdater instance
 */
expect fun createEnvFileUpdater(): EnvFileUpdater
