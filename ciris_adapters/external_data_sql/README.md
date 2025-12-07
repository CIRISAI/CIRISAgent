# External Data SQL Module

SQL database connector for DSAR automation and external data access. Provides dialect-aware operations for SQLite, MySQL, and PostgreSQL with runtime configuration support.

## Architecture

Follows CIRIS organic architecture:
- **External data sources = Tools** (not services)
- **Uses existing ToolBus** for service discovery
- **Uses existing MemoryBus** for identity resolution and caching
- **Composition over abstraction**
- **Runtime configuration** - Dynamic connector initialization without restart

## Supported Dialects

- **SQLite** - File-based, serverless
- **MySQL** - Popular open-source RDBMS
- **PostgreSQL** - Advanced open-source RDBMS

## Tools Provided

The service provides 9 tools with generic naming. The `connector_id` parameter routes requests to the appropriate connector instance:

### Configuration & Discovery Tools

1. **`initialize_sql_connector`** - Runtime connector configuration with connection details and privacy schema
2. **`get_sql_service_metadata`** - Discover connector metadata, capabilities, and table information

### DSAR Operations Tools

3. **`sql_find_user_data`** - Discover all locations where user data exists
4. **`sql_export_user`** - Export all user data (JSON/CSV format)
5. **`sql_delete_user`** - Delete all user data with cascade
6. **`sql_anonymize_user`** - Anonymize instead of delete
7. **`sql_verify_deletion`** - Verify zero user data + crypto proof

### Database Operations Tools

8. **`sql_get_stats`** - Database statistics and table information
9. **`sql_query`** - Raw SQL query (SELECT only, with privacy constraints)

## Configuration

### Privacy Schema

Define which tables and columns contain user data:

```json
{
  "tables": [
    {
      "table_name": "users",
      "identifier_column": "email",
      "columns": [
        {
          "column_name": "email",
          "data_type": "email",
          "is_identifier": true,
          "anonymization_strategy": "hash"
        },
        {
          "column_name": "full_name",
          "data_type": "name",
          "is_identifier": false,
          "anonymization_strategy": "pseudonymize"
        },
        {
          "column_name": "phone",
          "data_type": "phone",
          "is_identifier": false,
          "anonymization_strategy": "null"
        }
      ],
      "cascade_deletes": ["user_sessions", "user_preferences"]
    },
    {
      "table_name": "orders",
      "identifier_column": "customer_email",
      "columns": [
        {
          "column_name": "customer_email",
          "data_type": "email",
          "is_identifier": true,
          "anonymization_strategy": "hash"
        },
        {
          "column_name": "shipping_address",
          "data_type": "address",
          "is_identifier": false,
          "anonymization_strategy": "truncate"
        }
      ],
      "cascade_deletes": []
    }
  ]
}
```

### Anonymization Strategies

- **`delete`** - Delete the entire row (default for GDPR erasure)
- **`null`** - Set column to NULL
- **`hash`** - Hash the value (MD5/SHA256)
- **`pseudonymize`** - Replace with deterministic pseudonym
- **`truncate`** - Keep first 3 characters + '***'

### Connection String Format

**SQLite:**
```
sqlite:////path/to/database.db
```

**MySQL:**
```
mysql+pymysql://user:password@host:port/database
```

**PostgreSQL:**
```
postgresql+psycopg2://user:password@host:port/database
```

## Usage Examples

### 1. Runtime Connector Initialization

The service now supports dynamic runtime initialization without requiring restart:

```python
# Initialize connector at runtime via tool call
result = await sql_service.execute_tool(
    tool_name="initialize_sql_connector",
    parameters={
        "connector_id": "production_db",
        "connection_string": "postgresql+psycopg2://user:pass@localhost/mydb",
        "dialect": "postgresql",
        "privacy_schema_path": "/path/to/privacy_schema.yaml",
        "connection_timeout": 30,
        "query_timeout": 60
    }
)

# Result contains connector configuration details
print(f"Connector initialized: {result.success}")
print(f"Connector ID: {result.data['connector_id']}")
print(f"Dialect: {result.data['dialect']}")
print(f"Privacy schema loaded: {result.data['privacy_schema_loaded']}")
```

### 2. Discover Connector Metadata

Get metadata about connector capabilities and configuration:

