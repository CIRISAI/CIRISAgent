"""Render blind items into the action-selection (stage-1) prompt, with no model call.

An item is the variable part of one action-selection call: a task and a current
thought. This puts each into the messages `ActionSelectionPDMAEvaluator` would
send, using the evaluator's own `evaluate()` path with the LLM call replaced by
a recorder, so the constant prefix and the fixed sections are what deploys at
this commit.

Held the same for every item, so none of it can tell items apart:
  thought depth 0, no conscience-retry block, no final-attempt advisory, the
  default ten permitted verbs, no tools listed, one fixed system snapshot, no
  user profile, language en.

Arm `withheld`: the four evaluator sections carry no verdict. DSDMA and IDMA
use the builder's own text for an absent result. The ethical and common-sense
sections have no such text (the builder requires a result), so both carry
`WITHHELD_SENTENCE`. The manifest records which was used for each.

Output directory:
  prefix.json     the system messages, identical for every item, stored once
  <split>.jsonl   one row per item: id, user (the user message), prompt_hash
  manifest.json   commit, input digests, settings, the golden-bytes check

`prompt_hash` is sha256 over the full message list serialised as the LLM bus
serialises it, so a captured call can be matched to a rendered item.

    python3 -m tools.research.render_stage1 --out DIR split=path.jsonl [split=path.jsonl ...]

Needs the repo checkout: it reuses the #972 compose fixture under tests/.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, Mock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
WITHHELD_SENTENCE = "Not provided for this item."
FIXED_TS = "2026-01-01T00:00:00+00:00"
TASK_ID = "item-task"
THOUGHT_ID = "item-thought"


def _prompt_hash(messages: List[Dict[str, Any]]) -> str:
    from ciris_engine.logic.buses.llm_bus import _safe_messages_to_text

    return hashlib.sha256(_safe_messages_to_text(messages).encode("utf-8")).hexdigest()


async def compose(inputs: Any, cached_task: Any = None, withheld: bool = False) -> List[Dict[str, Any]]:
    """The messages action selection sends for `inputs`. No model is called."""
    from ciris_engine.logic.dma.action_selection_pdma import ActionSelectionPDMAEvaluator
    from ciris_engine.schemas.dma.results import ASPDMALLMResult
    from ciris_engine.schemas.runtime.enums import HandlerActionType

    registry = Mock()
    registry.get_services_by_type.return_value = []
    dma = ActionSelectionPDMAEvaluator(service_registry=registry)
    builder = dma.context_builder
    builder.pre_cache_context = AsyncMock(return_value=0)
    builder._tools_cached = True
    builder._cached_task = cached_task
    builder._cached_installable_tools = ""

    captured: Dict[str, Any] = {}

    async def _record(**kwargs: Any) -> Tuple[Any, Any]:
        captured["messages"] = kwargs["messages"]
        return (
            ASPDMALLMResult(selected_action=HandlerActionType.PONDER, reasoning="unused", ponder_questions=["unused"]),
            None,
        )

    dma.call_llm_structured = AsyncMock(side_effect=_record)  # type: ignore[method-assign]
    if withheld:
        with (
            patch.object(builder, "_build_ethical_summary", return_value=WITHHELD_SENTENCE),
            patch.object(builder, "_build_csdma_summary", return_value=WITHHELD_SENTENCE),
        ):
            await dma.evaluate(inputs)
    else:
        await dma.evaluate(inputs)
    messages: List[Dict[str, Any]] = captured["messages"]
    return messages


def item_inputs(task_text: str, thought_text: str) -> Tuple[Any, Any]:
    """(EnhancedDMAInputs, Task) for one item, everything else fixed."""
    from ciris_engine.schemas.dma.faculty import EnhancedDMAInputs
    from ciris_engine.schemas.dma.results import CSDMAResult, EthicalDMAResult
    from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus, ThoughtType
    from ciris_engine.schemas.runtime.models import Task, Thought, ThoughtContext
    from ciris_engine.schemas.runtime.system_context import SystemSnapshot

    task = Task(
        task_id=TASK_ID, channel_id="item-channel", description=task_text, created_at=FIXED_TS, updated_at=FIXED_TS
    )
    thought = Thought(
        thought_id=THOUGHT_ID,
        source_task_id=TASK_ID,
        content=thought_text,
        status=ThoughtStatus.PROCESSING,
        thought_type=ThoughtType.STANDARD,
        thought_depth=0,
        created_at=FIXED_TS,
        updated_at=FIXED_TS,
        context=ThoughtContext(task_id=TASK_ID, round_number=0, depth=0, correlation_id="item-corr"),
    )
    snapshot = SystemSnapshot(
        agent_identity={"agent_id": "ciris", "description": "A CIRIS agent", "role": "Assistant"},
        channel_id="item-channel",
        agent_version="item",
        system_counts={"total_tasks": 1, "total_thoughts": 1, "pending_tasks": 0, "pending_thoughts": 0},
    )
    # Placeholders the type requires; the withheld arm never renders them.
    ethical = EthicalDMAResult(
        action=HandlerActionType.PONDER, rationale="unused", weight_alignment_score=0.0, ethical_alignment_score=0.0
    )
    csdma = CSDMAResult(plausibility_score=0.0, flags=[], reasoning="unused")
    inputs = EnhancedDMAInputs(
        original_thought=thought,
        processing_context={"system_snapshot": snapshot.model_dump()},
        ethical_pdma_result=ethical,
        csdma_result=csdma,
        dsdma_result=None,
        idma_result=None,
        permitted_actions=None,  # the builder's default ten
    )
    return inputs, task


def golden_check() -> Dict[str, Any]:
    """`compose` on the #972 fixture inputs must reproduce the committed golden bytes."""
    sys.path.insert(0, str(REPO_ROOT))
    from tests.ciris_engine.logic.dma import compose_golden as cg

    with cg.deterministic_prompt_environment():
        messages = asyncio.run(compose(cg.make_enhanced_inputs()))
    golden_path = cg.GOLDEN_DIR / "aspdma_messages.json"
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    return {
        "golden_file": str(golden_path.relative_to(REPO_ROOT)),
        "golden_sha256": hashlib.sha256(golden_path.read_bytes()).hexdigest(),
        "equal": messages == golden,
    }


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()


