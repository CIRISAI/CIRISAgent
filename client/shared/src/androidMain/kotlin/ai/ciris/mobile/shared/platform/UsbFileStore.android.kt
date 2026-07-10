package ai.ciris.mobile.shared.platform

// TODO: wire the Storage Access Framework (ACTION_OPEN_DOCUMENT_TREE → DocumentFile)
// for removable media, mirroring DirectoryPickerDialog. Until then node-list
// save/restore over USB is a no-op stub on Android.
actual suspend fun writeTextFile(dir: String, filename: String, contents: String): Boolean = false

actual suspend fun readTextFile(dir: String, filename: String): String? = null
