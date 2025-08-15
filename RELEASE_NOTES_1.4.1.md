# Release Notes - v1.4.1

**Release Date**: January 15, 2025
**Version**: 1.4.1-beta
**Codename**: Graceful Guardian

## 🚀 Major Changes

### Removed CIRISGUI
- Simplified architecture by removing the GUI component
- Reduced complexity and maintenance burden
- Focus on core agent functionality

### Improved Test Coverage
- **Coverage increased from 55.3% to 62.5% (+7.2%)**
- Added 17 comprehensive runtime tests
- Fixed CI-only test failures
- All 1,648 tests passing

## 🐛 Bug Fixes

### Runtime Initialization
- Fixed runtime marking as initialized even on failure
- Improved error handling throughout initialization process

### Test Stability
- Fixed template file issue in CI tests
- Fixed flaky password generation test
- Made password generation deterministically secure

### Grace CI Shepherd
- Enhanced UX for CI monitoring
- Better progress indicators and status reporting

## 🔧 CI/CD Improvements

### Docker Image Tagging
- Fixed issue where `latest` tag wasn't updating to new versions
- Added version extraction from constants.py during build
- Now tags images with both version number and `latest`
- Added manual workflow to update `latest` tag when needed

### Deployment Pipeline
- Improved deployment reliability
- Better handling of image versioning
- Ensures deployments pull correct version

## 📊 Metrics

- **Test Coverage**: 62.5% (target: 80%)
- **Tests**: 1,648 (all passing)
- **Build Time**: ~12-15 minutes
- **Docker Image Size**: Optimized

## 🔄 Breaking Changes

None - This is a patch release with backward compatibility.

## 📝 Known Issues

- Coverage still below 80% target
- Some Dict[str, Any] violations remain (173 occurrences)
- SonarCloud showing 8 vulnerabilities (3 high, 2 moderate, 3 low)

## 🎯 Next Steps

- Continue improving test coverage toward 80% target
- Address remaining type safety violations
- Resolve SonarCloud security vulnerabilities
- Implement wisdom extension system (v1.4.2)

## 📦 Installation

```bash
docker pull ghcr.io/cirisai/ciris-agent:1.4.1-beta
# or
docker pull ghcr.io/cirisai/ciris-agent:latest
```

## 🙏 Contributors

- Eric Moore (@emooreatx)
- CIRIS L3C Team

---

*For questions or issues, please visit: https://github.com/CIRISAI/CIRISAgent/issues*
