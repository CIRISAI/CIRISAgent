"""Shared fixtures for /v1/federation/* route tests.

Provides:
- ``FakeEdge``: a stand-in for the ``ciris_edge.Edge`` PyO3 object whose
  return shapes match the real surface documented in
  ``ciris_engine.schemas.runtime.federation_api``.
- ``temp_db`` / ``time_service`` / ``seeder``: persistence + seeder
  scaffolding mirroring ``test_node_code_api.py``.
- ``make_app``: stand up a FastAPI app with the federation router
  mounted, dependency overrides applied, and Edge swapped in via
  ``monkeypatch`` on ``edge_runtime``.
"""

from __future__ import annotations

import base64
import os
import secrets
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.dependencies.auth import (
    require_observer,
    require_system_admin,
)
from ciris_engine.logic.adapters.api.routes.federation import router as federation_router
from ciris_engine.logic.persistence.db import initialize_database
from ciris_engine.logic.runtime.bootstrap_peers import BootstrapPeerSeeder


def _observer_auth() -> object:
    return MagicMock(user_id="obs", role="OBSERVER")


def _admin_auth() -> object:
    return MagicMock(user_id="root", role="SYSTEM_ADMIN")


def _pk_b64() -> str:
    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")


class _StubTimeService:
    def __init__(self, frozen: Optional[datetime] = None) -> None:
        self._frozen = frozen or datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)
        self._tick = 0

    def now(self) -> datetime:
        self._tick += 1
        return self._frozen.replace(microsecond=self._tick)

    def now_iso(self) -> str:
        return self.now().isoformat()


class FakeEdge:
    """Test double for the ciris_edge.Edge PyO3 object.

    Records call args and returns canned values configured via
    ``set_*`` methods. Methods that aren't pre-configured raise the
    same error types the real Edge would (RuntimeError / ValueError).
    """

    def __init__(
        self,
        *,
        signer_key_id_value: str = "agent-localnode001",
        crate_version_value: str = "1.0.0",
        inline_text_subscriber_count_value: int = 0,
    ) -> None:
        self._signer_key_id = signer_key_id_value
        self._crate_version = crate_version_value
        self._inline_text_subscriber_count = inline_text_subscriber_count_value
        self._reachability: Dict[str, Any] = {}
        self._sas_words: Dict[str, List[str]] = {}
        self._sas_digits: Dict[str, str] = {}
        self._metrics: Dict[str, Any] = {}
        self._content: Dict[Tuple[str, str], Any] = {}
        self._signer_key_id_raises: Optional[BaseException] = None
        self._crate_version_raises: Optional[BaseException] = None
        self._metrics_raises: Optional[BaseException] = None
        self._fetch_raises: Optional[BaseException] = None
        self.calls: list[tuple[str, tuple, dict]] = []

    # -- configuration --------------------------------------------------
    def set_reachability(self, key_id: str, value: Any) -> None:
        self._reachability[key_id] = value

    def set_sas(self, key_id: str, words: List[str], digits: str) -> None:
        self._sas_words[key_id] = words
        self._sas_digits[key_id] = digits

    def set_metrics(self, value: Any) -> None:
        self._metrics = value

    def set_content(self, peer_key_id: str, sha256: str, value: Any) -> None:
        self._content[(peer_key_id, sha256)] = value

    def raise_metrics(self, exc: BaseException) -> None:
        self._metrics_raises = exc

    def raise_fetch(self, exc: BaseException) -> None:
        self._fetch_raises = exc

    # -- Edge surface ---------------------------------------------------
    def signer_key_id(self) -> str:
        self.calls.append(("signer_key_id", (), {}))
        if self._signer_key_id_raises:
            raise self._signer_key_id_raises
        return self._signer_key_id

    def crate_version(self) -> str:
        self.calls.append(("crate_version", (), {}))
        if self._crate_version_raises:
            raise self._crate_version_raises
        return self._crate_version

    def peer_reachability(self, key_id: str) -> Any:
        self.calls.append(("peer_reachability", (key_id,), {}))
        if key_id not in self._reachability:
            return {}
        v = self._reachability[key_id]
        if isinstance(v, BaseException):
            raise v
        return v

    def peer_sas(self, peer_key_id: str) -> Any:
        self.calls.append(("peer_sas", (peer_key_id,), {}))
        if peer_key_id not in self._sas_words:
            raise ValueError(f"unknown peer {peer_key_id}")
        return self._sas_words[peer_key_id]

    def peer_sas_digits(self, peer_key_id: str) -> str:
        self.calls.append(("peer_sas_digits", (peer_key_id,), {}))
        if peer_key_id not in self._sas_digits:
            raise ValueError(f"unknown peer {peer_key_id}")
        return self._sas_digits[peer_key_id]

    def metrics_snapshot(self) -> Any:
        self.calls.append(("metrics_snapshot", (), {}))
        if self._metrics_raises:
            raise self._metrics_raises
        return self._metrics

    def inline_text_subscriber_count(self) -> int:
        self.calls.append(("inline_text_subscriber_count", (), {}))
        return self._inline_text_subscriber_count

    def fetch_content(
        self, peer_key_id: str, sha256: str, timeout_ms: int = 30000
    ) -> Any:
        self.calls.append(
            ("fetch_content", (), {"peer_key_id": peer_key_id, "sha256": sha256, "timeout_ms": timeout_ms})
        )
        if self._fetch_raises:
            raise self._fetch_raises
        key = (peer_key_id, sha256)
        if key not in self._content:
            return {"kind": "content_miss", "reason": "not_held"}
        return self._content[key]


