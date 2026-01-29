package ai.ciris.mobile.shared.models

import kotlinx.serialization.Serializable

/**
 * Setup API models for first-run setup wizard.
 *
 * Source: tools/qa_runner/modules/setup_tests.py
 * API endpoints:
 * - GET /v1/setup/status
 * - GET /v1/setup/providers
 * - GET /v1/setup/templates
 * - GET /v1/setup/adapters
 * - POST /v1/setup/validate-llm
 * - POST /v1/setup/complete
 */

// ========== GET /v1/setup/status ==========
// Source: android/app/src/main/java/ai/ciris/mobile/MainActivity.kt:1888-1891

/**
 * Response from GET /v1/setup/status
 * Wrapped in standard SuccessResponse format: {"data": {...}, "metadata": {...}}
 */
@Serializable
data class SetupStatusResponse(
    val data: SetupStatusData,
    val metadata: Map<String, String> = emptyMap()
)

@Serializable
data class SetupStatusData(
    val setup_required: Boolean,
    val has_env_file: Boolean = false,
    val has_admin_user: Boolean = false
)

// ========== GET /v1/setup/providers ==========

/**
 * Response from GET /v1/setup/providers
 * Lists available LLM providers (OpenAI, Anthropic, local, etc)
 */
@Serializable
data class LlmProvider(
    val id: String,          // "openai", "anthropic", "local", "other"
    val name: String,        // "OpenAI", "Anthropic", "LocalAI", "Azure OpenAI"
    val requires_api_key: Boolean = true,
    val supports_base_url: Boolean = false,
    val default_base_url: String? = null,
    val default_model: String? = null
)

// ========== GET /v1/setup/templates ==========
// Source: tools/qa_runner/modules/setup_tests.py:42-66

/**
 * Response from GET /v1/setup/templates
 * Lists available agent identity templates.
 *
 * Required templates (validated by QA):
 * - "default" (name: "Datum")
 * - "ally" (name: "Ally")
 * - Minimum 5 templates total
 */
@Serializable
data class AgentTemplate(
    val id: String,          // "default", "ally", "sage", "scout", "echo"
    val name: String,        // "Datum", "Ally", "Sage", "Scout", "Echo"
    val description: String,
    val personality: String? = null,
    val capabilities: List<String> = emptyList()
)

// ========== GET /v1/setup/adapters ==========

/**
 * Response from GET /v1/setup/adapters
 * Lists available communication adapters with platform requirements.
 * KMP client filters these based on local platform capabilities.
 */
@Serializable
data class CommunicationAdapter(
    val id: String,          // "api", "cli", "discord", "reddit"
    val name: String,        // "REST API", "Command Line", "Discord", "Reddit"
    val description: String,
    val requires_config: Boolean = false,
    val config_fields: List<String> = emptyList(),
    // Platform requirements for KMP-side filtering
    val requires_binaries: Boolean = false,           // Requires external CLI tools (not available on mobile)
    val required_binaries: List<String> = emptyList(), // Specific binary names if requires_binaries=true
    val supported_platforms: List<String> = emptyList(), // Empty = all, otherwise ["android", "ios", "desktop"]
    val requires_ciris_services: Boolean = false,     // Requires CIRIS AI services (Google sign-in)
    val enabled_by_default: Boolean = false
)

// ========== POST /v1/setup/validate-llm ==========

/**
 * Request to POST /v1/setup/validate-llm
 * Tests LLM connection before completing setup.
 */
@Serializable
data class ValidateLlmRequest(
    val provider: String,        // "openai", "anthropic", "local", "other"
    val api_key: String,
    val base_url: String? = null,
    val model: String? = null
)

/**
 * Response from POST /v1/setup/validate-llm
 * Returns whether the LLM connection is valid.
 */
@Serializable
data class ValidateLlmResponse(
    val valid: Boolean,
    val error: String? = null,
    val model_used: String? = null
)

// ========== Setup Complete Response wrapper ==========
// Python API returns responses wrapped in SuccessResponse format

/**
 * Metadata from Python SuccessResponse
 */
@Serializable
data class ResponseMetadata(
    val timestamp: String? = null,
    val request_id: String? = null,
    val duration_ms: Int? = null
)

