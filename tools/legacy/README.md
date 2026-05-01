# tools/legacy/

Scripts kept for one release after their replacement landed, then deleted.

| Script | Replaced by | Deprecated in | Delete in |
|---|---|---|---|
| `register_agent_build.py` | `ciris-build-sign --tree` (CIRISVerify v1.8.1) + `tools/ops/register_signed_manifest.py` | 2.7.8.4 | 2.7.9 |

## Why this dir exists

When a tool is replaced — especially a CI/build tool — there's value in keeping
the old version visible alongside the new one for one release. Operators
debugging a CI regression can `diff` against the working historical version
without spelunking through git history. Reviewers can audit the migration as
a focused diff (old script → legacy/ + new wrapper added) rather than as
"where did this code go?"

After one release, the legacy copy is removed. The history is preserved in
git; the working tree stays clean.

## Migration: register_agent_build.py → ciris-build-sign + register_signed_manifest.py

Migrated 2026-05-01 in 2.7.8.4 (issue #707). The legacy 538-line monolith
combined three concerns:

1. File-tree manifest generation (per-file SHA-256, EXEMPT_DIRS, EXEMPT_EXTENSIONS)
2. Manifest signing
3. Registry gRPC push (RegisterBuild RPC)

Concerns 1+2 moved to `ciris-build-sign --tree` (CIRISVerify v1.8.1, with
hybrid Ed25519 + ML-DSA-65 signing). Concern 3 — registry-client wrapper —
stayed in this repo as `tools/ops/register_signed_manifest.py` (~80 lines,
focused). The agent-specific build-secrets-hash dict moved to
`tools/ops/build_agent_extras.py` so the release-build secret tracking has
a single, version-controlled home.

CI now runs:

```bash
python tools/ops/build_agent_extras.py > build-secrets.json
ciris-build-sign sign --primitive agent --tree . ... --output build-manifest.json
python tools/ops/register_signed_manifest.py build-manifest.json --modules core
```

…instead of the historical:

```bash
python tools/ops/register_agent_build.py --build . --modules core
```

See `.github/workflows/build.yml` for the live CI configuration and
`CHANGELOG.md` 2.7.8.4 entry for the full migration writeup.
