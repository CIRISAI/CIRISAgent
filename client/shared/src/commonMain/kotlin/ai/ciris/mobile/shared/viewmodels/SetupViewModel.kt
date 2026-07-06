package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.config.CIRISConfig
import ai.ciris.mobile.shared.models.*
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.platform.createSecureStorage
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.api.CIRISApiClientProtocol
import ai.ciris.mobile.shared.api.LocationResultData
import ai.ciris.mobile.shared.models.safety.AgeBand

private const val TAG = "SetupViewModel"

/**
 * ViewModel for Setup Wizard state management.
 *
 * Source: android/app/src/main/java/ai/ciris/mobile/setup/SetupViewModel.kt
 * and android/app/src/main/java/ai/ciris/mobile/setup/SetupWizardActivity.kt
 *
 * Supports two LLM modes:
 * - CIRIS Proxy (free for Google OAuth users): Uses Google ID token with CIRIS hosted proxy
 * - BYOK (Bring Your Own Key): User provides their own API key from OpenAI/Anthropic/etc
 *
 * Key features:
 * - StateFlow for reactive UI updates
 * - Form validation with detailed error messages
 * - LLM validation (test call before setup completion)
 * - Auto-generated admin password (users don't set this)
 * - Google OAuth support for CIRIS proxy mode
 * - Survives configuration changes and app backgrounding (extends ViewModel)
 */