```python
result = await sql_service.execute_tool(
    tool_name="get_sql_service_metadata",
    parameters={"connector_id": "production_db"}
)

metadata = result.data
print(f"Data source type: {metadata['data_source_type']}")
print(f"DSAR capabilities: {metadata['dsar_capabilities']}")
print(f"Contains PII: {metadata['contains_pii']}")
print(f"GDPR applicable: {metadata['gdpr_applicable']}")
print(f"Table count: {metadata['table_count']}")
print(f"Privacy schema configured: {metadata['privacy_schema_configured']}")
```

### 3. Static Configuration (Legacy)

You can still initialize with static configuration for simple use cases:

```python
from ciris_adapters.external_data_sql import SQLToolService, SQLConnectorConfig, PrivacySchemaConfig

# Define privacy schema
privacy_schema = PrivacySchemaConfig(
    tables=[
        PrivacyTableMapping(
            table_name="users",
            identifier_column="email",
            columns=[
                PrivacyColumnMapping(
                    column_name="email",
                    data_type="email",
                    is_identifier=True,
                    anonymization_strategy="hash"
                ),
                PrivacyColumnMapping(
                    column_name="full_name",
                    data_type="name",
                    is_identifier=False,
                    anonymization_strategy="pseudonymize"
                )
            ],
            cascade_deletes=["user_sessions"]
        )
    ]
)

# Create connector config
config = SQLConnectorConfig(
    connector_id="production_db",
    connection_string="postgresql+psycopg2://user:pass@localhost/mydb",
    dialect=SQLDialect.POSTGRESQL,
    privacy_schema=privacy_schema,
    connection_timeout=30,
    query_timeout=60
)

# Initialize service
sql_service = SQLToolService(time_service=time_service, config=config)
await sql_service.initialize()

# Register with ToolBus
service_registry.register_service(sql_service, ServiceType.TOOL)
```

### 4. Find User Data

```python
result = await sql_service.execute_tool(
    tool_name="sql_find_user_data",
    parameters={
        "connector_id": "production_db",
        "user_identifier": "user@example.com",
        "identifier_type": "email"
    }
)

# Result contains DataLocation objects
locations = result.data["locations"]
for loc in locations:
    print(f"Found data: {loc['table_name']}.{loc['column_name']} ({loc['row_count']} rows)")
```

### 5. Export User Data

```python
result = await sql_service.execute_tool(
    tool_name="sql_export_user",
    parameters={
        "connector_id": "production_db",
        "user_identifier": "user@example.com",
        "identifier_type": "email",
        "export_format": "json"  # or "csv"
    }
)

export = result.data
print(f"Exported {export['total_rows']} rows from {len(export['tables_exported'])} tables")
print(f"Checksum: {export['checksum']}")
```

### 6. Delete User Data

```python
result = await sql_service.execute_tool(
    tool_name="sql_delete_user",
    parameters={
        "connector_id": "production_db",
        "user_identifier": "user@example.com",
        "identifier_type": "email",
        "soft_delete": False  # Hard delete (default)
    }
)

deletion = result.data
print(f"Deleted {deletion['total_rows_deleted']} rows from {len(deletion['tables_affected'])} tables")
print(f"Verification passed: {deletion.get('verification_passed', False)}")
```

### 7. Anonymize Instead of Delete

```python
result = await sql_service.execute_tool(
    tool_name="sql_anonymize_user",
    parameters={
        "connector_id": "production_db",
        "user_identifier": "user@example.com",
        "identifier_type": "email"
    }
)

anon = result.data
print(f"Anonymized {anon['total_rows_affected']} rows")
for table, cols in anon['columns_anonymized'].items():
    print(f"  {table}: {', '.join(cols)}")
```

### 8. Verify Deletion (with Crypto Proof)

```python
result = await sql_service.execute_tool(
    tool_name="sql_verify_deletion",
    parameters={
        "connector_id": "production_db",
        "user_identifier": "user@example.com",
        "identifier_type": "email"
    }
)

verification = result.data
print(f"Zero data confirmed: {verification['zero_data_confirmed']}")
print(f"Scanned {len(verification['tables_scanned'])} tables")
if verification.get('cryptographic_proof'):
    print(f"Ed25519 proof: {verification['cryptographic_proof']}")
```

