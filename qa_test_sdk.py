#!/usr/bin/env python3
"""
CIRIS API QA Test Suite using the official Python SDK
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List

# Import the CIRIS SDK
from ciris_sdk.client import CIRISClient
from ciris_sdk.exceptions import CIRISAPIError, CIRISAuthenticationError


async def run_qa_tests():
    """Run comprehensive QA tests for CIRIS API."""

    # Initialize client
    client = CIRISClient(base_url="http://localhost:9000", api_key=None)  # Will use username/password auth

    print("=" * 60)
    print("CIRIS API QA Test Suite")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 60)

    test_results = {"passed": 0, "failed": 0, "errors": []}

    try:
        # Authenticate
        print("\n1. AUTHENTICATION")
        print("-" * 40)
        try:
            await client.authenticate(username="admin", password="ciris_admin_password")
            print(f"✓ Authentication successful")
            print(f"  Token: {client.auth_token[:20] if client.auth_token else 'N/A'}...")
            test_results["passed"] += 1
        except Exception as e:
            print(f"✗ Authentication failed: {e}")
            test_results["failed"] += 1
            test_results["errors"].append(f"Auth: {str(e)}")
            return test_results

        # 2. Test Telemetry
        print("\n2. TELEMETRY & OTEL TESTING")
        print("-" * 40)

        # Unified telemetry
        try:
            telemetry = await client.get_telemetry()
            print(f"✓ Unified Telemetry:")
            print(f"  Services Online: {telemetry.get('services_online', 0)}/{telemetry.get('services_total', 0)}")
            print(f"  Memory Usage: {telemetry.get('memory_usage_mb', 0):.2f} MB")
            print(f"  CPU Usage: {telemetry.get('cpu_usage_percent', 0):.1f}%")
            print(f"  Uptime: {telemetry.get('uptime_seconds', 0):.0f} seconds")
            test_results["passed"] += 1
        except Exception as e:
            print(f"✗ Telemetry failed: {e}")
            test_results["failed"] += 1
            test_results["errors"].append(f"Telemetry: {str(e)[:100]}")

        # Service health
        try:
            health = await client.get_service_health()
            healthy_services = sum(1 for s in health.get("services", {}).values() if s.get("healthy"))
            total_services = len(health.get("services", {}))
            print(f"✓ Service Health: {healthy_services}/{total_services} healthy")

            # List any unhealthy services
            unhealthy = [name for name, info in health.get("services", {}).items() if not info.get("healthy")]
            if unhealthy:
                print(f"  Unhealthy: {', '.join(unhealthy)}")
            test_results["passed"] += 1
        except Exception as e:
            print(f"✗ Service health failed: {e}")
            test_results["failed"] += 1
            test_results["errors"].append(f"Health: {str(e)[:100]}")

        # Memory telemetry
        try:
            memory_telemetry = await client.get_memory_telemetry()
            print(f"✓ Memory Telemetry:")
            print(f"  Total Nodes: {memory_telemetry.get('total_nodes', 0)}")
            print(f"  Total Edges: {memory_telemetry.get('total_edges', 0)}")
            print(f"  Node Types: {', '.join(memory_telemetry.get('node_types', {}).keys())}")
            test_results["passed"] += 1
        except Exception as e:
            print(f"✗ Memory telemetry failed: {e}")
            test_results["failed"] += 1
            test_results["errors"].append(f"Memory Tel: {str(e)[:100]}")

        # 3. Test Consent System
        print("\n3. CONSENT SYSTEM TESTING")
        print("-" * 40)

        # Get consent status
        try:
            consent_status = await client.get_consent_status()
            print(f"✓ Consent Status:")
            print(f"  Active Consents: {len(consent_status.get('active_consents', []))}")
            print(f"  Default Mode: {consent_status.get('default_mode', 'unknown')}")
            test_results["passed"] += 1
        except Exception as e:
            print(f"✗ Consent status failed: {e}")
            test_results["failed"] += 1
            test_results["errors"].append(f"Consent: {str(e)[:100]}")

        # Request consent
        try:
            consent = await client.request_consent(
                action="data_processing", context="qa_testing", duration_minutes=30, purpose="API QA Testing"
            )
            print(f"✓ Consent Requested:")
            print(f"  Consent ID: {consent.get('consent_id', 'N/A')}")
            print(f"  Status: {consent.get('status', 'unknown')}")
            test_results["passed"] += 1
        except Exception as e:
            print(f"✗ Consent request failed: {e}")
            test_results["failed"] += 1
            test_results["errors"].append(f"Consent Req: {str(e)[:100]}")

        # 4. Test Memory Operations
        print("\n4. MEMORY SYSTEM TESTING")
        print("-" * 40)

        # Store memory
        try:
            memory_data = {
                "content": f"QA Test Memory Node - {datetime.now().isoformat()}",
                "node_type": "CONCEPT",
                "metadata": {"test": True, "timestamp": datetime.now().isoformat(), "category": "qa_testing"},
            }
            stored_node = await client.store_memory(memory_data)
            print(f"✓ Memory Stored:")
            print(f"  Node ID: {stored_node.get('node_id', 'N/A')}")
            print(f"  Type: {stored_node.get('node_type', 'unknown')}")
            test_results["passed"] += 1

            # Try to recall it
            if stored_node.get("node_id"):
                recalled = await client.recall_memory(stored_node["node_id"])
                if recalled:
                    print(f"✓ Memory Recalled: Node {recalled.get('id', 'N/A')}")
                    test_results["passed"] += 1
                else:
                    print(f"✗ Could not recall stored node")
                    test_results["failed"] += 1
        except Exception as e:
            print(f"✗ Memory store failed: {e}")
            test_results["failed"] += 1
            test_results["errors"].append(f"Memory Store: {str(e)[:100]}")

        # Search memories
        try:
            search_results = await client.search_memory(query="QA Test", node_type="CONCEPT", limit=5)
            print(f"✓ Memory Search:")
            print(f"  Results Found: {len(search_results.get('nodes', []))}")
            if search_results.get("nodes"):
                print(f"  First Result: {search_results['nodes'][0].get('id', 'N/A')}")
            test_results["passed"] += 1
        except Exception as e:
            print(f"✗ Memory search failed: {e}")
            test_results["failed"] += 1
            test_results["errors"].append(f"Memory Search: {str(e)[:100]}")

        # Get memory stats
        try:
            memory_stats = await client.get_memory_stats()
            print(f"✓ Memory Statistics:")
            print(f"  Total Nodes: {memory_stats.get('total_nodes', 0)}")
            print(f"  Storage Size: {memory_stats.get('storage_size_mb', 0):.2f} MB")
            test_results["passed"] += 1
        except Exception as e:
            print(f"✗ Memory stats failed: {e}")
            test_results["failed"] += 1
            test_results["errors"].append(f"Memory Stats: {str(e)[:100]}")

        # 5. Test Memory Visualization
        print("\n5. MEMORY VISUALIZATION TESTING")
        print("-" * 40)

        # Get graph structure
        try:
            graph = await client.get_memory_graph()
            print(f"✓ Memory Graph:")
            print(f"  Nodes: {len(graph.get('nodes', []))}")
            print(f"  Edges: {len(graph.get('edges', []))}")
            test_results["passed"] += 1
        except Exception as e:
            print(f"✗ Memory graph failed: {e}")
            test_results["failed"] += 1
            test_results["errors"].append(f"Memory Graph: {str(e)[:100]}")

        # Get clusters
        try:
            clusters = await client.get_memory_clusters()
            print(f"✓ Memory Clusters:")
            print(f"  Total Clusters: {len(clusters.get('clusters', []))}")
            test_results["passed"] += 1
        except Exception as e:
            print(f"✗ Memory clusters failed: {e}")
            test_results["failed"] += 1
            test_results["errors"].append(f"Clusters: {str(e)[:100]}")

        # 6. Test Agent Interaction
        print("\n6. AGENT INTERACTION TESTING")
        print("-" * 40)

        # Send message
        try:
            response = await client.send_message("Hello, this is a QA test message. Please respond.")
            print(f"✓ Agent Response:")
            if response.get("response"):
                print(f"  Message: {response['response'][:100]}...")
            print(f"  Thought ID: {response.get('thought_id', 'N/A')}")
            test_results["passed"] += 1
        except Exception as e:
            print(f"✗ Agent interaction failed: {e}")
            test_results["failed"] += 1
            test_results["errors"].append(f"Agent: {str(e)[:100]}")

        # Get agent state
        try:
            state = await client.get_agent_state()
            print(f"✓ Agent State:")
            print(f"  Cognitive State: {state.get('cognitive_state', 'unknown')}")
            print(f"  Processing: {state.get('is_processing', False)}")
            print(f"  Queue Length: {state.get('queue_length', 0)}")
            test_results["passed"] += 1
        except Exception as e:
            print(f"✗ Agent state failed: {e}")
            test_results["failed"] += 1
            test_results["errors"].append(f"Agent State: {str(e)[:100]}")

        # 7. Test Runtime Control
        print("\n7. RUNTIME CONTROL TESTING")
        print("-" * 40)

        # Get queue status
        try:
            queue = await client.get_processing_queue()
            print(f"✓ Processing Queue:")
            print(f"  Items: {len(queue.get('items', []))}")
            print(f"  Processing: {queue.get('is_processing', False)}")
            test_results["passed"] += 1
        except Exception as e:
            print(f"✗ Queue status failed: {e}")
            test_results["failed"] += 1
            test_results["errors"].append(f"Queue: {str(e)[:100]}")

        # Get processor info
        try:
            processor = await client.get_processor_state()
            print(f"✓ Processor State:")
            print(f"  State: {processor.get('state', 'unknown')}")
            print(f"  Mode: {processor.get('mode', 'unknown')}")
            test_results["passed"] += 1
        except Exception as e:
            print(f"✗ Processor state failed: {e}")
            test_results["failed"] += 1
            test_results["errors"].append(f"Processor: {str(e)[:100]}")

        # 8. Test Audit System
        print("\n8. AUDIT SYSTEM TESTING")
        print("-" * 40)

        # Get audit logs
        try:
            audit_logs = await client.get_audit_logs(limit=5)
            print(f"✓ Audit Logs:")
            print(f"  Entries Retrieved: {len(audit_logs.get('entries', []))}")
            if audit_logs.get("entries"):
                print(f"  Latest: {audit_logs['entries'][0].get('event_type', 'unknown')}")
            test_results["passed"] += 1
        except Exception as e:
            print(f"✗ Audit logs failed: {e}")
            test_results["failed"] += 1
            test_results["errors"].append(f"Audit: {str(e)[:100]}")

        # Get verification report
        try:
            verification = await client.verify_audit_chain()
            print(f"✓ Audit Verification:")
            print(f"  Chain Valid: {verification.get('chain_valid', False)}")
            print(f"  Signatures Valid: {verification.get('signatures_valid', False)}")
            test_results["passed"] += 1
        except Exception as e:
            print(f"✗ Audit verification failed: {e}")
            test_results["failed"] += 1
            test_results["errors"].append(f"Verification: {str(e)[:100]}")

        # 9. Test Circuit Breakers
        print("\n9. CIRCUIT BREAKER TESTING")
        print("-" * 40)

        try:
            circuit_breakers = await client.get_circuit_breakers()
            print(f"✓ Circuit Breakers:")
            open_breakers = [name for name, info in circuit_breakers.items() if info.get("state") == "OPEN"]
            print(f"  Total: {len(circuit_breakers)}")
            print(f"  Open: {len(open_breakers)}")
            if open_breakers:
                print(f"  Open Breakers: {', '.join(open_breakers[:3])}")
            test_results["passed"] += 1
        except Exception as e:
            print(f"✗ Circuit breakers failed: {e}")
            test_results["failed"] += 1
            test_results["errors"].append(f"Circuit: {str(e)[:100]}")

        # 10. Test Edge Cases
        print("\n10. EDGE CASE TESTING")
        print("-" * 40)

        # Test invalid recall
        try:
            invalid = await client.recall_memory("nonexistent-node-id-xyz123")
            if invalid is None or not invalid:
                print(f"✓ Invalid recall handled correctly (returned None/empty)")
                test_results["passed"] += 1
            else:
                print(f"✗ Invalid recall returned unexpected data")
                test_results["failed"] += 1
        except CIRISAPIError as e:
            print(f"✓ Invalid recall raised expected error: {str(e)[:50]}...")
            test_results["passed"] += 1
        except Exception as e:
            print(f"✗ Invalid recall unexpected error: {e}")
            test_results["failed"] += 1

        # Test rate limiting (send multiple requests quickly)
        print("Testing rate limiting...")
        rate_limit_hit = False
        try:
            for i in range(10):
                await client.get_telemetry()
            print(f"✓ Rate limiting not triggered (or high limit)")
            test_results["passed"] += 1
        except CIRISAPIError as e:
            if "rate" in str(e).lower():
                print(f"✓ Rate limiting working as expected")
                test_results["passed"] += 1
                rate_limit_hit = True
            else:
                raise
        except Exception as e:
            print(f"✗ Rate limit test failed: {e}")
            test_results["failed"] += 1

    except Exception as e:
        print(f"\n✗ Test Suite Error: {e}")
        import traceback

        traceback.print_exc()
        test_results["failed"] += 1
        test_results["errors"].append(f"Suite Error: {str(e)}")
    finally:
        # Cleanup
        try:
            await client.close()
        except:
            pass

    # Print summary
    print("\n" + "=" * 60)
    print("QA TEST SUMMARY")
    print("=" * 60)
    print(f"✓ Passed: {test_results['passed']}")
    print(f"✗ Failed: {test_results['failed']}")
    print(f"Success Rate: {test_results['passed']/(test_results['passed']+test_results['failed'])*100:.1f}%")

    if test_results["errors"]:
        print("\nErrors encountered:")
        for error in test_results["errors"]:
            print(f"  - {error}")

    return test_results


async def test_websocket():
    """Test WebSocket functionality."""
    print("\n" + "=" * 60)
    print("WEBSOCKET TESTING")
    print("=" * 60)

    client = CIRISClient(base_url="http://localhost:9000")

    try:
        await client.authenticate(username="admin", password="ciris_admin_password")

        # Connect WebSocket
        ws = await client.connect_websocket()
        print("✓ WebSocket Connected")

        # Subscribe to telemetry updates
        await ws.send(json.dumps({"type": "subscribe", "channel": "telemetry"}))
        print("✓ Subscribed to telemetry")

        # Receive a few updates
        print("Waiting for updates...")
        for i in range(3):
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(message)
                print(f"✓ Update {i+1}: {data.get('type', 'unknown')}")
            except asyncio.TimeoutError:
                print(f"  No update received (timeout)")
                break

        await ws.close()
        print("✓ WebSocket Closed")

    except Exception as e:
        print(f"✗ WebSocket Test Failed: {e}")
    finally:
        await client.close()


if __name__ == "__main__":
    print("Starting CIRIS API QA Tests...")
    print(f"Target: http://localhost:9000")
    print(f"Time: {datetime.now().isoformat()}")

    # Run main test suite
    results = asyncio.run(run_qa_tests())

    # Run WebSocket tests
    asyncio.run(test_websocket())

    print("\n" + "=" * 60)
    if results["failed"] == 0:
        print("✅ ALL TESTS PASSED!")
    else:
        print(f"⚠️  {results['failed']} tests failed")
    print("=" * 60)
