#!/bin/bash
# End-to-end test: Desktop wipe → setup wizard → verify consent partnership
# Usage: bash tools/test_desktop_wipe_setup.sh
set -uo pipefail

API="http://localhost:8091"
BACKEND="http://localhost:8080"
OPENROUTER_KEY=$(cat ~/.openrouter_key)

click() { curl -s -X POST $API/click -H "Content-Type: application/json" -d "{\"testTag\":\"$1\"}" > /dev/null; }
input_text() { curl -s -X POST $API/input -H "Content-Type: application/json" -d "{\"testTag\":\"$1\",\"text\":\"$2\",\"clearFirst\":true}" > /dev/null; }
screen() { curl -s $API/screen 2>/dev/null | python3 -c "import json,sys;print(json.load(sys.stdin).get('screen','DEAD'))" 2>/dev/null || echo "DEAD"; }
screenshot() { curl -s -X POST $API/screenshot -H "Content-Type: application/json" -d "{\"path\":\"$1\"}" > /dev/null; }
wait_screen() {
    local target=$1 timeout=${2:-60}
    for i in $(seq 1 $((timeout/2))); do
        [ "$(screen)" = "$target" ] && return 0
        sleep 2
    done
    echo "TIMEOUT waiting for screen=$target (got $(screen))" >&2
    return 1
}

echo "============================================"
echo "  CIRIS Desktop Wipe + Setup E2E Test"
echo "============================================"

# --- CLEAN START ---
echo "[1/8] Killing existing processes..."
# Kill server processes specifically (avoid matching this script)
for pid in $(lsof -i :8080 -P -t 2>/dev/null); do kill -9 "$pid" 2>/dev/null || true; done
for pid in $(lsof -i :8091 -P -t 2>/dev/null); do kill -9 "$pid" 2>/dev/null || true; done
pkill -9 -f "java.*CIRIS-macos" 2>/dev/null || true
sleep 3
# Wait for ports to free
for i in $(seq 1 15); do
    if ! lsof -i :8080 -P 2>/dev/null | grep -q LISTEN && ! lsof -i :8091 -P 2>/dev/null | grep -q LISTEN; then
        echo "  Ports 8080/8091 free"
        break
    fi
    echo "  Waiting for ports to free ($i)..."
    sleep 2
done

echo "[2/8] Setting up initial state (clean)..."
# Preserve signing key, wipe data for clean start
SIGNING_KEY_BACKUP="/tmp/agent_signing.key.bak"
cp ~/ciris/agent_signing.key "$SIGNING_KEY_BACKUP" 2>/dev/null || true
rm -rf ~/ciris/data /Users/macmini/CIRISAgent/data
rm -f /Users/macmini/CIRISAgent/ciris_engine.db /Users/macmini/CIRISAgent/ciris_audit.db /Users/macmini/CIRISAgent/secrets.db
mkdir -p ~/ciris/data /Users/macmini/CIRISAgent/data
cp "$SIGNING_KEY_BACKUP" ~/ciris/agent_signing.key 2>/dev/null || true
cp "$SIGNING_KEY_BACKUP" /Users/macmini/CIRISAgent/data/agent_signing.key 2>/dev/null || true
OPENROUTER_KEY_VALUE=$(cat ~/.openrouter_key)
cat > ~/ciris/.env << ENVEOF
CIRIS_CONFIGURED="true"
LOG_LEVEL="DEBUG"
CIRIS_OPENAI_API_KEY="$OPENROUTER_KEY_VALUE"
CIRIS_OPENAI_API_BASE="https://openrouter.ai/api/v1"
CIRIS_OPENAI_MODEL_NAME="mistralai/mistral-small-2603"
ENVEOF

echo "[3/8] Launching CIRIS desktop (test mode)..."
find /Users/macmini/CIRISAgent/ciris_engine -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
unset CIRIS_MOCK_LLM 2>/dev/null || true
# Export LLM config (CIRIS_ prefix matches setup wizard .env format)
export CIRIS_OPENAI_API_KEY="$OPENROUTER_KEY"
export CIRIS_OPENAI_API_BASE="https://openrouter.ai/api/v1"
export CIRIS_OPENAI_MODEL_NAME="mistralai/mistral-small-2603"
CIRIS_TEST_MODE=true python3 -m ciris_engine.cli > /tmp/ciris_e2e.log 2>&1 &
CIRIS_PID=$!
echo "  PID: $CIRIS_PID"

echo "  Waiting for test server..."
for i in $(seq 1 30); do
    if curl -s $API/health 2>/dev/null | grep -q '"ok"'; then
        echo "  Test server ready after $((i*2))s"
        break
    fi
    sleep 2
done
sleep 2
echo "  Screen: $(screen)"

# --- WAIT FOR LOGIN SCREEN ---
echo "[4/8] Waiting for Login screen then logging in..."
wait_screen "Login" 90
sleep 1
input_text "input_username" "admin"
input_text "input_password" "ciris_admin_password"
click "btn_login_submit"
wait_screen "Interact" 60
echo "  Screen: $(screen)"

