package ai.ciris.mobile.shared.api

import ai.ciris.mobile.shared.models.federation.FederationChannel
import ai.ciris.mobile.shared.models.federation.FederationEventEnvelope
import ai.ciris.mobile.shared.platform.PlatformLogger
import io.ktor.client.HttpClient
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.request.header
import io.ktor.client.request.prepareGet
import io.ktor.client.statement.bodyAsChannel
import io.ktor.http.HttpHeaders
import io.ktor.http.isSuccess
import io.ktor.utils.io.ByteReadChannel
import io.ktor.utils.io.readUTF8Line
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.withTimeout
import kotlinx.datetime.Clock
import kotlinx.datetime.Instant
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/**
 * SSE client wrapper for the federation event surface
 * (``GET /v1/federation/events/{channel}``).
 *
 * One [subscribe] call returns a cold [Flow] that emits one envelope
 * per SSE ``federation_event`` frame. The flow surfaces errors
 * (connection drops, heartbeat timeouts, terminal ``error``
 * frames from the bridge) by throwing — callers are responsible for
 * reconnecting with the last-known ``event_id`` as ``Last-Event-ID``.
 *
 * The Edge subscription side does NOT replay history on reconnect;
 * the bridge instead emits a one-shot synthetic envelope with
 * ``event_type = "resume-notice"`` so the caller knows to resync any
 * cached snapshot via a non-streaming endpoint. We forward that
 * envelope as a normal Flow emission so the caller decides what to
 * do with it.
 *
 * Heartbeat: the bridge sends ``: heartbeat`` SSE comments every 30s
 * of idle. We treat the absence of any line for >60s as a stall and
 * throw — this catches mid-stream hangs that don't surface as TCP
 * resets.
 *
 * Backpressure on the bridge is drop-oldest (server-side concern);
 * this client does no per-flow buffering beyond what Ktor's channel
 * provides.
 */
