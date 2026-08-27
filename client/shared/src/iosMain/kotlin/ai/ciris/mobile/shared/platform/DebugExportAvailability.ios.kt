package ai.ciris.mobile.shared.platform

/** Sandboxed app; the manager is a server deployment. */
actual fun isManagedDeployment(): Boolean = false
