# Security Policy

## Supported Versions

**2.6.3+ is required.** Earlier versions have known security issues that are resolved in 2.6.3:

| Version | Status | Notes |
|---------|--------|-------|
| 2.6.3+  | ✅ Supported | Comprehensive security hardening, native encryption support (CIRISVerify 1.6+), Ed25519 audit chain verification, service token revocation |
| 2.6.0–2.6.2 | ⚠️ Upgrade required | iOS jetsam/crash fixes, SQLite threading fixes, but missing hardening from 2.6.3 |
| < 2.6.0 | ❌ Unsupported | Known vulnerabilities in authentication, audit chain, and adapter isolation |


## Reporting a Vulnerability

email info@ciris.ai to report vulnerabilities

We ask 2 weeks before public disclosure to responsibly patch the gap and notify users

If the gap is in life safety, encryption, or redaction systems, we ask for an additional 2 weeks before any release occurs to give us a chance to ensure updates are deployed and users notified.

Thank you for helping us secure CIRIS
