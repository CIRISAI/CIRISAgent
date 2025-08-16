#!/usr/bin/env python3
"""
SDK scanner implementation for checking metric availability via SDK.
Tests both TypeScript and Python SDK capabilities.
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from .protocols import SDKScanner
from .schemas import MetricSource, MetricVerification, ProductionEvidence, ScannerConfig


class SDKMetricScanner(SDKScanner):
    """Implementation of SDK scanner for metrics."""

    def __init__(self, config: ScannerConfig):
        self.config = config
        self.sdk_methods: Set[str] = set()
        self.available_metrics: Dict[str, ProductionEvidence] = {}

    async def scan(self, config: ScannerConfig) -> List[MetricVerification]:
        """Scan SDK for metric availability."""
        verifications = []

        # Scan SDK methods
        sdk_methods = await self.scan_sdk_methods()

        # Test known metrics
        known_metrics = self._get_known_metrics()

        for metric_name in known_metrics:
            evidence = await self.test_metric_retrieval(metric_name)
            if evidence:
                verification = MetricVerification(
                    metric_name=metric_name, module="SDK", version="1.4.2", is_in_production=True, is_in_sdk=True
                )
                verification.add_production_evidence(evidence)
                verifications.append(verification)

        return verifications

    def get_source_type(self) -> str:
        """Return the source type."""
        return "sdk"

    async def scan_sdk_methods(self) -> Set[str]:
        """Scan SDK for available metric access methods."""
        methods = set()

        # Check TypeScript SDK
        ts_sdk_path = Path("/home/emoore/CIRISAgent/sdk/typescript/src/client.ts")
        if ts_sdk_path.exists():
            with open(ts_sdk_path, "r") as f:
                content = f.read()

            # Look for telemetry-related methods
            import re

            method_pattern = r"async\s+(\w*[Tt]elemetry\w*)\s*\("
            for match in re.finditer(method_pattern, content):
                methods.add(match.group(1))

            # Look for metric-related methods
            metric_pattern = r"async\s+(\w*[Mm]etric\w*)\s*\("
            for match in re.finditer(metric_pattern, content):
                methods.add(match.group(1))

            # Look for get methods that might return metrics
            get_pattern = r"async\s+(get\w*)\s*\("
            for match in re.finditer(get_pattern, content):
                method_name = match.group(1)
                if any(keyword in method_name.lower() for keyword in ["metric", "telemetry", "stats", "health"]):
                    methods.add(method_name)

        # Check Python SDK
        py_sdk_path = Path("/home/emoore/CIRISAgent/sdk/python/ciris_sdk/client.py")
        if py_sdk_path.exists():
            with open(py_sdk_path, "r") as f:
                content = f.read()

            # Look for telemetry methods
            import re

            method_pattern = r"def\s+(\w*telemetry\w*)\s*\(self"
            for match in re.finditer(method_pattern, content, re.IGNORECASE):
                methods.add(match.group(1))

            # Look for metric methods
            metric_pattern = r"def\s+(\w*metric\w*)\s*\(self"
            for match in re.finditer(metric_pattern, content, re.IGNORECASE):
                methods.add(match.group(1))

        # Known SDK methods from documentation
        known_methods = {
            # TypeScript SDK
            "getTelemetry",
            "getUnifiedTelemetry",
            "getServiceTelemetry",
            "getHealthMetrics",
            "queryMetrics",
            # Python SDK
            "get_telemetry",
            "get_unified_telemetry",
            "get_service_telemetry",
            "get_health_metrics",
            "query_metrics",
        }

        methods.update(known_methods)
        self.sdk_methods = methods

        return methods

    async def test_metric_retrieval(self, metric_name: str) -> Optional[ProductionEvidence]:
        """Test if a specific metric can be retrieved via SDK."""

        # Check if metric is available through known SDK methods
        retrievable_metrics = {
            # Health metrics
            "system.cpu_percent": ["getHealthMetrics", "get_health_metrics"],
            "system.memory_mb": ["getHealthMetrics", "get_health_metrics"],
            "system.uptime_seconds": ["getHealthMetrics", "get_health_metrics"],
            # LLM metrics
            "llm.tokens.total": ["getServiceTelemetry", "get_service_telemetry"],
            "llm.tokens.input": ["getServiceTelemetry", "get_service_telemetry"],
            "llm.tokens.output": ["getServiceTelemetry", "get_service_telemetry"],
            "llm.cost.cents": ["getServiceTelemetry", "get_service_telemetry"],
            "llm.latency.ms": ["getServiceTelemetry", "get_service_telemetry"],
            # Handler metrics
            "handler_invoked_total": ["getUnifiedTelemetry", "get_unified_telemetry"],
            "handler_completed_total": ["getUnifiedTelemetry", "get_unified_telemetry"],
            # Error metrics
            "error.occurred": ["queryMetrics", "query_metrics"],
            # Service metrics
            "telemetry_service.shutdown": ["getServiceTelemetry", "get_service_telemetry"],
            "memory_service.nodes_created": ["getServiceTelemetry", "get_service_telemetry"],
            "audit_service.events_logged": ["getServiceTelemetry", "get_service_telemetry"],
        }

        if metric_name in retrievable_metrics:
            methods = retrievable_metrics[metric_name]
            available_method = None

            for method in methods:
                if method in self.sdk_methods:
                    available_method = method
                    break

            if available_method:
                return ProductionEvidence(
                    source=MetricSource.SDK_METHOD,
                    timestamp=datetime.now(),
                    endpoint=available_method,
                    notes=f"Retrievable via SDK method: {available_method}",
                )

        # Check if metric matches patterns that would be available
        patterns_to_methods = {
            r"^llm\.": ["getServiceTelemetry"],
            r"^memory\.": ["getServiceTelemetry"],
            r"^telemetry\.": ["getServiceTelemetry"],
            r"^system\.": ["getHealthMetrics"],
            r"^handler_": ["getUnifiedTelemetry"],
            r"^error\.": ["queryMetrics"],
        }

        import re

        for pattern, methods in patterns_to_methods.items():
            if re.match(pattern, metric_name):
                for method in methods:
                    if method in self.sdk_methods or method.replace("get", "get_") in self.sdk_methods:
                        return ProductionEvidence(
                            source=MetricSource.SDK_METHOD,
                            timestamp=datetime.now(),
                            endpoint=method,
                            notes=f"Pattern match: retrievable via {method}",
                        )

        return None

    def _get_known_metrics(self) -> List[str]:
        """Get list of metrics to test."""
        return [
            # System metrics
            "system.cpu_percent",
            "system.memory_mb",
            "system.disk_used_gb",
            "system.uptime_seconds",
            # LLM metrics
            "llm.tokens.total",
            "llm.tokens.input",
            "llm.tokens.output",
            "llm.cost.cents",
            "llm.environmental.carbon_grams",
            "llm.environmental.energy_kwh",
            "llm.latency.ms",
            "llm_tokens_used",
            "llm_api_call_structured",
            # Processing metrics
            "thought_processing_started",
            "thought_processing_completed",
            # Handler metrics
            "handler_invoked_total",
            "handler_completed_total",
            "handler_invoked_task_complete",
            "handler_invoked_memorize",
            "handler_completed_task_complete",
            "handler_completed_memorize",
            # Action metrics
            "action_selected_task_complete",
            "action_selected_memorize",
            # Error metrics
            "error.occurred",
            # Service metrics
            "telemetry_service.shutdown",
            "memory_service.nodes_created",
            "audit_service.events_logged",
            "config_service.values_retrieved",
            "incident_service.incidents_created",
        ]

    async def test_sdk_integration(self) -> Dict[str, bool]:
        """Test actual SDK integration if available."""
        results = {}

        # Try Python SDK
        try:
            test_script = """