@pytest.fixture
def temp_db():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    initialize_database(db_path)
    yield db_path
    if os.path.exists(db_path):
        try:
            os.unlink(db_path)
        except OSError:
            pass


@pytest.fixture
def time_service() -> _StubTimeService:
    return _StubTimeService()


@pytest.fixture
def seeder(temp_db, time_service) -> BootstrapPeerSeeder:
    return BootstrapPeerSeeder(time_service=time_service, registry_fetch_url=None)


@pytest.fixture
def fake_edge() -> FakeEdge:
    return FakeEdge()


@pytest.fixture
def make_app(monkeypatch):
    """Factory that builds a FastAPI app with the federation router mounted.

    Patches ``edge_runtime.try_get_edge`` and ``get_edge`` to return the
    supplied edge (or None). Tests can pre-populate ``app.state.*``
    attributes for the seeder + identity overrides.
    """

    def _factory(
        *,
        edge: Any = None,
        seeder: Optional[BootstrapPeerSeeder] = None,
        time_service: Optional[_StubTimeService] = None,
        override_admin: bool = True,
        override_observer: bool = True,
    ) -> TestClient:
        # Patch on every module that imports try_get_edge directly.
        from ciris_engine.logic.adapters.api.routes.federation import (
            content as content_mod,
            identity as identity_mod,
            metrics as metrics_mod,
            peers as peers_mod,
            sas as sas_mod,
        )

        for mod in (content_mod, identity_mod, metrics_mod, peers_mod, sas_mod):
            monkeypatch.setattr(mod, "try_get_edge", lambda e=edge: e)

        app = FastAPI()
        app.include_router(federation_router, prefix="/v1")
        if time_service is not None:
            app.state.time_service = time_service
        if seeder is not None:
            app.state.bootstrap_peer_seeder = seeder
        if override_observer:
            app.dependency_overrides[require_observer] = _observer_auth
        if override_admin:
            app.dependency_overrides[require_system_admin] = _admin_auth
        return TestClient(app)

    return _factory


@pytest.fixture
def pk_b64():
    return _pk_b64


@pytest.fixture
def observer_auth():
    return _observer_auth


@pytest.fixture
def admin_auth():
    return _admin_auth
