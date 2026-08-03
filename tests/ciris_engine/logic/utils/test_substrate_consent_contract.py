"""Substrate contract for consent + location — the 2.9.8-readiness pins.

WHY THESE ARE TESTS RATHER THAN A NOTE.

Every dependency here is on a wheel that ships independently of this repo, and
this project's recurring failure is a claim that outruns what it measures. A
comment saying "mint lands in 2.9.8" rots silently; a test saying so FAILS the
day it arrives, which is exactly when someone needs to be told.

test_mint_is_the_only_missing_half was deliberately an inverted assertion: it
passed while the entry point was ABSENT and failed when it appeared. That was
not a mistake — it was the notification, and it FIRED on ciris-server 0.5.154
(CIRISServer#341 landed, 2026-08-02, the #979 refloat). The assertions below
are the flipped half it demanded: the symbol exists, the getattr-guarded
call site in location_utils._mint_location_proof activates on its own, and the
CEG 0.8 §0.8.1 rough-only bound is enforced against the REAL mint — with the
bound READ from consent_disclosure(), never restated as a literal.
"""
_ORIGINAL_DOC = """The 2.9.8-readiness contract: every substrate path we depend on is either
present and exercised, or absent and guarded so it activates without a release.
"""
import inspect
import json
import subprocess
import sys
import textwrap

import ciris_server as cs
import pytest


def test_consent_mint_signature_takes_analyze():
    sig = inspect.signature(cs.author_federation_consent)
    assert list(sig.parameters) == ["peer_key_id", "attestation_prefixes", "analyze"], sig
    # analyze must default OFF: an incomplete grant should require asking for it.
    assert sig.parameters["analyze"].default is False


def test_stance_probe_exists():
    assert callable(cs.analyze_consent_stance)


def test_disclosure_publishes_the_location_contract():
    d = json.loads(cs.consent_disclosure())
    loc = d["location"]
    assert loc["carrier"] == "location_proof"
    assert loc["cell_format"] == "h3"
    assert isinstance(loc["max_resolution"], int)


def test_mint_exists_and_defaults_to_the_build_resolution():
    """The 0.5.154 flip of test_mint_is_the_only_missing_half (CIRISServer#341).

    The mint is present, and its resolution parameter defaults to None — the
    convention (same as author_federation_consent's prefixes) under which the
    BUILD supplies its own bound instead of every caller restating it.
    """
    mint = getattr(cs, "mint_location_proof", None)
    assert mint is not None, (
        "mint_location_proof vanished from ciris_server — the #959 location_proof "
        "path is dead again and format_coordinates_for_trace silently emits no proof"
    )
    assert callable(mint)
    sig = inspect.signature(mint)
    assert list(sig.parameters) == ["latitude", "longitude", "resolution"], sig
    assert sig.parameters["resolution"].default is None


def test_call_site_activates_and_never_restates_the_bound(monkeypatch):
    """location_utils._mint_location_proof activates now that the symbol exists.

    The call site was getattr-guarded so it would turn itself on with no agent
    release; assert it did, and that it passes resolution=None — the substrate's
    own contract ("a caller that hardcodes 7 has made a copy that can silently
    disagree with the substrate"). Coordinates are Null Island (0.0, 0.0) —
    obviously a test value, nobody's locality.
    """
    from ciris_engine.logic.utils.location_utils import UserLocation, _mint_location_proof

    calls = []

    def recording_mint(latitude, longitude, resolution=None):
        calls.append((latitude, longitude, resolution))
        return '{"location_proof": "canned"}'

    monkeypatch.setattr(cs, "mint_location_proof", recording_mint)
    proof = _mint_location_proof(UserLocation(latitude=0.0, longitude=0.0))

    assert proof == '{"location_proof": "canned"}'
    assert calls == [(0.0, 0.0, None)], (
        "the call site must pass resolution=None (the build's own default) — "
        "a restated literal is a copy of the bound that can drift"
    )


# The real mint needs the live node runtime (in-process Engine + edge +
# start_federation_delivery — 0.5.154 refuses without it), and both the engine
# and the edge are process singletons. Run the real-substrate clamp check in a
# subprocess so nothing is left pinned in the pytest process.
_CLAMP_PROBE = textwrap.dedent(
    """
    import json, os, sys, tempfile
    import ciris_server as cs

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "clamp.db")
    for suffix in (".seed", ".pqc"):
        with open(db + suffix, "wb") as fh:
            fh.write(os.urandom(32))
    engine = cs.Engine(
        f"sqlite:///{db}",
        "clamp-key",
        local_key_id="clamp-key",
        local_key_path=db + ".seed",
        local_pqc_key_id="clamp-key-pqc",
        local_pqc_key_path=db + ".pqc",
    )
    engine.register_self_federation_key("agent", "clamp-key", None, None, None)
    # Keep the handle alive — dropping it un-registers the process-global edge.
    edge = cs.init_edge_runtime(
        engine,
        os.path.join(tmp, "edge_identity.rid"),
        listen_addr="127.0.0.1:0",
        enable_transport=True,
    )
    cs.start_federation_delivery()

    # The bound is READ from the disclosure — the single source, never restated.
    max_resolution = json.loads(cs.consent_disclosure())["location"]["max_resolution"]

    result = {"max_resolution": max_resolution}
    try:
        cs.mint_location_proof(0.0, 0.0, max_resolution + 1)
        result["over_bound"] = "MINTED"
    except Exception as exc:
        result["over_bound"] = str(exc)

    proof = json.loads(cs.mint_location_proof(0.0, 0.0, None))
    result["default_resolution"] = proof["location_proof"]["cell_resolution"]
    result["cell_id"] = proof["location_proof"]["cell_id"]
    print("RESULT:" + json.dumps(result))
    """
)


@pytest.mark.timeout(240)
def test_rough_only_clamp_holds_against_the_real_mint():
    """CEG 0.8 §0.8.1: minting finer than the bound is REFUSED by the substrate.

    Runs the REAL mint_location_proof (not a double): a request one step finer
    than consent_disclosure()'s max_resolution must be refused with the bound
    named, and the default (resolution=None — what our call site passes) must
    come back at or under the bound. This is the second line of defence the
    #959 note relies on; if it ever stops holding, raw-precision location could
    reach a trace through a client-gating failure.
    """
    completed = subprocess.run(
        [sys.executable, "-c", _CLAMP_PROBE],
        capture_output=True,
        text=True,
        timeout=220,
    )
    assert completed.returncode == 0, (
        f"clamp probe subprocess failed\nstdout: {completed.stdout}\nstderr: {completed.stderr}"
    )
    payload = next(
        (line[len("RESULT:") :] for line in completed.stdout.splitlines() if line.startswith("RESULT:")),
        None,
    )
    assert payload is not None, f"no RESULT line in probe output: {completed.stdout}"
    result = json.loads(payload)

    assert result["over_bound"] != "MINTED", (
        f"the substrate MINTED a proof finer than max_resolution={result['max_resolution']} — "
        "the §0.8.1 rough-only clamp is not enforced"
    )
    # The refusal names the bound it enforces — the same number the disclosure publishes.
    assert str(result["max_resolution"]) in result["over_bound"], result["over_bound"]
    assert result["default_resolution"] <= result["max_resolution"]
    assert result["cell_id"]  # a real H3 cell came back for Null Island
