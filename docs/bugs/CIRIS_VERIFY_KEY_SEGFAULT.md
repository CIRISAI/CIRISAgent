# Bug Report: CIRIS Verify FFI Segfault After Init Complete

**Severity:** Critical (blocks QA testing)
**Component:** Python ctypes FFI bindings (NOT the Rust library)
**Version:** v1.1.27
**Reporter:** Claude Code / Eric Moore
**Date:** 2026-03-16
**Status:** ✅ FIXED (2026-03-16)

## Resolution

**Root Cause:** Missing `argtypes` declaration in Python ctypes bindings caused 64-bit pointer truncation.

**Fix Location:** `ciris_adapters/ciris_verify/ffi_bindings/client.py` (lines 472-475)

```python
# CRITICAL: This must be set or ctypes truncates 64-bit pointers to 32-bit!
self._lib.ciris_verify_generate_key.argtypes = [ctypes.c_void_p]
self._lib.ciris_verify_generate_key.restype = ctypes.c_int
```

The CIRISVerify Rust library (v1.1.27) was working correctly - the bug was purely in the Python FFI wrapper.

---

## Original Bug Report (Historical)

## Summary

The CIRIS Verify FFI library crashes with SIGSEGV (exit code -11) immediately after successful initialization when no signing key exists. The crash occurs AFTER "CIRISVerify FFI init complete" and "Log callback registered" - meaning FFI init succeeds but some subsequent operation crashes.

## Steps to Reproduce

```bash
# 1. Remove any existing key files
rm -f /home/emoore/CIRISAgent/data/agent_signing.*

# 2. Run via QA runner (reliably crashes)
python3 -m tools.qa_runner auth

# Result: Server process died (exit code: -11)
```

## Key Observation

Running the server directly does NOT crash:
```bash
rm -f data/agent_signing.* && python3 main.py --port 8099 --mock-llm
# Works - server starts successfully
```

But running via QA runner crashes immediately:
```bash
rm -f data/agent_signing.* && python3 -m tools.qa_runner auth
# Crashes with SIGSEGV
```

The only difference is the QA runner spawns the process as a subprocess with specific environment variables.

## Console Output (crash sequence)

```
[INFO] ciris_verify_ffi: CIRISVerify FFI init starting (v1.1.25)
[INFO] ciris_verify_ffi: Creating async runtime
[INFO] ciris_verify_core::engine: LicenseEngine: initialization complete
[INFO] ciris_keyring::software: TPM-backed Ed25519 wrapper initialized (AES-256-GCM via TPM-derived key) alias=agent_signing
[INFO] ciris_keyring::software: Ed25519SoftwareSigner: created (no key loaded) alias=agent_signing
[INFO] ciris_keyring::software: Attempting to load TPM-backed Ed25519 key...
[INFO] ciris_verify_ffi: VERIFY Ed25519 signer initialized
[INFO] ciris_verify_ffi: MutableEd25519Signer diagnostics:
- alias: agent_signing
- has_key: false
- hardware_backed: true - ENABLED (AES-256-GCM via TPM-derived key)
- storage_path: Some("/home/emoore/CIRISAgent/data/agent_signing.key")
[INFO] ciris_verify_ffi: No persisted Portal key found.
[INFO] ciris_verify_ffi: CIRISVerify FFI init complete — handle ready
[INFO] ciris_verify_ffi: Log callback registered
*** SIGSEGV (exit code -11) ***
```

## What Should Happen

After init complete with no key:
1. `has_key_sync()` should return `false`
2. `generate_key_sync()` should create an ephemeral key
3. Server continues initialization

## What Actually Happens

After init complete with no key:
1. Process crashes with SIGSEGV before Python code can call any FFI functions
2. Crash occurs between "Log callback registered" and any subsequent operation
3. No key files are created

## Environment Difference

QA runner sets these env vars before spawning:
```python
env["PYTHONUNBUFFERED"] = "1"
env["CIRIS_HOME"] = str(project_root)  # /home/emoore/CIRISAgent
```

Direct run inherits shell environment which may have different values.

## Environment Details

- OS: Linux 6.17.0-19-generic (Ubuntu)
- Python: 3.12
- ciris-verify: 1.1.25 (PyPI)
- Binary: libciris_verify_ffi.so (9.3MB, md5: 70550c04d9f1b4b0c3359c21d9532249)
- TPM: Available (TpmFirmware)
- CIRIS_HOME: /home/emoore/CIRISAgent

## Impact

