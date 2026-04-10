FROM python:3.12-slim

# Install dependencies including build tools for psutil
# TPM2 TSS libraries required for CIRISVerify attestation
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    python3-dev \
    libtss2-esys-3.0.2-0t64 \
    libtss2-tcti-device0t64 \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Accept UID/GID as build arguments (default to 1000 for standard Linux user)
ARG USER_UID=1000
ARG USER_GID=1000

# Create a non-root user with the specified UID/GID
RUN groupadd -g ${USER_GID} cirisuser || true && \
    useradd -m -u ${USER_UID} -g ${USER_GID} cirisuser || true

# Copy the requirements file and install dependencies
COPY requirements.txt .
# Try to use pre-compiled wheels first, fall back to building from source
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# Copy the rest of the application code
COPY . .

# Ensure correct ownership
RUN chown -R cirisuser:cirisuser /app

# Switch to non-root user
USER cirisuser

# Default command - will be overridden by docker-compose
CMD ["python", "main.py"]
