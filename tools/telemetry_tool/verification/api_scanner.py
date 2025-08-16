#!/usr/bin/env python3
"""
API scanner implementation for finding metrics via API endpoints.
Scans health, service status, telemetry, and memory query endpoints.
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import aiohttp

from .protocols import APIScanner
from .schemas import MetricSource, MetricVerification, ProductionEvidence, ScannerConfig


class APIMetricScanner(APIScanner):
    """Implementation of API scanner for metrics."""

    def __init__(self, config: ScannerConfig):
        self.config = config
        # Use production API (with trailing slash for proper urljoin)
        self.base_url = "https://agents.ciris.ai/api/datum/v1/"

        # Get token from environment or use default
        import os

        token = os.getenv("DATUM_API_TOKEN", "21131fdf6cd5a44044fcec261aba2c596aa8fad1a5b9725a41cacf6b33419023")
        self.headers = {"Authorization": f"Bearer service:{token}"}
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(headers=self.headers)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()

    async def scan(self, config: ScannerConfig) -> List[MetricVerification]:
        """Scan API endpoints for metrics."""
        verifications = []

        async with aiohttp.ClientSession(headers=self.headers) as self.session:
            # Scan various endpoints
            health_evidence = await self.scan_health_endpoint()
            telemetry_evidence = await self.scan_telemetry_endpoints()

            # Scan service status for each service
            service_evidence = {}
            services = await self._get_services()
            for service_id in services:
                evidence = await self.scan_service_status(service_id)
                service_evidence.update(evidence)

            # Query memory for metric nodes
            memory_evidence = await self.query_memory_api(
                "MATCH (n:TimeSeriesDataPoint) RETURN n.metric_name LIMIT 100"
            )

            # Combine all evidence
            all_metrics = set()
            all_metrics.update(health_evidence.keys())
            all_metrics.update(telemetry_evidence.keys())
            all_metrics.update(service_evidence.keys())
            all_metrics.update(memory_evidence.keys())

            for metric_name in all_metrics:
                verification = MetricVerification(
                    metric_name=metric_name, module="API", version="1.4.2", is_in_production=True, is_in_api=True
                )

                # Add all evidence
                for evidence_dict in [health_evidence, telemetry_evidence, service_evidence, memory_evidence]:
                    if metric_name in evidence_dict:
                        verification.add_production_evidence(evidence_dict[metric_name])

                verifications.append(verification)

        return verifications

    def get_source_type(self) -> str:
        """Return the source type."""
        return "api"

    async def scan_health_endpoint(self) -> Dict[str, ProductionEvidence]:
        """Scan /health endpoint for metrics."""
        evidence = {}

        try:
            url = urljoin(self.base_url, "system/health")
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()

                    # Handle nested data structure
                    if "data" in data:
                        health_data = data["data"]

                        # Extract uptime
                        if "uptime_seconds" in health_data:
                            evidence["system.uptime_seconds"] = ProductionEvidence(
                                source=MetricSource.API_HEALTH,
                                timestamp=datetime.now(),
                                value=health_data["uptime_seconds"],
                                endpoint="/system/health",
                                notes="System uptime from health endpoint",
                            )

                        # Extract service health metrics
                        if "services" in health_data:
                            for service_name, service_data in health_data["services"].items():
                                if isinstance(service_data, dict):
                                    if "available" in service_data:
                                        metric_name = f"{service_name}.available"
                                        evidence[metric_name] = ProductionEvidence(
                                            source=MetricSource.API_HEALTH,
                                            timestamp=datetime.now(),
                                            value=service_data["available"],
                                            endpoint="/system/health",
                                            notes=f"Service availability for {service_name}",
                                        )
                                    if "healthy" in service_data:
                                        metric_name = f"{service_name}.healthy"
                                        evidence[metric_name] = ProductionEvidence(
                                            source=MetricSource.API_HEALTH,
                                            timestamp=datetime.now(),
                                            value=service_data["healthy"],
                                            endpoint="/system/health",
                                            notes=f"Service health for {service_name}",
                                        )
        except Exception as e:
            print(f"Error scanning health endpoint: {e}")

        return evidence

    async def scan_service_status(self, service_id: str) -> Dict[str, ProductionEvidence]:
        """Scan /services/{id}/status for metrics."""
        evidence = {}

        try:
            url = urljoin(self.base_url, f"services/{service_id}/status")
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()

                    # Extract service metrics
                    if "metrics" in data:
                        metrics = data["metrics"]

                        # Handle different metric formats
                        if isinstance(metrics, dict):
                            for key, value in metrics.items():
                                metric_name = f"{service_id}.{key}"
                                evidence[metric_name] = ProductionEvidence(
                                    source=MetricSource.API_SERVICE,
                                    timestamp=datetime.now(),
                                    value=value,
                                    endpoint=f"/services/{service_id}/status",
                                    notes=f"Service metric for {service_id}",
                                )

                    # Check for telemetry data
                    if "telemetry" in data:
                        telemetry = data["telemetry"]
                        for metric_name, value in self._flatten_dict(telemetry, prefix=service_id).items():
                            evidence[metric_name] = ProductionEvidence(
                                source=MetricSource.API_SERVICE,
                                timestamp=datetime.now(),
                                value=value,
                                endpoint=f"/services/{service_id}/status",
                                notes=f"Telemetry data for {service_id}",
                            )
        except Exception as e:
            print(f"Error scanning service {service_id}: {e}")

        return evidence

    async def scan_telemetry_endpoints(self) -> Dict[str, ProductionEvidence]:
        """Scan all telemetry-related endpoints."""
        evidence = {}

        telemetry_endpoints = [
            "telemetry/unified",
            "telemetry",
            "metrics",
            "system/metrics",
        ]

        for endpoint in telemetry_endpoints:
            try:
                url = urljoin(self.base_url, endpoint)
                async with self.session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                    elif response.status == 500:
                        print(f"Warning: {endpoint} returned 500 - skipping")
                        continue
                    else:
                        data = {}

                    # Extract metrics based on endpoint format
                    if data:
                        if endpoint == "telemetry/unified":
                            # Unified endpoint returns all metrics
                            if "metrics" in data:
                                for service_data in data["metrics"]:
                                    service_name = service_data.get("service_name", "unknown")
                                    if "metrics" in service_data:
                                        for metric_key, value in service_data["metrics"].items():
                                            metric_name = f"{service_name}.{metric_key}"
                                            evidence[metric_name] = ProductionEvidence(
                                                source=MetricSource.API_TELEMETRY,
                                                timestamp=datetime.now(),
                                                value=value,
                                                endpoint=f"/{endpoint}",
                                                notes="From unified telemetry endpoint",
                                            )

                        elif endpoint == "telemetry/metrics":
                            # List of available metrics
                            if isinstance(data, list):
                                for metric_name in data:
                                    evidence[metric_name] = ProductionEvidence(
                                        source=MetricSource.API_TELEMETRY,
                                        timestamp=datetime.now(),
                                        endpoint=f"/{endpoint}",
                                        notes="Available metric from telemetry/metrics",
                                    )

                        elif endpoint == "telemetry/current":
                            # Current metric values
                            for metric_name, value in self._flatten_dict(data).items():
                                evidence[metric_name] = ProductionEvidence(
                                    source=MetricSource.API_TELEMETRY,
                                    timestamp=datetime.now(),
                                    value=value,
                                    endpoint=f"/{endpoint}",
                                    notes="Current telemetry value",
                                )
            except Exception as e:
                print(f"Error scanning {endpoint}: {e}")

        return evidence

    async def query_memory_api(self, query: str) -> Dict[str, ProductionEvidence]:
        """Query memory API for metrics."""
        evidence = {}

        try:
            url = urljoin(self.base_url, "memory/query")
            payload = {"query": query}

            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()

                    # Extract metric names from query results
                    if "results" in data:
                        for result in data["results"]:
                            if "metric_name" in result:
                                metric_name = result["metric_name"]
                                evidence[metric_name] = ProductionEvidence(
                                    source=MetricSource.API_MEMORY,
                                    timestamp=datetime.now(),
                                    endpoint="/memory/query",
                                    query_used=query,
                                    notes="Found via memory query API",
                                )
        except Exception as e:
            print(f"Error querying memory API: {e}")

        return evidence

    async def _get_services(self) -> List[str]:
        """Get list of available services."""
        services = []

        try:
            url = urljoin(self.base_url, "services")
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if isinstance(data, list):
                        services = [s.get("id", s.get("name")) for s in data]
                    elif "services" in data:
                        services = [s.get("id", s.get("name")) for s in data["services"]]
        except Exception as e:
            print(f"Error getting services: {e}")

        # Fallback to known services
        if not services:
            services = [
                "llm",
                "memory",
                "telemetry",
                "audit",
                "config",
                "incident",
                "tsdb",
                "authentication",
                "resource_monitor",
                "wise_authority",
                "adaptive_filter",
                "visibility",
                "self_observation",
                "task_scheduler",
            ]

        return services

    def _flatten_dict(self, d: Dict[str, Any], prefix: str = "", sep: str = ".") -> Dict[str, Any]:
        """Flatten nested dictionary to dot-notation keys."""
        items = []
        for k, v in d.items():
            new_key = f"{prefix}{sep}{k}" if prefix else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
        return dict(items)
