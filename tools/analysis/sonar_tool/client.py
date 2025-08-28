"""SonarCloud API client with enhanced functionality."""

from typing import Any, Dict, List, Optional

import requests


class SonarClient:
    """Enhanced SonarCloud API client."""

    def __init__(self, token: str):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        self.api_base = "https://sonarcloud.io/api"
        self.project_key = "CIRISAI_CIRISAgent"

    def search_issues(
        self, severity: Optional[str] = None, resolved: bool = False, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Search for issues in the project."""
        params = {"componentKeys": self.project_key, "resolved": str(resolved).lower(), "ps": limit}

        if severity:
            params["severities"] = severity

        response = self.session.get(f"{self.api_base}/issues/search", params=params)
        response.raise_for_status()
        return response.json().get("issues", [])

    def get_coverage_metrics(self) -> Dict[str, Any]:
        """Get detailed coverage metrics."""
        metrics = "coverage,lines_to_cover,uncovered_lines,line_coverage,branch_coverage"
        params = {"component": self.project_key, "metricKeys": metrics}

        response = self.session.get(f"{self.api_base}/measures/component", params=params)
        response.raise_for_status()

        data = response.json()
        measures = {m["metric"]: m.get("value", 0) for m in data["component"]["measures"]}
        return measures

    def get_uncovered_files(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get files with lowest coverage."""
        params = {
            "component": self.project_key,
            "metricKeys": "coverage,ncloc,uncovered_lines",
            "strategy": "leaves",
            "s": "metric",
            "metricSort": "coverage",
            "asc": "true",
            "ps": limit,
        }

        response = self.session.get(f"{self.api_base}/measures/component_tree", params=params)
        response.raise_for_status()

        components = response.json().get("components", [])

        # Parse and enrich the data
        files = []
        for comp in components:
            measures = {m["metric"]: float(m.get("value", 0)) for m in comp.get("measures", [])}

            if "coverage" in measures:
                files.append(
                    {
                        "path": comp["path"],
                        "coverage": measures.get("coverage", 0),
                        "lines": int(measures.get("ncloc", 0)),
                        "uncovered_lines": int(measures.get("uncovered_lines", 0)),
                    }
                )

        return files

    def get_tech_debt_files(self, limit: int = 30) -> List[Dict[str, Any]]:
        """Get files with highest technical debt."""
        params = {
            "component": self.project_key,
            "metricKeys": "sqale_index,code_smells,cognitive_complexity",
            "strategy": "leaves",
            "s": "metric",
            "metricSort": "sqale_index",
            "asc": "false",
            "ps": limit,
        }

        response = self.session.get(f"{self.api_base}/measures/component_tree", params=params)
        response.raise_for_status()

        components = response.json().get("components", [])

        files = []
        for comp in components:
            measures = {m["metric"]: float(m.get("value", 0)) for m in comp.get("measures", [])}

            if measures.get("sqale_index", 0) > 0:
                files.append(
                    {
                        "path": comp["path"],
                        "tech_debt_minutes": int(measures.get("sqale_index", 0)),
                        "code_smells": int(measures.get("code_smells", 0)),
                        "cognitive_complexity": int(measures.get("cognitive_complexity", 0)),
                    }
                )

        return files

    def get_quality_gate_status(self) -> Dict[str, Any]:
        """Get quality gate details."""
        params = {"projectKey": self.project_key}

        response = self.session.get(f"{self.api_base}/qualitygates/project_status", params=params)
        response.raise_for_status()
        return response.json()["projectStatus"]

    def get_hotspots(self, status: str = "TO_REVIEW", limit: int = 20) -> List[Dict[str, Any]]:
        """Get security hotspots."""
        params = {"projectKey": self.project_key, "status": status, "ps": limit}

        response = self.session.get(f"{self.api_base}/hotspots/search", params=params)
        response.raise_for_status()
        return response.json().get("hotspots", [])
