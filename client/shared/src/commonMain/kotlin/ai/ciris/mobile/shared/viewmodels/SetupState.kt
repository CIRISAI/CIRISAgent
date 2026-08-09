package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.localization.LocalizationHelper
import ai.ciris.mobile.shared.models.CommunicationAdapter
import ai.ciris.mobile.shared.models.ConfigSessionData
import ai.ciris.mobile.shared.models.DiscoveredItemData
import ai.ciris.mobile.shared.models.LoadableAdaptersData
import ai.ciris.mobile.shared.models.SelectOptionData
import ai.ciris.mobile.shared.models.SetupMode
import ai.ciris.mobile.shared.models.ToolDisclosureReport
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
     * Screen 1 — **You**. One question: who are you?
     *
     * Merges the former WELCOME, ACCOUNT_AND_CONFIRMATION,
     * FEDERATION_IDENTITY_SETUP and AGE_RANGE. Those were four screens asking
     * the same question in four vocabularies: WELCOME collected nothing (169
     * lines, no interactive elements), the fed-ID copy already says "your
     * portable digital identity — how the network knows it is you", and the age
     * band is a property of the same person. The mint carries no reference to
     * the local account and its ordering is not enforced, so there is no reason
     * to ask twice.
     *
     * Collects: fed-ID name (required), username + password (required), device
     * name (optional), age range (optional, declining sets the protective
     * default). The fed-ID mint keeps its OWN button — it is an apex act with a
     * hardware ceremony, and hiding it behind Next would strand the user with no
     * legible cause when it fails.
     */
    YOU,

    /**
     * Screen 2 — **Join the federation**. One question: do you join?
     *
     * The consent decision, rendered from `ciris_server.consent_disclosure()`
     * rather than composed here. Announce is the FLOOR for service (a node that
     * does not announce gets no service access), sending traces and being scored
     * are two separate grants, and rough location is optional with named costs.
     *
     * The wizard only COLLECTS this. `author_consent_embedded` refuses on an
     * unclaimed node ("there is no owner on whose behalf to consent"), so
     * completion performs it after the claim. That is a substrate constraint,
     * not a design choice.
     */
    JOIN_FEDERATION,

    /**
     * Screen 3 — **AI**. One question: what powers it?
     *
     * Agent builds only ([CIRISBuild.HAS_AGENT]); the node client has no brain
     * to configure. Arrives pre-answered for almost everyone — the CIRIS proxy
     * on OAuth mobile, on-device inference on capable desktops — and every
     * keyless option is listed ahead of the ones that need a key.
     *
     * This step CANNOT simply be skipped. Any path that ends without a usable
     * provider must write `CIRIS_SERVICES_DISABLED=true`, or the NEXT boot makes
     * `llm_service` critical and initialization aborts instead of degrading.
     */
    AI,

    /**
     * Final step: Setup is complete.
     */
    COMPLETE
}

/**
 * The ONE forward transition. Not two branches — the old `isNodeFlow` fork
 * produced byte-identical transitions on both sides, which is a duplicate
 * pretending to be a choice.
 *
 * @param hasAgent [CIRISBuild.HAS_AGENT] — the node client has no brain, so it
 *        has no AI screen to show.
 */
fun nextSetupStep(current: SetupStep, hasAgent: Boolean): SetupStep = when (current) {
    SetupStep.YOU -> SetupStep.JOIN_FEDERATION
    SetupStep.JOIN_FEDERATION -> if (hasAgent) SetupStep.AI else SetupStep.COMPLETE
    SetupStep.AI -> SetupStep.COMPLETE
    SetupStep.COMPLETE -> SetupStep.COMPLETE
}

/** The exact mirror of [nextSetupStep]. */
fun previousSetupStep(current: SetupStep, hasAgent: Boolean): SetupStep = when (current) {
    SetupStep.YOU -> SetupStep.YOU
    SetupStep.JOIN_FEDERATION -> SetupStep.YOU
    SetupStep.AI -> SetupStep.JOIN_FEDERATION
    SetupStep.COMPLETE -> if (hasAgent) SetupStep.AI else SetupStep.JOIN_FEDERATION
}

/** Is [step] the last one the user acts on before the wizard completes? */
fun isFinalSetupStep(step: SetupStep, hasAgent: Boolean): Boolean =
    step == (if (hasAgent) SetupStep.AI else SetupStep.JOIN_FEDERATION)

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
 * Location sharing granularity for user preferences.
 * Mirrors the CLI wizard's location options from wizard.py:377-382.
 */
@Serializable
enum class LocationGranularity {
    NONE,           // Prefer not to say
    COUNTRY,        // Country only
    REGION,         // Country + Region/State
    CITY            // Country + Region + City
}

