package ai.ciris.mobile.shared.platform

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.platform.LocalContext
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
    val context = LocalContext.current

    val launcher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenDocument()
    ) { uri: Uri? ->
        if (uri == null) {
            onDismiss()
            return@rememberLauncherForActivityResult
        }
        val picked = readFileFromUri(context, uri)
        if (picked != null) {
            onFilePicked(picked)
        } else {
            onDismiss()
        }
    }

    LaunchedEffect(show) {
        if (show) {
            launcher.launch(mimeTypes.toTypedArray())
        }
    }
}

@OptIn(ExperimentalEncodingApi::class)
private fun readFileFromUri(context: Context, uri: Uri): PickedFile? {
    return try {
        val contentResolver = context.contentResolver
        val mimeType = contentResolver.getType(uri) ?: "application/octet-stream"

        // Get filename and size
        var fileName = "attachment"
        var fileSize = 0L
        contentResolver.query(uri, null, null, null, null)?.use { cursor ->
            if (cursor.moveToFirst()) {
                val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                if (nameIndex >= 0) fileName = cursor.getString(nameIndex) ?: "attachment"
                val sizeIndex = cursor.getColumnIndex(OpenableColumns.SIZE)
                if (sizeIndex >= 0) fileSize = cursor.getLong(sizeIndex)
            }
        }

        if (fileSize > PickedFile.MAX_FILE_SIZE_BYTES) {
            PlatformLogger.w("FilePicker", "File too large: $fileSize bytes")
            return null
        }

        // Read bytes and encode to base64
        val bytes = contentResolver.openInputStream(uri)?.use { it.readBytes() } ?: return null
        val base64 = Base64.encode(bytes)

        PickedFile(
            name = fileName,
            mediaType = mimeType,
            dataBase64 = base64,
            sizeBytes = bytes.size.toLong()
        )
    } catch (e: Exception) {
        PlatformLogger.e("FilePicker", "Failed to read file: ${e.message}")
        null
    }
}
