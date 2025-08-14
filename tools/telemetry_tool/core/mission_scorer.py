"""
Mission Alignment Scoring Engine

Evaluates telemetry metrics against CIRIS covenant principles and Meta-Goal M-1.
Scores each metric and module for alignment with adaptive coherence.
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


class MissionScorer:
    """Score telemetry metrics for mission alignment with M-1: Adaptive Coherence"""

    def __init__(self):
        # Covenant principles for scoring
        self.covenant_principles = {
            "beneficence": self._score_beneficence,
            "non_maleficence": self._score_non_maleficence,
            "transparency": self._score_transparency,
            "autonomy": self._score_autonomy,
            "justice": self._score_justice,
            "coherence": self._score_coherence,
        }

        # Critical keywords that indicate mission alignment
        self.mission_keywords = {
            "beneficence": ["help", "assist", "support", "benefit", "enable", "empower", "positive"],
            "non_maleficence": ["safety", "protect", "prevent", "secure", "guard", "shield", "harm"],
            "transparency": ["audit", "log", "trace", "observe", "visibility", "report", "explain"],
            "autonomy": ["choice", "consent", "control", "permission", "opt", "configure", "preference"],
            "justice": ["fair", "equal", "unbiased", "balanced", "inclusive", "accessible", "equitable"],
            "coherence": ["consistent", "stable", "reliable", "sustainable", "adaptive", "resilient"],
        }

    def score_module(self, module_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Score an entire module for mission alignment.

        Returns scores for each covenant principle (0.0 - 1.0)
        """
        scores = {}

        # Score each principle based on module data
        for principle, score_func in self.covenant_principles.items():
            scores[f"{principle}_score"] = score_func(module_data)

        # Calculate overall mission alignment
        scores["mission_alignment"] = sum(scores.values()) / len(scores)

        return scores

    def score_metric(self, metric: Dict[str, Any], module_context: Dict[str, Any]) -> Dict[str, float]:
        """
        Score an individual metric for mission alignment.

        Args:
            metric: The metric data from telemetry doc
            module_context: The module this metric belongs to

        Returns:
            Dictionary of scores for each principle
        """
        scores = {}

        # Analyze metric characteristics
        metric_name = metric.get("metric_name", "").lower()
        metric_type = metric.get("metric_type", "").lower()
        access_pattern = metric.get("access_pattern", "WARM")
        storage = metric.get("storage_location", "").lower()

        # Score based on metric properties
        scores["beneficence"] = self._score_metric_beneficence(metric_name, metric_type)
        scores["non_maleficence"] = self._score_metric_non_maleficence(metric_name, storage)
        scores["transparency"] = self._score_metric_transparency(metric_name, storage)
        scores["autonomy"] = self._score_metric_autonomy(metric_name, metric_type)
        scores["justice"] = self._score_metric_justice(metric_name, access_pattern)
        scores["coherence"] = self._score_metric_coherence(access_pattern, storage)

        # Apply module context boost
        module_type = module_context.get("module_type", "")
        if module_type == "SERVICE" and "governance" in module_context.get("doc_path", ""):
            # Governance services get higher scores for oversight metrics
            for principle in ["transparency", "non_maleficence", "justice"]:
                scores[principle] = min(1.0, scores[principle] * 1.2)

        return scores

    def _score_beneficence(self, module_data: Dict[str, Any]) -> float:
        """Score module for beneficence - actively doing good"""
        score = 0.0

        # Check overview for beneficence keywords
        overview = module_data.get("overview", "").lower()
        for keyword in self.mission_keywords["beneficence"]:
            if keyword in overview:
                score += 0.15

        # Bonus for user-facing services
        if "communication" in module_data.get("module_name", "").lower():
            score += 0.3
        if "tool" in module_data.get("module_name", "").lower():
            score += 0.2

        # Check for positive action metrics
        metrics = module_data.get("metrics", [])
        positive_metrics = [
            m
            for m in metrics
            if any(kw in m.get("metric_name", "").lower() for kw in ["success", "complete", "help", "assist"])
        ]
        if positive_metrics:
            score += 0.2 * (len(positive_metrics) / max(1, len(metrics)))

        return min(1.0, score)

    def _score_non_maleficence(self, module_data: Dict[str, Any]) -> float:
        """Score module for non-maleficence - avoiding harm"""
        score = 0.0

        # Check for safety and protection mechanisms
        overview = module_data.get("overview", "").lower()
        for keyword in self.mission_keywords["non_maleficence"]:
            if keyword in overview:
                score += 0.15

        # High score for security and filter services
        module_name = module_data.get("module_name", "").lower()
        if "filter" in module_name or "security" in module_name:
            score += 0.4
        if "authentication" in module_name:
            score += 0.3

        # Check for error handling metrics
        metrics = module_data.get("metrics", [])
        safety_metrics = [
            m
            for m in metrics
            if any(kw in m.get("metric_name", "").lower() for kw in ["error", "fail", "block", "reject", "limit"])
        ]
        if safety_metrics:
            score += 0.2 * (len(safety_metrics) / max(1, len(metrics)))

        return min(1.0, score)

    def _score_transparency(self, module_data: Dict[str, Any]) -> float:
        """Score module for transparency - openness and explainability"""
        score = 0.0

        # Check for transparency keywords
        overview = module_data.get("overview", "").lower()
        for keyword in self.mission_keywords["transparency"]:
            if keyword in overview:
                score += 0.15

        # High score for audit and telemetry services
        module_name = module_data.get("module_name", "").lower()
        if "audit" in module_name or "telemetry" in module_name:
            score += 0.5
        if "visibility" in module_name or "observation" in module_name:
            score += 0.4

        # Check for logging/tracking metrics
        metrics = module_data.get("metrics", [])
        transparency_metrics = [
            m
            for m in metrics
            if any(kw in m.get("metric_name", "").lower() for kw in ["log", "track", "record", "audit", "trace"])
        ]
        if transparency_metrics:
            score += 0.2 * (len(transparency_metrics) / max(1, len(metrics)))

        # Bonus for graph storage (permanent record)
        if module_data.get("storage_info", {}).get("graph_storage"):
            score += 0.1

        return min(1.0, score)

    def _score_autonomy(self, module_data: Dict[str, Any]) -> float:
        """Score module for autonomy - respecting user choice"""
        score = 0.0

        # Check for autonomy keywords
        overview = module_data.get("overview", "").lower()
        for keyword in self.mission_keywords["autonomy"]:
            if keyword in overview:
                score += 0.15

        # High score for configuration and control services
        module_name = module_data.get("module_name", "").lower()
        if "config" in module_name or "control" in module_name:
            score += 0.4
        if "permission" in module_name or "auth" in module_name:
            score += 0.3

        # Check for user control metrics
        metrics = module_data.get("metrics", [])
        autonomy_metrics = [
            m
            for m in metrics
            if any(kw in m.get("metric_name", "").lower() for kw in ["user", "choice", "preference", "opt", "consent"])
        ]
        if autonomy_metrics:
            score += 0.2 * (len(autonomy_metrics) / max(1, len(metrics)))

        return min(1.0, score)

    def _score_justice(self, module_data: Dict[str, Any]) -> float:
        """Score module for justice - fairness and equity"""
        score = 0.0

        # Check for justice keywords
        overview = module_data.get("overview", "").lower()
        for keyword in self.mission_keywords["justice"]:
            if keyword in overview:
                score += 0.15

        # High score for wise authority and governance
        module_name = module_data.get("module_name", "").lower()
        if "wise" in module_name or "authority" in module_name:
            score += 0.5
        if "governance" in module_data.get("doc_path", ""):
            score += 0.2

        # Check for fairness metrics
        metrics = module_data.get("metrics", [])
        justice_metrics = [
            m
            for m in metrics
            if any(kw in m.get("metric_name", "").lower() for kw in ["fair", "equal", "balance", "priority", "queue"])
        ]
        if justice_metrics:
            score += 0.2 * (len(justice_metrics) / max(1, len(metrics)))

        return min(1.0, score)

    def _score_coherence(self, module_data: Dict[str, Any]) -> float:
        """Score module for coherence - consistency and sustainability"""
        score = 0.0

        # Check for coherence keywords
        overview = module_data.get("overview", "").lower()
        for keyword in self.mission_keywords["coherence"]:
            if keyword in overview:
                score += 0.15

        # High score for memory and persistence services
        module_name = module_data.get("module_name", "").lower()
        if "memory" in module_name or "persistence" in module_name:
            score += 0.4
        if "circuit" in module_name or "resilient" in module_name:
            score += 0.3

        # Check HOT/WARM/COLD distribution for sustainability
        hot = module_data.get("hot_metrics", 0)
        warm = module_data.get("warm_metrics", 0)
        cold = module_data.get("cold_metrics", 0)
        total = hot + warm + cold

        if total > 0:
            # Ideal distribution: mostly WARM (sustainable), some HOT (critical), some COLD (historical)
            warm_ratio = warm / total
            if 0.4 <= warm_ratio <= 0.7:
                score += 0.3  # Good balance
            elif warm_ratio > 0.7:
                score += 0.2  # Too much WARM
            else:
                score += 0.1  # Too much HOT or COLD

        # Check for reliability metrics
        metrics = module_data.get("metrics", [])
        coherence_metrics = [
            m
            for m in metrics
            if any(
                kw in m.get("metric_name", "").lower() for kw in ["uptime", "stable", "consistent", "health", "status"]
            )
        ]
        if coherence_metrics:
            score += 0.2 * (len(coherence_metrics) / max(1, len(metrics)))

        return min(1.0, score)

    def _score_metric_beneficence(self, metric_name: str, metric_type: str) -> float:
        """Score individual metric for beneficence"""
        score = 0.3  # Base score

        # Positive indicators
        if any(kw in metric_name for kw in ["success", "complete", "help", "enable"]):
            score += 0.4
        if metric_type == "counter" and "success" in metric_name:
            score += 0.3

        return min(1.0, score)

    def _score_metric_non_maleficence(self, metric_name: str, storage: str) -> float:
        """Score individual metric for non-maleficence"""
        score = 0.3  # Base score

        # Safety indicators
        if any(kw in metric_name for kw in ["error", "fail", "block", "limit", "reject"]):
            score += 0.4
        if "graph" in storage:  # Permanent record of issues
            score += 0.2

        return min(1.0, score)

    def _score_metric_transparency(self, metric_name: str, storage: str) -> float:
        """Score individual metric for transparency"""
        score = 0.2  # Base score

        # Transparency indicators
        if any(kw in metric_name for kw in ["log", "audit", "trace", "record"]):
            score += 0.5
        if "graph" in storage or "persistent" in storage:
            score += 0.3

        return min(1.0, score)

    def _score_metric_autonomy(self, metric_name: str, metric_type: str) -> float:
        """Score individual metric for autonomy"""
        score = 0.2  # Base score

        # User control indicators
        if any(kw in metric_name for kw in ["user", "choice", "config", "preference"]):
            score += 0.5
        if metric_type == "gauge" and "setting" in metric_name:
            score += 0.3

        return min(1.0, score)

    def _score_metric_justice(self, metric_name: str, access_pattern: str) -> float:
        """Score individual metric for justice"""
        score = 0.3  # Base score

        # Fairness indicators
        if any(kw in metric_name for kw in ["fair", "equal", "priority", "queue"]):
            score += 0.4
        if access_pattern == "HOT":  # Real-time fairness monitoring
            score += 0.2

        return min(1.0, score)

    def _score_metric_coherence(self, access_pattern: str, storage: str) -> float:
        """Score individual metric for coherence"""
        score = 0.3  # Base score

        # Sustainability indicators
        if access_pattern == "WARM":  # Most sustainable
            score += 0.4
        elif access_pattern == "COLD":  # Good for historical
            score += 0.2
        else:  # HOT - use sparingly
            score += 0.1

        if "graph" in storage or "persistent" in storage:
            score += 0.2

        return min(1.0, score)

    def get_mission_critical_metrics(
        self, modules: List[Dict[str, Any]], threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Identify mission-critical metrics that strongly align with M-1.

        Args:
            modules: List of parsed module data
            threshold: Minimum score to be considered mission-critical

        Returns:
            List of mission-critical metrics with scores
        """
        critical_metrics = []

        for module in modules:
            module_scores = self.score_module(module)

            for metric in module.get("metrics", []):
                metric_scores = self.score_metric(metric, module)

                # Calculate overall mission score
                mission_score = sum(metric_scores.values()) / len(metric_scores)

                if mission_score >= threshold:
                    critical_metrics.append(
                        {
                            "module": module.get("module_name"),
                            "metric": metric.get("metric_name"),
                            "access_pattern": metric.get("access_pattern"),
                            "mission_score": mission_score,
                            "scores": metric_scores,
                            "reasoning": self._explain_criticality(metric, metric_scores),
                        }
                    )

        # Sort by mission score
        critical_metrics.sort(key=lambda x: x["mission_score"], reverse=True)

        return critical_metrics

    def _explain_criticality(self, metric: Dict[str, Any], scores: Dict[str, float]) -> str:
        """Generate explanation for why a metric is mission-critical"""

        # Find highest scoring principles
        top_principles = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:2]

        explanations = {
            "beneficence": "actively enables positive outcomes",
            "non_maleficence": "prevents harm and ensures safety",
            "transparency": "provides essential visibility",
            "autonomy": "respects user choice and control",
            "justice": "ensures fairness and equity",
            "coherence": "maintains system sustainability",
        }

        metric_name = metric.get("metric_name", "metric")
        reasons = [explanations[p] for p, _ in top_principles]

        return f"{metric_name} {reasons[0]} and {reasons[1]}"
