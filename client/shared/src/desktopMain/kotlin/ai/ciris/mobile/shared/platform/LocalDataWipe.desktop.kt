package ai.ciris.mobile.shared.platform

import java.io.File

/**
 * Desktop wipe: the CIRIS_HOME directory.
 *
 * Resolution order matches the runtime's own: CIRIS_HOME, then CIRIS_DATA_DIR,
 * then ~/ciris. Guessing a different path here would delete nothing and report
 * success, which is the failure this whole change exists to remove.
 */
actual fun wipeLocalData(): Boolean {
    val path = System.getenv("CIRIS_HOME")?.takeIf { it.isNotBlank() }
        ?: System.getenv("CIRIS_DATA_DIR")?.takeIf { it.isNotBlank() }
        ?: (System.getProperty("user.home")?.let { "$it/ciris" })
        ?: return false

    val home = File(path)
    if (!home.exists()) return true  // already absent is the state we want

    runCatching { home.deleteRecursively() }
    return !home.exists()
}
