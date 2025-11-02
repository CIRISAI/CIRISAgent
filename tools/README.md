# CIRIS Tools Directory

Consolidated development, testing, and operational tools for the CIRIS project.

## Directory Structure

```
tools/
├── analysis/          # System analysis and monitoring
├── database/          # Database and TSDB management
├── dev/              # Development and version control
├── ops/              # Deployment and operations
├── quality/          # Code quality analysis
├── security/         # Security and signing tools
├── templates/        # Template management and validation
├── testing/          # Testing utilities
│
├── ciris_mypy_toolkit/  # Type checking framework
├── grace/               # Development companion
├── qa_runner/           # QA test framework
├── quality_analyzer/    # Coverage analysis
├── test_tool/          # Docker test runner
│
└── api_telemetry_tool.py  # Frequently used telemetry tool
```

## Quick Reference

### Daily Development
- **Grace**: `python -m tools.grace status` - Development companion
- **Version**: `python tools/dev/bump_version.py` - Bump version
- **Pre-commit**: `python tools/dev/grace_precommit.py` - Run pre-commit checks

### Template Management
- **Validate**: `python tools/templates/validate_templates.py` - Validate all templates
- **Sign**: `python tools/templates/generate_manifest.py` - Sign templates and create manifest
- **Generate Keys**: `python tools/security/generate_wa_keypair.py` - Generate Ed25519 keypair

### Testing
- **API Test**: `python tools/testing/api_test.py` - Test API endpoints
- **Quick Test**: `./tools/testing/quick_test.sh` - Run quick tests
- **QA Runner**: `python -m tools.qa_runner` - Comprehensive test suite
- **Docker Tests**: `python -m tools.test_tool test tests/` - Run tests in Docker

### Database Management
- **Status**: `python tools/database/status.py` - Check database status
- **Debug**: `python tools/database/debug.py` - Debug database issues
- **TSDB**: `python tools/database/tsdb_consolidate_period.py` - Consolidate TSDB

### Operations
- **Deploy**: `./tools/ops/deploy.sh` - Deploy to production
- **Monitor**: `./tools/ops/monitor_deployment.sh` - Monitor deployment
- **Reset Admin**: `python tools/ops/reset_admin_password.py` - Reset admin password

### Analysis
- **Telemetry**: `python tools/api_telemetry_tool.py` - Analyze telemetry (kept at root for frequency)
- **Audit**: `python tools/analysis/audit_system.py` - Audit system
- **Sonar**: `python tools/analysis/sonar.py` - SonarCloud analysis

### Code Quality
- **Dict[str, Any]**: `python tools/quality/audit_dict_any_usage.py` - Find Dict[str, Any] usage
- **Orphans**: `python tools/quality/analyze_orphans.py` - Find orphaned code
- **Routes**: `python tools/quality/validate_prod_routes.py` - Validate production routes

## Frequently Used Commands

```bash
# Development workflow
python -m tools.grace morning              # Start day
python -m tools.grace status               # Check status
python tools/dev/bump_version.py patch     # Bump version
git commit -m "message"                    # Grace pre-commit runs automatically

# Testing
python tools/testing/api_test.py           # Test API
python -m tools.qa_runner                  # Full QA suite
python -m tools.test_tool test tests/      # Docker tests

# Templates
python tools/templates/validate_templates.py  # Validate templates
python tools/templates/generate_manifest.py   # Sign templates

# Monitoring
python tools/api_telemetry_tool.py --monitor  # Monitor telemetry
python tools/database/status.py               # Database status
```

## Migration from scripts/

All tools previously in `scripts/` have been consolidated here:
- `scripts/` → `tools/templates/`, `tools/security/`, `tools/testing/`, `tools/ops/`, `tools/database/`
- Organized by function rather than by type
- Simplified naming conventions
- No duplicate files

## Tool Development Guidelines

1. **Placement**: Add new tools to the appropriate subdirectory
2. **Naming**: Use descriptive names without redundant prefixes
3. **Documentation**: Include docstrings and usage examples
4. **Testing**: Add tests in `tests/tools/`
5. **Dependencies**: Update requirements.txt if needed

## Maintenance

- **Grace**: Primary development companion - use for all pre-commit and CI checks
- **QA Runner**: Comprehensive test framework - run before releases
- **Quality Analyzer**: Find test coverage gaps
- **API Telemetry**: Monitor system health
