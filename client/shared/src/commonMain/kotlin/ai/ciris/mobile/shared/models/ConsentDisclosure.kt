package ai.ciris.mobile.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * The consent surface the wizard RENDERS — `GET /v1/setup/consent-disclosure`,
 * which serves `ciris_server.consent_disclosure()` unedited.
 *
 * The export exists precisely so the client does not write its own version of
 * this copy: "a wizard that writes its own version of that paragraph drifts from
 * the substrate the moment either changes". So these models carry NO strings of
 * their own — every word arrives from the node.
 *
 * Each string comes with a stable [DisclosureString.id], a dot-notation key into
 * the 29-locale catalogue. Render with [DisclosureString.localized]: the locale
 * wins when it has the key, and the substrate's own wording is the fallback, so a
 * locale that has not caught up degrades to correct English rather than to a raw
 * key.
 */
@Serializable
data class ConsentDisclosure(
    @SerialName("primary_action")
    val primaryAction: DisclosureString,
    /**
     * NOT a consent choice — the floor for service. "A node that does not
     * announce gets no service access on the mesh and no agent services",
     * because the accord's kill switch is only meaningful against a node it can
     * reach. The screen states this as a requirement, not as an option.
     */
    @SerialName("announce_requirement")
    val announceRequirement: DisclosureString,
    val independent: DisclosureString,
    @SerialName("details_expandable")
    val detailsExpandable: Boolean = true,
    val grants: List<ConsentGrantDisclosure> = emptyList(),
    @SerialName("declining_analyze")
    val decliningAnalyze: DecliningDisclosure = DecliningDisclosure(),
    val location: LocationDisclosure,
    @SerialName("source_locale")
    val sourceLocale: String = "en",
) {
    /** The named grant, or null when this build does not publish it. */
    fun grant(id: String): ConsentGrantDisclosure? = grants.firstOrNull { it.id == id }
}

/** One piece of substrate-authored copy plus its localization key. */
@Serializable
data class DisclosureString(
    val id: String,
    val text: String,
)

/** One consent dimension the owner is being asked to grant. */
@Serializable
data class ConsentGrantDisclosure(
    val id: String,
    val title: DisclosureString,
    val permits: DisclosureString,
    val dimension: String,
    /**
     * Whether declining is a misconfiguration. Render an optional grant as a
     * real toggle — the substrate is explicit that marking it required
     * "misrepresents a legitimate choice as a misconfiguration".
     */
    val required: Boolean = false,
    val covers: List<String>? = null,
    val scope: String? = null,
    val parameter: String? = null,
)

/** Whether a grant may be declined, and what declining actually costs. */
@Serializable
data class DecliningDisclosure(
    val allowed: Boolean = false,
    val summary: DisclosureString? = null,
    val costs: List<DisclosureString> = emptyList(),
)

/** The location envelope field — purpose first, then the bound. */
@Serializable
data class LocationDisclosure(
    val title: DisclosureString,
    /**
     * What location is FOR. Rendered BEFORE [permits]: "presented first as a
     * restriction mechanism it reads as a pure cost, and an operator declines
     * it."
     */
    val purpose: DisclosureString,
    val permits: DisclosureString,
    val kind: String,
    val carrier: String,
    @SerialName("cell_format")
    val cellFormat: String,
    /** The substrate's own coarseness bound. Read it; never restate it. */
    @SerialName("max_resolution")
    val maxResolution: Int,
    val required: Boolean = false,
    val declining: DecliningDisclosure = DecliningDisclosure(),
)
