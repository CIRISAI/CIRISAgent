"""Privacy schema loading with hybrid YAML/graph storage."""

import json
from pathlib import Path
from typing import Any, Dict, Optional, Union

import yaml

from .schemas import PrivacySchemaConfig, PrivacyTableMapping


class PrivacySchemaLoader:
    """Load privacy schemas from YAML/JSON files.

    Supports hybrid approach:
    1. Load from file (YAML/JSON)
    2. Store in MemoryBus graph for runtime querying (future)
    3. Cache in memory for fast access
    """

    def __init__(self) -> None:
        self._cache: Dict[str, PrivacySchemaConfig] = {}

    def load_from_file(self, file_path: Union[str, Path]) -> PrivacySchemaConfig:
        """Load privacy schema from YAML or JSON file.

        Args:
            file_path: Path to YAML or JSON file

        Returns:
            Parsed privacy schema config

        Raises:
            ValueError: If file format not supported
            FileNotFoundError: If file doesn't exist
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Privacy schema file not found: {file_path}")

        # Check cache
        cache_key = str(path.absolute())
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Load file
        with open(path, "r") as f:
            if path.suffix in [".yaml", ".yml"]:
                data = yaml.safe_load(f)
            elif path.suffix == ".json":
                data = json.load(f)
            else:
                raise ValueError(f"Unsupported file format: {path.suffix}. Use .yaml, .yml, or .json")

        # Parse into Pydantic model
        schema = self._parse_schema(data)

        # Cache
        self._cache[cache_key] = schema

        return schema

    def _parse_schema(self, data: Dict[str, Any]) -> PrivacySchemaConfig:
        """Parse raw dict into PrivacySchemaConfig.

        Supports two formats:
        1. Verbose format (current JSON approach)
        2. Compact format (YAML-friendly)

        Args:
            data: Raw schema data

        Returns:
            Parsed schema config
        """
        # Check if compact format (YAML-style)
        if "tables" in data and isinstance(data["tables"], dict):
            return self._parse_compact_format(data)
        else:
            # Verbose format - direct Pydantic parse
            return PrivacySchemaConfig(**data)

    def _parse_compact_format(self, data: Dict[str, Any]) -> PrivacySchemaConfig:
        """Parse compact YAML format.

        Example:
        ```yaml
        tables:
          users:
            identifier_columns: [email, user_id]
            pii_columns:
              email: {type: email, strategy: hash}
              name: {type: name, strategy: pseudonymize}
              phone: {type: phone, strategy: null}
            cascade_deletes: [user_sessions]
        ```

        Args:
            data: Compact format data

        Returns:
            Parsed schema config
        """
        tables = []

        for table_name, table_config in data["tables"].items():
            # Get identifier columns
            identifier_cols = table_config.get("identifier_columns", [])
            primary_identifier = identifier_cols[0] if identifier_cols else "user_id"

            # Parse PII columns
            columns = []
            pii_columns = table_config.get("pii_columns", {})

            for col_name, col_config in pii_columns.items():
                # Handle both dict and simple format
                if isinstance(col_config, dict):
                    data_type = col_config.get("type", "text")
                    strategy = col_config.get("strategy", "delete")
                    is_identifier = col_name in identifier_cols
                else:
                    # Simple format: just strategy
                    data_type = "text"
                    strategy = str(col_config)
                    is_identifier = False

                from .schemas import PrivacyColumnMapping

                columns.append(
                    PrivacyColumnMapping(
                        column_name=col_name,
                        data_type=data_type,
                        is_identifier=is_identifier,
                        anonymization_strategy=strategy,
                    )
                )

            # Parse cascade deletes
            cascade_deletes = table_config.get("cascade_deletes", [])

            tables.append(
                PrivacyTableMapping(
                    table_name=table_name,
                    identifier_column=primary_identifier,
                    columns=columns,
                    cascade_deletes=cascade_deletes,
                )
            )

        return PrivacySchemaConfig(
            tables=tables,
            global_identifier_column=data.get("global_identifier_column"),
        )

    async def store_in_graph(self, connector_id: str, schema: PrivacySchemaConfig, memory_bus: Any) -> None:
        """Store privacy schema in graph for runtime querying.

        Creates GraphNodes for each table with privacy metadata.
        Uses GraphScope.ENVIRONMENT for persistence across agents.

        Args:
            connector_id: Unique connector identifier
            schema: Privacy schema to store
            memory_bus: MemoryBus instance for graph storage

        Future implementation - stores schema as graph nodes:
        - Node type: "privacy_schema"
        - Properties: connector_id, table_name, columns, etc.
        - Edges: table -> column relationships
        """
        # TODO: Implement graph storage using MemoryBus
        # This will enable cross-agent privacy schema sharing
        pass

    async def load_from_graph(self, connector_id: str, memory_bus: Any) -> Optional[PrivacySchemaConfig]:
        """Load privacy schema from graph storage.

        Args:
            connector_id: Unique connector identifier
            memory_bus: MemoryBus instance

        Returns:
            Privacy schema if found, None otherwise

        Future implementation - queries graph for schema nodes.
        """
        # TODO: Implement graph loading using MemoryBus
        pass
