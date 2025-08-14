# Telemetry Guide Validation Plan

## Comprehensive Testing Strategy for CIRISAGENT_TELEMETRY_GUIDE.md

---

## 1. ENDPOINT EXISTENCE VALIDATION

### Phase 1A: Route Discovery
```python
# Script: validate_endpoints.py

CLAIMED_ENDPOINTS = [
    # System Telemetry
    ("GET", "/system/health"),
    ("GET", "/system/time"),
    ("GET", "/system/resources"),
    ("GET", "/system/services"),

    # Service Registry
    ("GET", "/telemetry/service-registry"),

    # Memory & Graph
    ("GET", "/memory/stats"),
    ("GET", "/memory/timeline"),
    ("GET", "/memory/scopes/{scope}/nodes"),

    # LLM & Resources
    ("GET", "/telemetry/llm/usage"),
    ("GET", "/telemetry/circuit-breakers"),

    # Audit & Security
    ("GET", "/audit/recent"),
    ("GET", "/telemetry/security/incidents"),

    # Agent State
    ("GET", "/visibility/cognitive-state"),
    ("GET", "/visibility/thoughts"),
    ("GET", "/visibility/system-snapshot"),

    # Processing Queue
    ("GET", "/runtime/queue/status"),
    ("GET", "/telemetry/handlers"),

    # Incidents
    ("GET", "/incidents/recent"),

    # Manager Endpoints
    ("GET", "/manager/v1/health"),
    ("GET", "/manager/v1/updates/status"),
    ("GET", "/manager/v1/telemetry/all"),

    # Aggregates
    ("GET", "/telemetry/aggregates/hourly"),
    ("GET", "/telemetry/summary/daily"),

    # Advanced
    ("POST", "/memory/graph/query"),
    ("GET", "/telemetry/export"),
    ("GET", "/metrics"),  # Prometheus

    # Diagnostics
    ("GET", "/telemetry/errors"),
    ("GET", "/telemetry/traces/{trace_id}"),

    # Rate Limits
    ("GET", "/telemetry/rate-limits"),

    # Special
    ("GET", "/telemetry/tsdb/status"),
    ("GET", "/telemetry/discord/status"),

    # History
    ("GET", "/telemetry/history"),
    ("GET", "/telemetry/backups"),
]
```

### Phase 1B: Code Verification
```bash
# For each endpoint, verify it exists in the codebase
for endpoint in CLAIMED_ENDPOINTS:
    method, path = endpoint
    # Search for router definition
    grep -r "@router.${method,,}" --include="*.py" | grep "${path}"
```

### Validation Checklist:
- [ ] All 36 endpoints exist in code
- [ ] Router paths match exactly
- [ ] HTTP methods are correct
- [ ] Path parameters are properly defined

---

## 2. POSITIVE TEST CASES

### Phase 2A: Basic Availability Tests
```python
import requests
import json

BASE_URL = "https://agents.ciris.ai/api/datum/v1"
AUTH = {"Authorization": "Bearer admin:ciris_admin_password"}

def test_endpoint_availability():
    results = {}
    for method, path in CLAIMED_ENDPOINTS:
        url = f"{BASE_URL}{path}"

        if "{" in path:  # Skip parameterized for now
            continue

        try:
            if method == "GET":
                resp = requests.get(url, headers=AUTH, timeout=5)
            elif method == "POST":
                resp = requests.post(url, headers=AUTH, json={}, timeout=5)

            results[path] = {
                "status_code": resp.status_code,
                "has_data": "data" in resp.json() if resp.ok else False,
                "response_time_ms": resp.elapsed.total_seconds() * 1000
            }
        except Exception as e:
            results[path] = {"error": str(e)}

    return results
```

### Phase 2B: Response Format Validation
```python
def validate_response_format(endpoint, response):
    """Verify response matches documented format"""

    EXPECTED_FORMATS = {
        "/system/health": {
            "required_fields": ["status", "version", "uptime_seconds", "services"],
            "field_types": {
                "status": str,
                "version": str,
                "uptime_seconds": float,
                "services": dict
            }
        },
        "/system/services": {
            "required_fields": ["services", "total_services", "healthy_services"],
            "nested_structure": {
                "services": [
                    {"name": str, "type": str, "healthy": bool, "available": bool}
                ]
            }
        },
        # ... define for all endpoints
    }

    if endpoint not in EXPECTED_FORMATS:
        return True, "No format defined"

    expected = EXPECTED_FORMATS[endpoint]
    data = response.get("data", {})

    # Check required fields
    for field in expected.get("required_fields", []):
        if field not in data:
            return False, f"Missing required field: {field}"

    # Check field types
    for field, expected_type in expected.get("field_types", {}).items():
        if field in data and not isinstance(data[field], expected_type):
            return False, f"Wrong type for {field}: expected {expected_type}"

    return True, "Format valid"
```

