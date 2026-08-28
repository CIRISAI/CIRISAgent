package ai.ciris.mobile.shared.platform

/**
 * Web has no local CIRIS state directory to erase — the node is remote and its
 * data is not this browser's to delete. Reports false rather than pretending, so
 * the UI can say so instead of claiming a wipe that did not happen.
 */
actual fun wipeLocalData(): Boolean = false