### 9. Get Database Statistics

```python
result = await sql_service.execute_tool(
    tool_name="sql_get_stats",
    parameters={"connector_id": "production_db"}
)

stats = result.data
print(f"Database: {stats['database_name']}")
print(f"Total tables: {stats['total_tables']}")
print(f"Total rows: {stats['total_rows']}")
```

### 10. Execute Raw Query

```python
result = await sql_service.execute_tool(
    tool_name="sql_query",
    parameters={
        "connector_id": "production_db",
        "query": "SELECT COUNT(*) as user_count FROM users WHERE created_at > :start_date",
        "parameters": {"start_date": "2024-01-01"}
    }
)

query_result = result.data
print(f"Rows returned: {len(query_result['rows'])}")
print(f"Columns: {query_result['columns']}")
```

## Tool Parameter Schemas

### initialize_sql_connector

Initialize or reconfigure SQL connector at runtime.

**Parameters:**
- `connector_id` (required, string) - Unique identifier for the connector
- `connection_string` (required, string) - Database connection string
- `dialect` (required, string) - SQL dialect: sqlite, postgresql, mysql
- `privacy_schema_path` (optional, string) - Path to privacy schema YAML file
- `connection_timeout` (optional, integer) - Connection timeout in seconds (default: 30)
- `query_timeout` (optional, integer) - Query timeout in seconds (default: 60)
- `max_retries` (optional, integer) - Maximum retry attempts (default: 3)

**Returns:**
```json
{
  "connector_id": "production_db",
  "dialect": "postgresql",
  "privacy_schema_loaded": true,
  "table_count": 15
}
```

### get_sql_service_metadata

Get metadata about SQL connector capabilities.

**Parameters:**
- `connector_id` (required, string) - Connector to get metadata for

**Returns:**
```json
{
  "data_source": true,
  "data_source_type": "sql",
  "contains_pii": true,
  "gdpr_applicable": true,
  "connector_id": "production_db",
  "dialect": "postgresql",
  "dsar_capabilities": ["find", "export", "delete", "anonymize"],
  "privacy_schema_configured": true,
  "table_count": 15
}
```

### sql_find_user_data, sql_export_user, sql_delete_user, sql_anonymize_user, sql_verify_deletion

All DSAR tools accept:
- `connector_id` (required, string) - SQL connector ID to use
- `user_identifier` (required, string) - User identifier (email, user_id, etc.)
- `identifier_type` (required, string) - Type of identifier: email, user_id, phone, etc.

Additional parameters vary by tool (see usage examples above).

### sql_get_stats

**Parameters:**
- `connector_id` (required, string) - SQL connector ID to use

### sql_query

**Parameters:**
- `connector_id` (required, string) - SQL connector ID to use
- `query` (required, string) - SQL query to execute (SELECT only)
- `parameters` (optional, object) - Query parameters for parameterized queries

## Integration with CIRIS DSAR Automation

The SQL connector integrates seamlessly with existing CIRIS DSARAutomationService:

```python
# DSARAutomationService can now coordinate across:
# 1. CIRIS internal data (consent, interactions, contributions)
# 2. External SQL databases (via SQLToolService)
# 3. SaaS connectors (via future OpenAPIToolService)

async def handle_access_request(user_id: str):
    # 1. Discover available SQL connectors
    sql_connectors = []
    for tool_name in ["initialize_sql_connector", "get_sql_service_metadata"]:
        # Get metadata for each configured connector
        metadata = await tool_bus.execute_tool(
            "get_sql_service_metadata",
            {"connector_id": "production_db"}
        )
        if metadata.success and metadata.data.get("contains_pii"):
            sql_connectors.append(metadata.data)

    # 2. Get CIRIS internal data
    ciris_data = await self._get_ciris_access_package(user_id)

    # 3. Get external SQL data from all connectors
    for connector in sql_connectors:
        external_data = await tool_bus.execute_tool(
            "sql_export_user",
            {
                "connector_id": connector["connector_id"],
                "user_identifier": user_id,
                "identifier_type": "email"
            }
        )
        # Merge with CIRIS data

    # 4. Return aggregated package
    return DSARAccessPackage(...)
```

## Multi-Connector Support

