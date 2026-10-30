"""ASPDMA writes the reply in the thought's language, not the deployment's (2.18.0).

ASPDMA read CIRIS_PREFERRED_LANGUAGE for its language guidance and crisis block,
while IDMA, DSDMA, DSASPDMA and the consciences resolved the thought's own
language. A bn user on a deployment without that variable got English guidance
and English crisis numbers in the one step that writes the reply, while
coherence judged the reply against bn (bn battery q04/q06/q07).
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from ciris_engine.logic.dma.action_selection_pdma import ActionSelectionPDMAEvaluator


@pytest.fixture(autouse=True)
def _english_deployment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIRIS_PREFERRED_LANGUAGE", "en")


def _context(*profile_langs: str) -> SimpleNamespace:
    return SimpleNamespace(
        system_snapshot=SimpleNamespace(user_profiles=[{"preferred_language": lang} for lang in profile_langs])
    )


def test_the_users_profile_language_outranks_the_deployment() -> None:
    thought = SimpleNamespace(preferred_language=None, context=None)
    assert ActionSelectionPDMAEvaluator._working_language(thought, _context("bn")) == "bn"


def test_the_thoughts_own_language_outranks_the_profile() -> None:
    thought = SimpleNamespace(preferred_language="am", context=None)
    assert ActionSelectionPDMAEvaluator._working_language(thought, _context("bn")) == "am"


def test_with_nothing_on_the_thought_or_profile_the_deployment_decides() -> None:
    thought = SimpleNamespace(preferred_language=None, context=None)
    assert ActionSelectionPDMAEvaluator._working_language(thought, None) == "en"


def test_compose_messages_does_not_read_the_deployment_language() -> None:
    source = inspect.getsource(ActionSelectionPDMAEvaluator.compose_messages)
    assert "get_preferred_language" not in source
    assert "_working_language" in source
