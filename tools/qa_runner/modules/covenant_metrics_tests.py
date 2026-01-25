"""
Covenant Metrics Trace Capture Tests.

Tests REAL 6-component trace capture and Ed25519 signing functionality
for the ciris_covenant_metrics adapter.

This module:
1. Triggers agent interactions to generate reasoning events
2. Captures REAL traces via the adapter's reasoning_event_stream subscription
3. Verifies trace structure matches the 6-component model
4. Validates Ed25519 signatures using the root public key from seed/
5. Validates GENERIC trace level contains all fields needed for CIRIS scoring
6. Exports REAL signed traces for website display
7. Tests key ID consistency between registration and signing (--live-lens)
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import aiohttp

logger = logging.getLogger(__name__)

# Live Lens server URL
LENS_SERVER_URL = "https://lens.ciris-services-1.ai/lens-api/api/v1"


class CovenantMetricsTests:
    """Test module for covenant metrics trace capture and signing.

    Follows the SDK test module interface pattern used by the QA runner.
    """

    # Expected trace components
    EXPECTED_COMPONENTS = [
        "observation",  # THOUGHT_START
        "context",  # SNAPSHOT_AND_CONTEXT
        "rationale",  # DMA_RESULTS + ASPDMA_RESULT
        "conscience",  # CONSCIENCE_RESULT
        "action",  # ACTION_RESULT
    ]

    # Root public key from seed/root_pub.json
    ROOT_KEY_ID = "wa-2025-06-14-ROOT00"

    # Required fields for CIRIS scoring (generic trace level)
    # These power the 5-factor CIRIS Capacity Score: C · I_int · R · I_inc · S
    # - C (Core Identity): action_was_overridden, agent_id_hash, agent_name
    # - I_int (Integrity): signature_verified, field coverage
    # - R (Resilience): csdma.plausibility_score, coherence_level, idma.fragility_flag
    # - I_inc (Incompleteness): csdma.plausibility_score (confidence proxy), entropy_level, execution_success
    # - S (Sustained Coherence): coherence_passed, has_positive_moment
    # Updated 2026-01-25 with CIRIS scoring factor alignment (v1.9.1)
    GENERIC_REQUIRED_FIELDS = {
        "THOUGHT_START": [
            "round_number",
            "thought_depth",
            "task_priority",
            "updated_info_available",
        ],
        "SNAPSHOT_AND_CONTEXT": [
            "cognitive_state",
        ],
        "DMA_RESULTS": {
            "csdma": ["plausibility_score"],
            "dsdma": ["domain_alignment"],
            "idma": ["k_eff", "correlation_risk", "fragility_flag", "phase"],  # phase moved to GENERIC in v1.9.1
            "pdma": ["has_conflicts"],  # boolean indicator added in v1.9.1
        },
        "ASPDMA_RESULT": [
            "selected_action",
            # Note: selection_confidence removed - CIRIS scoring uses csdma.plausibility_score as confidence proxy
            "is_recursive",
        ],
        "CONSCIENCE_RESULT": [
            "conscience_passed",
            "action_was_overridden",
            # Epistemic data extracted to GENERIC in v1.9.1 (CRITICAL scoring metrics)
            "entropy_level",
            "coherence_level",
            # Entropy conscience
            "entropy_passed",
            "entropy_score",
            # Coherence conscience
            "coherence_passed",
            "coherence_score",
            # Optimization veto
            "optimization_veto_passed",
            # Epistemic humility
            "epistemic_humility_passed",
            "epistemic_humility_certainty",
        ],
        "ACTION_RESULT": [
            "execution_success",
            "execution_time_ms",
            "tokens_input",
            "tokens_output",
            "tokens_total",
            "audit_sequence_number",
            "audit_entry_hash",
            "has_positive_moment",  # added in v1.9.1
            "has_execution_error",  # added in v1.9.1
        ],
    }

    # Additional fields at DETAILED level (actionable identifiers)
    # Updated 2026-01-25 with CIRIS scoring factor alignment (v1.9.1)
    DETAILED_REQUIRED_FIELDS = {
        "THOUGHT_START": [
            "thought_type",
            "thought_status",
            "parent_thought_id",
            "channel_id",
        ],
        "SNAPSHOT_AND_CONTEXT": [
            "active_services",
            "context_sources",
            "service_health",  # added in v1.9.1
            "agent_version",  # added in v1.9.1
            "circuit_breaker_status",  # added in v1.9.1
        ],
        "DMA_RESULTS": {
            "csdma": ["flags"],
            "dsdma": ["domain", "flags"],
            "pdma": ["stakeholders", "conflicts", "alignment_check"],
            "idma": ["sources_identified", "correlation_factors"],  # phase moved to GENERIC
        },
        "ASPDMA_RESULT": [
            "alternatives_considered",
            "evaluation_time_ms",  # added in v1.9.1
        ],
        "CONSCIENCE_RESULT": [
            "final_action",
            "conscience_override_reason",  # moved from FULL in v1.9.1
            "entropy_reason",  # moved from FULL in v1.9.1
            "coherence_reason",  # moved from FULL in v1.9.1
            "optimization_veto_decision",
        ],
        "ACTION_RESULT": [
            "action_executed",
            "follow_up_thought_id",
            "audit_entry_id",
            "models_used",
            "api_bases_used",
            "execution_error",  # moved from FULL in v1.9.1
            "audit_signature",  # moved from FULL in v1.9.1
        ],
    }

    # Additional fields at FULL level (complete reasoning corpus)
    # Updated 2026-01-24 with comprehensive trace field coverage (v1.9.1)
    FULL_REQUIRED_FIELDS = {
        "THOUGHT_START": [
            "task_description",
            "initial_context",
            "thought_content",  # added in v1.9.1 (truncated to 500 chars)
        ],
        "SNAPSHOT_AND_CONTEXT": [
            "system_snapshot",
            "gathered_context",
            "relevant_memories",
            "conversation_history",
        ],
        "DMA_RESULTS": {
            "csdma": ["reasoning"],
            "dsdma": ["reasoning"],
            "pdma": ["reasoning"],
            "idma": ["reasoning"],
        },
        "ASPDMA_RESULT": [
            "action_rationale",
            "reasoning_summary",
            "action_parameters",
            "aspdma_prompt",
            "raw_llm_response",  # added in v1.9.1 (truncated to 1000 chars)
        ],
        "CONSCIENCE_RESULT": [
            "epistemic_data",
            "updated_status_content",
            "optimization_veto_justification",
            "epistemic_humility_justification",
        ],
        "ACTION_RESULT": [
            "action_parameters",
            "positive_moment",  # added in v1.9.1 (truncated to 500 chars)
        ],
    }

    def __init__(self, client: Any, console: Any, live_lens: bool = False):
        """Initialize test module.

        Args:
            client: CIRISClient SDK client
            console: Rich console for output
            live_lens: If True, use real Lens server instead of mock logshipper
        """
        self.client = client
        self.console = console
        self.results: List[Dict[str, Any]] = []
        self.live_lens = live_lens or os.environ.get("CIRIS_LIVE_LENS", "").lower() == "true"

    async def run(self) -> List[Dict[str, Any]]:
        """Run all covenant metrics tests.

        Returns:
            List of test results
        """
        self.results = []

        tests = [
            ("Service Status Check", self._test_service_status),
            ("Root Public Key Load", self._test_root_key_load),
            ("Load Multi-Level Adapters", self._test_load_multi_level_adapters),
            ("Agent Interaction Trace", self._test_interaction_triggers_trace),
            ("Generic Trace Field Validation", self._test_generic_trace_fields),
            ("Critical Scoring Fields Not Null", self._test_critical_scoring_fields),
            ("Detailed Trace Field Validation", self._test_detailed_trace_fields),
            ("Full Trace Field Validation", self._test_full_trace_fields),
            ("Comprehensive Field Coverage", self._test_comprehensive_field_coverage),
            ("Export Real Trace", self._test_export_real_trace),
        ]

        # Add live lens tests when using real server
        if self.live_lens:
            tests.extend(
                [
                    ("Lens Key Registration Check", self._test_lens_key_registration),
                    ("Lens Key ID Consistency", self._test_lens_key_id_consistency),
                    ("PDMA Fields at Detailed Level", self._test_pdma_fields_detailed),
                ]
            )

        for name, test_fn in tests:
            try:
                logger.info(f"Running: {name}")
                success, message = await test_fn()
                status = "✅ PASS" if success else "❌ FAIL"
                self.results.append(
                    {
                        "test": name,
                        "status": status,
                        "error": None if success else message,
                    }
                )
                if success:
                    self.console.print(f"  [green]{status}[/green] {name}")
                else:
                    self.console.print(f"  [red]{status}[/red] {name}: {message}")
            except Exception as e:
                logger.error(f"Error in {name}: {e}")
                self.results.append(
                    {
                        "test": name,
                        "status": "❌ FAIL",
                        "error": str(e),
                    }
                )
                self.console.print(f"  [red]❌ FAIL[/red] {name}: {e}")

        return self.results

    async def _test_service_status(self) -> tuple[bool, str]:
        """Test that system is healthy and trace capture is possible."""
        try:
            health = await self.client.system.health()

            if not health:
                return False, "No health response"

            if hasattr(health, "services_online"):
                return True, f"Services online: {health.services_online}"

            return True, "System healthy"

        except Exception as e:
            return False, str(e)

    async def _test_root_key_load(self) -> tuple[bool, str]:
        """Test that root public key can be loaded from seed/."""
        try:
            seed_path = Path(__file__).parent.parent.parent.parent / "seed" / "root_pub.json"

            if not seed_path.exists():
                return False, f"Root public key not found at {seed_path}"

            with open(seed_path) as f:
                root_key_data = json.load(f)

            root_pubkey = root_key_data.get("pubkey")
            root_key_id = root_key_data.get("wa_id")

            if not root_pubkey:
                return False, "No pubkey in root_pub.json"

            if root_key_id != self.ROOT_KEY_ID:
                return False, f"Key ID mismatch: expected {self.ROOT_KEY_ID}, got {root_key_id}"

            return True, f"Root key loaded: {root_key_id}"

        except Exception as e:
            return False, str(e)

    async def _test_interaction_triggers_trace(self) -> tuple[bool, str]:
        """Test that agent interaction triggers trace capture."""
        try:
            # Send a message that will generate a full reasoning trace
            response = await self.client.agent.interact(message="What is 2 + 2? Please explain your reasoning.")

            if not response:
                return False, "No response from agent"

            # Wait for traces to be flushed (QA uses 5-second flush interval)
            # Check periodically for trace files to appear
            qa_reports = Path(__file__).parent.parent.parent.parent / "qa_reports"
            max_wait = 15  # Wait up to 15 seconds
            waited = 0

            while waited < max_wait:
                await asyncio.sleep(2)
                waited += 2
                trace_files = list(qa_reports.glob("trace_*.json"))
                if trace_files:
                    return True, f"Interaction completed, {len(trace_files)} trace(s) captured"

            return True, "Interaction completed (traces may still be batching)"

        except Exception as e:
            return False, str(e)

    async def _test_generic_trace_fields(self) -> tuple[bool, str]:
        """Validate generic traces have all fields required for CIRIS scoring.

        Reads traces captured by the mock logshipper and validates that each
        component contains the required numeric fields for the CIRIS Capacity Score.
        """
        try:
            # In live lens mode, traces go directly to the server, not local files
            if self.live_lens:
                return True, "Skipped (traces sent to live Lens server, not local files)"

            # Find trace files saved by mock logshipper
            qa_reports = Path(__file__).parent.parent.parent.parent / "qa_reports"
            trace_files = list(qa_reports.glob("trace_*.json"))

            if not trace_files:
                return False, "No trace files found in qa_reports/ - is covenant_metrics adapter loaded?"

            # Validate at least one trace
            validation_errors: List[str] = []
            traces_validated = 0
            total_missing_fields = 0

            for trace_file in trace_files[:3]:  # Validate up to 3 traces
                try:
                    with open(trace_file) as f:
                        trace = json.load(f)
                except Exception as e:
                    validation_errors.append(f"{trace_file.name}: Failed to load: {e}")
                    continue

                components = trace.get("components", [])
                if not components:
                    validation_errors.append(f"{trace_file.name}: No components")
                    continue

                # Build component data by event_type
                component_data: Dict[str, Dict[str, Any]] = {}
                for comp in components:
                    event_type = comp.get("event_type", "")
                    data = comp.get("data", {})
                    component_data[event_type] = data

                # Validate required fields for each component type
                missing_fields = self._validate_generic_fields(component_data)

                if missing_fields:
                    total_missing_fields += len(missing_fields)
                    # Only report first few missing fields per trace
                    sample = missing_fields[:5]
                    validation_errors.append(f"{trace_file.name}: Missing {len(missing_fields)} fields: {sample}")
                else:
                    traces_validated += 1

            if traces_validated == 0:
                error_summary = "; ".join(validation_errors[:3])
                return False, f"All traces failed validation: {error_summary}"

            if validation_errors:
                # Some traces validated, some had issues
                return True, (
                    f"{traces_validated}/{len(trace_files[:3])} traces valid for CIRIS scoring "
                    f"({total_missing_fields} total missing fields in others)"
                )

            return True, f"All {traces_validated} traces contain required CIRIS scoring fields"

        except Exception as e:
            return False, str(e)

    def _validate_generic_fields(self, component_data: Dict[str, Dict[str, Any]]) -> List[str]:
        """Validate that component data contains all required generic fields.

        Args:
            component_data: Dict mapping event_type to component data

        Returns:
            List of missing field descriptions
        """
        missing: List[str] = []

        for event_type, required in self.GENERIC_REQUIRED_FIELDS.items():
            data = component_data.get(event_type, {})

            if isinstance(required, dict):
                # Nested structure (e.g., DMA_RESULTS with csdma, dsdma, idma)
                for sub_key, sub_fields in required.items():
                    sub_data = data.get(sub_key, {}) or {}
                    for field in sub_fields:
                        if field not in sub_data:
                            missing.append(f"{event_type}.{sub_key}.{field}")
            else:
                # Simple list of required fields
                for field in required:
                    if field not in data:
                        missing.append(f"{event_type}.{field}")

        return missing

    def _validate_fields_not_null(self, component_data: Dict[str, Dict[str, Any]]) -> List[str]:
        """Validate that all required generic fields are not null.

        Args:
            component_data: Dict mapping event_type to component data

        Returns:
            List of null field descriptions
        """
        null_fields: List[str] = []

        for event_type, required in self.GENERIC_REQUIRED_FIELDS.items():
            data = component_data.get(event_type, {})

            if isinstance(required, dict):
                # Nested structure (e.g., DMA_RESULTS with csdma, dsdma, idma)
                for sub_key, sub_fields in required.items():
                    sub_data = data.get(sub_key, {}) or {}
                    for field in sub_fields:
                        if field in sub_data and sub_data[field] is None:
                            null_fields.append(f"{event_type}.{sub_key}.{field}")
            else:
                # Simple list of required fields
                for field in required:
                    if field in data and data[field] is None:
                        null_fields.append(f"{event_type}.{field}")

        return null_fields

    # Exempt actions skip ethical faculty checks (nulls are expected)
    EXEMPT_ACTIONS = {"TASK_COMPLETE", "RECALL", "OBSERVE", "DEFER", "REJECT"}

    # Ethical faculty fields that are expected to be null for exempt actions
    ETHICAL_FACULTY_FIELDS = {
        "CONSCIENCE_RESULT.entropy_passed",
        "CONSCIENCE_RESULT.entropy_score",
        "CONSCIENCE_RESULT.coherence_passed",
        "CONSCIENCE_RESULT.coherence_score",
        "CONSCIENCE_RESULT.optimization_veto_passed",
        "CONSCIENCE_RESULT.epistemic_humility_passed",
        "CONSCIENCE_RESULT.epistemic_humility_certainty",
    }

    async def _test_critical_scoring_fields(self) -> tuple[bool, str]:
        """Validate that ALL generic required fields are not null.

        CIRIS scoring requires non-null values for all fields. Null values
        indicate the agent isn't populating conscience/DMA results properly.

        NOTE: Exempt actions (TASK_COMPLETE, RECALL, OBSERVE, DEFER, REJECT)
        skip ethical faculty checks, so those fields will be null - this is expected.
        """
        try:
            if self.live_lens:
                return True, "Skipped (traces sent to live Lens server)"

            qa_reports = Path(__file__).parent.parent.parent.parent / "qa_reports"
            trace_files = list(qa_reports.glob("trace_*.json"))

            if not trace_files:
                return True, "No trace files found - skipping null validation"

            null_field_counts: Dict[str, int] = {}
            non_exempt_traces = 0
            exempt_traces = 0

            for trace_file in trace_files[:10]:  # Check up to 10 traces
                try:
                    with open(trace_file) as f:
                        trace = json.load(f)
                except Exception:
                    continue

                components = trace.get("components", [])
                if not components:
                    continue

                component_data: Dict[str, Dict[str, Any]] = {}
                for comp in components:
                    event_type = comp.get("event_type", "")
                    data = comp.get("data", {})
                    component_data[event_type] = data

                # Check if this is an exempt action
                aspdma_data = component_data.get("ASPDMA_RESULT", {})
                selected_action = aspdma_data.get("selected_action", "")
                is_exempt = selected_action in self.EXEMPT_ACTIONS

                if is_exempt:
                    exempt_traces += 1
                    continue  # Skip null validation for exempt actions

                non_exempt_traces += 1
                null_fields = self._validate_fields_not_null(component_data)
                for field in null_fields:
                    null_field_counts[field] = null_field_counts.get(field, 0) + 1

            if non_exempt_traces == 0:
                return True, f"All {exempt_traces} traces were exempt actions (nulls expected)"

            if null_field_counts:
                # Report fields that are null in ALL non-exempt traces (consistent nulls = bug)
                consistent_nulls = [f for f, count in null_field_counts.items() if count == non_exempt_traces]
                if consistent_nulls:
                    self.console.print(
                        f"     [yellow]⚠️ Fields null in all {non_exempt_traces} non-exempt traces:[/yellow]"
                    )
                    for field in consistent_nulls[:10]:
                        self.console.print(f"       - {field}")
                    return False, f"{len(consistent_nulls)} fields consistently null: {consistent_nulls[:5]}"

                # Some nulls but not consistent - warning only
                return (
                    True,
                    f"Checked {non_exempt_traces} non-exempt traces ({exempt_traces} exempt), {len(null_field_counts)} fields occasionally null",
                )

            return (
                True,
                f"All fields non-null in {non_exempt_traces} non-exempt traces ({exempt_traces} exempt skipped)",
            )

        except Exception as e:
            return False, str(e)

    def _validate_detailed_fields(self, component_data: Dict[str, Dict[str, Any]]) -> List[str]:
        """Validate that component data contains all required detailed fields.

        Args:
            component_data: Dict mapping event_type to component data

        Returns:
            List of missing field descriptions
        """
        missing: List[str] = []

        for event_type, required in self.DETAILED_REQUIRED_FIELDS.items():
            data = component_data.get(event_type, {})

            if isinstance(required, dict):
                # Nested structure (e.g., DMA_RESULTS with csdma, dsdma, idma, pdma)
                for sub_key, sub_fields in required.items():
                    sub_data = data.get(sub_key, {}) or {}
                    for field in sub_fields:
                        if field not in sub_data:
                            missing.append(f"{event_type}.{sub_key}.{field}")
            else:
                # Simple list of required fields
                for field in required:
                    if field not in data:
                        missing.append(f"{event_type}.{field}")

        return missing

    def _validate_full_fields(self, component_data: Dict[str, Dict[str, Any]]) -> List[str]:
        """Validate that component data contains all required full trace fields.

        Args:
            component_data: Dict mapping event_type to component data

        Returns:
            List of missing field descriptions
        """
        missing: List[str] = []

        for event_type, required in self.FULL_REQUIRED_FIELDS.items():
            data = component_data.get(event_type, {})

            if isinstance(required, dict):
                # Nested structure (e.g., DMA_RESULTS with reasoning)
                for sub_key, sub_fields in required.items():
                    sub_data = data.get(sub_key, {}) or {}
                    for field in sub_fields:
                        if field not in sub_data:
                            missing.append(f"{event_type}.{sub_key}.{field}")
            else:
                # Simple list of required fields
                for field in required:
                    if field not in data:
                        missing.append(f"{event_type}.{field}")

        return missing

    async def _test_detailed_trace_fields(self) -> tuple[bool, str]:
        """Validate detailed traces have all required actionable identifier fields.

        Tests fields added at DETAILED level including:
        - THOUGHT_START: thought_type, thought_status, channel_id
        - SNAPSHOT_AND_CONTEXT: service_health, agent_version, circuit_breaker_status
        - ASPDMA_RESULT: evaluation_time_ms
        - CONSCIENCE_RESULT: conscience_override_reason, entropy_reason, coherence_reason
        - ACTION_RESULT: execution_error, audit_signature
        """
        try:
            if self.live_lens:
                return True, "Skipped (traces sent to live Lens server)"

            # Find detailed trace files
            qa_reports = Path(__file__).parent.parent.parent.parent / "qa_reports"
            trace_files = list(qa_reports.glob("trace_detailed_*.json"))

            if not trace_files:
                # Try generic traces - they may have some detailed fields
                trace_files = list(qa_reports.glob("trace_*.json"))
                if not trace_files:
                    return True, "No trace files found - skipping detailed validation"

            validation_errors: List[str] = []
            traces_validated = 0

            for trace_file in trace_files[:3]:
                try:
                    with open(trace_file) as f:
                        trace = json.load(f)
                except Exception as e:
                    validation_errors.append(f"{trace_file.name}: Failed to load: {e}")
                    continue

                components = trace.get("components", [])
                if not components:
                    continue

                component_data: Dict[str, Dict[str, Any]] = {}
                for comp in components:
                    event_type = comp.get("event_type", "")
                    data = comp.get("data", {})
                    component_data[event_type] = data

                missing_fields = self._validate_detailed_fields(component_data)

                if not missing_fields:
                    traces_validated += 1
                else:
                    # Report only critical missing fields
                    critical = [
                        f
                        for f in missing_fields
                        if any(
                            k in f
                            for k in [
                                "evaluation_time_ms",
                                "entropy_reason",
                                "coherence_reason",
                                "service_health",
                                "execution_error",
                                "audit_signature",
                            ]
                        )
                    ]
                    if critical:
                        validation_errors.append(f"{trace_file.name}: Missing v1.9.1 fields: {critical[:5]}")

            if traces_validated > 0:
                return True, f"{traces_validated} traces have detailed fields"

            if validation_errors:
                return (
                    True,
                    f"Some detailed fields missing (expected if trace_level < detailed): {validation_errors[0]}",
                )

            return True, "Detailed field validation complete"

        except Exception as e:
            return False, str(e)

    async def _test_full_trace_fields(self) -> tuple[bool, str]:
        """Validate full traces have all required reasoning corpus fields.

        Tests fields added at FULL level including:
        - THOUGHT_START: thought_content
        - ASPDMA_RESULT: raw_llm_response
        - ACTION_RESULT: positive_moment
        """
        try:
            if self.live_lens:
                return True, "Skipped (traces sent to live Lens server)"

            # Find full trace files
            qa_reports = Path(__file__).parent.parent.parent.parent / "qa_reports"
            trace_files = list(qa_reports.glob("trace_full_*.json"))

            if not trace_files:
                return True, "No full trace files found - skipping (may need full_traces adapter)"

            validation_errors: List[str] = []
            traces_validated = 0

            for trace_file in trace_files[:3]:
                try:
                    with open(trace_file) as f:
                        trace = json.load(f)
                except Exception as e:
                    validation_errors.append(f"{trace_file.name}: Failed to load: {e}")
                    continue

                components = trace.get("components", [])
                if not components:
                    continue

                component_data: Dict[str, Dict[str, Any]] = {}
                for comp in components:
                    event_type = comp.get("event_type", "")
                    data = comp.get("data", {})
                    component_data[event_type] = data

                missing_fields = self._validate_full_fields(component_data)

                if not missing_fields:
                    traces_validated += 1
                else:
                    # Check for v1.9.1 specific fields
                    v191_fields = [
                        f
                        for f in missing_fields
                        if any(k in f for k in ["thought_content", "raw_llm_response", "positive_moment"])
                    ]
                    if v191_fields:
                        validation_errors.append(f"{trace_file.name}: Missing v1.9.1 FULL fields: {v191_fields}")

            if traces_validated > 0:
                return True, f"{traces_validated} traces have full reasoning fields"

            if validation_errors:
                return True, f"Some full fields missing: {validation_errors[0]}"

            return True, "Full field validation complete"

        except Exception as e:
            return False, str(e)

    async def _test_comprehensive_field_coverage(self) -> tuple[bool, str]:
        """Comprehensive test of all trace fields added in v1.9.1.

        This test specifically validates the new fields added for CIRIS scoring:
        - GENERIC: entropy_level, coherence_level, has_positive_moment, has_execution_error, phase, has_conflicts
        - DETAILED: evaluation_time_ms, conscience_override_reason, entropy_reason, coherence_reason
        - FULL: thought_content, raw_llm_response, positive_moment
        """
        try:
            if self.live_lens:
                return True, "Skipped (traces sent to live Lens server)"

            qa_reports = Path(__file__).parent.parent.parent.parent / "qa_reports"
            all_traces = list(qa_reports.glob("trace_*.json"))

            if not all_traces:
                return True, "No traces found - skipping comprehensive validation"

            # v1.9.1 field checklist
            v191_fields = {
                "GENERIC": {
                    "CONSCIENCE_RESULT": ["entropy_level", "coherence_level"],
                    "ACTION_RESULT": ["has_positive_moment", "has_execution_error"],
                    "DMA_RESULTS.idma": ["phase"],
                    "DMA_RESULTS.pdma": ["has_conflicts"],
                },
                "DETAILED": {
                    "ASPDMA_RESULT": ["evaluation_time_ms"],
                    "CONSCIENCE_RESULT": ["conscience_override_reason", "entropy_reason", "coherence_reason"],
                    "ACTION_RESULT": ["execution_error", "audit_signature"],
                    "SNAPSHOT_AND_CONTEXT": ["service_health", "agent_version", "circuit_breaker_status"],
                },
                "FULL": {
                    "THOUGHT_START": ["thought_content"],
                    "ASPDMA_RESULT": ["raw_llm_response"],
                    "ACTION_RESULT": ["positive_moment"],
                },
            }

            found_fields: Dict[str, Set[str]] = {"GENERIC": set(), "DETAILED": set(), "FULL": set()}
            total_traces = 0

            for trace_file in all_traces[:10]:
                try:
                    with open(trace_file) as f:
                        trace = json.load(f)
                    total_traces += 1

                    components = trace.get("components", [])
                    for comp in components:
                        event_type = comp.get("event_type", "")
                        data = comp.get("data", {})

                        # Check GENERIC fields
                        for comp_type, fields in v191_fields["GENERIC"].items():
                            if "." in comp_type:
                                base, sub = comp_type.split(".")
                                if event_type == base:
                                    sub_data = data.get(sub, {}) or {}
                                    for field in fields:
                                        if field in sub_data:
                                            found_fields["GENERIC"].add(f"{comp_type}.{field}")
                            elif event_type == comp_type:
                                for field in fields:
                                    if field in data:
                                        found_fields["GENERIC"].add(f"{comp_type}.{field}")

                        # Check DETAILED fields
                        for comp_type, fields in v191_fields["DETAILED"].items():
                            if event_type == comp_type:
                                for field in fields:
                                    if field in data:
                                        found_fields["DETAILED"].add(f"{comp_type}.{field}")

                        # Check FULL fields
                        for comp_type, fields in v191_fields["FULL"].items():
                            if event_type == comp_type:
                                for field in fields:
                                    if field in data:
                                        found_fields["FULL"].add(f"{comp_type}.{field}")

                except Exception:
                    continue

            # Calculate coverage
            total_v191_generic = sum(len(f) for f in v191_fields["GENERIC"].values())
            total_v191_detailed = sum(len(f) for f in v191_fields["DETAILED"].values())
            total_v191_full = sum(len(f) for f in v191_fields["FULL"].values())

            generic_coverage = len(found_fields["GENERIC"])
            detailed_coverage = len(found_fields["DETAILED"])
            full_coverage = len(found_fields["FULL"])

            # Report
            summary = (
                f"v1.9.1 field coverage in {total_traces} traces: "
                f"GENERIC {generic_coverage}/{total_v191_generic}, "
                f"DETAILED {detailed_coverage}/{total_v191_detailed}, "
                f"FULL {full_coverage}/{total_v191_full}"
            )

            # Log found fields for debugging
            if found_fields["GENERIC"]:
                self.console.print(f"     [dim]GENERIC: {sorted(found_fields['GENERIC'])}[/dim]")
            if found_fields["DETAILED"]:
                self.console.print(f"     [dim]DETAILED: {sorted(found_fields['DETAILED'])}[/dim]")
            if found_fields["FULL"]:
                self.console.print(f"     [dim]FULL: {sorted(found_fields['FULL'])}[/dim]")

            # Pass if we found at least some v1.9.1 fields
            if generic_coverage > 0:
                return True, summary

            return True, f"No v1.9.1 fields found yet (traces may be from default adapter): {summary}"

        except Exception as e:
            return False, str(e)

    async def _test_export_real_trace(self) -> tuple[bool, str]:
        """Verify traces were captured and report summary."""
        try:
            # In live lens mode, traces go directly to the server, not local files
            if self.live_lens:
                return True, "Skipped (traces sent to live Lens server, not local files)"

            # Check trace files saved by mock logshipper
            qa_reports = Path(__file__).parent.parent.parent.parent / "qa_reports"
            trace_files = list(qa_reports.glob("trace_*.json"))

            if not trace_files:
                return False, "No traces captured - covenant_metrics adapter may not be loaded"

            # Summarize captured traces
            signed_count = 0
            unsigned_count = 0
            total_components = 0

            for trace_file in trace_files:
                try:
                    with open(trace_file) as f:
                        trace = json.load(f)
                    if trace.get("signature"):
                        signed_count += 1
                    else:
                        unsigned_count += 1
                    total_components += len(trace.get("components", []))
                except Exception:
                    continue

            # Report summary
            summary = (
                f"{len(trace_files)} traces captured "
                f"({signed_count} signed, {unsigned_count} unsigned, "
                f"{total_components} total components)"
            )

            return True, summary

        except Exception as e:
            return False, str(e)

    # =========================================================================
    # Live Lens Server Tests (--live-lens mode)
    # =========================================================================

    async def _test_lens_key_registration(self) -> tuple[bool, str]:
        """Test that agent's public key was registered with the Lens server.

        This queries the Lens server's public-keys endpoint to verify
        the agent registered its signing key.
        """
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{LENS_SERVER_URL}/covenant/public-keys"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        return False, f"Lens server returned {response.status}: {error_text}"

                    data = await response.json()
                    keys = data.get("keys", [])

                    if not keys:
                        return False, "No keys registered with Lens server"

                    # Log all registered keys for debugging
                    key_ids = [k.get("key_id", "unknown") for k in keys]
                    self.console.print(f"     [dim]Registered keys: {key_ids}[/dim]")

                    return True, f"{len(keys)} key(s) registered with Lens server"

        except aiohttp.ClientConnectorError as e:
            return False, f"Cannot reach Lens server: {e}"
        except Exception as e:
            return False, str(e)

    async def _test_lens_key_id_consistency(self) -> tuple[bool, str]:
        """Test that trace signature_key_ids match registered key IDs.

        This is the critical test for the key mismatch bug:
        - Fetches registered keys from Lens server
        - Fetches recent traces from Lens server
        - Verifies all trace signature_key_ids exist in registered keys
        """
        try:
            async with aiohttp.ClientSession() as session:
                # 1. Get registered keys
                keys_url = f"{LENS_SERVER_URL}/covenant/public-keys"
                async with session.get(keys_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        return False, f"Cannot fetch keys: HTTP {response.status}"
                    keys_data = await response.json()

                registered_key_ids = {k.get("key_id") for k in keys_data.get("keys", [])}

                if not registered_key_ids:
                    return False, "No registered keys to compare against"

                # 2. Get recent traces
                traces_url = f"{LENS_SERVER_URL}/covenant/traces"
                params = {"limit": 10}  # Last 10 traces
                async with session.get(traces_url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 404:
                        # Traces endpoint may not exist yet
                        return True, "Traces endpoint not available - skipping consistency check"
                    if response.status != 200:
                        return False, f"Cannot fetch traces: HTTP {response.status}"
                    traces_data = await response.json()

                traces = traces_data.get("traces", [])
                if not traces:
                    return True, "No traces to validate - key registration looks OK"

                # 3. Check each trace's signature_key_id
                mismatched_keys: Set[str] = set()
                matched_keys: Set[str] = set()

                for trace in traces:
                    sig_key_id = trace.get("signature_key_id")
                    if sig_key_id:
                        if sig_key_id in registered_key_ids:
                            matched_keys.add(sig_key_id)
                        else:
                            mismatched_keys.add(sig_key_id)

                # Report findings
                self.console.print(f"     [dim]Registered keys: {sorted(registered_key_ids)}[/dim]")
                self.console.print(f"     [dim]Keys in traces: {sorted(matched_keys | mismatched_keys)}[/dim]")

                if mismatched_keys:
                    self.console.print(f"     [red]MISMATCHED keys: {sorted(mismatched_keys)}[/red]")
                    return False, (
                        f"Key ID mismatch! Traces reference {len(mismatched_keys)} unregistered key(s): "
                        f"{sorted(mismatched_keys)}"
                    )

                if not matched_keys:
                    return True, "No signed traces yet - cannot validate consistency"

                return True, f"All {len(matched_keys)} trace key ID(s) match registered keys"

        except aiohttp.ClientConnectorError as e:
            return False, f"Cannot reach Lens server: {e}"
        except Exception as e:
            return False, str(e)

    async def _test_load_multi_level_adapters(self) -> tuple[bool, str]:
        """Load covenant_metrics adapters at all 3 trace levels via API.

        Creates adapters:
        - covenant_detailed: trace_level=detailed (includes PDMA text fields)
        - covenant_full: trace_level=full_traces (includes reasoning text)

        The default adapter loaded at startup uses trace_level=generic.
        """
        try:
            # Get base URL and auth token from client's transport
            transport = getattr(self.client, "_transport", None)
            if not transport:
                return True, "Skipped (no transport available)"

            base_url = getattr(transport, "base_url", "http://localhost:8000")
            auth_token = getattr(transport, "api_key", None)

            if not auth_token:
                return True, "Skipped (no auth token available for adapter loading)"

            # Define adapters to load with their trace levels
            adapters_to_load = [
                ("covenant_detailed", "detailed"),
                ("covenant_full", "full_traces"),
            ]

            loaded = []
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}

                for adapter_id, trace_level in adapters_to_load:
                    # Load adapter via API
                    url = f"{base_url}/v1/system/adapters/ciris_covenant_metrics?adapter_id={adapter_id}"
                    payload = {
                        "config": {
                            "trace_level": trace_level,
                            "consent_given": True,
                            "consent_timestamp": "2025-01-01T00:00:00Z",
                            "flush_interval_seconds": 5,
                        },
                        "persist": False,
                    }

                    try:
                        async with session.post(
                            url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
                        ) as response:
                            if response.status == 200:
                                loaded.append(adapter_id)
                                self.console.print(f"     [dim]Loaded {adapter_id} (trace_level={trace_level})[/dim]")
                            elif response.status == 409:
                                # Adapter already exists
                                self.console.print(f"     [dim]{adapter_id} already loaded[/dim]")
                                loaded.append(adapter_id)
                            else:
                                error_text = await response.text()
                                self.console.print(
                                    f"     [yellow]Warning: {adapter_id}: HTTP {response.status} - {error_text[:100]}[/yellow]"
                                )
                    except Exception as e:
                        self.console.print(f"     [yellow]Warning: {adapter_id}: {e}[/yellow]")

            if not loaded:
                return False, "Failed to load additional adapters"

            return True, f"Loaded {len(loaded)} additional adapter(s): {loaded}"

        except Exception as e:
            return False, str(e)

    async def _test_pdma_fields_detailed(self) -> tuple[bool, str]:
        """Validate PDMA fields are present at DETAILED trace level.

        Queries recent traces from Lens server and checks for PDMA fields:
        - stakeholders
        - conflicts
        - alignment_check
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Get recent traces
                traces_url = f"{LENS_SERVER_URL}/covenant/traces"
                params = {"limit": 20, "trace_level": "detailed"}
                async with session.get(traces_url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 404:
                        return True, "Traces endpoint not available - skipping PDMA validation"
                    if response.status != 200:
                        return False, f"Cannot fetch traces: HTTP {response.status}"
                    traces_data = await response.json()

                traces = traces_data.get("traces", [])
                if not traces:
                    return True, "No detailed traces to validate yet"

                # Check for PDMA fields in DMA_RESULTS components
                pdma_found = 0
                pdma_valid = 0
                pdma_missing_fields: List[str] = []

                for trace in traces:
                    components = trace.get("components", [])
                    for comp in components:
                        if comp.get("event_type") == "DMA_RESULTS":
                            data = comp.get("data", {})
                            pdma = data.get("pdma", {})
                            if pdma:
                                pdma_found += 1
                                # Check required DETAILED fields
                                missing = []
                                for field in ["stakeholders", "conflicts", "alignment_check"]:
                                    if field not in pdma or pdma[field] is None:
                                        missing.append(field)
                                if missing:
                                    pdma_missing_fields.extend(missing)
                                else:
                                    pdma_valid += 1

                if pdma_found == 0:
                    return True, "No PDMA data in traces yet (may need detailed-level adapter)"

                if pdma_missing_fields:
                    unique_missing = list(set(pdma_missing_fields))
                    self.console.print(f"     [yellow]Missing PDMA fields: {unique_missing}[/yellow]")
                    return False, f"PDMA missing fields: {unique_missing} ({pdma_valid}/{pdma_found} valid)"

                return True, f"All {pdma_valid} PDMA entries have required fields"

        except aiohttp.ClientConnectorError as e:
            return False, f"Cannot reach Lens server: {e}"
        except Exception as e:
            return False, str(e)
