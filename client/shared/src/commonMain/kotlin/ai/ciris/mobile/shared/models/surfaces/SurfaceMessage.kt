package ai.ciris.mobile.shared.models.surfaces

import kotlinx.serialization.Serializable

/**
 * **A server-emitted localizable string.**
 *
 * Every operator-facing sentence on the CIRISServer surfaces is an `{id, text}`
 * pair, never a bare sentence: the `id` is a stable localization key the client
 * resolves in the reader's own language, and `text` is the server's English
 * source — the designed fallback for an id the shipped bundle does not carry.
 *
 * The client MUST resolve [id] through the bundle first and fall back to [text]
 * only when the lookup misses. Rendering [text] unconditionally hardcodes
 * English into a 29-language client; rendering [id] unconditionally shows a raw
 * dotted key. `ai.ciris.mobile.shared.ui.components.surfaceText` is the one
 * resolver, so neither mistake can be made twice.
 *
 * Sources: `src/commons_surface.rs::m()` and `src/mesh_config_surface.rs::m()`.
 */
@Serializable
data class SurfaceMessage(
    /** The localization key — e.g. `commons_surface.standing.quiet`. */
    val id: String = "",
    /** The server's English source text. Fallback ONLY. */
    val text: String = "",
)
