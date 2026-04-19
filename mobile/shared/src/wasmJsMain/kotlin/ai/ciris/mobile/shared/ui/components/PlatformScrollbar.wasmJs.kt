package ai.ciris.mobile.shared.ui.components

import androidx.compose.foundation.ScrollState
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

@Composable
actual fun VerticalScrollbar(
    scrollState: ScrollState,
    modifier: Modifier
) {
    // Browser handles scrollbar natively
}

@Composable
actual fun LazyColumnScrollbar(
    listState: LazyListState,
    modifier: Modifier
) {
    // Browser handles scrollbar natively
}
