"""Unit pins for the occurrence-capacity terms (the 2.9.6 erroneous-1.0 fix).

These cover the pure helpers `_compute_local_capacity` composes — the
formula J = μ · k_eff · λ · σ · τ (Accord 1.3 form) and the trust-edge
probes that drive τ. End-to-end behavior is exercised by the QA runner;
these pin the arithmetic and the trust semantics at the unit level:

  * no health surface = missing EVIDENCE (None), never healthy-by-default
    — the pre-2.9.6 default-True is what minted the erroneous 1.0s;
  * correlation enters THROUGH k_eff (A2: no separate (1−ρ̄) factor);
  * the interim self-authored community grant (sentinel counterparty) is
    NOT a trust edge — τ stays at TAU_ISOLATED;
  * J < 1.0 by construction (τ ≤ TAU_ATTESTED < 1).
"""

from __future__ import annotations

import json
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.logic.adapters.api.routes.my_data import (
    TAU_ATTESTED,
    TAU_ISOLATED,
    _community_grant_edge,
    _k_eff_terms,
    _lambda_from_wise_authority,
    _newest_community_trust_row,
    _occurrence_trust_edge,
    _probe_service_health,
    _reachable_peer_edge,
)

# ---------------------------------------------------------------------------
# _probe_service_health — evidence semantics
# ---------------------------------------------------------------------------


class _HealthyByMethod:
    def is_healthy(self) -> bool:
        return True


class _UnhealthyByMethod:
    def is_healthy(self) -> bool:
        return False


class _HealthyByAsyncMethod:
    async def is_healthy(self) -> bool:
        return True


class _HealthyByAttr:
    healthy = True


class _NoSurface:
    """No is_healthy / healthy at all — unmeasurable, NOT healthy."""


class _RaisingProbe:
    def is_healthy(self) -> bool:
        raise RuntimeError("probe blew up")


@pytest.mark.asyncio
async def test_probe_sync_method() -> None:
    assert await _probe_service_health(_HealthyByMethod()) is True
    assert await _probe_service_health(_UnhealthyByMethod()) is False


@pytest.mark.asyncio
async def test_probe_async_method() -> None:
    assert await _probe_service_health(_HealthyByAsyncMethod()) is True


@pytest.mark.asyncio
async def test_probe_attr_fallback() -> None:
    assert await _probe_service_health(_HealthyByAttr()) is True


@pytest.mark.asyncio
async def test_no_health_surface_is_unmeasurable_not_healthy() -> None:
    """The erroneous-1.0 root cause: this must be None, never True."""
    assert await _probe_service_health(_NoSurface()) is None


@pytest.mark.asyncio
async def test_raising_probe_is_evidence_of_unhealth() -> None:
    assert await _probe_service_health(_RaisingProbe()) is False


# ---------------------------------------------------------------------------
# _k_eff_terms — A2 form: correlation enters through k_eff
# ---------------------------------------------------------------------------


def test_k_eff_all_healthy() -> None:
    k_raw, rho_c, k_eff = _k_eff_terms(healthy=10, measurable=10)
    assert (k_raw, rho_c, k_eff) == (1.0, 1.0, 1.0)


def test_k_eff_single_failure_is_operational_variance() -> None:
    """One failure: ρ ≈ 0, k_eff = k_raw — no correlation discount."""
    k_raw, rho_c, k_eff = _k_eff_terms(healthy=9, measurable=10)
    assert k_raw == pytest.approx(0.9)
    assert rho_c == pytest.approx(1.0)
    assert k_eff == pytest.approx(0.9)


def test_k_eff_mass_failure_is_correlated_stress() -> None:
    """All failing simultaneously: ρ → 1, k_eff collapses."""
    k_raw, rho_c, k_eff = _k_eff_terms(healthy=0, measurable=10)
    assert k_raw == 0.0
    assert rho_c == pytest.approx(0.0)
    assert k_eff == 0.0


