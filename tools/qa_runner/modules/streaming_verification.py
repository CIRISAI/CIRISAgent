"""
Reasoning Event Streaming Verification Module.

Validates that the 6 simplified reasoning events are properly streaming
via Server-Sent Events (SSE) to the reasoning-stream endpoint, and that
ONLY those 6 events are emitted (no extras from the 11 step points).
"""

import json
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

import requests

from ..config import QAConfig, QAModule, QATestCase


class StreamingVerificationModule:
    """Verify all 6 reasoning events are streaming correctly."""

    # All 6 reasoning events expected (with 60s timeout for wakeup to complete)
    EXPECTED_EVENTS = {
        "thought_start",
        "snapshot_and_context",
        "dma_results",
        "aspdma_result",
        "conscience_result",
        "action_result",
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

        def monitor_stream():
            """Monitor SSE stream in a separate thread."""
            nonlocal events_with_audit_data, events_with_recursive_flag
            nonlocal recursive_aspdma_count, recursive_conscience_count, unexpected_events
            nonlocal event_occurrences, duplicates_found, first_snapshot_printed

            try:
                headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream"}

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

                    # Only process data lines
                    if line.startswith("data:"):
                        try:
                            data = json.loads(line[6:])

                            # Extract events from stream update
                            events = data.get("events", [])

                            for event in events:
                                event_type = event.get("event_type")

                                if not event_type:
                                    errors.append("Event missing event_type field")
                                    continue

                                # Track this event type
                                received_events.add(event_type)

                                # Check if this is an unexpected event (not one of the 6)
                                if event_type not in StreamingVerificationModule.EXPECTED_EVENTS:
                                    unexpected_events.add(event_type)

                                # Track duplicates: (thought_id, event_type)
                                thought_id = event.get("thought_id")
                                if thought_id:
                                    key = (thought_id, event_type)
                                    event_occurrences[key] = event_occurrences.get(key, 0) + 1
                                    if event_occurrences[key] > 1:
                                        dup_msg = f"Duplicate {event_type} for thought {thought_id} (occurrence #{event_occurrences[key]})"
                                        if dup_msg not in duplicates_found:
                                            duplicates_found.append(dup_msg)
                                            errors.append(dup_msg)

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
                                            issue_msg = "system_snapshot.user_profiles is empty list (should contain at least API user profile)"
                                            event_detail["issues"].append(issue_msg)
                                            errors.append(f"🐛 EMPTY LIST: {issue_msg}")
                                            # Print the FULL event to debug why user_profiles is empty
                                            print("\n" + "=" * 80)
                                            print("🐛 DEBUG: FULL EVENT WITH EMPTY user_profiles")
                                            print("=" * 80)
                                            print(json.dumps(event, indent=2, default=str))
                                            print("=" * 80 + "\n")
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
                                                print("  ❌ EMPTY (should contain at least API user profile)")
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

                                    # Check for updated_status_available field (from UpdatedStatusConscience check)
                                    if "updated_status_available" not in event:
                                        event_detail["issues"].append("Missing updated_status_available field")
                                        errors.append(
                                            f"🐛 BUG 2: conscience_result missing updated_status_available flag"
                                        )

                                    # Optional recursive flag
                                    if "is_recursive" in event:
                                        events_with_recursive_flag += 1
                                        if event["is_recursive"]:
                                            recursive_conscience_count += 1

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
                                    "dma_results": {"csdma", "dsdma", "pdma"},  # Changed from aspdma_options to pdma
                                    "aspdma_result": {"selected_action", "action_rationale", "is_recursive"},
                                    "conscience_result": {
                                        "conscience_passed",
                                        "final_action",
                                        "epistemic_data",
                                        "is_recursive",
                                        "conscience_override_reason",
                                        "action_was_overridden",
                                        "updated_status_available",
                                    },
                                    "action_result": {
                                        "action_executed",
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

        # Trigger a task to generate events using new async message endpoint
        try:
            response = requests.post(
                f"{base_url}/v1/agent/message",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"message": "Test reasoning event streaming"},
                timeout=10,
            )
            # Validate the response schema
            if response.status_code == 200:
                data = response.json().get("data", {})
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
            message = f"✅ All 6 reasoning events received with valid schemas (no duplicates, no unexpected events)"
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
    def run_custom_test(test: QATestCase, config: QAConfig, token: str) -> Dict[str, Any]:
        """Run streaming verification custom test."""
        if test.custom_handler == "verify_reasoning_stream":
            return StreamingVerificationModule.verify_streaming_events(config.base_url, token, timeout=60)
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
        ]