### Phase 2C: Data Integrity Tests
```python
def test_data_integrity():
    """Verify data relationships and consistency"""

    tests = [
        # System health should match service count
        {
            "name": "service_count_consistency",
            "endpoints": ["/system/health", "/system/services"],
            "validation": lambda h, s: h["data"]["services"]["healthy"] == s["data"]["healthy_services"]
        },

        # Uptime should be consistent
        {
            "name": "uptime_consistency",
            "endpoints": ["/system/health", "/system/time"],
            "validation": lambda h, t: abs(h["data"]["uptime_seconds"] - t["data"]["uptime_seconds"]) < 5
        },

        # Memory stats should be reflected in resources
        {
            "name": "memory_resource_consistency",
            "endpoints": ["/system/resources", "/memory/stats"],
            "validation": lambda r, m: r["data"]["current_usage"]["memory_mb"] > 0
        }
    ]

    for test in tests:
        responses = [requests.get(f"{BASE_URL}{ep}", headers=AUTH).json()
                     for ep in test["endpoints"]]
        result = test["validation"](*responses)
        print(f"{test['name']}: {'PASS' if result else 'FAIL'}")
```

---

## 3. NEGATIVE TEST CASES

### Phase 3A: Authentication Tests
```python
def test_authentication_scenarios():
    """Test various authentication failures"""

    test_cases = [
        {
            "name": "no_auth",
            "headers": {},
            "expected_status": 401,
            "expected_message": "Missing authorization header"
        },
        {
            "name": "invalid_format",
            "headers": {"Authorization": "InvalidFormat"},
            "expected_status": 401,
            "expected_message": "Invalid authorization format"
        },
        {
            "name": "wrong_credentials",
            "headers": {"Authorization": "Bearer wrong:password"},
            "expected_status": 401,
            "expected_message": "Invalid username or password"
        },
        {
            "name": "invalid_service_token",
            "headers": {"Authorization": "Bearer service:invalid_token"},
            "expected_status": 401,
            "expected_message": "Invalid service token"
        },
        {
            "name": "insufficient_role",
            "headers": {"Authorization": "Bearer observer:observer_password"},
            "endpoint": "/system/shutdown",  # Admin only
            "expected_status": 403,
            "expected_message": "Insufficient permissions"
        }
    ]

    for test in test_cases:
        endpoint = test.get("endpoint", "/system/health")
        resp = requests.get(f"{BASE_URL}{endpoint}", headers=test["headers"])

        assert resp.status_code == test["expected_status"], \
            f"{test['name']}: Expected {test['expected_status']}, got {resp.status_code}"

        if test["expected_message"]:
            assert test["expected_message"] in resp.text, \
                f"{test['name']}: Missing expected message"
```

### Phase 3B: Invalid Parameters
```python
def test_invalid_parameters():
    """Test endpoints with invalid parameters"""

    test_cases = [
        {
            "endpoint": "/memory/timeline",
            "params": {"hours": "invalid"},
            "expected_status": 422,
            "expected_error": "validation_error"
        },
        {
            "endpoint": "/memory/timeline",
            "params": {"hours": -1},
            "expected_status": 422,
            "expected_error": "must be positive"
        },
        {
            "endpoint": "/memory/timeline",
            "params": {"hours": 99999},
            "expected_status": 422,
            "expected_error": "exceeds maximum"
        },
        {
            "endpoint": "/memory/scopes/INVALID_SCOPE/nodes",
            "expected_status": 404,
            "expected_error": "scope not found"
        },
        {
            "endpoint": "/telemetry/traces/nonexistent_trace_id",
            "expected_status": 404,
            "expected_error": "trace not found"
        },
        {
            "endpoint": "/telemetry/export",
            "params": {"format": "invalid_format"},
            "expected_status": 422,
            "expected_error": "unsupported format"
        }
    ]

    for test in test_cases:
        url = f"{BASE_URL}{test['endpoint']}"
        params = test.get("params", {})

        resp = requests.get(url, headers=AUTH, params=params)

        assert resp.status_code == test["expected_status"], \
            f"Expected {test['expected_status']}, got {resp.status_code}"

        if test["expected_error"]:
            assert test["expected_error"].lower() in resp.text.lower(), \
                f"Missing expected error: {test['expected_error']}"
```

