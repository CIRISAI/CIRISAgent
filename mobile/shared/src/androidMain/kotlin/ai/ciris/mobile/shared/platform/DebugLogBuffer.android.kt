package ai.ciris.mobile.shared.platform

/**
 * Android implementation of currentTimeMillis
 */
actual fun currentTimeMillis(): Long {
    return System.currentTimeMillis()
}
