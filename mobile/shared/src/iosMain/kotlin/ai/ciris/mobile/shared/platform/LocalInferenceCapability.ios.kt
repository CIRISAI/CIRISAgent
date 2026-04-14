package ai.ciris.mobile.shared.platform

import platform.Foundation.NSDocumentDirectory
import platform.Foundation.NSFileManager
import platform.Foundation.NSProcessInfo
import platform.Foundation.NSSearchPathForDirectoriesInDomains
import platform.Foundation.NSUserDomainMask

/**
 * iOS implementation of the local-inference capability probe.
 *
 * Per the Google AI Edge guidance for Gemma 4 on iPhone:
 *
 * - AI Edge Gallery now ships on iOS, but LiteRT-LM iOS model bundles
 *   are not yet distributed with the CIRIS app.
 * - Capable iOS hardware (arm64, ≥ 6 GB RAM) is therefore reported as
 *   [LocalInferenceTier.IOS_STUB] — the wizard shows the on-device
 *   option labelled "coming soon" and keeps it disabled until a model
 *   bundle is installed at the expected path.
 * - Anyone who side-loads a model into
 *   `Documents/ciris/models/gemma-4-litert.bundle` will see the tier
 *   flip to CAPABLE_E2B / CAPABLE_E4B automatically on next app launch.
 */

private const val IOS_E2B_MIN_RAM_GB = 6.0
private const val IOS_E4B_MIN_RAM_GB = 8.0
private const val BYTES_PER_GB = 1024.0 * 1024.0 * 1024.0

/** Documents-relative path at which a LiteRT-LM iOS model bundle is expected. */
private const val IOS_MODEL_BUNDLE_NAME = "ciris/models/gemma-4-litert.bundle"

actual fun probeLocalInferenceCapability(): LocalInferenceCapability {
    val processInfo = NSProcessInfo.processInfo
    val totalRamBytes = processInfo.physicalMemory.toDouble()
    val totalRamGb = totalRamBytes / BYTES_PER_GB
    val ramGbText = formatOneDecimal(totalRamGb)

    // iOS is arm64 everywhere it matters since iPhone 5S (2013). We keep
    // the check for parity with Android and for the simulator case.
    val isArm64 = processInfo.operatingSystemVersionString.contains("arm64") ||
        processInfo.environment["SIMULATOR_DEVICE_NAME"] == null
    if (!isArm64) {
        return LocalInferenceCapability(
            tier = LocalInferenceTier.INCAPABLE,
            totalRamGb = totalRamGb,
            reason = "iOS device does not appear to be arm64; on-device Gemma 4 requires arm64",
        )
    }

    if (totalRamGb < IOS_E2B_MIN_RAM_GB) {
        return LocalInferenceCapability(
            tier = LocalInferenceTier.INCAPABLE,
            totalRamGb = totalRamGb,
            reason = "iOS device has $ramGbText GB RAM; on-device Gemma 4 requires at least " +
                "${formatOneDecimal(IOS_E2B_MIN_RAM_GB)} GB",
        )
    }

    // Hardware is capable. Check whether the user already has a model
    // bundle installed; if not, return the IOS_STUB tier per the user
    // requirement ("on apple, leave it as a stub if an adequate model
    // does not exist").
    val hasModelBundle = iosModelBundleExists()
    if (!hasModelBundle) {
        return LocalInferenceCapability(
            tier = LocalInferenceTier.IOS_STUB,
            totalRamGb = totalRamGb,
            reason = "iOS device is capable ($ramGbText GB RAM), but no on-device Gemma 4 model " +
                "bundle is installed yet. Install one at Documents/$IOS_MODEL_BUNDLE_NAME or wait " +
                "for a future release.",
        )
    }

    return if (totalRamGb >= IOS_E4B_MIN_RAM_GB) {
        LocalInferenceCapability(
            tier = LocalInferenceTier.CAPABLE_E4B,
            totalRamGb = totalRamGb,
            reason = "iOS device with $ramGbText GB RAM and installed model bundle — " +
                "can run Gemma 4 E4B on-device",
        )
    } else {
        LocalInferenceCapability(
            tier = LocalInferenceTier.CAPABLE_E2B,
            totalRamGb = totalRamGb,
            reason = "iOS device with $ramGbText GB RAM and installed model bundle — " +
                "can run Gemma 4 E2B on-device",
        )
    }
}

/** Returns true if the expected LiteRT-LM model bundle is present in Documents/. */
private fun iosModelBundleExists(): Boolean {
    val documentsPath = NSSearchPathForDirectoriesInDomains(
        NSDocumentDirectory,
        NSUserDomainMask,
        true,
    ).firstOrNull() as? String ?: return false
    val fullPath = "$documentsPath/$IOS_MODEL_BUNDLE_NAME"
    return NSFileManager.defaultManager.fileExistsAtPath(fullPath)
}

/** Format a Double with one decimal place without depending on String.format (Kotlin/Native). */
private fun formatOneDecimal(value: Double): String {
    val rounded = (value * 10.0).toLong() / 10.0
    return rounded.toString()
}
