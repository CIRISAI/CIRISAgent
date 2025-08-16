#!/usr/bin/env python3
"""
Validate telemetry guide endpoints against actual implementation.
"""

import json
import sys
from typing import Dict, List, Tuple

# Endpoints claimed in the telemetry guide
CLAIMED_ENDPOINTS = [
    # System Telemetry
    ("GET", "/system/health"),
    ("GET", "/system/time"),
    ("GET", "/system/resources"),
    ("GET", "/system/services"),
    # Service Registry
    ("GET", "/telemetry/service-registry"),
    # Memory & Graph
    ("GET", "/memory/stats"),
    ("GET", "/memory/timeline"),
    ("GET", "/memory/scopes/{scope}/nodes"),
    # LLM & Resources
    ("GET", "/telemetry/llm/usage"),
    ("GET", "/telemetry/circuit-breakers"),
    # Audit & Security
    ("GET", "/audit/recent"),
    ("GET", "/telemetry/security/incidents"),
    # Agent State
    ("GET", "/visibility/cognitive-state"),
    ("GET", "/visibility/thoughts"),
    ("GET", "/visibility/system-snapshot"),
    # Processing Queue
    ("GET", "/runtime/queue/status"),
    ("GET", "/telemetry/handlers"),
    # Incidents
    ("GET", "/incidents/recent"),
    # WebSocket
    ("WS", "/ws/telemetry"),
    # Manager Endpoints (different base)
    ("GET", "/manager/v1/health"),
    ("GET", "/manager/v1/updates/status"),
    ("GET", "/manager/v1/telemetry/all"),
    # Aggregates
    ("GET", "/telemetry/aggregates/hourly"),
    ("GET", "/telemetry/summary/daily"),
    # Advanced
    ("POST", "/memory/graph/query"),
    ("GET", "/telemetry/export"),
    ("GET", "/metrics"),  # Prometheus format
    # Diagnostics
    ("GET", "/telemetry/errors"),
    ("GET", "/telemetry/traces/{trace_id}"),
    # Rate Limits
    ("GET", "/telemetry/rate-limits"),
    # Special
    ("GET", "/telemetry/tsdb/status"),
    ("GET", "/telemetry/discord/status"),
    # History
    ("GET", "/telemetry/history"),
    ("GET", "/telemetry/backups"),
]

# Actual endpoints found in codebase
ACTUAL_ENDPOINTS = [
    # System routes
    ("GET", "/system/health"),
    ("GET", "/system/time"),
    ("GET", "/system/resources"),
    ("GET", "/system/services"),
    ("POST", "/system/runtime/{action}"),
    ("POST", "/system/shutdown"),
    ("GET", "/system/adapters"),
    ("GET", "/system/tools"),
    # System extensions
    ("GET", "/system/runtime/queue"),
    ("POST", "/system/runtime/single-step"),
    ("GET", "/system/services/health"),
    ("PUT", "/system/services/{provider_name}/priority"),
    ("POST", "/system/services/circuit-breakers/reset"),
    ("GET", "/system/services/selection-logic"),
    ("GET", "/system/processors"),
    # Telemetry routes
    ("GET", "/telemetry/overview"),
    ("GET", "/telemetry/resources"),
    ("GET", "/telemetry/metrics"),
    ("GET", "/telemetry/traces"),
    ("GET", "/telemetry/logs"),
    ("POST", "/telemetry/query"),
    ("GET", "/telemetry/metrics/{metric_name}"),
    ("GET", "/telemetry/resources/history"),
    # Memory routes
    ("POST", "/memory/store"),
    ("POST", "/memory/query"),
    ("DELETE", "/memory/{node_id}"),
    ("GET", "/memory/timeline"),
    ("GET", "/memory/recall/{node_id}"),
    ("GET", "/memory/stats"),
    ("GET", "/memory/{node_id}"),
    ("GET", "/memory/visualize/graph"),
    ("POST", "/memory/edges"),
    ("GET", "/memory/{node_id}/edges"),
    # Audit routes
    ("GET", "/audit/entries"),
    ("GET", "/audit/entries/{entry_id}"),
    ("POST", "/audit/search"),
    ("POST", "/audit/verify/{entry_id}"),
    ("POST", "/audit/export"),
    # Agent routes
    ("POST", "/agent/interact"),
    ("GET", "/agent/history"),
    ("GET", "/agent/status"),
    ("GET", "/agent/identity"),
    ("GET", "/agent/channels"),
    # WA routes
    ("GET", "/wa/deferrals"),
    ("POST", "/wa/deferrals/{deferral_id}/resolve"),
    ("GET", "/wa/permissions"),
    ("GET", "/wa/status"),
    ("POST", "/wa/guidance"),
    # Transparency routes
    ("GET", "/transparency/feed"),
    ("GET", "/transparency/policy"),
    ("GET", "/transparency/status"),
]


