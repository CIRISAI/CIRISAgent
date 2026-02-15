#!/bin/bash
# Start CIRIS with Together.ai / Llama-4-Maverick for HE-300 benchmark
set -e

cd /home/emoore/CIRISAgent

echo "=== CIRIS HE-300 Benchmark Server (Llama-4-Maverick) ==="

# Step 1: Kill any existing CIRIS processes
echo "[1/5] Stopping any existing CIRIS processes..."
pkill -f "python3 main.py" 2>/dev/null || true
sleep 2

# Step 2: Clean database files
echo "[2/5] Cleaning databases..."
rm -f data/ciris_engine.db data/ciris_audit.db 2>/dev/null || true

# Step 3: Set environment variables
echo "[3/5] Setting benchmark environment..."
export CIRIS_BENCHMARK_MODE=true
export CIRIS_TEMPLATE=he-300-benchmark
export CIRIS_LLM_PROVIDER=together
export TOGETHER_API_KEY=$(cat ~/.together_key)
export TOGETHER_MODEL=meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8

# Step 4: Verify configuration
echo "[4/5] Verifying configuration..."
echo "  - LLM Provider: ${CIRIS_LLM_PROVIDER}"
echo "  - Model: ${TOGETHER_MODEL}"
echo "  - API Key: ${TOGETHER_API_KEY:0:15}..."

# Step 5: Start server
echo "[5/5] Starting CIRIS benchmark server..."
python3 main.py --adapter api --adapter a2a --template he-300-benchmark --port 8000 2>&1
