"""
Test OBSERVER SSE Streaming on Scout Remote Agent.

Validates that OBSERVER users receive SSE events for their own tasks.
"""

import json
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Set

import requests

# Configuration
BASE_URL = "https://scoutapi.ciris.ai/api/scout-remote-test-dahrb9"
OBSERVER_TOKEN = "ciris_observer_1n3Iwr-d1zme96_1MybJK262thIPvKYPJMgrP_Bjaec"
TIMEOUT_SECONDS = 60

# Expected reasoning events
EXPECTED_EVENTS = {
    "thought_start",
    "snapshot_and_context",
    "dma_results",
    "aspdma_result",
    "conscience_result",
    "action_result",
}


def test_observer_sse_streaming():
    """Test OBSERVER SSE streaming for their own tasks."""
    print("=" * 80)
    print("🧪 OBSERVER SSE Streaming Test")
    print("=" * 80)
    print(f"Base URL: {BASE_URL}")
    print(f"Timeout: {TIMEOUT_SECONDS}s")
    print(f"Token: {OBSERVER_TOKEN[:20]}...")
    print("=" * 80 + "\n")

    received_events: Set[str] = set()
    event_details: List[Dict[str, Any]] = []
    errors: List[str] = []
    start_time = time.time()

    # Shared state for thread communication
    stream_connected = threading.Event()
    stream_error = threading.Event()
    task_id_from_message: str = ""

    def monitor_stream():
        """Monitor SSE stream in a separate thread."""
        nonlocal received_events, event_details, errors

        try:
            headers = {"Authorization": f"Bearer {OBSERVER_TOKEN}", "Accept": "text/event-stream"}

            print(f"🔌 Connecting to SSE stream...")
            response = requests.get(
                f"{BASE_URL}/v1/system/runtime/reasoning-stream", headers=headers, stream=True, timeout=5
            )

            if response.status_code != 200:
                error_msg = f"Stream connection failed: HTTP {response.status_code}"
                print(f"❌ {error_msg}")
                errors.append(error_msg)
                stream_error.set()
                return

            print(f"✅ Connected to SSE stream (HTTP {response.status_code})")
            stream_connected.set()

            # Parse SSE stream
            event_count = 0
            for line in response.iter_lines():
                if not line:
                    continue

                line = line.decode("utf-8") if isinstance(line, bytes) else line

                # Handle SSE event types
                if line.startswith("event:"):
                    event_type_line = line[7:].strip()
                    if event_type_line:
                        print(f"📡 SSE Event Type: {event_type_line}")

                # Only process data lines
                if line.startswith("data:"):
                    try:
                        data = json.loads(line[6:])

                        # Extract events from stream update
                        events = data.get("events", [])

                        if not events:
                            print(f"⚠️  Received data line with no events: {line[:100]}")
                            continue

                        for event in events:
                            event_count += 1
                            event_type = event.get("event_type")
                            thought_id = event.get("thought_id", "unknown")
                            task_id = event.get("task_id", "unknown")

                            if not event_type:
                                errors.append("Event missing event_type field")
                                continue

                            # Track this event type
                            received_events.add(event_type)

                            # Print event receipt
                            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                            print(
                                f"[{timestamp}] 📨 Event #{event_count}: {event_type:20s} | task={task_id[:20]:<20s} | thought={thought_id[:20]}"
                            )

                            # Store event details
                            event_details.append(
                                {
                                    "event_type": event_type,
                                    "thought_id": thought_id,
                                    "task_id": task_id,
                                    "timestamp": event.get("timestamp"),
                                }
                            )

                            # For snapshot_and_context, check channel filtering
                            if event_type == "snapshot_and_context":
                                snapshot = event.get("system_snapshot", {})
                                user_profiles = snapshot.get("user_profiles", [])
                                print(f"   └─ 👥 User profiles in snapshot: {len(user_profiles)}")
                                for i, profile in enumerate(user_profiles, 1):
                                    if isinstance(profile, dict):
                                        user_id = profile.get("user_id", "unknown")
                                        display_name = profile.get("display_name", "unknown")
                                        print(f"      {i}. {user_id} ({display_name})")

                    except json.JSONDecodeError as e:
                        errors.append(f"JSON decode error: {e}")
                        print(f"❌ JSON decode error: {e}")
                    except Exception as e:
                        errors.append(f"Error processing event: {e}")
                        print(f"❌ Error processing event: {e}")

        except Exception as e:
            errors.append(f"Stream monitoring error: {e}")
            print(f"❌ Stream monitoring error: {e}")
            stream_error.set()

    # Start monitoring thread
    print("🚀 Starting SSE monitor thread...")
    monitor_thread = threading.Thread(target=monitor_stream, daemon=True)
    monitor_thread.start()

    # Wait for connection
    print("⏳ Waiting for stream connection...")
    if not stream_connected.wait(timeout=3):
        print("\n" + "=" * 80)
        print("❌ TEST FAILED: Failed to connect to SSE stream")
        print("=" * 80)
        return {
            "success": False,
            "error": "Failed to connect to SSE stream",
            "errors": errors,
        }

    # Wait a bit for stream to stabilize
    time.sleep(1)

    # Send a message to create a task
    print("\n📤 Sending message to agent...")
    try:
        response = requests.post(
            f"{BASE_URL}/v1/agent/message",
            headers={"Authorization": f"Bearer {OBSERVER_TOKEN}", "Content-Type": "application/json"},
            json={"message": "Test OBSERVER SSE streaming - can you confirm you received this message?"},
            timeout=10,
        )

        if response.status_code == 200:
            data = response.json().get("data", {})
            task_id_from_message = data.get("task_id", "unknown")
            print(f"✅ Message sent successfully")
            print(f"   └─ Task ID: {task_id_from_message}")
            print(f"   └─ Message ID: {data.get('message_id', 'unknown')}")
            print(f"   └─ Channel ID: {data.get('channel_id', 'unknown')}")
            print(f"   └─ Accepted: {data.get('accepted', False)}")
        else:
            error_msg = f"Message submission failed: HTTP {response.status_code}"
            print(f"❌ {error_msg}")
            errors.append(error_msg)
            print(f"   Response: {response.text[:200]}")
    except Exception as e:
        error_msg = f"Failed to send message: {e}"
        print(f"❌ {error_msg}")
        errors.append(error_msg)

    # Wait for events to stream
    print(f"\n⏳ Waiting up to {TIMEOUT_SECONDS}s for reasoning events...")
    elapsed = 0
    check_interval = 0.5
    last_event_count = 0

    while elapsed < TIMEOUT_SECONDS and len(received_events) < len(EXPECTED_EVENTS):
        time.sleep(check_interval)
        elapsed += check_interval

        # Show progress every 5 seconds
        if int(elapsed) % 5 == 0 and elapsed > 0 and len(received_events) != last_event_count:
            last_event_count = len(received_events)
            print(f"⏱️  {int(elapsed)}s: Received {len(received_events)}/{len(EXPECTED_EVENTS)} event types")

    duration = time.time() - start_time

    # Check results
    missing_events = EXPECTED_EVENTS - received_events
    received_count = len(event_details)

    # Print results
    print("\n" + "=" * 80)
    print("📊 TEST RESULTS")
    print("=" * 80)
    print(f"⏱️  Duration: {duration:.2f}s")
    print(f"📨 Total events received: {received_count}")
    print(f"✅ Event types received ({len(received_events)}/{len(EXPECTED_EVENTS)}): {sorted(received_events)}")

    if missing_events:
        print(f"❌ Missing event types ({len(missing_events)}): {sorted(missing_events)}")

    if errors:
        print(f"\n⚠️  Errors encountered ({len(errors)}):")
        for i, error in enumerate(errors[:5], 1):
            print(f"   {i}. {error}")
        if len(errors) > 5:
            print(f"   ... and {len(errors) - 5} more errors")

    # Determine success
    success = len(missing_events) == 0 and len(errors) == 0 and received_count > 0

    if success:
        print(f"\n✅ TEST PASSED: OBSERVER user received all {len(EXPECTED_EVENTS)} reasoning event types!")
        print("   └─ OBSERVER SSE filtering working correctly for own tasks")
    else:
        print(f"\n❌ TEST FAILED:")
        if received_count == 0:
            print("   └─ ⚠️  NO EVENTS RECEIVED - OBSERVER filtering may be blocking ALL events")
            print("   └─ Expected to receive events for task: " + task_id_from_message)
        elif missing_events:
            print(f"   └─ Missing {len(missing_events)} event types")
        if errors:
            print(f"   └─ {len(errors)} errors encountered")

    print("=" * 80 + "\n")

    return {
        "success": success,
        "received_events": sorted(list(received_events)),
        "missing_events": sorted(list(missing_events)),
        "duration": duration,
        "total_events": received_count,
        "errors": errors,
        "task_id": task_id_from_message,
    }


if __name__ == "__main__":
    result = test_observer_sse_streaming()
    exit(0 if result["success"] else 1)
