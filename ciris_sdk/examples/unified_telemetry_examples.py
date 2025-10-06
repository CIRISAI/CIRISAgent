"""
Examples of using the CIRISClient SDK to access unified telemetry.

The unified telemetry endpoint provides easy access to ALL 436+ metrics
from 22 services through a single, optimized endpoint.
"""
# mypy: disable-error-code="index,operator,union-attr,arg-type"

import asyncio

from ciris_sdk import CIRISClient


async def example_basic_usage() -> None:
    """Basic examples of accessing telemetry."""
    async with CIRISClient() as client:
        # 1. Quick health check
        health = await client.telemetry.check_system_health()
        print(f"System healthy: {health['healthy']}")
        print(f"Services: {health['services']['online']}/{health['services']['total']}")

        # 2. Executive summary
        summary = await client.telemetry.get_unified_telemetry()
        print(f"Error rate: {summary['overall_error_rate']:.2%}")
        print(f"Uptime: {summary['overall_uptime_seconds'] / 3600:.1f} hours")

        # 3. Get ALL metrics
        all_metrics = await client.telemetry.get_all_metrics()
        print(f"Total metrics available: {len(str(all_metrics))}")


async def example_specific_metrics() -> None:
    """Access specific metrics by path."""
    async with CIRISClient() as client:
        # Get specific metrics using dot notation
        cpu = await client.telemetry.get_metric_by_path("infrastructure.resource_monitor.cpu_percent")
        print(f"CPU usage: {cpu}%")

        llm_tokens = await client.telemetry.get_metric_by_path("runtime.llm.tokens_used")
        print(f"LLM tokens used: {llm_tokens:,}")

        memory_nodes = await client.telemetry.get_metric_by_path("graph_services.memory.total_nodes")
        print(f"Memory graph nodes: {memory_nodes:,}")


async def example_filtered_views() -> None:
    """Get filtered views of telemetry data."""
    async with CIRISClient() as client:
        # Performance metrics only
        perf = await client.telemetry.get_unified_telemetry(view="performance")
        print(f"Avg latency: {perf['performance']['avg_latency_ms']}ms")
        print(f"Throughput: {perf['performance']['throughput_rps']} req/s")

        # Reliability metrics
        reliability = await client.telemetry.get_unified_telemetry(view="reliability")
        print(f"Uptime: {reliability['uptime_seconds'] / 86400:.1f} days")
        print(f"Error rate: {reliability['error_rate']:.4%}")

        # Operational view with live data (bypass cache)
        ops = await client.telemetry.get_unified_telemetry(view="operational", live=True)
        print(f"Alerts: {ops.get('alerts', [])}")
        print(f"Warnings: {ops.get('warnings', [])}")


async def example_category_filtering() -> None:
    """Get metrics for specific service categories."""
    async with CIRISClient() as client:
        # Bus metrics only
        buses = await client.telemetry.get_unified_telemetry(view="detailed", category="buses")
        print("Message Bus Metrics:")
        for bus_name, metrics in buses.get("buses", {}).items():
            print(f"  {bus_name}: {metrics.get('request_count', 0)} requests")

        # Infrastructure metrics
        infra = await client.telemetry.get_unified_telemetry(view="detailed", category="infrastructure")
        print("\nInfrastructure Metrics:")
        resource = infra.get("infrastructure", {}).get("resource_monitor", {})
        print(f"  CPU: {resource.get('cpu_percent', 0)}%")
        print(f"  Memory: {resource.get('memory_mb', 0)} MB")

        # Graph services
        graph = await client.telemetry.get_unified_telemetry(view="detailed", category="graph")
        print("\nGraph Service Metrics:")
        for service, metrics in graph.get("graph_services", {}).items():
            print(f"  {service}: {metrics}")


async def example_export_formats() -> None:
    """Export telemetry in different formats."""
    async with CIRISClient() as client:
        # Prometheus format for monitoring systems
        prometheus = await client.telemetry.get_unified_telemetry(format="prometheus")
        print("Prometheus metrics (first 500 chars):")
        print(prometheus[:500])

        # Graphite format
        graphite = await client.telemetry.get_unified_telemetry(format="graphite")
        print("\nGraphite metrics (first 500 chars):")
        print(graphite[:500])


