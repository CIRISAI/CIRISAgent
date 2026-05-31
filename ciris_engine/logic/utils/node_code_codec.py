"""
NodeCode binary codec — encodes / decodes shareable peer-bootstrap codes.

Wire format (binary payload, encoded as RFC 4648 base32 without padding,
then grouped into 4-char chunks separated by dashes and prefixed with
``CIRIS-V1-``):

    offset  size  field
    ------  ----  -----
       0      1   version (currently 0x01)
       1     32   key_id_hash  = SHA-256(key_id_str_utf8)
      33     32   pubkey_ed25519 (raw 32 bytes)
      65      1   key_id_str_len (0-255)
      66      N   key_id_str (UTF-8)
     66+N     1   transport_hint_len (0-255)
   67+N      M   transport_hint (UTF-8)
  67+N+M     1   alias_hint_len (0-255)
  68+N+M     K   alias_hint (UTF-8)
       …      2   CRC-16-CCITT (over all preceding bytes)

Design notes:

* The ``key_id_hash`` field is a stable 32-byte fingerprint suitable for
  future binary-only Edge ANNOUNCE wire surfaces. The ``key_id_str``
  field carries the display form so round-trip preserves what the user
  saw. Spec gave the implementer a choice between "hash or raw bytes" —
  we picked hash + explicit string so both are available.
* All length-prefixed fields are 1 byte (max 255 UTF-8 bytes). The codec
  raises ``MalformedNodeCodeError`` if a field overflows.
* CRC-16-CCITT polynomial 0x1021, init 0xFFFF, no xor-out, big-endian.
* Base32 is RFC 4648 alphabet (A-Z + 2-7); we strip padding (``=``) on
  encode and re-pad on decode.
* The encoded form is case-insensitive; the decoder upper-cases input
  and tolerates dashes, whitespace, and the missing-dashes QR form.

Only stdlib + pydantic. No external CRC library.
"""

from __future__ import annotations

import base64
import hashlib
import re
from typing import Optional

from ciris_engine.schemas.runtime.node_code import NodeCode

# --------------------------------------------------------------------------- #
# Public exceptions
# --------------------------------------------------------------------------- #


class NodeCodeError(Exception):
    """Base error for NodeCode encode/decode failures."""


class InvalidVersionError(NodeCodeError):
    """The decoded payload's version byte is not a known NodeCode version."""


class ChecksumMismatchError(NodeCodeError):
    """The trailing CRC-16-CCITT did not match the recomputed checksum."""


class MalformedNodeCodeError(NodeCodeError):
    """The encoded string is structurally invalid (bad base32, truncated,
    over-long fields, wrong prefix, or otherwise undecodable before the
    checksum check can run)."""


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

CIRIS_NODE_CODE_VERSION = 0x01
"""Current NodeCode binary-format version."""

_PREFIX = "CIRIS-V1-"
_GROUP_SIZE = 4

# Per-field maximum (1-byte length field).
_MAX_HINT_BYTES = 255

# Ed25519 raw pubkey size.
_PUBKEY_RAW_LEN = 32

# SHA-256 digest size.
_KEY_ID_HASH_LEN = 32

# CRC-16-CCITT params.
_CRC_POLY = 0x1021
_CRC_INIT = 0xFFFF


# --------------------------------------------------------------------------- #
# CRC-16-CCITT (polynomial 0x1021, init 0xFFFF, no xor-out)
# --------------------------------------------------------------------------- #


def _crc16_ccitt(data: bytes) -> int:
    """Compute CRC-16-CCITT over ``data``.

    Polynomial 0x1021, initial value 0xFFFF, no final xor. Bytes are
    consumed MSB-first.
    """
    crc = _CRC_INIT
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ _CRC_POLY) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _encode_hint(value: Optional[str]) -> bytes:
    """Encode a hint string as ``len_byte + utf8_bytes``.

    None and empty string both serialize to ``b"\\x00"``. Raises
    ``MalformedNodeCodeError`` if the UTF-8 form exceeds 255 bytes.
    """
    if value is None or value == "":
        return b"\x00"
    raw = value.encode("utf-8")
    if len(raw) > _MAX_HINT_BYTES:
        raise MalformedNodeCodeError(
            f"Hint field exceeds {_MAX_HINT_BYTES}-byte limit ({len(raw)} bytes)"
        )
    return bytes([len(raw)]) + raw


def _read_length_prefixed(buf: bytes, offset: int) -> tuple[str, int]:
    """Read a 1-byte length + UTF-8 bytes from ``buf`` at ``offset``.

    Returns ``(value, new_offset)``. Empty fields decode to ``""``.
    Raises ``MalformedNodeCodeError`` on truncation or bad UTF-8.
    """
    if offset >= len(buf):
        raise MalformedNodeCodeError("Truncated NodeCode: missing length byte")
    length = buf[offset]
    offset += 1
    end = offset + length
    if end > len(buf):
        raise MalformedNodeCodeError(
            f"Truncated NodeCode: declared field length {length} exceeds remaining buffer"
        )
    try:
        value = buf[offset:end].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MalformedNodeCodeError(f"Field is not valid UTF-8: {exc}") from exc
    return value, end