# --- WIPE ---
echo "[5/8] Wiping data..."
click "btn_data_menu" && sleep 0.5
click "menu_data_management" && sleep 1
screenshot "/tmp/e2e_data_management.png"
click "btn_reset_account" && sleep 1
click "btn_reset_confirm"
echo "  Wipe triggered, waiting for Setup wizard..."
wait_screen "Setup" 60
screenshot "/tmp/e2e_setup_welcome.png"
echo "  Setup wizard ready"

# --- WIZARD ---
echo "[6/8] Running setup wizard..."

# Step 1: Welcome -> Next
click "btn_next" && sleep 1

# Step 2: Preferences (location)
echo "  Setting location: Schaumburg"
input_text "input_location_search" "Schaumburg"
sleep 2
screenshot "/tmp/e2e_location.png"
click "btn_next" && sleep 1

# Step 3: LLM Configuration
echo "  Configuring LLM: OpenRouter / mistral-small"
click "input_llm_provider" && sleep 0.5
click "menu_provider_openrouter" && sleep 0.5
input_text "input_api_key" "$OPENROUTER_KEY"
input_text "input_llm_model_text" "mistralai/mistral-small-2603"
screenshot "/tmp/e2e_llm_config.png"
click "btn_next" && sleep 1

# Step 4: Optional Features
echo "  Enabling: Accord metrics, location traces"
click "item_accord_metrics_consent" && sleep 0.3
click "item_share_location_traces" && sleep 0.3
screenshot "/tmp/e2e_optional_features.png"
click "btn_next" && sleep 1

# Step 5: Account
echo "  Creating account: humanuser"
input_text "input_username" "emoore"
input_text "input_password" "ciristest1"
screenshot "/tmp/e2e_account.png"

# Step 6: Finish Setup
echo "  Clicking Finish Setup..."
click "btn_next"
sleep 15
echo "  Screen: $(screen)"

# --- WAIT FOR AGENT ---
echo "[7/8] Waiting for agent..."
wait_screen "Interact" 60
screenshot "/tmp/e2e_interact.png"
echo "  Agent running on Interact screen"

# --- VERIFY ---
echo "[8/8] Verifying setup..."

# Check founding partnership
echo "  Checking founding partnership..."
PARTNERSHIP=$(grep -i "SETUP_COMPLETE.*founding\|founding.*partnership.*created" /tmp/ciris_e2e.log 2>/dev/null | tail -1)
if [ -n "$PARTNERSHIP" ]; then
    echo "  ✅ $PARTNERSHIP"
else
    echo "  ❌ Founding partnership NOT created"
fi

# Check consent status
echo "  Checking consent status..."
TOKEN=$(curl -s -X POST $BACKEND/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"emoore","password":"ciristest1"}' 2>/dev/null | \
    python3 -c "import json,sys; print(json.load(sys.stdin).get('access_token','FAIL'))")

CONSENT=$(curl -s $BACKEND/v1/consent/status -H "Authorization: Bearer $TOKEN" 2>/dev/null)
HAS_CONSENT=$(echo "$CONSENT" | python3 -c "import json,sys;print(json.load(sys.stdin).get('has_consent',False))")
STREAM=$(echo "$CONSENT" | python3 -c "import json,sys;print(json.load(sys.stdin).get('stream','None'))")

if [ "$HAS_CONSENT" = "True" ]; then
    echo "  ✅ has_consent=True, stream=$STREAM"
else
    echo "  ❌ has_consent=False (expected True/partnered)"
    echo "  Full response: $CONSENT"
fi

# Check lens-identifier
echo "  Checking lens-identifier..."
LENS=$(curl -s $BACKEND/v1/my-data/lens-identifier -H "Authorization: Bearer $TOKEN" 2>/dev/null)
LENS_SUCCESS=$(echo "$LENS" | python3 -c "import json,sys;print(json.load(sys.stdin).get('success',False))")
if [ "$LENS_SUCCESS" = "True" ]; then
    AGENT_HASH=$(echo "$LENS" | python3 -c "import json,sys;print(json.load(sys.stdin).get('data',{}).get('agent_id_hash','?'))")
    echo "  ✅ lens-identifier OK (hash=$AGENT_HASH)"
else
    echo "  ❌ lens-identifier FAILED"
fi

# Check .env doesn't have mock LLM
echo "  Checking .env..."
if grep -q "MOCK_LLM" ~/ciris/.env 2>/dev/null; then
    echo "  ❌ CIRIS_MOCK_LLM found in .env (should not be there)"
else
    echo "  ✅ No MOCK_LLM in .env"
fi

if grep -q "openrouter" ~/ciris/.env 2>/dev/null; then
    echo "  ✅ OpenRouter configured in .env"
else
    echo "  ❌ OpenRouter NOT found in .env"
fi

echo ""
echo "============================================"
echo "  Screenshots saved to /tmp/e2e_*.png"
echo "  Logs at /tmp/ciris_e2e.log"
echo "============================================"
