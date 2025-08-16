#!/usr/bin/env python3
"""
Mission-Driven Development Dashboard
Shows what's implemented, what's not, and what matters most
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from core.implementation_tracker import ImplementationTracker, MetricPriority


def generate_mdd_dashboard():
    """Generate a comprehensive MDD dashboard"""
    tracker = ImplementationTracker()
    tracker.update_implementation_status()

    conn = tracker.conn
    cursor = conn.cursor()

    print("=" * 80)
    print("MISSION-DRIVEN DEVELOPMENT DASHBOARD")
    print("Telemetry Implementation Status")
    print("=" * 80)

    # 1. Mission-Critical Metrics (What directly serves M-1)
    print("\n🎯 MISSION-CRITICAL METRICS (Direct User Flourishing)")
    print("-" * 60)

    cursor.execute(
        """
        SELECT module_name, metric_name, status, endpoint_path
        FROM endpoints
        WHERE priority = 'MISSION_CRITICAL'
        ORDER BY module_name, metric_name
    """
    )

    mission_critical = cursor.fetchall()
    implemented_mc = sum(1 for row in mission_critical if row[2] == "IMPLEMENTED")

    print(
        f"Status: {implemented_mc}/{len(mission_critical)} implemented ({implemented_mc/len(mission_critical)*100:.1f}%)\n"
    )

    for module, metric, status, endpoint in mission_critical[:10]:
        status_icon = "✅" if status == "IMPLEMENTED" else "❌"
        print(f"{status_icon} {module}: {metric}")
        print(f"   {endpoint}")

    if len(mission_critical) > 10:
        print(f"\n... and {len(mission_critical) - 10} more mission-critical metrics")

    # 2. Mission-Supporting Metrics (Required for mission to work)
    print("\n🛡️ MISSION-SUPPORTING METRICS (Safety & Reliability)")
    print("-" * 60)

    cursor.execute(
        """
        SELECT module_name, metric_name, status, endpoint_path
        FROM endpoints
        WHERE priority = 'MISSION_SUPPORTING'
        ORDER BY module_name, metric_name
    """
    )

    supporting = cursor.fetchall()
    implemented_sup = sum(1 for row in supporting if row[2] == "IMPLEMENTED")

    print(f"Status: {implemented_sup}/{len(supporting)} implemented ({implemented_sup/len(supporting)*100:.1f}%)\n")

    # Group by category
    safety_metrics = [r for r in supporting if "error" in r[1].lower() or "timeout" in r[1].lower()]
    auth_metrics = [r for r in supporting if "auth" in r[1].lower() or "permission" in r[1].lower()]
    resource_metrics = [r for r in supporting if "resource" in r[1].lower() or "memory" in r[1].lower()]

    print(f"Safety (errors/timeouts): {sum(1 for r in safety_metrics if r[2] == 'IMPLEMENTED')}/{len(safety_metrics)}")
    print(f"Auth & Permissions: {sum(1 for r in auth_metrics if r[2] == 'IMPLEMENTED')}/{len(auth_metrics)}")
    print(f"Resource Management: {sum(1 for r in resource_metrics if r[2] == 'IMPLEMENTED')}/{len(resource_metrics)}")

    # 3. Module Readiness
    print("\n📦 MODULE READINESS FOR DEPLOYMENT")
    print("-" * 60)

    cursor.execute(
        """
        SELECT
            module_name,
            total_metrics,
            implemented,
            mission_critical_done,
            mission_critical_total,
            CASE
                WHEN mission_critical_total = 0 THEN 100.0
                ELSE mission_critical_done * 100.0 / mission_critical_total
            END as mc_completion
        FROM implementation_stats
        ORDER BY mc_completion DESC, implemented DESC
    """
    )

    modules = cursor.fetchall()

    print(f"{'Module':<30} {'Total':>8} {'Impl':>8} {'MC Done':>10} {'Ready?':>10}")
    print("-" * 70)

    for module, total, impl, mc_done, mc_total, mc_comp in modules[:15]:
        ready = "✅ READY" if mc_comp == 100 and impl > 0 else "⚠️ PENDING" if mc_comp > 0 else "❌ NOT READY"
        module_short = module[:28] + ".." if len(module) > 30 else module
        print(f"{module_short:<30} {total:>8} {impl:>8} {mc_done}/{mc_total:>3} {ready:>10}")

    # 4. Implementation Path
    print("\n🚀 IMPLEMENTATION PATH (Next 10 Steps)")
    print("-" * 60)

    cursor.execute(
        """
        SELECT module_name, metric_name, priority, metric_type
        FROM endpoints
        WHERE status = 'NOT_IMPLEMENTED'
        ORDER BY
            CASE priority
                WHEN 'MISSION_CRITICAL' THEN 1
                WHEN 'MISSION_SUPPORTING' THEN 2
                WHEN 'OPERATIONAL' THEN 3
                ELSE 4
            END,
            module_name
        LIMIT 10
    """
    )

    next_steps = cursor.fetchall()

    for i, (module, metric, priority, mtype) in enumerate(next_steps, 1):
        priority_badge = {"MISSION_CRITICAL": "🎯", "MISSION_SUPPORTING": "🛡️", "OPERATIONAL": "⚙️"}.get(priority, "📊")

        print(f"{i:2}. {priority_badge} {module}: {metric} ({mtype})")

    # 5. Quick Stats
    print("\n📊 QUICK STATS")
    print("-" * 60)

    cursor.execute(
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'IMPLEMENTED' THEN 1 ELSE 0 END) as impl,
            SUM(CASE WHEN priority = 'MISSION_CRITICAL' THEN 1 ELSE 0 END) as mc,
            SUM(CASE WHEN priority = 'MISSION_SUPPORTING' THEN 1 ELSE 0 END) as ms,
            SUM(CASE WHEN priority = 'OPERATIONAL' THEN 1 ELSE 0 END) as op
        FROM endpoints
    """
    )

    total, impl, mc, ms, op = cursor.fetchone()

    print(f"Total Telemetry Endpoints: {total}")
    print(f"Currently Implemented: {impl} ({impl/total*100:.1f}%)")
    print(f"")
    print(f"By Priority:")
    print(f"  Mission-Critical: {mc} endpoints")
    print(f"  Mission-Supporting: {ms} endpoints")
    print(f"  Operational: {op} endpoints")

    # 6. The Real Question
    print("\n" + "=" * 80)
    print("THE REAL QUESTION: Can the agent know itself and be trusted?")
    print("=" * 80)

    # Self-knowledge metrics
    cursor.execute(
        """
        SELECT COUNT(*) FROM endpoints
        WHERE metric_name LIKE '%self_%' OR metric_name LIKE '%observation_%'
        OR module_name LIKE '%SELF_OBSERVATION%'
    """
    )
    self_knowledge = cursor.fetchone()[0]

    # Trust metrics
    cursor.execute(
        """
        SELECT COUNT(*) FROM endpoints
        WHERE metric_name LIKE '%audit_%' OR metric_name LIKE '%transparency_%'
        OR metric_name LIKE '%trust_%' OR module_name LIKE '%AUDIT%'
    """
    )
    trust_metrics = cursor.fetchone()[0]

    print(f"\n🪞 Self-Knowledge Metrics: {self_knowledge} defined")
    print(f"🤝 Trust & Transparency Metrics: {trust_metrics} defined")

    if impl == 0:
        print("\n⚠️ No telemetry endpoints are currently implemented.")
        print("   The agent cannot yet observe itself or provide transparency.")
    else:
        print(f"\n✅ {impl} endpoints implemented - the foundation for self-knowledge exists.")

    print("\n" + "=" * 80)

    return {
        "total": total,
        "implemented": impl,
        "mission_critical": mc,
        "mission_supporting": ms,
        "operational": op,
        "ready_modules": sum(1 for m in modules if m[5] == 100),
    }


if __name__ == "__main__":
    stats = generate_mdd_dashboard()

    # Save summary to file
    summary_path = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/mdd_summary.json")
    import json

    summary_path.write_text(json.dumps(stats, indent=2))

    print(f"\n📁 Summary saved to: {summary_path}")
