package ai.ciris.mobile.shared.models.federation

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Wire models for **self-occurrence enrollment** — the "manage my self + log in as
 * myself on another device" surface (CIRISServer#76, CEG §5.6.8.8 / §11.7).
 *
 * A "self" is a roster of occurrence rows over ONE root identity (fed-ID) key.
 * Any ACTIVE occurrence stands in for the self, so adding a second device makes
 * the founder's fed-ID survive the loss of the first device (OR-of-N redundancy a
 * single hardware-sealed key cannot give you).
 *
 * Mirrors `CIRISServer/src/auth/occurrence.rs`:
 *   GET  /v1/self/occurrences?identity_key_id=… → [SelfOccurrencesResponse]
 *   POST /v1/self/occurrence                     → [AddOccurrenceRequest] / [AddOccurrenceResponse]
 *   POST /v1/self/occurrence/revoke              → [RevokeOccurrenceRequest] / [RevokeOccurrenceResponse]
 *
 * ARCHITECTURE: the app holds NO keys and performs NO crypto. The ADD / REVOKE are
 * federation-signed requests; the signing is performed by THIS device's local
 * ciris-server in its substrate (the user's resolved fed-ID signer), driven by a
 * plain loopback POST — the same posture as the consent / peering / claim-remote
 * cards. The app only DRIVES the node and surfaces the public result.
 */

/** One ACTIVE occurrence (device) of a self — a row in the device roster. */
@Serializable
data class SelfOccurrence(
    /** The occurrence's signing `key_id` (a `federation_keys.key_id`). */
    @SerialName("occurrence_key_id")
    val occurrenceKeyId: String,
    /** Closed set: `phone | laptop | agent` (persist's `check_device_class`). */
    @SerialName("device_class")
    val deviceClass: String = "laptop",
    /** `true` when the occurrence registered content-encryption pubkeys (i.e. it is
     *  a Self-DEK recipient and can decrypt the self's at-rest content). */
    @SerialName("has_encryption_pubkeys")
    val hasEncryptionPubkeys: Boolean = false,
    /** Present when the occurrence carries hardware attestation (TPM / SE / StrongBox). */
    @SerialName("hardware_attestation")
    val hardwareAttestation: String? = null,
    /** RFC-3339 binding-asserted time. */
    @SerialName("asserted_at")
    val assertedAt: String? = null,
)

/** Response of `GET /v1/self/occurrences?identity_key_id=…` — the device roster. */
@Serializable
data class SelfOccurrencesResponse(
    @SerialName("identity_key_id")
    val identityKeyId: String = "",
    /** The currently-ACTIVE occurrences (admitted, not revoked) — the device list. */
    val occurrences: List<SelfOccurrence> = emptyList(),
)

/** The new device's content-encryption pubkeys (the wrap_algorithm:v2 recipient
 *  inputs). REQUIRED for the device to decrypt the self's at-rest content — an
 *  occurrence WITHOUT them is fail-secure EXCLUDED from the Self-DEK cascade. */
@Serializable
data class OccurrenceEncryptionPubkeys(
    @SerialName("x25519_base64")
    val x25519Base64: String,
    @SerialName("ml_kem_768_base64")
    val mlKem768Base64: String,
)

/** The occurrence to admit in [AddOccurrenceRequest]. */
@Serializable
data class AddOccurrenceBody(
    @SerialName("occurrence_key_id")
    val occurrenceKeyId: String,
    /** `phone | laptop | agent`. */
    @SerialName("device_class")
    val deviceClass: String,
    @SerialName("encryption_pubkeys")
    val encryptionPubkeys: OccurrenceEncryptionPubkeys? = null,
    @SerialName("hardware_attestation")
    val hardwareAttestation: String? = null,
    /** Optional reachability rows `[(transport_kind, destination)]`. */
    @SerialName("transport_destinations")
    val transportDestinations: List<List<String>>? = null,
)

/**
 * Body of `POST /v1/self/occurrence` (ADD). Enrolls [occurrence] under
 * [identityKeyId]. When the new device's signing key is not yet in the directory,
 * supply [occurrenceKeyRecord] to admit it via the fail-secure proof-of-possession
 * gate; when the key already exists this is ignored.
 */
@Serializable
data class AddOccurrenceRequest(
    @SerialName("identity_key_id")
    val identityKeyId: String,
    val occurrence: AddOccurrenceBody,
    @SerialName("occurrence_key_record")
    val occurrenceKeyRecord: SignedKeyRecord? = null,
)

/** Response of `POST /v1/self/occurrence` (ADD). */
@Serializable
data class AddOccurrenceResponse(
    @SerialName("identity_key_id")
    val identityKeyId: String = "",
    @SerialName("occurrence_key_id")
    val occurrenceKeyId: String = "",
    @SerialName("device_class")
    val deviceClass: String = "",
    /** `true` when this call admitted the device's key from the supplied record. */
    @SerialName("key_freshly_registered")
    val keyFreshlyRegistered: Boolean = false,
    /** How many `cohort_scope: self` at-rest DEKs were (re-)wrapped to this device. */
    @SerialName("self_dek_granted")
    val selfDekGranted: Int = 0,
    /** Occurrence key_ids fail-secure EXCLUDED from the cascade (no encryption pubkeys). */
    @SerialName("self_dek_excluded")
    val selfDekExcluded: List<String> = emptyList(),
    @SerialName("transport_destinations_registered")
    val transportDestinationsRegistered: Int = 0,
)

/** Body of `POST /v1/self/occurrence/revoke` (REVOKE). */
@Serializable
data class RevokeOccurrenceRequest(
    @SerialName("identity_key_id")
    val identityKeyId: String,
    @SerialName("occurrence_key_id")
    val occurrenceKeyId: String,
    /** Optional operator annotation (e.g. "laptop lost 2026-06-23"). */
    val reason: String? = null,
)

/** Response of `POST /v1/self/occurrence/revoke` (REVOKE). */
@Serializable
data class RevokeOccurrenceResponse(
    @SerialName("identity_key_id")
    val identityKeyId: String = "",
    @SerialName("occurrence_key_id")
    val occurrenceKeyId: String = "",
    /** The surviving key that authorized the revocation. */
    @SerialName("revoked_by")
    val revokedBy: String = "",
    /** RFC-3339 effective time (== now; effective immediately). */
    @SerialName("effective_at")
    val effectiveAt: String = "",
)