/**
 * Supported language for the PREFERENCES step.
 * Mirrors localization/manifest.json (29 languages).
 * ISO 639-1 codes with native names for display.
 */
data class SupportedLanguage(
    val code: String,        // ISO 639-1 code (e.g., "en", "am")
    val nativeName: String,  // Name in native script (e.g., "English", "አማርኛ")
    val englishName: String  // Name in English for accessibility
)

/**
 * Available languages for selection in the PREFERENCES step.
 * Sorted alphabetically by English name for consistent, culturally-neutral ordering.
 * Matches localization/manifest.json.
 */
val SUPPORTED_LANGUAGES = listOf(
    SupportedLanguage("am", "አማርኛ", "Amharic"),
    SupportedLanguage("ar", "العربية", "Arabic"),
    SupportedLanguage("bn", "বাংলা", "Bengali"),
    SupportedLanguage("my", "မြန်မာ", "Burmese"),
    SupportedLanguage("zh", "中文", "Chinese"),
    SupportedLanguage("en", "English", "English"),
    SupportedLanguage("fr", "Français", "French"),
    SupportedLanguage("de", "Deutsch", "German"),
    SupportedLanguage("ha", "Hausa", "Hausa"),
    SupportedLanguage("hi", "हिन्दी", "Hindi"),
    SupportedLanguage("id", "Bahasa Indonesia", "Indonesian"),
    SupportedLanguage("it", "Italiano", "Italian"),
    SupportedLanguage("ja", "日本語", "Japanese"),
    SupportedLanguage("ko", "한국어", "Korean"),
    SupportedLanguage("mr", "मराठी", "Marathi"),
    SupportedLanguage("fa", "فارسی", "Persian"),
    SupportedLanguage("pt", "Português", "Portuguese"),
    SupportedLanguage("pa", "ਪੰਜਾਬੀ", "Punjabi"),
    SupportedLanguage("ru", "Русский", "Russian"),
    SupportedLanguage("es", "Español", "Spanish"),
    SupportedLanguage("sw", "Kiswahili", "Swahili"),
    SupportedLanguage("ta", "தமிழ்", "Tamil"),
    SupportedLanguage("te", "తెలుగు", "Telugu"),
    SupportedLanguage("th", "ไทย", "Thai"),
    SupportedLanguage("tr", "Türkçe", "Turkish"),
    SupportedLanguage("uk", "Українська", "Ukrainian"),
    SupportedLanguage("ur", "اردو", "Urdu"),
    SupportedLanguage("vi", "Tiếng Việt", "Vietnamese"),
    SupportedLanguage("yo", "Yorùbá", "Yoruba")
)

/**
 * Supported currency for display and conversion.
 * Uses ISO 4217 codes.
 */
data class SupportedCurrency(
    val code: String,        // ISO 4217 code (e.g., "USD", "EUR")
    val symbol: String,      // Currency symbol (e.g., "$", "€")
    val name: String,        // English name (e.g., "US Dollar")
    val nativeName: String,  // Native/local name
    val decimals: Int = 2    // Decimal places for display
)

/**
 * Available currencies for wallet display conversion.
 * Sorted by common usage. USDC is the native wallet currency.
 * Exchange rates are fetched at runtime from CurrencyManager.
 */
val SUPPORTED_CURRENCIES = listOf(
    // Native crypto
    SupportedCurrency("USDC", "$", "USDC", "USD Coin", 2),
    // Major fiat
    SupportedCurrency("USD", "$", "US Dollar", "US Dollar", 2),
    SupportedCurrency("EUR", "€", "Euro", "Euro", 2),
    SupportedCurrency("GBP", "£", "British Pound", "Pound Sterling", 2),
    SupportedCurrency("JPY", "¥", "Japanese Yen", "円", 0),
    SupportedCurrency("CNY", "¥", "Chinese Yuan", "人民币", 2),
    // Regional
    SupportedCurrency("ETB", "Br", "Ethiopian Birr", "ብር", 2),
    SupportedCurrency("INR", "₹", "Indian Rupee", "रुपया", 2),
    SupportedCurrency("KRW", "₩", "South Korean Won", "원", 0),
    SupportedCurrency("BRL", "R$", "Brazilian Real", "Real", 2),
    SupportedCurrency("MXN", "$", "Mexican Peso", "Peso Mexicano", 2),
    SupportedCurrency("RUB", "₽", "Russian Ruble", "Рубль", 2),
    SupportedCurrency("TRY", "₺", "Turkish Lira", "Türk Lirası", 2),
    SupportedCurrency("ZAR", "R", "South African Rand", "Rand", 2),
    SupportedCurrency("NGN", "₦", "Nigerian Naira", "Naira", 2),
    SupportedCurrency("KES", "KSh", "Kenyan Shilling", "Shilingi", 2),
    // Crypto
    SupportedCurrency("BTC", "₿", "Bitcoin", "Bitcoin", 8),
    SupportedCurrency("ETH", "Ξ", "Ethereum", "Ethereum", 6)
)

