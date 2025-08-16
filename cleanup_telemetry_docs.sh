#!/bin/bash

# Script to remove outdated telemetry documentation
# Created for v1.4.3 cleanup

echo "Removing outdated telemetry documentation..."

# Remove auto-generated service telemetry docs
echo "Removing ciris_engine/docs/telemetry/ directory..."
rm -rf ciris_engine/docs/telemetry/

# Remove outdated planning/analysis docs
echo "Removing outdated planning docs..."
rm -f docs/MODULE_TELEMETRY_DOCUMENTATION_PLAN.md
rm -f docs/TELEMETRY_DOCUMENTATION_MODULES.md
rm -f docs/TELEMETRY_GAP_ANALYSIS.md
rm -f docs/TELEMETRY_GUIDE_VALIDATION_PLAN.md
rm -f docs/TELEMETRY_SPIKE_TODO.md
rm -f docs/GROUND_TRUTH_TELEMETRY_AUDIT.md
rm -f docs/TELEMETRY_SUCCESS_AUDIT.md
rm -f docs/CIRISAGENT_TELEMETRY_GUIDE.md

# Remove old telemetry tool reports (keeping only current ones)
echo "Removing outdated telemetry tool reports..."
rm -f tools/telemetry_tool/COMPLETE_METRICS_REPORT.md
rm -f tools/telemetry_tool/ENTERPRISE_TAXONOMY.md
rm -f tools/telemetry_tool/FINAL_CLEAN_METRICS_REPORT.md
rm -f tools/telemetry_tool/FINAL_PROGRESS_REPORT.md
rm -f tools/telemetry_tool/FINAL_VERIFICATION_REPORT.md
rm -f tools/telemetry_tool/GET_TELEMETRY_IMPLEMENTATION_GUIDE.md
rm -f tools/telemetry_tool/gpt5_summary.md
rm -f tools/telemetry_tool/implementation_guide.md
rm -f tools/telemetry_tool/IMPLEMENTATION_SUMMARY.md
rm -f tools/telemetry_tool/METRIC_IMPLEMENTATION_ROADMAP.md
rm -f tools/telemetry_tool/METRICS_REALITY_REPORT.md
rm -f tools/telemetry_tool/METRIC_TAXONOMY.md
rm -f tools/telemetry_tool/SCANNER_SUCCESS_REPORT.md
rm -f tools/telemetry_tool/SCORING_SUMMARY.md
rm -f tools/telemetry_tool/SEMANTIC_SCORING_TODO.md
rm -f tools/telemetry_tool/SEMANTIC_TODO.md
rm -f tools/telemetry_tool/SYSTEMATIC_PROGRESS.md
rm -f tools/telemetry_tool/TELEMETRY_IMPLEMENTATION_PLAN.md
rm -f tools/telemetry_tool/TELEMETRY_REALITY_REPORT.md
rm -f tools/telemetry_tool/UNIFIED_TELEMETRY_COMPLETE.md

# Remove score reports
rm -rf tools/telemetry_tool/scores/

# Remove test metrics summary
rm -f tests/METRICS_TEST_SUMMARY.md

# Remove SDK telemetry complete (replaced by SDK README)
rm -f SDK_TELEMETRY_ACCESS_COMPLETE.md

echo "Cleanup complete!"
echo ""
echo "Kept the following important telemetry docs:"
echo "  - docs/TELEMETRY_SYSTEM.md (main architecture)"
echo "  - FSD/TELEMETRY.md (functional spec)"
echo "  - API.md (API endpoints)"
echo "  - README.md (main readme)"
echo "  - RELEASE_NOTES_1.4.2.md (recent release)"
echo "  - tools/telemetry_tool/TELEMETRY_COVERAGE_REPORT.md (current coverage)"
echo ""
echo "Run 'git status' to see all removed files"