async def example_monitoring_loop() -> None:
    """Example of continuous monitoring."""
    async with CIRISClient() as client:
        print("Starting monitoring loop (Ctrl+C to stop)...")

        while True:
            try:
                # Get live metrics
                metrics = await client.telemetry.get_unified_telemetry(view="summary", live=True)

                # Check for issues
                if not metrics["system_healthy"]:
                    print("⚠️  SYSTEM UNHEALTHY!")

                if metrics.get("alerts"):
                    print(f"🚨 ALERTS: {metrics['alerts']}")

                if metrics.get("warnings"):
                    print(f"⚠️  Warnings: {metrics['warnings']}")

                # Display key metrics
                print(
                    f"Services: {metrics['services_online']}/{metrics['services_total']} | "
                    f"Error rate: {metrics['overall_error_rate']:.2%} | "
                    f"Uptime: {metrics['overall_uptime_seconds'] / 3600:.1f}h"
                )

                # Wait 30 seconds
                await asyncio.sleep(30)

            except KeyboardInterrupt:
                print("\nMonitoring stopped.")
                break
            except Exception as e:
                print(f"Error: {e}")
                await asyncio.sleep(30)


async def example_comprehensive_report() -> None:
    """Generate a comprehensive telemetry report."""
    async with CIRISClient() as client:
        # Get all data
        data = await client.telemetry.get_all_metrics()

        print("=" * 60)
        print("CIRIS TELEMETRY REPORT")
        print("=" * 60)

        # System Overview
        print("\n📊 SYSTEM OVERVIEW")
        print(f"  Health: {'✅ Healthy' if data['system_healthy'] else '❌ Unhealthy'}")
        print(f"  Services: {data['services_online']}/{data['services_total']} online")
        print(f"  Error Rate: {data['overall_error_rate']:.3%}")
        print(f"  Uptime: {data['overall_uptime_seconds'] / 86400:.2f} days")

        # Performance
        perf = data.get("performance", {})
        if perf:
            print("\n⚡ PERFORMANCE")
            print(f"  Avg Latency: {perf.get('avg_latency_ms', 'N/A')}ms")
            print(f"  Throughput: {perf.get('throughput_rps', 'N/A')} req/s")
            print(f"  Cache Hit Rate: {perf.get('cache_hit_rate', 0):.1%}")

        # Buses
        buses = data.get("buses", {})
        if buses:
            print("\n🚌 MESSAGE BUSES")
            for bus, metrics in buses.items():
                if isinstance(metrics, dict):
                    print(f"  {bus}:")
                    print(f"    Healthy: {metrics.get('healthy', False)}")
                    print(f"    Requests: {metrics.get('request_count', 0):,}")

        # Resources
        infra = data.get("infrastructure", {})
        if infra and "resource_monitor" in infra:
            rm = infra["resource_monitor"]
            print("\n💻 RESOURCES")
            print(f"  CPU: {rm.get('cpu_percent', 0)}%")
            print(f"  Memory: {rm.get('memory_mb', 0):,} MB")
            print(f"  Disk: {rm.get('disk_percent', 0)}%")

        # Alerts & Warnings
        if data.get("alerts") or data.get("warnings"):
            print("\n⚠️  ISSUES")
            for alert in data.get("alerts", []):
                print(f"  🚨 ALERT: {alert}")
            for warning in data.get("warnings", []):
                print(f"  ⚠️  Warning: {warning}")

        print("\n" + "=" * 60)


async def main() -> None:
    """Run all examples."""
    print("🚀 CIRIS Unified Telemetry SDK Examples\n")

    examples = [
        ("Basic Usage", example_basic_usage),
        ("Specific Metrics", example_specific_metrics),
        ("Filtered Views", example_filtered_views),
        ("Category Filtering", example_category_filtering),
        ("Export Formats", example_export_formats),
        ("Comprehensive Report", example_comprehensive_report),
    ]

    for name, func in examples:
        print(f"\n{'='*60}")
        print(f"Example: {name}")
        print("=" * 60)
        try:
            await func()
        except Exception as e:
            print(f"Error in {name}: {e}")

    # Optional: Run monitoring loop
    # await example_monitoring_loop()


if __name__ == "__main__":
    asyncio.run(main())