/**
 * Location search result from GeoNames database.
 * Used for typeahead autocomplete in the PREFERENCES step.
 */
data class LocationSearchResult(
    val city: String,
    val region: String?,
    val country: String,
    val countryCode: String,
    val latitude: Double,
    val longitude: Double,
    val population: Int,
    val timezone: String?,
    val displayName: String  // Pre-formatted "City, Region, Country"
)

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
 * State for the FEDERATION_IDENTITY_SETUP step.
 *
 * Tracks the hardware-key ceremony: whether the platform can mint a
 * hardware-rooted identity, progress, the resulting identity key id, and any
 * error. The actual key material + attestation blob are NOT held here (they are
 * transient and sent straight to /v1/self/login).
 */
@Serializable
data class FederationIdentitySetupState(
    /** Whether the platform reports a usable hardware authenticator. */
    val hardwareAvailable: Boolean = false,
    /** Probe completed (so the UI knows availability is meaningful). */
    val probed: Boolean = false,
    val inProgress: Boolean = false,
    /** Set once self-login admitted the identity. */
    val admitted: Boolean = false,
    /** Identity key id after a successful ceremony. */
    val identityKeyId: String? = null,
    val error: String? = null,
    // ── Mint inputs (driven into the local node's POST /v1/self/identity) ──
    /** REQUIRED unique identity name → the local node's `label-fingerprint`
     *  key_id. Must be non-blank and not a generic default (see [isLabelValid]);
     *  this is the single canonical name the user's federation identity is keyed
     *  by, so an empty/generic value would collide identities across devices. */
    val label: String = "",
    /** Custody backend hint. ALWAYS `null` now — the only option is the SECURE
     *  one: the substrate auto-picks the most secure custody available
     *  (YubiKey → TPM/Secure-Enclave → software). The UI exposes no selection. */
    val backend: String? = null,
    // ── Associate-existing-Fed-ID path (adopt prior crypto — same user) ──
    /** The user chose "associate existing Fed ID" instead of minting a new one. */
    val associateExisting: Boolean = false,
    /** The existing federation key_id (or fedcode) to associate. */
    val associateKeyId: String = "",
    // ── Mint result (the public surface returned by the local node) ──
    /** True once the local node minted a USER identity (vs only reporting one). */
    val minted: Boolean = false,
    /** The shareable `CIRIS-V2-…` fedcode the local node returned. */
    val fedcode: String? = null,
    /** The honest hardware-tier label ("YubiKey" / "TPM / Secure Enclave" /
     *  "software") the local node reported. */
    val hardwareLabel: String? = null,
) {
    /**
     * Is the entered [label] a usable, UNIQUE federation-identity name?
     *
     * The label is now REQUIRED (it names + keys the user's federation identity,
     * via the local node's `derive_key_id(label, pubkey)`). We reject:
     *  - blank / whitespace-only input (a name is mandatory), and
     *  - the generic node defaults `ciris-client` / `ciris-client-user`, which
     *    caused TWO machines to mint DIFFERENT identities under the SAME alias —
     *    the collision this gate exists to prevent. The user must choose a
     *    meaningful, unique name (e.g. `firstname-lastname-v1`).
     */
    fun isLabelValid(): Boolean {
        val trimmed = label.trim()
        if (trimmed.isEmpty()) return false
        return trimmed.lowercase() !in REJECTED_GENERIC_LABELS
    }

    companion object {
        /**
         * Generic default labels that MUST NOT name a federation identity. These
         * are the node-launch `--key-id` (`ciris-client`) and the identity it
         * would derive by default (`ciris-client-user`); reusing them across
         * devices collides distinct identities under one alias. Matched
         * case-insensitively against the trimmed label.
         */
        val REJECTED_GENERIC_LABELS = setOf("ciris-client", "ciris-client-user")
    }
}

/**
 * State for the AGE_RANGE onboarding step (the foundational protective gate).
 *
 * The app holds NO keys: the selected band is sent to THIS device's local node
 * (`POST /v1/safety/age-assurance`, self level) which signs + records it. This
 * state only tracks the user's selection + the in-flight/result of that drive.
 * `null` [selectedBand] = not yet chosen.
 */
