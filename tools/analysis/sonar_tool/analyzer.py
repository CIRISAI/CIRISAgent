"""Coverage and quality analysis utilities."""

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class FileImpact:
    """Represents a file's impact on coverage and quality."""

    path: str
    coverage: float
    uncovered_lines: int
    potential_coverage_gain: float
    tech_debt_minutes: int
    complexity_score: int
    priority_score: float


class CoverageAnalyzer:
    """Analyzes coverage data to identify high-impact improvements."""

    def __init__(self, client):
        self.client = client

    def analyze_coverage_opportunities(self) -> Dict[str, Any]:
        """Comprehensive analysis of coverage improvement opportunities."""
        # Get overall metrics
        metrics = self.client.get_coverage_metrics()

        # Get uncovered files
        uncovered_files = self.client.get_uncovered_files(limit=100)

        # Get tech debt files
        tech_debt_files = self.client.get_tech_debt_files(limit=50)

        # Combine and prioritize
        file_impacts = self._calculate_file_impacts(uncovered_files, tech_debt_files)

        # Group by package/module
        package_analysis = self._analyze_by_package(file_impacts)

        # Identify quick wins
        quick_wins = self._find_quick_wins(file_impacts)

        # Calculate effort vs impact
        strategic_targets = self._prioritize_strategic_targets(file_impacts)

        return {
            "current_coverage": float(metrics.get("coverage", 0)),
            "lines_to_cover": int(metrics.get("lines_to_cover", 0)),
            "uncovered_lines": int(metrics.get("uncovered_lines", 0)),
            "coverage_gap": 80.0 - float(metrics.get("coverage", 0)),
            "top_uncovered_files": uncovered_files[:10],
            "high_tech_debt_files": tech_debt_files[:10],
            "package_analysis": package_analysis,
            "quick_wins": quick_wins,
            "strategic_targets": strategic_targets,
            "estimated_files_to_80_percent": self._estimate_files_needed(file_impacts, metrics),
        }

    def _calculate_file_impacts(self, uncovered_files: List[Dict], tech_debt_files: List[Dict]) -> List[FileImpact]:
        """Calculate impact score for each file."""
        # Create tech debt lookup
        debt_lookup = {f["path"]: f for f in tech_debt_files}

        impacts = []
        for file in uncovered_files:
            path = file["path"]
            debt_info = debt_lookup.get(path, {})

            # Calculate potential coverage gain
            uncovered = file["uncovered_lines"]
            total_uncovered = sum(f["uncovered_lines"] for f in uncovered_files)
            potential_gain = (uncovered / total_uncovered * 100) if total_uncovered > 0 else 0

            # Calculate priority score (higher = more important)
            # Factors: low current coverage, high uncovered lines, high tech debt
            coverage_factor = (100 - file["coverage"]) / 100
            size_factor = min(uncovered / 100, 1.0)  # Normalize to 0-1
            debt_factor = min(debt_info.get("tech_debt_minutes", 0) / 1000, 1.0)

            priority = (coverage_factor * 0.4 + size_factor * 0.4 + debt_factor * 0.2) * 100

            impacts.append(
                FileImpact(
                    path=path,
                    coverage=file["coverage"],
                    uncovered_lines=uncovered,
                    potential_coverage_gain=potential_gain,
                    tech_debt_minutes=debt_info.get("tech_debt_minutes", 0),
                    complexity_score=debt_info.get("cognitive_complexity", 0),
                    priority_score=priority,
                )
            )

        return sorted(impacts, key=lambda x: x.priority_score, reverse=True)

    def _analyze_by_package(self, file_impacts: List[FileImpact]) -> Dict[str, Any]:
        """Group files by package/module for strategic planning."""
        packages = {}

        for impact in file_impacts:
            # Extract package from path
            parts = impact.path.split("/")
            if len(parts) > 2 and parts[0] == "ciris_engine":
                package = "/".join(parts[:3])  # e.g., ciris_engine/logic/adapters
            else:
                package = parts[0] if parts else "root"

            if package not in packages:
                packages[package] = {
                    "files": 0,
                    "total_uncovered_lines": 0,
                    "avg_coverage": 0,
                    "total_tech_debt_minutes": 0,
                }

            packages[package]["files"] += 1
            packages[package]["total_uncovered_lines"] += impact.uncovered_lines
            packages[package]["avg_coverage"] += impact.coverage
            packages[package]["total_tech_debt_minutes"] += impact.tech_debt_minutes

        # Calculate averages
        for package in packages.values():
            if package["files"] > 0:
                package["avg_coverage"] /= package["files"]

        # Sort by impact
        sorted_packages = sorted(
            [(k, v) for k, v in packages.items()], key=lambda x: x[1]["total_uncovered_lines"], reverse=True
        )

        return dict(sorted_packages[:10])

    def _find_quick_wins(self, file_impacts: List[FileImpact]) -> List[Dict[str, Any]]:
        """Identify files that are easy to improve."""
        quick_wins = []

        for impact in file_impacts:
            # Quick win criteria:
            # - Low coverage but small file
            # - Low complexity
            # - High impact relative to effort
            if impact.coverage < 30 and impact.uncovered_lines < 100 and impact.complexity_score < 20:

                quick_wins.append(
                    {
                        "path": impact.path,
                        "coverage": impact.coverage,
                        "uncovered_lines": impact.uncovered_lines,
                        "estimated_hours": impact.uncovered_lines / 20,  # Pre-AI estimate
                        "ai_hours": impact.uncovered_lines / 300,  # AI-accelerated (÷15)
                        "coverage_gain": impact.potential_coverage_gain,
                    }
                )

        return sorted(quick_wins, key=lambda x: x["coverage_gain"], reverse=True)[:10]

    def _prioritize_strategic_targets(self, file_impacts: List[FileImpact]) -> List[Dict[str, Any]]:
        """Identify strategic files for maximum impact."""
        targets = []

        for impact in file_impacts[:30]:  # Top 30 by priority
            effort_estimate = self._estimate_effort(impact)
            roi = impact.potential_coverage_gain / effort_estimate if effort_estimate > 0 else 0

            targets.append(
                {
                    "path": impact.path,
                    "current_coverage": impact.coverage,
                    "uncovered_lines": impact.uncovered_lines,
                    "tech_debt_minutes": impact.tech_debt_minutes,
                    "estimated_effort_hours": effort_estimate,
                    "ai_effort_hours": effort_estimate / 15,  # AI-accelerated
                    "coverage_gain": impact.potential_coverage_gain,
                    "roi_score": roi * 15,  # Adjust ROI for AI speed
                    "priority_score": impact.priority_score,
                }
            )

        return sorted(targets, key=lambda x: x["roi_score"], reverse=True)[:15]

    def _estimate_effort(self, impact: FileImpact) -> float:
        """Estimate hours needed to improve coverage."""
        # Base: 1 hour per 20 uncovered lines
        base_hours = impact.uncovered_lines / 20

        # Complexity multiplier
        if impact.complexity_score > 50:
            complexity_mult = 2.0
        elif impact.complexity_score > 30:
            complexity_mult = 1.5
        else:
            complexity_mult = 1.0

        # Tech debt multiplier
        debt_mult = 1 + (impact.tech_debt_minutes / 1000) * 0.1

        return base_hours * complexity_mult * debt_mult

    def _estimate_files_needed(self, file_impacts: List[FileImpact], metrics: Dict[str, Any]) -> int:
        """Estimate how many files need work to reach 80% coverage."""
        current = float(metrics.get("coverage", 0))
        total_lines = int(metrics.get("lines_to_cover", 0))

        if current >= 80.0:
            return 0

        # Calculate lines needed
        target_covered = total_lines * 0.8
        current_covered = total_lines * (current / 100)
        lines_needed = int(target_covered - current_covered)

        # Count files until we have enough lines
        lines_accumulated = 0
        files_needed = 0

        for impact in file_impacts:
            if lines_accumulated >= lines_needed:
                break
            lines_accumulated += impact.uncovered_lines
            files_needed += 1

        return files_needed
