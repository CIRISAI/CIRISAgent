"""Tests for the 2.7.8.1 storage_descriptor surfacing helpers in
verifier_singleton (issue #708 / CIRISVerify v1.8.0 coordination).

Why this exists:
The CIRISVerify v1.8.0 PoB substrate primitive `HardwareSigner.storage_descriptor()`
declares where the agent's identity seed lives. Surfacing it on /health and at
boot lets operators catch the canonical container-misconfiguration failure mode
where the keyring silently lands in ephemeral storage. These tests pin the
defensive accessor + boot-logging contract so a future refactor can't break
either surface silently.

The agent must run with ciris-verify <1.8.0 (descriptor not yet exposed) AND
ciris-verify >=1.8.0 (descriptor exposed) without surface failures — that's
the whole point of get_storage_descriptor() being best-effort. Tests cover
both shapes.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.logic.services.infrastructure.authentication import verifier_singleton
from ciris_engine.logic.services.infrastructure.authentication.verifier_singleton import (
    get_storage_descriptor,
    log_storage_descriptor_at_boot,
)


@pytest.fixture(autouse=True)
def reset_singleton_state():
    """Each test runs against a clean singleton — otherwise prior test verifiers leak through."""
    verifier_singleton.reset_verifier()
    yield
    verifier_singleton.reset_verifier()


class TestGetStorageDescriptorVersionGating:
    """The accessor must work across ciris-verify versions: pre-1.8 (no method),
    1.8 with method-returning-dict, 1.8 with method-returning-pydantic, and
    method-raises (transient FFI failure)."""

    def test_returns_none_when_no_verifier_initialized(self):
        """No singleton → no descriptor. Don't try to fabricate one."""
        # reset_singleton_state fixture leaves _verifier=None
        assert get_storage_descriptor() is None

    def test_returns_none_for_pre_1_8_library_no_method(self):
        """ciris-verify <1.8.0 doesn't expose storage_descriptor at all.
        getattr returns None; accessor falls through cleanly."""
        # Mock object with NO storage_descriptor attribute
        mock_verifier = MagicMock(spec=[])  # spec=[] → no attrs allowed
        verifier_singleton._verifier = mock_verifier

        assert get_storage_descriptor() is None

    def test_returns_dict_when_method_returns_dict(self):
        """v1.8.0 dict return shape — pass through unchanged."""
        mock_verifier = MagicMock()
        mock_verifier.storage_descriptor.return_value = {
            "path": "/var/lib/ciris-agent/keyring/agent.key",
            "signer_type": "ed25519",
            "hardware_backed": False,
        }
        verifier_singleton._verifier = mock_verifier

        result = get_storage_descriptor()
        assert result == {
            "path": "/var/lib/ciris-agent/keyring/agent.key",
            "signer_type": "ed25519",
            "hardware_backed": False,
        }

    def test_normalizes_pydantic_return_via_model_dump(self):
        """If the FFI returns a Pydantic model (or anything with model_dump),
        normalize to dict for /health consistency."""
        mock_descriptor = MagicMock()
        mock_descriptor.model_dump.return_value = {"path": "/data/keyring.bin", "kind": "file"}
        # Strip any other attrs that might confuse the dict-detection path
        del mock_descriptor.__dict__

        mock_verifier = MagicMock()
        mock_verifier.storage_descriptor.return_value = mock_descriptor
        verifier_singleton._verifier = mock_verifier

        result = get_storage_descriptor()
        assert result == {"path": "/data/keyring.bin", "kind": "file"}

    def test_normalizes_object_with_dict_attribute(self):
        """If the FFI returns a plain object, prefer __dict__ (filtered)."""

        class _Descriptor:
            def __init__(self):
                self.path = "/data/k.key"
                self.kind = "file"
                self._private = "skip"

        mock_verifier = MagicMock()
        mock_verifier.storage_descriptor.return_value = _Descriptor()
        verifier_singleton._verifier = mock_verifier

        result = get_storage_descriptor()
        assert result is not None
        assert result["path"] == "/data/k.key"
        assert result["kind"] == "file"
        # Underscore-prefixed attrs are filtered out
        assert "_private" not in result

    def test_normalizes_string_return_to_value_dict(self):
        """If the FFI returns a bare string (just the path), wrap it so
        downstream consumers can rely on dict shape."""
        mock_verifier = MagicMock()
        mock_verifier.storage_descriptor.return_value = "/var/lib/ciris/keyring.bin"
        verifier_singleton._verifier = mock_verifier

        result = get_storage_descriptor()
        assert result == {"value": "/var/lib/ciris/keyring.bin"}

    def test_falls_through_when_method_raises(self):
        """Transient FFI failure during descriptor() call must not propagate.
        Boot-time logging callers depend on this."""
        # spec= constrains the mock so the get_storage_descriptor fallback
        # doesn't auto-create a passing alias.
        mock_verifier = MagicMock(spec=["storage_descriptor"])
        mock_verifier.storage_descriptor.side_effect = RuntimeError("FFI hiccup")
        verifier_singleton._verifier = mock_verifier

        # MUST NOT raise
        assert get_storage_descriptor() is None

    def test_falls_back_to_get_storage_descriptor_alias(self):
        """If the FFI binding exposes get_storage_descriptor (older naming
        convention) instead of storage_descriptor, the accessor finds it."""
        mock_verifier = MagicMock(spec=["get_storage_descriptor"])
        mock_verifier.get_storage_descriptor = MagicMock(return_value={"path": "/foo"})
        verifier_singleton._verifier = mock_verifier

        result = get_storage_descriptor()
        assert result == {"path": "/foo"}