@Serializable
data class AgeRangeSetupState(
    /** The user's chosen band as the server token (`minor` / `adult`), or null
     *  if not yet selected. Kept as the raw token to avoid leaking the safety
     *  enum into the serializable setup state. */
    val selectedBandToken: String? = null,
    val inProgress: Boolean = false,
    /** Set once the local node recorded the self-declared assurance. */
    val recorded: Boolean = false,
    /** The `age_self_declared:{band}:v1` dimension the node returned. */
    val dimension: String? = null,
    val error: String? = null,
)

/**
 * State for the UNDER-18 STEWARDSHIP request (CIRIS Constitution 0.5.1 §2580 —
 * the minor-stewardship rule).
 *
 * When the founder self-declares the `minor` age band they MUST NOT self-claim
 * ownership; instead the wizard produces a **stewardship request** the minor
 * hands to an over-18 adult. The adult's signature on a live
 * `delegates_to(adult-user → minor-user)` (CC 2.4.1) IS the agreement to be the
 * accountable responsible party (CC 0.5.1 §2580). Until a live adult steward
 * accepts, the minor's account is **fail-secure**: it cannot operate. If the
 * steward is ever withdrawn/superseded-without-replacement the account pauses
 * until re-stewarded — identical posture to a steward-less node/agent.
 *
 * The app holds NO keys. This state only tracks the hand-off artifact (a claim
 * URL + PIN, mirroring the delegation-offer shape) and the in-flight/result of
 * generating it. The adult ACCEPTS out-of-band on their own device/session.
 */
@Serializable
data class MinorStewardshipState(
    val inProgress: Boolean = false,
    /** True once a hand-off stewardship request artifact has been generated. */
    val requested: Boolean = false,
    /** The claim URL the minor hands to their adult steward (the adult opens it
     *  on their own device to ACCEPT and sign `delegates_to(adult → minor)`). */
    val requestUrl: String? = null,
    /** The short human-handover PIN the adult enters to accept stewardship. */
    val requestPin: String? = null,
    /** Seconds until the request PIN expires. */
    val expiresIn: Long = 0,
    /** True once a live adult steward has accepted (account unlocked). Stays
     *  false through the wizard — acceptance happens out-of-band — so the
     *  account remains fail-secure until the steward signs. */
    val stewardAccepted: Boolean = false,
    val error: String? = null,
)

/**
 * State for the LOCAL-node ownership self-claim performed on setup COMPLETE.
 *
 * After the local account + federation ID exist, the setup flow drives the LOCAL
 * node to claim ownership so the just-created user becomes the node's ROOT/owner.
 * The app holds NO keys: the local node builds + signs the owner-binding in its
 * substrate (`POST /v1/setup/claim-remote` self-targeted → its own
 * `/v1/setup/root`). This state only tracks the in-flight/result for the UI.
 */
