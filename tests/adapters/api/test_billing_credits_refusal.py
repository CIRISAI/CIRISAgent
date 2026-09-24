"""GET /v1/billing/credits — a failed check is not a balance.

The incident: a desktop client whose one-hour Google ID token had expired 25
hours earlier showed "0 credits" and blocked every send, while the account held
398 the whole time. Billing said 401 (correct). The agent wrote the
token-refresh signal (correct) and then answered HTTP 200 with
has_credit=false, credits_remaining=0, purchase_required=true — the same shape
as a genuinely empty account. The client has a 401-handling branch that
refreshes and retries; it never ran, because it never saw a 401.

These tests pin the status the route now returns for each category of
non-answer, and bind the route's classifier to the provider's real reason
strings so a rename on either side fails a test instead of silently
re-opening the hole.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import HTTPException

from ciris_engine.logic.adapters.api.routes.billing import _refusal_for_non_answer, get_credits
from ciris_engine.logic.services.infrastructure.resource_monitor.ciris_billing_provider import CIRISBillingProvider
from ciris_engine.schemas.api.auth import AuthContext, UserRole
from ciris_engine.schemas.services.credit_gate import CreditCheckResult


@pytest.fixture
def auth():
    a = Mock(spec=AuthContext)
    a.user_id = "user-123"
    a.role = UserRole.OBSERVER
    a.api_key_id = None
    return a


def _jwt_mode_request(result: CreditCheckResult) -> Mock:
    """A request wired to a CIRISBillingProvider in JWT mode returning `result`."""
    request = Mock()
    request.app.state = Mock()
    request.app.state.auth_service = None
    request.app.state.runtime = Mock()
    request.app.state.runtime.agent_identity.agent_id = "test-agent"
    monitor = Mock()
    monitor.credit_provider = Mock()
    monitor.credit_provider.__class__.__name__ = "CIRISBillingProvider"
    monitor.check_credit = AsyncMock(return_value=result)
    request.app.state.resource_monitor = monitor
    return request


async def _call(auth, result: CreditCheckResult):
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("CIRIS_BILLING_API_KEY", raising=False)
        return await get_credits(_jwt_mode_request(result), auth)


# --- the classifier -------------------------------------------------------


def test_auth_expired_is_401_and_carries_the_reason():
    r = _refusal_for_non_answer(CreditCheckResult(has_credit=False, reason="the billing session expired (AUTH_EXPIRED: token expired)", provider_metadata={"error_category": "AUTH_EXPIRED"}))
    assert isinstance(r, HTTPException) and r.status_code == 401
    assert r.detail["error"] == "billing_auth_expired"
    assert "AUTH_EXPIRED" in r.detail["reason"], "the client needs the category to be visible"


@pytest.mark.parametrize("category", ["TIMEOUT", "CONNECTION_ERROR", "NETWORK_ERROR", "HTTP_502"])
def test_billing_unreachable_is_503_not_an_empty_wallet(category):
    r = _refusal_for_non_answer(
        CreditCheckResult(has_credit=False, reason="(human text)", provider_metadata={"error_category": category})
    )
    assert isinstance(r, HTTPException) and r.status_code == 503
    assert r.detail["error"] == "billing_unavailable"


def test_a_genuine_zero_is_still_a_balance():
    """NO_CREDITS is billing's real answer. It must keep rendering as one."""
    r = CreditCheckResult(has_credit=False, reason="NO_CREDITS:exhausted", provider_metadata={"error_category": "NO_CREDITS"})
    assert _refusal_for_non_answer(r) is None


def test_the_prose_is_not_parsed():
    """A result whose SENTENCE mentions AUTH_EXPIRED but carries no category is
    not refused — the wording must never be load-bearing."""
    r = CreditCheckResult(has_credit=False, reason="the billing session expired (AUTH_EXPIRED: token expired)")
    assert _refusal_for_non_answer(r) is None


def test_no_reason_at_all_is_treated_as_a_real_answer():
    """Older providers set no reason; do not start refusing them."""
    assert _refusal_for_non_answer(CreditCheckResult(has_credit=False)) is None


def test_fail_open_is_never_refused():
    """fail_open=True answers has_credit=True with a FAIL_OPEN: reason — a pass, not a failure."""
    r = CreditCheckResult(has_credit=True, reason="FAIL_OPEN:...", provider_metadata={"error_category": "AUTH_EXPIRED"})
    assert _refusal_for_non_answer(r) is None


# --- bound to the provider's real strings ---------------------------------


def _quiet_provider(monkeypatch) -> CIRISBillingProvider:
    p = CIRISBillingProvider(google_id_token="x" * 32, base_url="http://billing.invalid", fail_open=False)
    # The 401 path writes the token-refresh signal into CIRIS_HOME; keep the test off the disk.
    monkeypatch.setattr(p, "_signal_token_refresh_needed", lambda: None)
    return p


def test_the_providers_401_result_is_what_the_route_refuses(monkeypatch):
    """Bind the two ends: whatever the provider emits for a 401 must be a 401 here.

    Constructed from the provider's own handler, not a hand-written string, so
    renaming the category upstream of the route breaks this test rather than
    quietly turning expired tokens back into zero balances.
    """
    p = _quiet_provider(monkeypatch)
    resp = httpx.Response(401, json={"detail": "token expired"}, request=httpx.Request("POST", "http://x"))
    result = p._handle_check_unauthorized(resp, "api:user:anon")
    assert result.has_credit is False
    refusal = _refusal_for_non_answer(result)
    assert refusal is not None and refusal.status_code == 401


def test_the_providers_no_credits_result_is_not_refused(monkeypatch):
    p = _quiet_provider(monkeypatch)
    resp = httpx.Response(402, json={"detail": "no credits"}, request=httpx.Request("POST", "http://x"))
    result = p._handle_check_no_credits(resp, "api:user:anon")
    assert result.has_credit is False
    assert _refusal_for_non_answer(result) is None


# --- through the route ----------------------------------------------------


@pytest.mark.asyncio
async def test_route_401_on_expired_token(auth):
    """The incident, end to end at the route: expired token → 401, not 200/zeros."""
    with pytest.raises(HTTPException) as exc:
        await _call(auth, CreditCheckResult(has_credit=False, reason="the billing session expired (AUTH_EXPIRED: token expired)", provider_metadata={"error_category": "AUTH_EXPIRED"}))
    assert exc.value.status_code == 401
    assert exc.value.detail["error"] == "billing_auth_expired"
    assert "AUTH_EXPIRED" in exc.value.detail["reason"]


@pytest.mark.asyncio
async def test_route_503_when_billing_is_down(auth):
    with pytest.raises(HTTPException) as exc:
        await _call(auth, CreditCheckResult(has_credit=False, reason="(human)", provider_metadata={"error_category": "TIMEOUT"}))
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_route_still_renders_a_real_empty_account(auth):
    """The one case that SHOULD look like an empty wallet still does."""
    resp = await _call(auth, CreditCheckResult(has_credit=False, reason="no credits available (NO_CREDITS)", provider_metadata={"error_category": "NO_CREDITS"}))
    assert resp.has_credit is False
    assert resp.credits_remaining == 0
    assert resp.purchase_required is True
    assert resp.plan_name == "CIRIS Mobile"


@pytest.mark.asyncio
async def test_route_renders_a_real_balance_unchanged(auth):
    resp = await _call(auth, CreditCheckResult(has_credit=True, credits_remaining=398, free_uses_remaining=0))
    assert resp.has_credit is True
    assert resp.credits_remaining == 398
