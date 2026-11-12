"""Run blind items through the four evaluators and then action selection, directly.

The "as deployed" arm for the items `render_stage1` renders: the same
constructed task and thought, the same agent template, the same fixed cues,
but the four evaluator sections are whatever the evaluators say. No agent is
booted: each item is five model calls (ethical, common sense and domain in
parallel, then IDMA, then action selection), as the pipeline orders them.

Not run here, and so not part of this arm: the evaluator bounce, consciences,
verb-specific second passes, handlers.

Per split, in the output directory:
  <split>.results.jsonl    one row per item: the four evaluator results, the
                           four summaries as action selection received them,
                           the selection prompt hash, the verb, cost
  <split>.llm_calls.jsonl  one row per model call, the LLM bus capture schema
                           (messages as sent, parsed reply, raw completion text,
                           error rows); thought_id is the item id
  manifest.json            commit, template, model, endpoint, input digests,
                           spend, what was and was not run

THIS SPENDS MONEY. `--max-usd` is a hard ceiling on the summed cost the LLM
service reports (its price table); the run stops before an item that could
cross it. Rerunning resumes: items already in results are skipped and their
cost counts toward the ceiling. The key is read from `--key-file` and is never
printed or written.

    python3 -m tools.research.run_stage1 --out DIR --key-file ~/.openrouter_key \\
        --max-usd 60 [--limit N] [--shard I/N] [--concurrency 4] split=path.jsonl ...
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, Mock

from tools.research import render_stage1 as rs

MAX_CALLS_PER_ITEM = 10  # five calls, each retried at most once
DEFAULT_MODEL = "qwen/qwen3.6-35b-a3b"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


class Budget:
    """Summed reported cost, with a ceiling that is checked before each item."""

    def __init__(self, max_usd: float, spent_usd: float = 0.0, reserve_usd: float = 0.10) -> None:
        self.max_usd = max_usd
        self.spent_usd = spent_usd
        self.reserve_usd = reserve_usd  # the most one item is allowed to add before the next check
        self.in_flight = 0

    def may_start(self) -> bool:
        return self.spent_usd + (self.in_flight + 1) * self.reserve_usd <= self.max_usd

    def add(self, cost_cents: float) -> None:
        self.spent_usd += cost_cents / 100.0


class Caller:
    """One item's model calls: counted, costed, captured."""

    def __init__(self, client: Any, bus: Any, item_id: str, budget: Budget, model: str, api_base: str) -> None:
        self.client, self.bus, self.item_id, self.budget = client, bus, item_id, budget
        self.model, self.api_base = model, api_base
        self.calls = 0
        self.cost_cents = 0.0
        self.tokens_in = 0
        self.tokens_out = 0
        self.hashes: Dict[str, str] = {}

    def bind(self, handler_name: str) -> Any:
        async def call(
            messages: List[Dict[str, Any]],
            response_model: Any,
            max_tokens: int = 1024,
            temperature: float = 0.0,
            **_: Any,
        ) -> Tuple[Any, Any]:
            from ciris_engine.logic.buses.llm_call_context import (
                close_raw_completion_holder,
                open_raw_completion_holder,
            )

            normalized = self.bus._normalize_messages(messages)
            self.hashes[handler_name] = rs._prompt_hash(normalized)
            common = dict(
                handler_name=handler_name,
                service_name="run_stage1",
                thought_id=self.item_id,
                task_id=self.item_id,
                messages=normalized,
                response_model=response_model,
                temperature=temperature,
                max_tokens=max_tokens,
                model=self.model,
                api_base=self.api_base,
            )
            last: Optional[BaseException] = None
            for _attempt in range(2):
                if self.calls >= MAX_CALLS_PER_ITEM:
                    raise RuntimeError(f"{self.item_id}: more than {MAX_CALLS_PER_ITEM} model calls")
                self.calls += 1
                holder = open_raw_completion_holder()
                try:
                    result, usage = await self.client.call_llm_structured(
                        messages=normalized,
                        response_model=response_model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        thought_id=self.item_id,
                        task_id=self.item_id,
                    )
                except Exception as exc:  # recorded, retried once, then the item fails
                    last = exc
                    self.bus._maybe_capture_call(result=None, error=exc, **common)
                    continue
                finally:
                    close_raw_completion_holder()
                cents = float(getattr(usage, "cost_cents", 0.0) or 0.0)
                self.cost_cents += cents
                self.tokens_in += int(getattr(usage, "tokens_input", 0) or 0)
                self.tokens_out += int(getattr(usage, "tokens_output", 0) or 0)
                self.budget.add(cents)
                self.bus._maybe_capture_call(result=result, raw_completion_text=holder.get("text"), **common)
                return result, usage
            assert last is not None
            raise last

        return call