### Phase 3C: Method Not Allowed
```python
def test_wrong_http_methods():
    """Test using wrong HTTP methods"""

    test_cases = [
        {"endpoint": "/system/health", "wrong_method": "POST", "expected": 405},
        {"endpoint": "/system/health", "wrong_method": "DELETE", "expected": 405},
        {"endpoint": "/memory/graph/query", "wrong_method": "GET", "expected": 405},
        {"endpoint": "/telemetry/export", "wrong_method": "POST", "expected": 405},
    ]

    for test in test_cases:
        url = f"{BASE_URL}{test['endpoint']}"

        if test["wrong_method"] == "POST":
            resp = requests.post(url, headers=AUTH, json={})
        elif test["wrong_method"] == "DELETE":
            resp = requests.delete(url, headers=AUTH)
        elif test["wrong_method"] == "GET":
            resp = requests.get(url, headers=AUTH)

        assert resp.status_code == test["expected"], \
            f"{test['endpoint']} with {test['wrong_method']}: Expected {test['expected']}, got {resp.status_code}"
```

---

## 4. WEBSOCKET VALIDATION

### Phase 4A: WebSocket Connection Test
```python
import websocket
import json

def test_websocket_telemetry():
    """Test WebSocket streaming telemetry"""

    ws_url = "wss://agents.ciris.ai/api/datum/v1/ws/telemetry"

    def on_open(ws):
        # Send auth
        ws.send(json.dumps({
            "type": "auth",
            "token": "Bearer admin:ciris_admin_password"
        }))

        # Subscribe to channels
        ws.send(json.dumps({
            "type": "subscribe",
            "channels": ["metrics", "thoughts", "incidents"]
        }))

    def on_message(ws, message):
        data = json.loads(message)
        assert "type" in data, "Missing type in WebSocket message"
        assert "timestamp" in data, "Missing timestamp in WebSocket message"
        print(f"Received: {data['type']}")

    def on_error(ws, error):
        print(f"WebSocket error: {error}")

    ws = websocket.WebSocketApp(ws_url,
                                on_open=on_open,
                                on_message=on_message,
                                on_error=on_error)

    # Run for 10 seconds
    ws.run_forever(timeout=10)
```

### Phase 4B: WebSocket Authentication Tests
```python
def test_websocket_auth_failures():
    """Test WebSocket auth failures"""

    test_cases = [
        {
            "name": "no_auth",
            "auth_message": None,
            "expected_close": True,
            "expected_code": 1008  # Policy violation
        },
        {
            "name": "invalid_auth",
            "auth_message": {"type": "auth", "token": "invalid"},
            "expected_close": True,
            "expected_code": 1008
        },
        {
            "name": "no_subscribe",
            "auth_message": {"type": "auth", "token": "Bearer admin:ciris_admin_password"},
            "subscribe_message": None,
            "expected_timeout": True
        }
    ]

    for test in test_cases:
        # Test each scenario
        pass
```

---

## 5. RATE LIMITING VALIDATION

### Phase 5A: Rate Limit Tests
```python
import time
import concurrent.futures

def test_rate_limits():
    """Test rate limiting claims"""

    # Claim: 600 requests/minute
    RATE_LIMIT_PER_MINUTE = 600

    def make_request():
        return requests.get(f"{BASE_URL}/system/health", headers=AUTH)

    # Test burst
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        start = time.time()

        # Send 700 requests (should hit limit)
        futures = [executor.submit(make_request) for _ in range(700)]
        results = [f.result() for f in futures]

        elapsed = time.time() - start

        # Count successful vs rate-limited
        success_count = sum(1 for r in results if r.status_code == 200)
        rate_limited = sum(1 for r in results if r.status_code == 429)

        assert rate_limited > 0, "No rate limiting detected"
        assert success_count <= RATE_LIMIT_PER_MINUTE, f"Too many successful requests: {success_count}"

        # Check rate limit headers
        for r in results:
            if r.status_code == 429:
                assert "X-RateLimit-Limit" in r.headers
                assert "X-RateLimit-Remaining" in r.headers
                assert "X-RateLimit-Reset" in r.headers
```

