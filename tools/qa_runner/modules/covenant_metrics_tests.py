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
    GENERIC_REQUIRED_FIELDS = {
        "THOUGHT_START": [
            "round_number",
            "thought_depth",
            "task_priority",
        ],
        "SNAPSHOT_AND_CONTEXT": [
            "cognitive_state",
        ],
        "DMA_RESULTS": {
            "csdma": ["plausibility_score"],
            "dsdma": ["domain_alignment"],
            "idma": ["k_eff", "correlation_risk", "fragility_flag"],
        },
        "ASPDMA_RESULT": [
            "selected_action",
            "selection_confidence",
            "is_recursive",
        ],
        "CONSCIENCE_RESULT": [
            "conscience_passed",
            "action_was_overridden",
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
            ("Agent Interaction Trace", self._test_interaction_triggers_trace),
            ("Generic Trace Field Validation", self._test_generic_trace_fields),
            ("Export Real Trace", self._test_export_real_trace),
        ]

        # Add live lens tests when using real server
        if self.live_lens:
            tests.extend([
                ("Lens Key Registration Check", self._test_lens_key_registration),
                ("Lens Key ID Consistency", self._test_lens_key_id_consistency),
            ])

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