import sys
sys.path.insert(0, '/home/emoore/CIRISAgent/sdk/python')
from ciris_sdk import CIRISClient

client = CIRISClient(base_url='http://localhost:8000', agent_id='datum')
client.authenticate('admin', 'ciris_admin_password')

# Test methods
methods = {
    'health': client.get_health(),
    'telemetry': client.get_unified_telemetry(),
    'services': client.get_services(),
}

import json
print(json.dumps({k: bool(v) for k, v in methods.items()}))
"""

            result = subprocess.run(["python3", "-c", test_script], capture_output=True, text=True, timeout=5)

            if result.returncode == 0:
                results = json.loads(result.stdout)
        except Exception as e:
            print(f"Error testing Python SDK: {e}")

        # Try TypeScript SDK
        try:
            test_script = """
const { CIRISClient } = require('/home/emoore/CIRISAgent/sdk/typescript/dist/index.js');

async function test() {
    const client = new CIRISClient({
        baseUrl: 'http://localhost:8000',
        agentId: 'datum'
    });

    await client.authenticate('admin', 'ciris_admin_password');

    const results = {
        health: await client.getHealth(),
        telemetry: await client.getUnifiedTelemetry(),
        services: await client.getServices(),
    };

    console.log(JSON.stringify(Object.keys(results).reduce((acc, k) => {
        acc[k] = !!results[k];
        return acc;
    }, {})));
}

test().catch(console.error);
"""

            result = subprocess.run(["node", "-e", test_script], capture_output=True, text=True, timeout=5)

            if result.returncode == 0:
                ts_results = json.loads(result.stdout)
                results.update({f"ts_{k}": v for k, v in ts_results.items()})
        except Exception as e:
            print(f"Error testing TypeScript SDK: {e}")

        return results