@Serializable
data class NodeOwnershipClaimState(
    val inProgress: Boolean = false,
    /** True once the local node bound this user as ROOT/owner. */
    val claimed: Boolean = false,
    /** The bridged role on success (`SYSTEM_ADMIN`). */
    val role: String? = null,
    /** The claimed `wa_id` on success. */
    val waId: String? = null,
    /** Human-readable failure reason (e.g. "claim PIN not captured"). */
    val error: String? = null,
    /**
     * Non-fatal soft notice from the optional federation-announce opt-in. The
     * claim itself already succeeded; the announce can be retried later, so a
     * failure here is surfaced (not fatal). Null when not attempted / succeeded.
     */
    val announceNotice: String? = null,
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
    val currentStep: SetupStep = SetupStep.YOU,

    // Home Assistant addon mode: skips login and user creation
    val isHAAddonMode: Boolean = false,

    // Device auth state (Connect to Node flow)
    val deviceAuth: DeviceAuthState = DeviceAuthState(),

    // CIRISVerify setup state (node flow only)
    val verifySetup: VerifySetupState = VerifySetupState(),

    // Federation identity setup state (the mint card on screen 1)
    val federationIdentity: FederationIdentitySetupState = FederationIdentitySetupState(),

    // Age-range state (the foundational protective gate, on screen 1)
    val ageRange: AgeRangeSetupState = AgeRangeSetupState(),

    // Under-18 stewardship request state (CC 0.5.1 §2580). Populated only when
    // the founder self-declares the `minor` band; the minor cannot self-claim
    // ownership and must hand an adult a stewardship request to be accepted.
    val minorStewardship: MinorStewardshipState = MinorStewardshipState(),

    // LOCAL-node ownership self-claim state (driven on setup COMPLETE)
    val ownershipClaim: NodeOwnershipClaimState = NodeOwnershipClaimState(),

    // Google/Apple OAuth state
    val isGoogleAuth: Boolean = false,
    val googleIdToken: String? = null,
    val googleEmail: String? = null,
    val googleUserId: String? = null,
    val oauthProvider: String = "google", // "google" or "apple"

    // Language and location preferences
    // Mirrors CLI wizard fields from wizard.py:324-395
    val preferredLanguage: String = "en",  // ISO 639-1 code
    val locationGranularity: LocationGranularity = LocationGranularity.NONE,
    val country: String = "",
    val region: String = "",
    val city: String = "",
    // Consent to share location data in telemetry/traces
    // When enabled, location is included in anonymized telemetry
    val shareLocationInTraces: Boolean = false,

    // Location search state (typeahead autocomplete)
    val locationSearchQuery: String = "",
    @kotlinx.serialization.Transient
    val locationSearchResults: List<LocationSearchResult> = emptyList(),
    val locationSearchLoading: Boolean = false,
    // Selected location from search (auto-fills country/region/city)
    @kotlinx.serialization.Transient
    val selectedLocation: LocationSearchResult? = null,

    // Setup mode. Defaults to LOCAL_ON_DEVICE: this is the AI-free CIRIS NODE
    // client (agent optional), so there is no LLM/proxy choice — the node always
    // runs locally. This makes needsLocalAccountStep()=true + showLocalUserFields()
    // =true, so first-run ALWAYS asks for a local login/account to associate the
    // fed-ID + node ownership to (the agent inherits this; it only adds the brain).
    val setupMode: SetupMode? = SetupMode.LOCAL_ON_DEVICE,

    // LLM configuration (for BYOK mode)
    val llmProvider: String = "OpenAI",      // "OpenAI", "Anthropic", "LocalAI", "Azure OpenAI"
    val llmApiKey: String = "",
    val llmBaseUrl: String = "",
    val llmModel: String = "",

    // User account (for non-Google users only)
    val username: String = "",
    val email: String = "",
    val userPassword: String = "",
    val userPasswordConfirm: String = "",

    /**
     * OPTIONAL friendly per-device name (e.g. "Mac mini") — distinct from the
     * federation-identity label (which names the human's fed-ID). Empty is
     * allowed. There is no server field for this on the wizard's mint/claim
     * requests today, so it is persisted as a CLIENT-SIDE preference and used to
     * label "this device" in the UI. See [SetupViewModel.setDeviceName].
     */
    val deviceName: String = "",

    /**
     * Opt IN to an EXTERNAL hardware token (YubiKey / PKCS#11) as the custody
     * root for the federation identity. Defaults OFF: the mint then requests the
     * platform ladder — TPM/Secure-Enclave when available, software (keychain /
     * sealed-at-rest) as the last resort — which works on every device without a
     * token. Turning this ON routes the mint to pkcs11; if no token is present the
     * node falls back DOWN the same ladder rather than failing (server-side).
     *
     * Was defaulted ON + hard-mapped to pkcs11, which 500'd on any machine without
     * a YubiKey (libykcs11 missing) — see CIRISServer 0.5.61. The full priority is:
     * YubiKey (if available AND selected) → TPM/SE (if available) → software.
     */
    val secureWith2FA: Boolean = false,

    /**
     * ANNOUNCE this owner to the federation — `POST /v1/federation/announce`.
     * Promotes the owner-binding self→FEDERATION and enables the node's identity
     * announce so the community can find and federate with this node. Takes
     * effect on next boot; applied best-effort post-claim (see
     * [SetupViewModel.claimLocalNodeOwnership]).
     *
     * ON by default, and this is NOT a privacy default being overridden — it is
     * the FLOOR for service. The substrate is unambiguous: "a node that does not
     * announce gets no service access on the mesh and no agent services",
     * because the accord's kill switch is only meaningful against a node it can
     * reach. Turning it off leaves a working private node with no federation;
     * defaulting it off silently disabled the product while calling itself
     * "recommended".
     */
    val announceOwnership: Boolean = true,

    /**
     * **Send traces** — `consent:replication:v1`. The peer may HOLD your traces.
     * ON by default: this is the primary action of screen 2 and the substrate
     * marks the grant `required: true` within a mesh participation consent.
     */
    val accordMetricsConsent: Boolean = true,

    /**
     * **Be scored** — CC#46 `analyze`. The peer may SCORE your traces, which is
     * what builds reputation. A SEPARATE grant on the opposite edge: granting
     * one does not grant the other. ON by default, but genuinely declinable —
     * the substrate publishes three named costs and says in as many words that
     * marking it required "misrepresents a legitimate choice as a
     * misconfiguration". It shipped hardcoded true with no UI until 2.9.14.
     */
    val traceAnalyze: Boolean = true,

    /**
     * **Run without AI** — writes `CIRIS_SERVICES_DISABLED=true`, the same state
     * `POST /v1/system/llm/ciris-services/disable` produces, which is what keeps
     * `llm_service` optional at boot.
     *
     * NEVER a default. Defaulting it on would disable a working agent on capable
     * hardware and turn off CIRIS services on the platforms where they are the
     * entire point.
     */
    val runWithoutAi: Boolean = false,

    // Public API Services (Navigation & Weather)
    // Email included in User-Agent header for Nominatim (OSM) and weather.gov (NOAA)
    // Required by their usage policies for contact if issues arise
    // Default to support@ciris.ai so users don't need to enter email
    val publicApiEmail: String = "support@ciris.ai",
    val publicApiServicesEnabled: Boolean = false,

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

    // Tool disclosure (#941): exactly what each adapter choice grants the agent,
    // generated server-side from the live tool services. Disclosure only --
    // wide tool access is intended and nothing here gates or defaults anything off.
    // null = not fetched (or fetch failed); the UI must say so rather than imply
    // that a choice grants nothing.
    @kotlinx.serialization.Transient
    val toolDisclosure: ToolDisclosureReport? = null,
    val toolDisclosureLoading: Boolean = false,
    // Adapter ids (and always-on group ids) whose tool list is expanded
    val expandedToolDisclosureIds: Set<String> = emptySet(),

    // Adapter wizard state (for adapters that require configuration)
    // This mirrors AdaptersViewModel's wizard state for use during setup
    val showAdapterWizard: Boolean = false,
    val adapterWizardType: String? = null,  // Adapter type being configured (e.g., "home_assistant")
    @kotlinx.serialization.Transient
    val loadableAdaptersData: LoadableAdaptersData? = null,
    @kotlinx.serialization.Transient
    val adapterWizardSession: ConfigSessionData? = null,
    val adapterWizardError: String? = null,
    val adapterWizardLoading: Boolean = false,
    @kotlinx.serialization.Transient
    val adapterDiscoveredItems: List<DiscoveredItemData> = emptyList(),
    val adapterDiscoveryExecuted: Boolean = false,
    val adapterOAuthUrl: String? = null,
    val adapterAwaitingOAuthCallback: Boolean = false,
    @kotlinx.serialization.Transient
    val adapterSelectOptions: List<SelectOptionData> = emptyList(),
    // Map of adapterId -> completed configuration for adapters configured during setup
    val configuredAdapterData: Map<String, Map<String, String>> = emptyMap(),

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
     * Did the founder self-declare the `minor` (under-18) age band?
     *
     * When true the minor-stewardship rule (CC 0.5.1 §2580) applies: the minor
     * MUST NOT self-claim ownership and must instead hand an over-18 adult a
     * stewardship request. Drives the AGE_RANGE step's under-18 branch and the
     * fail-secure skip of the local-node self-claim on COMPLETE.
     */
    fun isMinorBand(): Boolean {
        return ageRange.selectedBandToken == "minor"
    }

    /**
     * Check if local user account fields should be shown.
     * Source: SetupViewModel.kt:133-135
     */
    fun showLocalUserFields(): Boolean {
        return !isGoogleAuth
    }

    /**
     * The keyless LLM providers — on-device inference and local inference
     * servers. Mirrors the backend's own whitelist (`KEYLESS_LLM_PROVIDERS` in
     * `routes/setup/complete.py`); a provider outside this set with no key is
     * not a configuration, it is an unfinished one.
     */
    fun isKeylessLlmProvider(): Boolean {
        val p = llmProvider.lowercase()
        return p == "localai" || p == "local" || p == "local_inference" ||
            p == "mobile_local" || p.startsWith("mobile local") || p.startsWith("local inference")
    }

    /**
     * Does the AI screen currently describe something that will actually run?
     *
     * "Run without AI" counts — it is an explicit, complete answer that writes
     * `CIRIS_SERVICES_DISABLED=true`. The untouched default (provider "OpenAI",
     * no key) does not.
     */
    fun hasUsableLlmChoice(): Boolean = when {
        runWithoutAi -> true
        setupMode == SetupMode.CIRIS_PROXY -> isGoogleAuth && googleIdToken != null
        llmProvider.isEmpty() -> false
        isKeylessLlmProvider() -> true
        else -> llmApiKey.isNotEmpty()
    }

    /**
     * Check if current step is valid and can proceed to next.
     */
    fun canProceedFromCurrentStep(): Boolean = when (currentStep) {
        // Screen 1 asks four things; three of them can block. The fed-ID needs a
        // valid, non-generic name (or an already-minted identity), the local
        // account needs a matching password pair, and a self-declared MINOR must
        // have generated a stewardship request first — that last one is
        // fail-secure (CC 0.5.1 §2580): an under-18 founder must not self-claim.
        // The age band itself is optional; declining sets the protective default.
        SetupStep.YOU -> {
            val fedIdOk = federationIdentity.minted ||
                federationIdentity.admitted ||
                federationIdentity.isLabelValid()
            val accountOk = if (showLocalUserFields()) {
                username.isNotEmpty() && userPassword.length >= 8 &&
                    userPassword == userPasswordConfirm
            } else {
                true
            }
            val stewardshipOk = !isMinorBand() || minorStewardship.requested
            fedIdOk && accountOk && stewardshipOk
        }

        // Every consent here is a real choice with a stated default, including
        // declining all of them. Nothing to block on.
        SetupStep.JOIN_FEDERATION -> true

        SetupStep.AI -> hasUsableLlmChoice()

        SetupStep.COMPLETE -> true
    }

    /**
     * Does this setup create a local admin account?
     *
     * For OAuth users (Google/Apple) the WA identity comes from the provider,
     * and HA addon mode authenticates via SUPERVISOR_TOKEN — both bypass local
     * username/password. Everyone else needs the first human user created
     * before COMPLETE, or the wizard ships an empty `admin_password` to
     * /v1/setup/complete and the desktop login fails (the 2.7.5 incident).
     */
    fun needsLocalAccountStep(): Boolean {
        if (isGoogleAuth) return false
        if (isHAAddonMode) return false
        // CIRIS_PROXY without isGoogleAuth shouldn't really exist (the proxy
        // mode requires Google/Apple), but be defensive — only require the
        // local-account step when the user is actually password-bound.
        return setupMode == SetupMode.BYOK || setupMode == SetupMode.LOCAL_ON_DEVICE
    }

    /**
     * Get validation error for current step — the reason Next is disabled.
     */
    fun getStepValidationError(): String? = when (currentStep) {
        SetupStep.YOU -> {
            val fedIdError = if (federationIdentity.minted || federationIdentity.admitted) {
                null
            } else {
                val trimmed = federationIdentity.label.trim()
                when {
                    trimmed.isEmpty() ->
                        LocalizationHelper.getString("setup_validation_fedid_label_required")
                    trimmed.lowercase() in FederationIdentitySetupState.REJECTED_GENERIC_LABELS ->
                        LocalizationHelper.getString("setup_validation_fedid_label_generic")
                    else -> null
                }
            }
            val accountError = if (showLocalUserFields()) {
                when {
                    username.isEmpty() -> LocalizationHelper.getString("setup_validation_username_required")
                    userPassword.isEmpty() -> LocalizationHelper.getString("setup_validation_password_required")
                    userPassword.length < 8 -> LocalizationHelper.getString("setup_validation_password_length")
                    userPassword != userPasswordConfirm -> LocalizationHelper.getString("setup_validation_password_mismatch")
                    else -> null
                }
            } else {
                null
            }
            val stewardshipError = if (isMinorBand() && !minorStewardship.requested) {
                LocalizationHelper.getString("setup_validation_minor_steward_required")
            } else {
                null
            }
            fedIdError ?: accountError ?: stewardshipError
        }

        SetupStep.JOIN_FEDERATION -> null

        SetupStep.AI -> when {
            runWithoutAi -> null
            setupMode == SetupMode.CIRIS_PROXY && googleIdToken == null ->
                LocalizationHelper.getString("setup_validation_google_required")
            llmProvider.isEmpty() -> LocalizationHelper.getString("setup_validation_select_provider")
            !isKeylessLlmProvider() && llmApiKey.isEmpty() ->
                LocalizationHelper.getString("setup_validation_api_key_required")
            else -> null
        }

        SetupStep.COMPLETE -> null
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
 * Discovered local LLM server from network discovery.
 * Source: POST /v1/setup/discover-local-llm
 */
@Serializable
data class DiscoveredLlmServer(
    /** Unique server ID (ip_port format) */
    val id: String,
    /** Display label (e.g., "jetson.local:8080 (Gemma 4)") */
    val label: String,
    /** Server URL (http://ip:port) */
    val url: String,
    /** Server type: ollama, llama_cpp, vllm, lmstudio, localai, openai_compatible */
    @SerialName("server_type")
    val serverType: String,
    /** Number of models available */
    @SerialName("model_count")
    val modelCount: Int = 0,
    /** Model names available on server */
    val models: List<String> = emptyList()
)

/**
 * Result of starting a local LLM server.
 * Source: POST /v1/setup/start-local-server
 */
@Serializable
data class StartLocalServerResult(
    /** Whether the server was started successfully */
    val success: Boolean,
    /** Human-readable message explaining the result */
    val message: String,
    /** Server URL if started (http://127.0.0.1:port) */
    @SerialName("server_url")
    val serverUrl: String? = null,
    /** Server type that was started: llama_cpp, ollama */
    @SerialName("server_type")
    val serverType: String? = null,
    /** Model being loaded */
    val model: String? = null,
    /** Process ID of the server */
    val pid: Int? = null,
    /** Estimated seconds until server is ready to accept requests */
    @SerialName("estimated_ready_seconds")
    val estimatedReadySeconds: Int = 60,
    /** Whether the model needs to be downloaded first */
    @SerialName("requires_download")
    val requiresDownload: Boolean = false,
    /** Human-readable download size (e.g., "~2.5 GB") */
    @SerialName("download_size")
    val downloadSize: String? = null
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
    /** CIRIS Agent version */
    @SerialName("agent_version")
    val agentVersion: String? = null,
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
    val registryMismatchFiles: Map<String, JsonElement>? = null,

    // =========================================================================
    // CIRISVerify 1.2.x: Hardware Trust Detection
    // =========================================================================
    // Detects SoC-level vulnerabilities (CVE-2026-20435, CVE-2026-21385) that compromise TEE

    /** THE KEY FLAG - True if hardware security is compromised. When true, wallet is RECEIVE-ONLY. */
    @SerialName("hardware_trust_degraded")
    val hardwareTrustDegraded: Boolean = false,
    /** Human-readable reason (e.g., "Vulnerable MediaTek SoC detected") */
    @SerialName("trust_degradation_reason")
    val trustDegradationReason: String? = null,
    /** SoC manufacturer (mediatek, qualcomm, samsung, etc.) */
    @SerialName("soc_manufacturer")
    val socManufacturer: String? = null,
    /** SoC model identifier (mt6893, sm8550, etc.) */
    @SerialName("soc_model")
    val socModel: String? = null,
    /** Android security patch level (YYYY-MM-DD) */
    @SerialName("security_patch_level")
    val securityPatchLevel: String? = null,
    /** Device is an emulator */
    @SerialName("is_emulator")
    val isEmulator: Boolean = false,
    /** Sophisticated emulator hiding detection */
    @SerialName("is_suspicious_emulator")
    val isSuspiciousEmulator: Boolean = false,
    /** Bootloader is unlocked (if detectable) */
    @SerialName("bootloader_unlocked")
    val bootloaderUnlocked: Boolean? = null,
    /** TEE implementation (TrustZone, StrongBox, etc.) */
    @SerialName("tee_implementation")
    val teeImplementation: String? = null,
    /** Device shows signs of root access */
    @SerialName("is_rooted")
    val isRooted: Boolean = false,
    /** List of limitations explaining why trust is degraded */
    @SerialName("hardware_limitations")
    val hardwareLimitations: List<HardwareLimitationData>? = null,
    /** CVE details for vulnerable hardware */
    @SerialName("security_advisories")
    val securityAdvisories: List<SecurityAdvisoryData>? = null
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
        // L4: Module integrity check (excludes server-only files correctly)
        val l4Passed = l3Passed && moduleIntegrityOk
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

/**
 * CIRISVerify 1.2.x: Hardware limitation explaining trust degradation.
 * Each limitation may have an associated security advisory (CVE).
 */
@Serializable
data class HardwareLimitationData(
    /** Type: Emulator, VulnerableSoC, OutdatedPatchLevel, RootedDevice, etc. */
    @SerialName("limitation_type")
    val limitationType: String,
    /** Affected manufacturer (mediatek, qualcomm, etc.) */
    val manufacturer: String? = null,
    /** Associated security advisory if applicable */
    val advisory: SecurityAdvisoryData? = null,
    /** Human-readable explanation */
    val reason: String? = null,
    /** Current security patch level on device */
    @SerialName("current_patch")
    val currentPatch: String? = null,
    /** Minimum required patch level to remediate */
    @SerialName("minimum_patch")
    val minimumPatch: String? = null
)

/**
 * CIRISVerify 1.2.x: Security advisory for hardware vulnerabilities.
 * Contains CVE details for UI display.
 */
@Serializable
data class SecurityAdvisoryData(
    /** CVE identifier (e.g., "CVE-2026-20435") */
    val cve: String,
    /** Brief title (e.g., "MediaTek TEE Key Extraction") */
    val title: String,
    /** Impact description (e.g., "Key extraction possible in <45s") */
    val impact: String,
    /** Whether a software patch can fix this (false for silicon-level vulns) */
    @SerialName("software_patchable")
    val softwarePatchable: Boolean,
    /** Minimum patch level that fixes (if software_patchable) */
    @SerialName("min_patch_level")
    val minPatchLevel: String? = null
)
