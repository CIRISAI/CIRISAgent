package ai.ciris.mobile.shared.platform

/**
 * Minimal text-file IO against a directory the user chose (typically a mounted
 * USB folder via [DirectoryPickerDialog]).
 *
 * This is the node-list sibling of the fed-ID USB import: a private/offline owner
 * can carry their list of known nodes across devices by sneakernet without ever
 * announcing to the federation. The fed-ID import only READS, server-side (the
 * local node opens the folder via `associateFedId`); the node list is a small
 * plain-JSON file the client writes + reads directly, so it needs its own
 * platform seam.
 *
 * - Desktop: `java.io.File`.
 * - Android/iOS/wasm: no-op stubs ([writeTextFile] returns `false`,
 *   [readTextFile] returns `null`) until the SAF tree / document-picker file path
 *   is wired — exactly the posture [DirectoryPickerDialog] holds on those targets.
 */
expect suspend fun writeTextFile(dir: String, filename: String, contents: String): Boolean

expect suspend fun readTextFile(dir: String, filename: String): String?
