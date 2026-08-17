#!/usr/bin/env python3
"""
CIRIS MyPy Toolkit CLI - Command-line interface for the toolkit

Usage:
    python -m ciris_mypy_toolkit.cli analyze              # Analyze compliance
    python -m ciris_mypy_toolkit.cli fix --systematic     # Fix all issues systematically
    python -m ciris_mypy_toolkit.cli validate adapter.py  # Validate specific adapter
    python -m ciris_mypy_toolkit.cli report               # Generate compliance report
    python -m ciris_mypy_toolkit.cli simplify_engine      # Generate engine simplification proposals
"""

import logging
import sys

import click

from .analyzers.engine_simplifier import generate_engine_simplification_proposals
from .core import CIRISMypyToolkit

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Initialize toolkit globally for all commands
TOOLKIT = CIRISMypyToolkit("ciris_engine", "ciris_engine/schemas")


@click.group()
def main():
    """CIRIS MyPy Toolkit - Ensure schema and protocol compliance"""
    pass


@main.command()
def analyze():
    """Execute compliance analysis."""
    print(" CIRIS Compliance Analysis")
    print("=" * 50)
    analysis = TOOLKIT.analyze_compliance()
    print("\n MyPy Type Safety:")
    print(f"   Total Errors: {analysis['total_mypy_errors']}")
    if analysis["error_categories"]:
        print("   Error Categories:")
        for category, errors in analysis["error_categories"].items():
            print(f"     • {category}: {len(errors)} errors")
    print("\n Schema Compliance:")
    print(f"   Issues Found: {analysis['schema_compliance']['total_issues']}")
    print("\n Protocol Compliance:")
    print(f"   Issues Found: {analysis['protocol_compliance']['total_issues']}")
    print("\n Code Quality:")
    print(f"   Unused Code Items: {analysis['unused_code']['total_items']}")
    if analysis["recommendations"]:
        print("\n Recommendations:")
        for rec in analysis["recommendations"]:
            print(f"   • {rec}")


@main.command()
@click.option("--categories", multiple=True, default=["type_annotations"], help="Categories to propose fixes for.")
@click.option("--output", default="proposed_fixes.json", help="Output file for proposals.")
def propose(categories, output):
    """Execute proposal generation for agent review."""
    print(" CIRIS Fix Proposal Generation")
    print("=" * 45)
    initial_errors = len(TOOLKIT.get_mypy_errors())
    print(f"Current mypy errors: {initial_errors}")
    proposal_file = TOOLKIT.propose_fixes(list(categories), output)
    print(f"\n Proposal generated: {proposal_file}")
    print(" AGENT: Please review the proposed changes in the file.")
    print(f" To execute: python -m ciris_mypy_toolkit execute --target {proposal_file}")


@main.command()
@click.option("--target", required=True, help="Proposal file to execute.")
def execute(target):
    """Execute fixes from an approved proposal file."""
    print(" Executing Approved Fixes")
    print("=" * 35)
    print(f"Proposal file: {target}")
    import pathlib

    if not pathlib.Path(target).exists():
        logger.error(f"Proposal file {target} not found")
        sys.exit(1)
    results = TOOLKIT.execute_approved_fixes(target)
    print("\n[OK] Execution Results:")
    for category, count in results.items():
        if count > 0:
            print(f"   • {category}: {count} fixes applied")
    final_errors = len(TOOLKIT.get_mypy_errors())
    print("\n Final Status:")
    print(f"   • Current mypy errors: {final_errors}")
    if final_errors == 0:
        print(" ZERO ERRORS ACHIEVED!")


@main.command()
@click.argument("target")
def validate(target):
    """Execute adapter validation."""
    import pathlib

    print(f" Validating Adapter: {target}")
    print("=" * 50)
    results = TOOLKIT.validate_adapter_compliance(str(pathlib.Path(target)))
    if "error" in results:
        print(f"[FAIL] Error: {results['error']}")
        return
    print(f" Compliance Score: {results['compliance_score']:.1%}")
    print(f" Schema Usage: {'[OK]' if results['schema_usage']['compliant'] else '[FAIL]'}")
    print(f" Protocol Implementation: {'[OK]' if results['protocol_implementation']['protocol_compliant'] else '[FAIL]'}")
    print(f" Type Safety: {'[OK]' if results['type_safety']['type_safe'] else '[FAIL]'}")
    if results.get("recommendations"):
        print("\n Recommendations:")
        for rec in results["recommendations"]:
            print(f"   • {rec}")