class SetupViewModel(
    private val apiClient: CIRISApiClientProtocol
) : ViewModel() {

    private val _state = MutableStateFlow(SetupFormState())
    val state: StateFlow<SetupFormState> = _state.asStateFlow()

    // OAuth poll job for adapter wizard
    private var adapterOAuthPollJob: Job? = null

    // Location search debounce job
    private var locationSearchJob: Job? = null

    // Available LLM providers for BYOK mode
    val availableProviders = listOf(
        "openai" to "OpenAI",
        "anthropic" to "Anthropic",
        "google" to "Google AI",
        "openrouter" to "OpenRouter",
        "groq" to "Groq",
        "together" to "Together AI",
        "mistral" to "Mistral",
        "cohere" to "Cohere",
        "deepseek" to "DeepSeek",
        "xai" to "xAI (Grok)",
        "azure" to "Azure OpenAI",
        "local_inference" to "Local Inference Server",
        "local" to "Local (Ollama)",
        "openai_compatible" to "OpenAI Compatible",
        "other" to "Other"
    )

    // ========== Google OAuth State ==========
    // Source: SetupViewModel.kt:68-80, SetupWizardActivity.kt:110-174

    /**
     * Set Google/Apple OAuth state from successful sign-in.
     *
     * Setup mode is determined by OAuth provider:
     * - Google or Apple OAuth → CIRIS_PROXY (free AI via CIRIS proxy)
     * - Any other provider → BYOK (bring your own key)
     *
     * Source: SetupViewModel.kt:68-80
     */
    fun setGoogleAuthState(
        isAuth: Boolean,
        idToken: String?,
        email: String?,
        userId: String?,
        provider: String = "google"
    ) {
        // CIRIS_PROXY only for Google or Apple OAuth, otherwise BYOK
        val isCirisEligible = isAuth && (provider == "google" || provider == "apple")

        _state.value = _state.value.copy(
            isGoogleAuth = isAuth,
            googleIdToken = idToken,
            googleEmail = email,
            googleUserId = userId,
            oauthProvider = provider,
            // Setup mode: CIRIS_PROXY for Google/Apple OAuth, BYOK otherwise
            setupMode = when {
                _state.value.setupMode != null -> _state.value.setupMode
                isCirisEligible -> SetupMode.CIRIS_PROXY
                else -> SetupMode.BYOK
            },
            // Skip Welcome step for authenticated users - go directly to Quick Setup
            currentStep = if (isAuth && _state.value.currentStep == SetupStep.WELCOME) {
                SetupStep.QUICK_SETUP
            } else {
                _state.value.currentStep
            }
        )
    }

    // ========== Setup Mode ==========
    // Source: SetupViewModel.kt:82-85

    /**
     * Set the LLM setup mode (CIRIS_PROXY or BYOK).
     */
    fun setSetupMode(mode: SetupMode) {
        _state.value = _state.value.copy(setupMode = mode)
    }

    // ========== Home Assistant Addon Mode ==========

    /**
     * Enable Home Assistant addon mode (also used by CIRISMedical, CIRISLegal, etc. via SSO).
     * In this mode:
     * - Login is skipped (HA/SSO handles auth via ingress provider)
     * - User creation is optional (handled in QuickSetup)
     * - Uses unified flow: WELCOME → QUICK_SETUP → COMPLETE
     * - QuickSetup provides BYOK configuration without requiring user account setup
     * - Defaults to BYOK mode since users provide their own API key
     */
    fun setHAAddonMode(enabled: Boolean) {
        _state.value = _state.value.copy(
            isHAAddonMode = enabled,
            // HA/SSO addon mode defaults to BYOK (user provides API key, no CIRIS proxy)
            setupMode = if (enabled) SetupMode.BYOK else _state.value.setupMode
        )
    }

    /**
     * Select the on-device Gemma 4 provider inside BYOK mode.
     *
     * This is a convenience wrapper the wizard UI calls when the user
     * taps the "Mobile Local (On-Device)" option in the provider
     * dropdown. It sets the canonical backend provider id
     * [LOCAL_ON_DEVICE_PROVIDER_ID] in `llmProvider`, clears any
     * previously entered API key, and pre-populates the loopback base
     * URL the Python adapter serves on. Users can still come back and
     * choose a different provider (e.g. OpenAI as a backup) if they
     * want cloud fallback — the on-device adapter runs in parallel at
     * [Priority.HIGH] so the LLM bus routes local-first.
     */
    fun selectLocalOnDeviceProvider() {
        _state.value = _state.value.copy(
            setupMode = SetupMode.BYOK,
            llmProvider = LOCAL_ON_DEVICE_PROVIDER_ID,
            llmApiKey = "",
            llmBaseUrl = LOCAL_ON_DEVICE_BASE_URL,
            llmModel = LOCAL_ON_DEVICE_DEFAULT_MODEL,
        )
    }

    companion object {
        /**
         * Scope carried on the under-18 stewardship request (CC 0.5.1 §2580).
         * Names the adult's relationship to the minor as RESPONSIBILITY, not
         * property — a steward is responsible *for* a ward, never a holder *of*
         * one. Used as the interim delegation-offer scope until the dedicated
         * minor steward-binding endpoint lands.
         */
        const val STEWARD_SCOPE = "steward:responsible-for"

        /**
         * SecureStorage key for the OPTIONAL friendly per-device name the wizard
         * collects (e.g. "Mac mini"). Client-side only — there is no server field
         * for it on the wizard's mint/claim requests yet. Read by the UI to label
         * "this device" (e.g. the My Identity device roster / node switcher).
         */
        const val PREF_DEVICE_NAME = "device_friendly_name"

        /** Canonical backend provider id for on-device Gemma 4 inference. */
        const val LOCAL_ON_DEVICE_PROVIDER_ID = "mobile_local"

        /** Display label shown in the BYOK provider dropdown. */
        const val LOCAL_ON_DEVICE_DISPLAY_NAME = "Mobile Local (On-Device)"

        /** Default model id used when the user picks on-device mode. */
        const val LOCAL_ON_DEVICE_DEFAULT_MODEL = "gemma-4-e2b"

        /**
         * Provider ids that point at a local OpenAI-compatible Ollama
         * server (on the device's loopback, or a LAN box reached via it).
         * Selecting one of these in the wizard pre-fills the canonical
         * local defaults below so the local-login path is one-tap.
         */
        val LOCAL_OLLAMA_PROVIDER_IDS = listOf("local", "openai_compatible")

        /**
         * Default base URL for a local Ollama server. Loopback by design:
         * a bare local install serves here, and emulator/CI bridges
         * (adb reverse, socat) map this onto a LAN inference box without
         * leaking an environment-specific IP into the saved config.
         */
        const val LOCAL_OLLAMA_BASE_URL = "http://localhost:11434/v1"

        /** Default local model — Gemma 4 e2b QAT fits an 8GB box at ~12 tok/s. */
        const val LOCAL_OLLAMA_DEFAULT_MODEL = "gemma4:e2b-it-qat"

        /**
         * Loopback base URL of the on-device OpenAI-compatible server
         * spawned by the Mobile Local LLM Python adapter. Kept in sync
         * with `MobileLocalLLMConfig.base_url()` in the Python side.
         */
        const val LOCAL_ON_DEVICE_BASE_URL = "http://127.0.0.1:8091/v1"

        /**
         * Map the current `llmProvider` state value to the canonical
         * backend provider id expected by `/v1/setup/complete` and
         * `/v1/setup/validate-llm`.
         *
         * The BYOK dropdown stores the canonical id (`anthropic`, `groq`,
         * `local_inference`, …) directly in state, so the pass-through
         * case is the common path. The explicit display-label cases
         * exist only as a back-compat shim for older state (e.g. saved
         * setup data from a previous build) that still carries raw
         * labels like `"Anthropic"`.
         *
         * Without this mapping, a user who picks any non-OpenAI
         * provider from the dropdown would silently have their
         * `llm_provider` serialised as `"openai"` because the old
         * when-block only matched display labels.
         */
        fun canonicalProviderId(value: String): String = when (value) {
            "" -> "openai"
            // Legacy display-label → canonical id mapping (pre-canonical
            // state, kept for back-compat).
            "OpenAI" -> "openai"
            "Anthropic" -> "anthropic"
            "Google AI" -> "google"
            "OpenRouter" -> "openrouter"
            "Groq" -> "groq"
            "Together AI" -> "together"
            "Azure OpenAI" -> "other"
            "LocalAI", "Local LLM" -> "local"
            "OpenAI Compatible" -> "openai_compatible"
            LOCAL_ON_DEVICE_DISPLAY_NAME -> LOCAL_ON_DEVICE_PROVIDER_ID
            // Canonical ids coming straight from `availableProviders`
            // pass through unchanged.
            else -> value
        }
    }

    // ========== LLM Configuration (BYOK mode) ==========
    // Source: SetupViewModel.kt:87-105

    /**
     * Set the LLM provider for BYOK mode.
     * Examples: "OpenAI", "Anthropic", "Azure OpenAI", "LocalAI"
     */
    fun setLlmProvider(provider: String) {
        val current = _state.value
        // Pre-fill canonical local-Ollama defaults when a local provider is
        // chosen and the fields are still empty. Keeps the local-login path
        // one-tap while leaving any value the user already typed untouched.
        val isLocalOllama = provider in LOCAL_OLLAMA_PROVIDER_IDS
        _state.value = current.copy(
            llmProvider = provider,
            llmBaseUrl = if (isLocalOllama && current.llmBaseUrl.isEmpty()) {
                LOCAL_OLLAMA_BASE_URL
            } else {
                current.llmBaseUrl
            },
            llmModel = if (isLocalOllama && current.llmModel.isEmpty()) {
                LOCAL_OLLAMA_DEFAULT_MODEL
            } else {
                current.llmModel
            },
        )
    }

    /**
     * Set the LLM API key for BYOK mode.
     */
    fun setLlmApiKey(key: String) {
        _state.value = _state.value.copy(llmApiKey = key)
    }

    /**
     * Set the LLM base URL (optional, for custom providers).
     */
    fun setLlmBaseUrl(url: String) {
        _state.value = _state.value.copy(llmBaseUrl = url)
    }

    /**
     * Set the LLM model (optional, provider default used if empty).
     */
    fun setLlmModel(model: String) {
        _state.value = _state.value.copy(llmModel = model)
    }

    // ========== User Account (non-Google users) ==========
    // Source: SetupViewModel.kt:107-120

    /**
     * Set the username for local user account.
     */
    fun setUsername(username: String) {
        _state.value = _state.value.copy(username = username)
    }

    /**
     * Set the email for local user account.
     */
    fun setEmail(email: String) {
        _state.value = _state.value.copy(email = email)
    }

    /**
     * Set the password for local user account.
     */
    fun setUserPassword(password: String) {
        _state.value = _state.value.copy(userPassword = password)
    }

    fun setUserPasswordConfirm(password: String) {
        _state.value = _state.value.copy(userPasswordConfirm = password)
    }

    /**
     * Set the OPTIONAL friendly per-device name (e.g. "Mac mini"). Distinct from
     * the federation-identity label (which names the human's fed-ID). Empty is
     * allowed. Stored only in state here; persisted as a client-side preference
     * on a successful ownership claim (see [claimLocalNodeOwnership]).
     */
    fun setDeviceName(name: String) {
        _state.value = _state.value.copy(deviceName = name)
    }

    fun setSecureWith2FA(enabled: Boolean) {
        PlatformLogger.i(TAG, "setSecureWith2FA: 2FA (CIRISVerify hardware factor) ${if (enabled) "ON" else "OFF"}")
        _state.value = _state.value.copy(secureWith2FA = enabled)
    }

    /**
     * Opt IN / OUT of announcing this owner to the federation (default OFF —
     * private/self-scoped). When ON, a successful claim promotes ownership
     * self→FEDERATION + enables the node's identity announce, applied best-effort
     * post-claim (see [claimLocalNodeOwnership]); takes effect on next boot.
     */
    fun setAnnounceOwnership(enabled: Boolean) {
        PlatformLogger.i(TAG, "setAnnounceOwnership: federation announce ${if (enabled) "ON (opt-in)" else "OFF (private)"}")
        _state.value = _state.value.copy(announceOwnership = enabled)
    }

    // ========== Language & Location Preferences ==========
    // Mirrors CLI wizard: ciris_engine/logic/setup/wizard.py:324-395

    /**
     * Set the preferred language (ISO 639-1 code).
     * Examples: "en", "am", "es", "ja", "zh"
     */
    fun setPreferredLanguage(language: String) {
        _state.value = _state.value.copy(preferredLanguage = language)
    }

    /**
     * Set the location sharing granularity.
     */
    fun setLocationGranularity(granularity: LocationGranularity) {
        _state.value = _state.value.copy(locationGranularity = granularity)
    }

    /**
     * Set the user's country.
     * Only used when locationGranularity >= COUNTRY.
     */
    fun setCountry(country: String) {
        _state.value = _state.value.copy(country = country)
    }

    /**
     * Set the user's region/state.
     * Only used when locationGranularity >= REGION.
     */
    fun setRegion(region: String) {
        _state.value = _state.value.copy(region = region)
    }

    /**
     * Set the user's city.
     * Only used when locationGranularity == CITY.
     */
    fun setCity(city: String) {
        _state.value = _state.value.copy(city = city)
    }

    /**
     * Set consent to share location data in telemetry traces.
     * When enabled, location info is included in anonymized telemetry
     * for contextual analysis (timezone patterns, regional usage, etc.).
     */
    fun setShareLocationInTraces(share: Boolean) {
        _state.value = _state.value.copy(shareLocationInTraces = share)
    }

    // ========== Location Search (Typeahead) ==========

    /**
     * Search for cities by name.
     * Uses debouncing to avoid excessive API calls during typing.
     * Results are sorted by population (largest cities first).
     *
     * @param query Search query (minimum 2 characters)
     */
    fun searchLocations(query: String) {
        // Update query immediately for responsive UI
        _state.value = _state.value.copy(locationSearchQuery = query)

        // Cancel any pending search
        locationSearchJob?.cancel()

        // Don't search for very short queries
        if (query.length < 2) {
            _state.value = _state.value.copy(
                locationSearchResults = emptyList(),
                locationSearchLoading = false
            )
            return
        }

        // Debounce: wait 300ms before searching
        locationSearchJob = viewModelScope.launch {
            _state.value = _state.value.copy(locationSearchLoading = true)

            delay(300)

            try {
                val response = apiClient.searchLocations(query = query, limit = 10)
                val results = response.results.map { result ->
                    LocationSearchResult(
                        city = result.city,
                        region = result.region,
                        country = result.country,
                        countryCode = result.countryCode,
                        latitude = result.latitude,
                        longitude = result.longitude,
                        population = result.population,
                        timezone = result.timezone,
                        displayName = result.displayName
                    )
                }
                _state.value = _state.value.copy(
                    locationSearchResults = results,
                    locationSearchLoading = false
                )
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "Location search failed: ${e.message}")
                _state.value = _state.value.copy(
                    locationSearchResults = emptyList(),
                    locationSearchLoading = false
                )
            }
        }
    }

    /**
     * Select a location from search results.
     * Auto-fills country, region, and city based on selection.
     * Sets location granularity to CITY.
     * Location is persisted after setup completes (in completeSetup).
     */
    fun selectLocation(location: LocationSearchResult) {
        _state.value = _state.value.copy(
            selectedLocation = location,
            country = location.country,
            region = location.region ?: "",
            city = location.city,
            locationGranularity = LocationGranularity.CITY,
            locationSearchQuery = location.displayName,
            locationSearchResults = emptyList()
        )
    }

    /**
     * Clear location search state.
     */
    fun clearLocationSearch() {
        locationSearchJob?.cancel()
        _state.value = _state.value.copy(
            locationSearchQuery = "",
            locationSearchResults = emptyList(),
            locationSearchLoading = false,
            selectedLocation = null
        )
    }

    // ========== Step Navigation ==========
    // Source: SetupWizardActivity.kt:77-97

    /**
     * Move to the next setup step.
     * Only proceeds if current step is valid.
     *
     * Returns true if navigation succeeded, false if validation failed.
     */
    fun nextStep(): Boolean {
        val currentState = _state.value

        if (!currentState.canProceedFromCurrentStep()) {
            return false
        }

        // NODE CLIENT first-run flow (drives a local ciris-server, NOT the agent).
        // USER CREATION LEADS: a fresh run creates the founder's local account
        // FIRST (ACCOUNT_AND_CONFIRMATION — the robust, existing creation step),
        // THEN mints the founder's hardware-rooted federation ID (now associated to
        // that just-created user), THEN states the protective age-range gate, then
        // completes (and on COMPLETE the local node is self-claimed for that user).
        // The agent setup steps (NODE_AUTH / PREFERENCES / LLM_CONFIGURATION /
        // OPTIONAL_FEATURES / QUICK_SETUP) are dropped from the node-client path.
        // BOTH the advanced (isNodeFlow) and the unified branch funnel through the
        // same account-first sequence:
        //   WELCOME → ACCOUNT_AND_CONFIRMATION → FEDERATION_IDENTITY_SETUP →
        //   AGE_RANGE → COMPLETE
        val nextStep = if (currentState.isNodeFlow) {
            when (currentState.currentStep) {
                SetupStep.WELCOME -> SetupStep.ACCOUNT_AND_CONFIRMATION
                // Account created — now MINT YOUR FEDERATION ID (associated to the
                // just-created user).
                SetupStep.ACCOUNT_AND_CONFIRMATION -> SetupStep.FEDERATION_IDENTITY_SETUP
                // You have an ID — now STATE YOUR AGE RANGE (the foundational
                // protective gate), THEN you're on the fabric.
                SetupStep.FEDERATION_IDENTITY_SETUP -> SetupStep.AGE_RANGE
                SetupStep.AGE_RANGE -> SetupStep.COMPLETE
                else -> SetupStep.COMPLETE
            }
        } else {
            // Unified branch — same account-first node-client flow.
            when (currentState.currentStep) {
                SetupStep.WELCOME -> SetupStep.ACCOUNT_AND_CONFIRMATION
                SetupStep.ACCOUNT_AND_CONFIRMATION -> SetupStep.FEDERATION_IDENTITY_SETUP
                SetupStep.FEDERATION_IDENTITY_SETUP -> SetupStep.AGE_RANGE
                SetupStep.AGE_RANGE -> SetupStep.COMPLETE
                else -> SetupStep.COMPLETE
            }
        }

        _state.value = currentState.copy(currentStep = nextStep)
        return true
    }

    /**
     * Move to the previous setup step.
     *
     * IMPORTANT: When going back from NODE_AUTH to WELCOME, we must reset isNodeFlow
     * so that the user can choose to NOT register this time.
     */
    fun previousStep() {
        val currentState = _state.value

        // Node-client back-button mirrors the account-first forward path:
        //   COMPLETE → AGE_RANGE → FEDERATION_IDENTITY_SETUP →
        //   ACCOUNT_AND_CONFIRMATION → WELCOME
        val prevStep = if (currentState.isNodeFlow) {
            when (currentState.currentStep) {
                SetupStep.WELCOME -> SetupStep.WELCOME
                SetupStep.ACCOUNT_AND_CONFIRMATION -> SetupStep.WELCOME
                SetupStep.FEDERATION_IDENTITY_SETUP -> SetupStep.ACCOUNT_AND_CONFIRMATION
                SetupStep.AGE_RANGE -> SetupStep.FEDERATION_IDENTITY_SETUP
                SetupStep.COMPLETE -> SetupStep.AGE_RANGE
                else -> SetupStep.WELCOME
            }
        } else {
            when (currentState.currentStep) {
                SetupStep.WELCOME -> SetupStep.WELCOME
                SetupStep.ACCOUNT_AND_CONFIRMATION -> SetupStep.WELCOME
                SetupStep.FEDERATION_IDENTITY_SETUP -> SetupStep.ACCOUNT_AND_CONFIRMATION
                SetupStep.AGE_RANGE -> SetupStep.FEDERATION_IDENTITY_SETUP
                SetupStep.COMPLETE -> SetupStep.AGE_RANGE
                else -> SetupStep.WELCOME
            }
        }

        // When going back from NODE_AUTH to WELCOME, reset isNodeFlow so user can
        // choose NOT to register this time (fixes bug where back->continue still went to NODE_AUTH)
        val shouldResetNodeFlow = currentState.isNodeFlow &&
            currentState.currentStep == SetupStep.NODE_AUTH &&
            prevStep == SetupStep.WELCOME

        _state.value = currentState.copy(
            currentStep = prevStep,
            isNodeFlow = if (shouldResetNodeFlow) false else currentState.isNodeFlow
        )

        // Also reset device auth state when backing out of NODE_AUTH to clear any
        // stale/error/timeout state. This ensures a clean slate for retry.
        if (shouldResetNodeFlow) {
            PlatformLogger.i(TAG, "previousStep: Backing out of NODE_AUTH, resetting device auth state")
            resetDeviceAuth()
        }
    }

    // ========== Federation Identity (FEDERATION_IDENTITY_SETUP) ==========

    /**
     * Probe the LOCAL node for the owner's federation identity.
     *
     * ARCHITECTURE: the federation identity lives in the LOCAL node's
     * keyring/substrate, NOT the app. The app holds no keys and mints nothing.
     * We ask the local node for its own signed key record; if it answers, the
     * node has a usable federation identity and the step can report it.
     */
    fun probeFederationIdentity() {
        val client = apiClient as? CIRISApiClient
        if (client == null) {
            _state.value = _state.value.copy(
                federationIdentity = _state.value.federationIdentity.copy(
                    probed = true,
                    hardwareAvailable = false,
                    error = "Local node unavailable: API client does not support it",
                )
            )
            return
        }
        // The USER fed-ID is DISTINCT from the node's own steward key. We deliberately
        // do NOT read the node's self-key-record here — that is the NODE identity
        // (always present, e.g. the TPM-sealed steward key), NOT the user's fed-ID.
        // Treating it as "you already have a fed-ID" is the bug that skipped minting a
        // real user identity. Per req A the wizard ALWAYS creates the user fed-ID via
        // the backend ladder (pkcs11-if-2FA → HW-if-available → SW; verify resolves
        // the custody). Probe only marks the node reachable; it does NOT assert an
        // existing user identity (`identityKeyId` stays null until a real mint/associate).
        viewModelScope.launch {
            val up = client.isLocalNodeUp(CIRISApiClient.LOCAL_NODE_URL)
            _state.value = _state.value.copy(
                federationIdentity = _state.value.federationIdentity.copy(
                    hardwareAvailable = up,
                    identityKeyId = null,
                    probed = true,
                )
            )
        }
    }

    /**
     * Set the REQUIRED unique identity name for the federation identity. Flows
     * into the local node's `POST /v1/self/identity` as `label` → the FSD-002
     * `label-fingerprint` key_id. This is the ONE canonical name the user's
     * federation identity is keyed by; the wizard blocks proceeding until it is
     * non-blank and not a generic default (see `FederationIdentitySetupState`).
     */
    fun setFederationLabel(label: String) {
        _state.value = _state.value.copy(
            federationIdentity = _state.value.federationIdentity.copy(label = label)
        )
    }

    /**
     * Set the custody backend hint for the mint: `pkcs11` (YubiKey),
     * `platform-sealed` (TPM / Secure Enclave), `software` (dev), or `null` to
     * let the local node use its configured default. The local node chooses the
     * real backend; this is only a hint it may honor.
     */
    fun setFederationBackend(backend: String?) {
        _state.value = _state.value.copy(
            federationIdentity = _state.value.federationIdentity.copy(backend = backend)
        )
    }

    /** Toggle the "associate existing Fed ID" path (adopt prior crypto). */
    fun toggleAssociateExisting() {
        val fed = _state.value.federationIdentity
        _state.value = _state.value.copy(
            federationIdentity = fed.copy(associateExisting = !fed.associateExisting, error = null)
        )
    }

    /** The existing federation key_id (or fedcode) the user wants to associate. */
    fun setAssociateKeyId(value: String) {
        _state.value = _state.value.copy(
            federationIdentity = _state.value.federationIdentity.copy(associateKeyId = value)
        )
    }

    /**
     * **Associate (RECLAIM) an EXISTING federation ID** on this device instead of
     * minting a fresh one — the "same user, same auth, anywhere" path.
     *
     * This is NOT special adopt code: it is how the YubiKey works. The private key
     * lives on the token and never leaves it; the `key_id` is RE-DERIVED from the
     * token's public key (`derive_key_id(label, pubkey)` = `<label>-sha256(pubkey)`,
     * CIRISVerify fedcode). So presenting the SAME YubiKey on ANY node with the same
     * display label reproduces the SAME fed-ID — no re-keying. We therefore drive
     * the mint with `backend = pkcs11, provision = false` (open the token, READ the
     * existing key, derive its id — never generate). The substrate + key + CC
     * `identity_occurrence` do the rest. Failures are surfaced, never block.
     */
    fun associateExistingFederationId() {
        val client = apiClient as? CIRISApiClient ?: run {
            _state.value = _state.value.copy(
                federationIdentity = _state.value.federationIdentity.copy(
                    error = "Local node unavailable: API client does not support it"
                )
            )
            return
        }
        val fed = _state.value.federationIdentity
        val existing = fed.associateKeyId.trim()
        if (existing.isBlank()) return
        _state.value = _state.value.copy(
            federationIdentity = fed.copy(inProgress = true, error = null)
        )
        viewModelScope.launch {
            try {
                val res = client.mintUserIdentity(
                    // RECLAIM: read the existing key off the YubiKey (no keygen),
                    // re-derive the SAME key_id from the token pubkey.
                    label = existing,
                    backend = "pkcs11",
                    provision = false,
                    localNodeUrl = CIRISApiClient.LOCAL_NODE_URL,
                )
                _state.value = _state.value.copy(
                    federationIdentity = _state.value.federationIdentity.copy(
                        inProgress = false,
                        admitted = true,
                        minted = true,
                        hardwareAvailable = true,
                        identityKeyId = res.keyId,
                        fedcode = res.fedcode,
                    )
                )
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    federationIdentity = _state.value.federationIdentity.copy(
                        inProgress = false,
                        error = "Associate existing Fed ID failed: ${e.message}",
                    )
                )
            }
        }
    }

    /**
     * **Import an EXISTING fed-ID from a USB / folder keyset** — the "same person,
     * new device" path. Drives the local node's `POST /v1/self/associate` with the
     * portable keyset directory; the node installs the keyset and **REPLACES** this
     * device's active user identity with it. The subsequent self-claim
     * ([claimLocalNodeOwnership]) then re-owns the node under the IMPORTED fed-ID
     * (the active alias the node now points at). One device = one person — import
     * replaces, it never coexists (families are the multi-person construct).
     *
     * Sets `minted`/`admitted` on success so the wizard proceeds straight to the
     * self-claim (the auto-mint-on-Next + mint-if-absent backstop both no-op once
     * an identity is present).
     */
    fun importPortableFromUsb(sourceDir: String) {
        val client = apiClient as? CIRISApiClient ?: run {
            _state.value = _state.value.copy(
                federationIdentity = _state.value.federationIdentity.copy(
                    error = "Local node unavailable: API client does not support it"
                )
            )
            return
        }
        val src = sourceDir.trim()
        if (src.isBlank()) return
        _state.value = _state.value.copy(
            federationIdentity = _state.value.federationIdentity.copy(inProgress = true, error = null)
        )
        viewModelScope.launch {
            try {
                val res = client.associateFedId(sourceDir = src)
                _state.value = _state.value.copy(
                    federationIdentity = _state.value.federationIdentity.copy(
                        inProgress = false,
                        admitted = true,
                        minted = true,
                        hardwareAvailable = true,
                        identityKeyId = res.associatedKeyId,
                        error = null,
                    )
                )
                PlatformLogger.i(TAG, "importPortableFromUsb: imported fed-ID ${res.associatedKeyId} from $src")
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "importPortableFromUsb failed: ${e.message}")
                _state.value = _state.value.copy(
                    federationIdentity = _state.value.federationIdentity.copy(
                        inProgress = false,
                        admitted = false,
                        minted = false,
                        error = "Couldn't import a fed-ID from that folder: ${e.message ?: "unknown error"}",
                    )
                )
            }
        }
    }

    /**
     * **Create the founder's federation ID by DRIVING the LOCAL node** to MINT a
     * hardware-rooted USER identity — `POST /v1/self/identity`.
     *
     * The app performs NO federation crypto: it does not mint keys, build
     * occurrences, or hybrid-sign anything. The local ciris-server mints the
     * hybrid Ed25519 + ML-DSA-65 keypair IN ITS SUBSTRATE — custodied by a
     * YubiKey (PKCS#11), TPM/Secure-Enclave (platform-sealed), or a software seed
     * (dev) per the server's config / the optional backend hint — and returns the
     * public result (key_id + `CIRIS-V2-…` fedcode + pubkeys + hardware_type),
     * which the app surfaces.
     *
     * Optional step — failures are surfaced but never block the wizard.
     */
    fun runFederationIdentitySetup() {
        val client = apiClient as? CIRISApiClient
        if (client == null) {
            _state.value = _state.value.copy(
                federationIdentity = _state.value.federationIdentity.copy(
                    error = "Local node unavailable: API client does not support it"
                )
            )
            return
        }
        val fed = _state.value.federationIdentity
        _state.value = _state.value.copy(
            federationIdentity = fed.copy(inProgress = true, error = null)
        )
        viewModelScope.launch {
            try {
                // DRIVE the LOCAL node to mint the owner's federation identity. The
                // node does all crypto (keygen, sealing, genesis-object signing) in
                // its substrate; the app only POSTs over plain localhost HTTP and
                // surfaces the public result. NO keys/crypto in Kotlin.
                // "Secure with 2FA" means a HARDWARE-custodied (YubiKey / PKCS#11)
                // identity — so route the mint to the pkcs11 backend (opens the token,
                // touch+PIN). An explicit backend choice wins; otherwise 2FA ⇒ pkcs11,
                // and only with 2FA OFF do we fall back to the server's default
                // (platform-sealed / software). Without this the mint sent no backend
                // and the node silently minted a software/TPM-sealed key — no YubiKey.
                val mintBackend = fed.backend
                    ?: if (_state.value.secureWith2FA) "pkcs11" else null
                val minted = client.mintUserIdentity(
                    label = fed.label.trim().ifBlank { null },
                    backend = mintBackend,
                    localNodeUrl = CIRISApiClient.LOCAL_NODE_URL,
                )
                _state.value = _state.value.copy(
                    federationIdentity = _state.value.federationIdentity.copy(
                        inProgress = false,
                        admitted = true,
                        minted = true,
                        hardwareAvailable = true,
                        identityKeyId = minted.keyId,
                        fedcode = minted.fedcode,
                        hardwareLabel = minted.hardwareLabel,
                        error = null,
                    )
                )
            } catch (e: Exception) {
                // The mint failed (no owner session, backend unavailable, etc.).
                // Report honestly; do NOT fall back to minting keys in Kotlin.
                PlatformLogger.w(TAG, "runFederationIdentitySetup: mint via local node failed: ${e.message}")
                _state.value = _state.value.copy(
                    federationIdentity = _state.value.federationIdentity.copy(
                        inProgress = false,
                        admitted = false,
                        minted = false,
                        error = "Couldn't create your federation ID on this device's local node: " +
                            "${e.message ?: "unknown error"}",
                    )
                )
            }
        }
    }

    // ========== Age Range (AGE_RANGE — the foundational protective gate) ======

    /**
     * **State your age range** — drive THIS device's LOCAL node to record the
     * founder's self-declared age band (`POST /v1/safety/age-assurance`, self
     * level). The app performs NO crypto: the local node signs + promotes the
     * subject-signed `age_self_declared:{band}:v1` assurance in its substrate.
     *
     * The subject controls their OWN band: misdeclaration NEVER slashes (it
     * routes to adjudication). This sets PROTECTIVE defaults ahead of content —
     * a `minor` band is gated out of adult content fabric-wide.
     *
     * Resolves the subject key_id from the just-minted federation identity (or a
     * pre-existing one the local node reported). If no identity is available the
     * step records the selection locally and surfaces an honest error — the band
     * can be (re)stated from the Safety surface once an ID exists.
     */
    fun setAgeRange(band: AgeBand) {
        // SELECTION ONLY — do NOT post yet. The age assurance is recorded AFTER the
        // node claim (the subject is the bound owner's fed-ID, which only exists +
        // owns post-claim), via the loopback owner endpoint POST /v1/self/age in
        // [claimLocalNodeOwnership]. Posting here (pre-claim) hit the federation
        // /v1/safety/age-assurance route, which needs an x-ciris signature the app
        // (no crypto) can't produce → 401. We just stash the chosen band.
        _state.value = _state.value.copy(
            ageRange = _state.value.ageRange.copy(
                selectedBandToken = if (band == AgeBand.MINOR) "minor" else "adult",
                error = null,
            ),
            // Switching to ADULT clears any pending under-18 stewardship request
            // (the adult self-claims as normal). Switching to MINOR keeps the
            // existing state so a re-selection doesn't discard a generated request.
            minorStewardship = if (band == AgeBand.ADULT) {
                MinorStewardshipState()
            } else {
                _state.value.minorStewardship
            },
        )
    }

    // ========== Under-18 Stewardship (CC 0.5.1 §2580 — minor-stewardship rule) ==

    /**
     * **Generate the under-18 STEWARDSHIP REQUEST** the minor hands to an over-18
     * adult. Per CC 0.5.1 §2580 a `minor` user MUST NOT self-claim ownership and
     * MUST have a live `delegates_to(adult-user → minor-user)` at all times; the
     * adult's signature on that envelope IS the agreement-to-stewardship. The
     * account is fail-secure: the minor cannot operate until a live adult steward
     * accepts, and pauses again if the steward is ever withdrawn/superseded
     * without replacement.
     *
     * The app holds NO keys. It DRIVES the LOCAL node to produce a hand-off
     * artifact (a claim URL + PIN, mirroring the delegation-offer shape) that the
     * minor gives to their adult. The adult opens it on their OWN device/session
     * and ACCEPTS, at which point the adult's node mints + hybrid-signs the
     * `delegates_to(adult → minor)` steward-binding in its substrate.
     *
     * INTERIM TRANSPORT: there is no dedicated minor steward-binding endpoint on
     * ciris-server yet, so this reuses the existing delegation-offer surface
     * (`POST /v1/auth/device/delegate`) with a `steward:*` scope purely to mint a
     * URL+PIN to hand over. The DEDICATED endpoints needed are documented in the
     * round report:
     *   - mint the request:  `POST /v1/safety/minor-steward/request`
     *       { minor_key_id } → { claim_url, pin, expires_in }
     *   - adult accepts:     `POST /v1/safety/minor-steward/accept`
     *       { pin } (adult owner session, age_band==adult) → signs
     *       `delegates_to(adult-user → minor-user)` (CC 2.4.1); its
     *       attesting_key_id == the adult = the agreement-to-stewardship.
     *
     * Failures are surfaced honestly and never silently self-claim — fail-secure.
     */
    fun requestMinorSteward() {
        val client = apiClient as? CIRISApiClient
        if (client == null) {
            _state.value = _state.value.copy(
                minorStewardship = _state.value.minorStewardship.copy(
                    error = "Local node unavailable: API client does not support it",
                )
            )
            return
        }
        val fed = _state.value.federationIdentity
        // Name the request after the minor's federation identity so the adult can
        // see WHO they are accepting responsibility for.
        val minorLabel = fed.label.trim().ifBlank { fed.identityKeyId ?: "minor" }
        _state.value = _state.value.copy(
            minorStewardship = _state.value.minorStewardship.copy(inProgress = true, error = null)
        )
        viewModelScope.launch {
            try {
                // INTERIM: reuse the delegation-offer surface to produce the
                // URL+PIN the minor hands over. Replace with the dedicated
                // `/v1/safety/minor-steward/request` endpoint when it lands.
                val offer = client.createDelegation(
                    label = "steward-for-$minorLabel",
                    mode = "create",
                    scope = listOf(STEWARD_SCOPE),
                    nodeUrl = CIRISApiClient.LOCAL_NODE_URL,
                )
                _state.value = _state.value.copy(
                    minorStewardship = _state.value.minorStewardship.copy(
                        inProgress = false,
                        requested = true,
                        requestUrl = offer.claimUrl,
                        requestPin = offer.pin,
                        expiresIn = offer.expiresIn,
                        error = null,
                    )
                )
                PlatformLogger.i(TAG, "requestMinorSteward: stewardship request generated for '$minorLabel'")
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "requestMinorSteward: failed to generate request: ${e.message}")
                _state.value = _state.value.copy(
                    minorStewardship = _state.value.minorStewardship.copy(
                        inProgress = false,
                        requested = false,
                        error = "Couldn't create your stewardship request yet: " +
                            "${e.message ?: "unknown error"}. You can try again, or an " +
                            "adult can set up stewardship for you later.",
                    )
                )
            }
        }
    }

    // ========== LOCAL-node ownership self-claim (on COMPLETE) ===============

    /**
     * **Claim ownership of THIS device's LOCAL node** so the just-created user
     * (the federation ID minted in FEDERATION_IDENTITY_SETUP) becomes the node's
     * ROOT/owner. Called on setup COMPLETE, after the account + fed-ID exist.
     *
     * ARCHITECTURE: the app holds NO keys and performs NO crypto. It DRIVES the
     * LOCAL node's `POST /v1/setup/claim-remote { node_code, claim_pin,
     * cohort_scope }`. For a SELF-claim the "target" IS the local node: the local
     * node decodes its own NodeCode (carrying a loopback transport_hint), builds +
     * JCS-canonicalizes + HYBRID-SIGNS the owner-binding `delegates_to(user →
     * THIS node, infra:*)` in its substrate with the resident user identity, and
     * POSTs the signed artifact to its own `/v1/setup/root`. The substrate does
     * all crypto; the app only supplies {node_code, claim_pin}.
     *
     * The one-time [claimPin] is CONSOLE-ONLY — it is read off the node's stdout
     * by PythonRuntime (the "OWNERSHIP UNCLAIMED" banner) and passed in here. If
     * it was never captured we surface an honest error and do NOT block the flow
     * (the node simply stays unclaimed until the user claims it from the network
     * surface).
     *
     * @param claimPin the one-time claim PIN captured from the node's console
     *        (PythonRuntime.localClaimPin), or null/blank if it was not seen.
     * @param capturedNodeCode the node's own NodeCode if it was also captured from
     *        the banner; when null we fetch it via `GET /v1/federation/node-code`.
     * @param cohortScope the cohort scope to claim under (`self` by default — a
     *        first-run desktop install is the founder's own node).
     */
    fun claimLocalNodeOwnership(
        claimPin: String?,
        capturedNodeCode: String? = null,
        cohortScope: String = "self",
    ) {
        // FAIL-SECURE under-18 gate (CC 0.5.1 §2580): a minor MUST NOT self-claim
        // ownership. The account stays steward-less (cannot operate) until a live
        // adult steward accepts the `delegates_to(adult → minor)` out-of-band. Do
        // NOT touch the local node's owner-binding here; surface the pending state.
        if (_state.value.isMinorBand()) {
            PlatformLogger.i(TAG, "claimLocalNodeOwnership: minor band — skipping self-claim (fail-secure, awaiting adult steward)")
            _state.value = _state.value.copy(
                ownershipClaim = _state.value.ownershipClaim.copy(
                    inProgress = false,
                    claimed = false,
                    error = null,
                )
            )
            return
        }
        val client = apiClient as? CIRISApiClient
        if (client == null) {
            _state.value = _state.value.copy(
                ownershipClaim = _state.value.ownershipClaim.copy(
                    error = "Local node unavailable: API client does not support it",
                )
            )
            return
        }
        if (claimPin.isNullOrBlank()) {
            // Console-only PIN was never captured — be honest, don't pretend.
            _state.value = _state.value.copy(
                ownershipClaim = _state.value.ownershipClaim.copy(
                    inProgress = false,
                    claimed = false,
                    error = "claim PIN not captured — this node's one-time ownership " +
                        "PIN was not seen on its console. You can claim ownership later " +
                        "from the Network surface using the PIN printed on the node.",
                )
            )
            return
        }
        _state.value = _state.value.copy(
            ownershipClaim = _state.value.ownershipClaim.copy(inProgress = true, error = null)
        )
        viewModelScope.launch {
            try {
                // MINT-IF-ABSENT: the self-claim REQUIRES a responsible-user fed-ID
                // (the node 503s "no responsible-user identity yet" otherwise). The
                // FEDERATION_IDENTITY_SETUP step lets the user proceed on a valid
                // *typed* label alone (canProceed = minted || admitted ||
                // isLabelValid), so a user who fills the name but never taps "Create
                // fed-ID" reaches here un-minted. Rather than fail the claim, mint it
                // now from the name they provided — mint-if-absent, mirroring the
                // node's own open_or_create unbrick. Awaited, so the fed-ID exists
                // before claim-remote runs. A mint failure falls to the outer catch.
                val fed0 = _state.value.federationIdentity
                if (!fed0.minted && !fed0.admitted) {
                    val mintBackend = fed0.backend
                        ?: if (_state.value.secureWith2FA) "pkcs11" else null
                    val minted = client.mintUserIdentity(
                        label = fed0.label.trim().ifBlank { null },
                        backend = mintBackend,
                        localNodeUrl = CIRISApiClient.LOCAL_NODE_URL,
                    )
                    _state.value = _state.value.copy(
                        federationIdentity = _state.value.federationIdentity.copy(
                            inProgress = false,
                            admitted = true,
                            minted = true,
                            hardwareAvailable = true,
                            identityKeyId = minted.keyId,
                            fedcode = minted.fedcode,
                            hardwareLabel = minted.hardwareLabel,
                            error = null,
                        )
                    )
                    PlatformLogger.i(TAG, "claimLocalNodeOwnership: minted fed-ID before claim (was absent) key_id=${minted.keyId}")
                }

                // Resolve THIS node's own NodeCode (PUBLIC handle). Prefer the one
                // captured from the banner; otherwise fetch it from the local node.
                val nodeCode = capturedNodeCode?.takeIf { it.isNotBlank() }
                    ?: client.getNodeCode(CIRISApiClient.LOCAL_NODE_URL).code

                // SELF-claim: drive the LOCAL node to claim ITSELF. The local node
                // decodes its own NodeCode (loopback transport_hint), signs the
                // owner-binding in its substrate, and POSTs it to its own
                // /v1/setup/root. Reuses the existing claim-remote client path.
                val resp = client.claimRemote(
                    nodeCode = nodeCode,
                    claimPin = claimPin.trim(),
                    cohortScope = cohortScope,
                    localNodeUrl = CIRISApiClient.LOCAL_NODE_URL,
                    // SELF-claim: set the owner's login password + friendly username
                    // on the ROOT cert so the owner can obtain a SYSTEM_ADMIN session
                    // (POST /v1/auth/login with EITHER `eric` or the wa_id) — the
                    // prerequisite for approving a device-auth grant.
                    ownerPassword = _state.value.userPassword.ifBlank { null },
                    ownerUsername = _state.value.username.ifBlank { null },
                )
                _state.value = _state.value.copy(
                    ownershipClaim = _state.value.ownershipClaim.copy(
                        inProgress = false,
                        claimed = resp.role != null,
                        role = resp.role,
                        waId = resp.waId,
                        error = if (resp.role == null) {
                            resp.error ?: "Node did not confirm ownership"
                        } else null,
                    )
                )

                // POST-CLAIM owner sequence (now that the node is owned + the owner
                // fed-ID exists): (1) log in with the account credential to get the
                // owner SYSTEM_ADMIN session, then (2) record the age band the user
                // chose earlier via the loopback owner endpoint POST /v1/self/age.
                // Both are best-effort — a failure surfaces but never blocks COMPLETE.
                if (resp.role != null) {
                    val waId = resp.waId
                    val password = _state.value.userPassword
                    if (!waId.isNullOrBlank() && password.isNotBlank()) {
                        try {
                            val auth = client.login(waId, password)
                            client.setAccessToken(auth.access_token)
                            PlatformLogger.i(TAG, "claimLocalNodeOwnership: owner session established post-claim")
                        } catch (e: Exception) {
                            PlatformLogger.w(TAG, "claimLocalNodeOwnership: post-claim owner login failed: ${e.message}")
                        }
                    }
                    val band = _state.value.ageRange.selectedBandToken
                    if (!band.isNullOrBlank()) {
                        try {
                            val r = client.setAgeSelf(band = band, localNodeUrl = CIRISApiClient.LOCAL_NODE_URL)
                            _state.value = _state.value.copy(
                                ageRange = _state.value.ageRange.copy(recorded = true, error = null)
                            )
                            PlatformLogger.i(TAG, "claimLocalNodeOwnership: age band '$band' recorded post-claim ($r)")
                        } catch (e: Exception) {
                            PlatformLogger.w(TAG, "claimLocalNodeOwnership: post-claim age record failed: ${e.message}")
                            _state.value = _state.value.copy(
                                ageRange = _state.value.ageRange.copy(
                                    recorded = false,
                                    error = "Couldn't record your age range yet: ${e.message ?: "unknown error"}",
                                )
                            )
                        }
                    }

                    // OPTIONAL federation opt-in: if the user toggled "Announce
                    // yourself to the federation" ON, promote the owner-binding
                    // self→FEDERATION and enable the node's identity announce. The
                    // claim already succeeded, so this is NON-FATAL — on failure we
                    // surface a soft notice and let the user retry later; it never
                    // blocks COMPLETE. Takes effect on the node's next boot.
                    if (_state.value.announceOwnership) {
                        try {
                            val ann = client.announceOwnership(localNodeUrl = CIRISApiClient.LOCAL_NODE_URL)
                            PlatformLogger.i(
                                TAG,
                                "claimLocalNodeOwnership: announced to federation " +
                                    "(owner=${ann.owner} cohort=${ann.cohortScope}); " +
                                    "takes effect ${ann.announceTakesEffect ?: "next boot"}",
                            )
                            _state.value = _state.value.copy(
                                ownershipClaim = _state.value.ownershipClaim.copy(announceNotice = null)
                            )
                        } catch (e: Exception) {
                            PlatformLogger.w(TAG, "claimLocalNodeOwnership: federation announce failed (non-fatal): ${e.message}")
                            _state.value = _state.value.copy(
                                ownershipClaim = _state.value.ownershipClaim.copy(
                                    announceNotice = "You're set up, but announcing to the " +
                                        "federation didn't complete: ${e.message ?: "unknown error"}. " +
                                        "You can turn it on later.",
                                )
                            )
                        }
                    }

                    // Persist the OPTIONAL friendly device name (e.g. "Mac mini")
                    // the user typed in the fed-ID step as a CLIENT-SIDE preference
                    // so the UI can label "this device". Best-effort; never blocks.
                    // TODO(0.5.60): persist device name to the occurrence once the
                    // server has a label field on the wizard's mint/claim request.
                    val deviceName = _state.value.deviceName.trim()
                    if (deviceName.isNotBlank()) {
                        try {
                            createSecureStorage().save(PREF_DEVICE_NAME, deviceName)
                            PlatformLogger.i(TAG, "claimLocalNodeOwnership: device name '$deviceName' saved (client-side pref)")
                        } catch (e: Exception) {
                            PlatformLogger.w(TAG, "claimLocalNodeOwnership: failed to persist device name: ${e.message}")
                        }
                    }
                }
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "claimLocalNodeOwnership: self-claim via local node failed: ${e.message}")
                val msg = e.message.orEmpty()
                val isPinRejection = msg.contains("claim_pin", ignoreCase = true) ||
                    msg.contains("claim pin", ignoreCase = true) ||
                    msg.contains("invalid pin", ignoreCase = true)
                _state.value = _state.value.copy(
                    ownershipClaim = _state.value.ownershipClaim.copy(
                        inProgress = false,
                        claimed = false,
                        error = if (isPinRejection) {
                            "The node rejected the claim PIN — it may have already been " +
                                "claimed or the PIN expired."
                        } else {
                            "Couldn't claim ownership of this device's local node: " +
                                "${e.message ?: "unknown error"}"
                        },
                    )
                )
            }
        }
    }

    // ========== Accord Metrics Opt-In ==========

    /**
     * Set accord metrics consent for AI alignment research.
     * When enabled, anonymous metrics (reasoning scores, decision patterns,
     * LLM provider/API base URL) are shared with CIRIS L3C.
     * No message content or PII is ever sent.
     */
    fun setAccordMetricsConsent(consent: Boolean) {
        _state.value = _state.value.copy(accordMetricsConsent = consent)
    }

    // ========== Public API Services (Navigation & Weather) ==========

    /**
     * Set the email address for public API services (Navigation & Weather).
     * This email is included in User-Agent headers as required by
     * OpenStreetMap Nominatim and NOAA weather.gov usage policies.
     */
    fun setPublicApiEmail(email: String) {
        _state.value = _state.value.copy(publicApiEmail = email)
    }

    /**
     * Enable or disable public API services (Navigation & Weather).
     * When enabled, navigation:geocode can resolve location names to coordinates
     * for use with weather tools.
     */
    fun setPublicApiServicesEnabled(enabled: Boolean) {
        _state.value = _state.value.copy(publicApiServicesEnabled = enabled)
    }

    // ========== Template Selection (V1.9.7) ==========

    /**
     * Load available templates from the setup API.
     * Call this when entering the OPTIONAL_FEATURES step.
     */
    suspend fun loadAvailableTemplates(
        fetchFunc: suspend () -> List<AgentTemplateInfo>
    ) {
        _state.value = _state.value.copy(templatesLoading = true)
        try {
            val templates = fetchFunc()
            _state.value = _state.value.copy(
                availableTemplates = templates,
                templatesLoading = false
            )
        } catch (e: Exception) {
            _state.value = _state.value.copy(templatesLoading = false)
        }
    }

    /**
     * Set the selected template ID.
     */
    fun setSelectedTemplate(templateId: String) {
        _state.value = _state.value.copy(selectedTemplateId = templateId)
    }

    /**
     * Toggle advanced settings visibility.
     */
    fun setShowAdvancedSettings(show: Boolean) {
        _state.value = _state.value.copy(showAdvancedSettings = show)
    }

    /**
     * Get selected template name for display.
     */
    fun getSelectedTemplateName(): String {
        val templates = _state.value.availableTemplates
        val selectedId = _state.value.selectedTemplateId
        return templates.find { it.id == selectedId }?.name ?: "Default"
    }

    // ========== Adapter Configuration ==========

    /**
     * Load available adapters from the setup API.
     * Call this when entering the OPTIONAL_FEATURES step.
     *
     * Adapters with enabled_by_default=true are automatically selected.
     * This includes ciris_hosted_tools when user has CIRIS AI services.
     */
    suspend fun loadAvailableAdapters(
        fetchFunc: suspend () -> List<ai.ciris.mobile.shared.models.CommunicationAdapter>
    ) {
        _state.value = _state.value.copy(adaptersLoading = true)
        try {
            val adapters = fetchFunc()

            // Auto-select adapters that have enabled_by_default=true
            // This includes ciris_hosted_tools for CIRIS AI services users
            val autoEnabled = adapters
                .filter { it.enabled_by_default }
                .map { it.id }
                .toSet()

            // Merge with existing enabled adapters (api is always in the set)
            val newEnabled = _state.value.enabledAdapterIds + autoEnabled

            _state.value = _state.value.copy(
                availableAdapters = adapters,
                enabledAdapterIds = newEnabled,
                adaptersLoading = false
            )
        } catch (e: Exception) {
            _state.value = _state.value.copy(adaptersLoading = false)
        }
    }

    /**
     * Toggle an adapter's enabled state.
     * Note: "api" adapter cannot be disabled.
     */
    fun toggleAdapter(adapterId: String, enabled: Boolean) {
        if (adapterId == "api") return // API adapter is always enabled

        val currentEnabled = _state.value.enabledAdapterIds.toMutableSet()
        if (enabled) {
            currentEnabled.add(adapterId)
        } else {
            currentEnabled.remove(adapterId)
        }
        _state.value = _state.value.copy(enabledAdapterIds = currentEnabled)
    }

    /**
     * Check if an adapter is enabled.
     */
    fun isAdapterEnabled(adapterId: String): Boolean {
        return _state.value.enabledAdapterIds.contains(adapterId)
    }

    // ========== Adapter Wizard (for adapters requiring configuration) ==========

    /**
     * Interface for adapter wizard API calls.
     * SetupScreen provides the implementation using apiClient.
     */
    interface AdapterWizardApi {
        suspend fun getLoadableAdapters(): LoadableAdaptersData
        suspend fun startAdapterConfiguration(adapterType: String): ConfigSessionData
        suspend fun executeConfigurationStep(sessionId: String, stepData: Map<String, String>): ConfigStepResultData
        suspend fun getConfigurationSessionStatus(sessionId: String): ConfigSessionData
        suspend fun completeAdapterConfiguration(sessionId: String): ConfigCompleteData
    }

    // Stored API instance for wizard operations
    private var wizardApi: AdapterWizardApi? = null

    /**
     * Set the API instance for wizard operations.
     * Call this before starting the wizard.
     */
    fun setWizardApi(api: AdapterWizardApi) {
        wizardApi = api
    }

    /**
     * Start the adapter wizard for a specific adapter type.
     * Called when user enables an adapter that requires configuration.
     */
    fun startAdapterWizard(adapterType: String) {
        val api = wizardApi
        if (api == null) {
            PlatformLogger.e(TAG, "startAdapterWizard: No API instance set")
            _state.value = _state.value.copy(
                adapterWizardError = "Configuration not available"
            )
            return
        }

        PlatformLogger.i(TAG, "startAdapterWizard: Starting wizard for adapter type: $adapterType")
        viewModelScope.launch {
            _state.value = _state.value.copy(
                showAdapterWizard = true,
                adapterWizardType = adapterType,
                adapterWizardLoading = true,
                adapterWizardError = null,
                adapterDiscoveredItems = emptyList(),
                adapterDiscoveryExecuted = false,
                adapterSelectOptions = emptyList()
            )
            try {
                val session = api.startAdapterConfiguration(adapterType)
                _state.value = _state.value.copy(
                    adapterWizardSession = session,
                    adapterWizardLoading = false
                )
                // Auto-execute discovery step if first step is discovery type
                if (session.currentStep?.stepType == "discovery") {
                    PlatformLogger.i(TAG, "First step is discovery, auto-executing...")
                    executeAdapterDiscoveryStepInternal(session)
                }
                // Auto-fetch options for select steps
                if (session.currentStep?.stepType == "select") {
                    PlatformLogger.i(TAG, "First step is select, auto-fetching options...")
                    fetchAdapterSelectOptionsInternal(session)
                }
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "startAdapterWizard: Failed - ${e.message}")
                _state.value = _state.value.copy(
                    adapterWizardError = "Failed to start wizard: ${e.message}",
                    adapterWizardLoading = false
                )
            }
        }
    }

    /**
     * Execute the discovery step for an adapter wizard.
     */
    fun executeAdapterDiscoveryStep() {
        val session = _state.value.adapterWizardSession ?: return
        val api = wizardApi ?: return
        PlatformLogger.i(TAG, "executeAdapterDiscoveryStep: Executing discovery for session: ${session.sessionId}")
        viewModelScope.launch {
            _state.value = _state.value.copy(
                adapterWizardLoading = true,
                adapterWizardError = null
            )
            try {
                executeAdapterDiscoveryStepInternal(session)
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "executeAdapterDiscoveryStep: Failed - ${e.message}")
                _state.value = _state.value.copy(
                    adapterWizardError = "Discovery failed: ${e.message}",
                    adapterWizardLoading = false
                )
            }
        }
    }

    private suspend fun executeAdapterDiscoveryStepInternal(session: ConfigSessionData) {
        val api = wizardApi ?: return
        val result = api.executeConfigurationStep(session.sessionId, emptyMap())
        _state.value = _state.value.copy(
            adapterDiscoveryExecuted = true,
            adapterDiscoveredItems = result.discoveredItems,
            adapterWizardLoading = false
        )
        if (result.nextStepIndex != null) {
            _state.value = _state.value.copy(
                adapterWizardSession = session.copy(currentStepIndex = result.nextStepIndex)
            )
        }
    }

    private suspend fun fetchAdapterSelectOptionsInternal(session: ConfigSessionData) {
        val api = wizardApi ?: return
        try {
            val result = api.executeConfigurationStep(session.sessionId, emptyMap())
            if (result.selectOptions.isNotEmpty()) {
                PlatformLogger.i(TAG, "Fetched ${result.selectOptions.size} select options")
                _state.value = _state.value.copy(adapterSelectOptions = result.selectOptions)
            }
        } catch (e: Exception) {
            PlatformLogger.e(TAG, "fetchAdapterSelectOptionsInternal: Failed - ${e.message}")
        }
    }

    /**
     * Select a discovered item in the wizard.
     */
    fun selectAdapterDiscoveredItem(item: DiscoveredItemData) {
        val session = _state.value.adapterWizardSession ?: return
        val api = wizardApi ?: return
        PlatformLogger.i(TAG, "selectAdapterDiscoveredItem: Selected ${item.label}")
        viewModelScope.launch {
            _state.value = _state.value.copy(adapterWizardLoading = true)
            try {
                val stepData = mapOf(
                    "selected_url" to item.value,
                    "selected_id" to item.id
                )
                val result = api.executeConfigurationStep(session.sessionId, stepData)
                handleAdapterWizardStepResult(session, result)
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "selectAdapterDiscoveredItem: Failed - ${e.message}")
                _state.value = _state.value.copy(
                    adapterWizardError = "Failed to select item: ${e.message}",
                    adapterWizardLoading = false
                )
            }
        }
    }

    /**
     * Submit a manual URL in the discovery step.
     */
    fun submitAdapterManualUrl(url: String) {
        val session = _state.value.adapterWizardSession ?: return
        val api = wizardApi ?: return
        PlatformLogger.i(TAG, "submitAdapterManualUrl: Submitting URL: $url")
        viewModelScope.launch {
            _state.value = _state.value.copy(adapterWizardLoading = true)
            try {
                val stepData = mapOf("manual_url" to url)
                val result = api.executeConfigurationStep(session.sessionId, stepData)
                handleAdapterWizardStepResult(session, result)
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "submitAdapterManualUrl: Failed - ${e.message}")
                _state.value = _state.value.copy(
                    adapterWizardError = "Failed to submit URL: ${e.message}",
                    adapterWizardLoading = false
                )
            }
        }
    }

    /**
     * Submit the current wizard step with field values.
     */
    fun submitAdapterWizardStep(stepData: Map<String, String>) {
        val session = _state.value.adapterWizardSession ?: return
        val api = wizardApi ?: return
        PlatformLogger.i(TAG, "submitAdapterWizardStep: Submitting step data: $stepData")
        viewModelScope.launch {
            _state.value = _state.value.copy(
                adapterWizardLoading = true,
                adapterWizardError = null
            )
            try {
                val result = api.executeConfigurationStep(session.sessionId, stepData)
                handleAdapterWizardStepResult(session, result)
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "submitAdapterWizardStep: Failed - ${e.message}")
                _state.value = _state.value.copy(
                    adapterWizardError = "Failed to submit step: ${e.message}",
                    adapterWizardLoading = false
                )
            }
        }
    }

    /**
     * Initiate OAuth step in the adapter wizard.
     */
    fun initiateAdapterOAuthStep() {
        val session = _state.value.adapterWizardSession ?: return
        val api = wizardApi ?: return
        PlatformLogger.i(TAG, "initiateAdapterOAuthStep: Starting OAuth for session: ${session.sessionId}")
        viewModelScope.launch {
            _state.value = _state.value.copy(
                adapterWizardLoading = true,
                adapterWizardError = null
            )
            try {
                val stepData = mapOf("callback_base_url" to "http://127.0.0.1:8080")
                val result = api.executeConfigurationStep(session.sessionId, stepData)
                if (result.oauthUrl != null) {
                    PlatformLogger.i(TAG, "OAuth URL received: ${result.oauthUrl.take(80)}...")
                    _state.value = _state.value.copy(
                        adapterOAuthUrl = result.oauthUrl,
                        adapterAwaitingOAuthCallback = true,
                        adapterWizardLoading = false
                    )
                    startAdapterOAuthPolling(session.sessionId)
                } else {
                    PlatformLogger.e(TAG, "No OAuth URL in response")
                    _state.value = _state.value.copy(
                        adapterWizardError = "Failed to get OAuth URL",
                        adapterWizardLoading = false
                    )
                }
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "initiateAdapterOAuthStep: Failed - ${e.message}")
                _state.value = _state.value.copy(
                    adapterWizardError = "OAuth initiation failed: ${e.message}",
                    adapterWizardLoading = false
                )
            }
        }
    }

    private fun startAdapterOAuthPolling(sessionId: String) {
        val api = wizardApi ?: return
        adapterOAuthPollJob?.cancel()
        adapterOAuthPollJob = viewModelScope.launch {
            PlatformLogger.i(TAG, "startAdapterOAuthPolling: Starting poll for session: $sessionId")
            var attempts = 0
            val maxAttempts = 120  // 2 minutes
            while (isActive && attempts < maxAttempts && _state.value.adapterAwaitingOAuthCallback) {
                delay(1000)
                attempts++
                try {
                    val updated = api.getConfigurationSessionStatus(sessionId)
                    val currentSession = _state.value.adapterWizardSession
                    if (currentSession != null && updated.currentStepIndex > currentSession.currentStepIndex) {
                        PlatformLogger.i(TAG, "OAuth callback received - step advanced")
                        _state.value = _state.value.copy(
                            adapterAwaitingOAuthCallback = false,
                            adapterOAuthUrl = null
                        )
                        onAdapterOAuthStepAdvanced(updated)
                        return@launch
                    }
                } catch (e: Exception) {
                    if (attempts % 10 == 0) {
                        PlatformLogger.e(TAG, "OAuth poll #$attempts failed: ${e.message}")
                    }
                }
            }
            if (_state.value.adapterAwaitingOAuthCallback) {
                PlatformLogger.e(TAG, "OAuth polling timed out")
                _state.value = _state.value.copy(
                    adapterAwaitingOAuthCallback = false,
                    adapterWizardError = "OAuth authentication timed out. Please try again."
                )
            }
        }
    }

    private suspend fun onAdapterOAuthStepAdvanced(updatedSession: ConfigSessionData) {
        _state.value = _state.value.copy(
            adapterWizardSession = updatedSession,
            adapterDiscoveredItems = emptyList(),
            adapterDiscoveryExecuted = false,
            adapterSelectOptions = emptyList()
        )

        // Check if wizard is complete
        if (updatedSession.currentStepIndex >= updatedSession.totalSteps) {
            completeAdapterWizardInternal(updatedSession)
            return
        }

        // Auto-execute discovery or fetch select options for next step
        if (updatedSession.currentStep?.stepType == "discovery") {
            executeAdapterDiscoveryStepInternal(updatedSession)
        }
        if (updatedSession.currentStep?.stepType == "select") {
            fetchAdapterSelectOptionsInternal(updatedSession)
        }
    }

    /**
     * Check OAuth status on app resume.
     */
    fun checkAdapterOAuthOnResume() {
        if (!_state.value.adapterAwaitingOAuthCallback) return
        val session = _state.value.adapterWizardSession ?: return
        val api = wizardApi ?: return
        PlatformLogger.i(TAG, "checkAdapterOAuthOnResume: Checking status...")
        viewModelScope.launch {
            try {
                val updated = api.getConfigurationSessionStatus(session.sessionId)
                if (updated.currentStepIndex > session.currentStepIndex) {
                    PlatformLogger.i(TAG, "OAuth completed while app was suspended")
                    _state.value = _state.value.copy(
                        adapterAwaitingOAuthCallback = false,
                        adapterOAuthUrl = null
                    )
                    adapterOAuthPollJob?.cancel()
                    onAdapterOAuthStepAdvanced(updated)
                }
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "checkAdapterOAuthOnResume: Failed - ${e.message}")
            }
        }
    }

    private suspend fun handleAdapterWizardStepResult(session: ConfigSessionData, result: ConfigStepResultData) {
        val api = wizardApi ?: return
        try {
            val updatedSession = api.getConfigurationSessionStatus(session.sessionId)
            PlatformLogger.i(TAG, "handleAdapterWizardStepResult: Step ${updatedSession.currentStepIndex}/${updatedSession.totalSteps}")

            // Check if wizard is complete
            if (updatedSession.currentStepIndex >= updatedSession.totalSteps) {
                PlatformLogger.i(TAG, "Wizard completed!")
                completeAdapterWizardInternal(updatedSession)
                return
            }

            _state.value = _state.value.copy(
                adapterWizardSession = updatedSession,
                adapterDiscoveredItems = emptyList(),
                adapterDiscoveryExecuted = false,
                adapterSelectOptions = emptyList(),
                adapterWizardLoading = false
            )

            // Auto-execute next step if needed
            if (updatedSession.currentStep?.stepType == "discovery") {
                executeAdapterDiscoveryStepInternal(updatedSession)
            }
            if (updatedSession.currentStep?.stepType == "select") {
                fetchAdapterSelectOptionsInternal(updatedSession)
            }
        } catch (e: Exception) {
            PlatformLogger.e(TAG, "handleAdapterWizardStepResult: Failed to fetch session status - ${e.message}")
            _state.value = _state.value.copy(adapterWizardLoading = false)
            if (result.nextStepIndex != null && result.nextStepIndex >= session.totalSteps) {
                completeAdapterWizardInternal(session)
            }
        }
    }

    private suspend fun completeAdapterWizardInternal(session: ConfigSessionData) {
        val api = wizardApi ?: return
        val adapterType = _state.value.adapterWizardType
        try {
            val completeResult = api.completeAdapterConfiguration(session.sessionId)
            PlatformLogger.i(TAG, "completeAdapterWizardInternal: Completed - success=${completeResult.success}")

            // Store the collected config for this adapter
            val collectedConfig = session.collectedConfig
            val currentConfigured = _state.value.configuredAdapterData.toMutableMap()
            if (adapterType != null) {
                currentConfigured[adapterType] = collectedConfig
            }

            // Enable the adapter since it's now configured
            val currentEnabled = _state.value.enabledAdapterIds.toMutableSet()
            if (adapterType != null) {
                currentEnabled.add(adapterType)
            }

            _state.value = _state.value.copy(
                enabledAdapterIds = currentEnabled,
                configuredAdapterData = currentConfigured
            )
            closeAdapterWizard()
        } catch (e: Exception) {
            PlatformLogger.e(TAG, "completeAdapterWizardInternal: Failed - ${e.message}")
            _state.value = _state.value.copy(
                adapterWizardError = "Failed to apply configuration: ${e.message}",
                adapterWizardLoading = false
            )
        }
    }

    /**
     * Go back in the adapter wizard.
     */
    fun adapterWizardBack() {
        // For now, just close the session and clear state
        _state.value = _state.value.copy(
            adapterWizardSession = null,
            adapterWizardError = null
        )
    }

    /**
     * Close the adapter wizard dialog.
     */
    fun closeAdapterWizard() {
        PlatformLogger.i(TAG, "closeAdapterWizard: Closing wizard")
        adapterOAuthPollJob?.cancel()
        _state.value = _state.value.copy(
            showAdapterWizard = false,
            adapterWizardType = null,
            adapterWizardSession = null,
            loadableAdaptersData = null,
            adapterWizardError = null,
            adapterWizardLoading = false,
            adapterDiscoveredItems = emptyList(),
            adapterDiscoveryExecuted = false,
            adapterOAuthUrl = null,
            adapterAwaitingOAuthCallback = false,
            adapterSelectOptions = emptyList()
        )
    }

    /**
     * Reset to welcome step.
     */
    fun resetToWelcome() {
        _state.value = _state.value.copy(currentStep = SetupStep.WELCOME)
    }

    // ========== Connect to Node (Device Auth Flow) ==========

    /**
     * Update the node URL for the Connect to Node flow.
     */
    fun updateNodeUrl(url: String) {
        _state.value = _state.value.copy(
            deviceAuth = _state.value.deviceAuth.copy(nodeUrl = url)
        )
    }

    /**
     * Enter the node flow from the WELCOME step.
     * Sets isNodeFlow=true and transitions to NODE_AUTH step.
     */
    fun enterNodeFlow() {
        _state.value = _state.value.copy(
            isNodeFlow = true,
            currentStep = SetupStep.NODE_AUTH
        )
    }

    /**
     * Initiate device auth with the target CIRISNode.
     * Calls POST /v1/setup/connect-node which:
     * 1. Fetches node manifest
     * 2. Initiates device auth with Portal
     * 3. Returns verification URL for user
     *
     * @param connectFunc Platform-specific HTTP call to POST /v1/setup/connect-node
     */
    suspend fun startNodeConnection(
        connectFunc: suspend (nodeUrl: String) -> ConnectNodeResult
    ) {
        val nodeUrl = _state.value.deviceAuth.nodeUrl
        if (nodeUrl.isBlank()) return

        _state.value = _state.value.copy(
            deviceAuth = _state.value.deviceAuth.copy(
                status = DeviceAuthStatus.CONNECTING,
                error = null
            )
        )

        try {
            val result = connectFunc(nodeUrl)
            _state.value = _state.value.copy(
                deviceAuth = _state.value.deviceAuth.copy(
                    status = DeviceAuthStatus.WAITING,
                    verificationUri = result.verificationUriComplete,
                    deviceCode = result.deviceCode,
                    userCode = result.userCode,
                    portalUrl = result.portalUrl,
                    expiresIn = result.expiresIn,
                    interval = result.interval
                )
            )
        } catch (e: Exception) {
            _state.value = _state.value.copy(
                deviceAuth = _state.value.deviceAuth.copy(
                    status = DeviceAuthStatus.ERROR,
                    error = e.message ?: "Connection failed"
                )
            )
        }
    }

    /**
     * Poll for device auth completion.
     * Called periodically while status == WAITING.
     *
     * @param pollFunc Platform-specific HTTP call to GET /v1/setup/connect-node/status
     */
    suspend fun pollNodeAuthStatus(
        pollFunc: suspend (deviceCode: String, portalUrl: String) -> NodeAuthPollResult
    ) {
        PlatformLogger.i(TAG, "[pollNodeAuthStatus] ========== ENTRY ==========")
        val auth = _state.value.deviceAuth
        PlatformLogger.i(TAG, "[pollNodeAuthStatus] Current status: ${auth.status}")
        PlatformLogger.i(TAG, "[pollNodeAuthStatus] deviceCode: ${auth.deviceCode.take(16)}...")
        PlatformLogger.i(TAG, "[pollNodeAuthStatus] portalUrl: ${auth.portalUrl}")

        if (auth.status != DeviceAuthStatus.WAITING) {
            PlatformLogger.w(TAG, "[pollNodeAuthStatus] Status is ${auth.status}, not WAITING - returning early!")
            return
        }

        try {
            PlatformLogger.i(TAG, "[pollNodeAuthStatus] Invoking pollFunc...")
            val result = pollFunc(auth.deviceCode, auth.portalUrl)
            PlatformLogger.i(TAG, "[pollNodeAuthStatus] pollFunc returned: status=${result.status}, keyId=${result.keyId}, error=${result.error}")
            when (result.status) {
                "pending" -> {
                    PlatformLogger.i(TAG, "pollNodeAuthStatus: status=pending, keep polling")
                }
                "complete" -> {
                    PlatformLogger.i(TAG, "pollNodeAuthStatus: COMPLETE - keyId=${result.keyId}, signingKeyB64=${result.signingKeyB64?.take(20)}...")
                    PlatformLogger.i(TAG, "pollNodeAuthStatus: template=${result.template}, adapters=${result.adapters}")
                    _state.value = _state.value.copy(
                        deviceAuth = auth.copy(
                            status = DeviceAuthStatus.COMPLETE,
                            provisionedTemplate = result.template,
                            provisionedAdapters = result.adapters ?: emptyList(),
                            signingKeyB64 = result.signingKeyB64,
                            keyId = result.keyId,
                            orgId = result.orgId,
                            stewardshipTier = result.stewardshipTier
                        ),
                        // Lock template to provisioned value in node flow
                        selectedTemplateId = result.template ?: "default",
                        enabledAdapterIds = (result.adapters ?: emptyList()).toSet() + "api"
                    )
                }
                else -> {
                    PlatformLogger.w(TAG, "[pollNodeAuthStatus] Unknown/error status: ${result.status}, error: ${result.error}")
                    _state.value = _state.value.copy(
                        deviceAuth = auth.copy(
                            status = DeviceAuthStatus.ERROR,
                            error = result.error ?: "Authorization failed"
                        )
                    )
                }
            }
            PlatformLogger.i(TAG, "[pollNodeAuthStatus] ========== EXIT (success) ==========")
        } catch (e: Exception) {
            PlatformLogger.e(TAG, "[pollNodeAuthStatus] EXCEPTION: ${e.message}")
            PlatformLogger.e(TAG, "[pollNodeAuthStatus] Exception type: ${e::class.simpleName}")
            _state.value = _state.value.copy(
                deviceAuth = auth.copy(
                    status = DeviceAuthStatus.ERROR,
                    error = e.message ?: "Polling failed"
                )
            )
            PlatformLogger.i(TAG, "[pollNodeAuthStatus] ========== EXIT (exception) ==========")
        }
    }

    // ========== CIRISVerify Setup ==========

    /**
     * Toggle CIRISVerify installation.
     */
    fun setVerifyEnabled(enabled: Boolean) {
        _state.value = _state.value.copy(
            verifySetup = _state.value.verifySetup.copy(enabled = enabled)
        )
    }

    /**
     * Toggle hardware requirement for CIRISVerify.
     */
    fun setVerifyRequireHardware(require: Boolean) {
        _state.value = _state.value.copy(
            verifySetup = _state.value.verifySetup.copy(requireHardware = require)
        )
    }

    /**
     * Download and configure CIRISVerify binary.
     * TODO: Implement actual binary download from CIRIS CDN or GitHub releases.
     * MVP: Stub that sets downloaded=true for UI flow testing.
     *
     * @param downloadFunc Platform-specific download function
     */
    suspend fun downloadVerifyBinary(
        downloadFunc: suspend () -> VerifyDownloadResult
    ) {
        _state.value = _state.value.copy(
            verifySetup = _state.value.verifySetup.copy(
                downloading = true,
                error = null
            )
        )

        try {
            val result = downloadFunc()
            _state.value = _state.value.copy(
                verifySetup = _state.value.verifySetup.copy(
                    downloading = false,
                    downloaded = true,
                    binaryPath = result.binaryPath,
                    version = result.version
                )
            )
        } catch (e: Exception) {
            _state.value = _state.value.copy(
                verifySetup = _state.value.verifySetup.copy(
                    downloading = false,
                    error = e.message ?: "Download failed"
                )
            )
        }
    }

    // ========== Validation ==========
    // Source: SetupWizardActivity.kt:209-286

    /**
     * Get validation error message for current step, or null if valid.
     */
    fun getValidationError(): String? {
        return _state.value.getStepValidationError()
    }

    /**
     * Validate LLM configuration by making a test call.
     *
     * This should be implemented per-platform using expect/actual:
     * - Android: Use HttpURLConnection
     * - iOS: Use URLSession
     *
     * Source: POST /v1/setup/validate-llm
     */
    suspend fun validateLlmConfiguration(
        validateFunc: suspend (ValidateLlmRequest) -> LlmValidationResult
    ): LlmValidationResult {
        _state.value = _state.value.copy(isValidating = true, validationError = null)

        val currentState = _state.value

        // On-device inference does not hit any external endpoint, so
        // there is nothing to validate here — the device capability
        // probe is the validation step for this provider. Return
        // success immediately so the wizard's "Test connection" action
        // does not appear broken.
        val providerLower = currentState.llmProvider.lowercase()
        if (providerLower == LOCAL_ON_DEVICE_PROVIDER_ID ||
            providerLower.startsWith("mobile local")) {
            val ok = LlmValidationResult(
                valid = true,
                message = "On-device inference — no remote endpoint to validate",
                error = null,
            )
            _state.value = _state.value.copy(isValidating = false, validationError = null)
            return ok
        }

        val request = ValidateLlmRequest(
            provider = canonicalProviderId(currentState.llmProvider),
            api_key = currentState.llmApiKey,
            base_url = currentState.llmBaseUrl.takeIf { it.isNotEmpty() },
            model = currentState.llmModel.takeIf { it.isNotEmpty() }
        )

        val result = validateFunc(request)

        _state.value = _state.value.copy(
            isValidating = false,
            validationError = result.error
        )

        return result
    }

    // ========== Setup Completion ==========
    // Source: SetupWizardActivity.kt:288-389

    /**
     * Build setup completion request.
     *
     * This generates the JSON payload for POST /v1/setup/complete.
     * Handles both CIRIS proxy and BYOK modes.
     *
     * Source: SetupWizardActivity.kt:395-500
     */
    fun buildSetupRequest(): CompleteSetupRequest {
        val currentState = _state.value
        val useCirisProxy = currentState.useCirisProxy()

        // Debug logging for node flow
        PlatformLogger.i(TAG, "buildSetupRequest: isNodeFlow=${currentState.isNodeFlow}, deviceAuth.status=${currentState.deviceAuth.status}")
        PlatformLogger.i(TAG, "buildSetupRequest: deviceAuth.keyId=${currentState.deviceAuth.keyId}, signingKeyB64=${currentState.deviceAuth.signingKeyB64?.take(20)}...")

        // Auto-generate admin password (32 chars)
        // Source: SetupViewModel.kt:141-146
        val adminPassword = generateAdminPassword()

        // Build enabled adapters list from user selections + consent-based adapters
        val enabledAdapters = buildList {
            // Add all user-selected adapters (api is always in the set)
            addAll(currentState.enabledAdapterIds)
            // Add accord metrics adapter if consented
            if (currentState.accordMetricsConsent) {
                add("ciris_accord_metrics")
            }
            // Add navigation & weather adapters if public API services enabled
            if (currentState.publicApiServicesEnabled && currentState.publicApiEmail.isNotBlank()) {
                add("navigation")
                add("weather")
            }
            // Add mobile_local_llm adapter if on-device inference is selected
            if (currentState.llmProvider == LOCAL_ON_DEVICE_PROVIDER_ID ||
                currentState.llmProvider == LOCAL_ON_DEVICE_DISPLAY_NAME) {
                add("mobile_local_llm")
            }
        }

        // Build adapter config with consent settings and adapter-specific config
        val adapterConfig = buildMap {
            // Accord metrics settings
            if (currentState.accordMetricsConsent) {
                put("CIRIS_ACCORD_METRICS_CONSENT", "true")
                put("CIRIS_ACCORD_METRICS_TRACE_LEVEL", "detailed")
            }
            // Public API services (Navigation & Weather)
            if (currentState.publicApiServicesEnabled && currentState.publicApiEmail.isNotBlank()) {
                put("PUBLIC_API_CONTACT_EMAIL", currentState.publicApiEmail)
            }
            // Include adapter-specific config from wizard (e.g., HA OAuth tokens)
            // configuredAdapterData is Map<String, Map<String, String>>
            for ((_, config) in currentState.configuredAdapterData) {
                putAll(config)
            }
        }

        // Node flow fields (if provisioned via Portal)
        val nodeFlowData = if (currentState.isNodeFlow && currentState.deviceAuth.status == DeviceAuthStatus.COMPLETE) {
            val da = currentState.deviceAuth
            PlatformLogger.i(TAG, "Node flow COMPLETE - extracting NodeFlowData: keyId=${da.keyId}, signingKeyB64=${da.signingKeyB64?.take(20)}...")
            NodeFlowData(
                nodeUrl = da.nodeUrl.takeIf { it.isNotEmpty() },
                identityTemplate = da.provisionedTemplate,
                stewardshipTier = da.stewardshipTier,
                approvedAdapters = da.provisionedAdapters.takeIf { it.isNotEmpty() },
                orgId = da.orgId,
                signingKeyProvisioned = da.signingKeyB64 != null,
                provisionedSigningKeyB64 = da.signingKeyB64,
                keyId = da.keyId
            )
        } else {
            PlatformLogger.w(TAG, "Node flow NOT complete or not in node flow - nodeFlowData will be null (isNodeFlow=${currentState.isNodeFlow}, status=${currentState.deviceAuth.status})")
            null
        }

        return if (useCirisProxy) {
            // CIRIS Proxy mode - use Google ID token with CIRIS hosted proxy
            CompleteSetupRequest(
                llm_provider = "other", // Use "other" so backend writes OPENAI_API_BASE to .env
                llm_api_key = currentState.googleIdToken ?: "",
                llm_base_url = CIRISConfig.CIRIS_LLM_PROXY_URL,  // US: llm01.ciris-services-1.ai
                llm_model = "default",

                // European backup
                backup_llm_api_key = currentState.googleIdToken,
                backup_llm_base_url = CIRISConfig.CIRIS_LLM_PROXY_URL_EU,  // EU: llm01.ciris-services-eu-1.com
                backup_llm_model = "default",

                // Agent configuration
                template_id = nodeFlowData?.identityTemplate ?: currentState.selectedTemplateId,
                enabled_adapters = enabledAdapters,
                adapter_config = adapterConfig,
                agent_port = 8080,

                // Admin account (auto-generated)
                system_admin_password = adminPassword,

                // OAuth user
                admin_username = "oauth_${currentState.oauthProvider}_user",
                admin_password = null,
                oauth_provider = currentState.oauthProvider,
                oauth_external_id = currentState.googleUserId,
                oauth_email = currentState.googleEmail,

                // Language and location preferences (extract from selectedLocation)
                preferred_language = currentState.preferredLanguage,
                location_country = currentState.selectedLocation?.country,
                location_region = currentState.selectedLocation?.region,
                location_city = currentState.selectedLocation?.city ?: currentState.city.takeIf { it.isNotEmpty() },
                location_latitude = currentState.selectedLocation?.latitude,
                location_longitude = currentState.selectedLocation?.longitude,
                timezone = currentState.selectedLocation?.timezone,
                share_location_in_traces = currentState.shareLocationInTraces,

                // Node flow fields
                node_url = nodeFlowData?.nodeUrl,
                identity_template = nodeFlowData?.identityTemplate,
                stewardship_tier = nodeFlowData?.stewardshipTier,
                approved_adapters = nodeFlowData?.approvedAdapters,
                org_id = nodeFlowData?.orgId,
                signing_key_provisioned = nodeFlowData?.signingKeyProvisioned ?: false,  // Must be boolean, not null
                provisioned_signing_key_b64 = nodeFlowData?.provisionedSigningKeyB64,
                signing_key_id = nodeFlowData?.keyId
            )
        } else {
            // BYOK mode — user-provided API key, or keyless providers
            // (LocalAI / Ollama, or on-device Gemma 4 via the
            // mobile_local adapter). `llmProvider` already holds the
            // canonical id (set by `setLlmProvider(key)` from the
            // dropdown); `canonicalProviderId()` also maps legacy
            // display labels for back-compat.
            val providerId = canonicalProviderId(currentState.llmProvider)

            var apiKey = currentState.llmApiKey
            if (apiKey.isEmpty() && providerId == "local") {
                apiKey = "local"
            }
            if (providerId == LOCAL_ON_DEVICE_PROVIDER_ID) {
                // No external credential is required: the Python adapter
                // runs its own OpenAI-compatible server on loopback.
                apiKey = ""
            }

            // For BYOK mode, we still need OAuth fields if user authenticated via OAuth
            // This allows OAuth users to use their own API keys while still using OAuth for login
            // HA addon mode is treated as external auth (SUPERVISOR_TOKEN) - no password needed
            val isOAuthUser = currentState.isGoogleAuth && currentState.googleUserId != null
            val isExternalAuthUser = isOAuthUser || currentState.isHAAddonMode

            // Determine the effective OAuth provider
            val effectiveOAuthProvider = when {
                currentState.isHAAddonMode -> "home_assistant"
                isOAuthUser -> currentState.oauthProvider
                else -> null
            }

            CompleteSetupRequest(
                llm_provider = providerId,
                llm_api_key = apiKey,
                llm_base_url = currentState.llmBaseUrl.takeIf { it.isNotEmpty() },
                llm_model = currentState.llmModel.takeIf { it.isNotEmpty() },

                // Agent configuration
                template_id = nodeFlowData?.identityTemplate ?: currentState.selectedTemplateId,
                enabled_adapters = enabledAdapters,
                adapter_config = adapterConfig,
                agent_port = 8080,

                // Admin account (auto-generated)
                system_admin_password = adminPassword,

                // User account - external auth users get auto-generated username, local users provide their own
                admin_username = when {
                    currentState.isHAAddonMode -> "ha_admin"
                    isOAuthUser -> "oauth_${currentState.oauthProvider}_user"
                    else -> currentState.username.ifEmpty { "admin" }
                },
                admin_password = if (isExternalAuthUser) null else currentState.userPassword,

                // OAuth fields - include for any external auth (OAuth or HA addon)
                oauth_provider = effectiveOAuthProvider,
                oauth_external_id = if (isOAuthUser) currentState.googleUserId else null,
                oauth_email = if (isOAuthUser) currentState.googleEmail else null,

                // Language and location preferences (extract from selectedLocation)
                preferred_language = currentState.preferredLanguage,
                location_country = currentState.selectedLocation?.country,
                location_region = currentState.selectedLocation?.region,
                location_city = currentState.selectedLocation?.city ?: currentState.city.takeIf { it.isNotEmpty() },
                location_latitude = currentState.selectedLocation?.latitude,
                location_longitude = currentState.selectedLocation?.longitude,
                timezone = currentState.selectedLocation?.timezone,
                share_location_in_traces = currentState.shareLocationInTraces,

                // Node flow fields
                node_url = nodeFlowData?.nodeUrl,
                identity_template = nodeFlowData?.identityTemplate,
                stewardship_tier = nodeFlowData?.stewardshipTier,
                approved_adapters = nodeFlowData?.approvedAdapters,
                org_id = nodeFlowData?.orgId,
                signing_key_provisioned = nodeFlowData?.signingKeyProvisioned ?: false,  // Must be boolean, not null
                provisioned_signing_key_b64 = nodeFlowData?.provisionedSigningKeyB64,
                signing_key_id = nodeFlowData?.keyId
            )
        }
    }

    /**
     * Helper data class for node flow fields.
     */
    private data class NodeFlowData(
        val nodeUrl: String?,
        val identityTemplate: String?,
        val stewardshipTier: Int?,
        val approvedAdapters: List<String>?,
        val orgId: String?,
        val signingKeyProvisioned: Boolean?,
        val provisionedSigningKeyB64: String?,
        val keyId: String?
    )

    /**
     * Submit setup completion request.
     *
     * This should be implemented per-platform using expect/actual.
     *
     * Source: SetupWizardActivity.kt:288-389
     */
    suspend fun completeSetup(
        submitFunc: suspend (CompleteSetupRequest) -> SetupCompletionResult
    ): SetupCompletionResult {
        _state.value = _state.value.copy(isSubmitting = true, submissionError = null)

        val request = buildSetupRequest()
        PlatformLogger.i(TAG, "completeSetup: signing_key_id=${request.signing_key_id}, signing_key_provisioned=${request.signing_key_provisioned}")
        PlatformLogger.i(TAG, "completeSetup: provisioned_signing_key_b64=${request.provisioned_signing_key_b64?.take(20)}...")
        val result = submitFunc(request)

        // After setup completes (.env now exists), persist location if selected
        if (result.success) {
            val selectedLocation = _state.value.selectedLocation
            if (selectedLocation != null) {
                try {
                    val locationData = LocationResultData(
                        city = selectedLocation.city,
                        region = selectedLocation.region,
                        country = selectedLocation.country,
                        countryCode = selectedLocation.countryCode,
                        latitude = selectedLocation.latitude,
                        longitude = selectedLocation.longitude,
                        population = selectedLocation.population,
                        timezone = selectedLocation.timezone,
                        displayName = selectedLocation.displayName
                    )
                    val locResult = apiClient.updateUserLocation(locationData)
                    if (locResult.success) {
                        PlatformLogger.i(TAG, "completeSetup: Location persisted: ${locResult.locationDisplay}")
                    } else {
                        PlatformLogger.e(TAG, "completeSetup: Failed to persist location: ${locResult.message}")
                    }
                } catch (e: Exception) {
                    PlatformLogger.e(TAG, "completeSetup: Location persist error: ${e.message}")
                }
            }
        }

        _state.value = _state.value.copy(
            isSubmitting = false,
            submissionError = result.error,
            currentStep = if (result.success) SetupStep.COMPLETE else _state.value.currentStep
        )

        return result
    }

    // ========== Utilities ==========

    /**
     * Generate a random admin password (32 chars).
     * Admin password is always auto-generated - users don't need to enter it.
     *
     * Source: SetupViewModel.kt:141-146
     */
    private fun generateAdminPassword(): String {
        val chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#\$%^&*"
        return (1..32).map { chars.random() }.joinToString("")
    }

    /**
     * Reset all setup state (useful for testing or retry).
     */
    fun resetState() {
        _state.value = SetupFormState()
    }

    /**
     * Reset device auth state only.
     * Called when user backs out of NODE_AUTH step to clear any stale/error state.
     * This allows the user to retry the node flow with a clean slate.
     */
    fun resetDeviceAuth() {
        PlatformLogger.i(TAG, "resetDeviceAuth: Clearing device auth state")
        _state.value = _state.value.copy(
            deviceAuth = DeviceAuthState()  // Reset to default empty state
        )
    }
}
