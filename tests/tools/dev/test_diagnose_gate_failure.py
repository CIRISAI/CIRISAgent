"""The gate's failure classifier must not read the product's, the harness's or
the platform's vocabulary as evidence about the model wire.

Each case here is a line that produced a wrong verdict on a real run."""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "tools" / "dev"))
import diagnose_gate_failure as d  # noqa: E402


def classify(text: str, phase: str = "setup") -> tuple[str, str]:
    layer, meaning, _ = d.classify(d.strip_advice(text), phase)
    return layer, meaning


def test_a_simulator_udid_is_not_an_http_429() -> None:
    """2026-09-04 run 33897843767: a wizard failure was called 'rate limited'
    because \\b429\\b matched inside ...383A25F7429C in a simctl JSON dump."""
    line = '"dataPath" : "/Users/runner/Library/Developer/CoreSimulator/Devices/A5A59AE1-A7CB-41C3-80DF-383A25F7429C/data",'
    layer, _ = classify(line + "\nelement with testTag input_llm_provider not found\n")
    assert layer == "CLIENT"


def test_a_real_http_429_is_still_the_wire() -> None:
    layer, meaning = classify("openrouter returned HTTP 429 Too Many Requests\n", phase="interact")
    assert (layer, meaning) == ("WIRE", "provider refused: rate limited")


def test_wallet_x402_lines_are_not_a_payment_refusal() -> None:
    text = "2026-09-04 14:55:10.909 - WARNING - ciris_adapters.wallet.adapter - [WALLET_INIT] Creating provider: x402\nelement with testTag btn_next not found\n"
    assert classify(text)[0] == "CLIENT"


def test_the_harness_advice_is_not_a_dma_error() -> None:
    text = "the reply assertion found no message_type=='agent' row, so the agent did not answer.\n        Check the LLM is configured and the agent log for DMA errors.\n"
    assert classify(text, phase="interact")[0] == "SILENT"


def test_a_pid_or_byte_count_is_not_a_status_code() -> None:
    assert classify("pid=402 rss=429 bytes\nno logs were produced: none of the given log paths exist\n")[0] == "INFRA"


def test_evidence_is_the_matching_line() -> None:
    text = "harmless line mentioning 429 bytes\nopenrouter returned HTTP 429 Too Many Requests\n"
    _, _, evidence = d.classify(text, "interact")
    assert evidence.startswith("openrouter returned HTTP 429")


def test_an_attestation_sources_dict_is_not_a_rate_limit() -> None:
    """2026-09-04 run 33901202920: an iOS LOGIN failure was called 'rate limited'
    because 'rate_limited' appeared as a boolean key in the attestation
    verifier's sources dump."""
    line = ("2026-09-04 17:47:41.650 - ciris_engine.logic.services.infrastructure.authentication.attestation.verifier_runner "
            "- INFO - [attestation] sources={'dns_us_reachable': True, 'dns_us_valid': True, 'dns_us_rate_limited': False, 'registry': 'ok'}")
    layer, _ = classify(line + "\nInput 'input_username' failed: no text sink is listening for input_username; the field is tagged but not drivable\n", phase="login")
    assert layer == "CLIENT"


def test_a_provider_naming_a_rate_limit_is_still_the_wire() -> None:
    assert classify("openrouter: rate limit exceeded, retry_after=30\n", phase="interact")[0] == "WIRE"
    assert classify("provider returned 429 Too Many Requests\n", phase="interact")[0] == "WIRE"