/**
 * Wrapper for setup complete API response
 * Python returns: {"data": {...}, "metadata": {...}}
 */
@Serializable
data class SetupCompleteSuccessResponse(
    val data: CompleteSetupResponseData,
    val metadata: ResponseMetadata = ResponseMetadata()
)

// ========== POST /v1/setup/complete ==========
// Source: android/app/src/main/java/ai/ciris/mobile/setup/SetupWizardActivity.kt:395-500

/**
 * Request to POST /v1/setup/complete
 * Completes first-run setup with full configuration.
 *
 * Example payload from SetupWizardActivity.kt:
 * - CIRIS Proxy mode: provider="other", api_key=googleIdToken, base_url=llm.ciris.ai
 * - BYOK mode: provider="openai", api_key=user_key, base_url=null
 */
@Serializable
data class CompleteSetupRequest(
    // LLM configuration
    val llm_provider: String,              // "openai", "anthropic", "local", "other"
    val llm_api_key: String,
    val llm_base_url: String? = null,
    val llm_model: String? = null,

    // Backup LLM (optional, for CIRIS proxy)
    val backup_llm_api_key: String? = null,
    val backup_llm_base_url: String? = null,
    val backup_llm_model: String? = null,

    // Agent identity
    val template_id: String,               // "ally", "default", etc

    // Communication adapters
    val enabled_adapters: List<String>,    // ["api"]
    val adapter_config: Map<String, String> = emptyMap(),
    val agent_port: Int = 8080,

    // Admin account (auto-generated, users don't set this)
    val system_admin_password: String,

    // User account
    val admin_username: String,
    val admin_password: String? = null,    // Optional for OAuth users

    // OAuth configuration (for Google users)
    val oauth_provider: String? = null,    // "google"
    val oauth_external_id: String? = null, // Google user ID
    val oauth_email: String? = null        // Google email
)

/**
 * Response data from POST /v1/setup/complete
 * Wrapped in SuccessResponse format: {"data": {...}, "metadata": {...}}
 *
 * Python returns:
 * - status: "completed" (success indicator)
 * - message: Human-readable status message
 * - config_path: Path where config was saved
 * - username: Created admin username
 * - next_steps: Instructions for the user
 */
@Serializable
data class CompleteSetupResponseData(
    val status: String,
    val message: String,
    val config_path: String? = null,
    val username: String? = null,
    val next_steps: String? = null
) {
    /**
     * Check if setup was successful
     * Maps Python's "status": "completed" to success boolean
     */
    val success: Boolean
        get() = status == "completed"
}

// ========== KMP Adapter Filtering ==========

/**
 * Platform types for adapter filtering.
 */
enum class Platform {
    ANDROID,
    IOS,
    DESKTOP
}

/**
 * Filter adapters based on platform capabilities.
 *
 * This filtering is done on the KMP client side to support both iOS and Android.
 * The server returns ALL adapters with their requirements; we filter locally.
 *
 * @param adapters List of all adapters from the server
 * @param platform Current platform (android, ios, or desktop)
 * @param useCirisServices Whether user is using CIRIS AI services (signed in with Google)
 * @return Filtered list of adapters available on this platform
 */
fun filterAdaptersForPlatform(
    adapters: List<CommunicationAdapter>,
    platform: Platform,
    useCirisServices: Boolean
): List<CommunicationAdapter> {
    val platformName = when (platform) {
        Platform.ANDROID -> "android"
        Platform.IOS -> "ios"
        Platform.DESKTOP -> "desktop"
    }
    val isMobile = platform == Platform.ANDROID || platform == Platform.IOS

    return adapters.filter { adapter ->
        // Rule 1: If adapter requires binaries, exclude on mobile platforms
        // Mobile can't run CLI tools like git, docker, etc.
        if (adapter.requires_binaries && isMobile) {
            return@filter false
        }

        // Rule 2: If adapter has supported_platforms specified, check if current platform is in list
        // Empty list means all platforms are supported
        if (adapter.supported_platforms.isNotEmpty()) {
            if (platformName !in adapter.supported_platforms) {
                return@filter false
            }
        }

        // Rule 3: If adapter requires CIRIS AI services, only include if user has them
        if (adapter.requires_ciris_services && !useCirisServices) {
            return@filter false
        }

        true
    }
}