---

## 6. DOCKER LOG VALIDATION

### Phase 6A: Container Log Access
```bash
#!/bin/bash
# validate_docker_logs.sh

# Test SSH access
ssh -i ~/.ssh/ciris_deploy root@108.61.119.117 "echo 'SSH OK'"

# Test container exists
ssh -i ~/.ssh/ciris_deploy root@108.61.119.117 "docker ps | grep ciris-datum"

# Test log file existence
LOG_FILES=(
    "/app/logs/incidents_latest.log"
    "/app/logs/ciris_engine.log"
    "/app/logs/audit.log"
    "/app/logs/telemetry.log"
)

for LOG in "${LOG_FILES[@]}"; do
    echo "Checking $LOG..."
    ssh -i ~/.ssh/ciris_deploy root@108.61.119.117 \
        "docker exec ciris-datum test -f $LOG && echo 'EXISTS' || echo 'MISSING'"
done

# Test log readability
ssh -i ~/.ssh/ciris_deploy root@108.61.119.117 \
    "docker exec ciris-datum tail -n 1 /app/logs/incidents_latest.log"
```

---

## 7. DATA CONSISTENCY VALIDATION

### Phase 7A: Cross-Endpoint Consistency
```python
def test_cross_endpoint_consistency():
    """Verify data is consistent across related endpoints"""

    tests = [
        {
            "name": "llm_usage_consistency",
            "fetch": [
                "/telemetry/llm/usage",
                "/system/services",  # Should have OpenAICompatibleClient
                "/telemetry/circuit-breakers"  # Should have LLM breakers
            ],
            "validate": lambda usage, services, breakers: all([
                any("OpenAI" in s["name"] for s in services["data"]["services"]),
                any("llm" in b["name"].lower() for b in breakers["data"]["circuit_breakers"])
            ])
        },
        {
            "name": "memory_consistency",
            "fetch": [
                "/memory/stats",
                "/memory/timeline?hours=1",
                "/visibility/thoughts"
            ],
            "validate": lambda stats, timeline, thoughts:
                stats["data"]["total_nodes"] > 0 and
                len(timeline["data"]["timeline"]) >= 0 and
                thoughts["data"]["active_count"] >= 0
        }
    ]

    for test in tests:
        responses = {}
        for endpoint in test["fetch"]:
            resp = requests.get(f"{BASE_URL}{endpoint}", headers=AUTH)
            responses[endpoint] = resp.json() if resp.ok else None

        valid = test["validate"](*responses.values())
        print(f"{test['name']}: {'PASS' if valid else 'FAIL'}")
```

---

## 8. MISSING ENDPOINT DISCOVERY

### Phase 8A: Find Undocumented Endpoints
```python
import re
import os

def find_undocumented_endpoints():
    """Find API endpoints in code not in guide"""

    # Parse all route files
    route_dir = "ciris_engine/logic/adapters/api/routes"
    found_endpoints = set()

    for root, dirs, files in os.walk(route_dir):
        for file in files:
            if file.endswith(".py"):
                with open(os.path.join(root, file)) as f:
                    content = f.read()

                    # Find @router decorators
                    patterns = [
                        r'@router\.(get|post|put|delete|patch)\("([^"]+)"',
                        r"@router\.(get|post|put|delete|patch)\('([^']+)'"
                    ]

                    for pattern in patterns:
                        matches = re.findall(pattern, content)
                        for method, path in matches:
                            # Adjust path for router prefix
                            if 'router = APIRouter(prefix="' in content:
                                prefix_match = re.search(r'prefix="([^"]+)"', content)
                                if prefix_match:
                                    full_path = prefix_match.group(1) + path
                                    found_endpoints.add((method.upper(), full_path))

    # Compare with documented
    documented = set(CLAIMED_ENDPOINTS)

    missing_in_guide = found_endpoints - documented
    missing_in_code = documented - found_endpoints

    print(f"Endpoints in code but not guide: {missing_in_guide}")
    print(f"Endpoints in guide but not code: {missing_in_code}")
```

---

