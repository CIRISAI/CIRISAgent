"""The shared CDE encoder and the rc21 derived digests (CEG-call/2, CEG-review/2, CEG-profile/2).

The golden vectors are the constitution's (``formal/admission/digest_vectors.json``),
copied to ``tests/fixtures/rc21_digest_vectors.json``. Every case in the file
runs: a case with ``cde_hex`` must reproduce its bytes and digest; a case that
names a refusal (``refused``/``refusal``/``token``/``error``) must be refused
with that token.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping

import pytest

from ciris_engine.logic.utils.cde import (
    CALL_ARGUMENT_UNREPRESENTABLE,
    CdeError,
    cde_encode,
    cde_set,
    ceg_digest,
    loads_exact,
)

VECTORS_PATH = Path(__file__).resolve().parents[3] / "fixtures" / "rc21_digest_vectors.json"
VECTORS: Dict[str, Any] = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
_REFUSAL_KEYS = ("refused", "refusal", "token", "error")


def _refusal_token(case: Dict[str, Any]) -> str | None:
    for key in _REFUSAL_KEYS:
        value = case.get(key)
        if isinstance(value, str) and value:
            return value
        if value is True:
            return CALL_ARGUMENT_UNREPRESENTABLE
    return None


def _wire(value: Any) -> Any:
    """A vector's JSON digest pair ``[-16, "<hex>"]`` as the encoder's ``[-16, bytes]``."""
    return [value[0], bytes.fromhex(value[1])]


# ------------------------------------------------------------------ RFC 8949 Appendix A


@pytest.mark.parametrize(
    "value,hex_",
    [
        (0, "00"),
        (23, "17"),
        (24, "1818"),
        (1000000000000, "1b000000e8d4a51000"),
        (18446744073709551615, "1bffffffffffffffff"),
        (-1, "20"),
        (-1000, "3903e7"),
        (-18446744073709551616, "3bffffffffffffffff"),
        (False, "f4"),
        (True, "f5"),
        (None, "f6"),
        ("", "60"),
        ("IETF", "6449455446"),
        ("ü", "62c3bc"),
        (b"\x01\x02\x03\x04", "4401020304"),
        ([], "80"),
        ([1, [2, 3], [4, 5]], "8301820203820405"),
        ({"a": 1, "b": [2, 3]}, "a26161016162820203"),
        (Decimal("273.15"), "c48221196ab3"),  # RFC 8949 3.4.4: 4([-2, 27315])
    ],
)
def test_rfc8949_examples(value: Any, hex_: str) -> None:
    assert cde_encode(value).hex() == hex_


# ---------------------------------------------------------------- numbers by exact value


def test_2_pow_53_plus_1_with_point_zero_is_that_exact_integer_via_decimal() -> None:
    parsed = loads_exact('{"n": 9007199254740993.0}')["n"]
    assert isinstance(parsed, Decimal)
    assert cde_encode(parsed).hex() == "1b0020000000000001"  # 9007199254740993, not ...992
    # Plain json.loads has already lost it: the limitation the module documents.
    assert cde_encode(json.loads("9007199254740993.0")).hex() == "1b0020000000000000"


def test_exponent_integral_is_an_integer() -> None:
    assert cde_encode(loads_exact("1e2")).hex() == "1864"
    assert cde_encode(1e2).hex() == "1864"


def test_negative_zero_is_zero() -> None:
    assert cde_encode(-0.0).hex() == "00"
    assert cde_encode(loads_exact("-0.0")).hex() == "00"


@pytest.mark.parametrize("text", ["0.1", "1.0e-1", "0.10", "0.100000"])
def test_a_non_integral_number_is_its_normalised_decimal_fraction(text: str) -> None:
    assert cde_encode(loads_exact(text)).hex() == "c4822001"  # 4([-1, 1])


def test_a_negative_decimal_fraction() -> None:
    assert cde_encode(loads_exact("-273.15")).hex() == "c48221396ab2"  # 4([-2, -27315])


def test_no_float_is_ever_written() -> None:
    for value in (loads_exact("1.5"), loads_exact("100000.5"), 0.5, 1.1, 5.960464477539063e-8, -4.1):
        encoded = cde_encode(value)
        assert encoded[0] == 0xC4, (value, encoded.hex())  # tag 4, never a major-7 float head
        assert not any(encoded.startswith(h) for h in (b"\xf9", b"\xfa", b"\xfb"))


def test_a_parsed_float_is_read_as_its_shortest_round_trip_decimal() -> None:
    """ToolParams arguments arrive as floats: Decimal(repr(f)) is the decimal the model wrote."""
    assert cde_encode(0.1) == cde_encode(loads_exact("0.1"))
    assert cde_encode(-273.15) == cde_encode(loads_exact("-273.15"))
    assert cde_encode(2.0).hex() == "02"


def test_1e300_is_integral_and_beyond_cbor_integers_so_refused() -> None:
    for value in (loads_exact("1e300"), 1e300):
        with pytest.raises(CdeError) as info:
            cde_encode(value)
        assert info.value.token == CALL_ARGUMENT_UNREPRESENTABLE


@pytest.mark.parametrize("value", [2**64, -(2**64) - 1, Decimal("18446744073709551616")])
def test_out_of_range_integer_refused(value: Any) -> None:
    with pytest.raises(CdeError) as info:
        cde_encode(value)
    assert info.value.token == CALL_ARGUMENT_UNREPRESENTABLE


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), Decimal("NaN"), Decimal("Infinity")])
def test_non_finite_refused(value: Any) -> None:
    with pytest.raises(CdeError):
        cde_encode(value)


@pytest.mark.parametrize(
    "text",
    [
        "1.00000000000000011102230246251565404236316680908203125",  # 1 + 2**-53 exactly: never rounded
        "0.18446744073709551616",  # mantissa 2**64
        "-0.18446744073709551617",  # mantissa -(2**64) - 1
        "1." + "1" * 400,
    ],
)
def test_a_mantissa_outside_cbor_integers_is_refused(text: str) -> None:
    with pytest.raises(CdeError) as info:
        cde_encode(loads_exact(text))
    assert info.value.token == CALL_ARGUMENT_UNREPRESENTABLE


def test_the_mantissa_range_ends_are_kept() -> None:
    assert cde_encode(loads_exact("0.18446744073709551615")).hex() == "c482331bffffffffffffffff"
    assert cde_encode(loads_exact("-0.18446744073709551616")).hex() == "c482333bffffffffffffffff"


def test_the_cbor_integer_range_ends_are_integers() -> None:
    assert cde_encode(loads_exact("18446744073709551615")).hex() == "1bffffffffffffffff"
    assert cde_encode(loads_exact("-18446744073709551616")).hex() == "3bffffffffffffffff"
    assert cde_encode(loads_exact("1.8446744073709551615e19")).hex() == "1bffffffffffffffff"


@pytest.mark.parametrize("text", ["1e400", "1e400000000", "-1e999999999", "100000000000000000000", "1e20"])
def test_an_integral_magnitude_from_1e20_is_refused_without_being_expanded(text: str) -> None:
    with pytest.raises(CdeError) as info:
        cde_encode(loads_exact(text))
    assert info.value.token == CALL_ARGUMENT_UNREPRESENTABLE


def test_a_zero_with_any_exponent_is_the_integer_zero() -> None:
    assert cde_encode(loads_exact("0e999999999")).hex() == "00"


def test_a_tiny_decimal_keeps_its_exponent_without_expansion() -> None:
    assert cde_encode(loads_exact("1e-999999")).hex() == "c4823a000f423e01"  # 4([-999999, 1])


def test_refusal_is_a_value_error() -> None:
    """Callers that catch ValueError (action_review_fingerprint) keep working."""
    assert issubclass(CdeError, ValueError)


# ----------------------------------------------------------------------------- maps


def test_nested_map_keys_in_bytewise_order_of_their_encodings() -> None:
    value = {"to": "room", "body": {"tags": ["b", "a"], "meta": {"z": -1, "a": [1, {"k": "v"}]}}}
    # "to" (2 chars) sorts before "body" (4 chars): length-first via the head byte.
    assert cde_encode(value).hex() == (
        "a262746f64726f6f6d64626f6479a2646d657461a261618201a1616b6176617a2064746167738261626161"
    )
    assert cde_encode(value) == cde_encode(dict(reversed(list(value.items()))))


def test_empty_map() -> None:
    assert cde_encode({}).hex() == "a0"


def test_unicode_keys_sort_by_the_bytes_of_their_encodings() -> None:
    # "z" -> 617a, "ab" -> 626162, "é" -> 62c3a9: shorter first, then bytewise UTF-8.
    assert cde_encode({"é": 1, "ab": 2, "z": 3}).hex() == "a3" + "617a03" + "62616202" + "62c3a901"


class _DuplicateKeys(Mapping[Any, Any]):
    """A mapping whose items name one key twice (two distinct Python keys, one encoding)."""

    def __getitem__(self, key: Any) -> Any:
        raise KeyError(key)

    def __iter__(self) -> Iterator[Any]:
        return iter(())

    def __len__(self) -> int:
        return 2

    def items(self) -> Any:  # type: ignore[override]
        return [("k", 1), ("k", 2)]


def test_two_keys_with_one_encoding_are_refused() -> None:
    with pytest.raises(CdeError):
        cde_encode(_DuplicateKeys())


def test_set_orders_by_encoding_and_dedupes() -> None:
    assert cde_set(["optimization_veto", "coherence", "entropy", "coherence"]) == [
        "entropy",
        "coherence",
        "optimization_veto",
    ]


# ----------------------------------------------------------- the constitution's goldens


def test_golden_file_has_every_family() -> None:
    assert {"call", "review", "profile"} <= set(VECTORS)
    assert VECTORS["call"] and VECTORS["review"] and VECTORS["profile"]


@pytest.mark.parametrize("case", VECTORS["call"], ids=lambda c: c.get("what", "?"))
def test_golden_call_vectors(case: Dict[str, Any]) -> None:
    from ciris_engine.logic.infrastructure.authorization.reviewed_action import ceg_call_fingerprint

    token = _refusal_token(case)
    if token is not None:
        with pytest.raises(CdeError) as info:
            ceg_call_fingerprint(case["verb"], case["tool"], loads_exact(case["arguments_json"]), case["channel"])
        assert info.value.token == token
        return
    arguments = loads_exact(case["arguments_json"])
    encoded = cde_encode(["CEG-call/2", case["verb"], case["tool"], arguments, case["channel"]])
    assert encoded.hex() == case["cde_hex"]
    assert ceg_digest("CEG-call/2", [case["verb"], case["tool"], arguments, case["channel"]]).hex() == case["digest"][1]
    # The agent's fingerprint function (the one review and dispatch share) gives the same digest.
    fingerprint = ceg_call_fingerprint(case["verb"], case["tool"], arguments, case["channel"] or None)
    assert fingerprint == f"-16:{case['digest'][1]}"


@pytest.mark.parametrize("case", VECTORS["profile"], ids=lambda c: c.get("what", "?"))
def test_golden_profile_vectors(case: Dict[str, Any]) -> None:
    from ciris_engine.logic.context.identity_profile import encode_profile, profile_digest

    hexes: List[str] = [link[1] for link in case["links"]]
    assert encode_profile(hexes[0], hexes[1:]).hex() == case["cde_hex"]
    assert profile_digest(hexes[0], hexes[1:]) == case["digest"][1]


def _review_records() -> List[Any]:
    """The review records the constitution's generator encodes (digest_vectors.py), rebuilt from the vectors."""
    from ciris_engine.schemas.runtime.reviewed_action_admission import (
        REQUIRED_REVIEW_FACULTIES,
        ReviewDischarge,
        ReviewOutcome,
        ReviewRecord,
    )

    fp = f"-16:{VECTORS['call'][0]['digest'][1]}"
    objection = ReviewRecord(fingerprint=fp, thought="th-1", outcome=ReviewOutcome.OBJECTED, faculties=("optimization_veto",))
    plain = ReviewRecord(
        fingerprint=fp, thought="th-1", outcome=ReviewOutcome.PASSED, faculties=tuple(sorted(REQUIRED_REVIEW_FACULTIES))
    )
    full = ReviewRecord(
        fingerprint=fp,
        thought="th-1",
        outcome=ReviewOutcome.PASSED,
        faculties=tuple(sorted(REQUIRED_REVIEW_FACULTIES)),
        discharges=(ReviewDischarge(objection=f"-16:{VECTORS['review'][0]['digest'][1]}", evidence="09" * 32),),
        considered=("-16:" + "04" * 32,),
        derived_from=("tool_output", "request"),
    )
    return [objection, plain, full]


