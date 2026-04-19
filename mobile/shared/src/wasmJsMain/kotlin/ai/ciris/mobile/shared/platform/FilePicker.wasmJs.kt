package ai.ciris.mobile.shared.platform

import androidx.compose.runtime.Composable

@Composable
actual fun FilePickerDialog(
    show: Boolean,
    mimeTypes: List<String>,
    onFilePicked: (PickedFile) -> Unit,
    onDismiss: () -> Unit
) {
    // TODO: Implement using HTML file input element
    // For now, dismiss immediately as web file picking requires HTML input element integration
    if (show) {
        onDismiss()
    }
}
