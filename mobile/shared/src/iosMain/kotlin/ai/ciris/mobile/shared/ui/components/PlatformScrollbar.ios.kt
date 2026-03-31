package ai.ciris.mobile.shared.ui.components

import androidx.compose.foundation.ScrollState
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

/**
 * iOS implementation: No-op, iOS has native scroll indicators.
 */
@Composable
actual fun VerticalScrollbar(
    scrollState: ScrollState,
    modifier: Modifier
) {
    // No-op on iOS - system handles scroll indicators
}

/**
 * iOS implementation: No-op, iOS has native scroll indicators.
 */
@Composable
actual fun LazyColumnScrollbar(
    listState: LazyListState,
    modifier: Modifier
) {
    // No-op on iOS - system handles scroll indicators
}
