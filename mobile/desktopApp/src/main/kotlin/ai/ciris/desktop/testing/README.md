# CIRIS Desktop Test Automation Server

Embedded HTTP server for UI automation of the CIRIS Desktop app.

## Enabling Test Mode

Set the environment variable before launching the app:

```bash
export CIRIS_TEST_MODE=true
./gradlew :desktopApp:run
```

Or with a custom port:

```bash
export CIRIS_TEST_MODE=true
export CIRIS_TEST_PORT=9000
./gradlew :desktopApp:run
```

## API Endpoints

The server runs on `http://localhost:9091` by default.

### Health Check

```bash
curl http://localhost:9091/health
```

Response:
```json
{
  "status": "ok",
  "testMode": true
}
```

### Get Current Screen

```bash
curl http://localhost:9091/screen
```

Response:
```json
{
  "screen": "Login"
}
```

### Get UI Element Tree

```bash
curl http://localhost:9091/tree
```

Response:
```json
{
  "screen": "Login",
  "elements": [
    {
      "testTag": "input_username",
      "x": 460,
      "y": 350,
      "width": 280,
      "height": 56,
      "centerX": 600,
      "centerY": 378
    },
    {
      "testTag": "input_password",
      "x": 460,
      "y": 420,
      "width": 280,
      "height": 56,
      "centerX": 600,
      "centerY": 448
    },
    {
      "testTag": "btn_login_submit",
      "x": 460,
      "y": 500,
      "width": 280,
      "height": 56,
      "centerX": 600,
      "centerY": 528
    }
  ],
  "count": 3
}
```

### Click Element

```bash
curl -X POST http://localhost:9091/click \
  -H "Content-Type: application/json" \
  -d '{"testTag": "btn_login_submit"}'
```

Response:
```json
{
  "success": true,
  "element": "btn_login_submit",
  "action": "click",
  "coordinates": "600,528"
}
```

### Input Text

```bash
curl -X POST http://localhost:9091/input \
  -H "Content-Type: application/json" \
  -d '{"testTag": "input_username", "text": "admin", "clearFirst": true}'
```

Response:
```json
{
  "success": true,
  "element": "input_username",
  "action": "input",
  "text": "admin"
}
```

### Wait for Element

```bash
curl -X POST http://localhost:9091/wait \
  -H "Content-Type: application/json" \
  -d '{"testTag": "btn_send", "timeoutMs": 5000}'
```

Response (success):
```json
{
  "success": true,
  "element": "btn_send",
  "action": "wait"
}
```

Response (timeout):
```json
{
  "success": false,
  "error": "Element not found within 5000ms: btn_send"
}
```

### Get Element Info

```bash
curl http://localhost:9091/element/input_username
```

Response:
```json
{
  "testTag": "input_username",
  "x": 460,
  "y": 350,
  "width": 280,
  "height": 56,
  "centerX": 600,
  "centerY": 378
}
```

## Available Test Tags

### Login Screen
- `input_username` - Username text field
- `input_password` - Password text field
- `btn_login_submit` - Login button
- `btn_local_login` - Local login button (mobile only)
- `btn_google_signin` / `btn_apple_signin` - OAuth sign-in buttons (mobile only)
- `btn_login_back` - Back button

### Interact Screen (Chat)
- `input_message` - Chat message input field
- `btn_send` - Send message button

## Example: Full Login Flow

```bash
# 1. Check we're on login screen
curl http://localhost:9091/screen
# {"screen":"Login"}

# 2. Wait for username field
curl -X POST http://localhost:9091/wait \
  -d '{"testTag": "input_username", "timeoutMs": 10000}'

# 3. Enter username
curl -X POST http://localhost:9091/input \
  -d '{"testTag": "input_username", "text": "admin"}'

# 4. Enter password
curl -X POST http://localhost:9091/input \
  -d '{"testTag": "input_password", "text": "password123"}'

# 5. Click login
curl -X POST http://localhost:9091/click \
  -d '{"testTag": "btn_login_submit"}'

# 6. Wait for chat screen
curl -X POST http://localhost:9091/wait \
  -d '{"testTag": "input_message", "timeoutMs": 10000}'

# 7. Verify we're on Interact screen
curl http://localhost:9091/screen
# {"screen":"Interact"}
```

## Adding New Testable Elements

In your Compose code, use the `testable` modifier instead of `testTag`:

```kotlin
import ai.ciris.mobile.shared.platform.testable

Button(
    onClick = { ... },
    modifier = Modifier.testable("my_button")
)

TextField(
    value = text,
    onValueChange = { ... },
    modifier = Modifier.testable("my_input")
)
```

The `testable` modifier:
- On desktop with test mode: Tracks element position for automation
- On desktop without test mode: Just applies `testTag`
- On mobile: Just applies `testTag`
