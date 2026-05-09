"""Coverage for the platform branch + tree_verify overlay in ``verifier_runner``.

Exercises ``create_verification_thread_target`` end-to-end via the same
thread invocation production uses, with the verifier + paths + hash/tree
helpers all stubbed at the module boundary.
"""
from __future__ import annotations

import threading
from typing import Any, Dict
from unittest.mock import MagicMock, patch

from ciris_engine.logic.services.infrastructure.authentication.attestation import verifier_runner
from ciris_engine.logic.services.infrastructure.authentication.attestation.types import (
    PythonHashesWrapper,
    VerifyThreadResult,
)


def _stub_verifier(attestation_data: Dict[str, Any]) -> MagicMock:
    """A verifier whose run_attestation_sync returns the supplied dict."""
    verifier = MagicMock()
    verifier.run_attestation_sync = MagicMock(return_value=attestation_data)
    verifier.verify_audit_trail_sync = MagicMock(return_value=None)
    verifier.version = "1.13.2"
    return verifier


def _run_thread_target(target_fn) -> None:
    t = threading.Thread(target=target_fn)
    t.start()
    t.join(timeout=10)
    assert not t.is_alive(), "thread target did not complete in 10s"


def test_desktop_path_uses_tree_verify_and_overlays_python_integrity():
    """Non-mobile → run_tree_verify is called, python_integrity overlay applied."""
    base_attestation = {"level": 3, "valid": True, "python_integrity": {"valid": False, "stub": "old"}}
    tree_overlay = {
        "valid": True,
        "modules_checked": 100,
        "modules_passed": 100,
        "registry_match": True,
        "algorithm": "A",
    }
    container = VerifyThreadResult()

    with patch.object(verifier_runner, "is_mobile", return_value=False), patch.object(
        verifier_runner, "get_default_agent_version", return_value="2.8.6"
    ), patch.object(verifier_runner, "run_tree_verify", return_value=tree_overlay) as mock_tree, patch.object(
        verifier_runner, "load_python_hashes"
    ) as mock_load, patch.object(
        verifier_runner, "get_agent_root", return_value="/app"
    ), patch.object(
        verifier_runner, "get_ed25519_fingerprint", return_value="fp"
    ), patch.object(
        verifier_runner, "find_audit_db_path", return_value=None
    ):
        target = verifier_runner.create_verification_thread_target(
            get_verifier=lambda: _stub_verifier(base_attestation),
            attestation_mode="full",
            result_container=container,
        )
        _run_thread_target(target)

    # Algorithm A path was taken, Algorithm B path was NOT.
    mock_tree.assert_called_once_with(agent_version="2.8.6")
    mock_load.assert_not_called()

    # python_integrity has been overlaid with the tree_verify result.
    assert container.error is None, container.error
    assert container.result is not None
    attestation = container.result["attestation"]
    assert attestation["python_integrity"] == tree_overlay
    assert attestation["python_integrity"]["algorithm"] == "A"


def test_mobile_path_uses_load_python_hashes_no_tree_verify():
    """Mobile → load_python_hashes is called, run_tree_verify is NOT, no overlay."""
    base_attestation = {"level": 3, "valid": True, "python_integrity": {"valid": True, "modules_checked": 50}}
    fake_wrapper = MagicMock(spec=PythonHashesWrapper)
    fake_wrapper.module_count = 50
    container = VerifyThreadResult()

    with patch.object(verifier_runner, "is_mobile", return_value=True), patch.object(
        verifier_runner, "load_python_hashes", return_value=(fake_wrapper, "2.8.6")
    ) as mock_load, patch.object(verifier_runner, "run_tree_verify") as mock_tree, patch.object(
        verifier_runner, "get_default_agent_version"
    ) as mock_default_ver, patch.object(
        verifier_runner, "get_agent_root", return_value="/data/data/ai.ciris.mobile"
    ), patch.object(
        verifier_runner, "get_ed25519_fingerprint", return_value="fp"
    ), patch.object(
        verifier_runner, "find_audit_db_path", return_value=None
    ):
        target = verifier_runner.create_verification_thread_target(
            get_verifier=lambda: _stub_verifier(base_attestation),
            attestation_mode="full",
            result_container=container,
        )
        _run_thread_target(target)

    # Algorithm B path was taken.
    mock_load.assert_called_once()
    mock_tree.assert_not_called()
    mock_default_ver.assert_not_called()

    # python_integrity NOT overlaid (mobile keeps whatever run_attestation_sync produced).
    assert container.error is None
    assert container.result is not None
    attestation = container.result["attestation"]
    assert attestation["python_integrity"] == {"valid": True, "modules_checked": 50}


def test_desktop_path_no_overlay_when_tree_verify_returns_none():
    """Desktop with verify_tree() unavailable → no overlay; original python_integrity preserved."""
    base_attestation = {"level": 3, "valid": True, "python_integrity": {"valid": True}}
    container = VerifyThreadResult()

    with patch.object(verifier_runner, "is_mobile", return_value=False), patch.object(
        verifier_runner, "get_default_agent_version", return_value="2.8.6"
    ), patch.object(verifier_runner, "run_tree_verify", return_value=None), patch.object(
        verifier_runner, "get_agent_root", return_value="/app"
    ), patch.object(
        verifier_runner, "get_ed25519_fingerprint", return_value="fp"
    ), patch.object(
        verifier_runner, "find_audit_db_path", return_value=None
    ):
        target = verifier_runner.create_verification_thread_target(
            get_verifier=lambda: _stub_verifier(base_attestation),
            attestation_mode="full",
            result_container=container,
        )
        _run_thread_target(target)

    assert container.error is None
    attestation = container.result["attestation"]
    # Original python_integrity untouched (no overlay because tree_verify returned None).
    assert attestation["python_integrity"] == {"valid": True}
