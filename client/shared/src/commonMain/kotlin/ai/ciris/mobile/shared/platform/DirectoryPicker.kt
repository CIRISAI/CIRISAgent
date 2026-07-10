package ai.ciris.mobile.shared.platform

import androidx.compose.runtime.Composable

/**
 * Native **folder** picker — returns the selected directory's absolute PATH (not
 * its contents, unlike [FilePickerDialog]). Used to choose the mounted USB folder
 * that holds the accord holder's AEAD-wrapped ML-DSA-65 half.
 *
 * Render it (like [FilePickerDialog]) and flip [show] to `true` to open the native
 * chooser; it calls [onDirectoryPicked] with the absolute path on confirm, or
 * [onDismiss] on cancel. The caller resets [show] in both callbacks.
 *
 * - Desktop: `JFileChooser` in DIRECTORIES_ONLY mode (the ceremony path).
 * - Android/iOS/wasm: no-op for now (the text field stays the source of truth) —
 *   TODO wire the SAF tree picker / iOS document picker for removable media.
 */
@Composable
expect fun DirectoryPickerDialog(
    show: Boolean,
    onDirectoryPicked: (String) -> Unit,
    onDismiss: () -> Unit,
)
