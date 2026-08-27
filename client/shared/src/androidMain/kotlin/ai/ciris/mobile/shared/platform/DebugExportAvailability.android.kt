package ai.ciris.mobile.shared.platform

/** A phone is never CIRIS-Manager-managed: the manager is a server deployment. */
actual fun isManagedDeployment(): Boolean = false
