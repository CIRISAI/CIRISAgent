package ai.ciris.mobile.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Proposed FFI surface from CIRISEdge 1.0 — the "Network" screen treats this as
 * source of truth. Maps to PyEdge pymethods that ought to exist on top of the
 * CIRISEdge#23–29 work.
 *
 * Mirrors the conceptual primitives of Reticulum Network Stack (RNS):
 *
 *  - **identity**: the local agent's Ed25519/ML-DSA federation key + display name
 *  - **transports** ("interfaces" in RNS terminology): TCP, UDP, RNode (LoRa),
 *    AutoInterface, I2P, KISS, Serial, Pipe, Local (FFI cohabitation), HTTPS
 *    (federation registry). Each has a `kind`, `status`, runtime config blob,
 *    and rolling stats.
 *  - **peers** ("destinations" in RNS terminology): every federation identity
 *    this stack has seen announced or been told about manually. Carries a
 *    per-transport reachability list so the UI can render the
 *    `peer × transport` matrix.
 *  - **events**: an ordered ring-buffer of network events the operator should
 *    be able to inspect: announce received, path discovered, link established,
 *    link dropped, transport up/down, key rotation, signature failure.
 *  - **config**: the canonical `reticulum.conf`-equivalent — what Edge will
 *    persist on disk. UI can view + diff + propose changes, but Edge owns the
 *    write.
 *
 * **HOLD POINT for Edge 1.0 ask.** The doc comment on each field is the
 * implementation prompt for the corresponding pymethod. If you see a comment
 * that says "Gap:" the FFI surface does not exist yet and the screen will
 * render a placeholder until it does.
 */
@Serializable
data class NetworkSnapshot(
    /** The local agent's federation identity (PyEdge.signer_key_id() exists in v0.9.1). */
    val localIdentity: LocalIdentity,
    /** Configured + runtime transports. Gap: needs `edge.transports()` pymethod (CIRISEdge#25). */
    val transports: List<NetworkTransport>,
    /** Every peer this stack has heard from. Gap: needs `edge.peers()` (CIRISEdge#26). */
    val peers: List<NetworkPeer>,
    /**
     * Path-table entries — every destination Edge knows how to reach + via which
     * interface + hop count + expiry. RNS-native and distinct from `peers`: a
     * peer is a federation identity; a path is a routing decision. Gap: needs
     * `edge.path_table()` (CIRISEdge#31 — to file).
     */
    val paths: List<NetworkPath>,
    /**
     * Active links — established cryptographic sessions to other peers. Carries
     * ephemeral X25519 keys, MTU/MDU, age, optional signal quality. Distinct
     * from peers: a peer may be reachable but have no active link.
     * Gap: needs `edge.link_table()` (CIRISEdge#30 — to file).
     */
    val links: List<NetworkLink>,
    /** Blackholed identities + reason + until. Gap: needs `edge.blackhole_list()` (CIRISEdge#31). */
    val blackholeList: List<BlackholeEntry>,
    /** Recent network events. Gap: needs `edge.recent_events(limit)` (CIRISEdge#28). */
    val recentEvents: List<NetworkEvent>,
    /** Aggregate counters for the Topology + Events tabs header strip. */
    val summary: NetworkSummary,
    /**
     * Generated-at timestamp, ISO-8601 UTC. UI uses this for staleness display
     * ("snapshot from 3s ago"). Returned by the snapshot endpoint, not stored on
     * Edge side.
     */
    @SerialName("generated_at")
    val generatedAt: String,
)

@Serializable
data class LocalIdentity(
    /** The federation key_id — full 64-hex string from `Ed25519::pubkey`. */
    @SerialName("key_id")
    val keyId: String,
    /** Short form for display (first 8 + last 4 hex with ellipsis), e.g. `ab12cd34…ef90`. */
    @SerialName("key_id_short")
    val keyIdShort: String,
    /** Optional operator-set nickname. Gap: needs `edge.local_display_name()` + setter. */
    @SerialName("display_name")
    val displayName: String?,
    /** Edge crate version, e.g. `0.9.1`. From PyEdge.crate_version() — exists. */
    @SerialName("edge_version")
    val edgeVersion: String,
    /** Hardware-backed signing status. Surfaces from CIRISVerify already. */
    @SerialName("hardware_backed")
    val hardwareBacked: Boolean,
)

