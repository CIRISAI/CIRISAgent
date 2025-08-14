#!/usr/bin/env python3
"""
Pure Semantic Scorer - Just the scores, no recommendations

This tool ONLY:
1. Gets semantic scores from GPT-4
2. Identifies modules above/below 0.6
3. Flags concerning scores
4. Does NOT make recommendations
5. Does NOT suggest features
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.doc_parser import TelemetryDocParser
from core.semantic_evaluator import SemanticMissionEvaluator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PureSemanticScorer:
    """Pure scoring without recommendations"""

    def __init__(self):
        self.evaluator = SemanticMissionEvaluator()
        self.parser = TelemetryDocParser()

        # Output directory
        self.scores_dir = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/scores")
        self.scores_dir.mkdir(exist_ok=True)

    async def score_all_modules(self):
        """Score all modules semantically without bias"""

        print("=" * 80)
        print("PURE SEMANTIC SCORING WITH GPT-5")
        print("Getting unbiased scores from GPT-5")
        print("=" * 80)

        # Parse all documentation
        print("\n📚 Loading telemetry documentation...")
        modules = self.parser.parse_all_docs()
        print(f"✓ Found {len(modules)} modules to score")

        # Prepare for evaluation
        eval_modules = []
        for module in modules:
            eval_modules.append(
                {
                    "module_name": module["module_name"],
                    "module_type": module["module_type"],
                    "doc_path": module["doc_path"],
                    "module_path": module.get("module_path"),
                }
            )

        # Run semantic scoring
        print(f"\n🧠 Getting semantic scores from GPT-5...")
        print(f"This will take a few minutes...")

        all_scores = []
        batch_size = 10

        for i in range(0, len(eval_modules), batch_size):
            batch = eval_modules[i : i + batch_size]
            print(f"  Scoring batch {i//batch_size + 1}/{(len(eval_modules)-1)//batch_size + 1}...")

            batch_results = await self.evaluator.evaluate_all_modules(batch, max_concurrent=5)
            all_scores.extend(batch_results)

            if i + batch_size < len(eval_modules):
                await asyncio.sleep(2)  # Brief pause between batches

        print(f"✓ Scored all {len(all_scores)} modules")

        # Analyze scores
        self._analyze_scores(all_scores)

        # Save results
        self._save_scores(all_scores)

        return all_scores

    def _analyze_scores(self, scores: List[Dict]):
        """Analyze scores without making recommendations"""

        print("\n" + "=" * 80)
        print("SCORING RESULTS")
        print("=" * 80)

        # Calculate statistics
        passing = [s for s in scores if s.get("mission_alignment_score", 0) >= 0.6]
        failing = [s for s in scores if s.get("mission_alignment_score", 0) < 0.6]

        print(f"\n📊 Score Distribution:")
        print(f"  • Modules Scored: {len(scores)}")
        print(f"  • Passing (≥0.6): {len(passing)} ({len(passing)/len(scores)*100:.1f}%)")
        print(f"  • Below 0.6: {len(failing)} ({len(failing)/len(scores)*100:.1f}%)")

        # System averages
        print(f"\n📈 System Averages:")
        principles = ["beneficence", "non_maleficence", "transparency", "autonomy", "justice", "coherence"]
        for principle in principles:
            avg = sum(s.get(f"{principle}_score", 0) for s in scores) / len(scores)
            print(f"  • {principle.title()}: {avg:.3f}")

        overall_avg = sum(s.get("mission_alignment_score", 0) for s in scores) / len(scores)
        print(f"  • Overall Mission: {overall_avg:.3f}")

        # Red flags (just identify, don't recommend)
        print(f"\n🚩 Red Flags:")
        critical_count = 0
        for score in scores:
            for principle in principles:
                if score.get(f"{principle}_score", 1) < 0.2:
                    print(
                        f"  • {score['module_name']}: {principle} = {score.get(f'{principle}_score', 0):.2f} (CRITICAL)"
                    )
                    critical_count += 1

        if critical_count == 0:
            print("  • No critical issues (all principles ≥0.2)")

        # Modules needing attention (just list them)
        print(f"\n⚠️ Modules Below 0.6:")
        for score in sorted(failing, key=lambda x: x.get("mission_alignment_score", 0))[:10]:
            print(f"  • {score['module_name']}: {score.get('mission_alignment_score', 0):.3f}")

        # Top performers (for reference)
        print(f"\n✅ Top Scoring Modules:")
        for score in sorted(scores, key=lambda x: x.get("mission_alignment_score", 0), reverse=True)[:5]:
            print(f"  • {score['module_name']}: {score.get('mission_alignment_score', 0):.3f}")

    def _save_scores(self, scores: List[Dict]):
        """Save scores to files"""

        # Save raw scores
        with open(self.scores_dir / "semantic_scores.json", "w") as f:
            json.dump(scores, f, indent=2, default=str)

        # Create score matrix CSV
        with open(self.scores_dir / "score_matrix.csv", "w") as f:
            # Header
            f.write("Module,Type,Beneficence,Non-maleficence,Transparency,Autonomy,Justice,Coherence,Overall,Status\n")

            # Data rows
            for score in scores:
                status = "PASS" if score.get("mission_alignment_score", 0) >= 0.6 else "BELOW_0.6"
                f.write(f"{score['module_name']},")
                f.write(f"{score.get('module_type', 'UNKNOWN')},")
                f.write(f"{score.get('beneficence_score', 0):.3f},")
                f.write(f"{score.get('non_maleficence_score', 0):.3f},")
                f.write(f"{score.get('transparency_score', 0):.3f},")
                f.write(f"{score.get('autonomy_score', 0):.3f},")
                f.write(f"{score.get('justice_score', 0):.3f},")
                f.write(f"{score.get('coherence_score', 0):.3f},")
                f.write(f"{score.get('mission_alignment_score', 0):.3f},")
                f.write(f"{status}\n")

        # Create red flags file
        red_flags = []
        principles = ["beneficence", "non_maleficence", "transparency", "autonomy", "justice", "coherence"]

        for score in scores:
            module_flags = []

            # Check for critical scores
            for principle in principles:
                p_score = score.get(f"{principle}_score", 1)
                if p_score < 0.2:
                    module_flags.append({"severity": "CRITICAL", "principle": principle, "score": p_score})
                elif p_score < 0.4:
                    module_flags.append({"severity": "HIGH", "principle": principle, "score": p_score})

            # Check overall score
            overall = score.get("mission_alignment_score", 1)
            if overall < 0.4:
                module_flags.append({"severity": "HIGH", "principle": "overall", "score": overall})

            if module_flags:
                red_flags.append({"module": score["module_name"], "flags": module_flags})

        with open(self.scores_dir / "red_flags.json", "w") as f:
            json.dump(red_flags, f, indent=2)

        # Create simple pass/fail report
        with open(self.scores_dir / "pass_fail_report.md", "w") as f:
            f.write("# Semantic Scoring Report\n\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n\n")

            f.write("## Summary\n\n")
            passing = [s for s in scores if s.get("mission_alignment_score", 0) >= 0.6]
            failing = [s for s in scores if s.get("mission_alignment_score", 0) < 0.6]

            f.write(f"- Total Modules: {len(scores)}\n")
            f.write(f"- Passing (≥0.6): {len(passing)}\n")
            f.write(f"- Below 0.6: {len(failing)}\n")
            f.write(f"- Pass Rate: {len(passing)/len(scores)*100:.1f}%\n\n")

            f.write("## Modules ≥0.6\n\n")
            for score in sorted(passing, key=lambda x: x.get("mission_alignment_score", 0), reverse=True):
                f.write(f"- {score['module_name']}: {score.get('mission_alignment_score', 0):.3f}\n")

            f.write("\n## Modules <0.6\n\n")
            for score in sorted(failing, key=lambda x: x.get("mission_alignment_score", 0)):
                f.write(f"- {score['module_name']}: {score.get('mission_alignment_score', 0):.3f}\n")

            f.write("\n## Red Flags\n\n")
            if red_flags:
                for flag in red_flags:
                    f.write(f"### {flag['module']}\n")
                    for issue in flag["flags"]:
                        f.write(f"- {issue['severity']}: {issue['principle']} = {issue['score']:.3f}\n")
                    f.write("\n")
            else:
                f.write("No critical issues detected.\n")

        print(f"\n📁 Scores saved to: {self.scores_dir}")
        print(f"  • semantic_scores.json - Raw scoring data")
        print(f"  • score_matrix.csv - Scoring matrix")
        print(f"  • red_flags.json - Issues to review")
        print(f"  • pass_fail_report.md - Summary report")


async def main():
    """Run pure semantic scoring"""

    scorer = PureSemanticScorer()
    scores = await scorer.score_all_modules()

    print("\n" + "=" * 80)
    print("SCORING COMPLETE")
    print("=" * 80)
    print("\nThis was pure semantic scoring.")
    print("No recommendations. No assumptions.")
    print("Just unbiased evaluation of mission alignment.")

    return scores


if __name__ == "__main__":
    asyncio.run(main())
