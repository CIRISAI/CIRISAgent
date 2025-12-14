package ai.ciris.mobile.config

/**
 * Centralized configuration for all CIRIS service endpoints.
 *
 * Update these values when migrating to new infrastructure.
 * All endpoint URLs should be defined here - no hardcoded URLs elsewhere.
 */
object CIRISConfig {

    // ==================== REGION SELECTION ====================

    /**
     * Available service regions.
     * - PRIMARY: Americas, Oceania
     * - SECONDARY: Europe, Africa, Asia
     */
    enum class Region {
        PRIMARY,    // ciris-services-1.ai
        SECONDARY   // ciris-services-2.ai
    }

    /**
     * Current active region. Change this to switch all services.
     * In the future, this could be auto-selected based on latency.
     */
    var activeRegion: Region = Region.PRIMARY

    // ==================== BILLING API ====================

    private const val BILLING_HOST_PRIMARY = "billing1.ciris-services-1.ai"
    private const val BILLING_HOST_SECONDARY = "billing1.ciris-services-2.ai"

    /**
     * Get the billing API base URL for the active region.
     */
    fun getBillingApiUrl(): String {
        val host = when (activeRegion) {
            Region.PRIMARY -> BILLING_HOST_PRIMARY
            Region.SECONDARY -> BILLING_HOST_SECONDARY
        }
        return "https://$host"
    }

    /**
     * Get billing API URL for a specific region.
     */
    fun getBillingApiUrl(region: Region): String {
        val host = when (region) {
            Region.PRIMARY -> BILLING_HOST_PRIMARY
            Region.SECONDARY -> BILLING_HOST_SECONDARY
        }
        return "https://$host"
    }

    // ==================== LLM PROXY ====================

    private const val LLM_PROXY_HOST_PRIMARY = "proxy1.ciris-services-1.ai"
    private const val LLM_PROXY_HOST_SECONDARY = "proxy1.ciris-services-2.ai"

    /**
     * Get the LLM proxy base URL for the active region.
     * This is OpenAI-compatible and used as OPENAI_API_BASE.
     */
    fun getLLMProxyUrl(): String {
        val host = when (activeRegion) {
            Region.PRIMARY -> LLM_PROXY_HOST_PRIMARY
            Region.SECONDARY -> LLM_PROXY_HOST_SECONDARY
        }
        return "https://$host/v1"
    }

    /**
     * Get LLM proxy URL for a specific region.
     */
    fun getLLMProxyUrl(region: Region): String {
        val host = when (region) {
            Region.PRIMARY -> LLM_PROXY_HOST_PRIMARY
            Region.SECONDARY -> LLM_PROXY_HOST_SECONDARY
        }
        return "https://$host/v1"
    }

    // ==================== AGENTS API ====================

    private const val AGENTS_HOST_PRIMARY = "agents.ciris-services-1.ai"
    private const val AGENTS_HOST_SECONDARY = "agents.ciris-services-2.ai"

    /**
     * Get the agents API base URL for the active region.
     */
    fun getAgentsApiUrl(): String {
        val host = when (activeRegion) {
            Region.PRIMARY -> AGENTS_HOST_PRIMARY
            Region.SECONDARY -> AGENTS_HOST_SECONDARY
        }
        return "https://$host"
    }

    // ==================== LENS API ====================

    private const val LENS_HOST_PRIMARY = "lens.ciris-services-1.ai"

    /**
     * Get the Lens API base URL (currently primary region only).
     */
    fun getLensApiUrl(): String {
        return "https://$LENS_HOST_PRIMARY"
    }

    // ==================== GOOGLE OAUTH ====================

    /**
     * Google OAuth Web Client ID.
     * Used for ID token requests (requestIdToken in GoogleSignInOptions).
     */
    const val GOOGLE_WEB_CLIENT_ID = "265882853697-l421ndojcs5nm7lkln53jj29kf7kck91.apps.googleusercontent.com"

