# Tools Consolidation Plan

## Proposed Organization Under tools/

### 1. Development Tools (tools/dev/)
**Grace & Pre-commit:**
- grace.py → tools/dev/grace.py
- grace_precommit.py → tools/dev/grace_precommit.py  
- grace_shared.py → tools/dev/grace_shared.py
- grace/ (directory) → Keep in tools/grace/ (already organized)

**Version & Git Management:**
- bump_version.py → tools/dev/bump_version.py
- smart_commit.sh → tools/dev/smart_commit.sh
- check_no_main_push.sh → tools/dev/check_no_main_push.sh
- check_version_reminder.sh → tools/dev/check_version_reminder.sh

**Code Quality:**
- audit_dict_any_usage.py → tools/quality/audit_dict_any_usage.py
- analyze_orphans.py → tools/quality/analyze_orphans.py
- generate_protocols.py → tools/dev/generate_protocols.py
- validate_prod_routes.py → tools/quality/validate_prod_routes.py
- scripts/run_ci_checks.sh → tools/dev/run_ci_checks.sh

### 2. Template & Security Tools (tools/templates/)
**Template Management:**
- scripts/generate-template-manifest.py → tools/templates/generate_manifest.py
- scripts/generate-template-manifest.sh → tools/templates/generate_manifest.sh
- scripts/utilities/generate-template-manifest.py → DUPLICATE - DELETE
- validate_schema.py (from root) → tools/templates/validate_templates.py

**Security & Signing:**
- scripts/security/generate_root_wa_keypair.py → tools/security/generate_wa_keypair.py
- scripts/security/sign_wa_mint.py → tools/security/sign_wa_mint.py

### 3. API & Testing Tools (tools/testing/)
**API Testing:**
- api_telemetry_tool.py → Keep in tools/ (frequently used)
- scripts/ciris_api_test.py → tools/testing/api_test.py
- scripts/ciris_api_auth.sh → tools/testing/api_auth.sh
- scripts/test_adapters.py → tools/testing/test_adapters.py
- scripts/utilities/quick_test.sh → tools/testing/quick_test.sh

**QA Runner:**
- qa_runner/ → Keep as tools/qa_runner/ (already organized)

**Test Tool:**
- test_tool/ → Keep as tools/test_tool/ (already organized)

### 4. Database Tools (tools/database/)
**DB Management:**
- db_status_tool.py → tools/database/status.py
- debug_tools.py → tools/database/debug.py
- ciris_db → tools/database/ciris_db
- ciris_db_tools/ → tools/database/ciris_db_tools/

**TSDB Operations:**
- scripts/tsdb/consolidate_period.py → tools/database/tsdb_consolidate_period.py
- scripts/tsdb/manual_consolidate.py → tools/database/tsdb_manual_consolidate.py
- scripts/tsdb/validate_and_delete.py → tools/database/tsdb_validate_delete.py

**Maintenance:**
- scripts/maintenance/force_edge_recalc.py → tools/database/force_edge_recalc.py
- scripts/maintenance/run_period_consolidation.py → tools/database/run_consolidation.py

### 5. Operations Tools (tools/ops/)
**Deployment:**
- check_deployment.py → tools/ops/check_deployment.py
- scripts/deployment/deploy.sh → tools/ops/deploy.sh
- scripts/deployment/monitor-current-deployment.sh → tools/ops/monitor_deployment.sh
- scripts/update_latest_tag.sh → tools/ops/update_latest_tag.sh

**Admin & Config:**
- reset_admin_password.py → tools/ops/reset_admin_password.py
- scripts/register_discord_from_env.sh → tools/ops/register_discord.sh
- scripts/utilities/register_discord_adapter.py → tools/ops/register_discord_adapter.py

### 6. Analysis Tools (tools/analysis/)
**Telemetry & Monitoring:**
- telemetry_analyzer.py → tools/analysis/telemetry_analyzer.py
- get_prometheus.py → tools/analysis/get_prometheus.py
- audit_ciris_system.py → tools/analysis/audit_system.py
- investigate_guidance_bug.py → tools/analysis/investigate_guidance.py

**Quality Analysis:**
- sonar.py → tools/analysis/sonar.py
- sonar_tool/ → tools/analysis/sonar_tool/
- quality_analyzer/ → Keep as tools/quality_analyzer/ (already organized)

**Type Checking:**
- ciris_mypy_toolkit/ → Keep as tools/ciris_mypy_toolkit/ (already organized)

## Files to Delete (Duplicates)
- scripts/utilities/generate-template-manifest.py (duplicate of scripts/generate-template-manifest.py)

## TODO List by Category

### Category 1: Create Directory Structure
- [ ] Create tools/dev/
- [ ] Create tools/templates/
- [ ] Create tools/security/
- [ ] Create tools/testing/
- [ ] Create tools/database/
- [ ] Create tools/ops/
- [ ] Create tools/analysis/
- [ ] Create tools/quality/

### Category 2: Move Development Tools
- [ ] Move grace files to tools/dev/
- [ ] Move version management scripts to tools/dev/
- [ ] Move git hooks to tools/dev/
- [ ] Move code quality tools to tools/quality/

### Category 3: Move Template & Security Tools
- [ ] Move template generation scripts to tools/templates/
- [ ] Move validate_schema.py from root to tools/templates/
- [ ] Move security scripts to tools/security/
- [ ] Update template manifest generation paths

### Category 4: Move Testing Tools
- [ ] Move API test scripts to tools/testing/
- [ ] Move adapter tests to tools/testing/
- [ ] Keep api_telemetry_tool.py in tools/ root (frequently used)

### Category 5: Move Database Tools
- [ ] Move db tools to tools/database/
- [ ] Move TSDB scripts to tools/database/
- [ ] Move maintenance scripts to tools/database/
- [ ] Consolidate debug_tools.py with db tools

### Category 6: Move Operations Tools  
- [ ] Move deployment scripts to tools/ops/
- [ ] Move admin tools to tools/ops/
- [ ] Move Discord registration to tools/ops/

### Category 7: Move Analysis Tools
- [ ] Move telemetry analysis to tools/analysis/
- [ ] Move audit tools to tools/analysis/
- [ ] Move sonar.py to tools/analysis/

### Category 8: Update References
- [ ] Update CIRIS_TEMPLATE_GUIDE.md with correct tool paths
- [ ] Update any shell scripts that reference scripts/
- [ ] Update documentation that mentions scripts/
- [ ] Update .gitignore if needed

### Category 9: Cleanup
- [ ] Delete scripts/utilities/generate-template-manifest.py (duplicate)
- [ ] Remove empty scripts/ directories
- [ ] Update tools/README.md with new organization

## Benefits of This Organization

1. **Clear Categories**: Each subdirectory has a clear purpose
2. **No Duplication**: Eliminates duplicate files
3. **Easier Discovery**: Developers can find tools by category
4. **Consistent Naming**: Simplified, descriptive names
5. **Frequently Used**: Keep frequently used tools (api_telemetry_tool.py, grace/) at root or well-organized
6. **Preserve Working Structure**: Keep already-organized dirs (qa_runner/, test_tool/, etc.)