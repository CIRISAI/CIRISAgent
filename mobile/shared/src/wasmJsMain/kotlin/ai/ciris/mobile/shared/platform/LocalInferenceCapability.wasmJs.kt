package ai.ciris.mobile.shared.platform

actual fun probeLocalInferenceCapability(): LocalInferenceCapability = LocalInferenceCapability(
    isCapable = false,
    reason = "Local inference not available in web browsers",
    availableModels = emptyList()
)
