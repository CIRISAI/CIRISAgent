"""Substrate contract for consent + location — the 2.9.8-readiness pins.

WHY THESE ARE TESTS RATHER THAN A NOTE.

Every dependency here is on a wheel that ships independently of this repo, and
this project's recurring failure is a claim that outruns what it measures. A
comment saying "mint lands in 2.9.8" rots silently; a test saying so FAILS the
day it arrives, which is exactly when someone needs to be told.

test_mint_is_the_only_missing_half is deliberately an inverted assertion: it
passes while the entry point is ABSENT and fails when it appears. That is not a
mistake — it is the notification. CIRISServer#341 landing should break this
build, at which point location_utils._mint_location_proof activates on its own
(it is getattr-guarded) and the assertion gets flipped.

"""
_ORIGINAL_DOC = """The 2.9.8-readiness contract: every substrate path we depend on is either
present and exercised, or absent and guarded so it activates without a release.
"""
import ciris_server as cs


def test_consent_mint_signature_takes_analyze():
    import inspect
    sig = inspect.signature(cs.author_federation_consent)
    assert list(sig.parameters) == ["peer_key_id", "attestation_prefixes", "analyze"], sig
    # analyze must default OFF: an incomplete grant should require asking for it.
    assert sig.parameters["analyze"].default is False


def test_stance_probe_exists():
    assert callable(cs.analyze_consent_stance)


def test_disclosure_publishes_the_location_contract():
    import json
    d = json.loads(cs.consent_disclosure())
    loc = d["location"]
    assert loc["carrier"] == "location_proof"
    assert loc["cell_format"] == "h3"
    assert isinstance(loc["max_resolution"], int)


def test_mint_is_the_only_missing_half():
    # Read exists; mint does not. When CIRISServer#341 lands this flips and the
    # agent-side path activates with no agent release.
    from ciris_engine.logic.persistence.models.graph import get_persist_engine  # noqa: F401
    assert hasattr(cs.Engine, "list_signed_location_proofs_since")
    assert getattr(cs, "mint_location_proof", None) is None, (
        "mint_location_proof now exists — location_utils._mint_location_proof activates; "
        "update this test and confirm resolution is read from consent_disclosure()"
    )
