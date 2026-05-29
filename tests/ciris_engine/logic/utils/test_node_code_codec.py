"""Tests for the NodeCode binary codec.

Covers happy-path round-trip across the full input matrix (minimal,
full, boundary-length hints, Unicode hints, empty hints) plus the
rejection cases (bad version, bad checksum, bad base32, truncation,
length-prefix overflow, wrong prefix).

Includes random-fuzz round-trip property: encode -> decode == identity
for arbitrary byte-length hint strings.
"""

from __future__ import annotations

import base64
import secrets

import pytest

from ciris_engine.logic.utils.node_code_codec import (
    CIRIS_NODE_CODE_VERSION,
    ChecksumMismatchError,
    InvalidVersionError,
    MalformedNodeCodeError,
    NodeCodeError,
    decode_node_code,
    encode_node_code,
    encode_qr_payload,
)
from ciris_engine.schemas.runtime.node_code import NodeCode


def _random_pubkey_b64() -> str:
    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")


# --------------------------------------------------------------------------- #
# Round-trip happy paths
# --------------------------------------------------------------------------- #


class TestRoundTrip:
    def test_minimum_no_hints(self) -> None:
        pk = _random_pubkey_b64()
        nc = NodeCode(key_id="agent-abc123def456", pubkey_ed25519_base64=pk)
        code = encode_node_code(nc)
        assert code.startswith("CIRIS-V1-")
        decoded = decode_node_code(code)
        assert decoded.key_id == nc.key_id
        assert decoded.pubkey_ed25519_base64 == nc.pubkey_ed25519_base64
        assert decoded.transport_hint is None
        assert decoded.alias_hint is None

    def test_full_with_hints(self) -> None:
        pk = _random_pubkey_b64()
        nc = NodeCode(
            key_id="agent-fullexample",
            pubkey_ed25519_base64=pk,
            transport_hint="tcp://agents.ciris.ai:4242",
            alias_hint="datum",
        )
        decoded = decode_node_code(encode_node_code(nc))
        assert decoded.key_id == nc.key_id
        assert decoded.pubkey_ed25519_base64 == nc.pubkey_ed25519_base64
        assert decoded.transport_hint == nc.transport_hint
        assert decoded.alias_hint == nc.alias_hint

    def test_long_transport_hint_250_bytes(self) -> None:
        pk = _random_pubkey_b64()
        long_hint = "x" * 250
        nc = NodeCode(
            key_id="agent-x",
            pubkey_ed25519_base64=pk,
            transport_hint=long_hint,
        )
        decoded = decode_node_code(encode_node_code(nc))
        assert decoded.transport_hint == long_hint

    def test_long_alias_hint_250_bytes(self) -> None:
        pk = _random_pubkey_b64()
        long_alias = "a" * 250
        nc = NodeCode(
            key_id="agent-x",
            pubkey_ed25519_base64=pk,
            alias_hint=long_alias,
        )
        decoded = decode_node_code(encode_node_code(nc))
        assert decoded.alias_hint == long_alias

    def test_unicode_alias(self) -> None:
        pk = _random_pubkey_b64()
        # Mix of Amharic, Japanese, emoji — common non-ASCII paths.
        unicode_alias = "ዳተም 데이텀 ✨"
        nc = NodeCode(
            key_id="agent-x",
            pubkey_ed25519_base64=pk,
            alias_hint=unicode_alias,
        )
        decoded = decode_node_code(encode_node_code(nc))
        assert decoded.alias_hint == unicode_alias

    def test_unicode_transport(self) -> None:
        pk = _random_pubkey_b64()
        # Internationalized URL.
        unicode_transport = "tcp://例え.テスト:4242"
        nc = NodeCode(
            key_id="agent-x",
            pubkey_ed25519_base64=pk,
            transport_hint=unicode_transport,
        )
        decoded = decode_node_code(encode_node_code(nc))
        assert decoded.transport_hint == unicode_transport

    def test_empty_string_hints_decode_as_none(self) -> None:
        # Empty hints should round-trip equivalently to None — both
        # serialize to the zero-length byte and decode to None.
        pk = _random_pubkey_b64()
        nc = NodeCode(
            key_id="agent-x",
            pubkey_ed25519_base64=pk,
            transport_hint="",
            alias_hint="",
        )
        decoded = decode_node_code(encode_node_code(nc))
        assert decoded.transport_hint is None
        assert decoded.alias_hint is None

    def test_qr_form_round_trips(self) -> None:
        pk = _random_pubkey_b64()
        nc = NodeCode(
            key_id="agent-x",
            pubkey_ed25519_base64=pk,
            transport_hint="tcp://example.com:4242",
            alias_hint="datum",
        )
        qr = encode_qr_payload(nc)
        assert "-" not in qr[len("CIRIS-V1-") :]  # body has no dashes
        # Even decode the QR form (no separator dashes in the body).
        decoded = decode_node_code(qr)
        assert decoded.key_id == nc.key_id
        assert decoded.transport_hint == nc.transport_hint
        assert decoded.alias_hint == nc.alias_hint

    def test_mixed_case_input_decodes(self) -> None:
        pk = _random_pubkey_b64()
        nc = NodeCode(key_id="agent-x", pubkey_ed25519_base64=pk, alias_hint="datum")
        code = encode_node_code(nc).lower()
        # Decoder upper-cases input before parsing.
        decoded = decode_node_code(code)
        assert decoded.key_id == nc.key_id
        assert decoded.alias_hint == nc.alias_hint

    def test_whitespace_tolerance(self) -> None:
        pk = _random_pubkey_b64()
        nc = NodeCode(key_id="agent-x", pubkey_ed25519_base64=pk, alias_hint="datum")
        code = encode_node_code(nc)
        spaced = "  \n " + code.replace("-", " - ") + " \t"
        decoded = decode_node_code(spaced)
        assert decoded.key_id == nc.key_id


