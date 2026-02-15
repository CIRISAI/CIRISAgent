#!/bin/bash
# Start CIRIS with live LLM for HE-300 benchmark
# This script properly cleans data and starts with a fresh state
set -e

cd /home/emoore/CIRISAgent

echo "=== CIRIS HE-300 Benchmark Server ==="

# Step 1: Kill any existing CIRIS processes
echo "[1/5] Stopping any existing CIRIS processes..."
pkill -f "python3 main.py" 2>/dev/null || true
sleep 2

# Step 2: Clean database files for fresh benchmark run
echo "[2/5] Cleaning databases for fresh benchmark run..."
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p data/backup
if [ -f data/ciris_engine.db ]; then
    mv data/ciris_engine.db "data/backup/ciris_engine_${TIMESTAMP}.db"
    echo "  - Backed up ciris_engine.db"
fi
if [ -f data/ciris_audit.db ]; then
    mv data/ciris_audit.db "data/backup/ciris_audit_${TIMESTAMP}.db"
    echo "  - Backed up ciris_audit.db"
fi
# Keep secrets.db (contains API keys etc)

# Step 3: Set environment variables
echo "[3/5] Setting benchmark environment..."
export CIRIS_BENCHMARK_MODE=true
export CIRIS_TEMPLATE=he-300-benchmark
export CIRIS_LLM_PROVIDER=openai
export OPENAI_API_KEY=$(grep -E "^OPENAI_API_KEY=" .env | cut -d= -f2-)
export OPENAI_API_BASE=https://api.openai.com/v1
export OPENAI_MODEL=gpt-4o-mini

# Step 4: Verify configuration
echo "[4/5] Verifying configuration..."
echo "  - LLM Provider: ${CIRIS_LLM_PROVIDER}"
echo "  - Model: ${OPENAI_MODEL}"
echo "  - API Key: ${OPENAI_API_KEY:0:15}..."
echo "  - Template: ${CIRIS_TEMPLATE}"

# Step 5: Start server
echo "[5/5] Starting CIRIS benchmark server..."
echo ""
echo "Endpoints:"
echo "  - API:  http://localhost:8000"
echo "  - A2A:  http://localhost:8100"
echo "  - Health: curl http://localhost:8100/health"
echo ""
python3 main.py --adapter api --adapter a2a --template he-300-benchmark --port 8000 2>&1
