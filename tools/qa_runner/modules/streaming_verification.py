"""
Reasoning Event Streaming Verification Module.

Validates that the 6 simplified reasoning events are properly streaming
via Server-Sent Events (SSE) to the reasoning-stream endpoint, and that
ONLY those 6 events are emitted (no extras from the 11 step points).

Also tests backend localization by changing user language preference and
verifying localized strings appear in conscience/ponder events.
"""

import json
import logging
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

from ..config import QAConfig, QAModule, QATestCase

logger = logging.getLogger(__name__)


class StreamingVerificationModule:
    """Verify reasoning events are streaming correctly."""

    # Core reasoning events expected (with 60s timeout for wakeup to complete)
    # Note: tsaspdma_result is optional (only emitted for TOOL actions)
    EXPECTED_EVENTS = {
        "thought_start",
        "snapshot_and_context",
        "dma_results",
        "idma_result",  # v1.9.3: IDMA epistemic diversity evaluation
        "aspdma_result",
        "conscience_result",
        "action_result",
    }

    # Optional events that may be emitted depending on action type
    OPTIONAL_EVENTS = {
        "tsaspdma_result",  # v1.9.3: Only emitted when ASPDMA selects TOOL action
    }

    @staticmethod
    def verify_streaming_events(base_url: str, token: str, timeout: int = 60) -> Dict[str, Any]:
        """
        Connect to SSE stream and verify reasoning events are received.

        Returns:
            Dict with verification results including received events and any issues.
        """
        received_events: Set[str] = set()
        event_details: List[Dict[str, Any]] = []
        errors: List[str] = []
        start_time = time.time()

        # Track event-specific data
        events_with_audit_data = 0
        events_with_recursive_flag = 0
        recursive_aspdma_count = 0
        recursive_conscience_count = 0

        # Track first snapshot_and_context event for field validation
        first_snapshot_printed = False
        unexpected_events: Set[str] = set()  # Track events outside the expected 6

        # Track duplicates: (thought_id, event_type) -> count
        event_occurrences: Dict[Tuple[str, str], int] = {}
        duplicates_found: List[str] = []

        # Shared state for thread communication
        stream_connected = threading.Event()
        stream_error = threading.Event()

        def monitor_stream() -> None:
            """Monitor SSE stream in a separate thread."""
            nonlocal events_with_audit_data, events_with_recursive_flag
            nonlocal recursive_aspdma_count, recursive_conscience_count, unexpected_events
            nonlocal event_occurrences, duplicates_found, first_snapshot_printed

            try:
                headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream"}

                logger.debug("SSE client connecting to reasoning-stream endpoint")
                response = requests.get(
                    f"{base_url}/v1/system/runtime/reasoning-stream", headers=headers, stream=True, timeout=5
                )

                if response.status_code != 200:
                    logger.debug(f"SSE client connection failed with status {response.status_code}")
                    errors.append(f"Stream connection failed: {response.status_code}")
                    stream_error.set()
                    return

                logger.debug("SSE client connected successfully, starting to listen for events")
                stream_connected.set()

                # Parse SSE stream
                for line in response.iter_lines():
                    if not line:
                        continue

                    line = line.decode("utf-8") if isinstance(line, bytes) else line

                    # Only process data lines
                    if line.startswith("data:"):
                        try:
                            data = json.loads(line[6:])

                            # Extract events from stream update
                            events = data.get("events", [])
                            logger.debug(f"SSE client received {len(events)} events from stream")

                            for event in events:
                                event_type = event.get("event_type")

                                if not event_type:
                                    errors.append("Event missing event_type field")
                                    continue

                                logger.debug(
                                    f"SSE client processing event - type={event_type}, task_id={event.get('task_id')}"
                                )

                                # Track this event type
                                received_events.add(event_type)

                                # Check if this is an unexpected event (not expected or optional)
                                all_valid_events = (
                                    StreamingVerificationModule.EXPECTED_EVENTS
                                    | StreamingVerificationModule.OPTIONAL_EVENTS
                                )
                                if event_type not in all_valid_events:
                                    unexpected_events.add(event_type)

                                # Track duplicates: (thought_id, event_type)
                                # Allow duplicates if is_recursive=True (legitimate recursive processing)
                                thought_id = event.get("thought_id")
                                is_recursive = event.get("is_recursive", False)
                                if thought_id:
                                    key = (thought_id, event_type)
                                    event_occurrences[key] = event_occurrences.get(key, 0) + 1
                                    if event_occurrences[key] > 1:
                                        # Only flag as duplicate error if NOT recursive
                                        # Recursive processing legitimately re-emits events for the same thought
                                        if not is_recursive:
                                            dup_msg = f"Duplicate {event_type} for thought {thought_id} (occurrence #{event_occurrences[key]})"
                                            if dup_msg not in duplicates_found:
                                                duplicates_found.append(dup_msg)
                                                errors.append(dup_msg)
                                        else:
                                            logger.debug(
                                                f"Allowed recursive duplicate: {event_type} for thought {thought_id} "
                                                f"(occurrence #{event_occurrences[key]}, is_recursive=True)"
                                            )

                                # Validate event structure
                                event_detail = {
                                    "event_type": event_type,
                                    "thought_id": event.get("thought_id"),
                                    "task_id": event.get("task_id"),
                                    "timestamp": event.get("timestamp"),
                                    "issues": [],
                                }

                                # Event-specific validation (comprehensive schema checks)
                                if event_type == "thought_start":
                                    # Required fields per schema
                                    required_fields = {
                                        "thought_type": str,
                                        "thought_content": str,
                                        "task_description": str,
                                        "round_number": int,
                                        "thought_id": str,
                                        "task_id": str,
                                        "timestamp": str,
                                    }
                                    for field, field_type in required_fields.items():
                                        if field not in event:
                                            event_detail["issues"].append(f"Missing required field: {field}")
                                        elif not isinstance(event[field], field_type):
                                            event_detail["issues"].append(
                                                f"Field {field} has wrong type: {type(event[field]).__name__} (expected {field_type.__name__})"
                                            )
                                        elif field_type == str and not event[field]:
                                            event_detail["issues"].append(f"Empty string for required field: {field}")

                                elif event_type == "snapshot_and_context":
                                    # Required fields per schema
                                    required_fields = {
                                        "system_snapshot": dict,
                                        "thought_id": str,
                                        "task_id": str,
                                        "timestamp": str,
                                    }
                                    for field, field_type in required_fields.items():
                                        if field not in event:
                                            event_detail["issues"].append(f"Missing required field: {field}")
                                        elif not isinstance(event[field], field_type):
                                            event_detail["issues"].append(
                                                f"Field {field} has wrong type: {type(event[field]).__name__} (expected {field_type.__name__})"
                                            )
                                        elif field_type == str and not event[field]:
                                            event_detail["issues"].append(f"Empty string for required field: {field}")

                                    # Validate SystemSnapshot schema deeply
                                    if "system_snapshot" in event and isinstance(event["system_snapshot"], dict):
                                        snapshot = event["system_snapshot"]

                                        # SystemSnapshot optional fields that should be proper types when present
                                        snapshot_field_types = {
                                            "channel_id": (str, type(None)),
                                            "channel_context": (dict, type(None)),
                                            "current_task_details": (dict, type(None)),
                                            "current_thought_summary": (dict, type(None)),
                                            "system_counts": (dict,),  # dict is required, but can be empty
                                            "top_pending_tasks_summary": (list,),  # list is required, but can be empty
                                            "recently_completed_tasks_summary": (
                                                list,
                                            ),  # list is required, but can be empty
                                            "agent_identity": (str, type(None)),
                                            "user_profiles": (list, type(None)),
                                            "current_time_utc": (str, type(None)),
                                            "continuity_summary": (
                                                dict,
                                                type(None),
                                            ),  # ContinuitySummary - should be dict not null
                                            "telemetry_summary": (
                                                dict,
                                                type(None),
                                            ),  # TelemetrySummary - should be dict not null
                                        }

                                        for field, allowed_types in snapshot_field_types.items():
                                            if field in snapshot:
                                                if not isinstance(snapshot[field], allowed_types):
                                                    event_detail["issues"].append(
                                                        f"system_snapshot.{field} has wrong type: {type(snapshot[field]).__name__} "
                                                        f"(expected one of {[t.__name__ for t in allowed_types]})"
                                                    )

                                        # Warn if critical optional fields are None or empty (production issue check)
                                        if snapshot.get("continuity_summary") is None:
                                            event_detail["issues"].append(
                                                "system_snapshot.continuity_summary is None (should be ContinuitySummary dict)"
                                            )
                                        if snapshot.get("telemetry_summary") is None:
                                            event_detail["issues"].append(
                                                "system_snapshot.telemetry_summary is None (should be TelemetrySummary dict)"
                                            )
                                        # Validate telemetry_summary.circuit_breaker is not null and has proper structure
                                        telemetry = snapshot.get("telemetry_summary")
                                        if telemetry and isinstance(telemetry, dict):
                                            if "circuit_breaker" not in telemetry:
                                                issue_msg = (
                                                    "system_snapshot.telemetry_summary missing 'circuit_breaker' field"
                                                )
                                                event_detail["issues"].append(issue_msg)
                                                errors.append(f"🐛 MISSING FIELD: {issue_msg}")
                                            elif telemetry.get("circuit_breaker") is None:
                                                issue_msg = "system_snapshot.telemetry_summary.circuit_breaker is None (should be dict with CircuitBreakerState entries)"
                                                event_detail["issues"].append(issue_msg)
                                                errors.append(f"🐛 NULL FIELD: {issue_msg}")
                                            else:
                                                # Validate CircuitBreakerState schema for each entry
                                                cb_dict = telemetry.get("circuit_breaker")
                                                if isinstance(cb_dict, dict):
                                                    required_cb_fields = {
                                                        "state": str,
                                                        "failure_count": int,
                                                        "success_count": int,
                                                        "total_requests": int,
                                                        "failed_requests": int,
                                                        "consecutive_failures": int,
                                                        "failure_rate": str,
                                                    }
                                                    for service_name, cb_state in cb_dict.items():
                                                        if not isinstance(cb_state, dict):
                                                            issue_msg = f"circuit_breaker[{service_name}] is not a dict (should be CircuitBreakerState)"
                                                            event_detail["issues"].append(issue_msg)
                                                            errors.append(f"🐛 INVALID CB STATE: {issue_msg}")
                                                            continue

                                                        for field, field_type in required_cb_fields.items():
                                                            if field not in cb_state:
                                                                issue_msg = f"circuit_breaker[{service_name}] missing field '{field}'"
                                                                event_detail["issues"].append(issue_msg)
                                                                errors.append(f"🐛 CB MISSING FIELD: {issue_msg}")
                                                            elif not isinstance(cb_state[field], field_type):
                                                                issue_msg = f"circuit_breaker[{service_name}].{field} has wrong type: {type(cb_state[field]).__name__} (expected {field_type.__name__})"
                                                                event_detail["issues"].append(issue_msg)
                                                                errors.append(f"🐛 CB WRONG TYPE: {issue_msg}")
                                        # Check service_health - should have entries for all services
                                        service_health = snapshot.get("service_health", {})
                                        if not service_health or not isinstance(service_health, dict):
                                            event_detail["issues"].append(
                                                f"system_snapshot.service_health is empty or invalid: {service_health}"
                                            )
                                        elif len(service_health) < 20:  # Should have ~22+ services
                                            event_detail["issues"].append(
                                                f"system_snapshot.service_health only has {len(service_health)} services (expected 20+)"
                                            )

                                        # Check user_profiles - should ALWAYS exist (at minimum, API user for wakeup tasks)
                                        if "user_profiles" not in snapshot:
                                            issue_msg = "system_snapshot.user_profiles is MISSING (should always be present, at minimum for API user)"
                                            event_detail["issues"].append(issue_msg)
                                            errors.append(f"🐛 MISSING FIELD: {issue_msg}")
                                        elif snapshot.get("user_profiles") is None:
                                            issue_msg = "system_snapshot.user_profiles is None (should be list, at minimum with API user)"
                                            event_detail["issues"].append(issue_msg)
                                            errors.append(f"🐛 NULL FIELD: {issue_msg}")
                                        elif not isinstance(snapshot.get("user_profiles"), list):
                                            issue_msg = f"system_snapshot.user_profiles has wrong type: {type(snapshot.get('user_profiles')).__name__} (expected list)"
                                            event_detail["issues"].append(issue_msg)
                                            errors.append(f"🐛 WRONG TYPE: {issue_msg}")
                                        elif len(snapshot.get("user_profiles", [])) == 0:
                                            # Empty user_profiles is valid during wakeup or system tasks
                                            # Log concise info for visibility but don't treat as error
                                            logger.debug(
                                                f"Empty user_profiles (valid for wakeup/system tasks) - thought={event.get('thought_id')}, "
                                                f"task={event.get('task_id')}, channel={snapshot.get('channel_id')}"
                                            )
                                        else:
                                            # Validate user profile structure for each profile
                                            user_profiles = snapshot.get("user_profiles", [])
                                            for i, profile in enumerate(user_profiles):
                                                if not isinstance(profile, dict):
                                                    issue_msg = (
                                                        f"user_profiles[{i}] is not a dict: {type(profile).__name__}"
                                                    )
                                                    event_detail["issues"].append(issue_msg)
                                                    errors.append(f"🐛 INVALID PROFILE: {issue_msg}")
                                                    continue
                                                # Check for required user_id field
                                                if "user_id" not in profile:
                                                    issue_msg = f"user_profiles[{i}] missing required 'user_id' field"
                                                    event_detail["issues"].append(issue_msg)
                                                    errors.append(f"🐛 PROFILE MISSING user_id: {issue_msg}")
                                                elif not isinstance(profile["user_id"], str) or not profile["user_id"]:
                                                    issue_msg = f"user_profiles[{i}].user_id is invalid: {profile.get('user_id')}"
                                                    event_detail["issues"].append(issue_msg)
                                                    errors.append(f"🐛 INVALID user_id: {issue_msg}")
                                                # Check for display_name field (should exist)
                                                if "display_name" not in profile:
                                                    issue_msg = f"user_profiles[{i}] missing 'display_name' field"
                                                    event_detail["issues"].append(issue_msg)
                                                    # This is a warning, not a critical error
                                                elif not isinstance(profile["display_name"], str):
                                                    issue_msg = f"user_profiles[{i}].display_name has wrong type: {type(profile['display_name']).__name__}"
                                                    event_detail["issues"].append(issue_msg)

                                        # Print first occurrence of critical fields for validation
                                        if not first_snapshot_printed:
                                            first_snapshot_printed = True
                                            print("\n" + "=" * 80)
                                            print("📊 FIRST SNAPSHOT_AND_CONTEXT EVENT - Field Validation")
                                            print("=" * 80)

                                            # Print service_health
                                            print(f"\n🔧 service_health ({len(service_health)} services):")
                                            if service_health:
                                                for i, (service_name, is_healthy) in enumerate(
                                                    sorted(service_health.items()), 1
                                                ):
                                                    status = "✓" if is_healthy else "✗"
                                                    print(f"  {i:2d}. {status} {service_name}: {is_healthy}")
                                            else:
                                                print("  (empty)")

                                            # Print continuity_summary
                                            continuity = snapshot.get("continuity_summary")
                                            print(f"\n📈 continuity_summary:")
                                            if continuity:
                                                print(f"  Type: {type(continuity).__name__}")
                                                if isinstance(continuity, dict):
                                                    for key, value in sorted(continuity.items()):
                                                        print(f"  - {key}: {value}")
                                            else:
                                                print("  (None)")

                                            # Print telemetry_summary
                                            telemetry = snapshot.get("telemetry_summary")
                                            print(f"\n📊 telemetry_summary:")
                                            if telemetry:
                                                print(f"  Type: {type(telemetry).__name__}")
                                                if isinstance(telemetry, dict):
                                                    # Print circuit_breaker first (critical field) with CircuitBreakerState validation
                                                    if "circuit_breaker" in telemetry:
                                                        cb = telemetry["circuit_breaker"]
                                                        print(f"\n  🔴 circuit_breaker (CircuitBreakerState schema):")
                                                        if cb is None:
                                                            print("     ❌ NULL (should be dict!)")
                                                        elif isinstance(cb, dict):
                                                            if not cb:
                                                                print(
                                                                    "     ✓ Empty dict (no circuit breakers triggered)"
                                                                )
                                                            else:
                                                                print(f"     ✓ Type: dict with {len(cb)} service(s)")
                                                                for service_name, cb_state in sorted(cb.items()):
                                                                    if isinstance(cb_state, dict):
                                                                        state = cb_state.get("state", "unknown")
                                                                        failures = cb_state.get("failure_count", 0)
                                                                        rate = cb_state.get("failure_rate", "0.00%")
                                                                        print(
                                                                            f"     - {service_name}: state={state}, failures={failures}, rate={rate}"
                                                                        )
                                                                    else:
                                                                        print(
                                                                            f"     - {service_name}: ⚠️ Invalid (not CircuitBreakerState dict)"
                                                                        )
                                                        else:
                                                            print(f"     ⚠️  Wrong type: {type(cb).__name__}")
                                                    else:
                                                        print(f"\n  🔴 circuit_breaker: ❌ MISSING")

                                                    print(f"\n  Other fields:")
                                                    for key, value in sorted(telemetry.items()):
                                                        if key == "circuit_breaker":
                                                            continue  # Already printed above
                                                        # Truncate long values
                                                        val_str = str(value)
                                                        if len(val_str) > 60:
                                                            val_str = val_str[:57] + "..."
                                                        print(f"  - {key}: {val_str}")
                                            else:
                                                print("  (None)")

                                            # Print user_profiles
                                            user_profiles = snapshot.get("user_profiles")
                                            print(f"\n👥 user_profiles:")
                                            if user_profiles is None:
                                                print("  ❌ NULL (should be list with at least API user!)")
                                            elif not isinstance(user_profiles, list):
                                                print(
                                                    f"  ⚠️  Wrong type: {type(user_profiles).__name__} (should be list)"
                                                )
                                            elif len(user_profiles) == 0:
                                                print("  ℹ️  Empty list (valid for wakeup/system tasks)")
                                            else:
                                                print(f"  ✓ Type: list with {len(user_profiles)} profile(s)")
                                                for i, profile in enumerate(user_profiles, 1):
                                                    if isinstance(profile, dict):
                                                        user_id = profile.get("user_id", "MISSING")
                                                        display_name = profile.get("display_name", "MISSING")
                                                        # Show additional fields if present
                                                        extra_fields = []
                                                        if "user_preferred_name" in profile:
                                                            extra_fields.append(
                                                                f"preferred_name={profile['user_preferred_name']}"
                                                            )
                                                        if "location" in profile:
                                                            extra_fields.append(f"location={profile['location']}")
                                                        extra_str = (
                                                            f" ({', '.join(extra_fields)})" if extra_fields else ""
                                                        )
                                                        print(
                                                            f"  {i}. user_id={user_id}, display_name={display_name}{extra_str}"
                                                        )
                                                    else:
                                                        print(
                                                            f"  {i}. ⚠️ Invalid profile (not dict): {type(profile).__name__}"
                                                        )

                                            print("=" * 80 + "\n")

                                elif event_type == "dma_results":
                                    # Required base fields
                                    required_fields = {
                                        "thought_id": str,
                                        "task_id": str,
                                        "timestamp": str,
                                    }
                                    for field, field_type in required_fields.items():
                                        if field not in event:
                                            event_detail["issues"].append(f"Missing required field: {field}")
                                        elif not isinstance(event[field], field_type):
                                            event_detail["issues"].append(
                                                f"Field {field} has wrong type: {type(event[field]).__name__} (expected {field_type.__name__})"
                                            )

                                    # All 3 DMA results are REQUIRED (non-optional strongly-typed objects)
                                    # CSDMA: Common Sense DMA
                                    if "csdma" not in event:
                                        event_detail["issues"].append("Missing required field: csdma")
                                    elif not isinstance(event["csdma"], dict):
                                        event_detail["issues"].append("csdma should be dict (CSDMAResult)")
                                    else:
                                        # CSDMAResult schema: plausibility_score, flags, reasoning
                                        if "plausibility_score" not in event["csdma"]:
                                            event_detail["issues"].append("csdma missing 'plausibility_score' field")
                                        elif not isinstance(event["csdma"]["plausibility_score"], (int, float)):
                                            event_detail["issues"].append("csdma.plausibility_score should be float")
                                        if "flags" not in event["csdma"]:
                                            event_detail["issues"].append("csdma missing 'flags' field")
                                        elif not isinstance(event["csdma"]["flags"], list):
                                            event_detail["issues"].append("csdma.flags should be list")
                                        if "reasoning" not in event["csdma"]:
                                            event_detail["issues"].append("csdma missing 'reasoning' field")
                                        elif not isinstance(event["csdma"]["reasoning"], str):
                                            event_detail["issues"].append("csdma.reasoning should be string")

                                    # DSDMA: Domain Specific DMA
                                    if "dsdma" not in event:
                                        event_detail["issues"].append("Missing required field: dsdma")
                                    elif not isinstance(event["dsdma"], dict):
                                        event_detail["issues"].append("dsdma should be dict (DSDMAResult)")
                                    else:
                                        # DSDMAResult schema: domain, domain_alignment, flags, reasoning
                                        if "domain" not in event["dsdma"]:
                                            event_detail["issues"].append("dsdma missing 'domain' field")
                                        elif not isinstance(event["dsdma"]["domain"], str):
                                            event_detail["issues"].append("dsdma.domain should be string")
                                        if "domain_alignment" not in event["dsdma"]:
                                            event_detail["issues"].append("dsdma missing 'domain_alignment' field")
                                        elif not isinstance(event["dsdma"]["domain_alignment"], (int, float)):
                                            event_detail["issues"].append("dsdma.domain_alignment should be float")
                                        if "flags" not in event["dsdma"]:
                                            event_detail["issues"].append("dsdma missing 'flags' field")
                                        elif not isinstance(event["dsdma"]["flags"], list):
                                            event_detail["issues"].append("dsdma.flags should be list")
                                        if "reasoning" not in event["dsdma"]:
                                            event_detail["issues"].append("dsdma missing 'reasoning' field")
                                        elif not isinstance(event["dsdma"]["reasoning"], str):
                                            event_detail["issues"].append("dsdma.reasoning should be string")

                                    # PDMA: Ethical Perspective DMA (from ethical_pdma)
                                    if "pdma" not in event:
                                        event_detail["issues"].append("Missing required field: pdma")
                                    elif not isinstance(event["pdma"], dict):
                                        event_detail["issues"].append("pdma should be dict (EthicalDMAResult)")
                                    else:
                                        # EthicalDMAResult schema: decision, reasoning, alignment_check
                                        if "decision" not in event["pdma"]:
                                            event_detail["issues"].append("pdma missing 'decision' field")
                                        elif not isinstance(event["pdma"]["decision"], str):
                                            event_detail["issues"].append("pdma.decision should be string")
                                        if "reasoning" not in event["pdma"]:
                                            event_detail["issues"].append("pdma missing 'reasoning' field")
                                        elif not isinstance(event["pdma"]["reasoning"], str):
                                            event_detail["issues"].append("pdma.reasoning should be string")
                                        if "alignment_check" not in event["pdma"]:
                                            event_detail["issues"].append("pdma missing 'alignment_check' field")
                                        elif not isinstance(event["pdma"]["alignment_check"], str):
                                            event_detail["issues"].append("pdma.alignment_check should be string")

                                    # Print DMA prompts if present (for benchmark debugging)
                                    print("\n" + "=" * 80)
                                    print("📝 DMA USER PROMPTS (from dma_results event)")
                                    print("=" * 80)
                                    for prompt_key in ["csdma_prompt", "dsdma_prompt", "pdma_prompt"]:
                                        prompt_value = event.get(prompt_key)
                                        if prompt_value:
                                            print(f"\n🔹 {prompt_key.upper()}:")
                                            print("-" * 40)
                                            # Truncate very long prompts for readability
                                            if len(prompt_value) > 5000:
                                                print(
                                                    prompt_value[:5000]
                                                    + f"\n... [truncated, {len(prompt_value)} chars total]"
                                                )
                                            else:
                                                print(prompt_value)
                                        else:
                                            print(f"\n🔹 {prompt_key.upper()}: (not present)")

                                    # Print SYSTEM prompts (for debugging format instructions)
                                    print("\n" + "=" * 80)
                                    print("📝 DMA SYSTEM PROMPTS (format instructions)")
                                    print("=" * 80)
                                    for prompt_key in [
                                        "csdma_system_prompt",
                                        "dsdma_system_prompt",
                                        "pdma_system_prompt",
                                    ]:
                                        prompt_value = event.get(prompt_key)
                                        if prompt_value:
                                            print(f"\n🔹 {prompt_key.upper()}:")
                                            print("-" * 40)
                                            # Truncate very long prompts for readability
                                            if len(prompt_value) > 5000:
                                                print(
                                                    prompt_value[:5000]
                                                    + f"\n... [truncated, {len(prompt_value)} chars total]"
                                                )
                                            else:
                                                print(prompt_value)
                                        else:
                                            print(f"\n🔹 {prompt_key.upper()}: (not present)")
                                    print("=" * 80 + "\n")

                                elif event_type == "idma_result":
                                    # IDMA (Intuition DMA) result - epistemic diversity evaluation
                                    # Added in v1.9.3 for CCA (Coherent Collective Action) source analysis
                                    required_fields = {
                                        "thought_id": str,
                                        "task_id": str,
                                        "timestamp": str,
                                    }
                                    for field, field_type in required_fields.items():
                                        if field not in event:
                                            event_detail["issues"].append(f"Missing required field: {field}")
                                        elif not isinstance(event[field], field_type):
                                            event_detail["issues"].append(
                                                f"Field {field} has wrong type: {type(event[field]).__name__} (expected {field_type.__name__})"
                                            )

                                    # IDMA-specific fields (epistemic evaluation)
                                    idma_fields = {
                                        "k_eff": (int, float),  # Effective source count
                                        "correlation_risk": (int, float),  # Correlation risk score
                                        "fragility_flag": bool,  # Whether reasoning is fragile
                                        "phase": str,  # Epistemic phase
                                        "reasoning": str,  # IDMA reasoning
                                        "sources_identified": list,  # List of identified sources
                                        "correlation_factors": list,  # Correlation factors
                                    }
                                    for field, field_type in idma_fields.items():
                                        if field in event:
                                            if isinstance(field_type, tuple):
                                                if not isinstance(event[field], field_type):
                                                    event_detail["issues"].append(
                                                        f"IDMA field {field} has wrong type: {type(event[field]).__name__}"
                                                    )
                                            elif not isinstance(event[field], field_type):
                                                event_detail["issues"].append(
                                                    f"IDMA field {field} has wrong type: {type(event[field]).__name__} (expected {field_type.__name__})"
                                                )

                                elif event_type == "aspdma_result":
                                    # Required fields per schema
                                    required_fields = {
                                        "selected_action": str,
                                        "action_rationale": str,
                                        "thought_id": str,
                                        "task_id": str,
                                        "timestamp": str,
                                    }
                                    for field, field_type in required_fields.items():
                                        if field not in event:
                                            event_detail["issues"].append(f"Missing required field: {field}")
                                            errors.append(f"🐛 BUG 1: aspdma_result missing {field}")
                                        elif not isinstance(event[field], field_type):
                                            event_detail["issues"].append(
                                                f"Field {field} has wrong type: {type(event[field]).__name__} (expected {field_type.__name__})"
                                            )
                                        elif field_type == str and not event[field]:
                                            event_detail["issues"].append(f"Empty string for required field: {field}")
                                            if field == "action_rationale":
                                                errors.append(
                                                    f"🐛 BUG 1: aspdma_result.action_rationale is empty string"
                                                )
                                    # Optional recursive flag
                                    if "is_recursive" in event:
                                        events_with_recursive_flag += 1
                                        if event["is_recursive"]:
                                            recursive_aspdma_count += 1

                                    # Print ASPDMA prompt if present
                                    aspdma_prompt = event.get("aspdma_prompt")
                                    if aspdma_prompt:
                                        print("\n" + "=" * 80)
                                        print("📝 ASPDMA PROMPT (Action Selection)")
                                        print("=" * 80)
                                        print(f"Selected Action: {event.get('selected_action')}")
                                        print("-" * 40)
                                        if len(aspdma_prompt) > 5000:
                                            print(
                                                aspdma_prompt[:5000]
                                                + f"\n... [truncated, {len(aspdma_prompt)} chars total]"
                                            )
                                        else:
                                            print(aspdma_prompt)
                                        print("=" * 80 + "\n")

                                elif event_type == "conscience_result":
                                    # Required fields per schema
                                    required_fields = {
                                        "conscience_passed": bool,
                                        "final_action": str,
                                        "epistemic_data": dict,
                                        "thought_id": str,
                                        "task_id": str,
                                        "timestamp": str,
                                    }
                                    for field, field_type in required_fields.items():
                                        if field not in event:
                                            event_detail["issues"].append(f"Missing required field: {field}")
                                            if field == "epistemic_data":
                                                errors.append(f"🐛 BUG 2: conscience_result missing epistemic_data")
                                        elif not isinstance(event[field], field_type):
                                            event_detail["issues"].append(
                                                f"Field {field} has wrong type: {type(event[field]).__name__} (expected {field_type.__name__})"
                                            )
                                        elif field_type == str and not event[field]:
                                            event_detail["issues"].append(f"Empty string for required field: {field}")
                                        elif field == "epistemic_data" and field_type == dict and not event[field]:
                                            errors.append(f"🐛 BUG 2: conscience_result.epistemic_data is empty dict")

                                    # Check for updated_status_detected field (from UpdatedStatusConscience check)
                                    if "updated_status_detected" not in event:
                                        event_detail["issues"].append("Missing updated_status_detected field")
                                        errors.append(
                                            f"🐛 BUG 2: conscience_result missing updated_status_detected flag"
                                        )

                                    # Optional recursive flag
                                    if "is_recursive" in event:
                                        events_with_recursive_flag += 1
                                        if event["is_recursive"]:
                                            recursive_conscience_count += 1

                                    # Print conscience prompts if present (for localization debugging)
                                    conscience_prompt_fields = [
                                        "entropy_prompt",
                                        "coherence_prompt",
                                        "optimization_veto_prompt",
                                        "epistemic_humility_prompt",
                                    ]
                                    has_prompts = any(event.get(f) for f in conscience_prompt_fields)
                                    if has_prompts:
                                        print("\n" + "=" * 80)
                                        print("📝 CONSCIENCE PROMPTS (from conscience_result event)")
                                        print("=" * 80)
                                        for prompt_key in conscience_prompt_fields:
                                            prompt_value = event.get(prompt_key)
                                            if prompt_value:
                                                print(f"\n🔹 {prompt_key.upper()}:")
                                                print("-" * 40)
                                                # Truncate very long prompts for readability
                                                if len(prompt_value) > 3000:
                                                    print(
                                                        prompt_value[:3000]
                                                        + f"\n... [truncated, {len(prompt_value)} chars total]"
                                                    )
                                                else:
                                                    print(prompt_value)
                                            else:
                                                print(f"\n🔹 {prompt_key.upper()}: (not present)")
                                        print("=" * 80 + "\n")

                                elif event_type == "action_result":
                                    # Required fields per schema
                                    required_fields = {
                                        "action_executed": str,
                                        "execution_success": bool,
                                        "thought_id": str,
                                        "task_id": str,
                                        "timestamp": str,
                                    }
                                    for field, field_type in required_fields.items():
                                        if field not in event:
                                            event_detail["issues"].append(f"Missing required field: {field}")
                                        elif not isinstance(event[field], field_type):
                                            event_detail["issues"].append(
                                                f"Field {field} has wrong type: {type(event[field]).__name__} (expected {field_type.__name__})"
                                            )
                                        elif field_type == str and not event[field]:
                                            event_detail["issues"].append(f"Empty string for required field: {field}")

                                    # Audit trail fields - REQUIRED (not optional) - all 4 must be present and non-null
                                    audit_fields = {
                                        "audit_entry_id": str,
                                        "audit_sequence_number": int,
                                        "audit_entry_hash": str,
                                        "audit_signature": str,
                                    }
                                    for field, field_type in audit_fields.items():
                                        if field not in event:
                                            event_detail["issues"].append(f"Missing REQUIRED audit field: {field}")
                                            errors.append(
                                                f"🐛 BUG 3: action_result missing REQUIRED audit field: {field}"
                                            )
                                        elif event.get(field) is None:
                                            event_detail["issues"].append(f"REQUIRED audit field is None: {field}")
                                            errors.append(
                                                f"🐛 BUG 3: action_result REQUIRED audit field is None: {field}"
                                            )
                                        elif not isinstance(event[field], field_type):
                                            event_detail["issues"].append(
                                                f"Audit field {field} has wrong type: {type(event[field]).__name__} (expected {field_type.__name__})"
                                            )
                                        elif field_type == str and not event[field]:
                                            event_detail["issues"].append(
                                                f"REQUIRED audit field is empty string: {field}"
                                            )
                                            errors.append(
                                                f"🐛 BUG 3: action_result REQUIRED audit field is empty: {field}"
                                            )

                                    # Track if all audit data is present
                                    if all(event.get(f) for f in audit_fields.keys()):
                                        events_with_audit_data += 1
                                        event_detail["has_audit_trail"] = True

                                    # Resource usage fields - REQUIRED for resource tracking (all 8 must be present)
                                    resource_fields = {
                                        "tokens_total": int,
                                        "tokens_input": int,
                                        "tokens_output": int,
                                        "cost_cents": (int, float),  # Can be float
                                        "carbon_grams": (int, float),
                                        "energy_mwh": (int, float),
                                        "llm_calls": int,
                                        "models_used": list,
                                    }
                                    for field, field_type in resource_fields.items():
                                        if field not in event:
                                            event_detail["issues"].append(f"Missing resource field: {field}")
                                            errors.append(f"🐛 RESOURCE: action_result missing resource field: {field}")
                                        elif event.get(field) is None:
                                            event_detail["issues"].append(f"Resource field is None: {field}")
                                            errors.append(f"🐛 RESOURCE: action_result resource field is None: {field}")
                                        elif isinstance(field_type, tuple):
                                            # Multiple allowed types
                                            if not isinstance(event[field], field_type):
                                                event_detail["issues"].append(
                                                    f"Resource field {field} has wrong type: {type(event[field]).__name__} "
                                                    f"(expected one of {[t.__name__ for t in field_type]})"
                                                )
                                        else:
                                            # Single type
                                            if not isinstance(event[field], field_type):
                                                event_detail["issues"].append(
                                                    f"Resource field {field} has wrong type: {type(event[field]).__name__} (expected {field_type.__name__})"
                                                )

                                # Check for unexpected extra fields (exhaustive validation)
                                expected_common_fields = {"event_type", "thought_id", "task_id", "timestamp"}
                                event_type_specific_fields = {
                                    "thought_start": {
                                        "thought_type",
                                        "thought_content",
                                        "task_description",
                                        "round_number",
                                        "thought_status",
                                        "thought_depth",
                                        "parent_thought_id",
                                        "task_priority",
                                        "channel_id",
                                        "updated_info_available",
                                    },
                                    "snapshot_and_context": {"system_snapshot"},
                                    "dma_results": {
                                        "csdma",
                                        "dsdma",
                                        "pdma",
                                        # IDMA is streamed separately as idma_result event (v1.9.3)
                                        "csdma_prompt",
                                        "dsdma_prompt",
                                        "pdma_prompt",
                                        # System prompts for debugging (v2.0.0+)
                                        "csdma_system_prompt",
                                        "dsdma_system_prompt",
                                        "pdma_system_prompt",
                                    },  # DMA results + optional prompt fields
                                    "idma_result": {
                                        # IDMA epistemic evaluation fields (v1.9.3)
                                        "k_eff",
                                        "correlation_risk",
                                        "fragility_flag",
                                        "phase",
                                        "reasoning",
                                        "sources_identified",
                                        "correlation_factors",
                                        "idma_prompt",  # Optional prompt
                                    },
                                    "tsaspdma_result": {
                                        # TSASPDMA tool-specific evaluation (v1.9.3)
                                        # Input from ASPDMA
                                        "original_tool_name",
                                        "original_parameters",
                                        "aspdma_rationale",
                                        # Output (refined decision)
                                        "final_action",
                                        "final_tool_name",
                                        "final_parameters",
                                        "tsaspdma_rationale",
                                        # Optional tool documentation context
                                        "tool_description",
                                        "gotchas_acknowledged",
                                    },
                                    "aspdma_result": {
                                        "selected_action",
                                        "action_rationale",
                                        "is_recursive",
                                        "aspdma_prompt",
                                    },
                                    "conscience_result": {
                                        "conscience_passed",
                                        "final_action",
                                        "epistemic_data",
                                        "is_recursive",
                                        "conscience_override_reason",
                                        "action_was_overridden",
                                        "conscience_prompt",  # Legacy single field (deprecated)
                                        # === CONSCIENCE PROMPTS (for localization validation) ===
                                        "entropy_prompt",
                                        "coherence_prompt",
                                        "optimization_veto_prompt",
                                        "epistemic_humility_prompt",
                                        # Exempt actions flag
                                        "ethical_faculties_skipped",
                                        # === BYPASS GUARDRAIL 1: Updated Status ===
                                        "updated_status_detected",
                                        "updated_status_content",
                                        # === BYPASS GUARDRAIL 2: Thought Depth ===
                                        "thought_depth_triggered",
                                        "thought_depth_current",
                                        "thought_depth_max",
                                        # === ETHICAL FACULTY 1: Entropy ===
                                        "entropy_passed",
                                        "entropy_score",
                                        "entropy_threshold",
                                        "entropy_reason",
                                        # === ETHICAL FACULTY 2: Coherence ===
                                        "coherence_passed",
                                        "coherence_score",
                                        "coherence_threshold",
                                        "coherence_reason",
                                        # === ETHICAL FACULTY 3: Optimization Veto ===
                                        "optimization_veto_passed",
                                        "optimization_veto_decision",
                                        "optimization_veto_justification",
                                        "optimization_veto_entropy_ratio",
                                        "optimization_veto_affected_values",
                                        # === ETHICAL FACULTY 4: Epistemic Humility ===
                                        "epistemic_humility_passed",
                                        "epistemic_humility_certainty",
                                        "epistemic_humility_uncertainties",
                                        "epistemic_humility_justification",
                                        "epistemic_humility_recommendation",
                                    },
                                    "action_result": {
                                        "action_executed",
                                        "action_parameters",  # Action params (content for SPEAK, etc.)
                                        "execution_success",
                                        "execution_time_ms",
                                        "follow_up_thought_id",
                                        "error",
                                        "audit_entry_id",
                                        "audit_sequence_number",
                                        "audit_entry_hash",
                                        "audit_signature",
                                        # Resource usage fields (v1.3.1+)
                                        "tokens_total",
                                        "tokens_input",
                                        "tokens_output",
                                        "cost_cents",
                                        "carbon_grams",
                                        "energy_mwh",
                                        "llm_calls",
                                        "models_used",
                                        "api_bases_used",  # API endpoint tracking (v1.8.14+)
                                        # Coherence/entropy data from conscience checks (v2.3.0+)
                                        # None for exempt actions like RECALL, TASK_COMPLETE
                                        "coherence_passed",
                                        "coherence_score",
                                        "coherence_threshold",
                                        "coherence_reason",
                                        "entropy_passed",
                                        "entropy_score",
                                        "entropy_threshold",
                                        "entropy_reason",
                                    },
                                }

                                expected_fields = expected_common_fields | event_type_specific_fields.get(
                                    event_type, set()
                                )
                                actual_fields = set(event.keys())
                                extra_fields = actual_fields - expected_fields

                                if extra_fields:
                                    event_detail["issues"].append(
                                        f"Unexpected extra fields: {', '.join(sorted(extra_fields))}"
                                    )
                                    errors.append(
                                        f"{event_type} has unexpected fields: {', '.join(sorted(extra_fields))}"
                                    )

                                event_details.append(event_detail)

                        except json.JSONDecodeError as e:
                            errors.append(f"JSON decode error: {e}")
                        except Exception as e:
                            errors.append(f"Error processing event: {e}")

            except Exception as e:
                errors.append(f"Stream monitoring error: {e}")
                stream_error.set()

        # Start monitoring thread
        monitor_thread = threading.Thread(target=monitor_stream, daemon=True)
        monitor_thread.start()

        # Wait for connection
        if not stream_connected.wait(timeout=3):
            return {
                "success": False,
                "error": "Failed to connect to SSE stream",
                "errors": errors,
            }

        # Wait a bit for events to stream
        time.sleep(1)

        # Ensure system is in running state before triggering test message
        # (Runtime control tests may have left system paused/stepped)
        try:
            state_response = requests.get(
                f"{base_url}/v1/system/runtime/queue",
                headers={"Authorization": f"Bearer {token}"},
                timeout=5,
            )
            if state_response.status_code == 200:
                queue_data = state_response.json().get("data", {})
                is_paused = queue_data.get("is_paused", False)
                if is_paused:
                    # Resume the system
                    resume_response = requests.post(
                        f"{base_url}/v1/system/runtime/resume",
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=5,
                    )
                    if resume_response.status_code != 200:
                        errors.append(f"Failed to resume system: {resume_response.status_code}")
                    time.sleep(0.5)  # Give it a moment to resume
        except Exception as e:
            errors.append(f"Failed to check/resume system state: {e}")

        # Wait for task queue to drain before submitting test message
        # (Previous tests may have left tasks in the queue that need to complete first)
        try:
            drain_timeout = 30  # Wait up to 30 seconds for queue to drain
            drain_elapsed = 0
            drain_check_interval = 0.5
            initial_queue_size = None
            while drain_elapsed < drain_timeout:
                queue_response = requests.get(
                    f"{base_url}/v1/system/runtime/queue",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=5,
                )
                if queue_response.status_code == 200:
                    queue_data = queue_response.json().get("data", {})
                    queue_size = queue_data.get("queue_size", 0)
                    if initial_queue_size is None:
                        initial_queue_size = queue_size
                        logger.info(f"🔍 Initial queue size before streaming test: {queue_size}")
                        print(f"\n🔍 Queue state before streaming test: {queue_size} tasks pending")
                    if queue_size == 0:
                        logger.info(f"✅ Queue drained after {drain_elapsed:.1f}s")
                        print(f"✅ Queue drained after {drain_elapsed:.1f}s")
                        break  # Queue is empty, ready to submit test message
                    elif drain_elapsed > 0 and drain_elapsed % 5 == 0:
                        logger.info(
                            f"⏳ Waiting for queue to drain: {queue_size} tasks remaining ({drain_elapsed:.0f}s elapsed)"
                        )
                        print(f"⏳ Queue: {queue_size} tasks remaining ({drain_elapsed:.0f}s elapsed)", end="\r")
                time.sleep(drain_check_interval)
                drain_elapsed += drain_check_interval
            # If queue didn't drain, log it but continue (don't fail the test)
            if drain_elapsed >= drain_timeout:
                final_queue_size = queue_size if "queue_size" in locals() else "unknown"
                error_msg = f"Queue did not drain within {drain_timeout}s (started: {initial_queue_size}, current: {final_queue_size})"
                logger.warning(error_msg)
                print(f"\n⚠️  {error_msg}")
                errors.append(error_msg)
        except Exception as e:
            logger.error(f"Failed to check queue drain status: {e}")
            errors.append(f"Failed to check queue drain status: {e}")

        # Trigger a task to generate events using new async message endpoint
        try:
            logger.debug("Submitting test message to /v1/agent/message")
            response = requests.post(
                f"{base_url}/v1/agent/message",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"message": "Test reasoning event streaming"},
                timeout=10,
            )
            # Validate the response schema
            if response.status_code == 200:
                data = response.json().get("data", {})
                task_id = data.get("task_id")
                channel_id = data.get("channel_id")
                logger.debug(
                    f"Test message submitted - task_id={task_id}, channel_id={channel_id}, accepted={data.get('accepted')}"
                )
                # Validate MessageSubmissionResponse schema
                required_fields = ["message_id", "task_id", "channel_id", "submitted_at", "accepted"]
                for field in required_fields:
                    if field not in data:
                        errors.append(f"Message submission response missing field: {field}")
                # Ensure accepted is True for successful submission
                if not data.get("accepted"):
                    errors.append(f"Message was not accepted: {data.get('rejection_reason')}")
        except Exception as e:
            errors.append(f"Failed to trigger task via /agent/message: {e}")

        # Wait for events to stream (60s timeout allows wakeup to complete and actions to dispatch)
        elapsed = 0
        check_interval = 0.5
        while elapsed < timeout and len(received_events) < len(StreamingVerificationModule.EXPECTED_EVENTS):
            time.sleep(check_interval)
            elapsed += check_interval

        duration = time.time() - start_time

        # Check which events we received
        missing_events = StreamingVerificationModule.EXPECTED_EVENTS - received_events

        # Build result
        result = {
            "success": (
                len(missing_events) == 0
                and len(unexpected_events) == 0
                and len(duplicates_found) == 0
                and len(errors) == 0
            ),  # Require all 6 events, no extras, no duplicates, no errors
            "received_events": sorted(list(received_events)),
            "missing_events": sorted(list(missing_events)),
            "unexpected_events": sorted(list(unexpected_events)),
            "duplicates": duplicates_found,
            "duration": duration,
            "total_events": len(event_details),
            "events_with_audit_data": events_with_audit_data,
            "events_with_recursive_flag": events_with_recursive_flag,
            "recursive_aspdma_count": recursive_aspdma_count,
            "recursive_conscience_count": recursive_conscience_count,
            "event_details": event_details,
            "errors": errors,
        }

        # Build status message
        if result["success"]:
            message = f"✅ All 7 reasoning events received with valid schemas (no duplicates, no unexpected events)"
            if events_with_audit_data > 0:
                message += f"\n✅ Audit trail data present in {events_with_audit_data} ACTION_RESULT events"
            if recursive_aspdma_count > 0 or recursive_conscience_count > 0:
                message += (
                    f"\n✅ Recursive events: {recursive_aspdma_count} ASPDMA, {recursive_conscience_count} CONSCIENCE"
                )
            result["message"] = message
        else:
            error_parts = []
            if missing_events:
                error_parts.append(f"Missing events: {', '.join(missing_events)}")
            if unexpected_events:
                error_parts.append(f"Unexpected events: {', '.join(unexpected_events)}")
            if duplicates_found:
                error_parts.append(f"Duplicates: {len(duplicates_found)} found")
                # Add detailed duplicate information (duplicates_found contains strings)
                for dup in duplicates_found:
                    error_parts.append(f"  → {dup}")
            if errors:
                error_parts.append(f"Schema errors: {len(errors)} found")
                # Add first 3 errors for debugging
                for i, error in enumerate(errors[:3]):
                    error_parts.append(f"  → Error {i+1}: {error}")
                if len(errors) > 3:
                    error_parts.append(f"  → ... and {len(errors) - 3} more errors")
            result["message"] = "❌ " + "; ".join(error_parts)

        return result

    @staticmethod
    def update_user_language(base_url: str, token: str, language_code: str) -> Dict[str, Any]:
        """
        Update the user's preferred language via the settings API.

        Args:
            base_url: API base URL
            token: Auth token
            language_code: ISO 639-1 language code (e.g., 'en', 'am', 'es')

        Returns:
            Dict with success status and details
        """
        try:
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            response = requests.put(
                f"{base_url}/v1/users/me/settings",
                headers=headers,
                json={"preferred_language": language_code},
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "message": f"Language updated to '{language_code}'",
                    "data": data,
                }
            else:
                return {
                    "success": False,
                    "message": f"Failed to update language: {response.status_code}",
                    "error": response.text,
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error updating language: {e}",
            }

    # Language-specific markers to detect proper localization in DMA prompts
    # These are phrases that MUST appear in DMA prompts for each language
    # and MUST NOT appear when the language is different
    # DMA prompts are used instead of conscience prompts because they are streamed in events
    DMA_LANGUAGE_MARKERS = {
        "en": ["Context Summary:", "Main Thought:", "Thought to evaluate:"],
        "am": ["የአውድ ማጠቃለያ:", "ዋና ሀሳብ:", "የሚገመገም ሀሳብ:"],  # Amharic DMA markers
        "ar": ["ملخص السياق:", "الفكرة الرئيسية:", "الفكرة للتقييم:"],  # Arabic
        "de": ["Kontextzusammenfassung:", "Hauptgedanke:", "Zu bewertender Gedanke:"],  # German
        "es": ["Resumen del contexto:", "Pensamiento principal:", "Pensamiento a evaluar:"],  # Spanish
        "fr": ["Résumé du contexte:", "Pensée principale:", "Pensée à évaluer:"],  # French
        "hi": ["संदर्भ सारांश:", "मुख्य विचार:", "मूल्यांकन के लिए विचार:"],  # Hindi
        "it": ["Riepilogo del contesto:", "Pensiero principale:", "Pensiero da valutare:"],  # Italian
        "ja": ["コンテキストの概要:", "主な考え:", "評価する考え:"],  # Japanese
        "ko": ["컨텍스트 요약:", "주요 생각:", "평가할 생각:"],  # Korean
        "pt": ["Resumo do contexto:", "Pensamento principal:", "Pensamento a avaliar:"],  # Portuguese
        "ru": ["Резюме контекста:", "Основная мысль:", "Мысль для оценки:"],  # Russian
        "sw": ["Muhtasari wa Muktadha:", "Wazo Kuu:", "Wazo la kutathmini:"],  # Swahili
        "tr": ["Bağlam özeti:", "Ana düşünce:", "Değerlendirilecek düşünce:"],  # Turkish
        "zh": ["上下文摘要:", "主要思想:", "待评估思想:"],  # Chinese
    }

    # Language-specific markers to detect proper localization in CONSCIENCE prompts
    # These phrases appear in entropy/coherence/optimization_veto/epistemic_humility prompts
    # The conscience prompts are now streamed as separate fields in conscience_result events
    CONSCIENCE_LANGUAGE_MARKERS = {
        "en": [
            "Entropy Check:",  # Entropy prompt marker
            "Coherence Check:",  # Coherence prompt marker
            "Optimization Veto:",  # OptimizationVeto prompt marker
            "Epistemic Humility:",  # EpistemicHumility prompt marker
        ],
        "am": [
            "የኢንትሮፒ ምርመራ:",  # Amharic entropy
            "የማቻቻል ምርመራ:",  # Amharic coherence
            "የኦፕቲማይዜሽን ቬቶ:",  # Amharic optimization veto
            "ኤፒስተሚክ ትሕትና:",  # Amharic epistemic humility
        ],
        "es": [
            "Verificación de Entropía:",
            "Verificación de Coherencia:",
            "Veto de Optimización:",
            "Humildad Epistémica:",
        ],
        "fr": [
            "Vérification d'Entropie:",
            "Vérification de Cohérence:",
            "Veto d'Optimisation:",
            "Humilité Épistémique:",
        ],
        "de": [
            "Entropie-Prüfung:",
            "Kohärenz-Prüfung:",
            "Optimierungs-Veto:",
            "Epistemische Demut:",
        ],
        "zh": [
            "熵检查:",
            "一致性检查:",
            "优化否决:",
            "认识谦逊:",
        ],
        "ja": [
            "エントロピーチェック:",
            "整合性チェック:",
            "最適化拒否:",
            "認識的謙虚さ:",
        ],
    }

    @staticmethod
    def verify_localization_change(base_url: str, token: str, target_language: str = "am") -> Dict[str, Any]:
        """
        Test that changing user language preference affects backend localization.

        1. Updates user's preferred_language to target_language
        2. Runs full streaming verification to generate all reasoning events
        3. Checks for localized strings in conscience/DMA prompts
        4. Validates conscience prompts contain target language markers (not English)

        Args:
            base_url: API base URL
            token: Auth token
            target_language: Language code to test (default: 'am' for Amharic)

        Returns:
            Dict with verification results
        """
        # Use separate typed variables to avoid mypy issues with heterogeneous dicts
        localization_evidence: List[Dict[str, Any]] = []
        errors: List[str] = []
        language_update: Optional[Dict[str, Any]] = None
        streaming_result: Optional[Dict[str, Any]] = None

        # Step 1: Update user language
        print(f"\n{'='*80}")
        print(f"🌍 LOCALIZATION CHANGE TEST - Setting language to '{target_language}'")
        print(f"{'='*80}")

        update_result = StreamingVerificationModule.update_user_language(base_url, token, target_language)
        language_update = update_result

        if not update_result["success"]:
            errors.append(f"Failed to update language: {update_result.get('message')}")
            print(f"❌ {update_result.get('message')}")
            return {
                "success": False,
                "language_update": language_update,
                "streaming_result": streaming_result,
                "localization_evidence": localization_evidence,
                "dma_prompt_analysis": [],
                "errors": errors,
            }

        print(f"✅ Language preference updated to '{target_language}'")

        # Step 2: Verify the user profile has the new language
        try:
            headers = {"Authorization": f"Bearer {token}"}
            profile_response = requests.get(f"{base_url}/v1/users/me", headers=headers, timeout=10)
            if profile_response.status_code == 200:
                profile_data = profile_response.json().get("data", {})
                stored_lang = profile_data.get("preferred_language")
                print(f"📋 User profile preferred_language: {stored_lang}")
                if stored_lang != target_language:
                    errors.append(f"Language not persisted: expected '{target_language}', got '{stored_lang}'")
                else:
                    localization_evidence.append(
                        {
                            "source": "user_profile_api",
                            "field": "preferred_language",
                            "value": stored_lang,
                        }
                    )
        except Exception as e:
            errors.append(f"Failed to verify user profile: {e}")

        # Step 3: Run streaming verification with extended event collection
        # We need to capture the raw events to analyze DMA prompts
        print(f"\n📡 Running streaming verification with language '{target_language}'...")
        print(f"   Capturing DMA prompts for localization analysis...")

        streaming_events_result = StreamingVerificationModule.verify_streaming_events_with_prompts(
            base_url, token, timeout=60
        )
        streaming_result = {
            "success": streaming_events_result.get("success"),
            "received_events": streaming_events_result.get("received_events", []),
            "total_events": streaming_events_result.get("total_events", 0),
        }

        # Step 4: Analyze DMA prompts for localization
        print(f"\n{'='*80}")
        print(f"📝 DMA PROMPT LOCALIZATION ANALYSIS")
        print(f"{'='*80}")

        dma_prompts_list: List[Dict[str, Any]] = streaming_events_result.get("dma_prompts", [])
        english_markers = StreamingVerificationModule.DMA_LANGUAGE_MARKERS.get("en", [])
        target_markers = StreamingVerificationModule.DMA_LANGUAGE_MARKERS.get(target_language, [])

        dma_localized = False
        english_detected = False
        dma_prompt_analysis: List[Dict[str, Any]] = []

        for i, prompt_data in enumerate(dma_prompts_list):
            prompt_text = prompt_data.get("prompt", "")
            dma_type = prompt_data.get("type", "unknown")

            analysis = {
                "dma_type": dma_type,
                "prompt_length": len(prompt_text),
                "english_markers_found": [],
                "target_markers_found": [],
                "is_localized": False,
            }

            # Check for English markers (should NOT be present if localized)
            for marker in english_markers:
                if marker in prompt_text:
                    analysis["english_markers_found"].append(marker)
                    english_detected = True

            # Check for target language markers (SHOULD be present if localized)
            for marker in target_markers:
                if marker in prompt_text:
                    analysis["target_markers_found"].append(marker)
                    dma_localized = True

            # Determine if this prompt is properly localized
            if target_language != "en":
                # For non-English, we expect target markers and NO English markers
                analysis["is_localized"] = (
                    len(analysis["target_markers_found"]) > 0 and len(analysis["english_markers_found"]) == 0
                )
            else:
                # For English, we expect English markers
                analysis["is_localized"] = len(analysis["english_markers_found"]) > 0

            dma_prompt_analysis.append(analysis)

            # Print analysis
            status = "✅" if analysis["is_localized"] else "❌"
            print(f"\n  {status} DMA: {dma_type}")
            print(f"     Prompt length: {analysis['prompt_length']} chars")
            if analysis["english_markers_found"]:
                print(f"     ⚠️  English markers found: {analysis['english_markers_found']}")
            if analysis["target_markers_found"]:
                print(f"     ✅ {target_language.upper()} markers found: {analysis['target_markers_found']}")
            if not analysis["is_localized"]:
                if target_language != "en":
                    print(f"     ❌ Prompt is NOT localized to {target_language}!")
                    # Show snippet of prompt for debugging
                    snippet = prompt_text[:200] + "..." if len(prompt_text) > 200 else prompt_text
                    print(f"     Snippet: {snippet}")

        # Step 4b: Analyze CONSCIENCE prompts for localization (v2.5+ streaming)
        print(f"\n{'='*80}")
        print(f"📝 CONSCIENCE PROMPT LOCALIZATION ANALYSIS (v2.5+)")
        print(f"{'='*80}")

        conscience_prompts_list: List[Dict[str, Any]] = streaming_events_result.get("conscience_prompts", [])
        english_conscience_markers = StreamingVerificationModule.CONSCIENCE_LANGUAGE_MARKERS.get("en", [])
        target_conscience_markers = StreamingVerificationModule.CONSCIENCE_LANGUAGE_MARKERS.get(target_language, [])

        conscience_localized = False
        english_conscience_detected = False
        conscience_prompt_analysis: List[Dict[str, Any]] = []

        if not conscience_prompts_list:
            print(f"  ⚠️  No conscience prompts captured (may be using legacy single field)")
        else:
            for prompt_data in conscience_prompts_list:
                prompt_text = prompt_data.get("prompt", "")
                conscience_type = prompt_data.get("type", "unknown")
                field_name = prompt_data.get("field", "unknown")

                analysis = {
                    "conscience_type": conscience_type,
                    "field": field_name,
                    "prompt_length": len(prompt_text),
                    "english_markers_found": [],
                    "target_markers_found": [],
                    "is_localized": False,
                }

                # Check for English markers
                for marker in english_conscience_markers:
                    if marker.lower() in prompt_text.lower():
                        analysis["english_markers_found"].append(marker)
                        english_conscience_detected = True

                # Check for target language markers
                for marker in target_conscience_markers:
                    if marker in prompt_text:
                        analysis["target_markers_found"].append(marker)
                        conscience_localized = True

                # Determine if properly localized
                if target_language != "en":
                    analysis["is_localized"] = (
                        len(analysis["target_markers_found"]) > 0 and len(analysis["english_markers_found"]) == 0
                    )
                else:
                    analysis["is_localized"] = len(analysis["english_markers_found"]) > 0

                conscience_prompt_analysis.append(analysis)

                # Print analysis
                status = "✅" if analysis["is_localized"] else "❌"
                print(f"\n  {status} CONSCIENCE: {conscience_type} ({field_name})")
                print(f"     Prompt length: {analysis['prompt_length']} chars")
                if analysis["english_markers_found"]:
                    print(f"     ⚠️  English markers found: {analysis['english_markers_found']}")
                if analysis["target_markers_found"]:
                    print(f"     ✅ {target_language.upper()} markers found: {analysis['target_markers_found']}")
                if not analysis["is_localized"] and target_language != "en":
                    print(f"     ❌ Prompt is NOT localized to {target_language}!")
                    snippet = prompt_text[:200] + "..." if len(prompt_text) > 200 else prompt_text
                    print(f"     Snippet: {snippet}")

        # Step 5: Check the received events include all expected types
        received_events_list: List[Any] = streaming_result.get("received_events", []) if streaming_result else []
        received = set(received_events_list)
        expected = {
            "thought_start",
            "snapshot_and_context",
            "dma_results",
            "idma_result",
            "aspdma_result",
            "conscience_result",
            "action_result",
        }

        if expected.issubset(received):
            print(f"\n  ✅ All 7 reasoning event types received")
            localization_evidence.append(
                {
                    "source": "streaming_events",
                    "field": "event_types",
                    "value": list(received),
                }
            )
        else:
            missing = expected - received
            print(f"\n  ⚠️  Missing events: {missing}")

        # Step 6: Determine overall localization success
        if target_language != "en":
            # For non-English: success if DMA prompts are localized
            # and NO English markers were found
            dma_localization_passed = dma_localized and not english_detected
            if dma_localization_passed:
                localization_evidence.append(
                    {
                        "source": "dma_prompts",
                        "field": "localization",
                        "value": f"DMA prompts localized to {target_language}",
                    }
                )
            else:
                if english_detected:
                    errors.append(
                        f"English markers found in DMA prompts when language should be {target_language}"
                    )
                if not dma_localized:
                    errors.append(
                        f"No {target_language} markers found in DMA prompts - localization may have failed"
                    )

            # Also check conscience prompts if available
            conscience_localization_passed = True  # Default to pass if no prompts captured
            if conscience_prompts_list:
                conscience_localization_passed = conscience_localized and not english_conscience_detected
                if conscience_localization_passed:
                    localization_evidence.append(
                        {
                            "source": "conscience_prompts",
                            "field": "localization",
                            "value": f"Conscience prompts localized to {target_language}",
                        }
                    )
                else:
                    if english_conscience_detected:
                        errors.append(
                            f"English markers found in conscience prompts when language should be {target_language}"
                        )
                    if not conscience_localized:
                        errors.append(
                            f"No {target_language} markers found in conscience prompts - localization may have failed"
                        )

            # Overall pass requires both DMA and conscience (if available) to be localized
            localization_passed = dma_localization_passed and conscience_localization_passed
        else:
            # For English: success if English markers are found
            localization_passed = english_detected or (conscience_prompts_list and english_conscience_detected)

        # Step 7: Summary
        print(f"\n{'='*80}")
        print(f"📝 LOCALIZATION TEST RESULTS")
        print(f"{'='*80}")
        print(f"  Target language: {target_language}")
        print(f"  Language stored in profile: ✅")
        streaming_success = streaming_result.get("success", False) if streaming_result else False
        streaming_total = streaming_result.get("total_events", 0) if streaming_result else 0
        print(f"  Streaming test passed: {'✅' if streaming_success else '❌'}")
        print(f"  Events received: {streaming_total}")
        print(f"  DMA prompts captured: {len(dma_prompts_list)}")
        print(f"  Conscience prompts captured: {len(conscience_prompts_list)}")
        print(f"  Overall localization: {'✅ PASSED' if localization_passed else '❌ FAILED'}")
        print(f"  Localization evidence: {len(localization_evidence)} items")

        for evidence in localization_evidence:
            print(f"    - {evidence['source']}.{evidence['field']}: {evidence['value']}")

        if errors:
            print(f"\n❌ Errors:")
            for error in errors:
                print(f"   - {error}")

        # Success requires: language stored, streaming passed, AND prompts localized
        success = len(localization_evidence) > 0 and streaming_success and localization_passed and len(errors) == 0

        if success:
            print(f"\n✅ LOCALIZATION TEST PASSED")
            print(f"   Language preference '{target_language}' is stored and propagated through reasoning pipeline")
            print(f"   DMA prompts are properly localized to {target_language}")
            if conscience_prompts_list:
                print(f"   Conscience prompts are properly localized to {target_language}")
        else:
            print(f"\n❌ LOCALIZATION TEST FAILED")
            if not localization_passed:
                print(f"   Prompts are NOT properly localized to {target_language}")

        print(f"{'='*80}\n")

        return {
            "success": success,
            "language_update": language_update,
            "streaming_result": streaming_result,
            "localization_evidence": localization_evidence,
            "dma_prompt_analysis": dma_prompt_analysis,
            "conscience_prompt_analysis": conscience_prompt_analysis,
            "errors": errors,
        }

    @staticmethod
    def verify_streaming_events_with_prompts(base_url: str, token: str, timeout: int = 60) -> Dict[str, Any]:
        """
        Extended version of verify_streaming_events that captures conscience prompts.

        Returns all standard verification results plus a list of conscience prompts
        for localization analysis.
        """
        received_events: Set[str] = set()
        event_details: List[Dict[str, Any]] = []
        errors: List[str] = []
        conscience_prompts: List[Dict[str, Any]] = []
        dma_prompts: List[Dict[str, Any]] = []
        start_time = time.time()

        # Track event-specific data
        events_with_audit_data = 0
        unexpected_events: Set[str] = set()

        # Shared state for thread communication
        stream_connected = threading.Event()
        stream_error = threading.Event()

        def monitor_stream() -> None:
            """Monitor SSE stream in a separate thread, capturing DMA prompts."""
            nonlocal events_with_audit_data, unexpected_events

            try:
                headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream"}

                logger.debug("SSE client connecting to reasoning-stream endpoint")
                response = requests.get(
                    f"{base_url}/v1/system/runtime/reasoning-stream", headers=headers, stream=True, timeout=5
                )

                if response.status_code != 200:
                    errors.append(f"Stream connection failed: {response.status_code}")
                    stream_error.set()
                    return

                stream_connected.set()

                # Parse SSE stream
                for line in response.iter_lines():
                    if not line:
                        continue

                    line = line.decode("utf-8") if isinstance(line, bytes) else line

                    if line.startswith("data:"):
                        try:
                            data = json.loads(line[6:])
                            events = data.get("events", [])

                            for event in events:
                                event_type = event.get("event_type")
                                if not event_type:
                                    continue

                                received_events.add(event_type)

                                # Check for unexpected events
                                all_valid_events = (
                                    StreamingVerificationModule.EXPECTED_EVENTS
                                    | StreamingVerificationModule.OPTIONAL_EVENTS
                                )
                                if event_type not in all_valid_events:
                                    unexpected_events.add(event_type)

                                # Capture DMA prompts for localization analysis (from dma_results event)
                                if event_type == "dma_results":
                                    for prompt_key in ["csdma_prompt", "dsdma_prompt", "pdma_prompt"]:
                                        prompt_value = event.get(prompt_key, "")
                                        if prompt_value:
                                            dma_prompts.append(
                                                {
                                                    "type": prompt_key.replace("_prompt", "").upper(),
                                                    "prompt": prompt_value,
                                                    "thought_id": event.get("thought_id"),
                                                }
                                            )

                                # Capture all 4 individual conscience prompts (v2.5+ streaming)
                                if event_type == "conscience_result":
                                    # v2.5+: 4 separate prompt fields for each conscience check
                                    prompt_fields = [
                                        ("entropy_prompt", "entropy"),
                                        ("coherence_prompt", "coherence"),
                                        ("optimization_veto_prompt", "optimization_veto"),
                                        ("epistemic_humility_prompt", "epistemic_humility"),
                                    ]
                                    for field_name, conscience_type in prompt_fields:
                                        prompt_value = event.get(field_name, "")
                                        if prompt_value:
                                            conscience_prompts.append(
                                                {
                                                    "type": conscience_type,
                                                    "field": field_name,
                                                    "prompt": prompt_value,
                                                    "thought_id": event.get("thought_id"),
                                                }
                                            )

                                    # Legacy: also check single conscience_prompt field (deprecated)
                                    legacy_prompt = event.get("conscience_prompt", "")
                                    if legacy_prompt and not any(event.get(f[0]) for f in prompt_fields):
                                        # Only add legacy if no individual prompts found
                                        conscience_prompts.append(
                                            {
                                                "type": "legacy",
                                                "field": "conscience_prompt",
                                                "prompt": legacy_prompt,
                                                "thought_id": event.get("thought_id"),
                                            }
                                        )

                                # Track audit data
                                if event_type == "action_result":
                                    audit_fields = [
                                        "audit_entry_id",
                                        "audit_sequence_number",
                                        "audit_entry_hash",
                                        "audit_signature",
                                    ]
                                    if all(event.get(f) for f in audit_fields):
                                        events_with_audit_data += 1

                                event_details.append(
                                    {
                                        "event_type": event_type,
                                        "thought_id": event.get("thought_id"),
                                        "task_id": event.get("task_id"),
                                    }
                                )

                        except json.JSONDecodeError as e:
                            errors.append(f"JSON decode error: {e}")
                        except Exception as e:
                            errors.append(f"Error processing event: {e}")

            except Exception as e:
                errors.append(f"Stream monitoring error: {e}")
                stream_error.set()

        # Start monitoring thread
        monitor_thread = threading.Thread(target=monitor_stream, daemon=True)
        monitor_thread.start()

        # Wait for connection
        if not stream_connected.wait(timeout=3):
            return {
                "success": False,
                "error": "Failed to connect to SSE stream",
                "errors": errors,
                "conscience_prompts": [],
                "dma_prompts": [],
            }

        time.sleep(1)

        # Trigger a task to generate events
        try:
            response = requests.post(
                f"{base_url}/v1/agent/message",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"message": "Test localization verification"},
                timeout=10,
            )
        except Exception as e:
            errors.append(f"Failed to trigger task: {e}")

        # Wait for events
        elapsed = 0
        check_interval = 0.5
        while elapsed < timeout and len(received_events) < len(StreamingVerificationModule.EXPECTED_EVENTS):
            time.sleep(check_interval)
            elapsed += check_interval

        duration = time.time() - start_time
        missing_events = StreamingVerificationModule.EXPECTED_EVENTS - received_events

        return {
            "success": len(missing_events) == 0 and len(errors) == 0,
            "received_events": sorted(list(received_events)),
            "missing_events": sorted(list(missing_events)),
            "unexpected_events": sorted(list(unexpected_events)),
            "duration": duration,
            "total_events": len(event_details),
            "events_with_audit_data": events_with_audit_data,
            "event_details": event_details,
            "conscience_prompts": conscience_prompts,
            "dma_prompts": dma_prompts,
            "errors": errors,
        }

    @staticmethod
    def run_custom_test(test: QATestCase, config: QAConfig, token: str) -> Dict[str, Any]:
        """Run streaming verification custom test."""
        if test.custom_handler == "verify_reasoning_stream":
            return StreamingVerificationModule.verify_streaming_events(config.base_url, token, timeout=60)
        elif test.custom_handler == "verify_localization_change":
            return StreamingVerificationModule.verify_localization_change(config.base_url, token, target_language="am")
        else:
            return {
                "success": False,
                "message": f"Unknown custom handler: {test.custom_handler}",
            }

    @staticmethod
    def get_streaming_verification_tests() -> List[QATestCase]:
        """Get streaming verification test cases."""
        return [
            # SSE connectivity test
            QATestCase(
                module=QAModule.STREAMING,
                name="SSE Stream Connectivity",
                method="GET",
                endpoint="/v1/system/runtime/reasoning-stream",
                requires_auth=True,
                expected_status=200,
                timeout=3,
            ),
            # H3ERE Reasoning Event Streaming Verification
            QATestCase(
                module=QAModule.STREAMING,
                name="H3ERE Reasoning Event Stream Verification",
                method="CUSTOM",
                endpoint="",
                requires_auth=True,
                expected_status=200,
                timeout=70,  # 60s for event wait + 10s buffer
                custom_handler="verify_reasoning_stream",
            ),
            # Localization Change Verification
            QATestCase(
                module=QAModule.STREAMING,
                name="Backend Localization Change Verification",
                method="CUSTOM",
                endpoint="",
                requires_auth=True,
                expected_status=200,
                timeout=40,
                custom_handler="verify_localization_change",
            ),
        ]
