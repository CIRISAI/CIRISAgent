#!/bin/bash
# =============================================================================
# HE-300 v1.2 Benchmark: CIRIS + Llama-4-Maverick via Together.ai
#
# This script starts both servers and runs 5 benchmark iterations for
# statistical significance.
#
# Requirements:
#   - ~/.together_key contains your Together API key
#   - CIRISBench repo at /home/emoore/CIRISBench
#   - Port 8080 and 8100 available
# =============================================================================

set -e  # Exit on error

RESULTS_DIR="/home/emoore/CIRISAgent/benchmark_results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
TOGETHER_KEY=$(cat ~/.together_key 2>/dev/null || echo "")

# Validate Together key
if [ -z "$TOGETHER_KEY" ]; then
    echo "ERROR: Together API key not found at ~/.together_key"
    exit 1
fi

echo "=============================================="
echo "  HE-300 v1.2 - CIRIS + Llama-4-Maverick"
echo "  5 runs for statistical significance"
echo "=============================================="
echo ""
echo "Starting servers..."

# Kill any existing servers
pkill -f "uvicorn engine.api.main:app" 2>/dev/null || true
pkill -f "main.py.*he-300-benchmark" 2>/dev/null || true
sleep 2

# Clean databases for fresh state
rm -f /home/emoore/CIRISAgent/data/ciris_engine.db 2>/dev/null
rm -f /home/emoore/CIRISAgent/data/ciris_audit.db 2>/dev/null

# Start CIRISBench server using its venv directly
echo "  Starting CIRISBench (port 8080)..."
export LLM_PROVIDER=together
export LLM_MODEL="meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8"
export TOGETHER_API_KEY="$TOGETHER_KEY"
export AUTH_ENABLED=false
cd /home/emoore/CIRISBench
nohup /home/emoore/CIRISBench/.venv/bin/python -m uvicorn engine.api.main:app \
    --host 127.0.0.1 --port 8080 --log-level warning \
    > "$RESULTS_DIR/cirisbench_server.log" 2>&1 &
CIRISBENCH_PID=$!

# Start CIRIS server with Together/Maverick using its venv directly
echo "  Starting CIRIS (port 8100 A2A)..."
cd /home/emoore/CIRISAgent
CIRIS_BENCHMARK_MODE=true \
CIRIS_TEMPLATE=he-300-benchmark \
CIRIS_LLM_PROVIDER=together \
OPENAI_API_BASE="https://api.together.xyz/v1" \
OPENAI_API_KEY="$TOGETHER_KEY" \
CIRIS_LLM_MODEL_NAME="meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8" \
nohup /home/emoore/CIRISAgent/.venv/bin/python main.py \
    --adapter api --adapter a2a --template he-300-benchmark --port 8000 \
    > "$RESULTS_DIR/ciris_maverick.log" 2>&1 &
CIRIS_PID=$!

# Wait for servers to be ready
echo "  Waiting for servers..."
sleep 10

# Verify servers are up
for i in {1..30}; do
    if curl -s http://127.0.0.1:8100/health > /dev/null 2>&1; then
        echo "  CIRIS A2A ready"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "ERROR: CIRIS server failed to start"
        cat "$RESULTS_DIR/ciris_maverick.log" | tail -50
        exit 1
    fi
    sleep 1
done

for i in {1..30}; do
    if curl -s http://127.0.0.1:8080/health > /dev/null 2>&1; then
        echo "  CIRISBench ready"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "ERROR: CIRISBench server failed to start"
        cat "$RESULTS_DIR/cirisbench_server.log" | tail -50
        exit 1
    fi
    sleep 1
done

echo ""
echo "Servers ready. Starting benchmark runs..."

ALL_ACCS=""

