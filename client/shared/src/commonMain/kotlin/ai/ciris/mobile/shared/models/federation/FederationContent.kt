package ai.ciris.mobile.shared.models.federation

import kotlinx.datetime.Instant
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Body for ``POST /v1/federation/content/{content_id}``.
 *
 * Both fields are required by the backend. ``peer_key_id`` is the
 * peer to ask for the content — there is no global content directory,
 * so the caller must already know a candidate holder. ``timeout_ms``
 * is per-fetch in the range ``[1, 300_000]`` ms (1ms..5min); the
 * backend defaults to 30_000 if the field is missing, but we surface
 * an explicit Kotlin default so callers don't trip on the lower
 * boundary.
 *
 * Backend source of truth: ``FederationContentFetchRequest``.
 */
@Serializable
data class FederationContentRequest(
    @SerialName("peer_key_id")
    val peerKeyId: String,
    @SerialName("timeout_ms")
    val timeoutMs: Int = 5000,
)

/**
 * Response body for ``POST /v1/federation/content/{content_id}`` —
 * the success branch only (404 ``content_miss`` and 503 surface as
 * errors via [ai.ciris.mobile.shared.api.CIRISApiClient]'s error
 * handling).
 *
 * ``payload_base64`` carries the raw bytes from Edge's
 * ``fetch_content`` (kind=="bytes" branch). The SHA-256 invariant
 * ``sha256(decode(payload_base64)) == content_id`` is enforced
 * Rust-side by Edge before the bytes cross the FFI boundary; the
 * mobile client does NOT need to re-check it.
 *
 * ``content_type`` is reserved for forward compatibility — today
 * Edge's ``fetch_content`` does not return a MIME type so this is
 * always ``null``.
 *
 * Backend source of truth: ``FederationContentResponse``.
 */
@Serializable
data class FederationContentResponse(
    @SerialName("content_id")
    val contentId: String,
    @SerialName("content_type")
    val contentType: String? = null,
    @SerialName("payload_base64")
    val payloadBase64: String,
    @SerialName("size_bytes")
    val sizeBytes: Long,
    @SerialName("fetched_at")
    val fetchedAt: Instant,
)