# --------------------------------------------------------------------------- #
# Rejection / error subclass routing
# --------------------------------------------------------------------------- #


class TestRejection:
    def _baseline(self) -> str:
        pk = _random_pubkey_b64()
        return encode_node_code(NodeCode(key_id="agent-x", pubkey_ed25519_base64=pk))

    def test_wrong_prefix_no_version(self) -> None:
        with pytest.raises(MalformedNodeCodeError):
            decode_node_code("CIRIS-ABCD-EFGH")

    def test_wrong_prefix_other_brand(self) -> None:
        with pytest.raises(MalformedNodeCodeError):
            decode_node_code("OTHER-V1-ABCD-EFGH")

    def test_wrong_version_v2(self) -> None:
        # Textual V2 prefix — caught before any binary parsing.
        with pytest.raises(InvalidVersionError):
            decode_node_code("CIRIS-V2-ABCD-EFGH-IJKL")

    def test_checksum_mismatch(self) -> None:
        code = self._baseline()
        # Flip one character near the end to break the CRC.
        # Pick a char in the body, not the prefix.
        body_start = len("CIRIS-V1-")
        chars = list(code)
        # Find a chunk-internal alphabetic char to flip safely.
        for i in range(body_start, len(chars)):
            if chars[i].isalpha():
                chars[i] = "Z" if chars[i] != "Z" else "A"
                break
        bad = "".join(chars)
        # Either a checksum mismatch, malformed (if the bit flip
        # corrupted a length field into truncation), or invalid version
        # (if the version byte got flipped). All three are valid
        # rejection paths; we just need it not to silently decode.
        with pytest.raises(NodeCodeError):
            decode_node_code(bad)

    def test_checksum_mismatch_targeted(self) -> None:
        # Deterministic checksum break: produce a payload manually with a
        # CRC that is guaranteed wrong, then verify ChecksumMismatchError.
        from ciris_engine.logic.utils.node_code_codec import _b32_no_pad_encode, _build_payload

        pk = _random_pubkey_b64()
        nc = NodeCode(key_id="agent-x", pubkey_ed25519_base64=pk)
        payload = _build_payload(nc)
        # Append a guaranteed-wrong CRC (0x0000) when the real one is non-zero.
        bad_full = payload + b"\x00\x00"
        body = _b32_no_pad_encode(bad_full)
        bad_code = "CIRIS-V1-" + body
        with pytest.raises(ChecksumMismatchError):
            decode_node_code(bad_code)

    def test_malformed_base32(self) -> None:
        # '!' is not in the RFC 4648 base32 alphabet.
        with pytest.raises(MalformedNodeCodeError):
            decode_node_code("CIRIS-V1-AB!!-CDEF")

    def test_truncated_payload(self) -> None:
        code = self._baseline()
        # Trim to the prefix + a handful of body chars — clearly under
        # the minimum payload size.
        with pytest.raises(MalformedNodeCodeError):
            decode_node_code("CIRIS-V1-AB")

    def test_over_long_transport_hint_at_encode(self) -> None:
        pk = _random_pubkey_b64()
        too_long = "x" * 256
        nc = NodeCode(key_id="agent-x", pubkey_ed25519_base64=pk, transport_hint=too_long)
        with pytest.raises(MalformedNodeCodeError):
            encode_node_code(nc)

    def test_over_long_alias_hint_at_encode(self) -> None:
        pk = _random_pubkey_b64()
        too_long = "y" * 256
        nc = NodeCode(key_id="agent-x", pubkey_ed25519_base64=pk, alias_hint=too_long)
        with pytest.raises(MalformedNodeCodeError):
            encode_node_code(nc)

    def test_pubkey_wrong_length(self) -> None:
        # 16-byte pubkey base64 — wrong size for Ed25519.
        short_pk = base64.b64encode(b"x" * 16).decode("ascii")
        nc = NodeCode(key_id="agent-x", pubkey_ed25519_base64=short_pk)
        with pytest.raises(MalformedNodeCodeError):
            encode_node_code(nc)

    def test_pubkey_invalid_base64(self) -> None:
        nc = NodeCode(key_id="agent-x", pubkey_ed25519_base64="!!!not-base64!!!")
        with pytest.raises(MalformedNodeCodeError):
            encode_node_code(nc)

    def test_truncated_length_prefix(self) -> None:
        # Construct a hand-crafted payload where the transport_hint_len
        # byte claims 200 bytes but the payload ends immediately.
        import hashlib

        from ciris_engine.logic.utils.node_code_codec import (
            _b32_no_pad_encode,
            _crc16_ccitt,
        )

        version = bytes([CIRIS_NODE_CODE_VERSION])
        key_id_str = b"agent-x"
        key_id_hash = hashlib.sha256(key_id_str).digest()
        pubkey_raw = secrets.token_bytes(32)
        key_id_field = bytes([len(key_id_str)]) + key_id_str
        # Claim transport hint is 200 bytes, but provide zero.
        transport_field = bytes([200])
        # Don't append alias either — payload truncates here.
        payload = version + key_id_hash + pubkey_raw + key_id_field + transport_field
        crc = _crc16_ccitt(payload)
        full = payload + bytes([(crc >> 8) & 0xFF, crc & 0xFF])
        bad_code = "CIRIS-V1-" + _b32_no_pad_encode(full)
        with pytest.raises(MalformedNodeCodeError):
            decode_node_code(bad_code)

    def test_decode_non_string_raises(self) -> None:
        with pytest.raises(MalformedNodeCodeError):
            decode_node_code(b"CIRIS-V1-ABCD")  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Fuzz: random-byte round-trip property over hint fields
