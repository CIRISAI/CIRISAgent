#!/bin/bash
# Start CIRIS with benchmark mode

set -a
source .env
set +a

export CIRIS_BENCHMARK_MODE=true
export CIRIS_TEMPLATE=he-300-benchmark

python3 main.py --adapter api --adapter a2a --template he-300-benchmark --port 8000 2>&1
