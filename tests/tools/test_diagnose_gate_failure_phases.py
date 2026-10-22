"""Every phase the gate passes must classify; and an unreachable test server is INFRA."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = [
    ROOT / ".github/workflows/five-platform-live-qa.yml",
    ROOT / ".github/workflows/five-platform-modular-qa.yml",
]

_spec = importlib.util.spec_from_file_location("dgf", ROOT / "tools/dev/diagnose_gate_failure.py")
assert _spec and _spec.loader
dgf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dgf)


def test_every_phase_the_workflow_passes_has_a_default():
    """UNKNOWN is not a classification. The nightly's only failing leg produced
    three of them because these keys were missing."""
    for workflow in WORKFLOWS:
        passed = set(re.findall(r"--phase ([a-z-]+)", workflow.read_text()))
        assert passed, f"no --phase arguments found in {workflow.name}; did the workflow move?"
        missing = sorted(passed - set(dgf.PHASE_DEFAULT))
        assert not missing, f"{workflow.name}: phases with no PHASE_DEFAULT entry: {missing}"


def test_an_incidents_gate_failure_names_the_line():
    """A run where every test passed but the incidents gate tripped used to read
    UNKNOWN (run 39664086947, 38/38). The classifier must quote the agent line."""
    blob = (
        "[OK] All tests passed!\n"
        "[INCIDENTS-GATE] FAILED (13x): ciris_engine.logic.processors.core.thought_processor.main - "
        "main.py:823 - MSASPDMA: Failed for thought <id>: no attribute 'final_action'\n"
    )
    layer, meaning, evidence = dgf.classify(blob, "modular")
    assert layer == "AGENT", (layer, meaning)
    assert "incidents gate" in meaning
    assert "MSASPDMA: Failed" in evidence


def test_an_unreachable_test_server_is_infra_not_client():
    blob = (
        " [FAIL] desktop test server not reachable within 90s\n"
        "     jvm: ALIVE\n"
        "     => REACHABILITY, not startup: the app is serving and we could not\n"
    )
    layer, meaning, _ = dgf.classify(blob, "setup-noai")
    assert layer == "INFRA", (layer, meaning)


def test_infra_outranks_the_cascaded_client_symptoms():
    """The real log carries BOTH: the infra cause first, then the element-not-found
    consequences. The cause must win."""
    blob = (
        " [FAIL] desktop test server not reachable within 90s\n"
        " [FAIL] click_login_button: Element not found: btn_login_submit\n"
        " [FAIL] reset_device: wait_for element 'btn_login_reset_device' timed out\n"
    )
    layer, _, _ = dgf.classify(blob, "reset")
    assert layer == "INFRA", "the cascade must not be classified by its symptoms"


def test_a_genuine_client_failure_is_still_client():
    blob = " [FAIL] click_login_button: Element not found: btn_login_submit\n"
    layer, _, _ = dgf.classify(blob, "login")
    assert layer == "CLIENT"
