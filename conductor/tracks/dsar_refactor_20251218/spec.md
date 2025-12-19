# Spec: DSAR Orchestration Refactor

## 1. Goal
Consolidate and refactor the Data Subject Access Request (DSAR) orchestration logic into a centralized, Pydantic-validated service within the 22-service architecture.

## 2. Context
The current DSAR implementation is spread across multiple modules and needs to be unified under the `governance` service category. It must use the standard H3ERE pipeline and provide Ed25519-signed audit trails for all operations.

## 3. Requirements
- **Centralization:** Move all DSAR-related logic to a unified `DsarOrchestrator` service.
- **Validation:** Use Pydantic models for all inputs, outputs, and internal state.
- **Auditability:** Every step (find, export, delete, verify) must generate a signed audit entry.
- **Compliance:** Ensure compatibility with GDPR/DSAR requirements as outlined in the project's comprehensive guide.
- **Integration:** Support SQLite, PostgreSQL, and MySQL through the SQL External Data Service.

## 4. Architecture
- **Service:** Part of the `governance` service category.
- **Buses:** Interacts with `CommunicationBus` (for notifications) and `MemoryBus` (for audit logging).
- **Tools:** Utilizes the 9 SQL tools defined in the comprehensive guide.
