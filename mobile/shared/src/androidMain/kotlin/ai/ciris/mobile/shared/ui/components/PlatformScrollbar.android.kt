package ai.ciris.mobile.shared.ui.components

import androidx.compose.foundation.ScrollState
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

/**
 * Android implementation: No-op, Android has native scroll indicators.
 */
@Composable
actual fun VerticalScrollbar(
    scrollState: ScrollState,
    modifier: Modifier
) {
    // No-op on Android - system handles scroll indicators
}

/**
 * Android implementation: No-op, Android has native scroll indicators.
 */
@Composable
actual fun LazyColumnScrollbar(
    listState: LazyListState,
    modifier: Modifier
) {
    // No-op on Android - system handles scroll indicators
}
