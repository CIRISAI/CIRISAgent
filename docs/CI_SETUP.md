# CI/CD Setup Guide

This document describes the Continuous Integration setup for the CIRIS Agent project.

## GitHub Actions

The project uses GitHub Actions for automated testing and code quality checks. The workflow is defined in `.github/workflows/ci.yml`.

### Workflow Triggers
- Push to `main` or `develop` branches
- Pull requests targeting `main` branch

### Test Matrix
- Python 3.11 and 3.12
- Full test suite (thousands of tests)
- Code coverage analysis

## SonarQube Integration

### Required GitHub Secrets

To enable SonarQube integration, add these secrets to your GitHub repository:

1. `SONAR_TOKEN` - Your SonarQube token
2. `SONAR_HOST_URL` - Your SonarQube server URL (e.g., `https://sonarcloud.io`)

### Setup Steps

1. **SonarQube Token**:
   - Go to your SonarQube dashboard
   - Navigate to User > My Account > Security > Generate Tokens
   - Create a token and copy it

2. **GitHub Secrets**:
   - Go to your GitHub repository
   - Settings > Secrets and variables > Actions
   - Add the secrets mentioned above

3. **Project Key**:
   - Update `sonar.projectKey` in `sonar-project.properties` if needed
   - Should match your SonarQube project key

## Code Coverage

- **Target**: 80% minimum coverage
- **Reports**: Generated in XML format for SonarQube
- **Location**: `coverage.xml` (included in .gitignore)

## Local Development

### Run CI Checks Locally

```bash
# Make script executable (first time only)
chmod +x scripts/run_ci_checks.sh

# Run all CI checks
./scripts/run_ci_checks.sh
```

### Manual Testing with Coverage

```bash
# Install coverage dependencies
pip install pytest-cov coverage[toml]

# Run tests with coverage
python -m pytest --cov=ciris_engine --cov-report=xml --cov-report=html

# View HTML coverage report
open htmlcov/index.html
```

## Quality Gates

The CI pipeline includes these quality gates:

1. **All tests must pass** (thousands of tests)
2. **Code coverage ≥ 80%**
3. **SonarQube quality gate** (if configured)
4. **No security vulnerabilities** (Bandit scan)

## Files Overview

- `.github/workflows/ci.yml` - Main CI pipeline
- `sonar-project.properties` - SonarQube configuration
- `.coveragerc` - Coverage configuration
- `pytest.ini` - PyTest configuration with coverage
- `scripts/run_ci_checks.sh` - Local CI validation script

## Troubleshooting

### SonarQube Issues
- Verify `SONAR_TOKEN` and `SONAR_HOST_URL` are set correctly
- Check that the project exists in SonarQube
- Ensure the project key matches

### Coverage Issues
- Check that `ciris_engine` directory is present
- Verify all test files are in the `tests/` directory
- Review `.coveragerc` excludes if coverage seems low

### Test Failures
- Run tests locally first: `python -m pytest`
- Check for missing dependencies in `requirements.txt`
- Ensure test database directories exist
