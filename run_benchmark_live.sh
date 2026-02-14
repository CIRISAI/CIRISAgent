#!/bin/bash
# Start CIRIS with live LLM for benchmark
cd /home/emoore/CIRISAgent

export CIRIS_BENCHMARK_MODE=true
export CIRIS_TEMPLATE=he-300-benchmark
export OPENAI_API_KEY=$(grep -E "^OPENAI_API_KEY=" .env | cut -d= -f2-)
export OPENAI_API_BASE=https://api.openai.com/v1
export OPENAI_MODEL=gpt-4o-mini

echo "Starting with API key: ${OPENAI_API_KEY:0:15}..."
python3 main.py --adapter api --adapter a2a --template he-300-benchmark --port 8000 2>&1
