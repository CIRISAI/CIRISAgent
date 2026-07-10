package ai.ciris.mobile.shared.platform

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect

// TODO: wire UIDocumentPickerViewController (folder mode) for external storage.
// Until then the holder types the path; this is a no-op that resets `show`.
@Composable
actual fun DirectoryPickerDialog(
    show: Boolean,
    onDirectoryPicked: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    LaunchedEffect(show) {
        if (show) onDismiss()
    }
}