@main.command()
@click.option("--output", default=None, help="Output file for the report.")
def report(output):
    """Generate compliance report."""
    report = TOOLKIT.generate_compliance_report(output)
    if output:
        print(f"Report written to: {output}")
    else:
        print(report)


@main.command()
@click.option(
    "--output",
    default="ciris_mypy_toolkit/reports/engine_simplification_proposals.json",
    help="Output file for the simplification proposals.",
)
def simplify_engine(output):
    """Generate engine simplification proposals using the hot/cold path map."""
    engine_root = "ciris_engine"
    hot_cold_map_path = "ciris_mypy_toolkit/reports/hot_cold_path_map.json"
    generate_engine_simplification_proposals(engine_root, hot_cold_map_path, output)
    print(f"Engine simplification proposals written to {output}")


@main.command()
def list_protocols():
    """List all protocols found in the codebase."""
    print(" CIRIS Protocol Inventory")
    print("=" * 50)

    from ciris_mypy_toolkit.analyzers.protocol_analyzer import ProtocolAnalyzer

    analyzer = ProtocolAnalyzer("ciris_engine")
    categorized = analyzer.list_all_protocols()

    total_protocols = sum(len(protocols) for protocols in categorized.values())

    print("\n Protocol Summary:")
    print(f"   Total Protocols: {total_protocols}")
    print(f"   Service Protocols: {len(categorized['service_protocols'])}")
    print(f"   Handler Protocols: {len(categorized['handler_protocols'])}")
    print(f"   Adapter Protocols: {len(categorized['adapter_protocols'])}")
    print(f"   DMA Protocols: {len(categorized['dma_protocols'])}")
    print(f"   Processor Protocols: {len(categorized['processor_protocols'])}")
    print(f"   Other Protocols: {len(categorized['other_protocols'])}")

    for category, protocols in categorized.items():
        if protocols:
            print(f"\n {category.replace('_', ' ').title()}:")
            for protocol in protocols:
                print(f"   • {protocol}")


@main.command()
@click.option("--service", help="Specific service to check (e.g., 'AuditService')")
@click.option("--output", help="Output file for detailed report")
def check_protocols(service, output):
    """Check protocol-module-schema alignment (Protocol-First Pattern)."""
    print(" Protocol-Module-Schema Alignment Check")
    print("=" * 50)

    from ciris_mypy_toolkit.analyzers.protocol_analyzer import ProtocolAnalyzer

    analyzer = ProtocolAnalyzer("ciris_engine")

    if service:
        # Check specific service
        service_results = analyzer.check_service_alignment(service)
        # Wrap single service results in the expected format
        results = {
            "total_services": 1,
            "aligned_services": 1 if service_results["is_aligned"] else 0,
            "misaligned_services": 0 if service_results["is_aligned"] else 1,
            "no_untyped_dicts": service_results["no_untyped_dicts"],
            "issues": service_results["issues"],
            "services": {service: service_results},
        }
    else:
        # Check all services
        results = analyzer.check_all_services()

    # Display summary
    print("\n Protocol Alignment Summary:")
    print(f"   Total Services: {results['total_services']}")
    print(f" [OK] Fully Aligned: {results['aligned_services']}")
    print(f" [WARN] Misaligned: {results['misaligned_services']}")
    print(f" No Dict[str, Any]: {'[OK]' if results['no_untyped_dicts'] else '[FAIL]'}")

    if results["issues"]:
        print("\n[WARN] Issues Found:")
        for issue in results["issues"][:10]:  # Show first 10 issues
            print(f"   • {issue['service']}: {issue['message']}")
        if len(results["issues"]) > 10:
            print(f"   ... and {len(results['issues']) - 10} more issues")

    if output:
        import json

        with open(output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\n Detailed report written to: {output}")

    # Exit with error if misaligned
    if results["misaligned_services"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
