package ai.ciris.mobile.shared.ui.components

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.size
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import ai.ciris.mobile.shared.api.CheckState
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.ui.theme.SemanticColors

/**
 * The state of one checkable fact about an LLM provider, as an icon.
 *
 * Sits next to the field it describes — the API key field, the model dropdown —
 * so the answer to "is this actually going to work?" is visible without pressing
 * anything. A user ran for days against a `401 Invalid API Key` while looking at
 * a settings screen that showed him a model list and no indication that nothing
 * on it would work.
 *
 * DEGRADED is deliberately its own state rather than folded into OK. A model
 * list that came from cached static data instead of the provider looks fine and
 * is not: selecting from it is how that same user ended up with `gpt-4o-mini`
 * configured against Groq.
 */
@Composable
fun LlmCheckIcon(
    state: CheckState,
    modifier: Modifier = Modifier,
    /** Shown to screen readers, and used as the icon's description. */
    message: String? = null,
) {
    val semantic = SemanticColors.Default
    when (state) {
        // Nothing asked yet — draw nothing rather than an ambiguous grey mark
        // that a user could read as either "fine" or "broken".
        CheckState.UNKNOWN -> Unit

        CheckState.CHECKING -> CircularProgressIndicator(
            modifier = modifier.size(16.dp),
            strokeWidth = 2.dp,
        )

        CheckState.OK -> Icon(
            imageVector = CIRISIcons.success,
            contentDescription = message ?: localizedString("mobile.llm_check_state_ok"),
            tint = semantic.success,
            modifier = modifier.size(18.dp),
        )

        CheckState.DEGRADED -> Icon(
            imageVector = CIRISIcons.warning,
            contentDescription = message ?: localizedString("mobile.llm_check_state_degraded"),
            tint = semantic.warning,
            modifier = modifier.size(18.dp),
        )

        CheckState.FAILED -> Icon(
            imageVector = CIRISIcons.error,
            contentDescription = message ?: localizedString("mobile.llm_check_state_failed"),
            tint = semantic.error,
            modifier = modifier.size(18.dp),
        )
    }
}

/**
 * The icon plus the provider's own words, for placing under a field.
 *
 * The message is always the provider's if we have it — "Invalid API Key",
 * "The model `default` does not exist" — because anything we write instead is
 * a paraphrase of something more precise.
 */
@Composable
fun LlmCheckRow(
    state: CheckState,
    message: String?,
    modifier: Modifier = Modifier,
) {
    if (state == CheckState.UNKNOWN || message.isNullOrBlank()) {
        LlmCheckIcon(state = state, modifier = modifier, message = message)
        return
    }
    val semantic = SemanticColors.Default
    Row(modifier = modifier, verticalAlignment = Alignment.CenterVertically) {
        LlmCheckIcon(state = state, message = message)
        Text(
            text = message,
            style = MaterialTheme.typography.bodySmall,
            color = when (state) {
                CheckState.FAILED -> semantic.error
                CheckState.DEGRADED -> semantic.warning
                CheckState.OK -> semantic.success
                else -> MaterialTheme.colorScheme.onSurfaceVariant
            },
            modifier = Modifier.size(width = 260.dp, height = 40.dp),
        )
    }
}
