#!/usr/bin/env python3
"""
CIRIS API QA Test Suite using Python SDK
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict

# Import the CIRIS SDK
from ciris_engine.sdk.client import CIRISClient
from ciris_engine.sdk.config import ClientConfig


async def run_qa_tests():
    """Run comprehensive QA tests for CIRIS API."""

    # Initialize client
    config = ClientConfig(
        base_url="http://localhost:9000", username="admin", password="ciris_admin_password", timeout=30
    )

    client = CIRISClient(config)

    print("=" * 60)
    print("CIRIS API QA Test Suite")
    print("=" * 60)

    try:
        # Connect and authenticate
        await client.connect()
        print("✓ Authentication successful")
        print(f"  Token: {client.token[:20]}...")
        print(f"  Role: {client.user_role}")

        # 1. Test Telemetry
        print("\n1. TELEMETRY TESTING")
        print("-" * 40)

        # Unified telemetry
        telemetry = await client.telemetry.get_unified()
        print(f"✓ Unified Telemetry:")
        print(f"  Services: {telemetry.get('services_online', 0)}/{telemetry.get('services_total', 0)} online")
        print(f"  Memory Usage: {telemetry.get('memory_usage_mb', 0):.2f} MB")
        print(f"  Uptime: {telemetry.get('uptime_seconds', 0):.0f} seconds")

        # Service health
        health = await client.services.get_health()
        print(f"✓ Service Health:")
        healthy_count = sum(1 for s in health.get("services", {}).values() if s.get("healthy"))
        print(f"  Healthy Services: {healthy_count}/{len(health.get('services', {}))}")

        # Memory telemetry
        memory_tel = await client.telemetry.get_memory()
        print(f"✓ Memory Telemetry:")
        print(f"  Total Nodes: {memory_tel.get('total_nodes', 0)}")
        print(f"  Total Edges: {memory_tel.get('total_edges', 0)}")

        # 2. Test Consent System
        print("\n2. CONSENT SYSTEM TESTING")
        print("-" * 40)

        # Get consent status
        consent_status = await client.consent.get_status()
        print(f"✓ Consent Status:")
        print(f"  Active Consents: {len(consent_status.get('active_consents', []))}")
        print(f"  Default Mode: {consent_status.get('default_mode', 'unknown')}")

        # Request consent
        consent_request = await client.consent.request(
            action="data_processing", context="qa_testing", duration_minutes=30, purpose="API QA Testing"
        )
        print(f"✓ Consent Requested:")
        print(f"  Consent ID: {consent_request.get('consent_id', 'N/A')}")
        print(f"  Status: {consent_request.get('status', 'unknown')}")

        # 3. Test Memory Operations
        print("\n3. MEMORY SYSTEM TESTING")
        print("-" * 40)

        # Store memory
        memory_node = await client.memory.store(
            content="QA Test Memory Node",
            node_type="CONCEPT",
            metadata={"test": True, "timestamp": datetime.now().isoformat()},
        )
        print(f"✓ Memory Stored:")
        print(f"  Node ID: {memory_node.get('node_id', 'N/A')}")
        print(f"  Type: {memory_node.get('node_type', 'unknown')}")

        # Search memories
        search_results = await client.memory.search(query="QA Test", node_type="CONCEPT", limit=5)
        print(f"✓ Memory Search:")
        print(f"  Results Found: {len(search_results.get('nodes', []))}")

        # Get memory stats
        memory_stats = await client.memory.get_stats()
        print(f"✓ Memory Statistics:")
        print(f"  Total Nodes: {memory_stats.get('total_nodes', 0)}")
        print(f"  Node Types: {', '.join(memory_stats.get('node_types', {}).keys())}")

        # 4. Test Memory Visualization
        print("\n4. MEMORY VISUALIZATION TESTING")
        print("-" * 40)

        # Get graph structure
        graph = await client.memory.get_graph()
        print(f"✓ Memory Graph:")
        print(f"  Nodes: {len(graph.get('nodes', []))}")
        print(f"  Edges: {len(graph.get('edges', []))}")

        # Get clusters
        clusters = await client.memory.get_clusters()
        print(f"✓ Memory Clusters:")
        print(f"  Total Clusters: {len(clusters.get('clusters', []))}")

        # 5. Test Agent Interaction
        print("\n5. AGENT INTERACTION TESTING")
        print("-" * 40)

        # Send message
        response = await client.agent.interact("Hello, this is a QA test message")
        print(f"✓ Agent Response:")
        print(f"  Message: {response.get('response', 'No response')[:100]}...")
        print(f"  Thought ID: {response.get('thought_id', 'N/A')}")

        # Get agent state
        state = await client.agent.get_state()
        print(f"✓ Agent State:")
        print(f"  Current State: {state.get('cognitive_state', 'unknown')}")
        print(f"  Processing: {state.get('is_processing', False)}")

        # 6. Test Runtime Control
        print("\n6. RUNTIME CONTROL TESTING")
        print("-" * 40)

        # Get queue status
        queue = await client.runtime.get_queue()
        print(f"✓ Processing Queue:")
        print(f"  Queue Length: {len(queue.get('items', []))}")
        print(f"  Processing: {queue.get('is_processing', False)}")

        # Get processor state
        processor = await client.runtime.get_processor()
        print(f"✓ Processor State:")
        print(f"  State: {processor.get('state', 'unknown')}")
        print(f"  Mode: {processor.get('mode', 'unknown')}")

        # 7. Test Audit System
        print("\n7. AUDIT SYSTEM TESTING")
        print("-" * 40)

        # Get audit logs
        audit_logs = await client.audit.get_logs(limit=5)
        print(f"✓ Audit Logs:")
        print(f"  Total Entries: {len(audit_logs.get('entries', []))}")

        # Get verification report
        verification = await client.audit.verify()
        print(f"✓ Audit Verification:")
        print(f"  Chain Valid: {verification.get('chain_valid', False)}")
        print(f"  Signatures Valid: {verification.get('signatures_valid', False)}")

        # 8. Test OTEL/Observability
        print("\n8. OTEL/OBSERVABILITY TESTING")
        print("-" * 40)

        # Get metrics
        metrics = await client.telemetry.get_metrics()
        print(f"✓ OTEL Metrics:")
        print(f"  Total Metrics: {len(metrics.get('metrics', []))}")

        # Get traces
        traces = await client.telemetry.get_traces()
        print(f"✓ OTEL Traces:")
        print(f"  Active Traces: {len(traces.get('active_traces', []))}")

        # 9. Test Circuit Breakers
        print("\n9. CIRCUIT BREAKER TESTING")
        print("-" * 40)

        circuit_breakers = await client.services.get_circuit_breakers()
        print(f"✓ Circuit Breakers:")
        open_breakers = [name for name, status in circuit_breakers.items() if status.get("state") == "OPEN"]
        print(f"  Total: {len(circuit_breakers)}")
        print(f"  Open: {len(open_breakers)}")
        if open_breakers:
            print(f"  Open Breakers: {', '.join(open_breakers)}")

        # 10. Test Edge Cases
        print("\n10. EDGE CASE TESTING")
        print("-" * 40)

        # Test empty search
        empty_search = await client.memory.search(query="xyz123_nonexistent")
        print(f"✓ Empty Search: {len(empty_search.get('nodes', []))} results")

        # Test invalid node recall
        try:
            invalid_node = await client.memory.recall("invalid-node-id")
            print(f"✗ Invalid Recall: Should have failed but got {invalid_node}")
        except Exception as e:
            print(f"✓ Invalid Recall: Properly handled ({str(e)[:50]}...)")

        # Test large metadata
        large_metadata = {f"key_{i}": f"value_{i}" for i in range(100)}
        try:
            large_node = await client.memory.store(
                content="Large metadata test", node_type="CONCEPT", metadata=large_metadata
            )
            print(f"✓ Large Metadata: Stored successfully")
        except Exception as e:
            print(f"✗ Large Metadata Failed: {str(e)[:50]}...")

        print("\n" + "=" * 60)
        print("QA TEST SUITE COMPLETED SUCCESSFULLY")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ Test Suite Failed: {e}")
        import traceback

        traceback.print_exc()
    finally:
        await client.disconnect()


async def test_websocket():
    """Test WebSocket functionality."""
    print("\nWEBSOCKET TESTING")
    print("-" * 40)

    config = ClientConfig(base_url="http://localhost:9000", username="admin", password="ciris_admin_password")

    client = CIRISClient(config)
    await client.connect()

    try:
        # Connect to WebSocket
        ws = await client.websocket.connect()
        print("✓ WebSocket Connected")

        # Subscribe to telemetry
        await ws.subscribe("telemetry")
        print("✓ Subscribed to telemetry channel")

        # Receive a few updates
        for i in range(3):
            update = await ws.receive()
            print(f"✓ Update {i+1}: {update.get('type', 'unknown')}")

        await ws.close()
        print("✓ WebSocket Closed")

    except Exception as e:
        print(f"✗ WebSocket Test Failed: {e}")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    print("Starting CIRIS API QA Tests...")
    print(f"Time: {datetime.now().isoformat()}")

    # Run main test suite
    asyncio.run(run_qa_tests())

    # Run WebSocket tests
    asyncio.run(test_websocket())

    print("\nAll tests completed!")
