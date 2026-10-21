"""Every registered service must be health-checkable.

`check_provider_health` is tri-state: True healthy, False unhealthy, **None
unknown** — the provider exposes no `is_healthy()` and cannot be asked. Unknown
deliberately counts as NOT healthy (#943), because the aggregate test is
`healthy == total` and an unaskable provider counted as healthy is one that can
help manufacture a 100% score.

That default is right, and it makes a missing method expensive. Four adapter
services had none:

    AccordMetricsService    registered for wise_authority
    CIRISHostedToolService  registered for tool
    CIRISVerifyService      registered for tool
    WalletToolService       registered for tool

so a fully working Android agent sat at 15/19 healthy services — 0.789, just
under the 0.8 threshold — and reported overall status **critical**, with
`cognitive_state=work`, while answering messages and sealing traces. Nothing was
wrong with it. Four methods were missing.

The health check's own warning always said the fix: "have X inherit base_service
(or implement is_healthy()), or stop registering it as a Y provider." This test
makes the next omission fail here instead of showing up as an unexplained
"critical" in production.
"""

from __future__ import annotations

import importlib
import inspect

import pytest

# Adapter services registered into the service registry. A new registered
# adapter service belongs in this list.
REGISTERED_ADAPTER_SERVICES = [
    ("ciris_adapters.ciris_accord_metrics.services", "AccordMetricsService"),
    ("ciris_adapters.ciris_hosted_tools.services", "CIRISHostedToolService"),
    ("ciris_adapters.ciris_verify.service", "CIRISVerifyService"),
    ("ciris_adapters.wallet.tool_service", "WalletToolService"),
]


def _load(module_path: str, class_name: str) -> type:
    return getattr(importlib.import_module(module_path), class_name)


@pytest.mark.parametrize("module_path,class_name", REGISTERED_ADAPTER_SERVICES)
def test_service_exposes_is_healthy(module_path: str, class_name: str) -> None:
    """The exact `hasattr` probe check_provider_health performs."""
    cls = _load(module_path, class_name)
    assert hasattr(cls, "is_healthy"), (
        f"{class_name} is registered but exposes no is_healthy(), so it is counted as "
        f"NOT healthy on every poll and permanently drags its service group toward "
        f"degraded — this is what reported 'critical' on a working agent"
    )


@pytest.mark.parametrize("module_path,class_name", REGISTERED_ADAPTER_SERVICES)
def test_is_healthy_returns_a_bool_not_a_coroutine_of_none(
    module_path: str, class_name: str
) -> None:
    """Signature conformance: awaited or not, the answer must be a real bool."""
    cls = _load(module_path, class_name)
    fn = cls.is_healthy
    assert callable(fn)
    sig = inspect.signature(fn)
    assert list(sig.parameters)[:1] == ["self"], f"{class_name}.is_healthy must be a method"
    ret = sig.return_annotation
    assert ret in (bool, "bool", inspect.Signature.empty), (
        f"{class_name}.is_healthy should return bool, annotated {ret!r}"
    )


@pytest.mark.parametrize("module_path,class_name", REGISTERED_ADAPTER_SERVICES)
def test_is_healthy_reports_state_rather_than_a_constant(
    module_path: str, class_name: str
) -> None:
    """A method that always returns True is the unaskable case with extra steps.

    The point of asking is to get an answer that can be no. Reading the source is
    crude but catches the obvious regression — someone silencing this test with
    `return True`.
    """
    cls = _load(module_path, class_name)
    body = inspect.getsource(cls.is_healthy)
    # Strip the docstring so prose mentioning "True" doesn't count.
    doc = inspect.getdoc(cls.is_healthy) or ""
    code = body.replace(doc, "")
    assert "return True" not in code, (
        f"{class_name}.is_healthy returns a constant True — it can never report a "
        f"problem, which is indistinguishable from having no method at all"
    )


@pytest.mark.asyncio
async def test_an_unstarted_service_reports_unhealthy() -> None:
    """End to end on the one with the clearest lifecycle."""
    from ciris_adapters.wallet.tool_service import WalletToolService

    svc = WalletToolService.__new__(WalletToolService)
    svc._started = False
    svc._providers = {}
    assert await svc.is_healthy() is False

    svc._started = True
    assert await svc.is_healthy() is False, "started with zero providers is not healthy"

    svc._providers = {"p": object()}
    assert await svc.is_healthy() is True
