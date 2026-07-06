package ai.ciris.mobile.shared.platform

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import java.io.File
import javax.swing.JFileChooser
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Composable
actual fun DirectoryPickerDialog(
    show: Boolean,
    onDirectoryPicked: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    LaunchedEffect(show) {
        if (!show) return@LaunchedEffect
        val path = withContext(Dispatchers.IO) { chooseDirectory() }
        if (path != null) onDirectoryPicked(path) else onDismiss()
    }
}

private fun chooseDirectory(): String? {
    val chooser = JFileChooser().apply {
        dialogTitle = "Select the mounted USB folder"
        fileSelectionMode = JFileChooser.DIRECTORIES_ONLY
        isMultiSelectionEnabled = false
        // Start at the common removable-media mount roots when one exists, so the
        // holder lands near their USB key instead of $HOME.
        val user = System.getProperty("user.name") ?: ""
        listOf("/media/$user", "/run/media/$user", "/media", "/Volumes")
            .map(::File)
            .firstOrNull { it.isDirectory }
            ?.let { currentDirectory = it }
    }
    val result = chooser.showDialog(null, "Select")
    if (result != JFileChooser.APPROVE_OPTION) return null
    return chooser.selectedFile?.absolutePath
}
