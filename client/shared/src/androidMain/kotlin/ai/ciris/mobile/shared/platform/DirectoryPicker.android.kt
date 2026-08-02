package ai.ciris.mobile.shared.platform

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect

// TODO: wire the Storage Access Framework tree picker (ACTION_OPEN_DOCUMENT_TREE)
// for removable media. Until then the holder types the path; this is a no-op that
// simply resets the caller's `show` flag.
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
