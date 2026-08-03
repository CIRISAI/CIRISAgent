"""The agent's wallet context block is actually produced.

``_get_wallet_summary`` looked the wallet adapter up through
``service_registry.get_service(ServiceType.TOOL)`` — an ``async def`` called
WITHOUT ``await`` and with the service type passed as the ``handler``
positional. Against a real ServiceRegistry that raises TypeError at bind time,
which the caller swallowed into ``logger.debug``. The predicate underneath was
fabricated too: no tool service exposes an ``_adapters`` map, and WalletAdapter
has no ``provider_id`` attribute. So this block was never produced for any
thought, on any deployment, ever.

The adapter is discovered off ``runtime.adapters`` now — the same seam the live
API route uses (``routes/wallet.py:_get_wallet_adapter_from_app``).
"""

import inspect
from decimal import Decimal
from typing import Any, Dict, List, Optional

import pytest

from ciris_engine.logic.context.batch_context import _get_wallet_summary


class _Balance:
    def __init__(self, available: Decimal, currency: str) -> None:
        self.available = available
        self.currency = currency


class _Account:
    def __init__(self, network: str) -> None:
        self.network = network


class _Provider:
    def __init__(self, available: str, currency: str, network: str, receive_only: bool = False) -> None:
        self._available = Decimal(available)
        self._currency = currency
        self._network = network
        self._receive_only = receive_only

    async def get_balance(self) -> _Balance:
        return _Balance(self._available, self._currency)

    async def get_account_details(self) -> _Account:
        return _Account(self._network)


class WalletAdapter:
    """Stands in for ciris_adapters.wallet.adapter.WalletAdapter by NAME.

    Discovery is by class name, so the name here is load-bearing.
    """

    def __init__(self, providers: Optional[Dict[str, Any]] = None) -> None:
        self._providers: Dict[str, Any] = providers if providers is not None else {}


class _OtherAdapter:
    def __init__(self) -> None:
        self._providers = {"x402": _Provider("999.00", "USDC", "should-not-be-read")}


class _Runtime:
    def __init__(self, adapters: Optional[List[Any]] = None) -> None:
        self.adapters = adapters if adapters is not None else []


class _ExplodingRegistry:
    """A ServiceRegistry stand-in that fails loudly if anyone reaches for it."""

    def get_service(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("_get_wallet_summary must not route through the service registry")


@pytest.mark.asyncio
async def test_summary_is_produced_from_runtime_adapters() -> None:
    runtime = _Runtime([_OtherAdapter(), WalletAdapter({"x402": _Provider("100.50", "USDC", "base-sepolia")})])

    summary = await _get_wallet_summary(runtime)

    assert summary is not None, "the wallet context block was not produced"
    assert "x402/USDC" in summary
    assert "100.50" in summary
    assert "base-sepolia" in summary


@pytest.mark.asyncio
async def test_receive_only_provider_is_marked() -> None:
    runtime = _Runtime([WalletAdapter({"pix": _Provider("12.00", "BRL", "pix", receive_only=True)})])

    summary = await _get_wallet_summary(runtime)

    assert summary is not None
    assert "(Recv Only)" in summary


@pytest.mark.asyncio
async def test_configured_adapter_with_no_providers_says_so() -> None:
    runtime = _Runtime([WalletAdapter({})])

    assert await _get_wallet_summary(runtime) == "💰 Wallet: Not configured"


@pytest.mark.asyncio
async def test_no_wallet_adapter_returns_none() -> None:
    assert await _get_wallet_summary(_Runtime([_OtherAdapter()])) is None
    assert await _get_wallet_summary(_Runtime([])) is None
    assert await _get_wallet_summary(None) is None


@pytest.mark.asyncio
async def test_runtime_without_adapters_attribute_is_tolerated() -> None:
    class _Bare:
        pass

    assert await _get_wallet_summary(_Bare()) is None


@pytest.mark.asyncio
async def test_a_failing_provider_does_not_sink_the_others() -> None:
    class _BrokenProvider:
        async def get_balance(self) -> _Balance:
            raise RuntimeError("rpc down")

        async def get_account_details(self) -> _Account:  # pragma: no cover - never reached
            raise RuntimeError("rpc down")

    providers = {"broken": _BrokenProvider(), "x402": _Provider("5.00", "USDC", "base-mainnet")}
    runtime = _Runtime([WalletAdapter(providers)])

    summary = await _get_wallet_summary(runtime)
    assert summary is not None
    assert "x402/USDC" in summary
    assert "broken" not in summary


@pytest.mark.asyncio
async def test_every_provider_failing_reports_no_balance() -> None:
    class _BrokenProvider:
        async def get_balance(self) -> _Balance:
            raise RuntimeError("rpc down")

    runtime = _Runtime([WalletAdapter({"broken": _BrokenProvider()})])

    assert await _get_wallet_summary(runtime) == "💰 Wallet: No balance available"


def test_signature_takes_runtime_not_service_registry() -> None:
    """Guard the seam: the registry lookup was the defect, not an implementation detail."""
    params = list(inspect.signature(_get_wallet_summary).parameters)
    assert params == ["runtime"], f"unexpected signature {params}"


@pytest.mark.asyncio
async def test_does_not_reach_for_the_service_registry() -> None:
    """Negative control: passing a registry-shaped object must not call get_service."""
    summary = await _get_wallet_summary(_ExplodingRegistry())
    assert summary is None
