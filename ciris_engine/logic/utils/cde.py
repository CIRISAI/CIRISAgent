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
* ``False``/``True``/``None`` as simple values 20/21/22;
* a digest is written ``[-16, digest-bytes]`` (an ordinary array);
* NO float is written anywhere (wire.md revision 4).

Numbers go by their EXACT decimal value (rc21 wire §4):

* an integral value is an integer (``1e2`` -> 100,
  ``9007199254740993.0`` -> 9007199254740993, ``-0.0`` -> 0); outside CBOR's
  integer range (major types 0/1: -2**64 .. 2**64-1) it is refused with
  :data:`CALL_ARGUMENT_UNREPRESENTABLE`; an integral value of 10**20 or more
  is refused from its decimal exponent without being expanded (``1e400``
  never becomes a 400-digit integer);
* a non-integral value is CBOR tag 4, a decimal fraction
  ``[exponent, mantissa]`` (RFC 8949 section 3.4.4), NORMALISED: the exponent
  negative and the mantissa not divisible by ten. ``0.1``, ``1.0e-1`` and
  ``0.10`` all encode as ``4([-1, 1])``; ``-273.15`` as ``4([-2, -27315])``.
  Never rounded: a mantissa outside CBOR's integer range is refused
  (``1 + 2**-53`` written out exactly has a 54-digit mantissa).

Where the JSON text is at hand, parse it with :func:`loads_exact` (``Decimal``
for every non-integer literal), so the value is the one the text states.

A Python ``float`` (the agent has only that for ``ToolParams`` arguments,
already parsed) is read as ``Decimal(repr(f))``: Python's ``repr`` is the
shortest decimal that round-trips to that binary64, which is the decimal a
model writes in its JSON (``0.1`` -> ``0.1``, never
``0.1000000000000000055511151231257827``). The one loss is a literal that
plain ``json.loads`` already rounded (``9007199254740993.0`` reads as
``9007199254740992.0``); both sides of a check that hash the same parsed object
still agree.
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


def _tag(tag: int, encoded: bytes) -> bytes:
    return _head(6, tag) + encoded


def _number_decimal(value: Decimal) -> bytes:
    """An exact decimal: an integer when integral by value, else tag 4 ``[exponent, mantissa]`` normalised."""
    if not value.is_finite():
        raise CdeError(f"{value} has no CDE form")
    if value.is_zero():
        return _int(0)  # -0, 0e999: integral by value
    if value == value.to_integral_value():
        # Integral: refuse a magnitude of 10**20 or more from its exponent, never expanding it (10**20 > 2**64).
        if value.adjusted() >= _MAGNITUDE_LIMIT_EXP10:
            raise CdeError(f"an integral number at or beyond 10**{_MAGNITUDE_LIMIT_EXP10} ({str(value)[:32]})")
        return _int(int(value))
    sign, digits, exponent = value.as_tuple()
    assert isinstance(exponent, int)  # finite
    # The digit count bounds the work: a mantissa of more than 20 digits is past 2**64 whatever its digits are.
    significant = "".join(map(str, digits)).rstrip("0")
    exponent += len(digits) - len(significant)
    if len(significant) > _MAGNITUDE_LIMIT_EXP10:
        raise CdeError(f"a decimal mantissa outside CBOR's integer range ({str(value)[:32]})")
    mantissa = int(significant) * (-1 if sign else 1)
    return _tag(4, _head(4, 2) + _int(exponent) + _int(mantissa))


def _number_float(value: float) -> bytes:
    """A parsed float, read as its shortest round-trip decimal (``Decimal(repr(f))``): no float is written."""
    if not math.isfinite(value):
        raise CdeError(f"{value!r} has no CDE form")
    return _number_decimal(Decimal(repr(value)))


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
