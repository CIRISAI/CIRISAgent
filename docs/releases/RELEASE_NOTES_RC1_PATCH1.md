# Release Notes - v1.0.1-RC1-patch1

## Release Overview
**Version**: 1.0.1-RC1-patch1
**Codename**: Stable Foundation
**Branch**: 1.0-RC1-patch1
**Date**: August 25, 2025

This branch contains the RC1 release plus comprehensive testing infrastructure and bug fixes. It includes 23 commits not yet in main.

## 📊 What's in this branch vs main
- **Total Commits**: 23 (includes QA runner system from before + today's fixes)
- **Total Changes**: 57 files changed, 7,910 insertions(+), 126 deletions(-)
- **Major Addition**: Complete QA testing framework (~7,500 lines)
- **Today's Work**: 8 commits with ~570 insertions, 206 deletions

## 🎯 Major Components (vs main)

### 1. QA Testing Framework (Already in branch)
The bulk of the changes (~7,500 lines) come from the comprehensive QA runner system that was added earlier:
- **Modular QA Runner** (`tools/qa_runner/`)
- **API test modules** with 60+ test cases
- **Handler testing** infrastructure
- **SDK integration tests**
- **Comprehensive unit tests** for CLI tools, AuditVerifier, BaseGraphService
- **Docker-based test execution**

### 2. Today's Improvements (8 commits)
- **Moved QA runner** from root to `tools/qa_runner/` directory
- **Added consent module** to QA runner
- **Reduced log spam** - Changed debug logs from INFO to DEBUG level
- **Added reverse proxy support** - FastAPI root_path configuration
- **Added test coverage** - 3 small tests to meet SonarCloud requirements
- **Fixed test bug** - Corrected method name in telemetry aggregator test
- **Code cleanup** - Eliminated duplication in consent.py

## 🐛 Bug Fixes in this branch

### From earlier QA work:
- Fixed all 5 tool services to handle unknown tools properly
- Fixed Docker permission issues
- Fixed API test endpoints and adapter tools validation
- Removed duplicate tool execution counter increment
- Fixed test payload issues

### From today:
- Fixed telemetry aggregator test (wrong method name)
- Reduced log spam in production
- Fixed QA runner server path

## 🔧 Technical Improvements

### Testing & Quality
- Complete QA runner system with parallel execution
- JSON/HTML report generation
- Automated server lifecycle management
- Coverage improvements to pass SonarCloud gate

### Production Support
- FastAPI root_path for reverse proxy deployments
- Environment variable detection for managed mode
- Cleaner logs with proper debug levels
- Better code organization (moved test files to tools/)

## 📝 Configuration Changes

### New Environment Variables
- `CIRIS_AGENT_ID` - Auto-configures proxy path
- `CIRIS_PROXY_PATH` - Explicit proxy path override

## 📋 All Commits in Branch (vs main)

The 23 commits unique to this branch:

### QA Framework & Tests (earlier work):
- b4421080 test: Add comprehensive test coverage for CLIToolService
- 30c3df51 feat: Add modular QA runner system
- 4a9b9e02 feat: Add handler and SDK test modules
- 29080a5e test: Add comprehensive unit tests
- b00e95a7 feat: Add comprehensive API test module
- 9cf7647c fix: Fix all 5 tool services
- d9e2c480 test: Fix tests to match correct tool service
- 16e33c8f fix: Docker permission issues
- 9106431c fix: Increment tool_executions counter
- 130fb003 fix: Fix API test endpoints
- 75170a20 fix: Fix remaining QA test payload issues
- 665c4f5d fix: Complete QA runner fixes
- 54bb6531 fix: Remove duplicate tool execution counter
- 3032ab9d fix: Remove test_base_graph_service.py

### Today's Work:
- d0fcc7f5 refactor: Eliminate code duplication in consent.py
- a78cbbb2 chore: Move QA runner files from root to tools/qa_runner
- 3c7a1d6c feat: Add consent module to QA runner
- a194d5d5 fix: Reduce log spam
- fd97efe6 feat: Add FastAPI root_path support
- 29d1ed51 test: Add test case for telemetry coverage
- 56df434c test: Add coverage for proxy path and consent
- a0b7912e fix: Correct method name in telemetry test
- 39b264cf docs: Add release notes

## Summary

This branch represents the RC1 release with a massive testing infrastructure addition (the QA runner system) plus production-ready improvements. The branch is ready for merge to main, bringing comprehensive testing capabilities and several quality-of-life improvements for production deployments.

---

*Note: This branch should be merged to main to bring in the QA testing framework and all associated fixes.*
