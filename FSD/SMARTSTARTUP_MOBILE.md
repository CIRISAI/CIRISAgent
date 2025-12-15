# Functional Specification Document: SmartStartup Mobile Server Negotiation

Version: 1.1
Date: December 15, 2025
Status: DRAFT

**Changelog:**
- 1.1: Added scenario 6a (activity recreation) and fix for self-server killing
- 1.0: Initial draft

## 1. Overview

This document specifies the SmartStartup protocol for Android mobile, which handles scenarios where:
- A Python server may already be running from a previous session
- App data may have been cleared while server was running
- Server may be in various states (initializing, resuming, ready, shutting down)
- Multiple Kotlin app instances may try to start servers

**Goal**: Ensure exactly one healthy Python server is running, with graceful handoff between old and new instances.

## 2. Architecture

```
┌─────────────────┐         ┌─────────────────┐
│  Kotlin App     │         │  Python Server  │
│  (MainActivity) │◄───────►│  (FastAPI)      │
└─────────────────┘  HTTP   └─────────────────┘
        │                           │
        ▼                           ▼
   SmartStartup              local-shutdown
   Detection                 Endpoint
```

### 2.1 Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| SmartStartup | `MainActivity.kt` | Detect/shutdown existing servers |
| local-shutdown | `/v1/system/local-shutdown` | Localhost-only shutdown endpoint |
| shutdown | `/v1/system/shutdown` | Authenticated shutdown endpoint |
| Health check | `/health` | Server readiness check |

## 3. Server States

### 3.1 Python Server States

| State | Description | Can Accept Shutdown? |
|-------|-------------|---------------------|
| `STARTING` | Server binding to port | No (not listening yet) |
| `INITIALIZING` | Services loading | Yes (graceful) |
| `RESUMING` | First-run resume in progress | **No (critical window)** |
| `READY` | Fully operational | Yes |
| `SHUTTING_DOWN` | Already shutting down | No (redundant) |

### 3.2 Kotlin App States

| State | Description | Server Expected? |
|-------|-------------|-----------------|
| Fresh install | No prior data | No |
| Normal launch | Has saved data | Maybe (if backgrounded) |
| After data clear | Cleared by user/system | Maybe (orphan process) |
| After force stop | App killed | Maybe (Python survived) |
| After crash | Unexpected termination | Maybe (Python survived) |

## 4. Scenario Matrix

### 4.1 First-Run Scenarios

| # | Scenario | Old Server | New Server | Auth Token | Expected Behavior |
|---|----------|------------|------------|------------|-------------------|
| 1 | Fresh install | None | Starts | None | Normal startup |
| 2 | Pre-wizard crash | Orphan (init) | Starts | None | Shutdown orphan, start new |
| 3 | Mid-wizard crash | Orphan (resume) | Starts | None | **WAIT for resume, then shutdown** |
| 4 | Post-wizard crash | Orphan (ready) | Starts | None | Shutdown orphan, start new |
| 5 | Wizard complete, app killed | Orphan (ready) | Starts | Saved | Use auth shutdown |

### 4.2 Returning User Scenarios

| # | Scenario | Old Server | New Server | Auth Token | Expected Behavior |
|---|----------|------------|------------|------------|-------------------|
| 6 | Normal resume | Running | Skip | Saved | Reuse existing server |
| 6a | Activity recreated (config change) | **OUR** server | **SKIP** | Saved | **Reconnect, don't kill** |
| 7 | Backgrounded, data cleared | Orphan | Starts | **None** | Shutdown via local-shutdown |
| 8 | Force stopped, data intact | Orphan | Starts | Saved | Shutdown via auth |
| 9 | Force stopped, data cleared | Orphan | Starts | None | Shutdown via local-shutdown |
| 10 | OOM killed | Orphan | Starts | Saved | Shutdown via auth |

### 4.3 Edge Cases

| # | Scenario | Old Server | New Server | Expected Behavior |
|---|----------|------------|------------|-------------------|
| 11 | Port stolen by other app | Other app | Fails | Error: port in use |
| 12 | Rapid app restart | Shutting down | Waits | Wait for old shutdown |
| 13 | Stale resume flag | Ready (flag stuck) | Blocked | **BUG - needs fix** |
| 14 | Concurrent app instances | Running | Blocked | Second instance waits |

## 5. HTTP Response Codes

### 5.1 Current Implementation

| Endpoint | Code | Meaning | Kotlin Action |
|----------|------|---------|---------------|
| local-shutdown | 200 | Shutdown initiated | Wait for server death |
| local-shutdown | 409 | Resume in progress | **Currently: fall through** |
| local-shutdown | 500 | Server error | Fall through to auth |
| shutdown | 200 | Shutdown initiated | Wait for server death |
| shutdown | 401 | No/invalid token | Cannot shutdown |
| shutdown | 403 | Insufficient role | Cannot shutdown |