@Serializable
data class NetworkTransport(
    /** Stable id chosen by Edge. UI never edits this. */
    val id: String,
    /** Human-readable label, operator-editable. */
    val name: String,
    /** Discriminator for content-aware rendering. */
    val kind: TransportKind,
    /** Runtime state from Edge. */
    val status: TransportStatus,
    /**
     * Free-form configuration blob — the YAML/TOML/JSON fragment that, if
     * written to `reticulum.conf`, reproduces this transport. UI renders as a
     * code block in the expanded transport card. Edge enforces schema.
     */
    @SerialName("config")
    val configBlob: String,
    /** Rolling per-transport stats. Gap: per-transport bytes counters (CIRISEdge#28). */
    val stats: TransportStats,
    /**
     * Number of peers reachable via this transport at the most recent path
     * discovery. Derived; Edge surfaces it for UI convenience.
     */
    @SerialName("peer_count")
    val peerCount: Int,
)

@Serializable
enum class TransportKind {
    /** HTTPS over TLS, mutual auth via federation key (CIRISEdge#23). */
    @SerialName("https") HTTPS,
    /** TCP via Leviculum (CIRISEdge#24). */
    @SerialName("tcp") TCP,
    /** UDP via Leviculum (CIRISEdge#24). */
    @SerialName("udp") UDP,
    /** Reticulum AutoInterface — auto-discovery on local network (CIRISEdge#24). */
    @SerialName("auto") AUTO,
    /** LoRa via RNode hardware (CIRISEdge#24). */
    @SerialName("rnode") RNODE,
    /** I2P tunneling (CIRISEdge#24). */
    @SerialName("i2p") I2P,
    /** KISS framing — packet radio (CIRISEdge#24). */
    @SerialName("kiss") KISS,
    /** Serial line (CIRISEdge#24). */
    @SerialName("serial") SERIAL,
    /** Pipe-based stdin/stdout (CIRISEdge#24). */
    @SerialName("pipe") PIPE,
    /** In-process FFI ("Local") — cohabitation path (CIRISEdge#16). */
    @SerialName("local") LOCAL,
    /** Anything Edge knows about but the UI doesn't yet have a rendering for. */
    @SerialName("unknown") UNKNOWN,
}

@Serializable
enum class TransportStatus {
    @SerialName("up") UP,
    @SerialName("down") DOWN,
    @SerialName("degraded") DEGRADED,
    @SerialName("starting") STARTING,
    @SerialName("disabled") DISABLED,
}

@Serializable
data class TransportStats(
    @SerialName("bytes_in") val bytesIn: Long,
    @SerialName("bytes_out") val bytesOut: Long,
    @SerialName("packets_in") val packetsIn: Long,
    @SerialName("packets_out") val packetsOut: Long,
    @SerialName("errors") val errors: Long,
    /** ISO-8601 UTC. Null when never seen. */
    @SerialName("last_announce_at") val lastAnnounceAt: String?,
    /** Edge-provided ring buffer of recent throughput. Gap: surface from #28. */
    @SerialName("throughput_history") val throughputHistory: List<ThroughputSample> = emptyList(),
)

@Serializable
data class ThroughputSample(
    /** ISO-8601 UTC at start of sample window. */
    @SerialName("at") val at: String,
    @SerialName("bytes_in") val bytesIn: Long,
    @SerialName("bytes_out") val bytesOut: Long,
)

