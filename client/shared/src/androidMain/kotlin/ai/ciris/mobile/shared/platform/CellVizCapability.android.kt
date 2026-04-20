package ai.ciris.mobile.shared.platform

import android.app.ActivityManager
import android.content.Context
import android.os.Build
import android.util.Log

/**
 * Android implementation of the cell-viz capability probe.
 *
 * Cell viz is offered when the device is 64-bit AND has at least 4 GB of
 * RAM. This is deliberately less strict than the on-device LLM probe —
 * the viz only has to push pixels, not run a model — but strict enough
 * to skip devices that would struggle with continuous canvas animation
 * (many of the older Ethiopia-deployment targets fall below the bar).
 */

private const val ANDROID_MIN_RAM_GB = 4.0
private const val BYTES_PER_GB = 1024.0 * 1024.0 * 1024.0

private var appContext: Context? = null

/** Call once from the Application's onCreate so the probe has a Context. */
fun initCellVizProbe(context: Context) {
    appContext = context.applicationContext
}

actual fun probeCellVizCapability(): CellVizCapability {
    val context = appContext
    if (context == null) {
        Log.w("CellViz", "probeCellVizCapability: context not initialised")
        return CellVizCapability(
            isCapable = false,
            totalRamGb = 0.0,
            reason = "capability probe not initialised; call initCellVizProbe() at startup",
        )
    }

    // 64-bit check — any of these ABIs implies a 64-bit runtime.
    val abis = Build.SUPPORTED_ABIS.toList()
    val is64Bit = abis.any { it == "arm64-v8a" || it == "x86_64" }
    if (!is64Bit) {
        return CellVizCapability(
            isCapable = false,
            totalRamGb = 0.0,
            reason = "cell viz requires a 64-bit Android runtime; this device reports ABIs=$abis",
        )
    }

    val am = context.getSystemService(Context.ACTIVITY_SERVICE) as? ActivityManager
    if (am == null) {
        return CellVizCapability(
            isCapable = false,
            totalRamGb = 0.0,
            reason = "ActivityManager unavailable; cannot determine device RAM",
        )
    }
    val memInfo = ActivityManager.MemoryInfo()
    am.getMemoryInfo(memInfo)
    val totalRamGb = memInfo.totalMem.toDouble() / BYTES_PER_GB

    return if (totalRamGb >= ANDROID_MIN_RAM_GB) {
        CellVizCapability(
            isCapable = true,
            totalRamGb = totalRamGb,
            reason = "64-bit Android with %.1f GB RAM — cell viz enabled".format(totalRamGb),
        )
    } else {
        CellVizCapability(
            isCapable = false,
            totalRamGb = totalRamGb,
            reason = "Android device has %.1f GB RAM; cell viz requires %.1f GB".format(totalRamGb, ANDROID_MIN_RAM_GB),
        )
    }
}
