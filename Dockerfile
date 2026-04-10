FROM python:3.12-slim

# Install dependencies including build tools for psutil
# Using --no-install-recommends to minimize attack surface
# TPM2 TSS libraries required for CIRISVerify attestation
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    python3-dev \
    libtss2-esys-3.0.2-0t64 \
    libtss2-tcti-device0t64 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for running the application
RUN useradd --create-home --shell /bin/bash ciris

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file and install dependencies (as root for system packages)
COPY requirements.txt .
# Try to use pre-compiled wheels first, fall back to building from source
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# Copy the rest of the application code
# Note: .dockerignore excludes sensitive files (.secrets/, *.env, data/, etc.)
COPY --chown=ciris:ciris . .

# Create directories that the app needs to write to
RUN mkdir -p /app/data /app/logs && chown -R ciris:ciris /app/data /app/logs

# Switch to non-root user
USER ciris

# Default command - will be overridden by docker-compose
CMD ["python", "main.py"]