@Serializable
data class NetworkPeer(
    /** Federation `key_id` — the canonical identity. */
    @SerialName("key_id")
    val keyId: String,
    /** Short form, mirror of LocalIdentity.keyIdShort. */
    @SerialName("key_id_short")
    val keyIdShort: String,
    /**
     * Operator-set display name. Null when no alias has been recorded —
     * common for newly-announced peers. Gap: setter via `edge.set_peer_alias()`.
     */
    @SerialName("display_name")
    val displayName: String?,
    /** Trust state set by operator. Gap: trust mutation via `edge.set_peer_trust()`. */
    val trust: PeerTrust,
    /**
     * Reachability per transport: which transport saw this peer most recently
     * and what's the link quality. This is the core data backing the
     * "reachability matrix" in the Peers tab — and it requires per-transport
     * announce tracking on the Edge side (gap on #29).
     */
    val reachability: List<PeerReachability>,
    /**
     * Optional operator note (Sideband-style alias annotation). Gap: setter.
     */
    val notes: String? = null,
    /**
     * How this peer entered the local directory: announce / manual / registry /
     * cohabitation. Drives the "discovered via" badge in the peer detail view.
     */
    @SerialName("discovered_via")
    val discoveredVia: PeerDiscoverySource,
    /** ISO-8601 UTC. Null when never seen — i.e. manually seeded but no announce. */
    @SerialName("first_seen_at") val firstSeenAt: String?,
    @SerialName("last_seen_at") val lastSeenAt: String?,
)

@Serializable
enum class PeerTrust {
    @SerialName("trusted") TRUSTED,
    @SerialName("untrusted") UNTRUSTED,
    @SerialName("blocked") BLOCKED,
    @SerialName("unknown") UNKNOWN,
}

@Serializable
enum class PeerDiscoverySource {
    @SerialName("announce") ANNOUNCE,
    @SerialName("manual") MANUAL,
    @SerialName("registry") REGISTRY,
    @SerialName("cohabitation") COHABITATION,
    @SerialName("unknown") UNKNOWN,
}

@Serializable
data class PeerReachability(
    @SerialName("transport_id") val transportId: String,
    @SerialName("transport_kind") val transportKind: TransportKind,
    /** Hop count along the discovered path. 0 = direct. */
    val hops: Int,
    /** ISO-8601 UTC, when this transport last witnessed this peer. */
    @SerialName("last_seen_at") val lastSeenAt: String?,
    /** Optional signal-quality scalar in dB. RNode/LoRa only. */
    @SerialName("snr_db") val snrDb: Double? = null,
    /** Optional RSSI in dBm. RNode/LoRa only. */
    @SerialName("rssi_dbm") val rssiDbm: Int? = null,
    /** Recent delivery success ratio in [0,1]. Tier 3 precursor. */
    @SerialName("delivery_ratio") val deliveryRatio: Double? = null,
)

@Serializable
data class NetworkPath(
    /** RNS destination_hash for the target (truncated SHA-256, 16 bytes hex). */
    @SerialName("destination_hash") val destinationHash: String,
    /** Federation key_id mapped from destination_hash, if known to Edge. */
    @SerialName("peer_key_id") val peerKeyId: String?,
    val hops: Int,
    @SerialName("via_transport_id") val viaTransportId: String,
    @SerialName("via_transport_kind") val viaTransportKind: TransportKind,
    /** Next-hop identity along the path (transport-layer). */
    @SerialName("next_hop") val nextHop: String?,
    /** ISO-8601 UTC. */
    @SerialName("last_seen_at") val lastSeenAt: String?,
    /** ISO-8601 UTC. When this entry will be evicted unless refreshed. */
    @SerialName("expires_at") val expiresAt: String?,
)