def _build_payload(node_code: NodeCode) -> bytes:
    """Build the raw binary payload (without checksum) from a NodeCode.

    Raises ``MalformedNodeCodeError`` if any field is over-long, the
    pubkey is the wrong size, or pubkey base64 is malformed.
    """
    key_id_bytes = node_code.key_id.encode("utf-8")
    if len(key_id_bytes) > _MAX_HINT_BYTES:
        raise MalformedNodeCodeError(
            f"key_id exceeds {_MAX_HINT_BYTES}-byte limit ({len(key_id_bytes)} bytes)"
        )

    try:
        pubkey_raw = base64.b64decode(node_code.pubkey_ed25519_base64, validate=True)
    except Exception as exc:
        raise MalformedNodeCodeError(f"pubkey_ed25519_base64 is not valid base64: {exc}") from exc

    if len(pubkey_raw) != _PUBKEY_RAW_LEN:
        raise MalformedNodeCodeError(
            f"pubkey_ed25519 must be {_PUBKEY_RAW_LEN} raw bytes, got {len(pubkey_raw)}"
        )

    key_id_hash = hashlib.sha256(key_id_bytes).digest()
    assert len(key_id_hash) == _KEY_ID_HASH_LEN  # sha256 invariant

    parts: list[bytes] = [
        bytes([CIRIS_NODE_CODE_VERSION]),
        key_id_hash,
        pubkey_raw,
        bytes([len(key_id_bytes)]) + key_id_bytes,
        _encode_hint(node_code.transport_hint),
        _encode_hint(node_code.alias_hint),
    ]
    return b"".join(parts)


def _b32_no_pad_encode(data: bytes) -> str:
    """Base32 encode without padding (RFC 4648 alphabet)."""
    return base64.b32encode(data).decode("ascii").rstrip("=")


def _b32_no_pad_decode(text: str) -> bytes:
    """Base32 decode tolerating missing padding.

    Raises ``MalformedNodeCodeError`` on bad characters.
    """
    # Pad to multiple of 8.
    pad_len = (-len(text)) % 8
    padded = text + ("=" * pad_len)
    try:
        return base64.b32decode(padded, casefold=False)
    except Exception as exc:
        raise MalformedNodeCodeError(f"Invalid base32 payload: {exc}") from exc


def _group(text: str, size: int = _GROUP_SIZE, sep: str = "-") -> str:
    """Split ``text`` into ``size``-char groups joined by ``sep``."""
    if not text:
        return text
    chunks = [text[i : i + size] for i in range(0, len(text), size)]
    return sep.join(chunks)


# --------------------------------------------------------------------------- #
# Public encode / decode API
# --------------------------------------------------------------------------- #


def encode_node_code(node_code: NodeCode) -> str:
    """Encode a NodeCode as a ``CIRIS-V1-...`` dashed display string.

    Raises:
        MalformedNodeCodeError: if any field is over-length or pubkey
            is the wrong size / not valid base64.
    """
    payload = _build_payload(node_code)
    crc = _crc16_ccitt(payload)
    full = payload + bytes([(crc >> 8) & 0xFF, crc & 0xFF])
    body = _b32_no_pad_encode(full)
    return _PREFIX + _group(body)


def encode_qr_payload(node_code: NodeCode) -> str:
    """Encode a NodeCode as the QR-friendly (no-dashes) form.

    Same content as ``encode_node_code`` but with separator dashes
    stripped — the prefix ``CIRIS-V1-`` is still present.
    """
    payload = _build_payload(node_code)
    crc = _crc16_ccitt(payload)
    full = payload + bytes([(crc >> 8) & 0xFF, crc & 0xFF])
    body = _b32_no_pad_encode(full)
    # Keep the leading marker so a scanned QR is still self-identifying.
    return _PREFIX + body


