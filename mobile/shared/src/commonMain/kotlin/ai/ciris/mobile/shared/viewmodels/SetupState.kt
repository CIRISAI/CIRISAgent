package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.models.CommunicationAdapter
import ai.ciris.mobile.shared.models.SetupMode
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

/**
 * Setup wizard state management.
 *
 * Source: android/app/src/main/java/ai/ciris/mobile/setup/SetupWizardActivity.kt
 * and android/app/src/main/java/ai/ciris/mobile/setup/SetupViewModel.kt
 */

/**
 * Setup wizard steps.
 *
 * Source: SetupWizardActivity.kt:29-32
 * The Android app uses a 3-step wizard:
 * 1. Welcome - Introduction
 * 2. LLM Configuration - Choose CIRIS_PROXY or BYOK mode
 * 3. Confirmation - Summary + account creation (if needed)
 */
enum class SetupStep {
    /**
     * Step 1: Welcome screen with introduction.
     * In node flow, includes "Connect to Node" option.
     */
    WELCOME,

    /**
     * Step 1b (Node flow only): Device auth with CIRISPortal.
     * Agent polls while user authenticates in browser and selects template.
     */
    NODE_AUTH,

    /**
     * Step 2: LLM mode selection (CIRIS_PROXY vs BYOK) and configuration.
     */
    LLM_CONFIGURATION,

    /**
     * Step 3: Optional features - Accord Metrics opt-in for AI alignment research.
     */
    OPTIONAL_FEATURES,

    /**
     * Step 4: Account creation (for non-Google users) and confirmation.
     */
    ACCOUNT_AND_CONFIRMATION,

    /**
     * Step 4b (Node flow only): Optional CIRISVerify download and configuration.
     */
    VERIFY_SETUP,

    /**
     * Final step: Setup is complete.
     */
    COMPLETE
}

/**
 * Device auth state for the "Connect to Node" flow.
 * Tracks the RFC 8628 device authorization session.
 */
@Serializable
data class DeviceAuthState(
    val nodeUrl: String = "",
    val verificationUri: String = "",
    val deviceCode: String = "",
    val userCode: String = "",
    val portalUrl: String = "",
    val status: DeviceAuthStatus = DeviceAuthStatus.IDLE,
    val expiresIn: Int = 900,
    val interval: Int = 5,
    // Provisioned data (set after user completes in Portal)
    val provisionedTemplate: String? = null,
    val provisionedAdapters: List<String> = emptyList(),
    val signingKeyB64: String? = null,
    val keyId: String? = null,
    val orgId: String? = null,
    val stewardshipTier: Int? = null,
    val error: String? = null,
    // Node manifest for display
    val nodeManifest: Map<String, String> = emptyMap()
)

/**
 * Device auth flow status.
 */
@Serializable
enum class DeviceAuthStatus {
    IDLE,           // Not started
    CONNECTING,     // Fetching node manifest + initiating device auth
    WAITING,        // Waiting for user to complete in browser
    COMPLETE,       // User completed, key provisioned
    ERROR           // Something went wrong
}

/**
 * CIRISVerify setup state for the optional verification step.
 */
@Serializable
data class VerifySetupState(
    val enabled: Boolean = false,
    val downloading: Boolean = false,
    val downloaded: Boolean = false,
    val binaryPath: String? = null,
    val version: String? = null,
    val requireHardware: Boolean = false,
    val error: String? = null
)

/**
 * Form state for the setup wizard.
 *
 * Source: SetupViewModel.kt:15-167
 * Tracks all user inputs and Google OAuth state.
 */
