#!/usr/bin/env python
"""
Comprehensive API endpoint testing for CIRIS v1.0 API.

Tests all major API endpoints to ensure proper functionality.
"""

import json
import time
import requests
import sys
from typing import Optional, Dict, Any, List

BASE_URL = "http://localhost:8000"


class APITestSuite:
    """Test suite for CIRIS API endpoints."""
    
    def __init__(self):
        self.token = None
        self.admin_token = None
        self.test_results = {}
        
    def get_token(self, username: str = "admin", password: str = "ciris_admin_password") -> str:
        """Get authentication token."""
        response = requests.post(
            f"{BASE_URL}/v1/auth/login",
            json={"username": username, "password": password}
        )
        if response.status_code != 200:
            print(f"❌ Failed to get token: {response.status_code}")
            print(f"Response: {response.text}")
            sys.exit(1)
        
        token = response.json()["access_token"]
        print(f"✅ Got auth token for {username}")
        return token
    
    def test_endpoint(self, name: str, method: str, path: str, 
                     headers: Optional[Dict] = None, 
                     json_data: Optional[Dict] = None,
                     params: Optional[Dict] = None,
                     expected_status: int = 200) -> bool:
        """Test a single endpoint."""
        print(f"\nTesting {name}...")
        
        if headers is None:
            headers = {}
        
        if self.token and "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {self.token}"
        
        try:
            if method == "GET":
                response = requests.get(f"{BASE_URL}{path}", headers=headers, params=params)
            elif method == "POST":
                response = requests.post(f"{BASE_URL}{path}", headers=headers, json=json_data)
            elif method == "PUT":
                response = requests.put(f"{BASE_URL}{path}", headers=headers, json=json_data)
            elif method == "DELETE":
                response = requests.delete(f"{BASE_URL}{path}", headers=headers)
            else:
                print(f"❌ Unknown method: {method}")
                return False
            
            if response.status_code == expected_status:
                print(f"✅ {name}: Status {response.status_code}")
                if response.status_code == 200:
                    try:
                        data = response.json()
                        # Print summary of response
                        if isinstance(data, dict):
                            if "services_online" in data:
                                print(f"   Services: {data['services_online']}/{data['services_total']} healthy")
                            elif "events" in data:
                                print(f"   Events: {len(data['events'])} entries")
                            elif "message" in data:
                                print(f"   Message: {data['message'][:100]}...")
                            elif "response" in data:
                                print(f"   Response: {data['response'][:100]}...")
                    except:
                        pass
                
                self.test_results[name] = {"success": True, "status": response.status_code}
                return True
            else:
                print(f"❌ {name}: Expected {expected_status}, got {response.status_code}")
                print(f"   Response: {response.text[:200]}...")
                self.test_results[name] = {"success": False, "status": response.status_code, "error": response.text[:200]}
                return False
                
        except Exception as e:
            print(f"❌ {name}: Exception {e}")
            self.test_results[name] = {"success": False, "error": str(e)}
            return False
    
    def run_auth_tests(self):
        """Test authentication endpoints."""
        print("\n" + "="*60)
        print("AUTHENTICATION TESTS")
        print("="*60)
        
        # Login (already done in init)
        print("✅ Login: Already authenticated")
        
        # Verify token
        self.test_endpoint("Verify Token", "GET", "/v1/auth/verify")
        
        # Refresh token
        self.test_endpoint("Refresh Token", "POST", "/v1/auth/refresh")
    
    def run_telemetry_tests(self):
        """Test telemetry endpoints."""
        print("\n" + "="*60)
        print("TELEMETRY TESTS")
        print("="*60)
        
        self.test_endpoint("Unified Telemetry", "GET", "/v1/telemetry/unified")
        self.test_endpoint("Services Health", "GET", "/v1/telemetry/services")
        self.test_endpoint("Metrics", "GET", "/v1/telemetry/metrics")
        self.test_endpoint("Node Stats", "GET", "/v1/telemetry/nodes")
        self.test_endpoint("System Snapshot", "GET", "/v1/telemetry/snapshot")
    
    def run_consent_tests(self):
        """Test consent endpoints."""
        print("\n" + "="*60)
        print("CONSENT TESTS")
        print("="*60)
        
        self.test_endpoint("Consent Status", "GET", "/v1/consent/status")
        self.test_endpoint("Query Consents", "GET", "/v1/consent/query")
        self.test_endpoint("Consent Streams", "GET", "/v1/consent/streams")
        self.test_endpoint("Consent Categories", "GET", "/v1/consent/categories")
        self.test_endpoint("Partnership Status", "GET", "/v1/consent/partnership/status")
    
    def run_agent_tests(self):
        """Test agent interaction endpoints."""
        print("\n" + "="*60)
        print("AGENT INTERACTION TESTS")
        print("="*60)
        
        # Basic interaction
        self.test_endpoint(
            "Agent Interact", "POST", "/v1/agent/interact",
            json_data={"message": "Hello from API test"}
        )
        
        # Agent status
        self.test_endpoint("Agent Status", "GET", "/v1/agent/status")
        
        # Cognitive state
        self.test_endpoint("Cognitive State", "GET", "/v1/agent/cognitive_state")
    
    def run_audit_tests(self):
        """Test audit endpoints."""
        print("\n" + "="*60)
        print("AUDIT TESTS")
        print("="*60)
        
        self.test_endpoint("Audit Entries", "GET", "/v1/audit/entries", params={"limit": 10})
        self.test_endpoint("Audit Search", "POST", "/v1/audit/search", json_data={"limit": 10})
        self.test_endpoint("Audit Export", "GET", "/v1/audit/export", params={"format": "json"})
    
    def run_memory_tests(self):
        """Test memory endpoints."""
        print("\n" + "="*60)
        print("MEMORY TESTS")
        print("="*60)
        
        # Store a test memory
        self.test_endpoint(
            "Memorize", "POST", "/v1/memory/memorize",
            json_data={
                "node_id": "test_api_node",
                "node_type": "CONCEPT",
                "attributes": {"test": "data", "source": "api_test"}
            }
        )
        
        # Recall the memory
        self.test_endpoint(
            "Recall", "POST", "/v1/memory/recall",
            json_data={"node_id": "test_api_node"}
        )
        
        # Query memories
        self.test_endpoint("Query Memories", "GET", "/v1/memory/query", params={"node_type": "CONCEPT"})
        
        # Forget the test memory
        self.test_endpoint(
            "Forget", "POST", "/v1/memory/forget",
            json_data={"node_id": "test_api_node"}
        )
    
    def run_runtime_tests(self):
        """Test runtime control endpoints."""
        print("\n" + "="*60)
        print("RUNTIME CONTROL TESTS")
        print("="*60)
        
        self.test_endpoint("Runtime Status", "GET", "/v1/runtime/status")
        self.test_endpoint("Processing Queue", "GET", "/v1/runtime/queue")
        self.test_endpoint("Service Health", "GET", "/v1/runtime/services/health")
        self.test_endpoint("Processor Info", "GET", "/v1/runtime/processor")
    
    def run_all_tests(self):
        """Run all API tests."""
        print("="*80)
        print("CIRIS API TEST SUITE")
        print("="*80)
        
        # Get token
        self.token = self.get_token()
        
        # Run test categories
        self.run_auth_tests()
        self.run_telemetry_tests()
        self.run_consent_tests()
        self.run_agent_tests()
        self.run_audit_tests()
        self.run_memory_tests()
        self.run_runtime_tests()
        
        # Summary
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        
        total = len(self.test_results)
        passed = sum(1 for r in self.test_results.values() if r["success"])
        
        print(f"\nResults: {passed}/{total} tests passed")
        print("\nDetails:")
        for test_name, result in self.test_results.items():
            status = "✅" if result["success"] else "❌"
            print(f"  {status} {test_name}")
            if not result["success"] and "error" in result:
                print(f"      Error: {result['error'][:100]}...")
        
        # Final status
        print("\n" + "="*80)
        if passed == total:
            print("🎉 ALL TESTS PASSED!")
        elif passed >= total * 0.8:
            print(f"✅ MOST TESTS PASSED ({passed}/{total})")
        else:
            print(f"⚠️  SOME TESTS FAILED ({passed}/{total})")
        print("="*80)
        
        return passed == total


def main():
    """Run the API test suite."""
    suite = APITestSuite()
    success = suite.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()