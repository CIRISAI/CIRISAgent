# Multi-stage build (2.8.5+):
#   1) `stager` — runs tools.dev.stage_runtime to produce the canonical runtime
#      tree (matches Android Chaquopy bundle, iOS Resources bundle, and the
#      PyPI wheel content byte-for-byte). CIRISVerify's runtime walk produces
#      the same total_hash on every platform → L4 file integrity passes by
#      construction.
#   2) `runtime` — the actual deployed image; carries ONLY the staged tree
#      plus the small set of root-level files the entrypoint needs. No tests,
#      docs, FSDs, .git history, IDE cruft, or build caches.

# ---- Stage 1: stage the canonical runtime ------------------------------------
FROM python:3.12-slim AS stager

WORKDIR /src

# Copy just enough source to run the staging script. We need:
#   - tools/dev/stage_runtime.py (the algorithm)
#   - tools/__init__.py + tools/dev/__init__.py (so it's importable as a package)
#   - the include_roots: ciris_engine, ciris_adapters, ciris_sdk
COPY tools/__init__.py tools/__init__.py
COPY tools/dev tools/dev
COPY ciris_engine ciris_engine
COPY ciris_adapters ciris_adapters
COPY ciris_sdk ciris_sdk

RUN python -m tools.dev.stage_runtime /staged --quiet

# Generate startup_python_hashes.json from the same source tree so the
# bundled JSON's `agent_version` + `total_hash` match the bytes the runtime
# walker will see. Output lives at /src/startup_python_hashes.json (the
# script's hardcoded location); COPY --from=stager picks it up below.
RUN python tools/dev/regenerate_python_hashes.py

# ---- Stage 2: the runtime image ---------------------------------------------
FROM python:3.12-slim AS runtime

# Install dependencies including build tools for psutil
# Using --no-install-recommends to minimize attack surface
# TPM2 TSS libraries required for CIRISVerify attestation
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libtss2-esys-3.0.2-0t64 \
    libtss2-tctildr0t64 \
    libtss2-tcti-device0t64 \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for running the application
RUN useradd --create-home --shell /bin/bash ciris

WORKDIR /app

# Install Python dependencies (as root for system packages).
# Try pre-compiled wheels first, fall back to building from source.
COPY requirements.txt .
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# Copy the canonical staged runtime tree from stage 1. This is the SAME content
# the wheel ships and the mobile bundles ship — every platform carries the
# identical file set, so CIRISVerify file_integrity is byte-stable across
# desktop / Android / iOS / docker.
COPY --from=stager --chown=ciris:ciris /staged /app

# Plus the small root-level set the entrypoint + setup needs at runtime
# (NOT part of the canonical runtime tree, but needed for the container to
# start the agent and report build provenance).
COPY --chown=ciris:ciris main.py /app/main.py
COPY --chown=ciris:ciris setup.py /app/setup.py
COPY --chown=ciris:ciris BUILD_INFO.txt /app/BUILD_INFO.txt
# startup_python_hashes.json is generated inside the stager (above) so it
# always exists in the build context — no optional COPY tricks, no
# dependence on a CI step having run before docker build.
COPY --from=stager --chown=ciris:ciris /src/startup_python_hashes.json /app/startup_python_hashes.json

# Create directories that the app needs to write to
RUN mkdir -p /app/data /app/logs && chown -R ciris:ciris /app/data /app/logs

# Switch to non-root user
USER ciris

# Default command - will be overridden by docker-compose
CMD ["python", "main.py"]