@Serializable
data class SetupFormState(
    // Current step in the wizard
    val currentStep: SetupStep = SetupStep.WELCOME,

    // Node flow flag: when true, step sequence is modified
    // WELCOME → NODE_AUTH → LLM_CONFIGURATION → OPTIONAL_FEATURES → COMPLETE
    val isNodeFlow: Boolean = false,

    // Device auth state (Connect to Node flow)
    val deviceAuth: DeviceAuthState = DeviceAuthState(),

    // CIRISVerify setup state (node flow only)
    val verifySetup: VerifySetupState = VerifySetupState(),

    // Google OAuth state
    val isGoogleAuth: Boolean = false,
    val googleIdToken: String? = null,
    val googleEmail: String? = null,
    val googleUserId: String? = null,

    // LLM mode selection (CIRIS_PROXY or BYOK)
    val setupMode: SetupMode? = null,

    // LLM configuration (for BYOK mode)
    val llmProvider: String = "OpenAI",      // "OpenAI", "Anthropic", "LocalAI", "Azure OpenAI"
    val llmApiKey: String = "",
    val llmBaseUrl: String = "",
    val llmModel: String = "",

    // User account (for non-Google users only)
    val username: String = "",
    val email: String = "",
    val userPassword: String = "",

    // Accord Metrics opt-in (for AI alignment research)
    // Data shared: reasoning scores, decision patterns, LLM provider/API base URL
    // No message content or PII is ever sent
    val accordMetricsConsent: Boolean = false,

    // V1.9.7: Template selection (Advanced Settings)
    val availableTemplates: List<AgentTemplateInfo> = emptyList(),
    val selectedTemplateId: String = "default",
    val showAdvancedSettings: Boolean = false,
    val templatesLoading: Boolean = false,

    // Adapter configuration
    // Available adapters from /v1/setup/adapters
    val availableAdapters: List<CommunicationAdapter> = emptyList(),
    // IDs of adapters that will be enabled (api is always included)
    val enabledAdapterIds: Set<String> = setOf("api"),
    // Loading state for adapter list
    val adaptersLoading: Boolean = false,

    // Validation state
    val isValidating: Boolean = false,
    val validationError: String? = null,

    // Submission state
    val isSubmitting: Boolean = false,
    val submissionError: String? = null
) {
    /**
     * Check if using CIRIS proxy mode.
     * Source: SetupViewModel.kt:125-127
     */
    fun useCirisProxy(): Boolean {
        return setupMode == SetupMode.CIRIS_PROXY
    }

    /**
     * Check if local user account fields should be shown.
     * Source: SetupViewModel.kt:133-135
     */
    fun showLocalUserFields(): Boolean {
        return !isGoogleAuth
    }

    /**
     * Check if current step is valid and can proceed to next.
     * Source: SetupWizardActivity.kt:209-286
     */
    fun canProceedFromCurrentStep(): Boolean {
        return when (currentStep) {
            SetupStep.WELCOME -> true

            SetupStep.NODE_AUTH -> {
                // Can proceed when device auth is complete
                deviceAuth.status == DeviceAuthStatus.COMPLETE
            }

            SetupStep.LLM_CONFIGURATION -> {
                if (setupMode == SetupMode.CIRIS_PROXY) {
                    // CIRIS proxy mode - need Google auth token
                    googleIdToken != null
                } else if (setupMode == SetupMode.BYOK) {
                    // BYOK mode - need provider and API key (unless LocalAI)
                    if (llmProvider == "LocalAI") {
                        true
                    } else {
                        llmApiKey.isNotEmpty()
                    }
                } else {
                    false // No mode selected
                }
            }

            SetupStep.OPTIONAL_FEATURES -> {
                // Optional features step - always valid (consent is optional)
                true
            }

            SetupStep.ACCOUNT_AND_CONFIRMATION -> {
                if (isGoogleAuth) {
                    // Google user - no account creation needed
                    true
                } else {
                    // Local user - validate username/password
                    username.isNotEmpty() && userPassword.length >= 8
                }
            }

            SetupStep.VERIFY_SETUP -> {
                // CIRISVerify setup is optional — always can proceed
                true
            }

            SetupStep.COMPLETE -> true
        }
    }

    /**
     * Get validation error for current step.
     * Source: SetupWizardActivity.kt:209-286
     */
    fun getStepValidationError(): String? {
        return when (currentStep) {
            SetupStep.WELCOME -> null

            SetupStep.NODE_AUTH -> {
                when (deviceAuth.status) {
                    DeviceAuthStatus.ERROR -> deviceAuth.error ?: "Device authorization failed"
                    DeviceAuthStatus.IDLE -> "Enter a node URL to connect"
                    DeviceAuthStatus.CONNECTING -> "Connecting to node..."
                    DeviceAuthStatus.WAITING -> "Waiting for authorization in browser..."
                    DeviceAuthStatus.COMPLETE -> null
                }
            }

            SetupStep.LLM_CONFIGURATION -> {
                when {
                    setupMode == null -> "Please select an AI mode"
                    setupMode == SetupMode.CIRIS_PROXY && googleIdToken == null ->
                        "Google sign-in required for free AI"
                    setupMode == SetupMode.BYOK && llmProvider != "LocalAI" && llmApiKey.isEmpty() ->
                        "API Key is required"
                    else -> null
                }
            }

            SetupStep.OPTIONAL_FEATURES -> {
                // Optional features - no validation required (consent is optional)
                null
            }

            SetupStep.ACCOUNT_AND_CONFIRMATION -> {
                if (!isGoogleAuth) {
                    when {
                        username.isEmpty() -> "Username is required"
                        userPassword.isEmpty() -> "Password is required"
                        userPassword.length < 8 -> "Password must be at least 8 characters"
                        else -> null
                    }
                } else {
                    null
                }
            }

            SetupStep.VERIFY_SETUP -> null

            SetupStep.COMPLETE -> null
        }
    }
}

