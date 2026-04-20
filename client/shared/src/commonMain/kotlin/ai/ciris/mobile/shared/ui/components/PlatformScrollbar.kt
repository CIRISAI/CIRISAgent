package ai.ciris.mobile.shared.ui.components

import androidx.compose.foundation.ScrollState
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

/**
 * Platform-specific vertical scrollbar for ScrollState (Column with verticalScroll).
 * On desktop: Shows a visible scrollbar
 * On mobile: No-op (mobile has native scroll indicators)
 */
@Composable
expect fun VerticalScrollbar(
    scrollState: ScrollState,
    modifier: Modifier = Modifier
)

/**
 * Platform-specific vertical scrollbar for LazyListState (LazyColumn).
 * On desktop: Shows a visible scrollbar
 * On mobile: No-op (mobile has native scroll indicators)
 */
@Composable
expect fun LazyColumnScrollbar(
    listState: LazyListState,
    modifier: Modifier = Modifier
)