def check_endpoint_existence():
    """Check which claimed endpoints actually exist."""

    # Convert actual endpoints to a set for quick lookup
    actual_set = set(ACTUAL_ENDPOINTS)

    # Normalize claimed endpoints (remove parameters for comparison)
    claimed_normalized = []
    for method, path in CLAIMED_ENDPOINTS:
        # Skip manager and WS endpoints (different routing)
        if path.startswith("/manager") or path.startswith("/ws"):
            continue
        # Remove path parameters for comparison
        normalized_path = path.replace("/{scope}", "/{param}").replace("/{trace_id}", "/{param}")
        claimed_normalized.append((method, normalized_path))

    results = {"exists": [], "missing": [], "undocumented": []}

    # Check claimed endpoints
    for method, path in claimed_normalized:
        # Try to find exact or similar match
        found = False
        for actual_method, actual_path in actual_set:
            if method == actual_method:
                if path == actual_path or path.replace("{param}", "{node_id}") == actual_path:
                    found = True
                    results["exists"].append((method, path))
                    break

        if not found:
            results["missing"].append((method, path))

    # Find undocumented endpoints
    claimed_paths = set(p for _, p in claimed_normalized)
    for method, path in ACTUAL_ENDPOINTS:
        normalized = path.replace("{node_id}", "{param}").replace("{entry_id}", "{param}")
        if normalized not in claimed_paths and path not in claimed_paths:
            results["undocumented"].append((method, path))

    return results


def main():
    """Run validation and generate report."""

    print("=" * 60)
    print("TELEMETRY GUIDE ENDPOINT VALIDATION REPORT")
    print("=" * 60)

    results = check_endpoint_existence()

    print(f"\n✅ EXISTING ENDPOINTS ({len(results['exists'])})")
    print("-" * 40)
    for method, path in sorted(results["exists"]):
        print(f"  {method:6} {path}")

    print(f"\n❌ MISSING ENDPOINTS ({len(results['missing'])})")
    print("-" * 40)
    for method, path in sorted(results["missing"]):
        print(f"  {method:6} {path}")

    print(f"\n📝 UNDOCUMENTED BUT AVAILABLE ({len(results['undocumented'])})")
    print("-" * 40)
    for method, path in sorted(results["undocumented"][:20]):  # Limit output
        print(f"  {method:6} {path}")

    # Summary
    total_claimed = len(
        [e for e in CLAIMED_ENDPOINTS if not e[1].startswith("/manager") and not e[1].startswith("/ws")]
    )
    exists_count = len(results["exists"])
    missing_count = len(results["missing"])

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total Claimed Endpoints: {total_claimed}")
    print(f"Verified Existing:       {exists_count}")
    print(f"Missing Implementation:  {missing_count}")
    print(f"Success Rate:           {(exists_count/total_claimed)*100:.1f}%")

    # Recommendations
    print("\n" + "=" * 60)
    print("RECOMMENDATIONS")
    print("=" * 60)

    if results["missing"]:
        print("\n1. Missing endpoints that need implementation or guide correction:")
        for method, path in results["missing"][:5]:
            print(f"   - {method} {path}")

    if results["undocumented"]:
        print("\n2. Available endpoints to add to guide:")
        for method, path in results["undocumented"][:5]:
            print(f"   - {method} {path}")

    # Write detailed report
    with open("telemetry_validation_report.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nDetailed report saved to: telemetry_validation_report.json")

    return 0 if missing_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
