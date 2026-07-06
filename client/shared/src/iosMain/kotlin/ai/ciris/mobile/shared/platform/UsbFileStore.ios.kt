package ai.ciris.mobile.shared.platform

// TODO: wire UIDocumentPickerViewController (folder mode) for external storage,
// mirroring DirectoryPickerDialog. Until then node-list save/restore over USB is
// a no-op stub on iOS.
actual suspend fun writeTextFile(dir: String, filename: String, contents: String): Boolean = false

actual suspend fun readTextFile(dir: String, filename: String): String? = null
