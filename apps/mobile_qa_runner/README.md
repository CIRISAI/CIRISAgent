# Mobile QA Runner

Bridge for testing CIRIS on Android emulators. This tool connects the main QA runner to the CIRIS server running on an Android emulator via ADB port forwarding.

## Quick Start

```bash
# From mobile/ directory
cd /path/to/CIRISAgent/mobile

# 1. Check device status
python -m tools.mobile_qa_runner status

# 2. Setup device with API key (bypasses setup wizard for testing)
python -m tools.mobile_qa_runner setup --llm-api-key sk-...

# 3. Restart app to apply config
python -m tools.mobile_qa_runner restart

# 4. Wait for server to be ready
python -m tools.mobile_qa_runner wait

# 5. Run QA tests
python -m tools.mobile_qa_runner run auth
python -m tools.mobile_qa_runner run auth telemetry agent
```

## Commands

| Command | Description |
|---------|-------------|
| `status` | Check device, .env status, and server health |
| `bridge` | Start ADB port forwarding (keeps running) |
| `setup` | Create .env on device to complete first-run |
| `reset` | Delete .env to reset to first-run state |
| `restart` | Force stop and restart the CIRIS app |
| `logs` | Show recent Python logcat output |
| `wait` | Wait for server to become healthy |
| `run <modules>` | Run QA test modules via bridge |

## Architecture

```
┌─────────────────┐     ADB Port Forward      ┌─────────────────────┐
│   Host Machine  │◄─────────────────────────►│  Android Emulator   │
├─────────────────┤   localhost:8080 ───►     ├─────────────────────┤
│                 │   ◄─── device:8080        │                     │
│  QA Runner      │                           │  CIRIS App          │
│  (Python)       │                           │  ├─ Python Runtime  │
│                 │                           │  ├─ FastAPI Server  │
│  mobile_qa_     │                           │  └─ 22 Services     │
│  runner/bridge  │                           │                     │
└─────────────────┘                           └─────────────────────┘
```

## Testing First-Run Setup

```bash
# 1. Reset to first-run state
python -m tools.mobile_qa_runner reset
python -m tools.mobile_qa_runner restart

# 2. Check status (should show is_first_run=True)
python -m tools.mobile_qa_runner status

# 3. Wait for minimal services (10/10 in first-run mode)
python -m tools.mobile_qa_runner wait

# 4. Complete setup via API (same as setup wizard)
python -m tools.mobile_qa_runner setup --llm-api-key sk-...

# 5. Restart to apply full config
python -m tools.mobile_qa_runner restart

# 6. Wait for all 22 services
python -m tools.mobile_qa_runner wait
```

## Running Main QA Tests

The bridge allows you to run any test module from the main QA runner:

```bash
# Run specific modules
python -m tools.mobile_qa_runner run auth
python -m tools.mobile_qa_runner run telemetry
python -m tools.mobile_qa_runner run agent

# Run multiple modules
python -m tools.mobile_qa_runner run auth telemetry agent system

# Force run even if server not fully healthy
python -m tools.mobile_qa_runner run auth --force
```

## Manual Bridge Mode

For advanced testing, start the bridge manually and use the main QA runner directly:

```bash
# Terminal 1: Start bridge
python -m tools.mobile_qa_runner bridge

# Terminal 2: Run main QA runner
cd /path/to/CIRISAgent
python -m tools.qa_runner auth --url http://localhost:8080 --no-auto-start
```

## Device Selection

```bash
# List devices
adb devices

# Use specific device
python -m tools.mobile_qa_runner -s emulator-5554 status

# Use physical device
python -m tools.mobile_qa_runner -s XXXXXXXX status
```

## Troubleshooting

### No device connected
```bash
# Start emulator
~/Android/Sdk/emulator/emulator -avd Pixel_6_API_34 &

# Or check running emulators
adb devices
```

### Server not reachable
```bash
# Check if app is running
adb shell ps | grep ciris

# Check logcat for errors
python -m tools.mobile_qa_runner logs -n 200

# Restart app
python -m tools.mobile_qa_runner restart
```

### Port already in use
```bash
# Use different local port
python -m tools.mobile_qa_runner --port 8081 bridge

# Then update QA runner URL
python -m tools.qa_runner auth --url http://localhost:8081 --no-auto-start
```

## Extending with Mobile-Specific Tests

Create new test modules in `modules/`:

```python
# modules/setup_tests.py
from ..config import MobileQAModule

class SetupTestModule:
    @staticmethod
    def get_first_run_tests():
        return [
            # Test that setup wizard appears on first run
            # Test Google OAuth flow
            # Test BYOK flow
            # Test validation errors
        ]
```

## Integration with CI/CD

```yaml
# .github/workflows/mobile-qa.yml
jobs:
  mobile-qa:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4

      - name: Start emulator
        uses: reactivecircus/android-emulator-runner@v2
        with:
          api-level: 34
          script: |
            cd mobile
            python -m tools.mobile_qa_runner wait
            python -m tools.mobile_qa_runner run auth telemetry
```