def decode_node_code(code: str) -> NodeCode:
    """Decode a ``CIRIS-V1-...`` string back into a ``NodeCode``.

    Accepts dashed (display) or undashed (QR) forms. Whitespace and
    case differences are tolerated. The prefix is required.

    Raises:
        InvalidVersionError: if the leading version byte is not
            ``CIRIS_NODE_CODE_VERSION``, or the textual prefix is
            ``CIRIS-VN-`` for some other N.
        ChecksumMismatchError: if the trailing CRC does not match.
        MalformedNodeCodeError: for any other structural problem —
            wrong prefix, bad base32, truncated payload, over-long
            length declarations, invalid UTF-8.
    """
    if not isinstance(code, str):
        raise MalformedNodeCodeError("NodeCode must be a string")

    # Normalize: drop all whitespace, uppercase, drop separator dashes.
    cleaned = re.sub(r"\s+", "", code).upper()

    # Detect the prefix. Accept "CIRIS-V1-" and any other "CIRIS-VN-"
    # for clearer error messages on version mismatch.
    m = re.match(r"^CIRIS-V(\d+)-", cleaned)
    if m is not None:
        declared_version = int(m.group(1))
        if declared_version != CIRIS_NODE_CODE_VERSION:
            raise InvalidVersionError(
                f"Unsupported NodeCode version (textual prefix V{declared_version}); "
                f"this build supports V{CIRIS_NODE_CODE_VERSION}"
            )
        body = cleaned[len(m.group(0)) :]
    else:
        # Maybe undashed QR form: "CIRISVN..."
        m2 = re.match(r"^CIRISV(\d+)", cleaned)
        if m2 is None:
            raise MalformedNodeCodeError(
                f"NodeCode does not start with {_PREFIX!r} (or its undashed equivalent)"
            )
        declared_version = int(m2.group(1))
        if declared_version != CIRIS_NODE_CODE_VERSION:
            raise InvalidVersionError(
                f"Unsupported NodeCode version (textual prefix V{declared_version}); "
                f"this build supports V{CIRIS_NODE_CODE_VERSION}"
            )
        body = cleaned[len(m2.group(0)) :]

    # Strip the separator dashes from the body.
    body = body.replace("-", "")
    if not body:
        raise MalformedNodeCodeError("NodeCode has no payload after prefix")

    raw = _b32_no_pad_decode(body)

    # Minimum viable payload size:
    #   1 (ver) + 32 (hash) + 32 (pubkey) + 1 (key_id_len) + 1 (transport_len)
    #   + 1 (alias_len) + 2 (crc) = 70 bytes (with zero-length key_id which
    #   is technically allowed by the binary but is also nonsensical; the
    #   pydantic NodeCode model will reject empty key_id downstream).
    min_size = 1 + _KEY_ID_HASH_LEN + _PUBKEY_RAW_LEN + 1 + 1 + 1 + 2
    if len(raw) < min_size:
        raise MalformedNodeCodeError(
            f"NodeCode payload too short ({len(raw)} bytes; need at least {min_size})"
        )

    # Pull off the trailing CRC and verify.
    payload, crc_bytes = raw[:-2], raw[-2:]
    actual_crc = (crc_bytes[0] << 8) | crc_bytes[1]
    expected_crc = _crc16_ccitt(payload)
    if actual_crc != expected_crc:
        raise ChecksumMismatchError(
            f"CRC mismatch (declared 0x{actual_crc:04x}, computed 0x{expected_crc:04x})"
        )

    # Parse the binary fields.
    version = payload[0]
    if version != CIRIS_NODE_CODE_VERSION:
        raise InvalidVersionError(
            f"Unsupported NodeCode binary version 0x{version:02x}; "
            f"this build supports 0x{CIRIS_NODE_CODE_VERSION:02x}"
        )

    offset = 1
    # key_id_hash is consumed but not directly returned — the explicit
    # key_id string field is the round-trip source of truth.
    _key_id_hash = payload[offset : offset + _KEY_ID_HASH_LEN]
    offset += _KEY_ID_HASH_LEN

    pubkey_raw = payload[offset : offset + _PUBKEY_RAW_LEN]
    offset += _PUBKEY_RAW_LEN

    key_id_str, offset = _read_length_prefixed(payload, offset)
    transport_hint, offset = _read_length_prefixed(payload, offset)
    alias_hint, offset = _read_length_prefixed(payload, offset)

    if offset != len(payload):
        raise MalformedNodeCodeError(
            f"NodeCode has trailing garbage after parsed fields ({len(payload) - offset} extra bytes)"
        )

    if not key_id_str:
        raise MalformedNodeCodeError("Decoded key_id is empty — NodeCode is malformed")

    # Sanity-check the hash matches what we recover (defends against a
    # crafted payload that passes CRC but has a key_id_hash that doesn't
    # match key_id_str — would indicate tampering or codec bug).
    if hashlib.sha256(key_id_str.encode("utf-8")).digest() != _key_id_hash:
        raise MalformedNodeCodeError(
            "Decoded key_id hash does not match key_id string — NodeCode is corrupt"
        )

    pubkey_b64 = base64.b64encode(pubkey_raw).decode("ascii")

    return NodeCode(
        key_id=key_id_str,
        pubkey_ed25519_base64=pubkey_b64,
        transport_hint=transport_hint if transport_hint else None,
        alias_hint=alias_hint if alias_hint else None,
    )


__all__ = [
    "CIRIS_NODE_CODE_VERSION",
    "ChecksumMismatchError",
    "InvalidVersionError",
    "MalformedNodeCodeError",
    "NodeCodeError",
    "decode_node_code",
    "encode_node_code",
    "encode_qr_payload",
]
