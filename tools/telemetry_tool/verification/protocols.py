#!/usr/bin/env python3
"""
Protocols for telemetry verification modules.
Defines interfaces that scanner modules must implement.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from .schemas import (
    MetricLocation,
    MetricPattern,
    MetricVerification,
    ModuleScanResult,
    ProductionEvidence,
    ScannerConfig,
)


class MetricScanner(ABC):
    """Base protocol for metric scanners."""

    @abstractmethod
    async def scan(self, config: ScannerConfig) -> List[MetricVerification]:
        """Scan for metrics based on configuration."""
        pass

    @abstractmethod
    def get_source_type(self) -> str:
        """Return the source type this scanner handles."""
        pass


class CodeScanner(MetricScanner):
    """Protocol for scanning code for metrics."""

    @abstractmethod
    def scan_file(self, file_path: Path) -> List[MetricLocation]:
        """Scan a single file for metrics."""
        pass

    @abstractmethod
    def scan_module(self, module_path: Path) -> ModuleScanResult:
        """Scan an entire module for metrics."""
        pass

    @abstractmethod
    def extract_patterns(self, code: str) -> List[MetricPattern]:
        """Extract metric patterns from code."""
        pass

    @abstractmethod
    def resolve_dynamic_patterns(self, pattern: MetricPattern) -> List[str]:
        """Resolve dynamic patterns to concrete metric names."""
        pass


class ProductionScanner(MetricScanner):
    """Protocol for scanning production for metrics."""

    @abstractmethod
    async def scan_tsdb(self) -> Dict[str, ProductionEvidence]:
        """Scan TSDB nodes in memory graph."""
        pass

    @abstractmethod
    async def scan_memory_graph(self, query: Optional[str] = None) -> Dict[str, ProductionEvidence]:
        """Scan memory graph for metric-related nodes."""
        pass

    @abstractmethod
    async def scan_logs(self, start_time: Optional[datetime] = None) -> Dict[str, ProductionEvidence]:
        """Scan production logs for metric emissions."""
        pass


class APIScanner(MetricScanner):
    """Protocol for scanning API endpoints for metrics."""

    @abstractmethod
    async def scan_health_endpoint(self) -> Dict[str, ProductionEvidence]:
        """Scan /health endpoint for metrics."""
        pass

    @abstractmethod
    async def scan_service_status(self, service_id: str) -> Dict[str, ProductionEvidence]:
        """Scan /services/{id}/status for metrics."""
        pass

    @abstractmethod
    async def scan_telemetry_endpoints(self) -> Dict[str, ProductionEvidence]:
        """Scan all telemetry-related endpoints."""
        pass

    @abstractmethod
    async def query_memory_api(self, query: str) -> Dict[str, ProductionEvidence]:
        """Query memory API for metrics."""
        pass


class SDKScanner(MetricScanner):
    """Protocol for scanning SDK capabilities."""

    @abstractmethod
    async def scan_sdk_methods(self) -> Set[str]:
        """Scan SDK for available metric access methods."""
        pass

    @abstractmethod
    async def test_metric_retrieval(self, metric_name: str) -> Optional[ProductionEvidence]:
        """Test if a specific metric can be retrieved via SDK."""
        pass


class MetricVerifier(ABC):
    """Protocol for verifying metrics across dimensions."""

    @abstractmethod
    def verify_metric(self, metric_name: str, sources: List[ProductionEvidence]) -> MetricVerification:
        """Verify a metric across all sources."""
        pass

    @abstractmethod
    def correlate_findings(
        self, code_findings: List[MetricLocation], prod_findings: List[ProductionEvidence]
    ) -> MetricVerification:
        """Correlate code and production findings."""
        pass

    @abstractmethod
    def resolve_naming_mismatches(self, code_name: str, prod_name: str) -> bool:
        """Determine if two metric names refer to the same metric."""
        pass


class ReportGenerator(ABC):
    """Protocol for generating verification reports."""

    @abstractmethod
    def generate_summary(self, verifications: List[MetricVerification]) -> str:
        """Generate summary report."""
        pass

    @abstractmethod
    def generate_detailed_report(self, verifications: List[MetricVerification]) -> str:
        """Generate detailed report with all findings."""
        pass

    @abstractmethod
    def generate_action_items(self, verifications: List[MetricVerification]) -> List[str]:
        """Generate list of action items based on findings."""
        pass

    @abstractmethod
    def export_to_database(self, verifications: List[MetricVerification], db_path: str):
        """Export findings to database."""
        pass


class MetricRepository(ABC):
    """Protocol for storing and retrieving metric verifications."""

    @abstractmethod
    def save_verification(self, verification: MetricVerification):
        """Save a metric verification."""
        pass

    @abstractmethod
    def get_verification(self, metric_name: str) -> Optional[MetricVerification]:
        """Get verification for a specific metric."""
        pass

    @abstractmethod
    def get_all_verifications(self) -> List[MetricVerification]:
        """Get all verifications."""
        pass

    @abstractmethod
    def get_by_module(self, module_name: str) -> List[MetricVerification]:
        """Get verifications for a specific module."""
        pass

    @abstractmethod
    def get_by_status(self, status: str) -> List[MetricVerification]:
        """Get verifications by status."""
        pass

    @abstractmethod
    def update_verification(self, metric_name: str, verification: MetricVerification):
        """Update an existing verification."""
        pass