@Serializable
data class NetworkLink(
    /** RNS link_id (hex). */
    @SerialName("link_id") val linkId: String,
    /** Peer this link terminates at. */
    @SerialName("peer_key_id") val peerKeyId: String,
    val state: LinkState,
    /** Seconds since establishment. */
    @SerialName("age_seconds") val ageSeconds: Long,
    /** Link MTU (negotiated payload max). */
    val mtu: Int?,
    /** Link MDU (max data unit after framing). */
    val mdu: Int?,
    /** RSSI dBm if from a wireless transport. */
    @SerialName("rssi_dbm") val rssiDbm: Int? = null,
    /** SNR dB if from a wireless transport. */
    @SerialName("snr_db") val snrDb: Double? = null,
    /** Establishment rate scalar from RNS. */
    @SerialName("establishment_rate") val establishmentRate: Double? = null,
    /** Which transport this link rides on. */
    @SerialName("transport_id") val transportId: String,
    @SerialName("transport_kind") val transportKind: TransportKind,
)

@Serializable
enum class LinkState {
    @SerialName("pending") PENDING,
    @SerialName("active") ACTIVE,
    @SerialName("closing") CLOSING,
    @SerialName("closed") CLOSED,
    @SerialName("stale") STALE,
}

@Serializable
data class BlackholeEntry(
    /** Identity hash or federation key_id. */
    @SerialName("identity_hash") val identityHash: String,
    /** Optional federation key_id when identity_hash maps to a known peer. */
    @SerialName("peer_key_id") val peerKeyId: String?,
    /** ISO-8601 UTC. Null = indefinite. */
    @SerialName("until") val until: String?,
    /** Operator-supplied reason. */
    val reason: String?,
    /** ISO-8601 UTC of when this entry was added. */
    @SerialName("added_at") val addedAt: String,
)

@Serializable
data class NetworkEvent(
    /** ISO-8601 UTC. */
    val at: String,
    val kind: NetworkEventKind,
    /** Free-form human description. Edge generates these. */
    val message: String,
    /** Optional peer involvement. */
    @SerialName("peer_key_id") val peerKeyId: String? = null,
    /** Optional transport involvement. */
    @SerialName("transport_id") val transportId: String? = null,
    /** Optional severity hint for UI coloring. */
    val severity: EventSeverity = EventSeverity.INFO,
)

@Serializable
enum class NetworkEventKind {
    @SerialName("announce_received") ANNOUNCE_RECEIVED,
    @SerialName("announce_sent") ANNOUNCE_SENT,
    @SerialName("path_discovered") PATH_DISCOVERED,
    @SerialName("path_lost") PATH_LOST,
    @SerialName("link_established") LINK_ESTABLISHED,
    @SerialName("link_dropped") LINK_DROPPED,
    @SerialName("transport_up") TRANSPORT_UP,
    @SerialName("transport_down") TRANSPORT_DOWN,
    @SerialName("key_rotated") KEY_ROTATED,
    @SerialName("signature_failure") SIGNATURE_FAILURE,
    @SerialName("policy_block") POLICY_BLOCK,
    @SerialName("unknown") UNKNOWN,
}

@Serializable
enum class EventSeverity {
    @SerialName("info") INFO,
    @SerialName("warning") WARNING,
    @SerialName("error") ERROR,
}

@Serializable
data class NetworkSummary(
    @SerialName("transport_count") val transportCount: Int,
    @SerialName("transports_up") val transportsUp: Int,
    @SerialName("peer_count") val peerCount: Int,
    @SerialName("peers_reachable_now") val peersReachableNow: Int,
    @SerialName("trusted_peer_count") val trustedPeerCount: Int,
    @SerialName("active_link_count") val activeLinkCount: Int,
    @SerialName("path_count") val pathCount: Int,
    @SerialName("blackhole_count") val blackholeCount: Int,
    @SerialName("recent_event_count") val recentEventCount: Int,
)

/**
 * Catalog of every gap in the proposed FFI vs what PyEdge surfaces today
 * (Edge v0.9.1). Used by the screen to render an "FFI Coverage" footer chip on
 * each tab so the operator knows what's live vs stubbed, and by us as a
 * traceable list of asks against the CIRISEdge#23–29 epic.
 */
