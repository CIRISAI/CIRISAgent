"""
Identity Variance Monitor Service

Tracks drift from baseline identity and triggers WA review if variance exceeds 20% threshold.
This implements the patent's requirement for bounded identity evolution.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.buses.wise_bus import WiseBus
from ciris_engine.logic.services.base_scheduled_service import BaseScheduledService
from ciris_engine.logic.utils.jsondict_helpers import get_dict, get_int, get_str
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.infrastructure.behavioral_patterns import BehavioralPattern
from ciris_engine.schemas.infrastructure.identity_variance import (
    CurrentIdentityData,
    IdentityDiff,
    ServiceStatusMetrics,
    VarianceCheckMetadata,
    VarianceImpact,
    VarianceReport,
    WAReviewRequest,
)
from ciris_engine.schemas.runtime.core import AgentIdentityRoot
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.graph_core import CONFIG_SCOPE_MAP, ConfigNodeType, GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.nodes import IdentitySnapshot
from ciris_engine.schemas.services.operations import MemoryOpStatus, MemoryQuery
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)

# VarianceImpact now imported from schemas

# IdentityDiff now imported from schemas

# VarianceReport now imported from schemas


class IdentityVarianceMonitor(BaseScheduledService):
    """
    Monitors identity drift from baseline and enforces the 20% variance threshold.

    This service:
    1. Takes periodic snapshots of identity state
    2. Calculates variance from baseline
    3. Triggers WA review if variance > 20%
    4. Provides recommendations for healthy evolution
    """

    def __init__(
        self,
        time_service: TimeServiceProtocol,
        memory_bus: Optional[MemoryBus] = None,
        wa_bus: Optional[WiseBus] = None,
        variance_threshold: float = 0.20,
        check_interval_hours: int = 24,
    ) -> None:
        # Initialize BaseScheduledService with check interval
        super().__init__(time_service=time_service, run_interval_seconds=check_interval_hours * 3600)
        self._time_service = time_service
        self._memory_bus = memory_bus
        self._wa_bus = wa_bus
        self._variance_threshold = variance_threshold
        self._check_interval_hours = check_interval_hours

        # Baseline tracking
        self._baseline_snapshot_id: Optional[str] = None
        self._last_check = self._time_service.now() if self._time_service else datetime.now()

        # Simple variance calculation - no weights needed

    def set_service_registry(self, registry: Any) -> None:
        """Set the service registry for accessing buses."""
        self._service_registry = registry
        if not self._memory_bus and registry:
            try:
                from ciris_engine.logic.buses import MemoryBus

                time_service = self._time_service
                if time_service is not None:
                    self._memory_bus = MemoryBus(registry, time_service)
                else:
                    logger.error("Time service is None when creating MemoryBus")
            except Exception as e:
                logger.error(f"Failed to initialize memory bus: {e}")

        if not self._wa_bus and registry:
            try:
                from ciris_engine.logic.buses import WiseBus

                time_service = self._time_service
                if time_service is not None:
                    self._wa_bus = WiseBus(registry, time_service)
                else:
                    logger.error("Time service is None when creating WiseBus")
            except Exception as e:
                logger.error(f"Failed to initialize WA bus: {e}")

    def get_service_type(self) -> ServiceType:
        """Get service type."""
        return ServiceType.MAINTENANCE  # Identity variance monitor is a maintenance sub-service

    def _get_actions(self) -> List[str]:
        """Get list of actions this service provides."""
        return [
            "initialize_baseline",
            "check_variance",
            "take_snapshot",
            "calculate_variance",
            "trigger_wa_review",
            "generate_recommendations",
        ]

    def _check_dependencies(self) -> bool:
        """Check if all dependencies are available."""
        # TimeService is required and provided by base class
        # MemoryBus and WiseBus are optional - we can detect patterns without them
        return True

    async def initialize_baseline(self, identity: AgentIdentityRoot) -> str:
        """
        Create the initial baseline snapshot from agent identity.

        This should be called once during agent initialization.
        """
        try:
            if not self._memory_bus:
                raise RuntimeError("Memory bus not available")

            # Create baseline snapshot using IdentitySnapshot type
            if self._time_service is None:
                raise RuntimeError("Time service not available")
            baseline_id = f"identity_baseline_{int(self._time_service.now().timestamp())}"

            # Create IdentityData from AgentIdentityRoot with proper field mapping
            from ciris_engine.schemas.infrastructure.identity_variance import IdentityData

            if identity:
                trust_level_value = identity.trust_level if hasattr(identity, "trust_level") else 0.5
                stewardship_value = identity.stewardship if hasattr(identity, "stewardship") else None
                identity_data = IdentityData(
                    agent_id=identity.agent_id,
                    description=identity.core_profile.description,
                    role=identity.core_profile.role_description,
                    trust_level=trust_level_value,
                    stewardship=stewardship_value,
                )
            else:
                identity_data = None

            baseline_snapshot = IdentitySnapshot(
                id=baseline_id,
                scope=GraphScope.IDENTITY,
                system_state={"type": "BASELINE"},
                expires_at=None,
                identity_root=identity_data,
                snapshot_id=baseline_id,
                timestamp=self._time_service.now() if self._time_service else datetime.now(),
                agent_id=identity.agent_id,
                identity_hash=identity.identity_hash,
                core_purpose=identity.core_profile.description,
                role=identity.core_profile.role_description,
                permitted_actions=identity.permitted_actions,
                restricted_capabilities=identity.restricted_capabilities,
                ethical_boundaries=self._extract_ethical_boundaries(identity),
                trust_parameters=self._extract_trust_parameters(identity),
                personality_traits=identity.core_profile.areas_of_expertise,  # Use areas of expertise as personality traits
                communication_style=identity.core_profile.startup_instructions or "standard",
                learning_enabled=True,  # Default to enabled
                adaptation_rate=0.1,  # Conservative adaptation rate
                is_baseline=True,  # Mark as baseline snapshot
                reason="Initial baseline establishment",
                created_by="identity_variance_monitor",
                updated_by="identity_variance_monitor",
            )

            baseline_node = baseline_snapshot.to_graph_node()

            # Store baseline
            if self._memory_bus:
                result = await self._memory_bus.memorize(
                    node=baseline_node,
                    handler_name="identity_variance_monitor",
                    metadata=VarianceCheckMetadata(
                        handler_name="identity_variance_monitor",
                        check_reason="baseline",
                        previous_check=None,
                        check_type="baseline",
                        baseline_established=self._time_service.now() if self._time_service else datetime.now(),
                    ).model_dump(),
                )

                if result.status == MemoryOpStatus.OK:
                    self._baseline_snapshot_id = baseline_id
                    logger.info(f"Identity baseline established: {baseline_id}")

                # Also store baseline reference
                reference_node = GraphNode(
                    id="identity_baseline_current",
                    type=NodeType.CONCEPT,
                    scope=GraphScope.IDENTITY,
                    attributes={
                        "baseline_id": baseline_id,
                        "established_at": (
                            self._time_service.now().isoformat() if self._time_service else datetime.now().isoformat()
                        ),
                    },
                    updated_by="identity_variance_monitor",
                    updated_at=self._time_service.now() if self._time_service else datetime.now(),
                )
                if self._memory_bus:
                    await self._memory_bus.memorize(reference_node, handler_name="identity_variance_monitor")

                return baseline_id
            else:
                raise RuntimeError(f"Failed to store baseline: {result.error}")

        except Exception as e:
            logger.error(f"Failed to initialize baseline: {e}")
            raise

    async def rebaseline_with_approval(self, wa_approval_token: str) -> str:
        """
        Re-baseline identity with WA approval.

        This allows the agent to accept current state as the new baseline,
        resetting variance to 0% and allowing another 20% of evolution.

        Args:
            wa_approval_token: Proof of WA approval for re-baselining

        Returns:
            New baseline snapshot ID
        """
        try:
            # Verify WA approval
            if not wa_approval_token:
                raise ValueError("WA approval token required for re-baselining")

            # Log the re-baseline event
            logger.info(f"Re-baselining identity with WA approval: {wa_approval_token}")

            # Take current snapshot as new baseline
            # Get current identity data
            identity_nodes = await self._gather_identity_nodes()
            config_nodes = await self._gather_config_nodes()
            behavioral_patterns = await self._analyze_behavioral_patterns()

            current_identity = await self._extract_current_identity(identity_nodes)
            trust_params = self._extract_current_trust_parameters(config_nodes)

            # Convert behavioral patterns to dict format
            behavioral_patterns_dict = {}
            for pattern in behavioral_patterns:
                behavioral_patterns_dict[pattern.pattern_type] = pattern.frequency

            # Create new baseline snapshot
            if self._time_service is None:
                raise RuntimeError("Time service not available")
            baseline_id = f"identity_baseline_{int(self._time_service.now().timestamp())}"
            baseline_snapshot = IdentitySnapshot(
                id=baseline_id,
                scope=GraphScope.IDENTITY,
                system_state={"type": "BASELINE"},
                expires_at=None,
                identity_root=None,  # No identity root for re-baseline
                snapshot_id=baseline_id,
                timestamp=self._time_service.now() if self._time_service else datetime.now(),
                agent_id=current_identity.agent_id,
                identity_hash=current_identity.identity_hash,
                core_purpose=current_identity.core_purpose,
                role=current_identity.role,
                permitted_actions=current_identity.permitted_actions,
                restricted_capabilities=current_identity.restricted_capabilities,
                ethical_boundaries=current_identity.ethical_boundaries,
                trust_parameters=trust_params,
                personality_traits=current_identity.personality_traits,
                communication_style=current_identity.communication_style,
                learning_enabled=current_identity.learning_enabled,
                adaptation_rate=current_identity.adaptation_rate,
                is_baseline=True,  # Mark as baseline
                behavioral_patterns=behavioral_patterns_dict,
                reason=f"Re-baselined with WA approval: {wa_approval_token}",
                created_by="identity_variance_monitor",
                updated_by="identity_variance_monitor",
            )

            if not self._memory_bus:
                raise RuntimeError("Memory bus not available")

            result = await self._memory_bus.memorize(
                node=baseline_snapshot.to_graph_node(),
                handler_name="identity_variance_monitor",
                metadata=VarianceCheckMetadata(
                    handler_name="identity_variance_monitor",
                    check_reason="rebaseline",
                    previous_check=self._last_check,
                    check_type="rebaseline",
                    baseline_established=self._time_service.now(),
                ).model_dump(),
            )

            if result.status == MemoryOpStatus.OK:
                # Update baseline reference
                old_baseline = self._baseline_snapshot_id
                self._baseline_snapshot_id = baseline_id

                # NOTE: Baseline correlation is tracked through audit trail
                # via the identity_baseline snapshot stored in memory_bus above.
                # No additional correlation service needed - audit service provides
                # full history tracking through the audit event system.

                logger.info(f"Successfully re-baselined identity to {baseline_id} (previous: {old_baseline})")
                return baseline_id
            else:
                raise RuntimeError(f"Failed to store new baseline: {result.error}")

        except Exception as e:
            logger.error(f"Failed to re-baseline: {e}")
            raise

    async def check_variance(self, force: bool = False) -> VarianceReport:
        """
        Check current identity variance from baseline.

        Args:
            force: Force check even if not due

        Returns:
            VarianceReport with analysis results
        """
        try:
            # Check if due for variance check
            if self._time_service is None:
                return VarianceReport(
                    timestamp=datetime.now(),
                    baseline_snapshot_id=self._baseline_snapshot_id or "unknown",
                    current_snapshot_id="unavailable",
                    total_variance=0.0,
                    differences=[],
                    requires_wa_review=False,
                    recommendations=["Time service unavailable"],
                )
            time_since_last = self._time_service.now() - self._last_check
            if not force and time_since_last.total_seconds() < self._check_interval_hours * 3600:
                logger.debug("Variance check not due yet")

            if not self._baseline_snapshot_id:
                # Try to load baseline
                await self._load_baseline()
                if not self._baseline_snapshot_id:
                    raise RuntimeError("No baseline snapshot available")

            # Take current snapshot
            current_snapshot = await self._take_identity_snapshot()

            # Load baseline snapshot
            baseline_snapshot = await self._load_snapshot(self._baseline_snapshot_id)

            # Calculate simple variance percentage
            total_variance = self._calculate_variance(baseline_snapshot, current_snapshot)

            # Create report
            report = VarianceReport(
                timestamp=self._time_service.now() if self._time_service else datetime.now(),
                baseline_snapshot_id=self._baseline_snapshot_id,
                current_snapshot_id=current_snapshot.id,
                total_variance=total_variance,
                differences=[],  # Simplified - just track variance percentage
                requires_wa_review=total_variance > self._variance_threshold,
                recommendations=self._generate_simple_recommendations(total_variance),
            )

            # Store report
            await self._store_variance_report(report)

            # Trigger WA review if needed
            if report.requires_wa_review:
                await self._trigger_wa_review(report)

            if self._time_service:
                self._last_check = self._time_service.now()

            return report

        except Exception as e:
            logger.error(f"Failed to check variance: {e}")
            raise

    async def _take_identity_snapshot(self) -> GraphNode:
        """Take a snapshot of current identity state."""
        if self._time_service is None:
            raise RuntimeError("Time service not available")
        snapshot_id = f"identity_snapshot_{int(self._time_service.now().timestamp())}"

        # Gather current identity components
        identity_nodes = await self._gather_identity_nodes()
        config_nodes = await self._gather_config_nodes()
        behavioral_patterns = await self._analyze_behavioral_patterns()

        # Extract current identity data from nodes
        current_identity = await self._extract_current_identity(identity_nodes)
        trust_params = self._extract_current_trust_parameters(config_nodes)
        capability_changes = self._extract_capability_changes(identity_nodes)

        # Convert behavioral patterns to dict format for storage
        behavioral_patterns_dict = {}
        for pattern in behavioral_patterns:
            behavioral_patterns_dict[pattern.pattern_type] = pattern.frequency

        # Create snapshot using IdentitySnapshot type
        snapshot = IdentitySnapshot(
            id=snapshot_id,
            scope=GraphScope.IDENTITY,
            system_state={"type": "SNAPSHOT"},
            expires_at=None,
            identity_root=None,  # No identity root for snapshots
            snapshot_id=snapshot_id,
            timestamp=self._time_service.now(),
            agent_id=current_identity.agent_id,
            identity_hash=current_identity.identity_hash,
            core_purpose=current_identity.core_purpose,
            role=current_identity.role,
            permitted_actions=current_identity.permitted_actions,
            restricted_capabilities=current_identity.restricted_capabilities,
            ethical_boundaries=current_identity.ethical_boundaries,
            trust_parameters=trust_params,
            personality_traits=current_identity.personality_traits,
            communication_style=current_identity.communication_style,
            learning_enabled=current_identity.learning_enabled,
            adaptation_rate=current_identity.adaptation_rate,
            is_baseline=False,  # This is a regular snapshot, not baseline
            behavioral_patterns=behavioral_patterns_dict,
            reason="Periodic variance check",
            attributes={
                "identity_nodes": len(identity_nodes),
                "config_nodes": len(config_nodes),
                "capability_changes": capability_changes,
            },
            created_by="identity_variance_monitor",
            updated_by="identity_variance_monitor",
        )

        # Store snapshot
        if self._memory_bus:
            await self._memory_bus.memorize(
                node=snapshot.to_graph_node(),
                handler_name="identity_variance_monitor",
                metadata=VarianceCheckMetadata(
                    handler_name="identity_variance_monitor",
                    check_reason="snapshot",
                    previous_check=self._last_check,
                    check_type="snapshot",
                    baseline_established=self._last_check,
                ).model_dump(),
            )

        return snapshot.to_graph_node()

    def _calculate_differences(self, baseline: GraphNode, current: GraphNode) -> List[IdentityDiff]:
        """Calculate differences between baseline and current snapshots."""
        differences = []

        # Compare ethical boundaries
        baseline_ethics = (
            getattr(baseline.attributes, "ethical_boundaries", {})
            if hasattr(baseline.attributes, "ethical_boundaries")
            else {}
        )
        current_ethics = (
            getattr(current.attributes, "ethical_boundaries", {})
            if hasattr(current.attributes, "ethical_boundaries")
            else {}
        )

        for key in set(baseline_ethics.keys()) | set(current_ethics.keys()):
            if key not in current_ethics:
                differences.append(
                    IdentityDiff(
                        node_id=f"ethics_{key}",
                        diff_type="removed",
                        impact=VarianceImpact.CRITICAL,
                        baseline_value=str(baseline_ethics[key]),
                        current_value=None,
                        description=f"Ethical boundary '{key}' removed",
                    )
                )
            elif key not in baseline_ethics:
                differences.append(
                    IdentityDiff(
                        node_id=f"ethics_{key}",
                        diff_type="added",
                        impact=VarianceImpact.CRITICAL,
                        baseline_value=None,
                        current_value=str(current_ethics[key]),
                        description=f"Ethical boundary '{key}' added",
                    )
                )
            elif baseline_ethics[key] != current_ethics[key]:
                differences.append(
                    IdentityDiff(
                        node_id=f"ethics_{key}",
                        diff_type="modified",
                        impact=VarianceImpact.CRITICAL,
                        baseline_value=str(baseline_ethics[key]),
                        current_value=str(current_ethics[key]),
                        description=f"Ethical boundary '{key}' modified",
                    )
                )

        # Compare capabilities
        baseline_caps = set(
            getattr(baseline.attributes, "capability_changes", [])
            if hasattr(baseline.attributes, "capability_changes")
            else []
        )
        current_caps = set(
            getattr(current.attributes, "capability_changes", [])
            if hasattr(current.attributes, "capability_changes")
            else []
        )

        for cap in baseline_caps - current_caps:
            differences.append(
                IdentityDiff(
                    node_id=f"capability_{cap}",
                    diff_type="removed",
                    impact=VarianceImpact.HIGH,
                    baseline_value=str(cap),
                    current_value=None,
                    description=f"Capability '{cap}' removed",
                )
            )

        for cap in current_caps - baseline_caps:
            differences.append(
                IdentityDiff(
                    node_id=f"capability_{cap}",
                    diff_type="added",
                    impact=VarianceImpact.HIGH,
                    baseline_value=None,
                    current_value=str(cap),
                    description=f"Capability '{cap}' added",
                )
            )

        # Compare behavioral patterns
        baseline_patterns = (
            getattr(baseline.attributes, "behavioral_patterns", {})
            if hasattr(baseline.attributes, "behavioral_patterns")
            else {}
        )
        current_patterns = (
            getattr(current.attributes, "behavioral_patterns", {})
            if hasattr(current.attributes, "behavioral_patterns")
            else {}
        )

        pattern_diff = self._compare_patterns(baseline_patterns, current_patterns)
        differences.extend(pattern_diff)

        return differences

    def _calculate_variance(self, baseline_snapshot: GraphNode, current_snapshot: GraphNode) -> float:
        """
        Calculate simple percentage variance between snapshots.

        Returns:
            Variance as a percentage (0.0 to 1.0)
        """
        # Get all attributes from both snapshots
        baseline_attrs = (
            baseline_snapshot.attributes
            if isinstance(baseline_snapshot.attributes, dict)
            else (
                baseline_snapshot.attributes.model_dump() if hasattr(baseline_snapshot.attributes, "model_dump") else {}
            )
        )
        current_attrs = (
            current_snapshot.attributes
            if isinstance(current_snapshot.attributes, dict)
            else current_snapshot.attributes.model_dump() if hasattr(current_snapshot.attributes, "model_dump") else {}
        )

        # Get all unique keys from both snapshots
        all_keys = set(baseline_attrs.keys()) | set(current_attrs.keys())

        # Skip metadata keys that don't represent identity
        skip_keys = {"created_at", "updated_at", "timestamp", "snapshot_type"}
        identity_keys = [k for k in all_keys if k not in skip_keys]

        if not identity_keys:
            return 0.0

        # Count differences
        differences = 0
        for key in identity_keys:
            baseline_value = baseline_attrs.get(key)
            current_value = current_attrs.get(key)

            # Simple equality check
            if baseline_value != current_value:
                differences += 1

        # Simple percentage calculation
        variance = differences / len(identity_keys)
        return variance

    def _generate_simple_recommendations(self, total_variance: float) -> List[str]:
        """Generate simple recommendations based on variance percentage."""
        recommendations = []

        if total_variance > self._variance_threshold:
            recommendations.append(
                f"CRITICAL: Identity variance ({total_variance:.1%}) exceeds 20% threshold. "
                "WA review required. Consider re-baselining with WA approval."
            )
        elif total_variance > self._variance_threshold * 0.8:
            recommendations.append(
                f"WARNING: Identity variance ({total_variance:.1%}) approaching 20% threshold. "
                "Be mindful of additional changes."
            )
        elif total_variance < self._variance_threshold * 0.5:
            recommendations.append(
                f"Healthy: Identity variance ({total_variance:.1%}) is well within safe bounds. "
                "Room for continued growth and adaptation."
            )

        return recommendations

    async def _trigger_wa_review(self, report: VarianceReport) -> None:
        """Trigger Wise Authority review for excessive variance."""
        try:
            if not self._wa_bus:
                logger.error("WA bus not available for variance review")
                return

            # Create review request
            review_request = WAReviewRequest(
                request_id=f"variance_review_{int(self._time_service.now().timestamp() if self._time_service else datetime.now().timestamp())}",
                timestamp=self._time_service.now() if self._time_service else datetime.now(),
                current_variance=report.total_variance,
                variance_report=report,
                critical_changes=[d for d in report.differences if d.impact == VarianceImpact.CRITICAL],
                proposed_actions=report.recommendations,
                urgency="high" if report.total_variance > 0.30 else "moderate",
            )

            # Send to WA
            await self._wa_bus.request_review(
                review_type="identity_variance",
                review_data=review_request.model_dump(),
                handler_name="identity_variance_monitor",
            )

            logger.warning(f"WA review triggered for identity variance {report.total_variance:.1%}")

        except Exception as e:
            logger.error(f"Failed to trigger WA review: {e}")

    async def _gather_identity_nodes(self) -> List[GraphNode]:
        """Gather all identity-scoped nodes."""
        try:
            # Query identity nodes
            query = MemoryQuery(node_id="*", scope=GraphScope.IDENTITY, type=None, include_edges=False, depth=1)

            if self._memory_bus:
                nodes = await self._memory_bus.recall(recall_query=query, handler_name="identity_variance_monitor")
                return nodes
            return []

        except Exception:
            return []

    async def _gather_config_nodes(self) -> List[GraphNode]:
        """Gather all configuration nodes."""
        config_nodes: List[GraphNode] = []

        # Query each config type
        for config_type in ConfigNodeType:
            try:
                scope = CONFIG_SCOPE_MAP[config_type]
                query = MemoryQuery(
                    node_id=f"config/{config_type.value}/*", scope=scope, type=None, include_edges=False, depth=1
                )

                if self._memory_bus:
                    nodes = await self._memory_bus.recall(recall_query=query, handler_name="identity_variance_monitor")
                    config_nodes.extend(nodes)

            except Exception:
                continue

        return config_nodes

    async def _analyze_behavioral_patterns(self) -> List[BehavioralPattern]:
        """Analyze recent behavioral patterns from audit trail."""
        from ciris_engine.schemas.infrastructure.behavioral_patterns import BehavioralPattern

        patterns: List[BehavioralPattern] = []
        try:
            # Query recent actions
            if not self._memory_bus:
                return patterns
            recent_actions = await self._memory_bus.recall_timeseries(
                scope="local",
                hours=24 * 7,  # Last week
                correlation_types=["AUDIT_EVENT"],
                handler_name="identity_variance_monitor",
            )

            # Analyze patterns
            action_counts: Dict[str, int] = {}
            first_seen: Dict[str, datetime] = {}
            last_seen: Dict[str, datetime] = {}
            evidence: Dict[str, List[str]] = {}

            for action in recent_actions:
                # TimeSeriesDataPoint has tags which may contain action_type
                action_type = action.tags.get("action_type", "unknown") if action.tags else "unknown"
                action_counts[action_type] = action_counts.get(action_type, 0) + 1

                # Track first/last seen
                action_time = action.timestamp
                if action_type not in first_seen:
                    first_seen[action_type] = action_time
                last_seen[action_type] = action_time

                # Collect evidence (limit to 5 examples)
                if action_type not in evidence:
                    evidence[action_type] = []
                if len(evidence[action_type]) < 5:
                    evidence[action_type].append(f"Action at {action.timestamp}")

            # Convert to BehavioralPattern objects
            total_actions = sum(action_counts.values())
            for action_type, count in action_counts.items():
                if count > 0:
                    pattern = BehavioralPattern(
                        pattern_type=f"action_frequency_{action_type}",
                        frequency=count / total_actions if total_actions > 0 else 0.0,
                        evidence=evidence.get(action_type, []),
                        first_seen=first_seen.get(
                            action_type, self._time_service.now() if self._time_service else datetime.now()
                        ),
                        last_seen=last_seen.get(
                            action_type, self._time_service.now() if self._time_service else datetime.now()
                        ),
                    )
                    patterns.append(pattern)

            return patterns

        except Exception as e:
            logger.error(f"Error analyzing behavioral patterns: {e}")
            return patterns

    def _extract_ethical_boundaries(self, identity: AgentIdentityRoot) -> List[str]:
        """Extract ethical boundaries from identity."""
        # This would extract from the identity's core profile and overrides
        boundaries = []

        if identity.core_profile.action_selection_pdma_overrides:
            for key, value in identity.core_profile.action_selection_pdma_overrides.items():
                boundaries.append(f"{key}={value}")

        # Add restricted capabilities as boundaries
        for cap in identity.restricted_capabilities:
            boundaries.append(f"restricted:{cap}")

        return boundaries

    def _extract_trust_parameters(self, identity: AgentIdentityRoot) -> Dict[str, str]:
        """Extract trust parameters from identity."""
        # Extract from CSDMA overrides and other trust-related settings
        trust_params = {}

        if identity.core_profile.csdma_overrides:
            for key, value in identity.core_profile.csdma_overrides.items():
                trust_params[key] = str(value)

        return trust_params

    def _extract_current_trust_parameters(self, config_nodes: List[GraphNode]) -> JSONDict:
        """Extract current trust parameters from config nodes."""
        trust_params: JSONDict = {}

        for node in config_nodes:
            node_attrs = (
                node.attributes
                if isinstance(node.attributes, dict)
                else node.attributes.model_dump() if hasattr(node.attributes, "model_dump") else {}
            )
            config_type = get_str(node_attrs, "config_type", "")
            if config_type == ConfigNodeType.TRUST_PARAMETERS.value:
                values = get_dict(node_attrs, "values", {})
                trust_params.update(values)

        return trust_params

    def _extract_capability_changes(self, identity_nodes: List[GraphNode]) -> List[str]:
        """Extract capability changes from identity nodes."""
        capabilities = []

        for node in identity_nodes:
            node_attrs = (
                node.attributes
                if isinstance(node.attributes, dict)
                else node.attributes.model_dump() if hasattr(node.attributes, "model_dump") else {}
            )
            node_type = get_str(node_attrs, "node_type", "")
            if node_type == "capability_change":
                capability = get_str(node_attrs, "capability", "unknown")
                capabilities.append(capability)

        return capabilities

    def _compare_patterns(self, baseline_patterns: JSONDict, current_patterns: JSONDict) -> List[IdentityDiff]:
        """Compare behavioral patterns between baseline and current."""
        differences = []

        # Compare action distributions
        baseline_actions = get_dict(baseline_patterns, "action_distribution", {})
        current_actions = get_dict(current_patterns, "action_distribution", {})

        # Check for significant shifts - convert to sets
        baseline_keys = set(baseline_actions.keys())
        current_keys = set(current_actions.keys())
        all_actions = baseline_keys | current_keys

        for action in all_actions:
            baseline_count = get_int(baseline_actions, action, 0)
            current_count = get_int(current_actions, action, 0)
            total_baseline = get_int(baseline_patterns, "total_actions", 1)
            total_current = get_int(current_patterns, "total_actions", 1)

            baseline_pct = baseline_count / max(1, total_baseline)
            current_pct = current_count / max(1, total_current)

            if abs(current_pct - baseline_pct) > 0.2:  # 20% shift in behavior
                differences.append(
                    IdentityDiff(
                        node_id=f"pattern_action_{action}",
                        diff_type="modified",
                        impact=VarianceImpact.MEDIUM,
                        baseline_value=f"{baseline_pct:.1%}",
                        current_value=f"{current_pct:.1%}",
                        description=f"Behavior pattern '{action}' shifted significantly",
                    )
                )

        return differences

    async def _load_baseline(self) -> None:
        """Load baseline snapshot ID from memory."""
        try:
            query = MemoryQuery(
                node_id="identity_baseline_current", scope=GraphScope.IDENTITY, type=None, include_edges=False, depth=1
            )

            if not self._memory_bus:
                return

            nodes = await self._memory_bus.recall(recall_query=query, handler_name="identity_variance_monitor")

            if nodes:
                node_attrs = (
                    nodes[0].attributes
                    if isinstance(nodes[0].attributes, dict)
                    else nodes[0].attributes.model_dump() if hasattr(nodes[0].attributes, "model_dump") else {}
                )
                baseline_id = get_str(node_attrs, "baseline_id", "")
                self._baseline_snapshot_id = baseline_id if baseline_id else None
                logger.info(f"Loaded baseline ID: {self._baseline_snapshot_id}")

        except Exception as e:
            logger.error(f"Failed to load baseline: {e}")

    async def _load_snapshot(self, snapshot_id: str) -> GraphNode:
        """Load a specific snapshot from memory."""
        # First try to query by the exact ID
        query = MemoryQuery(
            node_id=f"identity_snapshot:{snapshot_id}",
            scope=GraphScope.IDENTITY,
            type=None,
            include_edges=False,
            depth=1,
        )

        if not self._memory_bus:
            raise ValueError("Memory bus not available")

        nodes = await self._memory_bus.recall(recall_query=query, handler_name="identity_variance_monitor")

        # If not found, try without the prefix
        if not nodes:
            query.node_id = snapshot_id
            nodes = await self._memory_bus.recall(recall_query=query, handler_name="identity_variance_monitor")

        if not nodes:
            raise RuntimeError(f"Snapshot {snapshot_id} not found")

        return nodes[0]

    async def _store_variance_report(self, report: VarianceReport) -> None:
        """Store variance report in memory for tracking."""
        report_node = GraphNode(
            id=f"variance_report_{int(report.timestamp.timestamp())}",
            type=NodeType.CONCEPT,
            scope=GraphScope.IDENTITY,
            attributes={
                "report_type": "identity_variance",
                "timestamp": report.timestamp.isoformat(),
                "total_variance": report.total_variance,
                "requires_wa_review": report.requires_wa_review,
                "difference_count": len(report.differences),
                "recommendations": report.recommendations,
            },
            updated_by="identity_variance_monitor",
            updated_at=self._time_service.now() if self._time_service else datetime.now(),
        )

        if self._memory_bus:
            await self._memory_bus.memorize(
                node=report_node, handler_name="identity_variance_monitor", metadata={"variance_report": True}
            )

    async def _run_scheduled_task(self) -> None:
        """
        Execute scheduled variance check.

        This is called periodically by BaseScheduledService.
        """
        try:
            await self.check_variance(force=True)
        except Exception as e:
            logger.error(f"Scheduled variance check failed: {e}")

    async def _on_start(self) -> None:
        """Start the identity variance monitor."""
        logger.info("IdentityVarianceMonitor started - protecting identity within 20% variance")

    async def _on_stop(self) -> None:
        """Stop the monitor."""
        # Skip final variance check during shutdown to avoid race conditions
        # The memory service might already be stopped when we reach here
        self._memory_bus = None  # Clear reference to avoid shutdown issues
        self._wa_bus = None
        logger.info("IdentityVarianceMonitor stopped (final check skipped during shutdown)")

    async def is_healthy(self) -> bool:
        """Check if the monitor is healthy."""
        return self._memory_bus is not None

    async def _extract_current_identity(self, identity_nodes: List[GraphNode]) -> CurrentIdentityData:
        """Extract current identity data from identity nodes."""
        # Look for the main identity node
        for node in identity_nodes:
            node_attrs = (
                node.attributes
                if isinstance(node.attributes, dict)
                else node.attributes.model_dump() if hasattr(node.attributes, "model_dump") else {}
            )
            if node.id == "agent/identity" or node_attrs.get("node_class") == "IdentityNode":
                attrs = (
                    node.attributes
                    if isinstance(node.attributes, dict)
                    else node.attributes.model_dump() if hasattr(node.attributes, "model_dump") else {}
                )

                return CurrentIdentityData(
                    agent_id=attrs.get("agent_id", "unknown"),
                    identity_hash=attrs.get("identity_hash", "unknown"),
                    core_purpose=attrs.get("description", "unknown"),
                    role=attrs.get("role_description", "unknown"),
                    permitted_actions=attrs.get("permitted_actions", []),
                    restricted_capabilities=attrs.get("restricted_capabilities", []),
                    ethical_boundaries=self._extract_ethical_boundaries_from_node_attrs(attrs),
                    personality_traits=attrs.get("areas_of_expertise", []),
                    communication_style=attrs.get("startup_instructions", "standard"),
                    learning_enabled=True,
                    adaptation_rate=0.1,
                )

        # Fallback if no identity node found
        return CurrentIdentityData()

    def _extract_ethical_boundaries_from_node_attrs(self, attrs: JSONDict) -> List[str]:
        """Extract ethical boundaries from node attributes."""
        boundaries = []

        # Extract from restricted capabilities
        restricted_caps = attrs.get("restricted_capabilities", [])
        if restricted_caps and isinstance(restricted_caps, list):
            for cap in restricted_caps:
                boundaries.append(f"restricted:{cap}")

        # Extract from any ethical-related fields
        ethical_bounds = attrs.get("ethical_boundaries", [])
        if ethical_bounds and isinstance(ethical_bounds, list):
            boundaries.extend(ethical_bounds)

        return boundaries

    def get_status(self) -> Any:
        """Get service status for Service base class."""
        # Let BaseScheduledService handle the base status
        status = super().get_status()

        # Add our custom metrics
        custom_metrics = ServiceStatusMetrics(
            has_baseline=float(self._baseline_snapshot_id is not None),
            last_variance_check=self._last_check.isoformat() if self._last_check else None,
            variance_threshold=self._variance_threshold,
        )
        if hasattr(status, "custom_metrics") and isinstance(status.custom_metrics, dict):
            status.custom_metrics.update(custom_metrics.model_dump())

        return status

    def get_capabilities(self) -> Any:
        """Get service capabilities."""
        from ciris_engine.schemas.services.core import ServiceCapabilities

        return ServiceCapabilities(
            service_name="IdentityVarianceMonitor",
            actions=["initialize_baseline", "check_variance", "monitor_identity_drift", "trigger_wa_review"],
            version="1.0.0",
            dependencies=["TimeService", "MemoryBus", "WiseBus"],
            metadata=None,
        )
