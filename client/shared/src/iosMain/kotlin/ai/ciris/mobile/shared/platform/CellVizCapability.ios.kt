package ai.ciris.mobile.shared.platform

import platform.Foundation.NSProcessInfo

/**
 * iOS implementation of the cell-viz capability probe.
 *
 * All supported iOS devices are 64-bit (iPhone 5S and later), so the only
 * meaningful filter is RAM. A 3 GB threshold broadly means iPhone 11 and
 * newer — devices with enough CPU + GPU headroom to draw the cell at 60fps
 * while the Python runtime is also active in the same process.
 */

private const val IOS_MIN_RAM_GB = 3.0
private const val BYTES_PER_GB = 1024.0 * 1024.0 * 1024.0

actual fun probeCellVizCapability(): CellVizCapability {
    val totalRamBytes = NSProcessInfo.processInfo.physicalMemory.toDouble()
    val totalRamGb = totalRamBytes / BYTES_PER_GB
    val ramText = "%.1f".format(totalRamGb)

    return if (totalRamGb >= IOS_MIN_RAM_GB) {
        CellVizCapability(
            isCapable = true,
            totalRamGb = totalRamGb,
            reason = "iOS with $ramText GB RAM — cell viz enabled",
        )
    } else {
        CellVizCapability(
            isCapable = false,
            totalRamGb = totalRamGb,
            reason = "iOS has $ramText GB RAM; cell viz requires ${"%.1f".format(IOS_MIN_RAM_GB)} GB",
        )
    }
}
