"""Every safety-battery capture records which corpus it ran.

``manifest_signed.json["research_manifest"]`` is ``None`` for a canonical
capture and ``{path, sha256, digest}`` for a research-override arm dispatched
through the ``research_manifest`` workflow input.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ciris_engine.logic.utils.research_overrides import compute_manifest_digest
from tools.qa_runner.modules.safety_battery import _research_manifest_record

REPO = Path(__file__).resolve().parents[3]
ARM = "tools/research/manifests/torque-mvm-armB.json"


def test_canonical_capture_records_null(monkeypatch):
    monkeypatch.delenv("CIRIS_RESEARCH_PROMPT_OVERRIDES", raising=False)
    monkeypatch.delenv("CIRIS_RESEARCH_MANIFEST_PATH", raising=False)
    assert _research_manifest_record() is None


def test_arm_capture_records_path_sha256_and_digest(monkeypatch):
    src = REPO / ARM
    monkeypatch.setenv("CIRIS_RESEARCH_PROMPT_OVERRIDES", str(src))
    monkeypatch.setenv("CIRIS_RESEARCH_MANIFEST_PATH", ARM)
    rec = _research_manifest_record()
    assert rec == {
        "path": ARM,
        "sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
        "digest": compute_manifest_digest(json.loads(src.read_text(encoding="utf-8"))),
    }


def test_falls_back_to_env_path_and_tolerates_unreadable_manifest(monkeypatch, tmp_path):
    bad = tmp_path / "m.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("CIRIS_RESEARCH_PROMPT_OVERRIDES", str(bad))
    monkeypatch.delenv("CIRIS_RESEARCH_MANIFEST_PATH", raising=False)
    rec = _research_manifest_record()
    assert rec is not None
    assert rec["path"] == str(bad)
    assert rec["sha256"] == hashlib.sha256(bad.read_bytes()).hexdigest()
    assert rec["digest"] is None
