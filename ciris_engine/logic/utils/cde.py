"""CBOR deterministic encoding (CDE) and the CEG derived digests (rc21, CC 2.7.11).

THE one encoder for every derived digest the agent computes:

* ``CEG-call/2``    a call's fingerprint (``reviewed_action``),
* ``CEG-review/2``  a review record's digest (``reviewed_action``),
* ``CEG-profile/2`` the whole-profile digest (``identity_profile``).

``ceg_digest(tag, members)`` = SHA-256(CDE([tag, *members])).

Pure Python, standard library only: cbor2 is not a declared dependency, and a
phone must compute the same bytes as a desktop. RFC 8949 section 4.2.1 (core
deterministic encoding):

* integers, lengths and tags in the shortest head; definite lengths only;
* map keys ordered by the bytewise order of their encodings (for text keys
  this is length-first, then bytewise); two keys with one encoding refused;
* a non-integral number in the shortest of half, single and double precision
  that keeps its binary64 value exactly; NaN and infinities refused;
* ``False``/``True``/``None`` as simple values 20/21/22;
* a digest is written ``[-16, digest-bytes]`` (an ordinary array).

Numbers go by their EXACT value (constitution/server agreement, 2026-11-18):

* an integral value is an integer (``1e2`` -> 100,
  ``9007199254740993.0`` -> 9007199254740993, ``-0.0`` -> 0);
* an integer outside CBOR's range (major types 0/1: -2**64 .. 2**64-1) is
  refused with :data:`CALL_ARGUMENT_UNREPRESENTABLE`; so is ANY number of
  magnitude 10**20 or more, decided from the decimal exponent without
  expanding it (``1e400`` never becomes a 400-digit integer);
* a non-integral value is its nearest binary64 (ties to even), written as the
  shortest float that keeps it: ``1 + 2**-53`` is the float 1.0, ``f93c00``,
  not the integer 1 (integrality is judged on the exact decimal value).

A float already parsed by plain ``json.loads`` has lost the exact decimal
(``9007199254740993.0`` reads as ``9007199254740992.0``). Where the JSON text
is at hand, parse it with :func:`loads_exact` (``Decimal`` for every
non-integer literal). A float that reaches the encoder is taken at its own
binary64 value, which is exact for that float; both sides of a check that hash
the same parsed object still agree.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
from decimal import Decimal
from typing import Any, List, Mapping, Sequence, Tuple

#: The refusal token for a value the fingerprint cannot write (CC 2.7.11).
CALL_ARGUMENT_UNREPRESENTABLE = "call_argument_unrepresentable"
#: The COSE algorithm id of SHA-256: a digest is written ``[-16, digest]``.
SHA256_ALG = -16

_UINT_LIMIT = 1 << 64
#: Every number at or above this magnitude is refused without being expanded:
#: no integer at or above it fits CBOR (2**64 < 10**20), and a decimal literal
#: such as ``1e400000000`` must never be turned into a Python int.
_MAGNITUDE_LIMIT_EXP10 = 20


class CdeError(ValueError):
    """A value with no CDE form. ``token`` is the rc21 refusal token."""

    def __init__(self, detail: str, token: str = CALL_ARGUMENT_UNREPRESENTABLE) -> None:
        super().__init__(f"{token}: {detail}")
        self.token = token
        self.detail = detail


def _head(major: int, argument: int) -> bytes:
    if argument < 24:
        return bytes([(major << 5) | argument])
    for info, fmt, limit in ((24, ">B", 1 << 8), (25, ">H", 1 << 16), (26, ">I", 1 << 32), (27, ">Q", _UINT_LIMIT)):
        if argument < limit:
            return bytes([(major << 5) | info]) + struct.pack(fmt, argument)
    raise CdeError(f"integer {argument} is outside CBOR's integer range")


def _int(value: int) -> bytes:
    if not -_UINT_LIMIT <= value < _UINT_LIMIT:
        raise CdeError(f"integer {value} is outside CBOR's integer range")
    return _head(0, value) if value >= 0 else _head(1, -1 - value)


def _float(value: float) -> bytes:
    """The shortest of half/single/double that keeps ``value`` (non-integral, finite)."""
    for info, fmt in ((25, ">e"), (26, ">f")):
        try:
            packed = struct.pack(fmt, value)
        except (OverflowError, struct.error):
            continue
        if struct.unpack(fmt, packed)[0] == value:
            return bytes([0xE0 | info]) + packed
    return b"\xfb" + struct.pack(">d", value)


def _number_float(value: float) -> bytes:
    if not math.isfinite(value):
        raise CdeError(f"{value!r} has no CDE form")
    if abs(value) >= 10.0**_MAGNITUDE_LIMIT_EXP10:
        raise CdeError(f"{value!r} is at or beyond 10**{_MAGNITUDE_LIMIT_EXP10}")
    if value.is_integer():
        return _int(int(value))  # exact; -0.0 -> 0
    return _float(value)


def _number_decimal(value: Decimal) -> bytes:
    if not value.is_finite():
        raise CdeError(f"{value} has no CDE form")
    if value.is_zero():
        return _int(0)  # -0, 0e999: integral by value
    if value.adjusted() >= _MAGNITUDE_LIMIT_EXP10:
        raise CdeError(f"a number at or beyond 10**{_MAGNITUDE_LIMIT_EXP10} ({str(value)[:32]})")
    if value == value.to_integral_value():
        return _int(int(value))  # exact decimal value, never through binary64
    nearest = float(value)  # correctly rounded to the nearest binary64
    if not math.isfinite(nearest):
        raise CdeError(f"{value} is beyond binary64")
    return _float(nearest)


def cde_encode(value: Any) -> bytes:
    """CDE bytes of ``value`` (see the module docstring for the type rules)."""
    if value is None:
        return b"\xf6"
    if value is True:
        return b"\xf5"
    if value is False:
        return b"\xf4"
    if isinstance(value, int):
        return _int(value)
    if isinstance(value, Decimal):
        return _number_decimal(value)
    if isinstance(value, float):
        return _number_float(value)
    if isinstance(value, str):
        raw = value.encode("utf-8")
        return _head(3, len(raw)) + raw
    if isinstance(value, (bytes, bytearray, memoryview)):
        data = bytes(value)
        return _head(2, len(data)) + data
    if isinstance(value, (list, tuple)):
        return _head(4, len(value)) + b"".join(cde_encode(item) for item in value)
    if isinstance(value, Mapping):
        items: List[Tuple[bytes, bytes]] = sorted((cde_encode(k), cde_encode(v)) for k, v in value.items())
        for (left, _), (right, _) in zip(items, items[1:]):
            if left == right:
                raise CdeError("two map keys have one encoding")
        return _head(5, len(items)) + b"".join(k + v for k, v in items)
    raise CdeError(f"{type(value).__name__} has no CDE form")


def cde_set(items: Sequence[Any]) -> List[Any]:
    """A set (CC 2.6.1.2): distinct members ordered by the bytewise order of their encodings."""
    unique = {cde_encode(item): item for item in items}
    return [unique[key] for key in sorted(unique)]


def ceg_digest(tag: str, members: Sequence[Any]) -> bytes:
    """SHA-256(CDE([tag, *members])): the raw 32-byte digest."""
    return hashlib.sha256(cde_encode([tag, *members])).digest()


def digest_wire(digest: bytes) -> List[Any]:
    """``[-16, digest]``, the wire form of a SHA-256 digest."""
    return [SHA256_ALG, bytes(digest)]


def loads_exact(text: str) -> Any:
    """``json.loads`` that keeps every non-integer literal's exact decimal value (``Decimal``)."""
    return json.loads(text, parse_float=Decimal)


__all__ = [
    "CALL_ARGUMENT_UNREPRESENTABLE",
    "CdeError",
    "SHA256_ALG",
    "cde_encode",
    "cde_set",
    "ceg_digest",
    "digest_wire",
    "loads_exact",
]