class TestLogStorageDescriptorAtBoot:
    """Boot-time logging contract: log at WARNING when descriptor available,
    log at DEBUG when unavailable, log at ERROR when path looks ephemeral
    without explicit override."""

    def test_silent_at_debug_when_descriptor_unavailable(self, caplog):
        """Pre-1.8 library: don't shout. The feature is opt-in."""
        # No verifier initialized
        with caplog.at_level(logging.DEBUG, logger=verifier_singleton.__name__):
            log_storage_descriptor_at_boot()

        # Some logger framework produces messages even when no records emit;
        # filter to the specific logger.
        messages = [r.message for r in caplog.records if r.name == verifier_singleton.__name__]
        # The "unavailable" debug message should be the only one
        assert any("storage_descriptor() unavailable" in m for m in messages)
        # No WARNING or ERROR
        assert not any(r.levelno >= logging.WARNING for r in caplog.records if r.name == verifier_singleton.__name__)

    def test_logs_at_warning_for_persistent_path(self, caplog):
        """Persistent path → single WARNING-level surfacing line."""
        mock_verifier = MagicMock()
        mock_verifier.storage_descriptor.return_value = {
            "path": "/var/lib/ciris-agent/keyring/agent.key",
            "signer_type": "ed25519",
        }
        verifier_singleton._verifier = mock_verifier

        with caplog.at_level(logging.DEBUG, logger=verifier_singleton.__name__):
            log_storage_descriptor_at_boot()

        warnings = [r for r in caplog.records if r.name == verifier_singleton.__name__ and r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "storage descriptor" in warnings[0].message.lower()
        # Persistent path must NOT trigger ephemeral ERROR
        errors = [r for r in caplog.records if r.name == verifier_singleton.__name__ and r.levelno == logging.ERROR]
        assert not errors, f"Persistent path /var/lib should not trigger ephemeral warning: {errors}"

    def test_logs_error_for_ephemeral_tmp_path(self, caplog):
        """/tmp/ → ephemeral → ERROR-level warning."""
        mock_verifier = MagicMock()
        mock_verifier.storage_descriptor.return_value = {"path": "/tmp/keyring.bin"}
        verifier_singleton._verifier = mock_verifier

        with caplog.at_level(logging.DEBUG, logger=verifier_singleton.__name__):
            log_storage_descriptor_at_boot()

        errors = [r for r in caplog.records if r.name == verifier_singleton.__name__ and r.levelno == logging.ERROR]
        assert len(errors) == 1
        assert "ephemeral" in errors[0].message.lower()
        assert "CIRIS_PERSIST_KEYRING_PATH_OK" in errors[0].message

    def test_logs_error_for_docker_overlay_path(self, caplog):
        """/var/lib/docker → also ephemeral. The container-misconfig case."""
        mock_verifier = MagicMock()
        mock_verifier.storage_descriptor.return_value = {
            "path": "/var/lib/docker/overlay2/abc123/diff/keyring.bin"
        }
        verifier_singleton._verifier = mock_verifier

        with caplog.at_level(logging.DEBUG, logger=verifier_singleton.__name__):
            log_storage_descriptor_at_boot()

        errors = [r for r in caplog.records if r.name == verifier_singleton.__name__ and r.levelno == logging.ERROR]
        assert len(errors) == 1

    def test_override_acknowledges_ephemeral_path(self, caplog, monkeypatch):
        """CIRIS_PERSIST_KEYRING_PATH_OK=1 → explicit operator acknowledgment.
        Drop the ERROR; emit an INFO instead so audit trails still see it."""
        mock_verifier = MagicMock()
        mock_verifier.storage_descriptor.return_value = {"path": "/tmp/keyring.bin"}
        verifier_singleton._verifier = mock_verifier
        monkeypatch.setenv("CIRIS_PERSIST_KEYRING_PATH_OK", "1")

        with caplog.at_level(logging.DEBUG, logger=verifier_singleton.__name__):
            log_storage_descriptor_at_boot()

        errors = [r for r in caplog.records if r.name == verifier_singleton.__name__ and r.levelno == logging.ERROR]
        assert not errors, f"Override should suppress ERROR: {errors}"
        infos = [r for r in caplog.records if r.name == verifier_singleton.__name__ and r.levelno == logging.INFO]
        assert any("CIRIS_PERSIST_KEYRING_PATH_OK=1" in r.message for r in infos)

    def test_no_path_field_skips_ephemeral_check(self, caplog):
        """Descriptor without a path-shaped field → log it, don't run heuristics."""
        mock_verifier = MagicMock()
        mock_verifier.storage_descriptor.return_value = {
            "signer_type": "tpm",
            "hardware_backed": True,
            # No path/keyring_path/value field
        }
        verifier_singleton._verifier = mock_verifier

        with caplog.at_level(logging.DEBUG, logger=verifier_singleton.__name__):
            log_storage_descriptor_at_boot()

        warnings = [r for r in caplog.records if r.name == verifier_singleton.__name__ and r.levelno == logging.WARNING]
        assert len(warnings) == 1
        # No ERROR even though path-check would have skipped
        errors = [r for r in caplog.records if r.name == verifier_singleton.__name__ and r.levelno == logging.ERROR]
        assert not errors


class TestHealthEndpointSurfacing:
    """The /health endpoint must include storage_descriptor when available
    and OMIT it (not return null) when not.

    /health is registered inside `_add_api_root_endpoint` (the API-only /
    managed-mode root helper). Tests build a fresh FastAPI app + call the
    helper directly — avoids GUI-mount routing collisions in the test env.
    """

    def _make_app_with_health(self):
        """Build a fresh FastAPI app with just the /health endpoint we added."""
        from fastapi import FastAPI

        from ciris_engine.logic.adapters.api.app import _add_api_root_endpoint

        app = FastAPI()
        _add_api_root_endpoint(app, "test", "test mode")
        return app

    def test_health_omits_descriptor_when_not_initialized(self):
        """Pre-1.8 / no verifier → field is absent from payload (smaller wire format)."""
        from fastapi.testclient import TestClient

        # No verifier set; reset_singleton_state fixture leaves it None
        app = self._make_app_with_health()
        with TestClient(app) as client:
            r = client.get("/health")
            assert r.status_code == 200
            payload = r.json()
            assert payload["status"] == "ok"
            # Descriptor field absent (None means accessor returned None → field omitted)
            assert "storage_descriptor" not in payload

    def test_health_includes_descriptor_when_singleton_has_it(self):
        """When the singleton produces a descriptor, /health surfaces it."""
        mock_verifier = MagicMock(spec=["storage_descriptor"])
        mock_verifier.storage_descriptor.return_value = {
            "path": "/var/lib/ciris-agent/keyring/agent.key",
            "signer_type": "ed25519",
        }
        verifier_singleton._verifier = mock_verifier

        from fastapi.testclient import TestClient

        app = self._make_app_with_health()
        with TestClient(app) as client:
            r = client.get("/health")
            assert r.status_code == 200
            payload = r.json()
            # Descriptor must be passed through
            assert "storage_descriptor" in payload
            assert payload["storage_descriptor"]["path"] == "/var/lib/ciris-agent/keyring/agent.key"
            assert payload["storage_descriptor"]["signer_type"] == "ed25519"

    def test_health_does_not_500_when_accessor_raises(self, monkeypatch):
        """Even a totally broken accessor must not break /health.
        Operators rely on /health for liveness probes."""

        def _broken():
            raise RuntimeError("totally broken")

        monkeypatch.setattr(
            "ciris_engine.logic.services.infrastructure.authentication.verifier_singleton.get_storage_descriptor",
            _broken,
        )

        from fastapi.testclient import TestClient

        app = self._make_app_with_health()
        with TestClient(app) as client:
            r = client.get("/health")
            # MUST be 200, not 500
            assert r.status_code == 200
            assert r.json()["status"] == "ok"
            # And must omit the descriptor field
            assert "storage_descriptor" not in r.json()


class TestNormalizeDescriptor:
    """Direct unit tests for the `_normalize_descriptor` helper extracted in
    2.7.8.x to drop the cognitive-complexity of `get_storage_descriptor`. Each
    branch (None, dict, model_dump, __dict__, scalar) must produce the
    documented return shape."""

    def test_none_returns_none(self):
        from ciris_engine.logic.services.infrastructure.authentication.verifier_singleton import (
            _normalize_descriptor,
        )

        assert _normalize_descriptor(None) is None

    def test_dict_returns_dict_unchanged(self):
        from ciris_engine.logic.services.infrastructure.authentication.verifier_singleton import (
            _normalize_descriptor,
        )

        d = {"path": "/x", "signer_type": "ed25519"}
        assert _normalize_descriptor(d) == d

    def test_pydantic_like_uses_model_dump(self):
        """If the FFI returns something with `.model_dump()`, prefer that."""
        from ciris_engine.logic.services.infrastructure.authentication.verifier_singleton import (
            _normalize_descriptor,
        )

        class _PydanticLike:
            def model_dump(self):
                return {"path": "/from/model_dump", "kind": "file"}

        result = _normalize_descriptor(_PydanticLike())
        assert result == {"path": "/from/model_dump", "kind": "file"}

    def test_pydantic_model_dump_failure_falls_through(self):
        """If model_dump() raises, fall through to __dict__ extraction."""
        from ciris_engine.logic.services.infrastructure.authentication.verifier_singleton import (
            _normalize_descriptor,
        )

        class _PydanticBroken:
            def __init__(self):
                self.path = "/from/dict_attr"

            def model_dump(self):
                raise RuntimeError("model_dump broken")

        result = _normalize_descriptor(_PydanticBroken())
        assert result is not None
        # Falls through to __dict__ branch
        assert result["path"] == "/from/dict_attr"

    def test_object_with_dict_attr_uses_filtered_dict(self):
        """Plain object → filtered __dict__ (drops underscore-prefixed)."""
        from ciris_engine.logic.services.infrastructure.authentication.verifier_singleton import (
            _normalize_descriptor,
        )

        class _Plain:
            def __init__(self):
                self.path = "/data/k.key"
                self._private = "filtered_out"

        result = _normalize_descriptor(_Plain())
        assert result == {"path": "/data/k.key"}

    def test_scalar_path_string_wraps_to_value_dict(self):
        """Bare string from the FFI → wrapped as {'value': ...}."""
        from ciris_engine.logic.services.infrastructure.authentication.verifier_singleton import (
            _normalize_descriptor,
        )

        assert _normalize_descriptor("/var/lib/ciris/keyring.bin") == {
            "value": "/var/lib/ciris/keyring.bin"
        }

    def test_scalar_int_wraps_via_str(self):
        """Defensive: even a non-string scalar gets stringified into the
        wrapper so callers always see Dict[str, str|...] keyed by 'value'."""
        from ciris_engine.logic.services.infrastructure.authentication.verifier_singleton import (
            _normalize_descriptor,
        )

        assert _normalize_descriptor(42) == {"value": "42"}


class TestGetStorageDescriptorReturnsNoneForCallableNone:
    """Edge case: the verifier method exists, returns None, and the
    accessor must propagate None back. Covers the post-method None branch."""

    def test_method_returns_none_propagates(self):
        from ciris_engine.logic.services.infrastructure.authentication import verifier_singleton
        from ciris_engine.logic.services.infrastructure.authentication.verifier_singleton import (
            get_storage_descriptor,
        )

        verifier_singleton.reset_verifier()
        mock_verifier = MagicMock()
        mock_verifier.storage_descriptor.return_value = None
        verifier_singleton._verifier = mock_verifier

        try:
            assert get_storage_descriptor() is None
        finally:
            verifier_singleton.reset_verifier()
