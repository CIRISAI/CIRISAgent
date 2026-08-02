package ai.ciris.mobile.shared.models.federation

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Wire models for the **portable software identity occurrence** — the owner's
 * deliberate, labeled bootstrap trade-off: a fresh *software* hybrid keyset that the
 * local TPM-bound primary authorizes as an occurrence of the same self, written to a
 * directory the owner picks (a USB key), so a second device is recognized as "him".
 *
 * NOT a "backup" — the owner was specific about the wording: it is a *portable
 * software identity occurrence*. A software keyset is inherently insecure; that is
 * the explicitly-accepted trade-off, surfaced in the UI danger sublabel + the
 * on-disk manifest.
 *
 * Mirrors `CIRISServer/src/auth/portable_occurrence.rs`:
 *   POST /v1/self/occurrence/portable → [PortableOccurrenceRequest] / [PortableOccurrenceResponse]
 *   POST /v1/self/associate           → [AssociateRequest] / [AssociateResponse]
 *
 * ARCHITECTURE: the app holds NO keys and writes NO key material. The client only
 * passes a directory PATH; the LOCAL node mints + writes the seeds to that path and
 * does the occurrence binding. Both endpoints are owner-gated + loopback-only.
 */

/** Body of `POST /v1/self/occurrence/portable`. The one user choice is [targetDir]. */
@Serializable
data class PortableOccurrenceRequest(
    /** The directory (a mounted USB folder) the fresh software seeds are written to. */
    @SerialName("target_dir")
    val targetDir: String,
    /** Optional display label flowed into the fedcode + the derived key alias. */
    val label: String? = null,
)

/** Response of `POST /v1/self/occurrence/portable`. NO private seed bytes are returned. */
@Serializable
data class PortableOccurrenceResponse(
    /** The new portable occurrence's federation `key_id` (now an active occurrence
     *  of the owner's self). */
    @SerialName("key_id")
    val keyId: String = "",
    /** The shareable `CIRIS-V2-…` usercode. */
    val fedcode: String = "",
    /** Where the node wrote the keyset (echo of the chosen directory). */
    @SerialName("target_dir")
    val targetDir: String = "",
    /** Always `portable_software`. */
    @SerialName("device_class")
    val deviceClass: String = "portable_software",
    /** The seed/marker/manifest filenames written into [targetDir] (names only). */
    @SerialName("files_written")
    val filesWritten: List<String> = emptyList(),
)

/**
 * Body of `POST /v1/self/associate`. Two shapes:
 *  - directory: [sourceDir] — install a portable software keyset from a folder.
 *  - yubikey: [yubikey] = true — associate a YubiKey-backed fed-ID (server-GATED in
 *    this pass; returns 501 until the on-device token read is wired).
 */
@Serializable
data class AssociateRequest(
    @SerialName("source_dir")
    val sourceDir: String? = null,
    val yubikey: Boolean = false,
)

/** Response of `POST /v1/self/associate`. */
@Serializable
data class AssociateResponse(
    /** The keystore alias the portable keyset was installed under. */
    val alias: String = "",
    /** The resolved occurrence `key_id` this device now signs as (null if the
     *  re-open could not report it). */
    @SerialName("associated_key_id")
    val associatedKeyId: String? = null,
    /** Always `portable_software`. */
    @SerialName("device_class")
    val deviceClass: String = "portable_software",
    /** The destination filenames installed. */
    @SerialName("files_installed")
    val filesInstalled: List<String> = emptyList(),
)
