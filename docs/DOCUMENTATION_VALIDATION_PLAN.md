# Documentation Validation Plan - Bottom-Up Approach

## Overview

This plan outlines a systematic bottom-up approach to validate and maintain CIRIS documentation accuracy. Starting from the lowest-level implementation files and working up to high-level architecture documents ensures ground truth accuracy.

## Validation Hierarchy

### Level 1: Implementation Files (Ground Truth)
These are the source of truth - code never lies.

1. **Service Implementations** (`ciris_engine/logic/services/`)
   - Count actual services
   - Verify service categories
   - Check implemented methods

2. **Protocol Definitions** (`ciris_engine/protocols/`)
   - Verify protocol-implementation match
   - Check inheritance hierarchy
   - Validate method signatures

3. **Schema Definitions** (`ciris_engine/schemas/`)
   - Count schema directories
   - Verify type definitions
   - Check for Dict[str, Any] usage

4. **Handler Implementations** (`ciris_engine/logic/handlers/`)
   - Verify all 10 handlers exist
   - Check handler categories
   - Validate action mappings

### Level 2: Module Documentation
Documentation within code directories.

1. **Service READMEs** (`*/services/*/README.md`)
   - Match implementation details
   - Update API examples
   - Remove aspirational features

2. **Protocol READMEs** (`*/protocols/*/README.md`)
   - Verify file references
   - Update counts and categories
   - Fix import paths

3. **Schema READMEs** (`*/schemas/*/README.md`)
   - Document actual directories
   - Update type examples
   - Remove version references

### Level 3: System Documentation
High-level architecture and design docs.

1. **CLAUDE.md** (Developer guidance)
   - Verify service counts
   - Update architecture claims
   - Check code examples

2. **README.md** (Project overview)
   - Validate performance claims
   - Update feature status
   - Fix architecture diagrams

3. **Architecture Docs** (`docs/architecture/`)
   - Verify component counts
   - Update service categories
   - Fix dependency graphs

### Level 4: Integration Documentation
Cross-cutting concerns and workflows.

1. **API Documentation** (`docs/api/`)
   - Verify endpoint counts
   - Update request/response schemas
   - Check authentication flows

2. **Deployment Guides** (`deployment/`)
   - Validate resource requirements
   - Update configuration examples
   - Check docker-compose files

3. **Test Documentation** (`tests/README.md`)
   - Update test counts
   - Verify coverage claims
   - Document test categories

## Validation Process

### Step 1: Inventory (Automated)
```bash
# Count services
find ciris_engine/logic/services -name "*.py" -type f | grep -E "(service|Service)" | wc -l

# Count protocols
find ciris_engine/protocols/services -name "*.py" -type f | wc -l

# Count schemas
find ciris_engine/schemas -type d | wc -l

# Find Dict[str, Any] usage
grep -r "Dict\[str, Any\]" ciris_engine/ --include="*.py" | grep -v test | wc -l
```

### Step 2: Cross-Reference
1. Create a source-of-truth table:
   - Service name | Category | Protocol file | Implementation file | Documented?
2. Identify discrepancies
3. Flag outdated documentation

### Step 3: Update Documentation
1. Start with Level 1 files (never change implementation to match docs)
2. Update Level 2 based on Level 1
3. Update Level 3 based on Levels 1-2
4. Update Level 4 based on all previous levels

### Step 4: Validation Rules

#### Rule 1: Count Consistency
- All service counts must be 22
- All handler counts must be 10
- Schema directory count must match LS output

#### Rule 2: Category Consistency
- Graph Services: 6
- Infrastructure: 7
- Governance: 4
- Runtime: 3
- Tool: 1

#### Rule 3: No Aspirational Content
- Remove "planned features"
- Remove "future enhancements"
- Document only what exists

#### Rule 4: API Examples Must Work
- Test all code examples
- Verify import paths
- Check method signatures

## Maintenance Schedule

### Daily
- Check for new services/handlers/schemas
- Validate recent PRs for doc updates

### Weekly
- Run full validation script
- Update any drift
- Check for new Dict[str, Any]

### Monthly
- Deep review of architecture docs
- Update performance metrics
- Refresh API documentation

### Quarterly
- Full bottom-up validation
- Update all examples
- Architecture diagram refresh

## Red Flags

These indicate documentation drift:
1. Service count != 22 anywhere
2. "Coming soon" or "planned" features
3. Import paths that don't exist
4. Code examples that don't run
5. Performance claims without data
6. Dict[str, Any] in examples
7. Version numbers in paths
8. Non-existent file references

## Validation Tools

### ciris_doc_validator.py
```python
"""
Automated documentation validator.
Checks counts, paths, and consistency.
"""
# Implementation to be created
```

### validate_examples.py
```python
"""
Tests all code examples in documentation.
Ensures they compile and run.
"""
# Implementation to be created
```

## Success Metrics

1. **Accuracy**: 100% of counts match implementation
2. **Currency**: No documentation >30 days out of date
3. **Executability**: 100% of code examples run
4. **Completeness**: All components documented
5. **Consistency**: No conflicting information

## Current Status (July 2025)

### Completed Updates
- [x] protocols/README.md - Updated to 22 services
- [x] schemas/README.md - Documented 24 directories
- [x] handler protocols/README.md - Removed non-existent files
- [x] memory service/README.md - Removed aspirational features
- [x] service protocols/README.md - Fixed categorizations

### Validation Results
- Service count: Verified 22 services
- Dict[str, Any] count: 216 instances (README claim of 0 is false)
- Schema directories: 24 (verified by LS)
- Handler count: 10 (verified)
- API endpoints: 78 (verified)

### Next Steps
1. Create automated validation scripts
2. Update main README.md claims
3. Fix Dict[str, Any] count claim
4. Update performance benchmarks with real data
5. Create documentation update checklist for PRs
