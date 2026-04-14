package ai.ciris.mobile.shared.platform

import android.app.ActivityManager
import android.content.Context
import android.os.Build
import android.util.Log

/**
 * Android implementation of the local-inference capability probe.
 *
 * Mirrors the thresholds used by the Python `mobile_local_llm` adapter:
 *
 * - Total RAM ≥ 8 GB → [LocalInferenceTier.CAPABLE_E4B]
 * - Total RAM ≥ 6 GB → [LocalInferenceTier.CAPABLE_E2B]
 * - arm64 required; 32-bit devices are reported as [LocalInferenceTier.INCAPABLE]
 *
 * We do not consult free disk here — the Python adapter owns the model
 * download path and re-checks disk before spawning the inference server.
 * The wizard just needs to know whether to show the option.
 */

private const val ANDROID_E2B_MIN_RAM_GB = 6.0
private const val ANDROID_E4B_MIN_RAM_GB = 8.0
private const val BYTES_PER_GB = 1024.0 * 1024.0 * 1024.0

/**
 * Application context stash populated by [initLocalInferenceProbe].
 * Reuses the same pattern as `initUrlOpener` in Platform.android.kt so
 * that probes never need to traipse through static Android globals.
 */
private var probeContext: Context? = null

/** Call once during app startup to enable the capability probe. */
fun initLocalInferenceProbe(context: Context) {
    probeContext = context.applicationContext
}

actual fun probeLocalInferenceCapability(): LocalInferenceCapability {
    val context = probeContext
    if (context == null) {
        Log.w("LocalInference", "probeLocalInferenceCapability: context not initialized")
        return LocalInferenceCapability(
            tier = LocalInferenceTier.INCAPABLE,
            totalRamGb = 0.0,
            reason = "capability probe not initialised; call initLocalInferenceProbe() at startup",
        )
    }

    val abi = Build.SUPPORTED_ABIS.firstOrNull().orEmpty()
    if (abi != "arm64-v8a") {
        return LocalInferenceCapability(
            tier = LocalInferenceTier.INCAPABLE,
            totalRamGb = 0.0,
            reason = "local Gemma 4 builds require arm64-v8a; this device is $abi",
        )
    }

    val activityManager = context.getSystemService(Context.ACTIVITY_SERVICE) as? ActivityManager
    if (activityManager == null) {
        return LocalInferenceCapability(
            tier = LocalInferenceTier.INCAPABLE,
            totalRamGb = 0.0,
            reason = "ActivityManager unavailable; cannot determine device RAM",
        )
    }

    val memInfo = ActivityManager.MemoryInfo()
    activityManager.getMemoryInfo(memInfo)
    val totalRamGb = memInfo.totalMem.toDouble() / BYTES_PER_GB

    return when {
        totalRamGb >= ANDROID_E4B_MIN_RAM_GB -> LocalInferenceCapability(
            tier = LocalInferenceTier.CAPABLE_E4B,
            totalRamGb = totalRamGb,
            reason = "Android device with %.1f GB RAM — can run Gemma 4 E4B on-device".format(totalRamGb),
        )
        totalRamGb >= ANDROID_E2B_MIN_RAM_GB -> LocalInferenceCapability(
            tier = LocalInferenceTier.CAPABLE_E2B,
            totalRamGb = totalRamGb,
            reason = "Android device with %.1f GB RAM — can run Gemma 4 E2B on-device".format(totalRamGb),
        )
        else -> LocalInferenceCapability(
            tier = LocalInferenceTier.INCAPABLE,
            totalRamGb = totalRamGb,
            reason = "Android device has %.1f GB RAM; on-device Gemma 4 requires at least %.1f GB".format(totalRamGb, ANDROID_E2B_MIN_RAM_GB),
        )
    }
}
