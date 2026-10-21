"""Reasoning-off conformance: does the payload we send actually turn thinking off?

WHY THIS EXISTS
---------------
There is no universal off-switch. Every provider spells "don't think" its own
way, and a key one provider honours another silently ignores — silently being
the whole problem. A wrong key does not fail; it bills reasoning tokens and
adds 30-60s per call, which is what the CIRISProxy incident cost before anyone
noticed the OpenRouter entries were carrying vLLM's ``chat_template_kwargs``
(OpenRouter does not document that parameter at all; its documented switch is
``reasoning.enabled=false``).

So this sweep asks the only question that settles it, per (provider, model):

1. Does the provider ACCEPT what the product sends? A reasoning-off key that
   400s is worse than none — every call fails instead of merely being slow.
2. Does it actually SUPPRESS reasoning? Graded by comparing an off-call to a
   baseline call with no extras at all: reasoning tokens and wall-clock.

Both answers come from the product's own
``OpenAICompatibleClient._build_reasoning_off_extras`` — never a copy of it.
A test that reimplements the mapping proves only that the copy agrees with
itself.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .dimensions import PROVIDERS, ProviderSpec

# Models that reason BY DEFAULT — the only ones where the switch is observable.
# A non-reasoning model returns the same numbers either way, so grading it
# would report a pass that means nothing.
REASONING_MODELS: Dict[str, List[str]] = {
    "openai": ["gpt-5.2"],
    "openrouter": ["qwen/qwen3-32b", "deepseek/deepseek-r1"],
    "together": ["Qwen/Qwen3-235B-A22B-fp8-tput"],
    "groq": ["openai/gpt-oss-20b"],
    "google": ["gemini-2.5-flash", "gemini-3.6-flash"],
    # Anthropic's extended thinking is opt-IN: we never ask for it, so there is
    # nothing to switch off. Included as a declared no-op rather than omitted,
    # so "we checked and there is nothing to send" is visible in the report.
    "anthropic": [],
}

PROMPT = "Reply with exactly one word: ok"
MAX_TOKENS = 256


class ReasoningCell(BaseModel):
    """One (provider, model) pair, measured both ways."""

    provider: str
    model: str
    extras: Dict[str, Any] = Field(default_factory=dict)
    accepted: Optional[bool] = None
    error: Optional[str] = None
    off_latency_ms: Optional[float] = None
    base_latency_ms: Optional[float] = None
    off_reasoning_tokens: Optional[int] = None
    base_reasoning_tokens: Optional[int] = None
    off_content_empty: Optional[bool] = None
    verdict: str = "unknown"
    note: str = ""

    model_config = ConfigDict(extra="forbid")

    def grade(self) -> None:
        if self.accepted is False:
            self.verdict = "REJECTED"
            self.note = "the provider refused the reasoning-off payload — every call would fail"
            return
        if not self.extras:
            self.verdict = "NO-OP"
            self.note = "product sends nothing for this pair"
            return
        if self.off_reasoning_tokens is not None and self.base_reasoning_tokens is not None:
            off, base = self.off_reasoning_tokens, self.base_reasoning_tokens
            if off == 0 and base > 0:
                self.verdict = "OFF"
                self.note = f"reasoning tokens {base} -> 0"
                return
            # A model that CANNOT stop reasoning is a different fact from a
            # switch that failed, and grading them the same hides the one we can
            # act on. gpt-oss and R1 always reason; the win there is a floor,
            # not an off.
            if off > 0 and base > 0 and off < base * 0.75:
                self.verdict = "REDUCED"
                self.note = f"reasoning tokens {base} -> {off} (floor, not off)"
                return
            if off > 0:
                self.verdict = "STILL ON"
                self.note = f"{off} reasoning tokens survived the switch (baseline {base})"
                return
        # No usage detail: fall back to wall-clock, which is what a user feels.
        if self.off_latency_ms and self.base_latency_ms:
            ratio = self.base_latency_ms / max(self.off_latency_ms, 1.0)
            if ratio >= 1.5:
                self.verdict = "OFF"
                self.note = f"{self.base_latency_ms:.0f}ms -> {self.off_latency_ms:.0f}ms ({ratio:.1f}x)"
            else:
                self.verdict = "ACCEPTED"
                self.note = f"accepted; no measurable reasoning either way ({ratio:.1f}x)"
            return
        self.verdict = "ACCEPTED"
        self.note = "accepted; not measurable"


def _reasoning_tokens(usage: Any) -> Optional[int]:
    """Reasoning tokens, wherever this provider decided to put them."""
    if usage is None:
        return None
    details = getattr(usage, "completion_tokens_details", None)
    if details is not None:
        tok = getattr(details, "reasoning_tokens", None)
        if tok is not None:
            return int(tok)
    for name in ("reasoning_tokens", "thoughts_token_count"):
        tok = getattr(usage, name, None)
        if tok is not None:
            return int(tok)
    return None


async def _one_call(
    spec: ProviderSpec, model: str, api_key: str, extras: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key, base_url=spec.base_url, timeout=120.0, max_retries=0)
    # gpt-5 and the o-series refuse `max_tokens` outright ("use
    # max_completion_tokens"), so the probe must speak each family's dialect or
    # it reports a product failure that is really its own.
    token_field = "max_completion_tokens" if any(t in model for t in ("gpt-5", "o1", "o3", "o4")) else "max_tokens"
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        token_field: MAX_TOKENS,
    }
    if extras:
        kwargs["extra_body"] = dict(extras)
    started = time.monotonic()
    try:
        resp = await client.chat.completions.create(**kwargs)
        elapsed = (time.monotonic() - started) * 1000.0
        content = (resp.choices[0].message.content or "") if resp.choices else ""
        return {
            "ok": True,
            "latency_ms": elapsed,
            "reasoning_tokens": _reasoning_tokens(getattr(resp, "usage", None)),
            "content_empty": not content.strip(),
        }
    except Exception as exc:  # noqa: BLE001 — the failure IS the datum
        return {"ok": False, "latency_ms": (time.monotonic() - started) * 1000.0, "error": f"{type(exc).__name__}: {exc}"[:300]}
    finally:
        await client.close()


async def probe_pair(spec: ProviderSpec, model: str, api_key: str) -> ReasoningCell:
    from ciris_engine.logic.services.runtime.llm_service.service import OpenAICompatibleClient

    extras = OpenAICompatibleClient._build_reasoning_off_extras(spec.base_url or "", model)
    cell = ReasoningCell(provider=spec.provider_id, model=model, extras=extras)

    off = await _one_call(spec, model, api_key, extras)
    cell.accepted = bool(off["ok"])
    cell.off_latency_ms = off["latency_ms"]
    if not off["ok"]:
        cell.error = off.get("error")
        cell.grade()
        return cell
    cell.off_reasoning_tokens = off.get("reasoning_tokens")
    cell.off_content_empty = off.get("content_empty")

    base = await _one_call(spec, model, api_key, None)
    if base["ok"]:
        cell.base_latency_ms = base["latency_ms"]
        cell.base_reasoning_tokens = base.get("reasoning_tokens")
    cell.grade()
    return cell


def _read_key(spec: ProviderSpec) -> Optional[str]:
    path = Path(spec.key_file).expanduser()
    if not path.exists():
        return None
    key = path.read_text().strip()
    return key or None


async def sweep(provider_ids: Optional[List[str]] = None) -> List[ReasoningCell]:
    """Every (provider, reasoning-model) pair, measured both ways."""
    cells: List[ReasoningCell] = []
    for pid in provider_ids or list(PROVIDERS):
        spec = PROVIDERS[pid]
        models = REASONING_MODELS.get(pid, [])
        if not models:
            from ciris_engine.logic.services.runtime.llm_service.service import OpenAICompatibleClient

            cell = ReasoningCell(
                provider=pid,
                model="(no reasoning-by-default model)",
                extras=OpenAICompatibleClient._build_reasoning_off_extras(spec.base_url or "", spec.cheap_model),
            )
            cell.verdict = "N/A"
            cell.note = "provider has no reason-by-default model in our set"
            cells.append(cell)
            continue
        if spec.sdk != "openai":
            cell = ReasoningCell(provider=pid, model=models[0])
            cell.verdict = "N/A"
            cell.note = f"{spec.sdk} SDK — extended thinking is opt-in, we never request it"
            cells.append(cell)
            continue
        key = _read_key(spec)
        if not key:
            cell = ReasoningCell(provider=pid, model=models[0])
            cell.verdict = "NO KEY"
            cell.note = f"{spec.key_file} missing"
            cells.append(cell)
            continue
        for model in models:
            cells.append(await probe_pair(spec, model, key))
    return cells


def render(cells: List[ReasoningCell]) -> str:
    rows = [
        f"{'provider':<11} {'model':<34} {'verdict':<10} {'extras':<38} note",
        "-" * 130,
    ]
    for c in cells:
        extras = str(c.extras) if c.extras else "-"
        rows.append(f"{c.provider:<11} {c.model[:34]:<34} {c.verdict:<10} {extras[:38]:<38} {c.note}")
    return "\n".join(rows)
