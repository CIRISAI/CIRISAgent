package ai.ciris.mobile.shared.platform

actual fun appendToFile(path: String, text: String) {
    console.log(text)  // Log to console instead of file
}
actual fun getFileSize(path: String): Long = 0L
actual fun deleteFile(path: String) {}
actual fun renameFile(from: String, to: String) {}
actual fun ensureDirectoryExists(path: String) {}
actual fun getCurrentTimestamp(): String = js("new Date().toISOString()") as String
actual fun getKMPLogDir(): String = "/logs"