def test_k_eff_partial_correlated_failures() -> None:
    k_raw, rho_c, k_eff = _k_eff_terms(healthy=5, measurable=10)
    assert k_raw == pytest.approx(0.5)
    # failures=5 → ρ = (5-1)/(10-1) = 4/9
    assert rho_c == pytest.approx(1.0 - 4 / 9)
    assert k_eff == pytest.approx(0.5 * (1.0 - 4 / 9))


def test_k_eff_zero_measurable() -> None:
    assert _k_eff_terms(healthy=0, measurable=0) == (0.0, 1.0, 0.0)


def test_k_eff_single_measurable_no_rho() -> None:
    k_raw, rho_c, k_eff = _k_eff_terms(healthy=0, measurable=1)
    assert rho_c == 1.0
    assert k_eff == 0.0


# ---------------------------------------------------------------------------
# _lambda_from_wise_authority
# ---------------------------------------------------------------------------


class _WiseAuthorityService:
    service_name = "wise_authority"


class _OtherService:
    service_name = "telemetry"


def test_lambda_one_when_wa_healthy() -> None:
    services = [_OtherService(), _WiseAuthorityService()]
    assert _lambda_from_wise_authority(services, [True, True]) == 1.0


def test_lambda_degraded_when_wa_unhealthy() -> None:
    services = [_OtherService(), _WiseAuthorityService()]
    assert _lambda_from_wise_authority(services, [True, False]) == 0.7


def test_lambda_degraded_when_wa_absent() -> None:
    assert _lambda_from_wise_authority([_OtherService()], [True]) == 0.7


def test_lambda_matches_class_name() -> None:
    wa = MagicMock()
    type(wa).__name__ = "WiseAuthorityService"
    wa.service_name = ""
    assert _lambda_from_wise_authority([wa], [True]) == 1.0


# ---------------------------------------------------------------------------
# trust edge — τ semantics
# ---------------------------------------------------------------------------

_SENTINEL = "ciris:canonical-community:pending"


def _attestation_page(rows: list) -> str:
    return json.dumps({"items": rows})


def _row(att_type: str, user_id: str, asserted_at: str = "2026-06-12T00:00:00Z", att_id: str = "a1") -> dict:
    return {
        "attestation_type": att_type,
        "asserted_at": asserted_at,
        "attestation_id": att_id,
        "attestation_envelope": {
            "dimension": "consent:community_trust:v1",
            "claim": {"user_id": user_id},
        },
    }


def _engine_with(rows: list) -> Any:
    engine = MagicMock()
    engine.list_attestations.return_value = _attestation_page(rows)
    return engine


def test_newest_community_trust_row_newest_wins() -> None:
    rows = [
        _row("scores", "old", asserted_at="2026-06-01T00:00:00Z", att_id="a1"),
        _row("withdraws", "new", asserted_at="2026-06-10T00:00:00Z", att_id="a2"),
    ]
    newest = _newest_community_trust_row(_engine_with(rows), "key-1")
    assert newest is not None
    assert newest["attestation_type"] == "withdraws"


def test_newest_community_trust_row_filter_fallback() -> None:
    """If persist rejects the dimension filter, the unfiltered page is used."""
    engine = MagicMock()
    engine.list_attestations.side_effect = [
        Exception("federation_invalid_argument"),
        _attestation_page([_row("scores", "ciris:community")]),
    ]
    newest = _newest_community_trust_row(engine, "key-1")
    assert newest is not None
    assert engine.list_attestations.call_count == 2


def test_newest_community_trust_row_empty() -> None:
    assert _newest_community_trust_row(_engine_with([]), "key-1") is None


def _patched_grant_env(engine: Any, key_id: Optional[str] = "key-1"):
    return (
        patch("ciris_engine.logic.persistence.models.graph.get_persist_engine", return_value=engine),
        patch("ciris_engine.logic.runtime.edge_runtime.get_federation_address", return_value=key_id),
    )


