# Multi-stage build for optimized production image
# Stage 1: Build stage with compilation tools
FROM python:3.12-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Runtime stage with minimal dependencies
FROM python:3.12-slim

# Install only runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -m -u 1000 ciris

# Set working directory
WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /root/.local /home/ciris/.local

# Copy application code
COPY --chown=ciris:ciris . .

# Create necessary directories with proper permissions
# Note: .ciris_keys directory will be copied from repo if it exists
RUN mkdir -p /app/data /app/logs /app/audit_keys /app/data_archive && \
    chown -R ciris:ciris /app/data /app/logs /app/audit_keys /app/data_archive && \
    chmod 750 /app/data /app/logs /app/audit_keys /app/data_archive && \
    # Ensure /app directory itself is writable by ciris user for audit_logs.jsonl
    chown ciris:ciris /app && \
    chmod 755 /app

# Switch to non-root user
USER ciris

# Ensure Python packages are in PATH
ENV PATH=/home/ciris/.local/bin:$PATH

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/v1/system/health || exit 1

# Default command
CMD ["python", "main.py"]