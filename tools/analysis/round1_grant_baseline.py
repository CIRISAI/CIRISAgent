#!/usr/bin/env python3
"""Generate a reproducible Round 1 grant-readiness baseline for CIRISAgent.

This script captures three frequently stale claim surfaces:
1. Core service taxonomy (22 services)
2. REST endpoint inventory counts from FastAPI route registration
3. Test inventory via pytest collection

Outputs:
- JSON summary to stdout
- Optional markdown report (--markdown-out)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ciris_engine.logic.adapters.api.app import create_app
from ciris_engine.logic.adapters.api.service_configuration import ApiServiceConfiguration


@dataclass
class CategorySummary:
    category: str
    count: int
    runtime_attributes: list[str]


@dataclass
class EndpointSummary:
    total_routes: int
    methods: dict[str, int]
    auth_related_routes: int
    oauth_routes: int


@dataclass
class TestCollectionSummary:
    collected: int
    collection_errors: int
    missing_pytest_plugins: list[str]
    raw_summary_line: str


@dataclass
class Round1Baseline:
    generated_at_utc: str
    service_taxonomy: list[CategorySummary]
    service_total: int
    endpoint_summary: EndpointSummary
    test_collection: TestCollectionSummary | None


HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def summarize_services() -> tuple[list[CategorySummary], int]:
    categories = [
        ("graph", ApiServiceConfiguration.GRAPH_SERVICES),
        ("infrastructure", ApiServiceConfiguration.INFRASTRUCTURE_SERVICES),
        ("lifecycle", ApiServiceConfiguration.LIFECYCLE_SERVICES),
        ("governance", ApiServiceConfiguration.GOVERNANCE_SERVICES),
        ("runtime", ApiServiceConfiguration.RUNTIME_SERVICES),
        ("tool", ApiServiceConfiguration.TOOL_SERVICES),
    ]

    results: list[CategorySummary] = []
    total = 0
    for category_name, service_mappings in categories:
        attrs = [mapping.runtime_attr for mapping in service_mappings]
        count = len(attrs)
        total += count
        results.append(CategorySummary(category=category_name, count=count, runtime_attributes=attrs))

    return results, total


def summarize_endpoints() -> EndpointSummary:
    app = create_app()

    method_counter: Counter[str] = Counter()
    auth_related = 0
    oauth_related = 0
    total_routes = 0

    for route in app.routes:
        methods = getattr(route, "methods", None)
        if not methods:
            continue

        filtered_methods = [method for method in methods if method in HTTP_METHODS]
        if not filtered_methods:
            continue

        total_routes += 1
        for method in filtered_methods:
            method_counter[method] += 1

        route_path = getattr(route, "path", "")
        if "/auth/" in route_path:
            auth_related += 1
        if "/oauth/" in route_path:
            oauth_related += 1

    return EndpointSummary(
        total_routes=total_routes,
        methods=dict(sorted(method_counter.items())),
        auth_related_routes=auth_related,
        oauth_routes=oauth_related,
    )


def extract_first_match(lines: Iterable[str], pattern: re.Pattern[str]) -> str | None:
    for line in lines:
        if pattern.search(line):
            return line.strip()
    return None


def summarize_test_collection() -> TestCollectionSummary:
    command = ["pytest", "--collect-only", "-q", "tests", "-o", "addopts="]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)

    combined_output = f"{completed.stdout}\n{completed.stderr}".splitlines()
    summary_line = extract_first_match(
        combined_output,
        re.compile(r"\d+ tests collected, \d+ errors", re.IGNORECASE),
    )
    if summary_line is None:
        summary_line = "pytest collection summary not found"

    count_match = re.search(r"(\d+) tests collected, (\d+) errors", summary_line)
    if count_match:
        collected = int(count_match.group(1))
        collection_errors = int(count_match.group(2))
    else:
        collected = 0
        collection_errors = 0

    missing_plugin_pattern = re.compile(r"No module named '([^']+)'", re.IGNORECASE)
    missing_plugins: set[str] = set()
    for line in combined_output:
        plugin_match = missing_plugin_pattern.search(line)
        if plugin_match:
            missing_plugins.add(plugin_match.group(1))

    return TestCollectionSummary(
        collected=collected,
        collection_errors=collection_errors,
        missing_pytest_plugins=sorted(missing_plugins),
        raw_summary_line=summary_line,
    )


def render_markdown(baseline: Round1Baseline) -> str:
    lines: list[str] = []
    lines.append("# CIRIS Round 1 Baseline")
    lines.append("")
    lines.append(f"Generated (UTC): {baseline.generated_at_utc}")
    lines.append("")
    lines.append("## Service taxonomy")
    lines.append("")
    for category in baseline.service_taxonomy:
        lines.append(f"- **{category.category}** ({category.count}): {', '.join(category.runtime_attributes)}")
    lines.append(f"- **total**: {baseline.service_total}")
    lines.append("")
    lines.append("## Endpoint inventory")
    lines.append("")
    lines.append(f"- Total method+path routes: **{baseline.endpoint_summary.total_routes}**")
    lines.append(f"- Method split: **{baseline.endpoint_summary.methods}**")
    lines.append(f"- Auth-related routes: **{baseline.endpoint_summary.auth_related_routes}**")
    lines.append(f"- OAuth-related routes: **{baseline.endpoint_summary.oauth_routes}**")

    if baseline.test_collection is not None:
        lines.append("")
        lines.append("## Test collection")
        lines.append("")
        lines.append(f"- Collected tests: **{baseline.test_collection.collected}**")
        lines.append(f"- Collection errors: **{baseline.test_collection.collection_errors}**")
        lines.append(f"- Missing plugins observed: **{baseline.test_collection.missing_pytest_plugins}**")
        lines.append(f"- Raw summary: `{baseline.test_collection.raw_summary_line}`")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate CIRIS round-1 baseline metrics")
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip pytest collection (faster, avoids dependency-sensitive collection issues)",
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        help="Optional markdown output path",
    )
    args = parser.parse_args()

    services, total_services = summarize_services()
    endpoints = summarize_endpoints()
    test_summary = None if args.skip_tests else summarize_test_collection()

    baseline = Round1Baseline(
        generated_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        service_taxonomy=services,
        service_total=total_services,
        endpoint_summary=endpoints,
        test_collection=test_summary,
    )

    if args.markdown_out is not None:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(render_markdown(baseline), encoding="utf-8")

    print(json.dumps(asdict(baseline), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