### 5.2 Proposed Response Codes

| Endpoint | Code | Meaning | Kotlin Action |
|----------|------|---------|---------------|
| local-shutdown | 200 | Shutdown initiated | Wait for server death |
| local-shutdown | 202 | Shutdown accepted, delayed | Wait longer (5s) |
| local-shutdown | 409 | Resume in progress | **Retry after 2s (max 5x)** |
| local-shutdown | 423 | Server locked (other op) | Retry after 1s (max 3x) |
| local-shutdown | 503 | Server not ready | Retry after 1s (max 3x) |

### 5.3 Response Body Schema

```json
{
  "status": "accepted|rejected|busy",
  "reason": "string describing why",
  "retry_after_ms": 2000,
  "server_state": "INITIALIZING|RESUMING|READY|SHUTTING_DOWN",
  "uptime_seconds": 45.2
}
```

## 6. SmartStartup Protocol

### 6.1 Current Flow

```
1. Check if server running (GET /health)
   └─ No  → Start new server
   └─ Yes → Continue to step 2

2. Try local-shutdown (POST /v1/system/local-shutdown)
   └─ 200 → Wait for death, start new
   └─ 409 → Fall through to step 3 (BUG!)
   └─ Error → Fall through to step 3

3. Try authenticated shutdown (POST /v1/system/shutdown)
   └─ 200 → Wait for death, start new
   └─ 401 → Cannot shutdown (no token)
   └─ Error → Give up

4. If shutdown failed → Start new server anyway (port conflict!)
```

### 6.2 Proposed Flow

```
1. Check if server running (GET /health)
   └─ No  → Start new server
   └─ Yes → Continue to step 2

2. Try local-shutdown (POST /v1/system/local-shutdown)
   └─ 200 → Wait for death, start new
   └─ 202 → Wait 5s, check death, start new
   └─ 409 → **Retry up to 5x with 2s delay**
            └─ Still 409 after 10s → Log error, try auth shutdown
   └─ 503 → Retry up to 3x with 1s delay
   └─ Error → Fall through to step 3

3. Try authenticated shutdown (POST /v1/system/shutdown)
   └─ 200 → Wait for death, start new
   └─ 401/403 → Log warning, check if server still needed
   └─ Error → Log error

4. Wait for server death (poll /health for failure)
   └─ Dead within 10s → Start new server
   └─ Still alive → **Force kill via SIGTERM if possible**
                    └─ Cannot kill → Error state, user intervention needed

5. Start new server
   └─ Port available → Normal startup
   └─ Port busy → Fatal error (shouldn't happen after step 4)
```

## 7. Python Server Changes

### 7.1 Enhanced local-shutdown Endpoint

```python
@router.post("/local-shutdown")
async def local_shutdown(request: Request):
    # Verify localhost only
    if not is_localhost(request):
        raise HTTPException(403, "Localhost only")

    runtime = get_runtime()

    # Check server state
    if runtime._resume_in_progress:
        # Calculate how long resume has been running
        resume_elapsed = time.time() - runtime._resume_started_at
        if resume_elapsed < 15.0:  # Max reasonable resume time
            return JSONResponse(
                status_code=409,
                content={
                    "status": "busy",
                    "reason": "Resume from first-run in progress",
                    "retry_after_ms": 2000,
                    "server_state": "RESUMING",
                    "uptime_seconds": runtime.uptime_seconds
                }
            )
        else:
            # Resume took too long - likely stuck, allow shutdown
            logger.warning(f"Resume exceeded 15s ({resume_elapsed:.1f}s) - allowing shutdown")

    if runtime._shutdown_in_progress:
        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "reason": "Shutdown already in progress",
                "server_state": "SHUTTING_DOWN"
            }
        )

    # Initiate shutdown
    await runtime.request_shutdown("local-shutdown endpoint")
    return JSONResponse(
        status_code=200,
        content={
            "status": "accepted",
            "reason": "Shutdown initiated",
            "server_state": "SHUTTING_DOWN"
        }
    )
```

### 7.2 Resume Timeout Protection

```python
async def resume_from_first_run(self):
    self._resume_in_progress = True
    self._resume_started_at = time.time()

    try:
        # ... resume steps ...
    finally:
        self._resume_in_progress = False
        self._resume_started_at = None
```

## 8. Kotlin Changes

### 8.1 Enhanced shutdownExistingServer

