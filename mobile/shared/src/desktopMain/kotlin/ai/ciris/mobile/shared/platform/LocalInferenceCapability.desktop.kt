package ai.ciris.mobile.shared.platform

/**
 * Desktop implementation of the local-inference capability probe.
 *
 * The first-start wizard does not offer the on-device option on desktop.
 * Desktop developers who want to exercise the adapter can opt in via the
 * Python config flag `CIRIS_MOBILE_LOCAL_LLM_ALLOW_DESKTOP=1`, which the
 * adapter honours at runtime. From the UI's perspective the option is
 * simply hidden.
 */
actual fun probeLocalInferenceCapability(): LocalInferenceCapability {
    return LocalInferenceCapability(
        tier = LocalInferenceTier.INCAPABLE,
        totalRamGb = 0.0,
        reason = "on-device Gemma 4 is a mobile-only option; use a cloud provider on desktop",
    )
}