@pytest.mark.parametrize("index", range(3))
def test_golden_review_vectors(index: int) -> None:
    from ciris_engine.logic.infrastructure.authorization.reviewed_action import review_record_digest, review_record_wire

    case = VECTORS["review"][index]
    record = _review_records()[index]
    assert cde_encode(review_record_wire(record)).hex() == case["record_cde_hex"]
    assert cde_encode(["CEG-review/2", review_record_wire(record)]).hex() == case["cde_hex"]
    assert review_record_digest(record) == f"-16:{case['digest'][1]}"


def test_every_review_vector_is_covered() -> None:
    """A vector added to the file without a rebuilt record here fails, rather than passing unseen."""
    assert len(VECTORS["review"]) == len(_review_records())


def test_golden_digests_are_sha256_of_their_bytes() -> None:
    for family in ("call", "review", "profile"):
        for case in VECTORS[family]:
            if "cde_hex" in case:
                assert hashlib.sha256(bytes.fromhex(case["cde_hex"])).hexdigest() == case["digest"][1]


def test_a_proposed_call_is_verified_from_its_json_text_by_exact_value() -> None:
    """The deferral's proposed_call is JSON text: its numbers are read exactly, not through binary64."""
    from ciris_engine.logic.infrastructure.authorization.reviewed_action import tool_call_fingerprint
    from ciris_engine.logic.infrastructure.authorization.tool_approval import proposed_call_fingerprint

    arguments_text = '{"amount": 9007199254740993.0}'
    stated = tool_call_fingerprint("pay", loads_exact(arguments_text), "c1")
    assert stated != tool_call_fingerprint("pay", json.loads(arguments_text), "c1")
    raw = '{"tool": "pay", "arguments": %s, "channel": "c1", "call_fingerprint": "%s"}' % (arguments_text, stated)
    assert proposed_call_fingerprint({"proposed_call": raw}) == stated
