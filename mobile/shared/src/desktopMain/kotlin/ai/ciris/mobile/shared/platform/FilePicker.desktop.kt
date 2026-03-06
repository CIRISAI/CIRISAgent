package ai.ciris.mobile.shared.platform

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import javax.swing.JFileChooser
import javax.swing.filechooser.FileNameExtensionFilter
import kotlin.io.encoding.Base64
import kotlin.io.encoding.ExperimentalEncodingApi

@OptIn(ExperimentalEncodingApi::class)
@Composable
actual fun FilePickerDialog(
    show: Boolean,
    mimeTypes: List<String>,
    onFilePicked: (PickedFile) -> Unit,
    onDismiss: () -> Unit
) {
    LaunchedEffect(show) {
        if (!show) return@LaunchedEffect

        val result = withContext(Dispatchers.IO) {
            showNativeFileChooser(mimeTypes)
        }

        if (result != null) {
            onFilePicked(result)
        } else {
            onDismiss()
        }
    }
}

@OptIn(ExperimentalEncodingApi::class)
private fun showNativeFileChooser(mimeTypes: List<String>): PickedFile? {
    val chooser = JFileChooser().apply {
        dialogTitle = "Select file to attach"
        isMultiSelectionEnabled = false

        // Build extension filters from MIME types
        val extensions = mutableListOf<String>()
        for (mime in mimeTypes) {
            when (mime) {
                "image/jpeg" -> extensions.addAll(listOf("jpg", "jpeg"))
                "image/png" -> extensions.add("png")
                "image/gif" -> extensions.add("gif")
                "image/webp" -> extensions.add("webp")
                "application/pdf" -> extensions.add("pdf")
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document" -> extensions.add("docx")
            }
        }

        if (extensions.isNotEmpty()) {
            fileFilter = FileNameExtensionFilter(
                "Supported files (${extensions.joinToString(", ") { "*.$it" }})",
                *extensions.toTypedArray()
            )
        }
    }

    val result = chooser.showOpenDialog(null)
    if (result != JFileChooser.APPROVE_OPTION) return null

    val file = chooser.selectedFile ?: return null
    return readDesktopFile(file)
}

@OptIn(ExperimentalEncodingApi::class)
private fun readDesktopFile(file: File): PickedFile? {
    return try {
        val sizeBytes = file.length()
        if (sizeBytes > PickedFile.MAX_FILE_SIZE_BYTES) {
            println("[FilePicker] File too large: $sizeBytes bytes")
            return null
        }

        val bytes = file.readBytes()
        val base64 = Base64.encode(bytes)
        val mediaType = guessMimeType(file.name)

        PickedFile(
            name = file.name,
            mediaType = mediaType,
            dataBase64 = base64,
            sizeBytes = sizeBytes
        )
    } catch (e: Exception) {
        println("[FilePicker] Failed to read file: ${e.message}")
        null
    }
}

private fun guessMimeType(fileName: String): String {
    val ext = fileName.substringAfterLast('.', "").lowercase()
    return when (ext) {
        "jpg", "jpeg" -> "image/jpeg"
        "png" -> "image/png"
        "gif" -> "image/gif"
        "webp" -> "image/webp"
        "pdf" -> "application/pdf"
        "docx" -> "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else -> "application/octet-stream"
    }
}
