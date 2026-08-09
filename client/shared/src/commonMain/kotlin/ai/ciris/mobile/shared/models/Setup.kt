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

// ========== GET /v1/setup/tool-disclosure ==========
//
// Exhaustive, GENERATED disclosure of what each setup choice actually grants the
// agent. Wide tool access is intended -- this surface restricts nothing and
// defaults nothing off. It exists so the operator accepting the (enabled-by-
// default) optional features is told what they are accepting, including the
// tools no choice controls.
//
// Every field originates in a live tool service's get_all_tool_info() on the
// Python side. Nothing here is a transcription, so it cannot drift the way
// ciris_templates/echo.yaml's `moderation_tools` did.

/**
 * A consequential capability a tool grants, derived server-side from the tool's
 * declared parameter shape (not from a name table).
 *
 * Unknown values from a newer server are preserved verbatim so the UI degrades
 * to showing the raw flag rather than silently dropping a disclosure.
 */
object ToolCapabilityFlags {
    const val NETWORK_FETCH = "network_fetch"
    const val CUSTOM_HEADERS = "custom_headers"
    const val REQUEST_BODY = "request_body"
    const val SHELL_EXECUTION = "shell_execution"
    const val FILE_READ = "file_read"
    const val FILE_WRITE = "file_write"
    const val SECRET_PLAINTEXT = "secret_plaintext"
    const val AFFECTS_OTHER_PEOPLE = "affects_other_people"
    const val REQUIRES_APPROVAL = "requires_approval"

    /** Localization key carrying the plain-language sentence for [flag]. */
    fun localizationKey(flag: String): String = "mobile.tool_cap_$flag"

    /**
     * Flags whose consequences the operator is least likely to expect, ordered
     * by how surprising they are. Used to decide what a collapsed summary says.
     */
    val NOTABLE: List<String> = listOf(
        SHELL_EXECUTION,
        SECRET_PLAINTEXT,
        NETWORK_FETCH,
        CUSTOM_HEADERS,
        FILE_WRITE,
        AFFECTS_OTHER_PEOPLE,
        REQUEST_BODY,
        FILE_READ,
        REQUIRES_APPROVAL
    )
}

/** Where a disclosed tool list was read from. Mirrors ToolDisclosureSource. */
object ToolDisclosureSources {
    const val RUNTIME = "runtime"
    const val PROSPECTIVE = "prospective"
    const val UNAVAILABLE = "unavailable"
}

/** One tool, as disclosed at the consent point. */
@Serializable
data class ToolDisclosure(
    val name: String,
    val description: String = "",
    val category: String = "general",
    val model_authored_parameters: List<String> = emptyList(),
    val capability_flags: List<String> = emptyList()
)

/** Every tool one wizard choice grants (or that no choice controls). */
@Serializable
data class AdapterToolDisclosure(
    val adapter_id: String,
    val adapter_name: String = "",
    val always_on: Boolean = false,
    val source: String = ToolDisclosureSources.PROSPECTIVE,
    val source_note: String? = null,
    val tools: List<ToolDisclosure> = emptyList()
)

/** Response from GET /v1/setup/tool-disclosure. */
@Serializable
data class ToolDisclosureReport(
    val adapters: List<AdapterToolDisclosure> = emptyList(),
    val always_on: List<AdapterToolDisclosure> = emptyList(),
    val total_tools: Int = 0
)

/**
 * Find the disclosure for [adapterId], or null if the server sent none.
 *
 * A null result means "not disclosed", never "grants nothing" -- callers MUST
 * render the difference, because showing an empty tool list for an adapter whose
 * grants are unknown is precisely the false assurance this feature exists to
 * remove.
 */
fun ToolDisclosureReport.forAdapter(adapterId: String): AdapterToolDisclosure? =
    adapters.firstOrNull { it.adapter_id == adapterId }

/**
 * Distinct capability flags across [tools], ordered by [ToolCapabilityFlags.NOTABLE]
 * so a collapsed summary leads with the least expected consequence. Flags the
 * client does not know about sort last and are kept, not dropped.
 */
