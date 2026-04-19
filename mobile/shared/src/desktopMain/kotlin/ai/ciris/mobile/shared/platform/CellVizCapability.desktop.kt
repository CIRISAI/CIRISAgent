package ai.ciris.mobile.shared.platform

/**
 * Desktop implementation of the cell-viz capability probe.
 *
 * Desktops (Windows, macOS, Linux) are always treated as capable — modern
 * desktop hardware has more than enough CPU, RAM, and GPU to render the
 * cell viz comfortably. We still surface the detected RAM for diagnostics
 * so support tickets can include a concrete number.
 */

private const val BYTES_PER_GB = 1024.0 * 1024.0 * 1024.0

actual fun probeCellVizCapability(): CellVizCapability {
    val totalBytes = Runtime.getRuntime().maxMemory().toDouble()
    val totalRamGb = totalBytes / BYTES_PER_GB
    return CellVizCapability(
        isCapable = true,
        totalRamGb = totalRamGb,
        reason = "Desktop platform — cell viz always enabled",
    )
}
