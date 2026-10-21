"""Recorded provider behaviour, for ``--dry-run``.

A fixture is one provider's real reply to one cell, captured on a live run and
stored as the fields of an ``LLMProbeOutcome``. Because
``_classify_llm_connection_error`` reads nothing but ``str(exception)``, a
recorded ``exception_str`` replayed through :class:`ReplayedProviderError`
drives the product's classifier down exactly the branch the live call did.

That is what makes ``--dry-run`` worth having: it is not a smoke test of the
plumbing, it re-grades known provider behaviour against the current
classifier. A refactor that changes which branch an OpenRouter data-policy 404
lands in shows up in CI, with no key and no spend.

Refreshing the corpus
---------------------
``--update-fixtures`` on a live run writes the observed outcomes to
``<report-dir>/fixtures.json``. Review the diff, then copy it over
``fixtures.json`` in this package. It is never overwritten automatically — a
fixture is a claim about what a provider does, and claims get reviewed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from .schemas import CellResult, LLMProbeOutcome, ProbeKind, QuirksReport

FIXTURES_PATH = Path(__file__).with_name("fixtures.json")

# Fields of LLMProbeOutcome worth recording. `latency_ms` is deliberately
# excluded — replaying a timing would imply the dry run measured one.
_RECORDED_FIELDS = (
    "succeeded",
    "http_status",
    "exception_type",
    "exception_str",
    "provider_error_code",
    "provider_error_message",
    "raw_body_excerpt",
    "effective_model",
    "completion_tokens",
    "listed_model_ids",
    "listed_model_ids_truncated",
)


def load_fixtures(path: Optional[Path] = None) -> Dict[str, LLMProbeOutcome]:
    """Load the recorded corpus as typed outcomes. ``{}`` when the file is absent.

    Parsing here rather than downstream means a corpus that has drifted out of
    shape fails at load with a Pydantic error naming the field, instead of
    quietly replaying a half-populated outcome as if it were observed.
    """
    target = path or FIXTURES_PATH
    if not target.exists():
        return {}
    with target.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    cells = data.get("cells", {})
    return {str(k): LLMProbeOutcome(**v) for k, v in cells.items()}


def fixtures_from_report(report: QuirksReport, max_listed_models: int = 40) -> Dict[str, LLMProbeOutcome]:
    """Extract a fixture corpus from a completed live run.

    Model listings are truncated: the corpus exists to reproduce
    classification behaviour, not to mirror a provider's whole catalogue into
    the repo.
    """
    corpus: Dict[str, LLMProbeOutcome] = {}
    for result in report.results:
        if result.skipped_reason is not None or result.cell.probe is ProbeKind.STATIC_AUDIT:
            continue
        corpus[result.cell.cell_id] = _record(result, max_listed_models)
    return corpus


def _record(result: CellResult, max_listed_models: int) -> LLMProbeOutcome:
    outcome = result.outcome
    kept = {field: getattr(outcome, field) for field in _RECORDED_FIELDS}
    listed = list(kept.get("listed_model_ids") or [])
    if len(listed) > max_listed_models:
        kept["listed_model_ids"] = listed[:max_listed_models]
        kept["listed_model_ids_truncated"] = True
    return LLMProbeOutcome(**kept)


def write_fixtures(corpus: Dict[str, LLMProbeOutcome], path: Path, note: str = "") -> None:
    """Write a corpus for review. Never targets the in-tree file by default."""
    payload = {
        "note": note
        or "Captured by tools.qa_runner.modules.llm_matrix --live --update-fixtures. "
        "Review before copying over the in-tree fixtures.json.",
        "cells": {cell_id: outcome.model_dump() for cell_id, outcome in corpus.items()},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


__all__ = ["FIXTURES_PATH", "fixtures_from_report", "load_fixtures", "write_fixtures"]