fun summarizeCapabilityFlags(tools: List<ToolDisclosure>): List<String> {
    val present = tools.flatMap { it.capability_flags }.toSet()
    val known = ToolCapabilityFlags.NOTABLE.filter { it in present }
    val unknown = present.filter { it !in ToolCapabilityFlags.NOTABLE }.sorted()
    return known + unknown
}

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
 * - CIRIS Proxy mode: provider="other", api_key=googleIdToken, base_url=llm01.ciris-services-1.ai
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
    val oauth_email: String? = null,       // Google email

    // Language and location preferences (from PREFERENCES step)
    // Mirrors Python: ciris_engine/logic/adapters/api/routes/setup/models.py:296-320
    val preferred_language: String? = null,    // ISO 639-1 code (e.g., "en", "am", "es")
    val location_country: String? = null,      // Country name
    val location_region: String? = null,       // Region/state name
    val location_city: String? = null,         // City name
    val location_latitude: Double? = null,     // Latitude in decimal degrees (ISO 6709)
    val location_longitude: Double? = null,    // Longitude in decimal degrees (ISO 6709)
    val timezone: String? = null,              // IANA timezone (from selected location)
    val share_location_in_traces: Boolean = false,  // Consent to include location in telemetry

    /**
     * CC#46 "be scored" — whether shipped traces may be ANALYZED to build this
     * node's reputation. A separate grant from sending them, `required: false`
     * with named costs, so it carries the owner's toggle. Only consulted when
     * `ciris_accord_metrics` is in [enabled_adapters].
     */
    val trace_analyze: Boolean = true,

    /**
     * The owner chose to run with no LLM. Makes the backend write
     * `CIRIS_SERVICES_DISABLED=true`, which keeps `llm_service` optional on the
     * next boot instead of aborting initialization.
     */
    val run_without_ai: Boolean = false,

    // Node flow fields (Connect to Node / Portal provisioning)
    val node_url: String? = null,                      // Portal URL from node flow
    val identity_template: String? = null,             // Portal-assigned template
    val stewardship_tier: Int? = null,                 // Portal-assigned tier (1-5)
    val approved_adapters: List<String>? = null,       // Portal-approved adapters
    val org_id: String? = null,                        // Organization ID from Portal
    val signing_key_provisioned: Boolean? = null,      // Whether Portal key was provisioned
    val provisioned_signing_key_b64: String? = null,   // Base64 Portal signing key (one-time)
    val signing_key_id: String? = null                  // Portal-issued key ID (saved to .env)
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

// ========== Connect to Node (Device Auth Flow) ==========
// Source: POST /v1/setup/connect-node, GET /v1/setup/connect-node/status

/**
 * Result from POST /v1/setup/connect-node.
 * Contains the RFC 8628 device auth parameters.
 */
@Serializable
data class ConnectNodeResult(
    val verificationUriComplete: String,  // URL for user to open in browser
    val deviceCode: String,               // Opaque code for polling
    val userCode: String,                 // Human-readable code
    val portalUrl: String,                // Portal URL (from node manifest)
    val expiresIn: Int = 900,             // Seconds until expiry
    val interval: Int = 5                 // Polling interval in seconds
)

/**
 * Result from GET /v1/setup/connect-node/status.
 * Returned each time the agent polls for device auth completion.
 */
@Serializable
data class NodeAuthPollResult(
    val status: String,                   // "pending", "complete", "error"
    val template: String? = null,         // Provisioned identity template ID
    val adapters: List<String>? = null,   // Approved adapter list
    val orgId: String? = null,            // Organization ID
    val signingKeyB64: String? = null,    // Base64 Ed25519 private key (one-time)
    val keyId: String? = null,            // Key ID from Registry
    val stewardshipTier: Int? = null,     // Stewardship tier from template
    val error: String? = null             // Error message if status == "error"
)

/**
 * Result from CIRISVerify binary download.
 * TODO: Wire to actual POST /v1/setup/verify/download endpoint.
 * MVP: Stub for UI flow testing.
 */
@Serializable
data class VerifyDownloadResult(
    val binaryPath: String,
    val version: String
)

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
