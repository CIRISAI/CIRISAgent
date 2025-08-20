#!/usr/bin/env python3
"""
Get Prometheus metrics from CIRIS telemetry endpoint.

Usage:
    python tools/get_prometheus.py                     # Get all metrics
    python tools/get_prometheus.py --summary           # Show summary only
    python tools/get_prometheus.py --filter system     # Filter metrics by name
    python tools/get_prometheus.py --save metrics.txt  # Save to file
    python tools/get_prometheus.py --port 8000         # Use custom port
"""

import argparse
import json
import sys
from datetime import datetime
from typing import Optional

import requests


def get_auth_token(host: str = "localhost", port: int = 8080) -> Optional[str]:
    """Get authentication token from the API."""
    try:
        response = requests.post(
            f"http://{host}:{port}/v1/auth/login",
            headers={"Content-Type": "application/json"},
            json={"username": "admin", "password": "ciris_admin_password"},
            timeout=5,
        )
        if response.status_code == 200:
            return response.json()["access_token"]
        else:
            print(f"❌ Failed to authenticate: {response.status_code}")
            return None
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to API at {host}:{port}")
        print("   Make sure the server is running: python main.py --adapter api")
        return None
    except Exception as e:
        print(f"❌ Error getting token: {e}")
        return None


def get_prometheus_metrics(token: str, host: str = "localhost", port: int = 8080) -> Optional[str]:
    """Get Prometheus metrics from the telemetry endpoint."""
    try:
        response = requests.get(
            f"http://{host}:{port}/v1/telemetry/unified?format=prometheus",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if response.status_code == 200:
            return response.text
        else:
            print(f"❌ Failed to get metrics: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Error getting metrics: {e}")
        return None


def get_json_telemetry(token: str, host: str = "localhost", port: int = 8080) -> Optional[dict]:
    """Get JSON telemetry for summary."""
    try:
        response = requests.get(
            f"http://{host}:{port}/v1/telemetry/unified", headers={"Authorization": f"Bearer {token}"}, timeout=10
        )
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except Exception:
        return None


def print_summary(metrics: str, json_data: Optional[dict] = None):
    """Print a summary of the metrics."""
    lines = metrics.split("\n")
    metric_lines = [l for l in lines if l and not l.startswith("#")]

    print("\n" + "=" * 60)
    print("📊 CIRIS TELEMETRY SUMMARY")
    print("=" * 60)

    if json_data:
        print(f"\n🟢 System Health: {'✅ HEALTHY' if json_data.get('system_healthy') else '❌ UNHEALTHY'}")
        print(f"📈 Services: {json_data.get('services_online', 0)}/{json_data.get('services_total', 0)} online")
        print(f"⚡ Error Rate: {json_data.get('overall_error_rate', 0):.2%}")
        print(f"⏱️  Uptime: {json_data.get('overall_uptime_seconds', 0):.0f} seconds")
        print(f"📝 Total Requests: {json_data.get('total_requests', 0)}")

    print(f"\n📊 Total Metrics: {len(metric_lines)}")

    # Count metrics by category
    categories = {}
    for line in metric_lines:
        if line.startswith("ciris_"):
            parts = line.split("_")
            if len(parts) >= 2:
                category = parts[1]
                categories[category] = categories.get(category, 0) + 1

    if categories:
        print("\n📂 Metrics by Category:")
        for cat, count in sorted(categories.items()):
            print(f"   • {cat}: {count}")

    # Show key metrics
    key_metrics = {}
    for line in metric_lines:
        if "ciris_system_healthy" in line:
            key_metrics["system_healthy"] = line.split()[-1]
        elif "ciris_services_online" in line and "custom" not in line:
            key_metrics["services_online"] = line.split()[-1]
        elif "ciris_services_total" in line and "custom" not in line:
            key_metrics["services_total"] = line.split()[-1]
        elif "ciris_overall_error_rate" in line:
            key_metrics["error_rate"] = line.split()[-1]

    if key_metrics:
        print("\n🎯 Key Metrics:")
        for name, value in key_metrics.items():
            print(f"   • {name}: {value}")

    print("\n" + "=" * 60)


def filter_metrics(metrics: str, filter_term: str) -> str:
    """Filter metrics by search term."""
    lines = metrics.split("\n")
    filtered = []
    for line in lines:
        if filter_term.lower() in line.lower() or line.startswith("#"):
            filtered.append(line)
    return "\n".join(filtered)


def main():
    parser = argparse.ArgumentParser(description="Get Prometheus metrics from CIRIS telemetry")
    parser.add_argument("--host", default="localhost", help="API host (default: localhost)")
    parser.add_argument("--port", type=int, default=8080, help="API port (default: 8080)")
    parser.add_argument("--summary", action="store_true", help="Show summary only")
    parser.add_argument("--filter", help="Filter metrics by term")
    parser.add_argument("--save", help="Save metrics to file")
    parser.add_argument("--count", action="store_true", help="Count metrics only")

    args = parser.parse_args()

    print(f"🔐 Authenticating with {args.host}:{args.port}...")
    token = get_auth_token(args.host, args.port)

    if not token:
        sys.exit(1)

    print("📡 Fetching metrics...")
    metrics = get_prometheus_metrics(token, args.host, args.port)

    if not metrics:
        sys.exit(1)

    # Get JSON data for summary if needed
    json_data = None
    if args.summary or args.count:
        json_data = get_json_telemetry(token, args.host, args.port)

    # Apply filter if specified
    if args.filter:
        metrics = filter_metrics(metrics, args.filter)
        print(f"🔍 Filtered for: {args.filter}")

    # Handle different output modes
    if args.count:
        lines = [l for l in metrics.split("\n") if l and not l.startswith("#")]
        print(f"\n📊 Total metrics: {len(lines)}")
    elif args.summary:
        print_summary(metrics, json_data)
    else:
        # Print full metrics
        print("\n" + "=" * 60)
        print("📊 PROMETHEUS METRICS")
        print("=" * 60)
        print(metrics)

    # Save if requested
    if args.save:
        with open(args.save, "w") as f:
            f.write(metrics)
        print(f"\n💾 Saved metrics to {args.save}")

        # Also save JSON if we have it
        if json_data:
            json_file = args.save.replace(".txt", ".json")
            with open(json_file, "w") as f:
                json.dump(json_data, f, indent=2)
            print(f"💾 Saved JSON telemetry to {json_file}")

    print("\n✅ Done!")


if __name__ == "__main__":
    main()
