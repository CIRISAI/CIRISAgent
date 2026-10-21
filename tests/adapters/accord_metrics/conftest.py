"""Fixtures for accord_metrics adapter tests.

2.9.7 (second-signer removal): the instance-hash / key-id derivations read
the persist Engine's local signer via get_persist_engine(). Tests run
without a wired engine, so the service exercises the fallback agent_id
hashing path; no signing mock is needed. (Trace SIGNING moved to the
lens-core substrate in the 2.9.6 fold — CIRISAgent#866.)
"""


import pytest


@pytest.fixture(autouse=True)
def _substrate_can_scrub(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let these tests get the trace level they ask for.

    2.9.18 made the service downgrade `full_traces` -> `detailed` when the
    substrate has no reachable egress scrubber, because persist v32.1.0 rejects
    unscrubbed full-detail batches outright and NOTHING persists
    (CIRISServer#418). CI has no scrubbable substrate, so every test here that
    constructs a full_traces service silently got `detailed` instead — which is
    how a correct guard broke `test_full_traces_adds_prompt_and_response` with
    `KeyError: 'prompt'`.

    These suites are about level RESOLUTION and EXTRACTION, not about substrate
    capability, so they get a substrate that can scrub and keep testing what
    they were written to test. The capability behaviour itself is covered
    explicitly by tests/ciris_adapters/ciris_accord_metrics/
    test_full_traces_downgrade.py — asserted there rather than assumed here.
    """
    import ciris_adapters.ciris_accord_metrics.services as svc

    monkeypatch.setattr(svc, "substrate_can_scrub", lambda: True, raising=True)
