package ai.ciris.mobile.shared.platform.util

import kotlin.io.encoding.Base64
import kotlin.io.encoding.ExperimentalEncodingApi
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Cross-fidelity tests for the Kotlin NodeCode codec.
 *
 * The KNOWN VECTORS here are the EXACT `CIRIS-V1-...` strings the agent's
 * authoritative Python codec (`node_code_codec.py`) and the Rust port
 * (`CIRISServer/src/nodecode.rs::agent_cross_fidelity`) produce for the same
 * fixed inputs. Byte-equality proves this port is a drop-in for the cross-app
 * wire contract: a code shared from agent / node decodes — byte-identically —
 * here, and vice versa. If any of these assertions ever fails, the port has
 * diverged and the founder bootstrap (NodeCode → connect → pin → claim) breaks.
 */
@OptIn(ExperimentalEncodingApi::class)
class NodeCodeCodecTest {

    // ─── Known vectors lifted verbatim from src/nodecode.rs ──────────────────

    /** key_id "ciris-server", pubkey = bytes 0x01..=0x20, both hints set. */
    private val AGENT_DASHED_WITH_HINTS =
        "CIRIS-V1-AFJW-7PUM-PAMO-IHJL-XNGO-ZUBP-DA2P-CRZD-SBEK-5UVO-OGA3-YAQR-SZYS-OAIC-AMCA-KBQH-BAEQ-UCYM-BUHA-6EAR-CIJR-IFIW-C4MB-SGQ3-DQOR-4HZA-BRRW-S4TJ-OMWX-GZLS-OZSX-EGDI-OR2H-A4Z2-F4XW-433E-MUXG-K6DB-NVYG-YZJO-N5ZG-ODCG-N52W-4ZDF-OIQE-433E-MUVZ-A"

    private val AGENT_QR_WITH_HINTS =
        "CIRIS-V1-AFJW7PUMPAMOIHJLXNGOZUBPDA2PCRZDSBEK5UVOOGA3YAQRSZYSOAICAMCAKBQHBAEQUCYMBUHA6EARCIJRIFIWC4MBSGQ3DQOR4HZABRRWS4TJOMWXGZLSOZSXEGDIOR2HA4Z2F4XW433EMUXGK6DBNVYGYZJON5ZGODCGN52W4ZDFOIQE433EMUVZA"

    /** key_id "node-a", pubkey = 32 bytes of 0x07, no hints. */
    private val AGENT_DASHED_NO_HINTS =
        "CIRIS-V1-AFTF-OD7Q-LIQH-IBBQ-QTKK-ZKKC-SPXQ-M5JQ-3XUU-75HJ-FOGY-IWJF-H23X-SBYH-A4DQ-OBYH-A4DQ-OBYH-A4DQ-OBYH-A4DQ-OBYH-A4DQ-OBYH-A4DQ-OBYH-AZXG-6ZDF-FVQQ-AAAI-QM"

    private fun pk0x01to0x20(): String = Base64.encode(ByteArray(32) { (it + 1).toByte() })
    private fun pk0x07(): String = Base64.encode(ByteArray(32) { 7 })

    private fun sampleWithHints() = DecodedNodeCode(
        keyId = "ciris-server",
        pubkeyEd25519Base64 = pk0x01to0x20(),
        transportHint = "https://node.example.org",
        aliasHint = "Founder Node",
    )

    private fun sampleNoHints() = DecodedNodeCode(
        keyId = "node-a",
        pubkeyEd25519Base64 = pk0x07(),
        transportHint = null,
        aliasHint = null,
    )

    // ─── Byte-for-byte encode equality with the agent / Rust ─────────────────

    @Test
    fun encode_matches_agent_byte_for_byte_with_hints() {
        assertEquals(AGENT_DASHED_WITH_HINTS, NodeCodeCodec.encode(sampleWithHints()))
        assertEquals(AGENT_QR_WITH_HINTS, NodeCodeCodec.encodeQr(sampleWithHints()))
    }

    @Test
    fun encode_matches_agent_byte_for_byte_no_hints() {
        assertEquals(AGENT_DASHED_NO_HINTS, NodeCodeCodec.encode(sampleNoHints()))
    }

    // ─── Decode of an agent-produced string recovers the identity ────────────

    @Test
    fun decode_of_agent_string_recovers_identity() {
        val nc = NodeCodeCodec.decode(AGENT_DASHED_WITH_HINTS)
        assertEquals("ciris-server", nc.keyId)
        assertEquals(pk0x01to0x20(), nc.pubkeyEd25519Base64)
        assertEquals("https://node.example.org", nc.transportHint)
        assertEquals("Founder Node", nc.aliasHint)
        // The agent's QR form decodes to the same identity.
        assertEquals(nc, NodeCodeCodec.decode(AGENT_QR_WITH_HINTS))
    }

    @Test
    fun decode_agent_no_hints_recovers_identity() {
        val nc = NodeCodeCodec.decode(AGENT_DASHED_NO_HINTS)
        assertEquals("node-a", nc.keyId)
        assertEquals(pk0x07(), nc.pubkeyEd25519Base64)
        assertNull(nc.transportHint)
        assertNull(nc.aliasHint)
    }

    // ─── Round-trips ─────────────────────────────────────────────────────────

    @Test
    fun round_trip_dashed() {
        val nc = sampleWithHints()
        val s = NodeCodeCodec.encode(nc)
        assertTrue(s.startsWith("CIRIS-V1-"))
        assertEquals(nc, NodeCodeCodec.decode(s))
    }

    @Test
    fun round_trip_qr_no_dashes() {
        val nc = sampleWithHints()
        val s = NodeCodeCodec.encodeQr(nc)
        assertTrue(!s.removePrefix("CIRIS-V1-").contains('-'))
        assertEquals(nc, NodeCodeCodec.decode(s))
    }

    // ─── Tolerances ──────────────────────────────────────────────────────────

    @Test
    fun dash_and_case_tolerance() {
        val nc = sampleWithHints()
        val s = NodeCodeCodec.encode(nc)
        val mangled = "  " + s.lowercase().replace("-", "") + "  \n"
        assertEquals(nc, NodeCodeCodec.decode(mangled))
        val spaced = s.replace("-", " - ")
        assertEquals(nc, NodeCodeCodec.decode(spaced))
    }

    // ─── Rejections ──────────────────────────────────────────────────────────

    @Test
    fun crc_rejection() {
        val s = NodeCodeCodec.encodeQr(sampleWithHints())
        val chars = s.toCharArray()
        val i = "CIRIS-V1-".length + 1
        chars[i] = if (chars[i] == 'A') 'B' else 'A'
        val corrupted = chars.concatToString()
        assertFailsWith<NodeCodeException> { NodeCodeCodec.decode(corrupted) }
    }

    @Test
    fun version_rejection_textual() {
        val s = NodeCodeCodec.encode(sampleWithHints())
        val v2 = s.replaceFirst("CIRIS-V1-", "CIRIS-V2-")
        assertFailsWith<NodeCodeException.InvalidVersion> { NodeCodeCodec.decode(v2) }
    }

    @Test
    fun bad_prefix_rejected() {
        assertFailsWith<NodeCodeException.Malformed> { NodeCodeCodec.decode("NOTACODE-ABCD") }
    }

    @Test
    fun bad_pubkey_size_rejected_on_encode() {
        val nc = DecodedNodeCode(
            keyId = "x",
            pubkeyEd25519Base64 = Base64.encode(ByteArray(16)),
            transportHint = null,
            aliasHint = null,
        )
        assertFailsWith<NodeCodeException.Malformed> { NodeCodeCodec.encode(nc) }
    }
}