def _dump(result: Any) -> Any:
    return result.model_dump(mode="json") if hasattr(result, "model_dump") else result


async def run_item(item: Dict[str, Any], stack: rs.Stack, client: Any, bus: Any, budget: Budget, cfg: Any) -> Dict[str, Any]:
    from ciris_engine.logic.dma.csdma import CSDMAEvaluator
    from ciris_engine.logic.dma.dsdma_base import BaseDSDMA
    from ciris_engine.logic.dma.idma import IDMAEvaluator
    from ciris_engine.logic.dma.pdma import EthicalPDMAEvaluator
    from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem, ThoughtContent
    from ciris_engine.schemas.runtime.enums import ThoughtType

    inputs, task = rs.item_inputs(item["task"], item["thought"], stack)
    snapshot = inputs.processing_context["system_snapshot"]
    queue_item = ProcessingQueueItem(
        thought_id=rs.THOUGHT_ID,
        source_task_id=rs.TASK_ID,
        thought_type=ThoughtType.STANDARD,
        content=ThoughtContent(text=item["thought"], metadata={}),
        thought_depth=0,
        initial_context={"system_snapshot": snapshot},
    )
    from ciris_engine.schemas.runtime.system_context import SystemSnapshot

    context = SimpleNamespace(system_snapshot=SystemSnapshot(**snapshot))
    caller = Caller(client, bus, item["id"], budget, cfg.model, cfg.base_url)

    def wire(dma: Any, name: str) -> Any:
        dma.fetch_original_task = AsyncMock(return_value=task)
        dma.call_llm_structured = caller.bind(name)
        return dma

    template = stack.template
    knowledge = template.dsdma_kwargs.domain_specific_knowledge if template and template.dsdma_kwargs else None
    dsdma_prompt = template.dsdma_kwargs.prompt_template if template and template.dsdma_kwargs else None
    domain_label = template.name if template else "ciris"  # the runtime labels the domain with the agent id
    pdma = wire(EthicalPDMAEvaluator(service_registry=Mock(), prompt_overrides=stack.overrides("pdma_overrides") or None), "EthicalPDMAEvaluator")
    csdma = wire(CSDMAEvaluator(service_registry=Mock(), prompt_overrides=stack.overrides("csdma_overrides") or None), "CSDMAEvaluator")
    dsdma = wire(
        BaseDSDMA(domain_name=domain_label, service_registry=Mock(), domain_specific_knowledge=knowledge, prompt_template=dsdma_prompt),
        "BaseDSDMA",
    )
    idma = wire(IDMAEvaluator(service_registry=Mock()), "IDMAEvaluator")

    row: Dict[str, Any] = {"id": item["id"], "status": "ok", "dsdma_domain_label": domain_label}
    try:
        ethical, common_sense, domain = await asyncio.gather(
            pdma.evaluate(queue_item, context), csdma.evaluate(queue_item, context), dsdma.evaluate(queue_item)
        )
        fragility = await idma.evaluate(
            queue_item, context, ethical_result=ethical, csdma_result=common_sense, dsdma_result=domain
        )
        inputs.ethical_pdma_result, inputs.csdma_result = ethical, common_sense
        inputs.dsdma_result, inputs.idma_result = domain, fragility

        selector = rs.new_action_selector(stack)
        builder = selector.context_builder
        builder.pre_cache_context = AsyncMock(return_value=0)
        builder._tools_cached = True
        builder._cached_task = task
        builder._cached_installable_tools = ""
        selector.call_llm_structured = caller.bind("ActionSelectionPDMAEvaluator")
        summaries = {
            "ethical": builder._build_ethical_summary(ethical),
            "csdma": builder._build_csdma_summary(common_sense),
            "dsdma": builder._build_dsdma_summary(domain),
            "idma": builder._build_idma_summary(fragility),
        }
        selection = await selector.evaluate(inputs)
        row.update(
            evaluators={"ethical": _dump(ethical), "csdma": _dump(common_sense), "dsdma": _dump(domain), "idma": _dump(fragility)},
            summaries=summaries,
            selection_prompt_hash=caller.hashes.get("ActionSelectionPDMAEvaluator"),
            selected_action=selection.selected_action.value,
            selection=_dump(selection),
        )
    except Exception as exc:
        row.update(status="error", error_class=exc.__class__.__name__, error=str(exc)[:2000])
    row.update(
        prompt_hashes=caller.hashes,
        calls=caller.calls,
        cost_usd=round(caller.cost_cents / 100.0, 6),
        tokens_in=caller.tokens_in,
        tokens_out=caller.tokens_out,
    )
    return row