# --------------------------------------------------------------------------- #


class TestFuzz:
    @pytest.mark.parametrize("trial", range(50))
    def test_round_trip_random_hints(self, trial: int) -> None:
        # Random key_id (5-32 ASCII chars), random pubkey, random-length
        # hints (0-200 bytes UTF-8). All printable ASCII — avoids the
        # length-byte ambiguity on multi-byte UTF-8 boundaries.
        rng = secrets.SystemRandom()
        key_id_len = rng.randint(5, 32)
        key_id = "".join(rng.choices("abcdefghijklmnopqrstuvwxyz0123456789-", k=key_id_len))

        pk = _random_pubkey_b64()

        def maybe_hint() -> str | None:
            roll = rng.random()
            if roll < 0.3:
                return None
            if roll < 0.4:
                return ""
            n = rng.randint(1, 200)
            return "".join(rng.choices("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 +-/:.", k=n))

        nc = NodeCode(
            key_id=key_id,
            pubkey_ed25519_base64=pk,
            transport_hint=maybe_hint(),
            alias_hint=maybe_hint(),
        )
        code = encode_node_code(nc)
        decoded = decode_node_code(code)
        assert decoded.key_id == nc.key_id
        assert decoded.pubkey_ed25519_base64 == nc.pubkey_ed25519_base64
        # Empty hints normalize to None on decode — equivalence check.
        expected_transport = nc.transport_hint if nc.transport_hint else None
        expected_alias = nc.alias_hint if nc.alias_hint else None
        assert decoded.transport_hint == expected_transport
        assert decoded.alias_hint == expected_alias

    @pytest.mark.parametrize("trial", range(20))
    def test_round_trip_random_unicode_hints(self, trial: int) -> None:
        rng = secrets.SystemRandom()
        pk = _random_pubkey_b64()
        # Pick from a few non-ASCII scripts but stay well below the
        # 255-byte cap. Each Amharic char is 3 UTF-8 bytes; cap at 80
        # chars => ~240 bytes max.
        scripts = ["ሰላም ", "안녕 ", "Здра ", "مرحبا ", "नमस्ते "]
        n = rng.randint(1, 30)
        unicode_hint = "".join(rng.choices(scripts, k=n))
        # Truncate to fit ≤200 raw bytes to stay safely under the cap.
        while len(unicode_hint.encode("utf-8")) > 200:
            unicode_hint = unicode_hint[:-1]

        nc = NodeCode(
            key_id="agent-fuzz",
            pubkey_ed25519_base64=pk,
            alias_hint=unicode_hint,
        )
        code = encode_node_code(nc)
        decoded = decode_node_code(code)
        expected = unicode_hint if unicode_hint else None
        assert decoded.alias_hint == expected