The service supports multiple SQL connectors through the connector_id parameter:

```python
# Initialize multiple connectors
await sql_service.execute_tool(
    "initialize_sql_connector",
    {
        "connector_id": "production_db",
        "connection_string": "postgresql://...",
        "dialect": "postgresql"
    }
)

await sql_service.execute_tool(
    "initialize_sql_connector",
    {
        "connector_id": "analytics_db",
        "connection_string": "mysql://...",
        "dialect": "mysql"
    }
)

# Route operations to specific connector via connector_id parameter
result1 = await sql_service.execute_tool(
    "sql_export_user",
    {"connector_id": "production_db", "user_identifier": "user@example.com", "identifier_type": "email"}
)

result2 = await sql_service.execute_tool(
    "sql_export_user",
    {"connector_id": "analytics_db", "user_identifier": "user@example.com", "identifier_type": "email"}
)
```

**Note:** Currently each SQLToolService instance handles one connector at a time. The service validates that the connector_id in the request matches its configured connector. For true multi-connector support, deploy multiple SQLToolService instances with different connector configurations.

## Security Considerations

1. **Privacy Schema Required** - Cannot query arbitrary tables without privacy schema
2. **WiseAuthority Approval** - Raw SQL queries should require WA approval
3. **Connection Security** - Use SSL/TLS for production databases
4. **Secret Management** - Store connection strings in SecretsService
5. **Transaction Safety** - All delete/anonymize operations use transactions
6. **Verification** - Post-deletion verification with cryptographic proof
7. **Runtime Reconfiguration** - initialize_sql_connector allows dynamic updates without restart

## TODO

- [ ] Integrate with AuditService for Ed25519 signatures on verification
- [ ] Add privacy constraint enforcement for raw queries
- [ ] Add connection pooling configuration
- [ ] Add support for additional dialects (SQL Server, Oracle)
- [ ] Add batch operations for large datasets
- [ ] Add progress tracking for long-running operations
- [ ] Add GraphNode caching for query results (use existing MemoryBus)
- [ ] Add GraphEdge identity resolution (use existing MemoryBus)

## Standards Compliance

- **ODBC** - ISO/IEC 9075 (SQL standard)
- **SQLAlchemy** - Database abstraction layer
- **GDPR** - Articles 15 (Access), 16 (Correction), 17 (Erasure), 20 (Portability)
- **Ed25519** - Cryptographic proof of deletion

## File Structure

```
ciris_adapters/external_data_sql/
├── manifest.json          # Service declaration
├── protocol.py            # SQLDataSourceProtocol
├── schemas.py             # Pydantic models
├── service.py             # SQLToolService implementation
├── __init__.py            # Package exports
└── README.md              # This file
```

## Dependencies

- **sqlalchemy** >=2.0.0,<3.0.0 - Database abstraction
- **pyodbc** >=5.0.0,<6.0.0 - ODBC driver (optional, dialect-specific)
- **pymysql** - MySQL driver (install separately if needed)
- **psycopg2** - PostgreSQL driver (install separately if needed)

## Key Features

- **Runtime Configuration** - Dynamic connector initialization via initialize_sql_connector tool
- **Metadata Discovery** - Query connector capabilities via get_sql_service_metadata tool
- **Generic Tool Names** - Tools use sql_* prefix with connector_id parameter for routing
- **Multi-Connector Ready** - Architecture supports multiple connectors via connector_id routing
- **Full DSAR Support** - Find, export, delete, anonymize, verify deletion
- **Privacy Schema** - YAML-based PII mapping for compliant operations
- **Dialect Aware** - Specialized handling for SQLite, MySQL, PostgreSQL
- **Transaction Safety** - All write operations use database transactions
- **Cryptographic Verification** - Ed25519 proof of deletion (when integrated with AuditService)

## Lines of Code

- **manifest.json**: 56 lines
- **schemas.py**: 188 lines
- **protocol.py**: 111 lines
- **service.py**: 1162 lines (includes runtime initialization tools)
- **dialects/**: 374 lines (dialect-specific implementations)
- **privacy_schema_loader.py**: 197 lines
- **__init__.py**: 35 lines
- **Total**: ~2123 lines (excluding service_old.py and tests)

Follows organic architecture - no new abstractions, just tool implementations using existing primitives.
