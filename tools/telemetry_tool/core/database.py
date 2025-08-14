"""
Mission-Driven Telemetry Database Schema

This SQLite database stores telemetry data with mission alignment scoring,
ensuring every metric serves the covenant's Meta-Goal M-1.
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TelemetryDatabase:
    """Database for mission-driven telemetry management"""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize database with mission-driven schema"""
        if db_path is None:
            db_path = "/home/emoore/CIRISAgent/tools/telemetry_tool/data/telemetry.db"

        db_path_obj = Path(db_path)
        db_path_obj.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self):
        """Create mission-driven telemetry schema"""
        cursor = self.conn.cursor()

        # Core tables reflecting the three-legged stool + mission
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS telemetry_modules (
            id INTEGER PRIMARY KEY,
            module_name TEXT UNIQUE NOT NULL,
            module_path TEXT,
            doc_path TEXT,  -- Path to the .md documentation file
            module_type TEXT CHECK(module_type IN ('BUS', 'SERVICE', 'COMPONENT', 'ADAPTER', 'REGISTRY', 'PROCESSOR')),
            protocol_interface TEXT,  -- Which protocol it implements
            schema_types TEXT,  -- JSON array of schemas used

            -- Mission alignment scores (0.0 to 1.0)
            beneficence_score REAL DEFAULT 0.0,  -- Does it do good?
            non_maleficence_score REAL DEFAULT 0.0,  -- Does it avoid harm?
            transparency_score REAL DEFAULT 0.0,  -- Is it auditable?
            autonomy_score REAL DEFAULT 0.0,  -- Does it respect agency?
            justice_score REAL DEFAULT 0.0,  -- Is it fair?
            coherence_score REAL DEFAULT 0.0,  -- Does it support M-1?

            -- Grace sustainable development metrics
            complexity_debt_hours REAL DEFAULT 0.0,  -- Technical debt
            last_human_review TIMESTAMP,  -- When WA last reviewed
            ci_pipeline_health TEXT,  -- Current CI status

            -- Metadata
            total_metrics INTEGER DEFAULT 0,
            hot_metrics INTEGER DEFAULT 0,
            warm_metrics INTEGER DEFAULT 0,
            cold_metrics INTEGER DEFAULT 0,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        )

        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS telemetry_metrics (
            id INTEGER PRIMARY KEY,
            module_id INTEGER REFERENCES telemetry_modules(id),
            metric_name TEXT NOT NULL,
            metric_type TEXT CHECK(metric_type IN ('counter', 'gauge', 'histogram', 'summary', 'boolean', 'timestamp', 'list', 'calculated')),
            description TEXT,

            -- Access patterns from hot/cold analyzer
            access_pattern TEXT CHECK(access_pattern IN ('HOT', 'WARM', 'COLD')),
            latency_sla_ms INTEGER,  -- Required response time
            update_frequency TEXT,  -- How often it updates

            -- Storage patterns
            storage_location TEXT CHECK(storage_location IN ('memory', 'graph', 'database', 'redis', 'cache', 'file')),
            retention_days INTEGER DEFAULT 30,
            is_persistent BOOLEAN DEFAULT 0,

            -- Mission criticality
            is_safety_critical BOOLEAN DEFAULT 0,  -- Circuit breakers, resource limits
            is_audit_required BOOLEAN DEFAULT 0,  -- Compliance needs
            is_wa_observable BOOLEAN DEFAULT 0,  -- Should WAs see this?

            -- Privacy and ethics
            contains_pii BOOLEAN DEFAULT 0,
            requires_consent BOOLEAN DEFAULT 0,
            data_sensitivity TEXT CHECK(data_sensitivity IN ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'SECRET')),

            -- Access method
            access_method TEXT,  -- How to retrieve this metric

            UNIQUE(module_id, metric_name)
        )
        """
        )

        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS api_endpoints (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE NOT NULL,
            method TEXT CHECK(method IN ('GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'WS')),
            endpoint_category TEXT CHECK(endpoint_category IN ('REALTIME_OPS', 'OBSERVABILITY', 'ANALYTICS', 'COMPLIANCE')),

            -- Which metrics does this endpoint expose?
            metric_ids TEXT,  -- JSON array of metric IDs
            module_ids TEXT,  -- JSON array of module IDs

            -- API design from mission perspective
            serves_purpose TEXT NOT NULL,  -- Why does this exist?
            advances_flourishing TEXT,  -- How does it support M-1?

            -- Performance requirements
            cache_ttl_seconds INTEGER DEFAULT 0,
            rate_limit_per_minute INTEGER DEFAULT 60,
            requires_auth BOOLEAN DEFAULT 1,
            required_role TEXT,  -- OBSERVER, ADMIN, AUTHORITY, SYSTEM_ADMIN

            -- Generated artifacts
            openapi_spec TEXT,  -- Generated OpenAPI definition
            pytest_test_path TEXT,  -- Generated test file
            implementation_path TEXT,  -- Generated FastAPI route

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        )

        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS mission_validations (
            id INTEGER PRIMARY KEY,
            module_id INTEGER REFERENCES telemetry_modules(id),
            validation_type TEXT,  -- 'protocol_alignment', 'schema_compliance', 'covenant_adherence'
            passed BOOLEAN,
            score REAL,  -- 0.0 to 1.0
            issues TEXT,  -- JSON array of issues found
            recommendations TEXT,  -- JSON array of improvements
            validated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        )

        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS data_structures (
            id INTEGER PRIMARY KEY,
            module_id INTEGER REFERENCES telemetry_modules(id),
            structure_name TEXT NOT NULL,
            structure_type TEXT,  -- 'status', 'response', 'config', etc.
            json_schema TEXT,  -- JSON schema definition
            example_data TEXT,  -- Example JSON data

            UNIQUE(module_id, structure_name)
        )
        """
        )

        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS integration_points (
            id INTEGER PRIMARY KEY,
            source_module_id INTEGER REFERENCES telemetry_modules(id),
            target_module_id INTEGER REFERENCES telemetry_modules(id),
            integration_type TEXT,  -- 'depends_on', 'provides_to', 'monitors', etc.
            description TEXT
        )
        """
        )

        self.conn.commit()

    def add_module(self, module_data: Dict[str, Any]) -> int:
        """Add a telemetry module with mission alignment scores"""
        cursor = self.conn.cursor()

        # Convert lists to JSON strings
        if "schema_types" in module_data and isinstance(module_data["schema_types"], list):
            module_data["schema_types"] = json.dumps(module_data["schema_types"])

        cursor.execute(
            """
        INSERT OR REPLACE INTO telemetry_modules (
            module_name, module_path, doc_path, module_type, protocol_interface, schema_types,
            beneficence_score, non_maleficence_score, transparency_score,
            autonomy_score, justice_score, coherence_score,
            total_metrics, hot_metrics, warm_metrics, cold_metrics
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                module_data.get("module_name"),
                module_data.get("module_path"),
                module_data.get("doc_path"),
                module_data.get("module_type"),
                module_data.get("protocol_interface"),
                module_data.get("schema_types"),
                module_data.get("beneficence_score", 0.0),
                module_data.get("non_maleficence_score", 0.0),
                module_data.get("transparency_score", 0.0),
                module_data.get("autonomy_score", 0.0),
                module_data.get("justice_score", 0.0),
                module_data.get("coherence_score", 0.0),
                module_data.get("total_metrics", 0),
                module_data.get("hot_metrics", 0),
                module_data.get("warm_metrics", 0),
                module_data.get("cold_metrics", 0),
            ),
        )

        self.conn.commit()
        return cursor.lastrowid

    def add_metric(self, metric_data: Dict[str, Any]) -> int:
        """Add a telemetry metric with mission criticality flags"""
        cursor = self.conn.cursor()

        cursor.execute(
            """
        INSERT OR REPLACE INTO telemetry_metrics (
            module_id, metric_name, metric_type, description,
            access_pattern, latency_sla_ms, update_frequency,
            storage_location, retention_days, is_persistent,
            is_safety_critical, is_audit_required, is_wa_observable,
            contains_pii, requires_consent, data_sensitivity,
            access_method
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                metric_data.get("module_id"),
                metric_data.get("metric_name"),
                metric_data.get("metric_type"),
                metric_data.get("description"),
                metric_data.get("access_pattern"),
                metric_data.get("latency_sla_ms"),
                metric_data.get("update_frequency"),
                metric_data.get("storage_location"),
                metric_data.get("retention_days", 30),
                metric_data.get("is_persistent", False),
                metric_data.get("is_safety_critical", False),
                metric_data.get("is_audit_required", False),
                metric_data.get("is_wa_observable", False),
                metric_data.get("contains_pii", False),
                metric_data.get("requires_consent", False),
                metric_data.get("data_sensitivity", "INTERNAL"),
                metric_data.get("access_method"),
            ),
        )

        self.conn.commit()
        return cursor.lastrowid

    def get_module_by_name(self, module_name: str) -> Optional[Dict]:
        """Get module data by name"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM telemetry_modules WHERE module_name = ?", (module_name,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_all_modules(self) -> List[Dict]:
        """Get all telemetry modules"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM telemetry_modules ORDER BY module_name")
        return [dict(row) for row in cursor.fetchall()]

    def get_metrics_for_module(self, module_id: int) -> List[Dict]:
        """Get all metrics for a module"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM telemetry_metrics WHERE module_id = ? ORDER BY metric_name", (module_id,))
        return [dict(row) for row in cursor.fetchall()]

    def insert_module(self, **kwargs) -> int:
        """Alias for add_module for compatibility"""
        return self.add_module(kwargs)

    def insert_metric(self, **kwargs) -> int:
        """Alias for add_metric for compatibility"""
        return self.add_metric(kwargs)

    def insert_api_endpoint(
        self,
        module_id: int,
        method: str,
        path: str,
        description: str,
        response_type: str,
        cache_ttl_seconds: int = 0,
        requires_auth: bool = True,
        rate_limit_per_minute: int = 60,
    ) -> int:
        """Add an API endpoint recommendation"""
        cursor = self.conn.cursor()

        cursor.execute(
            """
        INSERT OR REPLACE INTO api_endpoints (
            path, method, module_ids, serves_purpose,
            cache_ttl_seconds, rate_limit_per_minute, requires_auth
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                path,
                method,
                json.dumps([module_id]),
                description,
                cache_ttl_seconds,
                rate_limit_per_minute,
                requires_auth,
            ),
        )

        self.conn.commit()
        return cursor.lastrowid

    def get_module_id(self, module_name: str) -> Optional[int]:
        """Get module ID by name"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM telemetry_modules WHERE module_name = ?", (module_name,))
        row = cursor.fetchone()
        return row[0] if row else None

    def close(self):
        """Close database connection"""
        self.conn.close()