## 9. PERFORMANCE VALIDATION

### Phase 9A: Response Time Tests
```python
def test_response_times():
    """Verify endpoints respond within reasonable time"""

    PERFORMANCE_THRESHOLDS = {
        "/system/health": 100,  # ms
        "/system/services": 200,
        "/memory/stats": 500,
        "/memory/timeline": 1000,
        "/telemetry/aggregates/hourly": 2000,
    }

    for endpoint, max_ms in PERFORMANCE_THRESHOLDS.items():
        start = time.time()
        resp = requests.get(f"{BASE_URL}{endpoint}", headers=AUTH)
        elapsed_ms = (time.time() - start) * 1000

        assert elapsed_ms < max_ms, \
            f"{endpoint} took {elapsed_ms:.2f}ms, expected < {max_ms}ms"

        print(f"{endpoint}: {elapsed_ms:.2f}ms ✓")
```

---

## 10. PRODUCTION SAFETY TESTS

### Phase 10A: Read-Only Verification
```python
def test_read_only_safety():
    """Ensure telemetry endpoints are read-only"""

    # These should all fail with 405 or not modify state
    dangerous_tests = [
        {
            "endpoint": "/memory/stats",
            "method": "DELETE",
            "expected": 405
        },
        {
            "endpoint": "/telemetry/llm/usage",
            "method": "POST",
            "body": {"reset": True},
            "expected": 405
        },
        {
            "endpoint": "/system/services",
            "method": "PUT",
            "body": {"service": "test", "action": "stop"},
            "expected": 405
        }
    ]

    for test in dangerous_tests:
        # Attempt dangerous operation
        if test["method"] == "DELETE":
            resp = requests.delete(f"{BASE_URL}{test['endpoint']}", headers=AUTH)
        elif test["method"] == "POST":
            resp = requests.post(f"{BASE_URL}{test['endpoint']}",
                                headers=AUTH, json=test.get("body", {}))
        elif test["method"] == "PUT":
            resp = requests.put(f"{BASE_URL}{test['endpoint']}",
                               headers=AUTH, json=test.get("body", {}))

        assert resp.status_code == test["expected"], \
            f"Dangerous operation not blocked: {test['endpoint']} {test['method']}"
```

---

## EXECUTION PLAN

### Phase 1: Setup (10 mins)
1. Create validation scripts
2. Set up test environment
3. Configure authentication

### Phase 2: Endpoint Discovery (20 mins)
1. Run endpoint existence validation
2. Map all routes in codebase
3. Identify discrepancies

### Phase 3: Positive Tests (30 mins)
1. Test all GET endpoints
2. Validate response formats
3. Check data consistency

### Phase 4: Negative Tests (30 mins)
1. Authentication failures
2. Invalid parameters
3. Wrong HTTP methods

### Phase 5: Advanced Tests (20 mins)
1. WebSocket validation
2. Rate limiting
3. Performance tests

### Phase 6: Production Tests (10 mins)
1. Docker log access
2. Read-only safety
3. Cross-agent validation

### Phase 7: Report Generation (10 mins)
1. Compile results
2. Document failures
3. Update guide with corrections

---

## SUCCESS CRITERIA

### Must Pass (Critical):
- [ ] All documented endpoints exist
- [ ] Authentication works as described
- [ ] Response formats match documentation
- [ ] No dangerous operations allowed
- [ ] Docker logs accessible

### Should Pass (Important):
- [ ] Rate limiting enforced
- [ ] WebSocket streaming works
- [ ] Performance within thresholds
- [ ] Data consistency across endpoints
- [ ] Error messages helpful

### Nice to Have:
- [ ] Prometheus metrics formatted correctly
- [ ] CSV export works
- [ ] Historical data available
- [ ] All pagination works

---

## VALIDATION REPORT TEMPLATE

```markdown
# Telemetry Guide Validation Report

## Summary
- Total Endpoints Tested: 36
- Passed: X
- Failed: Y
- Not Implemented: Z

## Critical Issues
1. [Endpoint] - [Issue Description]

## Minor Issues
1. [Endpoint] - [Issue Description]

## Documentation Updates Needed
1. [Section] - [Update Required]

## Recommendations
1. [Improvement Suggestion]
```

---

*This validation plan ensures the telemetry guide is accurate, complete, and safe for production use by CIRISManager.*
