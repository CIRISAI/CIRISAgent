#!/usr/bin/env python3
"""
CIRIS Database Tools CLI

A comprehensive command-line interface for database analysis and maintenance.
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from .audit_verifier import AuditVerifierWrapper
from .consolidation_monitor import ConsolidationMonitor
from .graph_analyzer import GraphAnalyzer
from .status_reporter import DBStatusReporter
from .storage_analyzer import StorageAnalyzer
from .tsdb_analyzer import TSDBAnalyzer


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="CIRIS Database Tools - Analysis and Maintenance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  status          Overall database status
  tsdb            TSDB consolidation analysis
  tsdb-age        TSDB node age analysis
  audit           Audit trail status
  verify          Audit trail verification
  orphaned        Find orphaned nodes
  connectivity    Graph connectivity analysis
  consolidation   Consolidation health report
  gaps            Find consolidation gaps
  comprehensive   COMPREHENSIVE analysis with orphaned nodes, storage, edges
  storage         Detailed storage analysis

Examples:
  %(prog)s status                    # Full status report
  %(prog)s tsdb                      # TSDB consolidation status
  %(prog)s orphaned                  # Find nodes without edges
  %(prog)s verify --sample 1000      # Verify sample of audit entries
  %(prog)s consolidation             # Check consolidation health
  %(prog)s comprehensive             # Complete analysis with critical issues
        """,
    )

    parser.add_argument(
        "command",
        choices=[
            "status",
            "tsdb",
            "tsdb-age",
            "audit",
            "verify",
            "orphaned",
            "connectivity",
            "consolidation",
            "gaps",
            "comprehensive",
            "storage",
        ],
        help="Command to run",
    )

    parser.add_argument("--db-path", help="Path to main database (default: auto-detect)")

    parser.add_argument("--sample", type=int, help="Sample size for verification (verify command only)")

    parser.add_argument("--limit", type=int, default=100, help="Limit for orphaned nodes display (default: 100)")

    args = parser.parse_args()

    try:
        # Execute commands
        if args.command == "status":
            reporter = DBStatusReporter(args.db_path)
            reporter.print_full_report()

        elif args.command == "tsdb":
            analyzer = TSDBAnalyzer(args.db_path)
            analyzer.print_report()

        elif args.command == "tsdb-age":
            analyzer = TSDBAnalyzer(args.db_path)
            age_analysis = analyzer.get_node_age_analysis()

            from .base import ReportFormatter

            formatter = ReportFormatter()
            formatter.print_section("TSDB NODE AGE ANALYSIS")

            print("\nTSDB Data Nodes:")
            nodes = age_analysis["tsdb_data_nodes"]
            print(f"  Total: {nodes['total']:,}")
            print(f"  Within 30h (expected): {nodes['within_30h']:,}")
            print(f"  30-36h (pending): {nodes['between_30_36h']:,}")
            print(f"  Over 36h (overdue): {nodes['over_36h']:,}")

            print("\nBasic Summaries:")
            summaries = age_analysis["basic_summaries"]
            print(f"  Total: {summaries['total']:,}")
            print(f"  Within 7d: {summaries['within_7d']:,}")
            print(f"  7-15d: {summaries['over_7d']:,}")
            print(f"  Over 15d: {summaries['over_15d']:,}")

            if age_analysis["recommendations"]:
                print("\nRecommendations:")
                for rec in age_analysis["recommendations"]:
                    print(f"  [{rec['severity']}] {rec['issue']}")
                    print(f"    → {rec['action']}")

        elif args.command == "audit":
            verifier = AuditVerifierWrapper(args.db_path)
            verifier.print_audit_report()

        elif args.command == "verify":
            verifier = AuditVerifierWrapper(args.db_path)
            verifier.print_verification_report(args.sample)

        elif args.command == "orphaned":
            analyzer = GraphAnalyzer(args.db_path)
            analyzer.print_orphaned_nodes_report()

        elif args.command == "connectivity":
            analyzer = GraphAnalyzer(args.db_path)
            analyzer.print_connectivity_report()

        elif args.command == "consolidation":
            monitor = ConsolidationMonitor(args.db_path)
            monitor.print_consolidation_health_report()

        elif args.command == "gaps":
            monitor = ConsolidationMonitor(args.db_path)
            gaps = monitor.get_consolidation_gaps()

            from .base import ReportFormatter

            formatter = ReportFormatter()
            formatter.print_section("CONSOLIDATION GAP ANALYSIS")

            for level, stats in gaps["expected_vs_actual"].items():
                print(f"\n{level.capitalize()} Level:")
                print(f"  Expected: {stats['expected']}")
                print(f"  Actual: {stats['actual']}")
                print(f"  Coverage: {stats['coverage']:.1f}%")

            if gaps["basic_gaps"]:
                print(f"\nFound {len(gaps['basic_gaps'])} missing basic periods")
                for gap in gaps["basic_gaps"][:10]:
                    print(f"  {gap['period_start'][:16]} - Age: {gap['age']}")
                if len(gaps["basic_gaps"]) > 10:
                    print(f"  ... and {len(gaps['basic_gaps']) - 10} more")

        elif args.command == "comprehensive":
            monitor = ConsolidationMonitor(args.db_path)
            monitor.print_comprehensive_analysis()

        elif args.command == "storage":
            storage = StorageAnalyzer(args.db_path)
            storage.print_comprehensive_storage_report()

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
