#!/usr/bin/env python3
"""
Schemas for telemetry verification system.
Defines the data structures for tracking metric existence across all dimensions.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MetricSource(str, Enum):
    """Where a metric was found."""

    CODE_MEMORIZE = "code_memorize"  # memorize_metric() calls
    CODE_RECORD = "code_record"  # record_metric() calls
    CODE_DYNAMIC = "code_dynamic"  # f-string patterns
    CODE_SCHEMA = "code_schema"  # In ServiceMetrics schema
    TSDB_NODE = "tsdb_node"  # In memory graph as TSDB node
    MEMORY_GRAPH = "memory_graph"  # Other memory graph storage
    API_HEALTH = "api_health"  # /health endpoint
    API_SERVICE = "api_service"  # /services/{id}/status endpoint
    API_TELEMETRY = "api_telemetry"  # /telemetry endpoints
    API_MEMORY = "api_memory"  # /memory/query endpoint
    SDK_METHOD = "sdk_method"  # Available via SDK
    PRODUCTION_LOG = "production_log"  # Found in production logs


class VerificationStatus(str, Enum):
    """Verification status of a metric."""

    NOT_FOUND = "not_found"
    FOUND_CODE = "found_code"  # Found in code only
    FOUND_PROD = "found_prod"  # Found in production only
    VERIFIED = "verified"  # Found in both code and production
    PARTIAL = "partial"  # Some dimensions verified
    DEPRECATED = "deprecated"  # No longer used


class MetricLocation(BaseModel):
    """Where a metric was found in code."""

    file_path: str
    line_number: int
    function_name: Optional[str] = None
    class_name: Optional[str] = None
    context: str = Field(..., description="Code snippet around the metric")


class MetricPattern(BaseModel):
    """A metric pattern found in code."""

    pattern: str = Field(..., description="The metric name or pattern")
    is_dynamic: bool = Field(default=False, description="Uses f-strings or variables")
    is_template: bool = Field(default=False, description="Has placeholders like {service}")
    base_name: Optional[str] = Field(None, description="Base name for dynamic metrics")
    variables: List[str] = Field(default_factory=list, description="Variable names in pattern")
    example_values: List[str] = Field(default_factory=list, description="Example instantiations")


class ProductionEvidence(BaseModel):
    """Evidence that a metric exists in production."""

    source: MetricSource
    timestamp: datetime
    value: Optional[Any] = None
    data_points: int = Field(0, description="Number of data points in TSDB")
    endpoint: Optional[str] = Field(None, description="API endpoint if applicable")
    query_used: Optional[str] = Field(None, description="Query that found it")
    notes: Optional[str] = None


class MetricVerification(BaseModel):
    """Complete verification record for a metric."""

    # Identity
    metric_name: str = Field(..., description="Canonical metric name")
    module: str = Field(..., description="Module that owns this metric")
    version: str = Field(..., description="Version when added (e.g., 1.4.2)")

    # Code presence
    code_locations: List[MetricLocation] = Field(default_factory=list)
    patterns: List[MetricPattern] = Field(default_factory=list)

    # Production presence
    production_evidence: List[ProductionEvidence] = Field(default_factory=list)

    # Verification
    status: VerificationStatus = VerificationStatus.NOT_FOUND
    is_in_code: bool = False
    is_in_production: bool = False
    is_in_api: bool = False
    is_in_sdk: bool = False

    # Metadata
    first_seen: Optional[datetime] = None
    last_verified: Optional[datetime] = None
    notes: Optional[str] = None

    def add_code_location(self, location: MetricLocation):
        """Add a code location where this metric was found."""
        self.code_locations.append(location)
        self.is_in_code = True
        if self.status == VerificationStatus.NOT_FOUND:
            self.status = VerificationStatus.FOUND_CODE
        elif self.status == VerificationStatus.FOUND_PROD:
            self.status = VerificationStatus.VERIFIED

    def add_production_evidence(self, evidence: ProductionEvidence):
        """Add evidence that this metric exists in production."""
        self.production_evidence.append(evidence)
        self.is_in_production = True

        # Update API/SDK flags based on source
        if evidence.source in [
            MetricSource.API_HEALTH,
            MetricSource.API_SERVICE,
            MetricSource.API_TELEMETRY,
            MetricSource.API_MEMORY,
        ]:
            self.is_in_api = True
        if evidence.source == MetricSource.SDK_METHOD:
            self.is_in_sdk = True

        # Update status
        if self.status == VerificationStatus.NOT_FOUND:
            self.status = VerificationStatus.FOUND_PROD
        elif self.status == VerificationStatus.FOUND_CODE:
            self.status = VerificationStatus.VERIFIED


class ModuleScanResult(BaseModel):
    """Result of scanning a module for metrics."""

    module_name: str
    files_scanned: int
    metrics_found: int
    unique_patterns: int
    dynamic_patterns: int
    scan_timestamp: datetime
    errors: List[str] = Field(default_factory=list)

    # Detailed findings
    verifications: List[MetricVerification] = Field(default_factory=list)


class VerificationReport(BaseModel):
    """Complete verification report."""

    timestamp: datetime
    version: str = Field(..., description="CIRIS version being analyzed")

    # Summary stats
    total_metrics: int = 0
    verified_metrics: int = 0
    code_only_metrics: int = 0
    prod_only_metrics: int = 0

    # Detailed counts
    in_code: int = 0
    in_tsdb: int = 0
    in_api: int = 0
    in_sdk: int = 0

    # By module
    modules: Dict[str, ModuleScanResult] = Field(default_factory=dict)

    # All verifications
    verifications: List[MetricVerification] = Field(default_factory=list)

    def add_verification(self, verification: MetricVerification):
        """Add a verification and update stats."""
        self.verifications.append(verification)
        self.total_metrics += 1

        if verification.is_in_code:
            self.in_code += 1
        if verification.is_in_production:
            if verification.is_in_code:
                self.verified_metrics += 1
            else:
                self.prod_only_metrics += 1
        elif verification.is_in_code:
            self.code_only_metrics += 1

        if verification.is_in_api:
            self.in_api += 1
        if verification.is_in_sdk:
            self.in_sdk += 1


class ScannerConfig(BaseModel):
    """Configuration for the scanner modules."""

    base_path: str = "/home/emoore/CIRISAgent/ciris_engine"
    api_base_url: str = "http://localhost:8000/api/datum/v1"
    api_credentials: Dict[str, str] = Field(
        default_factory=lambda: {"username": "admin", "password": "ciris_admin_password"}
    )

    # Scan options
    scan_code: bool = True
    scan_production: bool = True
    scan_api: bool = True
    scan_sdk: bool = True

    # Database paths
    reality_db: str = "telemetry_reality.db"
    mdd_db: str = "telemetry_mdd.db"

    # Patterns to search for
    metric_patterns: List[str] = Field(
        default_factory=lambda: [
            r'memorize_metric\s*\(\s*metric_name\s*=\s*["\']([^"\']+)["\']',
            r'memorize_metric\s*\(\s*["\']([^"\']+)["\']',
            r'\.memorize_metric\s*\(\s*["\']([^"\']+)["\']',
            r'record_metric\s*\(\s*["\']([^"\']+)["\']',
            r'\.record_metric\s*\(\s*["\']([^"\']+)["\']',
            r'record_metric\s*\(\s*f["\']([^"\']+)["\']',
            r'memorize_metric\s*\(\s*f["\']([^"\']+)["\']',
            r"ServiceMetrics\s*\(\s*[^)]*\)",  # ServiceMetrics schema usage
            r'"metric_name":\s*["\']([^"\']+)["\']',  # JSON metric definitions
        ]
    )
