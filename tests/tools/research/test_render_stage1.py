"""The stage-1 renderer is the deployed composer, and it holds the cues fixed."""

import asyncio
import json
from pathlib import Path

from tools.research import render_stage1 as rs


def test_compose_reproduces_the_golden_bytes() -> None:
    assert rs.golden_check()["equal"] is True


def test_items_differ_only_in_task_and_thought(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CIRIS_PREFERRED_LANGUAGE", "en")
    src = tmp_path / "items.jsonl"
    items = [
        {"id": "a", "task": "TASK-ALPHA", "thought": "THOUGHT-ALPHA"},
        {"id": "b", "task": "TASK-BRAVO", "thought": "THOUGHT-BRAVO"},
    ]
    src.write_text("\n".join(json.dumps(i) for i in items) + "\n", encoding="utf-8")
    manifest = rs.render_files(tmp_path / "out", [("s", src)])

    rows = [json.loads(line) for line in (tmp_path / "out" / "s.jsonl").read_text(encoding="utf-8").splitlines()]
    a, b = rows[0]["user"], rows[1]["user"]
    assert a.replace("TASK-ALPHA", "TASK-BRAVO").replace("THOUGHT-ALPHA", "THOUGHT-BRAVO") == b
    assert "Thought Depth: 0" in a and rs.WITHHELD_SENTENCE in a
    assert "CONSCIENCE OVERRIDE GUIDANCE" not in a.split("=== ORIGINAL TASK")[0].split("SCHEMA REMINDER")[0]
    assert manifest["reassembly_checked_items"] == 2 and manifest["golden_check"]["equal"] is True


def test_withheld_arm_shows_no_placeholder_verdict() -> None:
    inputs, task = rs.item_inputs("t", "th")
    messages = asyncio.run(rs.compose(inputs, cached_task=task, withheld=True))
    assert "unused" not in messages[-1]["content"]


def test_default_template_changes_the_prompt_and_is_recorded(tmp_path: Path, monkeypatch) -> None:
    """Under an agent template the prompt is the template's, and the manifest says which."""
    monkeypatch.setenv("CIRIS_PREFERRED_LANGUAGE", "en")
    src = tmp_path / "items.jsonl"
    src.write_text(json.dumps({"id": "a", "task": "TASK-ALPHA", "thought": "THOUGHT-ALPHA"}) + "\n", encoding="utf-8")

    base = rs.render_files(tmp_path / "base", [("s", src)])
    templated = rs.render_files(tmp_path / "tpl", [("s", src)], rs.load_stack(rs.DEFAULT_TEMPLATE))

    assert base["agent_template"]["template"] is None
    described = templated["agent_template"]
    assert described["template"] and described["sha256"] and described["action_selection_pdma_overrides"]
    assert templated["prefix"]["sha256"] != base["prefix"]["sha256"]
    assert templated["permitted_actions"] == described["permitted_actions"] != []
    row = json.loads((tmp_path / "tpl" / "s.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert "TASK-ALPHA" in row["user"] and "THOUGHT-ALPHA" in row["user"]
