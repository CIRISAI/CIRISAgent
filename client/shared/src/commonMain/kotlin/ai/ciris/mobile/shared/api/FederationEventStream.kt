package ai.ciris.mobile.shared.api

import ai.ciris.mobile.shared.models.federation.FederationChannel
import ai.ciris.mobile.shared.models.federation.FederationEventEnvelope
import io.ktor.client.HttpClient
import io.ktor.client.plugins.HttpTimeout
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow

/**
 * SSE client wrapper for the federation event surface
 * (``GET /v1/federation/events/{channel}``).
 *
 * DISABLED: the agent-side SSE route + bridge were deleted in the 2.9.7
 * DRY purge — Edge's ``subscribe_*`` PyO3 surface owns the capability,
 * and the local ciris-server node (:4243) does not expose an SSE events
 * route yet. TODO(CIRISServer ask: expose GET /v1/federation/events/{channel}
 * on the node) — when it lands, reimplement frame parsing against the
 * node's SSE contract (the old parser encoded the deleted Python
 * bridge's frame vocabulary: ``federation_event`` / ``resume-notice`` /
 * ``connected`` / ``error`` / ``stream-closed`` + 30s heartbeats — do
 * NOT assume the node replicates it).
 *
 * [subscribe] returns a cold [Flow] that throws
 * [FederationEventStreamException] on collection; the stream ViewModels
 * already surface that as their ERROR connection state.
 */
class FederationEventStream(
    @Suppress("unused") private val httpClient: HttpClient,
    @Suppress("unused") private val baseUrl: String,
    @Suppress("unused") private val getToken: suspend () -> String?,
) {
    /**
     * Convenience constructor that sources auth from a
     * [CIRISApiClient]. Kept so call-sites compile unchanged while the
     * surface is disabled.
     */
    constructor(
        api: CIRISApiClient,
    ) : this(
        httpClient = HttpClient {
            install(HttpTimeout) {
                requestTimeoutMillis = Long.MAX_VALUE
                socketTimeoutMillis = Long.MAX_VALUE
                connectTimeoutMillis = 10_000
            }
        },
        baseUrl = api.baseUrl,
        getToken = { api.getAccessToken() },
    )

    /**
     * Subscribe to one federation channel. DISABLED — see class KDoc.
     * Throws [FederationEventStreamException] on collection.
     */
    fun subscribe(
        channel: FederationChannel,
        @Suppress("unused") lastEventId: String? = null,
    ): Flow<FederationEventEnvelope> = flow {
        throw FederationEventStreamException(
            "GET /v1/federation/events/${channel.pathSegment} is not served yet: " +
                "agent SSE bridge deleted (2.9.7 DRY purge), node route pending (CIRISServer ask)"
        )
    }
}

/**
 * Thrown when the federation SSE stream encounters a terminal
 * condition. While the surface is disabled (see [FederationEventStream])
 * every subscription throws this immediately on collection.
 */
class FederationEventStreamException(
    message: String,
    cause: Throwable? = null,
) : RuntimeException(message, cause)
