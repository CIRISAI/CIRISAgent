package ai.ciris.mobile.shared.platform

// Browsers have no concept of a server-side directory path; node-list save/restore
// over a USB folder is a no-op stub on wasm (matches DirectoryPickerDialog).
actual suspend fun writeTextFile(dir: String, filename: String, contents: String): Boolean = false

actual suspend fun readTextFile(dir: String, filename: String): String? = null
