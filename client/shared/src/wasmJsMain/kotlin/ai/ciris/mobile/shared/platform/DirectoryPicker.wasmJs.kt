package ai.ciris.mobile.shared.platform

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect

// Browsers have no concept of a server-side directory path; the holder types it.
// No-op that resets the caller's `show` flag.
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
