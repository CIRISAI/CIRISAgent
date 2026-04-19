package ai.ciris.mobile.shared.platform

import kotlinx.datetime.Clock

/**
 * WASM/JS implementation of currentTimeMillis.
 * Uses kotlinx.datetime for cross-platform compatibility.
 */
actual fun currentTimeMillis(): Long = Clock.System.now().toEpochMilliseconds()
