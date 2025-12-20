# Plan: DSAR Orchestration Refactor

This plan follows the Test-Driven Development (TDD) workflow and includes phase completion checkpoints.

## Phase 1: Foundation and Models

- [x] **Task 1: Define Pydantic Schemas for DSAR** (2082b0b)
  - [ ] Write tests for DSAR request and response schemas.
  - [ ] Implement schemas in `ciris_engine/schemas/dsar.py`.
- [x] **Task 2: Define DSAR Orchestrator Interface** (6e43beb)
  - [ ] Write unit tests for the orchestrator interface (mocking dependencies).
  - [ ] Create the `DsarOrchestrator` class in `ciris_engine/logic/dsar_orchestrator.py`.
- [x] **Task: Conductor - User Manual Verification 'Foundation and Models' (Protocol in workflow.md)** [checkpoint: 46ae868]

## Phase 2: Core Orchestration Logic

- [ ] **Task 3: Implement Data Discovery Logic**
  - [ ] Write tests for multi-table/multi-db discovery.
  - [ ] Implement `find_user_data` logic using SQL tools.
- [ ] **Task 4: Implement Export and Deletion Logic**
  - [ ] Write tests for JSON/CSV export and permanent deletion.
  - [ ] Implement `export_user_data` and `delete_user_data`.
- [ ] **Task 5: Implement Verification and Audit Signing**
  - [ ] Write tests for Ed25519-signed verification reports.
  - [ ] Implement `verify_deletion` and audit logging integration.
- [ ] **Task: Conductor - User Manual Verification 'Core Orchestration Logic' (Protocol in workflow.md)**

## Phase 3: Integration and Consolidation

- [ ] **Task 6: Migrate Existing DSAR Endpoints**
  - [ ] Write integration tests for the new orchestrator via API.
  - [ ] Update existing API routes to use the `DsarOrchestrator`.
- [ ] **Task 7: Final Cleanup and Documentation**
  - [ ] Remove deprecated DSAR code and update internal documentation.
- [ ] **Task: Conductor - User Manual Verification 'Integration and Consolidation' (Protocol in workflow.md)**