class FederationEventStream(
    private val httpClient: HttpClient,
    private val baseUrl: String,
    private val getToken: suspend () -> String?,
) {
    /**
     * Convenience constructor that sources auth from a
     * [CIRISApiClient]. The HTTP client is owned by this stream
     * (created per-subscription so timeouts don't bleed across
     * unrelated callers).
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
     * Subscribe to one federation channel.
     *
     * @param channel which event channel to subscribe to.
     * @param lastEventId optional ``Last-Event-ID`` to send. The
     *        bridge does not replay history; if this is non-null the
     *        first emitted envelope will be a synthetic
     *        ``resume-notice`` so the caller knows to resync.
     */
    fun subscribe(
        channel: FederationChannel,
        lastEventId: String? = null,
    ): Flow<FederationEventEnvelope> = flow {
        val token = getToken()
        val url = "$baseUrl/v1/federation/events/${channel.pathSegment}"
        PlatformLogger.i(TAG, "subscribing channel=${channel.pathSegment}, lastEventId=$lastEventId")

        httpClient.prepareGet(url) {
            header(HttpHeaders.Accept, "text/event-stream")
            if (token != null) header(HttpHeaders.Authorization, "Bearer $token")
            if (lastEventId != null) header("Last-Event-ID", lastEventId)
        }.execute { response ->
            if (!response.status.isSuccess()) {
                throw FederationEventStreamException(
                    "SSE handshake failed: HTTP ${response.status.value} on ${channel.pathSegment}"
                )
            }

            val body: ByteReadChannel = response.bodyAsChannel()

            // SSE frame accumulators — reset on blank-line boundary.
            var currentEvent: String? = null
            var currentDataLines = mutableListOf<String>()
            var currentId: String? = null

            while (!body.isClosedForRead) {
                val line = readLineWithStallGuard(body, channel.pathSegment) ?: break

                when {
                    line.isEmpty() -> {
                        // Frame boundary — dispatch if we have data.
                        if (currentDataLines.isNotEmpty()) {
                            val envelope = parseFrame(
                                eventName = currentEvent,
                                dataJson = currentDataLines.joinToString("\n"),
                                channel = channel,
                                sseEventId = currentId,
                            )
                            if (envelope != null) emit(envelope)
                        }
                        currentEvent = null
                        currentDataLines = mutableListOf()
                        currentId = null
                    }
                    line.startsWith(":") -> {
                        // SSE comment — treated as heartbeat.
                        PlatformLogger.d(TAG, "heartbeat on ${channel.pathSegment}")
                    }
                    line.startsWith("event:") -> {
                        currentEvent = line.substring(6).trim()
                    }
                    line.startsWith("data:") -> {
                        currentDataLines.add(line.substring(5).trim())
                    }
                    line.startsWith("id:") -> {
                        currentId = line.substring(3).trim().takeIf { it.isNotEmpty() }
                    }
                    line.startsWith("retry:") -> {
                        // Not honored — caller controls reconnect cadence.
                    }
                }
            }
        }
    }

    /**
     * Read one line, throwing [FederationEventStreamException] if no
     * data arrives within [STALL_TIMEOUT_MS]. The bridge sends a
     * heartbeat every 30s, so a stall >60s means the connection has
     * silently dropped.
     */
    private suspend fun readLineWithStallGuard(
        channel: ByteReadChannel,
        channelName: String,
    ): String? {
        return try {
            withTimeout(STALL_TIMEOUT_MS) { channel.readUTF8Line() }
        } catch (e: Exception) {
            throw FederationEventStreamException(
                "SSE stall on $channelName after ${STALL_TIMEOUT_MS}ms: ${e.message}",
                e,
            )
        }
    }

    /**
     * Parse one SSE frame into an envelope. Returns ``null`` for
     * frames that are intentionally not surfaced as envelopes
     * (heartbeats, terminal stream-closed markers we already logged).
     *
     * Throws [FederationEventStreamException] for ``error`` frames
     * the bridge emits — those are terminal conditions the caller
     * needs to know about.
     */
    private fun parseFrame(
        eventName: String?,
        dataJson: String,
        channel: FederationChannel,
        sseEventId: String?,
    ): FederationEventEnvelope? {
        val data = try {
            jsonParser.parseToJsonElement(dataJson).jsonObject
        } catch (e: Exception) {
            PlatformLogger.w(TAG, "SSE parse error: ${e.message}, raw=${dataJson.take(120)}")
            return null
        }

        return when (eventName) {
            // The bridge wraps every Edge emission in this discriminator.
            "federation_event" -> try {
                jsonParser.decodeFromString(FederationEventEnvelope.serializer(), dataJson)
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "federation_event decode failed: ${e.message}")
                null
            }

            // Synthetic envelope: replay not supported, caller should
            // resync via a non-streaming endpoint.
            "resume-notice" -> FederationEventEnvelope(
                eventId = sseEventId ?: "resume-notice-${Clock.System.now().toEpochMilliseconds()}",
                channel = channel.pathSegment,
                timestamp = parseTimestamp(data) ?: Clock.System.now(),
                eventType = "resume-notice",
                payload = data,
            )

            // Initial handshake frame — surface as an envelope so the
            // caller can observe stream-readiness; payload carries the
            // server-side timestamp.
            "connected" -> FederationEventEnvelope(
                eventId = "connected-${Clock.System.now().toEpochMilliseconds()}",
                channel = channel.pathSegment,
                timestamp = parseTimestamp(data) ?: Clock.System.now(),
                eventType = "connected",
                payload = data,
            )

            // Terminal frames — surface as exceptions so the Flow
            // completes-with-error and the caller can decide whether
            // to retry with Last-Event-ID.
            "error" -> {
                val code = data["error"]?.jsonPrimitive?.contentOrNull ?: "EDGE_ERROR"
                val detail = data["detail"]?.jsonPrimitive?.contentOrNull ?: "(no detail)"
                throw FederationEventStreamException("SSE error frame: $code — $detail")
            }

            "stream-closed" -> {
                val reason = data["reason"]?.jsonPrimitive?.contentOrNull ?: "unknown"
                throw FederationEventStreamException("SSE stream-closed: $reason")
            }

            // Unknown discriminator — log and skip rather than crash
            // the consumer. New SSE event names should be added to
            // this when-branch before they ship.
            else -> {
                PlatformLogger.d(TAG, "unhandled SSE event=$eventName on ${channel.pathSegment}")
                null
            }
        }
    }

    private fun parseTimestamp(data: JsonObject): Instant? {
        val raw = data["timestamp"]?.jsonPrimitive?.contentOrNull ?: return null
        return try {
            Instant.parse(raw)
        } catch (_: Exception) {
            null
        }
    }

    companion object {
        private const val TAG = "FederationEventStream"

        /**
         * Hard ceiling on how long we'll wait for ANY line (event,
         * data, or ``: heartbeat`` comment) before treating the
         * connection as silently dead. Set to 2× the bridge's 30s
         * heartbeat cadence so a single missed heartbeat doesn't kill
         * an otherwise-healthy stream.
         */
        private const val STALL_TIMEOUT_MS = 60_000L

        private val jsonParser = Json {
            ignoreUnknownKeys = true
            isLenient = true
        }
    }
}

/**
 * Thrown when the federation SSE stream encounters a terminal
 * condition — connection failure, stall, terminal ``error`` frame
 * from the bridge. The Flow returned by [FederationEventStream.subscribe]
 * surfaces this so the caller can decide whether to retry with
 * ``Last-Event-ID``.
 */
class FederationEventStreamException(
    message: String,
    cause: Throwable? = null,
) : RuntimeException(message, cause)
