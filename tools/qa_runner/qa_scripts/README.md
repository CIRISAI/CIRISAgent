# QA Scripts for CIRIS API v1.0

This directory contains Quality Assurance test scripts for the CIRIS API v1.0.

## Prerequisites

- Python 3.12+
- httpx library (`pip install httpx --break-system-packages`)
- Running CIRIS API server (local or containerized)

## Available Scripts

### qa_v1.0_sdk_comprehensive.py
**Purpose**: Comprehensive QA test suite using direct httpx SDK implementation

**Coverage**:
- Authentication and authorization
- Agent status and interaction
- Telemetry (OTEL) system
- Memory system (store, query, forget)
- Tools endpoint with Discord adapter verification
- Consent system
- Audit system
- System health checks
- Transparency endpoints

**Usage**:
```bash
# Run against local API (port 8000)
python qa_scripts/qa_v1.0_sdk_comprehensive.py

# To test a different port, edit the script's base_url variable
```

**Expected Results**:
- 18 total tools (with Discord adapter)
- 4 tool providers
- 36/40 services online (4 Discord services unhealthy with fake token)
- All key endpoints operational

### qa_v1.0_unhealthy_services_check.py
**Purpose**: Diagnose which services are unhealthy and why

**Usage**:
```bash
python qa_scripts/qa_v1.0_unhealthy_services_check.py
```

**Output**:
- Lists all healthy services
- Details on unhealthy services including errors
- Service registry information

## Running with Docker

### Build QA Container
```bash
docker build -t ciris-qa:latest -f- . <<'EOF'
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc git && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1
ENV MOCK_LLM=true
EXPOSE 8000
CMD ["python", "main.py", "--adapter", "api", "--adapter", "discord", "--mock-llm", "--host", "0.0.0.0", "--port", "8000"]
EOF
```

### Run Container
```bash
# With both API and Discord adapters
docker run -d --name ciris-qa \
  -p 8005:8000 \
  -e DISCORD_BOT_TOKEN="MTIzNDU2Nzg5MDEyMzQ1Njc4OQ.FakeToken.ThisIsNotARealTokenJustForTesting123" \
  ciris-qa:latest
```

### Run QA Tests
```bash
# Update base_url in script to http://localhost:8005
python qa_scripts/qa_v1.0_sdk_comprehensive.py
```

## Key Fixes Verified (as of 2025-08-22)

1. **Discord Tools Loading**: All 10 Discord tools now load correctly with async/await fix
2. **Memory Endpoint Import**: Fixed import path from non-existent module to correct path
3. **Tools Endpoint Metadata**: Added provider count, provider list, and total tools to metadata
4. **Test Coverage**: Fixed failing tests after removing hardcoded uptime values

## CI/CD Integration

These scripts can be integrated into CI/CD pipelines for automated testing:

```yaml
# Example GitHub Actions step
- name: Run QA Tests
  run: |
    docker run -d --name ciris-test -p 8000:8000 ciris-qa:latest
    sleep 30  # Wait for startup
    python qa_scripts/qa_v1.0_sdk_comprehensive.py
```

## Default Credentials

- Username: `admin`
- Password: `ciris_admin_password`
- Role: `SYSTEM_ADMIN`

## Notes

- Discord services will show as unhealthy when using a fake token (expected behavior)
- Memory system requires proper GraphNode format with id, type, scope, and attributes
- Consent endpoints may need additional implementation
- All timestamps are in ISO format with timezone info
