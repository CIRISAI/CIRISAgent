package ai.ciris.mobile.shared.ui.components

import androidx.compose.runtime.Composable
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.surfaces.SurfaceMessage

/**
 * **The one resolver for a server-emitted `{id, text}` pair.**
 *
 * The server sends both halves on purpose: the `id` is a stable key that has
 * been translated into every shipped language, and `text` is the English source
 * kept as the designed fallback for an id this bundle does not carry yet.
 *
 * `LocalizationManager.getString` returns the KEY when a lookup misses, so a
 * result equal to the id is the miss signal — and the miss is exactly when the
 * server's own English is the right thing to show.
 *
 * Rendering `text` unconditionally would hardcode English into a 29-language
 * client; rendering the resolved id unconditionally would put a raw dotted key
 * on screen whenever a new server string lands ahead of its translation. This
 * function is the only place either mistake could be made, so it is the only
 * place it has to be prevented.
 */
@Composable
fun surfaceText(message: SurfaceMessage?): String {
    if (message == null) return ""
    if (message.id.isBlank()) return message.text
    val resolved = localizedString(message.id)
    return if (resolved == message.id) message.text else resolved
}

/**
 * The localized sentence for a refusal TOKEN, under a namespace whose ids are
 * derived from the substrate's own closed vocabulary
 * (`commons_surface.refusal.{token}` / `mesh_config.refusal.{token}`).
 *
 * The server derives those ids from persist's append-only token set rather than
 * writing a variant list down, so this client does the same: no arm list here
 * either. [fallback] is whatever sentence the response carried; when the token
 * is brand new and untranslated, that is what shows.
 */
@Composable
fun refusalText(namespace: String, token: String?, fallback: SurfaceMessage?): String {
    if (token.isNullOrBlank()) return surfaceText(fallback)
    val id = "$namespace.refusal.$token"
    val resolved = localizedString(id)
    if (resolved != id) return resolved
    val carried = surfaceText(fallback)
    return if (carried.isNotBlank()) carried else token
}