```kotlin
private suspend fun shutdownExistingServer(): Boolean {
    var retryCount = 0
    val maxRetries = 5

    while (retryCount < maxRetries) {
        try {
            val response = tryLocalShutdown()

            when (response.code) {
                200 -> {
                    Log.i(TAG, "[SmartStartup] Shutdown initiated")
                    return true
                }
                202 -> {
                    Log.i(TAG, "[SmartStartup] Shutdown already in progress")
                    return true  // Will wait for death
                }
                409 -> {
                    val retryAfter = response.retryAfterMs ?: 2000
                    Log.i(TAG, "[SmartStartup] Server busy (resume), retry in ${retryAfter}ms")
                    delay(retryAfter.toLong())
                    retryCount++
                }
                503 -> {
                    Log.i(TAG, "[SmartStartup] Server not ready, retry in 1s")
                    delay(1000)
                    retryCount++
                }
                else -> {
                    Log.w(TAG, "[SmartStartup] Unexpected response: ${response.code}")
                    break  // Fall through to auth
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "[SmartStartup] local-shutdown error: ${e.message}")
            break
        }
    }

    // Fall back to authenticated shutdown
    return tryAuthenticatedShutdown()
}
```

## 9. Testing Matrix

### 9.1 Unit Tests

| Test | Input | Expected Output |
|------|-------|-----------------|
| local_shutdown_ready | Server ready | 200, shutdown initiated |
| local_shutdown_resuming | Resume in progress | 409, retry_after_ms |
| local_shutdown_resume_stuck | Resume > 15s | 200, shutdown allowed |
| local_shutdown_shutting_down | Already shutting | 202, accepted |
| local_shutdown_not_localhost | Remote IP | 403, forbidden |

### 9.2 Integration Tests

| Test | Setup | Action | Expected |
|------|-------|--------|----------|
| Fresh install | No server | Start app | Server starts normally |
| Data clear with orphan | Server running, clear data | Start app | Orphan killed, new starts |
| Mid-resume restart | Server resuming | Start app | Wait for resume, then handoff |
| Rapid restart | Kill app, restart | Start app | Wait for shutdown, then start |

## 10. Migration Path

### 10.1 Phase 1: Server-Side (Current PR)
1. Add `_resume_started_at` timestamp
2. Add timeout check (15s) to local-shutdown
3. Return structured JSON response with retry info

### 10.2 Phase 2: Client-Side
1. Parse JSON response from local-shutdown
2. Implement retry loop for 409
3. Add logging for debugging

### 10.3 Phase 3: Robustness
1. Add process kill capability (if Android permits)
2. Add telemetry for startup scenarios
3. Add user-facing error messages

## 11. Open Questions

1. **Process killing**: Can Kotlin kill orphan Python processes directly?
2. **Timeout values**: Is 15s too long/short for resume timeout?
3. **Retry limits**: Are 5 retries with 2s delay (10s total) appropriate?
4. **Telemetry**: Should we track startup scenario frequency?

## 12. Appendix: Observed Failures

### 12.1 2025-12-15 - Resume Protection Blocking Stale Server

**Symptom**: New server failed to start, port 8080 in use

**Cause**: Old server had `_resume_in_progress=True` stuck from previous session where app was killed mid-resume. New Kotlin app tried local-shutdown, got 409, fell through to auth (401), couldn't shutdown old server.

**Fix**: Add timeout to resume protection - if resume has been "in progress" for > 15s, it's stuck and shutdown should be allowed.

### 12.2 2025-12-15 - Activity Recreation Killing Own Server

**Symptom**: App crashed after setup wizard completed, server killed mid-operation

**Cause**: When Android recreates the activity (e.g., configuration change, returning from background after partial process death), `onCreate()` runs again and triggers `initializePythonAndStartServer()`. This function runs SmartStartup, which detects the existing server on port 8080 and attempts to shut it down - even though that server is the CORRECT one started by this same process!

**Root cause**: No mechanism to distinguish between:
- Orphan server (from previous app session) → Should be killed
- Our server (started by this process) → Should be kept

**Fix**: Added static `serverStartedByThisProcess` flag in `companion object`:
1. Set to `true` when server starts successfully
2. Set to `false` on server failure/exception
3. Checked in `startPythonServer()` BEFORE running SmartStartup
4. If flag is `true` AND server is running → SKIP SmartStartup, reconnect to existing server

**Code pattern**:
```kotlin
companion object {
    @Volatile
    private var serverStartedByThisProcess = false
}

private fun startPythonServer() {
    // CRITICAL: Check if we already started a server in this process
    if (serverStartedByThisProcess && isExistingServerRunning()) {
        Log.i(TAG, "[SmartStartup] ⏩ SKIPPING - server was started by THIS process")
        // Reconnect to existing server instead of killing it
        return
    }

    // Only run SmartStartup for ORPHAN servers (different process)
    if (isExistingServerRunning()) {
        Log.i(TAG, "[SmartStartup] Detected ORPHAN server (not started by this process)")
        // ... shutdown orphan ...
    }
}
```

**Why static flag works**: JVM static variables persist for the lifetime of the process. When the Android process dies, all statics reset to default (`false`). So:
- Activity recreation (same process) → Flag is `true` → Keep server
- Process death → Flag is `false` → Run SmartStartup for orphans