    /**
     * Google OAuth Android Client ID.
     * Auto-detected by Google Play Services based on package signature.
     */
    const val GOOGLE_ANDROID_CLIENT_ID = "265882853697-vqfv6ecjgc1ku7n6bm4hllg6csdiaild.apps.googleusercontent.com"

    /**
     * Android package name for OAuth configuration.
     */
    const val PACKAGE_NAME = "ai.ciris.mobile"

    // ==================== LEGACY ENDPOINTS ====================
    // Keep these for backward compatibility during migration

    /**
     * Legacy billing endpoint (deprecated - use getBillingApiUrl()).
     */
    @Deprecated("Use getBillingApiUrl() instead", ReplaceWith("getBillingApiUrl()"))
    const val LEGACY_BILLING_URL = "https://billing.ciris.ai"

    /**
     * Legacy LLM proxy endpoint (deprecated - use getLLMProxyUrl()).
     */
    @Deprecated("Use getLLMProxyUrl() instead", ReplaceWith("getLLMProxyUrl()"))
    const val LEGACY_LLM_PROXY_URL = "https://llm.ciris.ai"

    /**
     * Legacy agents endpoint (deprecated - use getAgentsApiUrl()).
     */
    @Deprecated("Use getAgentsApiUrl() instead", ReplaceWith("getAgentsApiUrl()"))
    const val LEGACY_AGENTS_URL = "https://agents.ciris.ai"

    // ==================== UTILITY ====================

    /**
     * All LLM proxy hostnames (for detecting CIRIS proxy mode in .env files).
     */
    val LLM_PROXY_HOSTNAMES = listOf(
        LLM_PROXY_HOST_PRIMARY,
        LLM_PROXY_HOST_SECONDARY,
        "llm.ciris.ai",      // Legacy
        "api.ciris.ai"       // Legacy
    )

    /**
     * Check if a URL is a CIRIS LLM proxy URL.
     */
    fun isCirisProxyUrl(url: String): Boolean {
        return LLM_PROXY_HOSTNAMES.any { url.contains(it) }
    }

    /**
     * All billing hostnames (for URL detection).
     */
    val BILLING_HOSTNAMES = listOf(
        BILLING_HOST_PRIMARY,
        BILLING_HOST_SECONDARY,
        "billing.ciris.ai"   // Legacy
    )

    /**
     * Check if a URL is a CIRIS billing URL.
     */
    fun isCirisBillingUrl(url: String): Boolean {
        return BILLING_HOSTNAMES.any { url.contains(it) }
    }

    // ==================== ENV MIGRATION ====================

    /**
     * Legacy URL to new infrastructure URL mappings.
     */
    private val LEGACY_URL_MIGRATIONS = mapOf(
        // LLM Proxy migrations
        "https://llm.ciris.ai/v1" to "https://proxy1.ciris-services-1.ai/v1",
        "https://llm.ciris.ai" to "https://proxy1.ciris-services-1.ai/v1",
        "https://api.ciris.ai/v1" to "https://proxy1.ciris-services-1.ai/v1",
        "https://api.ciris.ai" to "https://proxy1.ciris-services-1.ai/v1",
        // Billing migrations
        "https://billing.ciris.ai" to "https://billing1.ciris-services-1.ai"
    )

    /**
     * Migrate .env content from legacy infrastructure URLs to new ciris-services URLs.
     *
     * @param envContent The current .env file content
     * @return Pair of (migratedContent, wasModified)
     */
    fun migrateEnvToNewInfra(envContent: String): Pair<String, Boolean> {
        var content = envContent
        var wasModified = false

        for ((legacyUrl, newUrl) in LEGACY_URL_MIGRATIONS) {
            if (content.contains(legacyUrl)) {
                content = content.replace(legacyUrl, newUrl)
                wasModified = true
            }
        }

        return Pair(content, wasModified)
    }

    /**
     * Check if .env content contains any legacy URLs that need migration.
     */
    fun needsInfraMigration(envContent: String): Boolean {
        return LEGACY_URL_MIGRATIONS.keys.any { envContent.contains(it) }
    }
}
