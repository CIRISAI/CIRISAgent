package ai.ciris.mobile.shared.platform

/**
 * Device capability gate for the rich "cell" Interact visualization.
 *
 * The new viz (bus-membrane cell, organelles, pseudopod channels, nucleus
 * pipeline) draws dozens of animated primitives continuously. It targets
 * 64-bit devices with enough RAM to handle a steady canvas load without
 * starving the main thread or spiking battery.
 *
 * 32-bit / low-RAM devices fall through to the legacy LiveGraphBackground
 * (cylinder view), which stays frozen and unmodified as an orphaned code
 * path. This keeps CIRIS usable on constrained hardware — e.g. Ethiopia
 * deployments on older Android — without dragging the new design down to
 * their lowest-common-denominator.
 *
 * Thresholds (matched across platforms for predictability):
 *
 * - Android: arm64-v8a (or x86_64) AND total RAM ≥ 4 GB.
 * - iOS: any 64-bit iOS device with physical memory ≥ 3 GB (iPhone 11+
 *   broadly). All iOS builds are 64-bit so the ABI check is implicit.
 * - Desktop: always capable. Windows/macOS/Linux can handle the viz.
 */
data class CellVizCapability(
    /** Whether the device should render the new cell visualization. */
    val isCapable: Boolean,
    /** Total RAM in GB, for diagnostics (0.0 when unknown). */
    val totalRamGb: Double,
    /** Human-readable reason — useful for logs and debug overlays. */
    val reason: String,
)

/**
 * Probe the current device for the cell-viz capability gate.
 *
 * Pure detection — does not touch preferences or user settings. If a user
 * wants to force the legacy view on capable hardware (e.g. accessibility,
 * reduced motion), that belongs in a separate user-facing toggle.
 */
expect fun probeCellVizCapability(): CellVizCapability