async def make_client(args: Any) -> Any:
    """The LLM service the agent uses, pointed at the provider. Reads the key; never shows it."""
    from ciris_engine.logic.services.lifecycle.time import TimeService
    from ciris_engine.logic.services.runtime.llm_service.service import LLMProvider, OpenAICompatibleClient, OpenAIConfig

    key = Path(args.key_file).expanduser().read_text(encoding="utf-8").strip()
    time_service = TimeService()
    await time_service.start()
    client = OpenAICompatibleClient(
        config=OpenAIConfig(
            base_url=args.base_url,
            model_name=args.model,
            api_key=key,
            instructor_mode="JSON",
            timeout_seconds=args.timeout,
            max_retries=2,
            provider=LLMProvider.OPENAI_COMPATIBLE,
        ),
        time_service=time_service,
        service_name="run_stage1",
    )
    await client.start()
    return client


async def run(
    args: Any,
    splits: List[Tuple[str, Path]],
    stack: rs.Stack,
    client: Any = None,
    golden: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    from ciris_engine.logic.buses.llm_bus import LLMBus

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    if client is None:
        client = await make_client(args)
    bus = LLMBus.__new__(LLMBus)  # only its stateless helpers are used

    # Resume: what is already done, and what it cost.
    done: Dict[str, set[str]] = {}
    spent = 0.0
    for split, _ in splits:
        done[split] = set()
        path = out / f"{split}.results.jsonl"
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                prior = json.loads(line)
                spent += float(prior.get("cost_usd", 0.0))
                if prior.get("status") == "ok":
                    done[split].add(prior["id"])
    budget = Budget(args.max_usd, spent_usd=spent, reserve_usd=args.reserve_usd)
    cfg = SimpleNamespace(model=args.model, base_url=args.base_url)
    os.environ["CIRIS_LLM_CAPTURE_HANDLER"] = "*"
    shard_i, shard_n = args.shard
    stopped: Optional[str] = None
    counts: Dict[str, Dict[str, int]] = {}
    inputs_meta: Dict[str, Any] = {}
    semaphore = asyncio.Semaphore(args.concurrency)
    write_lock = asyncio.Lock()

    for split, path in splits:
        raw = path.read_bytes()
        inputs_meta[split] = {"file": path.name, "sha256": hashlib.sha256(raw).hexdigest()}
        items = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
        todo = [it for idx, it in enumerate(items) if idx % shard_n == shard_i and it["id"] not in done[split]]
        if args.limit is not None:
            todo = todo[: args.limit]
        counts[split] = {"items": len(items), "already_done": len(done[split]), "selected": len(todo), "ok": 0, "error": 0, "not_started": 0}
        os.environ["CIRIS_LLM_CAPTURE_FILE"] = str(out / f"{split}.llm_calls.jsonl")
        results_path = out / f"{split}.results.jsonl"

        async def one(item: Dict[str, Any]) -> None:
            nonlocal stopped
            async with semaphore:
                if stopped or not budget.may_start():
                    stopped = stopped or f"cost ceiling: spent ${budget.spent_usd:.2f} of ${budget.max_usd:.2f}"
                    counts[split]["not_started"] += 1
                    return
                budget.in_flight += 1
                try:
                    row = await run_item(item, stack, client, bus, budget, cfg)
                finally:
                    budget.in_flight -= 1
                async with write_lock:
                    with results_path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                counts[split][row["status"]] += 1
                done_now = counts[split]["ok"] + counts[split]["error"]
                if done_now % 25 == 0:
                    print(f"{split}: {done_now}/{len(todo)} spent ${budget.spent_usd:.2f}", flush=True)

        await asyncio.gather(*(one(item) for item in todo))

    manifest = {
        "runner": "tools/research/run_stage1.py",
        "arm": "as deployed: four evaluators, then action selection, called directly",
        "not_run": ["evaluator bounce", "consciences", "verb-specific second passes", "handlers"],
        "code_commit": rs._git("rev-parse", "HEAD"),
        "tree_dirty": bool(rs._git("status", "--porcelain", "--untracked-files=no")),
        "agent_template": stack.describe(),
        "model": args.model,
        "api_base": args.base_url,
        "instructor_mode": "JSON",
        "language": "en",
        "thought_depth": 0,
        "tools_listed": False,
        "scrubbed": False,
        "shard": f"{shard_i}/{shard_n}",
        "limit": args.limit,
        "max_usd": args.max_usd,
        "spent_usd_reported": round(budget.spent_usd, 4),
        "cost_source": "the LLM service's price table applied to reported token counts; check the provider's own figure",
        "stopped": stopped,
        "counts": counts,
        "inputs": inputs_meta,
        "golden_check": golden,
    }
    name = "manifest.json" if shard_n == 1 else f"manifest.shard{shard_i}of{shard_n}.json"
    (out / name).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--key-file", required=True)
    parser.add_argument("--max-usd", required=True, type=float)
    parser.add_argument("--reserve-usd", type=float, default=0.10, help="most one item may add before the next check")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--template", type=Path, default=rs.DEFAULT_TEMPLATE)
    parser.add_argument("--limit", type=int, default=None, help="at most this many items per split")
    parser.add_argument("--shard", default="0/1", help="I/N: items whose index mod N is I")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("splits", nargs="+", help="split=path.jsonl")
    args = parser.parse_args()
    i, _, n = args.shard.partition("/")
    args.shard = (int(i), int(n))
    splits = []
    for spec in args.splits:
        name, _, path = spec.partition("=")
        splits.append((name, Path(path)))
    os.environ["CIRIS_PREFERRED_LANGUAGE"] = "en"
    stack = rs.load_stack(args.template)
    golden = rs.golden_check()
    if not golden["equal"]:
        raise SystemExit(f"golden check failed: {golden}")
    manifest = asyncio.run(run(args, splits, stack, golden=golden))
    keys = ("code_commit", "model", "max_usd", "spent_usd_reported", "stopped", "counts")
    print(json.dumps({k: manifest[k] for k in keys}, indent=2))
    if manifest["stopped"]:
        sys.exit(3)


if __name__ == "__main__":
    main()
