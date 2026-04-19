package ai.ciris.mobile.shared.platform

import androidx.compose.runtime.Composable

@Composable
actual fun FilePickerDialog(
    show: Boolean,
    fileExtensions: List<String>,
    onFileSelected: (String?) -> Unit,
    onDismiss: () -> Unit
) {
    // TODO: Implement using HTML file input element
    if (show) {
        onFileSelected(null)
        onDismiss()
    }
}
