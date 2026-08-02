package ai.ciris.mobile.shared.platform

import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

actual suspend fun writeTextFile(dir: String, filename: String, contents: String): Boolean =
    withContext(Dispatchers.IO) {
        try {
            val target = File(dir)
            if (!target.isDirectory) return@withContext false
            File(target, filename).writeText(contents)
            true
        } catch (e: Exception) {
            false
        }
    }

actual suspend fun readTextFile(dir: String, filename: String): String? =
    withContext(Dispatchers.IO) {
        try {
            val file = File(dir, filename)
            if (file.isFile) file.readText() else null
        } catch (e: Exception) {
            null
        }
    }
