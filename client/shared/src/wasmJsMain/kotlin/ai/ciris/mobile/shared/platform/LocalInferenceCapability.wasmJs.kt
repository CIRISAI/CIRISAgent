package ai.ciris.mobile.shared.platform

actual fun probeLocalInferenceCapability(): LocalInferenceCapability = LocalInferenceCapability(
    tier = LocalInferenceTier.INCAPABLE,
    totalRamGb = 0.0,
    reason = "Local inference not available in web browsers"
)
