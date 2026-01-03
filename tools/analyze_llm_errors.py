#!/usr/bin/env python3
"""
Analyze LLM errors from CIRIS incident logs.

Extracts rate limiting, token usage, retry patterns, and circuit breaker behavior.
"""

import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def parse_timestamp(line: str) -> datetime | None:
    """Extract timestamp from log line."""
    match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)", line)
    if match:
        return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S.%f")
    return None


def analyze_log(log_path: str) -> dict:
    """Analyze a log file for LLM errors and patterns."""

    stats = {
        "rate_limits": [],
        "circuit_breaker_events": [],
        "token_usage": [],
        "retries": [],
        "errors_by_type": defaultdict(int),
        "llm_calls": [],
        "first_timestamp": None,
        "last_timestamp": None,
    }

    with open(log_path, "r") as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        ts = parse_timestamp(line)
        if ts:
            if stats["first_timestamp"] is None:
                stats["first_timestamp"] = ts
            stats["last_timestamp"] = ts

        # Rate limit detection
        if "429" in line or "rate limit" in line.lower() or "rate_limit" in line.lower():
            # Extract token info
            token_match = re.search(r"Limit (\d+), Used (\d+), Requested (\d+)", line)
            retry_match = re.search(r"try again in ([\d.]+)s", line, re.IGNORECASE)

            stats["rate_limits"].append({
                "timestamp": ts,
                "line_num": i + 1,
                "limit": int(token_match.group(1)) if token_match else None,
                "used": int(token_match.group(2)) if token_match else None,
                "requested": int(token_match.group(3)) if token_match else None,
                "retry_after": float(retry_match.group(1)) if retry_match else None,
            })
            stats["errors_by_type"]["rate_limit_429"] += 1

        # Circuit breaker events
        if "circuit breaker" in line.lower() or "Circuit breaker" in line:
            if "opened" in line.lower() or "OPEN" in line:
                stats["circuit_breaker_events"].append({
                    "timestamp": ts,
                    "event": "OPENED",
                    "line_num": i + 1,
                    "line": line.strip()[:150],
                })
            elif "closed" in line.lower() or "reset" in line.lower():
                stats["circuit_breaker_events"].append({
                    "timestamp": ts,
                    "event": "CLOSED/RESET",
                    "line_num": i + 1,
                    "line": line.strip()[:150],
                })
            elif "skipping" in line.lower():
                stats["errors_by_type"]["circuit_breaker_skip"] += 1

        # Retry detection
        if "retry" in line.lower() and ("waiting" in line.lower() or "attempt" in line.lower()):
            retry_match = re.search(r"\((\d+)/(\d+)\)", line)
            wait_match = re.search(r"waiting ([\d.]+)s", line, re.IGNORECASE)
            stats["retries"].append({
                "timestamp": ts,
                "attempt": int(retry_match.group(1)) if retry_match else None,
                "max_attempts": int(retry_match.group(2)) if retry_match else None,
                "wait_time": float(wait_match.group(1)) if wait_match else None,
                "line_num": i + 1,
            })

        # LLM call completion
        if "LLM call completed" in line or "call_llm_structured" in line:
            stats["llm_calls"].append({
                "timestamp": ts,
                "line_num": i + 1,
                "success": "completed" in line.lower() or "success" in line.lower(),
            })

        # Error type categorization
        if "ERROR" in line:
            if "SCHEMA VALIDATION" in line:
                stats["errors_by_type"]["schema_validation"] += 1
            elif "TIMEOUT" in line:
                stats["errors_by_type"]["timeout"] += 1
            elif "503" in line or "SERVICE UNAVAILABLE" in line:
                stats["errors_by_type"]["service_unavailable_503"] += 1
            elif "401" in line or "unauthorized" in line.lower():
                stats["errors_by_type"]["unauthorized_401"] += 1
            elif "DMA" in line and "failed" in line.lower():
                stats["errors_by_type"]["dma_failure"] += 1
            elif "InstructorRetryException" in line:
                stats["errors_by_type"]["instructor_retry"] += 1

    return stats