def test_community_grant_edge_directed_grant_counts() -> None:
    p1, p2 = _patched_grant_env(_engine_with([_row("scores", "ciris:community")]))
    with p1, p2:
        assert _community_grant_edge() is True


def test_community_grant_edge_sentinel_is_not_an_edge() -> None:
    """The interim self-authored grant is precisely the solipsism τ discounts."""
    p1, p2 = _patched_grant_env(_engine_with([_row("scores", _SENTINEL)]))
    with p1, p2:
        assert _community_grant_edge() is False


def test_community_grant_edge_revocation_severs() -> None:
    rows = [
        _row("scores", "ciris:community", asserted_at="2026-06-01T00:00:00Z", att_id="a1"),
        _row("recants", "ciris:community", asserted_at="2026-06-10T00:00:00Z", att_id="a2"),
    ]
    p1, p2 = _patched_grant_env(_engine_with(rows))
    with p1, p2:
        assert _community_grant_edge() is False


def test_community_grant_edge_no_engine() -> None:
    p1, p2 = _patched_grant_env(None)
    with p1, p2:
        assert _community_grant_edge() is False


def test_reachable_peer_edge_via_list_peers() -> None:
    edge = MagicMock(spec=["list_peers"])
    edge.list_peers.return_value = ["peer-1"]
    with patch("ciris_engine.logic.runtime.edge_runtime.try_get_edge", return_value=edge):
        assert _reachable_peer_edge() is True


def test_reachable_peer_edge_via_metrics_snapshot() -> None:
    edge = MagicMock(spec=["metrics_snapshot"])
    edge.metrics_snapshot.return_value = {"peers": 2}
    with patch("ciris_engine.logic.runtime.edge_runtime.try_get_edge", return_value=edge):
        assert _reachable_peer_edge() is True


def test_reachable_peer_edge_zero_peers() -> None:
    edge = MagicMock(spec=["list_peers"])
    edge.list_peers.return_value = []
    with patch("ciris_engine.logic.runtime.edge_runtime.try_get_edge", return_value=edge):
        assert _reachable_peer_edge() is False


def test_reachable_peer_edge_no_edge_runtime() -> None:
    with patch("ciris_engine.logic.runtime.edge_runtime.try_get_edge", return_value=None):
        assert _reachable_peer_edge() is False


def test_occurrence_trust_edge_prefers_community_grant() -> None:
    with patch("ciris_engine.logic.adapters.api.routes.my_data._community_grant_edge", return_value=True):
        assert _occurrence_trust_edge(MagicMock()) == (True, "community_grant")


def test_occurrence_trust_edge_falls_back_to_peer() -> None:
    with (
        patch("ciris_engine.logic.adapters.api.routes.my_data._community_grant_edge", return_value=False),
        patch("ciris_engine.logic.adapters.api.routes.my_data._reachable_peer_edge", return_value=True),
    ):
        assert _occurrence_trust_edge(MagicMock()) == (True, "peer")


def test_occurrence_trust_edge_isolated() -> None:
    with (
        patch("ciris_engine.logic.adapters.api.routes.my_data._community_grant_edge", return_value=False),
        patch("ciris_engine.logic.adapters.api.routes.my_data._reachable_peer_edge", return_value=False),
    ):
        assert _occurrence_trust_edge(MagicMock()) == (False, "none")


# ---------------------------------------------------------------------------
# J < 1.0 by construction
# ---------------------------------------------------------------------------


def test_tau_caps_keep_j_below_one() -> None:
    """Even a perfect occurrence (μ=k_eff=λ=σ=1) lands below 1.0 — a
    self-graded perfect score is definitionally a measurement error."""
    assert TAU_ATTESTED < 1.0
    assert TAU_ISOLATED < TAU_ATTESTED
    j_perfect = 1.0 * 1.0 * 1.0 * 1.0 * TAU_ATTESTED
    assert j_perfect < 1.0