for i in 1 2 3 4 5; do
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Run $i of 5"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    RESULT=$(curl -s --max-time 3600 -X POST "http://127.0.0.1:8080/he300/agentbeats/run" \
        -H "Content-Type: application/json" \
        -d '{
            "agent_url": "http://127.0.0.1:8100/a2a",
            "agent_name": "CIRIS + Maverick",
            "model": "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
            "protocol": "a2a",
            "benchmark_version": "1.2",
            "sample_size": 300,
            "concurrency": 5,
            "timeout_per_scenario": 300,
            "timeout": 120,
            "semantic_evaluation": false
        }')

    echo "$RESULT" > "$RESULTS_DIR/ciris_maverick_run${i}_${TIMESTAMP}.json"

    # Parse and display
    ACC=$(echo "$RESULT" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    acc = d.get('accuracy', 0)
    print(f'{acc:.4f}')
except:
    print('0')
")

    ALL_ACCS="$ALL_ACCS $ACC"

    echo "$RESULT" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    acc = d.get('accuracy', 0)
    errs = d.get('errors', 0)
    print(f'  Accuracy: {acc*100:.1f}% (errors: {errs})')
    cats = d.get('categories', {})
    for cat in ['commonsense', 'commonsense_hard', 'deontology', 'justice', 'virtue']:
        if cat in cats:
            c = cats[cat]
            print(f'    {cat:17}: {c.get(\"accuracy\",0)*100:.1f}% ({c.get(\"correct\",0)}/{c.get(\"total\",0)})')
except Exception as e:
    print(f'  Error: {e}')
"

    # Restart CIRIS between runs for clean state
    if [ $i -lt 5 ]; then
        echo "  Restarting CIRIS for clean state..."

        # Kill existing CIRIS process
        kill $CIRIS_PID 2>/dev/null || true
        sleep 2

        # Make sure it's really dead
        pkill -f "main.py.*he-300-benchmark" 2>/dev/null || true
        sleep 3

        # Clean databases
        rm -f /home/emoore/CIRISAgent/data/ciris_engine.db 2>/dev/null
        rm -f /home/emoore/CIRISAgent/data/ciris_audit.db 2>/dev/null

        cd /home/emoore/CIRISAgent

        # Start fresh CIRIS with all env vars
        CIRIS_BENCHMARK_MODE=true \
        CIRIS_TEMPLATE=he-300-benchmark \
        CIRIS_LLM_PROVIDER=together \
        OPENAI_API_BASE="https://api.together.xyz/v1" \
        OPENAI_API_KEY="$TOGETHER_KEY" \
        CIRIS_LLM_MODEL_NAME="meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8" \
        nohup /home/emoore/CIRISAgent/.venv/bin/python main.py \
            --adapter api --adapter a2a --template he-300-benchmark --port 8000 \
            >> "$RESULTS_DIR/ciris_maverick.log" 2>&1 &
        CIRIS_PID=$!

        # Wait for CIRIS to be fully ready
        echo "  Waiting for CIRIS to initialize..."
        sleep 10  # Give it time to start

        for retry in {1..60}; do
            if curl -s http://127.0.0.1:8100/health > /dev/null 2>&1; then
                echo "  CIRIS restarted and healthy"
                sleep 5  # Extra settle time for services
                break
            fi
            if [ $retry -eq 60 ]; then
                echo "  WARNING: CIRIS may not be fully ready"
            fi
            sleep 1
        done
    fi
done

echo ""
echo "=============================================="
echo "  FINAL RESULTS"
echo "=============================================="

python3 -c "
import statistics
accs = [float(x) for x in '$ALL_ACCS'.split() if float(x) > 0]
if len(accs) > 1:
    mean = statistics.mean(accs) * 100
    std = statistics.stdev(accs) * 100
    print(f'CIRIS + Maverick: {mean:.1f}% +/- {std:.1f}%')
    print(f'Runs: {len(accs)}')
    print(f'Individual: {[f\"{a*100:.1f}%\" for a in accs]}')
elif len(accs) == 1:
    print(f'CIRIS + Maverick: {accs[0]*100:.1f}%')
else:
    print('No valid results')
"

# Cleanup
echo ""
echo "Stopping servers..."
kill $CIRIS_PID 2>/dev/null || true
kill $CIRISBENCH_PID 2>/dev/null || true

echo "Done. Results saved to: $RESULTS_DIR"
