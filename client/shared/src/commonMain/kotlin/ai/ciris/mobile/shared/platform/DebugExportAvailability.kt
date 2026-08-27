package ai.ciris.mobile.shared.platform

/**
 * Is on-device diagnostics export offered on this deployment?
 *
 * **Desktop and mobile only.** Two exclusions, for different reasons:
 *
 * **Web** — there is nothing to export. The node is remote, its logs are not
 * this browser's to read, and neither saving a file nor the clipboard is
 * reliably available. Offering a "download logs" button that yields an empty
 * buffer is worse than not offering it: it looks like the diagnostics ran and
 * found nothing. Web is also why the log buffer is not populated there at all.
 *
 * **Managed** (CIRIS-Manager, `/app`) — the operator already owns the logs by a
 * better route. These are multi-tenant deployments where the person in front of
 * the UI is not necessarily the person entitled to the node's diagnostics, and a
 * bundle carries environment, device and recent activity. The affordance exists
 * for someone holding the device, which is exactly the case a managed
 * deployment is not.
 *
 * The screens this gates — login, startup, interact — are all reachable in both
 * excluded cases, so the check has to be here rather than assumed from context.
 */
fun isDebugExportAvailable(): Boolean {
    if (isWeb()) return false
    if (isManagedDeployment()) return false
    return true
}

/**
 * Running under CIRIS-Manager? Detected from the filesystem layout the manager
 * creates, mirroring `get_ciris_home()`'s own `/app` check — there is no env var
 * to read, and inventing one would be a second source of truth.
 */
expect fun isManagedDeployment(): Boolean