data class FfiGap(
    val gap: String,
    val tracksOn: String, // e.g. "CIRISEdge#26"
)

val NETWORK_FFI_GAPS: List<FfiGap> = listOf(
    // ── Identity (gap — no Edge issue today; suggest sibling issue under #22)
    FfiGap("edge.local_display_name() + setter — operator-set nickname for own identity", "CIRISEdge#22 sibling"),
    FfiGap("edge.export_qr_payload() — own identity + a freshly-signed announce (Briar pattern)", "CIRISEdge#26"),
    FfiGap("edge.import_qr_payload(blob) — Briar-style trust-on-first-handshake", "CIRISEdge#26"),

    // ── Transports (#25 + #24)
    FfiGap("edge.transports() → list of NetworkTransport with stats + config_blob", "CIRISEdge#25"),
    FfiGap("edge.add_transport(kind, config_blob) / remove_transport(id) — runtime mutation", "CIRISEdge#25"),
    FfiGap("edge.transport_health(id) — focused health probe (TLS state, last error, etc.)", "CIRISEdge#28"),
    FfiGap("edge.transport_set_mode(id, mode) — full/gateway/access_point/roaming/boundary", "CIRISEdge#25"),
    FfiGap("Expand #24 to cover KISSInterface / AX25KISSInterface / SerialInterface / PipeInterface", "CIRISEdge#24"),

    // ── Peers (#26)
    FfiGap("edge.peers() → list of NetworkPeer with reachability per transport", "CIRISEdge#26"),
    FfiGap("edge.peer_probe(key_id) — rnprobe equivalent: trigger path request + measure RTT", "CIRISEdge#26"),
    FfiGap("edge.peer_announce(destination_hash) — manual announce trigger", "CIRISEdge#26"),
    FfiGap("edge.add_peer(key_id, hint?) for manual seed + announce solicitation", "CIRISEdge#26"),
    FfiGap("edge.remove_peer(key_id) for forget", "CIRISEdge#26"),
    FfiGap("edge.set_peer_alias(key_id, alias) / set_peer_trust(key_id, trust) / set_peer_notes()", "CIRISEdge#26"),

    // ── Links (gap — no Edge issue today; suggest CIRISEdge#30)
    FfiGap("edge.link_list() → active links with mtu/age/state/rssi/snr", "CIRISEdge#30 (to file)"),
    FfiGap("edge.link_open(destination_hash) / link_teardown(link_id) / link_request()", "CIRISEdge#30 (to file)"),

    // ── Paths + blackhole (gap — suggest CIRISEdge#31)
    FfiGap("edge.path_table(max_hops?) → path-table entries with destination_hash, hops, via, expires", "CIRISEdge#31 (to file)"),
    FfiGap("edge.path_request(dest) / path_drop(dest) / path_drop_via(transport)", "CIRISEdge#31 (to file)"),
    FfiGap("edge.blackhole_list() / blackhole_add(id, until?, reason?) / blackhole_remove(id)", "CIRISEdge#31 (to file)"),

    // ── Observability (#28)
    FfiGap("edge.recent_events(limit) → ordered ring buffer of NetworkEvent", "CIRISEdge#28"),
    FfiGap("edge.recent_errors(limit) → typed error events so UI doesn't tail logs", "CIRISEdge#28"),
    FfiGap("edge.delivery_ratio(peer, transport) precursor for Tier 3", "CIRISEdge#29"),

    // ── Event stream (gap — suggest CIRISEdge#32)
    FfiGap("edge.subscribe_announces() / subscribe_link_events() / subscribe_path_events() — async iterators normalize Reticulum's per-callback model", "CIRISEdge#32 (to file)"),

    // ── Config-as-code (#25 extension)
    FfiGap("edge.config_read() / edge.config_write(blob) — canonical config.cfg-equivalent round-trip", "CIRISEdge#25"),
    FfiGap("edge.config_diff(proposed) → drift between spec and runtime, K8s-style", "CIRISEdge#25"),
)
