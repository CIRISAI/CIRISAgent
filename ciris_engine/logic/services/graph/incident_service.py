"""
Incident Management Service - ITIL-aligned incident processing for self-improvement.

This service processes incidents captured from logs, detects patterns, identifies problems,
and generates insights for agent self-improvement. It's integrated with the dream cycle
for continuous learning from operational issues.
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Dict, List, Optional

import aiofiles

from ciris_engine.logic.services.graph.base import BaseGraphService
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.graph.incident import (
    IncidentInsightNode,
    IncidentNode,
    IncidentSeverity,
    IncidentStatus,
    ProblemNode,
)
from ciris_engine.schemas.services.graph_core import GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryOpStatus

if TYPE_CHECKING:
    from ciris_engine.logic.buses import MemoryBus
    from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

logger = logging.getLogger(__name__)


class IncidentManagementService(BaseGraphService):
    """
    Manages incidents, problems, and insights for agent self-improvement.

    This service:
    1. Processes incidents captured from WARNING/ERROR logs
    2. Detects patterns and recurring issues
    3. Identifies root causes (problems)
    4. Generates actionable insights for self-improvement
    5. Tracks effectiveness of applied changes
    """

    def __init__(
        self, memory_bus: Optional["MemoryBus"] = None, time_service: Optional["TimeServiceProtocol"] = None
    ) -> None:
        super().__init__(memory_bus=memory_bus, time_service=time_service)
        self.service_name = "IncidentManagementService"
        self._started = False
        self._start_time: Optional[datetime] = None

    def _get_time_service(self) -> "TimeServiceProtocol":
        """Get time service for consistent timestamps."""

        if self._time_service is None:
            raise RuntimeError("Time service not initialized")
        return self._time_service

    async def process_recent_incidents(self, hours: int = 24) -> IncidentInsightNode:
        """
        Process recent incidents to identify patterns and generate insights.
        This is called during the dream cycle for self-improvement.

        Args:
            hours: How many hours of incidents to analyze

        Returns:
            IncidentInsightNode with analysis results and recommendations
        """
        try:
            # Get time service
            time_service = self._get_time_service()
            if not time_service:
                raise RuntimeError("CRITICAL: TimeService not available")

            # Query recent incidents
            current_time = time_service.now()
            cutoff_time = current_time - timedelta(hours=hours)

            incidents = await self._get_recent_incidents(cutoff_time)

            if not incidents:
                logger.info("No incidents found in the last %d hours", hours)
                return self._create_no_incidents_insight(current_time)

            # Analyze incidents
            patterns = self._detect_patterns(incidents)
            problems = await self._identify_problems(patterns)
            recommendations = self._generate_recommendations(patterns, problems)

            # Create insight node
            insight = IncidentInsightNode(
                id=f"incident_insight_{current_time.strftime('%Y%m%d_%H%M%S')}",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={},  # Required for TypedGraphNode
                insight_type="PERIODIC_ANALYSIS",
                summary=self._summarize_analysis(len(incidents), len(patterns), len(problems)),
                details={
                    "incident_count": len(incidents),
                    "pattern_count": len(patterns),
                    "problem_count": len(problems),
                    "severity_breakdown": self._get_severity_breakdown(incidents),
                    "component_breakdown": self._get_component_breakdown(incidents),
                    "time_distribution": self._get_time_distribution(incidents),
                },
                behavioral_adjustments=recommendations.get("behavioral", []),
                configuration_changes=recommendations.get("configuration", []),
                source_incidents=[i.id for i in incidents],
                source_problems=[p.id for p in problems],
                analysis_timestamp=current_time,
                updated_by="IncidentManagementService",
                updated_at=current_time,
            )

            # Store insight in graph
            if self._memory_bus:
                result = await self._memory_bus.memorize(node=insight.to_graph_node(), handler_name=self.service_name)

                if result.status != MemoryOpStatus.OK:
                    logger.error("Failed to store incident insight: %s", result.error)
            else:
                logger.warning("Memory bus not available, cannot store incident insight")

            # Mark analyzed incidents
            await self._mark_incidents_analyzed(incidents)

            return insight

        except Exception as e:
            logger.error("Failed to process incidents: %s", e, exc_info=True)
            raise

    async def _get_recent_incidents(self, cutoff_time: datetime) -> List[IncidentNode]:
        """Get recent incidents from memory service."""
        if not self._memory_bus:
            logger.error("Memory bus not available")
            return []

        try:
            # First try to get from memory service (for tests)
            memory_services = (
                self._memory_bus.service_registry.get_services_by_type("memory")
                if hasattr(self._memory_bus, "service_registry")
                else []
            )
            memory_service = memory_services[0] if memory_services else None

            if memory_service and hasattr(memory_service, "search"):
                # Use the mocked search method in tests
                nodes = await memory_service.search(NodeType.AUDIT_ENTRY, cutoff_time)
                incidents = []
                for node in nodes:
                    try:
                        incident = IncidentNode.from_graph_node(node)
                        incidents.append(incident)
                    except Exception as e:
                        logger.warning(f"Failed to parse incident node: {e}")
                        continue
                return incidents

            # Otherwise query memory bus normally
            from ciris_engine.schemas.services.graph.memory import MemorySearchFilter

            # Create search filter for audit entries created after cutoff time
            search_filter = MemorySearchFilter(
                node_type=NodeType.AUDIT_ENTRY.value, created_after=cutoff_time, limit=1000
            )

            # Use search method to find audit entries
            nodes = await self._memory_bus.search(
                query="",  # Empty query to get all matching nodes
                filters=search_filter,
                handler_name="incident_service",
            )

            # Convert GraphNodes to IncidentNodes
            incidents = []
            for node in nodes:
                try:
                    incident = IncidentNode.from_graph_node(node)
                    incidents.append(incident)
                except Exception as e:
                    logger.warning(f"Failed to parse incident node: {e}")
                    continue

            return incidents

        except Exception as e:
            logger.warning(f"Failed to get incidents from memory service: {e}")

            # Fallback to reading from file if memory service fails
            from pathlib import Path

            log_dir = Path("/app/logs")
            incidents_file = log_dir / "incidents_latest.log"

            if not incidents_file.exists():
                logger.warning("No incidents log file found")
                return []

            incidents = []
            try:
                # Parse the incidents log file
                async with aiofiles.open(incidents_file, "r") as f:
                    async for line in f:
                        line = line.strip()
                        if not line or line.startswith("==="):
                            continue

                        # Parse log line: "2025-07-09 15:24:43.200 - WARNING  - component - file.py:line - message"
                        parts = line.split(" - ", 4)
                        if len(parts) >= 5:
                            timestamp_str = parts[0]
                            level = parts[1].strip()
                            component = parts[2].strip()
                            location = parts[3].strip()
                            message = parts[4].strip()

                            # Parse timestamp
                            from datetime import datetime

                            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f")

                            # Skip if before cutoff
                            if timestamp.replace(tzinfo=cutoff_time.tzinfo) < cutoff_time:
                                continue

                            # Create incident node
                            incident = IncidentNode(
                                id=f"incident_{timestamp.strftime('%Y%m%d_%H%M%S')}_{hash(message) % 10000}",
                                type=NodeType.AUDIT_ENTRY,
                                scope=GraphScope.LOCAL,
                                attributes={},
                                incident_type=level,
                                severity=IncidentSeverity.HIGH if level == "ERROR" else IncidentSeverity.MEDIUM,
                                status=IncidentStatus.OPEN,
                                description=message,
                                source_component=component,
                                detected_at=timestamp,
                                filename=location,  # Use location as filename
                                line_number=0,  # Line number not available from log parsing
                                impact="TBD",
                                urgency="MEDIUM",
                                updated_by="incident_service",
                                updated_at=timestamp,
                            )
                        incidents.append(incident)

            except Exception as e:
                logger.error(f"Failed to parse incidents log: {e}")

            logger.info(f"Found {len(incidents)} incidents since {cutoff_time}")
            return incidents

    def _detect_patterns(self, incidents: List[IncidentNode]) -> Dict[str, List[IncidentNode]]:
        """Detect patterns in incidents."""
        patterns = defaultdict(list)

        # Group by error message similarity
        error_groups = self._group_by_similarity(incidents)
        for group_key, group_incidents in error_groups.items():
            if len(group_incidents) >= 3:  # At least 3 occurrences
                patterns[f"recurring_error_{group_key}"] = group_incidents

        # Group by component
        component_groups = defaultdict(list)
        for incident in incidents:
            if hasattr(incident, "source_component") and incident.source_component:
                component_groups[incident.source_component].append(incident)
            else:
                component_groups["unknown"].append(incident)

        for component, comp_incidents in component_groups.items():
            if len(comp_incidents) >= 5:  # Component with many incidents
                patterns[f"component_issues_{component}"] = comp_incidents

        # Detect time-based clusters (error spikes)
        time_clusters = self._detect_time_clusters(incidents)
        for idx, cluster in enumerate(time_clusters):
            if len(cluster) >= 5:  # At least 5 incidents in cluster
                patterns[f"error_spike_{idx}"] = cluster

        return dict(patterns)

    async def _identify_problems(self, patterns: Dict[str, List[IncidentNode]]) -> List[ProblemNode]:
        """Identify root cause problems from patterns."""
        problems: List[ProblemNode] = []

        # Get current time for timestamps
        if not self._time_service:
            raise RuntimeError("CRITICAL: TimeService not available for incident problem identification")
        current_time = self._time_service.now()

        for pattern_key, pattern_incidents in patterns.items():
            # Skip if too few incidents
            if len(pattern_incidents) < 3:
                continue

            # Analyze root causes
            root_causes = self._analyze_root_causes(pattern_incidents)

            # Create problem node
            problem = ProblemNode(
                id=f"problem_{pattern_key}_{len(problems)}",
                type=NodeType.CONCEPT,
                scope=GraphScope.IDENTITY,
                attributes={},  # Required for TypedGraphNode
                problem_statement=self._create_problem_statement(pattern_key, pattern_incidents),
                affected_incidents=[i.id for i in pattern_incidents],
                status="UNDER_INVESTIGATION",
                potential_root_causes=root_causes,
                recommended_actions=self._suggest_fixes(pattern_key, root_causes),
                incident_count=len(pattern_incidents),
                first_occurrence=min(i.detected_at for i in pattern_incidents),
                last_occurrence=max(i.detected_at for i in pattern_incidents),
                updated_by="IncidentManagementService",
                updated_at=current_time,
            )

            # Store problem in graph
            if self._memory_bus:
                result = await self._memory_bus.memorize(node=problem.to_graph_node(), handler_name=self.service_name)

                if result.status == MemoryOpStatus.OK:
                    problems.append(problem)

                    # Link incidents to problem
                    for incident in pattern_incidents:
                        incident.problem_id = problem.id
                        incident.status = IncidentStatus.RECURRING
                        await self._update_incident(incident)
            else:
                logger.warning("Memory bus not available, cannot store problem node")
                problems.append(problem)  # Still add to problems list for return value

        return problems

    def _generate_recommendations(
        self, patterns: Dict[str, List[IncidentNode]], problems: List[ProblemNode]
    ) -> Dict[str, List[str]]:
        """Generate actionable recommendations."""
        recommendations: Dict[str, List[str]] = {"behavioral": [], "configuration": []}

        # Analyze patterns for recommendations
        for pattern_key, incidents in patterns.items():
            if "timeout" in pattern_key.lower():
                recommendations["configuration"].append("Consider increasing timeout values for affected operations")
                recommendations["behavioral"].append(
                    "Add retry logic with exponential backoff for timeout-prone operations"
                )

            elif "memory" in pattern_key.lower():
                recommendations["configuration"].append("Increase memory limits or implement memory usage monitoring")
                recommendations["behavioral"].append("Implement periodic memory cleanup in long-running operations")

            elif "component_issues" in pattern_key:
                component = pattern_key.split("_")[-1]
                recommendations["behavioral"].append(f"Add additional error handling and logging to {component}")
                recommendations["configuration"].append(f"Consider circuit breaker pattern for {component}")

        # Analyze problems for deeper recommendations
        for problem in problems:
            if "configuration" in " ".join(problem.potential_root_causes).lower():
                recommendations["configuration"].append("Review and validate all configuration settings")

            if "resource" in " ".join(problem.potential_root_causes).lower():
                recommendations["behavioral"].append("Implement resource usage monitoring and alerts")

        # De-duplicate recommendations
        recommendations["behavioral"] = list(set(recommendations["behavioral"]))
        recommendations["configuration"] = list(set(recommendations["configuration"]))

        return recommendations

    # Helper methods

    def _group_by_similarity(self, incidents: List[IncidentNode]) -> Dict[str, List[IncidentNode]]:
        """Group incidents by error message similarity."""
        groups = defaultdict(list)

        for incident in incidents:
            # Simple grouping by first few words of description
            key = "_".join(incident.description.split()[:3]).lower()
            groups[key].append(incident)

        return dict(groups)

    def _detect_time_clusters(self, incidents: List[IncidentNode]) -> List[List[IncidentNode]]:
        """Detect time-based clusters of incidents."""
        # Sort by time
        sorted_incidents = sorted(incidents, key=lambda i: i.detected_at)

        clusters: List[List[IncidentNode]] = []
        current_cluster: List[IncidentNode] = []
        cluster_threshold = timedelta(minutes=5)  # Incidents within 5 minutes

        for incident in sorted_incidents:
            if not current_cluster:
                current_cluster.append(incident)
            else:
                time_diff = incident.detected_at - current_cluster[-1].detected_at
                if time_diff <= cluster_threshold:
                    current_cluster.append(incident)
                else:
                    if len(current_cluster) >= 3:
                        clusters.append(current_cluster)
                    current_cluster = [incident]

        if len(current_cluster) >= 3:
            clusters.append(current_cluster)

        return clusters

    def _analyze_root_causes(self, incidents: List[IncidentNode]) -> List[str]:
        """Analyze potential root causes."""
        root_causes: List[str] = []

        # Check for common patterns
        descriptions = [i.description.lower() for i in incidents]

        if any("timeout" in d for d in descriptions):
            root_causes.append("Timeout configuration may be too aggressive")

        if any("connection" in d for d in descriptions):
            root_causes.append("Network connectivity or service availability issues")

        if any("memory" in d or "resource" in d for d in descriptions):
            root_causes.append("Resource constraints or memory leaks")

        if any("permission" in d or "auth" in d for d in descriptions):
            root_causes.append("Authentication or authorization configuration issues")

        # Check for specific components
        components = set(i.source_component for i in incidents)
        if len(components) == 1:
            root_causes.append(f"Issue isolated to {list(components)[0]} component")

        return root_causes

    def _create_problem_statement(self, pattern_key: str, incidents: List[IncidentNode]) -> str:
        """Create a human-readable problem statement."""
        if "recurring_error" in pattern_key:
            return f"Recurring error: {incidents[0].description} (occurred {len(incidents)} times)"
        elif "component_issues" in pattern_key:
            component = pattern_key.split("_")[-1]
            return f"Multiple issues in {component} component ({len(incidents)} incidents)"
        elif "error_spike" in pattern_key:
            return f"Error spike detected with {len(incidents)} incidents in short time period"
        else:
            return f"Pattern detected: {pattern_key} affecting {len(incidents)} incidents"

    def _suggest_fixes(self, pattern_key: str, root_causes: List[str]) -> List[str]:
        """Suggest specific fixes for the problem."""
        fixes = []

        # Pattern-based fixes
        if "timeout" in pattern_key.lower():
            fixes.append("Increase timeout values in configuration")
            fixes.append("Implement retry logic with exponential backof")

        # Root cause based fixes
        for cause in root_causes:
            if "memory" in cause.lower():
                fixes.append("Implement memory profiling to identify leaks")
                fixes.append("Add memory usage limits and monitoring")
            elif "network" in cause.lower():
                fixes.append("Add connection pooling and retry logic")
                fixes.append("Implement circuit breaker for external services")

        return fixes

    def _summarize_analysis(self, incident_count: int, pattern_count: int, problem_count: int) -> str:
        """Create a summary of the analysis."""
        if incident_count == 0:
            return "No incidents detected in the analysis period"
        elif problem_count == 0:
            return f"Analyzed {incident_count} incidents, no recurring problems identified"
        else:
            return (
                f"Analyzed {incident_count} incidents, found {pattern_count} patterns "
                f"and identified {problem_count} problems requiring attention"
            )

    def _get_severity_breakdown(self, incidents: List[IncidentNode]) -> Dict[str, int]:
        """Get breakdown by severity."""
        breakdown: defaultdict[str, int] = defaultdict(int)
        for incident in incidents:
            breakdown[incident.severity.value] += 1
        return dict(breakdown)

    def _get_component_breakdown(self, incidents: List[IncidentNode]) -> Dict[str, int]:
        """Get breakdown by component."""
        breakdown: defaultdict[str, int] = defaultdict(int)
        for incident in incidents:
            breakdown[incident.source_component] += 1
        return dict(breakdown)

    def _get_time_distribution(self, incidents: List[IncidentNode]) -> Dict[str, int]:
        """Get distribution over time (hourly buckets)."""
        distribution: defaultdict[str, int] = defaultdict(int)
        for incident in incidents:
            hour_key = incident.detected_at.strftime("%Y-%m-%d %H:00")
            distribution[hour_key] += 1
        return dict(distribution)

    def _create_no_incidents_insight(self, current_time: datetime) -> IncidentInsightNode:
        """Create insight when no incidents found."""
        return IncidentInsightNode(
            id=f"incident_insight_{current_time.strftime('%Y%m%d_%H%M%S')}",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes={},  # Required for TypedGraphNode
            insight_type="NO_INCIDENTS",
            summary="No incidents detected - system operating normally",
            details={"incident_count": 0, "pattern_count": 0, "problem_count": 0},
            behavioral_adjustments=[],
            configuration_changes=[],
            source_incidents=[],
            source_problems=[],
            analysis_timestamp=current_time,
            updated_by="IncidentManagementService",
            updated_at=current_time,
        )

    async def get_incident_count(self, hours: int = 1) -> int:
        """Get count of incidents in the specified time window.

        Args:
            hours: Number of hours to look back

        Returns:
            Count of incidents
        """
        try:
            time_service = self._get_time_service()
            current_time = time_service.now()
            cutoff_time = current_time - timedelta(hours=hours)
            incidents = await self._get_recent_incidents(cutoff_time)
            return len(incidents)
        except Exception as e:
            logger.warning(f"Failed to get incident count: {e}")
            return 0

    async def _mark_incidents_analyzed(self, incidents: List[IncidentNode]) -> None:
        """Mark incidents as analyzed."""
        for incident in incidents:
            incident.status = IncidentStatus.INVESTIGATING
            await self._update_incident(incident)

    async def _update_incident(self, incident: IncidentNode) -> None:
        """Update an incident in the graph."""
        if self._memory_bus:
            result = await self._memory_bus.memorize(node=incident.to_graph_node(), handler_name=self.service_name)

            if result.status != MemoryOpStatus.OK:
                logger.error("Failed to update incident %s: %s", incident.id, result.error)
        else:
            logger.warning("Memory bus not available, cannot update incident %s", incident.id)

    # Service protocol methods

    def get_node_type(self) -> str:
        """Get the type of nodes this service manages."""
        return "INCIDENT"

    def start(self) -> None:
        """Start the service."""
        super().start()
        self._start_time = self._time_service.now() if self._time_service else datetime.now()
        logger.info("IncidentManagementService started")

    def stop(self) -> None:
        """Stop the service."""
        super().stop()
        logger.info("IncidentManagementService stopped")

    def get_capabilities(self) -> ServiceCapabilities:
        """Get service capabilities."""
        return ServiceCapabilities(
            service_name="IncidentManagementService",
            actions=["process_recent_incidents", "detect_patterns", "identify_problems", "generate_insights"],
            version="1.0.0",
            dependencies=["MemoryService", "TimeService"],
            metadata={"itil_aligned": True, "analysis_window_hours": 24},
        )

    def get_status(self) -> ServiceStatus:
        """Get service status."""
        current_time = self._time_service.now() if self._time_service else datetime.now()
        uptime_seconds = (current_time - self._start_time).total_seconds() if self._start_time else 0.0

        return ServiceStatus(
            service_name="IncidentManagementService",
            service_type="graph_service",
            is_healthy=self._started and self._memory_bus is not None,
            uptime_seconds=uptime_seconds,
            metrics={"service_available": bool(self._memory_bus)},
            last_error=None,
            last_health_check=current_time,
        )

    def is_healthy(self) -> bool:
        """Check if service is healthy."""
        return self._started and self._memory_bus is not None

    def get_service_type(self) -> ServiceType:
        """Get the service type."""
        return ServiceType.AUDIT
