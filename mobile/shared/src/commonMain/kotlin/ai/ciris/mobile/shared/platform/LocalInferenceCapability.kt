package ai.ciris.mobile.shared.platform

/**
 * Device capability tier for the on-device Gemma 4 inference adapter.
 *
 * Mirrors the Python-side `DeviceTier` enum in
 * `ciris_adapters/mobile_local_llm/config.py`. Keeping the set of values
 * aligned lets the wizard map the backend capability probe straight onto
 * UI states without translation.
 */
enum class LocalInferenceTier {
    /** Device has ≥ 8 GB RAM and an arm64 mobile CPU — can run E2B and E4B. */
    CAPABLE_E4B,
    /** Device has ≥ 6 GB RAM and an arm64 mobile CPU — can run E2B. */
    CAPABLE_E2B,
    /**
     * iOS hardware looks capable but no Gemma 4 model bundle is shipped
     * yet. The wizard shows this as "Coming soon" and disables selection.
     */
    IOS_STUB,
    /** Device cannot safely run local inference. The wizard hides the option. */
    INCAPABLE
}

/**
 * Minimal capability snapshot the wizard uses to decide whether — and
 * how — to offer the local on-device LLM option.
 *
 * @property tier The coarse-grained bucket the device falls into.
 * @property totalRamGb Total device RAM in GB (0.0 when unknown).
 * @property reason Human-readable explanation, shown in the UI as a tooltip / subtitle.
 */
data class LocalInferenceCapability(
    val tier: LocalInferenceTier,
    val totalRamGb: Double,
    val reason: String,
) {
    /** True when the wizard should offer the local option as a normal choice. */
    val isReady: Boolean get() = tier == LocalInferenceTier.CAPABLE_E2B || tier == LocalInferenceTier.CAPABLE_E4B

    /** True when the wizard should show the option but mark it "coming soon". */
    val isComingSoon: Boolean get() = tier == LocalInferenceTier.IOS_STUB

    /** True when the wizard should hide the local option entirely. */
    val isHidden: Boolean get() = tier == LocalInferenceTier.INCAPABLE
}

/**
 * Probe the current device and report whether it can run local inference.
 *
 * This is intentionally pure UI-side: the wizard uses it to decide
 * whether to surface the on-device option. The actual inference server
 * is owned by the Python `mobile_local_llm` adapter, which runs its own
 * capability probe and owns the subprocess lifecycle.
 *
 * Platform expectations:
 *
 * - Android: read RAM via `ActivityManager`, verify ABI is `arm64-v8a`,
 *   apply the same 6 GB / 8 GB thresholds the Python probe uses.
 * - iOS: read RAM via `NSProcessInfo.processInfo.physicalMemory`, verify
 *   arm64, return `IOS_STUB` because no LiteRT-LM iOS model is shipped
 *   yet (the user will need to install one before `isReady` flips true).
 * - Desktop: always return `INCAPABLE` — desktop dev opt-in is handled
 *   via the Python config flag, not the wizard.
 */
expect fun probeLocalInferenceCapability(): LocalInferenceCapability