def print_report(stats: dict, log_path: str):
    """Print a formatted analysis report."""

    print("=" * 70)
    print(f"LLM ERROR ANALYSIS REPORT")
    print(f"Log file: {log_path}")
    print("=" * 70)

    if stats["first_timestamp"] and stats["last_timestamp"]:
        duration = stats["last_timestamp"] - stats["first_timestamp"]
        print(f"\nTime Range: {stats['first_timestamp']} to {stats['last_timestamp']}")
        print(f"Duration: {duration}")

    # Rate Limits
    print("\n" + "-" * 50)
    print("RATE LIMITS (429)")
    print("-" * 50)
    if stats["rate_limits"]:
        print(f"Total rate limit hits: {len(stats['rate_limits'])}")

        # Token analysis
        token_events = [r for r in stats["rate_limits"] if r["limit"]]
        if token_events:
            print(f"\nToken Usage at Rate Limit Events:")
            for event in token_events[:10]:  # Show first 10
                pct = (event["used"] / event["limit"] * 100) if event["limit"] else 0
                print(f"  {event['timestamp']}: Used {event['used']:,}/{event['limit']:,} ({pct:.1f}%) + Requested {event['requested']:,}")
            if len(token_events) > 10:
                print(f"  ... and {len(token_events) - 10} more")

        # Retry-after times
        retry_times = [r["retry_after"] for r in stats["rate_limits"] if r["retry_after"]]
        if retry_times:
            print(f"\nRetry-After times suggested by API:")
            print(f"  Min: {min(retry_times):.2f}s")
            print(f"  Max: {max(retry_times):.2f}s")
            print(f"  Avg: {sum(retry_times)/len(retry_times):.2f}s")
    else:
        print("No rate limit events found")

    # Circuit Breaker
    print("\n" + "-" * 50)
    print("CIRCUIT BREAKER EVENTS")
    print("-" * 50)
    if stats["circuit_breaker_events"]:
        for event in stats["circuit_breaker_events"]:
            print(f"  {event['timestamp']}: {event['event']}")
            print(f"    Line {event['line_num']}: {event['line'][:100]}...")

        # Time from first rate limit to circuit breaker open
        opens = [e for e in stats["circuit_breaker_events"] if e["event"] == "OPENED"]
        if opens and stats["rate_limits"]:
            first_rl = stats["rate_limits"][0]["timestamp"]
            first_open = opens[0]["timestamp"]
            if first_rl and first_open:
                delta = first_open - first_rl
                print(f"\n  Time from first rate limit to CB open: {delta.total_seconds():.2f}s")
    else:
        print("No circuit breaker events found")

    cb_skips = stats["errors_by_type"].get("circuit_breaker_skip", 0)
    if cb_skips:
        print(f"\n  Circuit breaker skips (calls rejected): {cb_skips}")

    # Retries
    print("\n" + "-" * 50)
    print("RETRY BEHAVIOR")
    print("-" * 50)
    if stats["retries"]:
        print(f"Total retry attempts: {len(stats['retries'])}")
        wait_times = [r["wait_time"] for r in stats["retries"] if r["wait_time"]]
        if wait_times:
            print(f"Wait times used: {', '.join(f'{t}s' for t in sorted(set(wait_times)))}")
    else:
        print("No retry events found")

    # Error Summary
    print("\n" + "-" * 50)
    print("ERROR TYPE SUMMARY")
    print("-" * 50)
    if stats["errors_by_type"]:
        for error_type, count in sorted(stats["errors_by_type"].items(), key=lambda x: -x[1]):
            print(f"  {error_type}: {count}")
    else:
        print("No categorized errors found")

    # Recommendations
    print("\n" + "-" * 50)
    print("ANALYSIS & RECOMMENDATIONS")
    print("-" * 50)

    rl_count = len(stats["rate_limits"])
    cb_opens = len([e for e in stats["circuit_breaker_events"] if e["event"] == "OPENED"])

    if rl_count > 0 and cb_opens > 0:
        print("  ⚠️  Rate limits triggered circuit breaker opening")
        print("     - Fix: Rate limits should NOT count as circuit breaker failures")
        print("     - Rate limits are transient; circuit breaker is for persistent failures")

    if stats["rate_limits"]:
        avg_retry = sum(r["retry_after"] or 0 for r in stats["rate_limits"]) / max(1, len([r for r in stats["rate_limits"] if r["retry_after"]]))
        if avg_retry > 0:
            print(f"  💡 API suggests retry after ~{avg_retry:.1f}s on average")
            print(f"     - Consider setting retry wait to {max(2, avg_retry + 0.5):.1f}s")

    token_events = [r for r in stats["rate_limits"] if r["used"] and r["limit"]]
    if token_events:
        avg_usage_pct = sum(e["used"]/e["limit"]*100 for e in token_events) / len(token_events)
        print(f"  📊 Average token usage at rate limit: {avg_usage_pct:.1f}%")
        if avg_usage_pct > 90:
            print("     - Tokens nearly exhausted before rate limit")
            print("     - Consider reducing concurrent LLM calls")


def main():
    # Find the most recent log file
    log_dir = Path("logs")

    # Check for incidents_latest.log symlink or direct file
    latest_log = log_dir / "incidents_latest.log"

    if not latest_log.exists():
        # Find in sqlite subdirectory
        sqlite_logs = list((log_dir / "sqlite").glob("incidents_*.log"))
        if sqlite_logs:
            latest_log = max(sqlite_logs, key=lambda p: p.stat().st_mtime)
        else:
            # Try root logs directory
            root_logs = list(log_dir.glob("incidents_*.log"))
            if root_logs:
                latest_log = max(root_logs, key=lambda p: p.stat().st_mtime)

    if len(sys.argv) > 1:
        latest_log = Path(sys.argv[1])

    if not latest_log.exists():
        print(f"Error: Log file not found: {latest_log}")
        print("Usage: python analyze_llm_errors.py [log_file_path]")
        sys.exit(1)

    print(f"Analyzing: {latest_log}")
    stats = analyze_log(str(latest_log))
    print_report(stats, str(latest_log))


if __name__ == "__main__":
    main()
