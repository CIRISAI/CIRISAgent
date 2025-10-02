#!/bin/bash

# Start server
python main.py --adapter api --mock-llm --port 8000 &
SERVER_PID=$!

# Wait for server
sleep 30

# Get token
TOKEN=$(curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"ciris_admin_password"}' 2>/dev/null | \
  python -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

echo "Testing SSE endpoint..."
curl -N -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/v1/system/runtime/reasoning-stream 2>&1 | head -20

# Cleanup
kill $SERVER_PID