/**
 * Result of LLM validation test.
 * Source: POST /v1/setup/validate-llm
 */
@Serializable
data class LlmValidationResult(
    val valid: Boolean,
    val message: String,
    val error: String? = null
)

/**
 * Model info from provider's live API.
 * Source: POST /v1/setup/list-models
 */
@Serializable
data class ModelInfo(
    val id: String,
    val displayName: String,
    val cirisCompatible: Boolean = false,
    val cirisRecommended: Boolean = false,
    val contextWindow: Int? = null
)

/**
 * Result of setup completion.
 * Source: POST /v1/setup/complete
 */
@Serializable
data class SetupCompletionResult(
    val success: Boolean,
    val message: String,
    val agentId: String? = null,
    val adminUserId: String? = null,
    val error: String? = null
)

/**
 * Agent template info for display in setup wizard.
 * Source: GET /v1/setup/templates
 */
@Serializable
data class AgentTemplateInfo(
    val id: String,
    val name: String,
    val description: String
)

/**
 * CIRISVerify status response for Trust and Security card.
 * Source: GET /v1/setup/verify-status
 *
 * CIRISVerify is REQUIRED for CIRIS 2.0+ agents. Without it, agents cannot
 * operate as they need cryptographic identity verification.
 */
@Serializable
data class VerifyStatusResponse(
    /** Whether CIRISVerify library is loaded */
    val loaded: Boolean,
    /** CIRISVerify version if loaded */
    val version: String? = null,
    /** Hardware security type (TPM_2_0, SECURE_ENCLAVE, SOFTWARE_ONLY, etc.) */
    @SerialName("hardware_type")
    val hardwareType: String? = null,
    /** Key status: 'none', 'ephemeral', 'portal_pending', 'portal_active' */
    @SerialName("key_status")
    val keyStatus: String = "none",
    /** Portal-issued key ID if activated */
    @SerialName("key_id")
    val keyId: String? = null,
    /** Attestation: 'not_attempted', 'pending', 'verified', 'failed' */
    @SerialName("attestation_status")
    val attestationStatus: String = "not_attempted",
    /** Error message if verify failed to load */
    val error: String? = null,
    /** Detailed diagnostic info for troubleshooting */
    @SerialName("diagnostic_info")
    val diagnosticInfo: String? = null,
    /** Trust and security disclaimer text */
    val disclaimer: String = "CIRISVerify provides cryptographic attestation of agent identity.",

    // === Attestation Level Checks ===
    /** CIRIS DNS connectivity (US) */
    @SerialName("dns_us_ok")
    val dnsUsOk: Boolean = false,
    /** CIRIS DNS connectivity (EU) */
    @SerialName("dns_eu_ok")
    val dnsEuOk: Boolean = false,
    /** CIRIS HTTPS connectivity (US) */
    @SerialName("https_us_ok")
    val httpsUsOk: Boolean = false,
    /** CIRIS HTTPS connectivity (EU) */
    @SerialName("https_eu_ok")
    val httpsEuOk: Boolean = false,
    /** CIRISVerify binary loaded and functional */
    @SerialName("binary_ok")
    val binaryOk: Boolean = false,
    /** File integrity verified */
    @SerialName("file_integrity_ok")
    val fileIntegrityOk: Boolean = false,
    /** Signing key registered with Portal/Registry */
    @SerialName("registry_ok")
    val registryOk: Boolean = false,
    /** Audit trail intact */
    @SerialName("audit_ok")
    val auditOk: Boolean = false,
    /** Environment (.env) properly configured */
    @SerialName("env_ok")
    val envOk: Boolean = false,
    /** Google Play Integrity verification passed */
    @SerialName("play_integrity_ok")
    val playIntegrityOk: Boolean = false,
    /** Play Integrity verdict (MEETS_STRONG_INTEGRITY, etc.) */
    @SerialName("play_integrity_verdict")
    val playIntegrityVerdict: String? = null,
    /** Maximum attestation level achieved (0-5) */
    @SerialName("max_level")
    val maxLevel: Int = 0,
    /** True if waiting for device attestation (Play Integrity/App Attest) */
    @SerialName("level_pending")
    val levelPending: Boolean = false,
    /** Attestation mode: 'full' or 'partial' */
    @SerialName("attestation_mode")
    val attestationMode: String = "partial",
    /** Per-check details with ok/label/level */
    val checks: Map<String, CheckDetail>? = null,
    /** Full attestation details from CIRISVerify */
    val details: Map<String, kotlinx.serialization.json.JsonElement>? = null,
    /** Platform OS from attestation */
    @SerialName("platform_os")
    val platformOs: String? = null,
    /** Platform architecture */
    @SerialName("platform_arch")
    val platformArch: String? = null,
    /** Total files in registry manifest */
    @SerialName("total_files")
    val totalFiles: Int? = null,
    /** Number of files checked for integrity */
    @SerialName("files_checked")
    val filesChecked: Int? = null,
    /** Number of files that passed integrity */
    @SerialName("files_passed")
    val filesPassed: Int? = null,
    /** Number of files that failed integrity */
    @SerialName("files_failed")
    val filesFailed: Int? = null,
    /** Reason for integrity failure if any */
    @SerialName("integrity_failure_reason")
    val integrityFailureReason: String? = null,

    // === v0.6.0 Fields ===
    /** Function integrity: verified, tampered, unavailable:{reason}, signature_invalid, not_found, pending */
    @SerialName("function_integrity")
    val functionIntegrity: String? = null,
    /** Per-source error details: {source: {category: str, details: str}} */
    @SerialName("source_errors")
    val sourceErrors: Map<String, SourceErrorDetail>? = null,

    // === v0.7.0 Fields - Enhanced verification details ===
    /** Ed25519 public key fingerprint (SHA-256 hex) */
    @SerialName("ed25519_fingerprint")
    val ed25519Fingerprint: String? = null,
    /** Key storage mode: SOFTWARE, HARDWARE_BACKED, or specific provider */
    @SerialName("key_storage_mode")
    val keyStorageMode: String? = null,
    /** Whether the key is hardware-backed (Secure Enclave/Keystore) */
    @SerialName("hardware_backed")
    val hardwareBacked: Boolean = false,
    /** Target triple being checked against registry (e.g., aarch64-linux-android) */
    @SerialName("target_triple")
    val targetTriple: String? = null,
    /** Binary self-check status: verified, mismatch, not_found, unavailable:{reason} */
    @SerialName("binary_self_check")
    val binarySelfCheck: String? = null,
    /** Binary hash computed locally */
    @SerialName("binary_hash")
    val binaryHash: String? = null,
    /** Expected binary hash from registry */
    @SerialName("expected_binary_hash")
    val expectedBinaryHash: String? = null,
    /** Function self-check status: verified, mismatch, not_found, unavailable:{reason} */
    @SerialName("function_self_check")
    val functionSelfCheck: String? = null,
    /** Number of functions verified */
    @SerialName("functions_checked")
    val functionsChecked: Int? = null,
    /** Number of functions that passed verification */
    @SerialName("functions_passed")
    val functionsPassed: Int? = null,
    /** Registry key verification status */
    @SerialName("registry_key_status")
    val registryKeyStatus: String? = null,
    // v0.8.1: Python integrity for mobile
    /** Python module integrity verified */
    @SerialName("python_integrity_ok")
    val pythonIntegrityOk: Boolean = false,
    /** Number of Python modules checked */
    @SerialName("python_modules_checked")
    val pythonModulesChecked: Int? = null,
    /** Number of Python modules that passed */
    @SerialName("python_modules_passed")
    val pythonModulesPassed: Int? = null,
    /** Total hash of all Python modules */
    @SerialName("python_total_hash")
    val pythonTotalHash: String? = null,
    /** Whether Python total hash matches expected */
    @SerialName("python_hash_valid")
    val pythonHashValid: Boolean = false,

    // v0.8.4: Detail lists for UI
    /** Number of manifest files not on device */
    @SerialName("files_missing_count")
    val filesMissingCount: Int? = null,
    /** List of missing files (max 50) */
    @SerialName("files_missing_list")
    val filesMissingList: List<String>? = null,
    /** List of files that failed hash check (max 50) */
    @SerialName("files_failed_list")
    val filesFailedList: List<String>? = null,
    /** List of unexpected files (max 50) */
    @SerialName("files_unexpected_list")
    val filesUnexpectedList: List<String>? = null,
    /** List of functions that failed verification (max 50) */
    @SerialName("functions_failed_list")
    val functionsFailedList: List<String>? = null,

    // v0.8.6: Mobile exclusion tracking (discord, reddit, cli, etc. not bundled in APK)
    /** Number of files excluded from mobile (server-only adapters) */
    @SerialName("mobile_excluded_count")
    val mobileExcludedCount: Int? = null,
    /** List of mobile-excluded files (max 50) */
    @SerialName("mobile_excluded_list")
    val mobileExcludedList: List<String>? = null,

    // v0.8.6+: Per-file results for deconflicted integrity display
    /** Per-file status map (path → passed/failed/missing/unreadable) */
    @SerialName("per_file_results")
    val perFileResults: Map<String, String>? = null,

    // v0.8.5: Registry sources agreement
    /** Number of registry sources that agree (0-3) */
    @SerialName("sources_agreeing")
    val sourcesAgreeing: Int? = null,

    // v0.8.5: Attestation proof hardware type (SoftwareOnly, TEE, StrongBox, etc.)
    // This is the actual hardware security level from attestation_proof.hardware_type
    @SerialName("attestation_proof_hardware_type")
    val attestationProofHardwareType: String? = null,

    // v0.9.7: Cache timestamp
    /** When this attestation result was cached (ISO 8601 timestamp) */
    @SerialName("cached_at")
    val cachedAt: String? = null,

    // v0.9.7: Unified module integrity (cross-validation of disk/agent/registry)
    /** Whether unified module integrity check passed */
    @SerialName("module_integrity_ok")
    val moduleIntegrityOk: Boolean = false,
    /** Summary counts: total_manifest, verified, failed, missing, excluded, cross_validated */
    @SerialName("module_integrity_summary")
    val moduleIntegritySummary: Map<String, Int>? = null,
    /** Files where disk == agent == registry (strongest verification) */
    @SerialName("cross_validated_files")
    val crossValidatedFiles: List<String>? = null,
    /** Files where disk == registry (no agent hash) */
    @SerialName("filesystem_verified_files")
    val filesystemVerifiedFiles: List<String>? = null,
    /** Files where agent == registry (not on disk, e.g., Chaquopy) */
    @SerialName("agent_verified_files")
    val agentVerifiedFiles: List<String>? = null,
    /** RED FLAG: Files with disk != agent hash (tampering indicator) */
    @SerialName("disk_agent_mismatch")
    val diskAgentMismatch: Map<String, JsonElement>? = null,
    /** Files that don't match registry */
    @SerialName("registry_mismatch_files")
    val registryMismatchFiles: Map<String, JsonElement>? = null
) {
    /**
     * Calculate actual achieved attestation level (0-5).
     * This is the highest level where ALL required checks pass.
     * Use this instead of maxLevel which is the maximum *achievable* level.
     *
     * @param deviceAttestationPassed Optional override for Play Integrity from UI check
     */
    fun calculateActualLevel(deviceAttestationPassed: Boolean? = null): Int {
        // L1: Binary loaded and verified
        val l1Passed = binaryOk && binarySelfCheck == "verified"
        // L2: Environment AND device attestation (HW + Play Integrity)
        // Use UI's device attestation result if provided, otherwise fall back to API field
        val playOk = deviceAttestationPassed ?: playIntegrityOk
        val l2Passed = l1Passed && envOk && playOk
        // L3: Registry cross-validation (need majority agreement - 2+ sources)
        val sourcesOk = (sourcesAgreeing ?: 0) >= 2
        val l3Passed = l2Passed && sourcesOk
        // L4: File integrity check
        val l4Passed = l3Passed && fileIntegrityOk
        // L5: Portal key active AND audit trail intact
        val portalKeyOk = registryKeyStatus?.contains("active", ignoreCase = true) == true
        val l5Passed = l4Passed && portalKeyOk && auditOk

        return when {
            l5Passed -> 5
            l4Passed -> 4
            l3Passed -> 3
            l2Passed -> 2
            l1Passed -> 1
            else -> 0
        }
    }
}

/**
 * Detail for a single attestation check.
 */
@Serializable
data class CheckDetail(
    val ok: Boolean = false,
    val label: String = "",
    val level: Int = 0,
    // File integrity specific
    @SerialName("total_files")
    val totalFiles: Int? = null,
    @SerialName("files_checked")
    val filesChecked: Int? = null,
    @SerialName("files_passed")
    val filesPassed: Int? = null,
    @SerialName("files_failed")
    val filesFailed: Int? = null,
    @SerialName("failure_reason")
    val failureReason: String? = null
)

/**
 * v0.6.0: Per-source error details for network validation.
 * Categories: timeout, dns_resolution, tls_error, connection_refused, network_unreachable, server_error
 */
@Serializable
data class SourceErrorDetail(
    val category: String = "unknown",
    val details: String = ""
)