- Blocks all QA testing via `python3 -m tools.qa_runner`
- CI/CD pipeline cannot run automated tests
- Manual testing via direct `python3 main.py` still works (workaround)

## Status: PARTIALLY FIXED in v1.1.27

v1.1.27 fixed the init-time crash. Now the crash happens in `generate_key_sync()`.

## Current Crash (v1.1.27)

```
[signing] No signing key found, generating ephemeral Ed25519 key
[signing] Attempting key generation (attempt 1/2)
*** CORE DUMP ***
```

The `ciris_verify_generate_key()` FFI call is crashing when trying to create a TPM-backed ephemeral key.

---

## Previous Root Cause (FIXED in v1.1.27)

**The Rust library internally calls `get_ed25519_public_key` during initialization, BEFORE Python has a chance to call `generate_key_sync()`.**

Console output proves this:
```
[INFO] ciris_verify_ffi: CIRISVerify FFI init complete — handle ready
[INFO] ciris_verify_ffi: Log callback registered
[ERROR] ciris_verify_ffi: get_ed25519_public_key: no key loaded   <-- RUST side, not Python!
*** SIGSEGV ***
```

The `get_ed25519_public_key: no key loaded` error is logged from Rust code (ciris_verify_ffi), not Python. This means something in the Rust library is internally calling `get_ed25519_public_key` during or immediately after log callback registration.

**Expected flow (what Android/iOS do):**
1. `ciris_verify_init()` - just initializes library, NO key operations
2. Python calls `has_key_sync()` → returns false (no key yet)
3. Python calls `generate_key_sync()` → creates ephemeral key with TPM
4. Python calls `get_ed25519_public_key_sync()` → now works

**Actual flow (broken):**
1. `ciris_verify_init()` - initializes library
2. Log callback registered
3. **RUST INTERNALLY calls `get_ed25519_public_key`** → ERROR "no key loaded"
4. SIGSEGV crash (likely null pointer dereference in key access)
5. Python never gets chance to call `generate_key_sync()`

## Hypothesis (secondary)

Why it crashes as subprocess but not direct execution:
1. Subprocess spawning may affect Rust async runtime timing
2. Different stdout/stderr redirection affects callback behavior
3. Thread scheduling differences expose the race condition

## Workaround

Run server directly instead of via QA runner:
```bash
python3 main.py --adapter api --mock-llm --port 8080
```

## Related Files

- `ciris_adapters/ciris_verify/ffi_bindings/client.py` - Python FFI wrapper
- `ciris_engine/logic/audit/signing_protocol.py` - Signing protocol
- `tools/qa_runner/server.py` - QA runner subprocess spawning (line 521-528)

---

## Final Root Cause Analysis (2026-03-16)

### The Actual Problem

The crash was **NOT** in the Rust library. It was a **Python ctypes ABI mismatch**.

When ctypes calls a C function without `argtypes` set, it defaults to treating pointer arguments as `int` (32-bit on many systems). This caused **64-bit pointer truncation**:

```
Before: handle = 0x787f7804d100 (48-bit valid address)
After:  handle = 0x7804d100     (truncated to 32 bits)
```

When the Rust code dereferenced this corrupted pointer → SIGSEGV.

### Why It Only Crashed in generate_key()

The `ciris_verify_generate_key` function was the ONLY Ed25519-related function missing proper `argtypes`:

```python
# These were correctly declared:
self._lib.ciris_verify_has_key.argtypes = [ctypes.c_void_p]
self._lib.ciris_verify_import_key.argtypes = [ctypes.c_void_p, ...]
self._lib.ciris_verify_sign_ed25519.argtypes = [ctypes.c_void_p, ...]

# THIS WAS MISSING:
# self._lib.ciris_verify_generate_key.argtypes = [ctypes.c_void_p]
```

### Debug Evidence

Adding pointer logging revealed the corruption:
```
[init] self ptr: 0x787f7804d100  # Valid 48-bit address
[FFI]  self ptr: 0x7804d100      # TRUNCATED! Missing high bytes
```

### The Fix

Added the missing declaration (line 472-475 in client.py):
```python
self._lib.ciris_verify_generate_key.argtypes = [ctypes.c_void_p]
self._lib.ciris_verify_generate_key.restype = ctypes.c_int
```

### Verification

After the fix:
- Key generation succeeds with TPM backing
- Fingerprint: `f0630705` (TPM-wrapped)
- Key file created: `agent_signing.ed25519.tpm`
- Hardware backing confirmed: `hardware_backed=true`