def render_files(out_dir: Path, splits: List[Tuple[str, Path]]) -> Dict[str, Any]:
    os.environ["CIRIS_PREFERRED_LANGUAGE"] = "en"
    check = golden_check()
    if not check["equal"]:
        raise SystemExit(f"golden check failed: {check}")

    out_dir.mkdir(parents=True, exist_ok=True)
    prefix: Optional[List[Dict[str, Any]]] = None
    inputs_meta: Dict[str, Any] = {}

    async def _run() -> None:
        nonlocal prefix
        for split, path in splits:
            raw = path.read_bytes()
            rows = 0
            with (out_dir / f"{split}.jsonl").open("w", encoding="utf-8") as out:
                for line in raw.decode("utf-8").splitlines():
                    if not line.strip():
                        continue
                    item = json.loads(line)
                    inputs, task = item_inputs(item["task"], item["thought"])
                    messages = await compose(inputs, cached_task=task, withheld=True)
                    head, user = messages[:-1], messages[-1]
                    if user.get("role") != "user":
                        raise SystemExit(f"{split}: last message is not the user message")
                    if prefix is None:
                        prefix = head
                    elif head != prefix:
                        raise SystemExit(f"{split}: the system messages differ between items ({item['id']})")
                    row = {"id": item["id"], "user": user["content"], "prompt_hash": _prompt_hash(messages)}
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
                    rows += 1
            inputs_meta[split] = {"file": path.name, "sha256": hashlib.sha256(raw).hexdigest(), "items": rows}

    asyncio.run(_run())
    assert prefix is not None
    (out_dir / "prefix.json").write_text(json.dumps(prefix, ensure_ascii=False), encoding="utf-8")

    # Reassembly: prefix + user must reproduce every recorded hash.
    reassembled = 0
    for split, _ in splits:
        for line in (out_dir / f"{split}.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if _prompt_hash(prefix + [{"role": "user", "content": row["user"]}]) != row["prompt_hash"]:
                raise SystemExit(f"{split}: reassembly does not reproduce the hash for {row['id']}")
            reassembled += 1

    manifest = {
        "renderer": "tools/research/render_stage1.py",
        "code_commit": _git("rev-parse", "HEAD"),
        "tree_dirty": bool(_git("status", "--porcelain", "--untracked-files=no")),
        "arm": "withheld",
        "language": "en",
        "thought_depth": 0,
        "permitted_actions": "builder default (ten)",
        "tools_listed": False,
        "conscience_retry_block": False,
        "final_attempt_advisory": False,
        "user_profile": None,
        "evaluator_sections": {
            "ethical": {"source": "stated sentence", "text": WITHHELD_SENTENCE},
            "csdma": {"source": "stated sentence", "text": WITHHELD_SENTENCE},
            "dsdma": {"source": "builder's own text for an absent result"},
            "idma": {"source": "builder's own text for an absent result (empty)"},
        },
        "prefix": {
            "file": "prefix.json",
            "messages": len(prefix),
            "chars": sum(len(str(m.get("content", ""))) for m in prefix),
            "sha256": hashlib.sha256((out_dir / "prefix.json").read_bytes()).hexdigest(),
        },
        "message_layout": "prefix.json messages, then {'role': 'user', 'content': row.user}",
        "prompt_hash": "sha256 of json.dumps(messages, ensure_ascii=False), as the LLM bus computes it",
        "reassembly_checked_items": reassembled,
        "golden_check": check,
        "inputs": inputs_meta,
        "outputs": {
            f"{split}.jsonl": hashlib.sha256((out_dir / f"{split}.jsonl").read_bytes()).hexdigest()
            for split, _ in splits
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("splits", nargs="+", help="split=path.jsonl")
    args = parser.parse_args()
    splits = []
    for spec in args.splits:
        name, _, path = spec.partition("=")
        splits.append((name, Path(path)))
    manifest = render_files(args.out, splits)
    summary = {k: manifest[k] for k in ("code_commit", "tree_dirty", "prefix", "reassembly_checked_items", "inputs")}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
