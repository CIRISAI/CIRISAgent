package ai.ciris.mobile.shared.platform

/**
 * Web implementation - always capable since modern browsers can handle the viz.
 */
actual fun probeCellVizCapability(): CellVizCapability = CellVizCapability(
    isCapable = true,
    totalRamGb = 0.0,  // Unknown on web
    reason = "Web browsers can handle the cell visualization"
)
