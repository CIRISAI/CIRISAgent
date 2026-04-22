# CIRISVerify Ed25519 Signing Failure Report

**Date:** 2026-04-21
**Severity:** Critical
**Impact:** All audit hash chain signing fails, blocking normal operation

## Summary

The CIRISVerify Ed25519 signing key is failing to sign because it was originally bound to hardware security (TPM/HSM) but the hardware is now unavailable.

## Error Messages

```
[ciris_keyring::software] Software fallback attempted but hardware marker is set - key is secured by hardware, marker=Some("HARDWARE_SECURED:99044633")

[ciris_verify_ffi] Ed25519 signing failed: Hardware security error: Key is secured by hardware key (marker=HARDWARE_SECURED:99044633) but hardware access failed

VerificationFailedError: Verification failed (-3): Ed25519 signing failed with code -3

RuntimeError: Hash chain data not generated for action task_complete. enable_hash_chain=True. This is a critical audit trail failure.
```

## Root Cause Analysis

1. **Key Creation**: The Ed25519 signing key was created with hardware security enabled (TPM or HSM binding)

2. **Hardware Marker**: The key was persisted with marker `HARDWARE_SECURED:99044633`, indicating it's bound to hardware security module ID `99044633`

3. **Hardware Unavailable**: When signing is attempted:
   - The library detects the hardware marker
   - Attempts to use hardware path but hardware access fails
   - Software fallback is explicitly blocked because key has hardware marker
   - Result: Error code -3 (signing failure)

4. **Cascade Effect**: Every action (speak, task_complete, etc.) requires audit hash chain signing → all actions fail

## Key Storage Location

```
~/.local/share/ciris-verify/
├── ciris_verify_key.p256.key  (32 bytes, raw key material)
├── named_keys.master.key      (32 bytes)
├── test.p256.key              (32 bytes)
└── keystore.db                (0 bytes - empty)
```

The hardware marker (`HARDWARE_SECURED:99044633`) is NOT stored in these files - it appears to be encoded in the native library's internal state or key metadata format.

## Timeline

```
15:26:07.010 - First signing failure detected
15:26:07.010 - Software fallback blocked due to hardware marker
15:26:07.010 - Hash chain failure triggers error handling
15:26:07.xxx - Pattern repeats for every action
```

## Affected Components

1. `ciris_engine/logic/audit/signature_manager.py` - Cannot sign entries
2. `ciris_engine/logic/audit/signing_protocol.py:166` - Raises VerificationFailedError
3. `ciris_engine/logic/services/graph/audit_service/service.py` - Hash chain generation fails
4. `ciris_engine/logic/infrastructure/handlers/action_dispatcher.py` - All action handlers fail
5. `ciris_adapters/ciris_verify/ffi_bindings/client.py` - FFI calls return error -3

## Possible Causes

1. **Hardware Changed**: The TPM/HSM that created the key is no longer accessible
2. **Container/VM**: Running in environment without access to original hardware
3. **Key Migration**: Key was created on different machine with hardware security
4. **Driver Issue**: TPM driver not loaded or malfunctioning

## Resolution Options

### Option 1: Re-enable Hardware Access (Preferred if possible)
- Ensure TPM/HSM driver is loaded
- Check `/dev/tpm0` or equivalent exists
- Verify permissions for hardware access

### Option 2: Generate New Software-Only Key
```bash
# Delete existing key storage (DESTRUCTIVE - loses existing audit chain)
rm -rf ~/.local/share/ciris-verify/

# Restart server - new key will be generated without hardware binding
# Note: Existing audit chain signatures will be invalid
```

### Option 3: Fix in CIRISVerify Library
- Add configuration to allow software fallback even with hardware marker
- Implement key migration from hardware to software mode
- Add CLI tool to re-key with software-only mode

### Option 4: Disable Hash Chain (Development Only)
```python
# In config, set enable_hash_chain=False
# WARNING: This disables audit integrity guarantees
```

## Verification Steps

1. Check TPM availability:
   ```bash
   ls -la /dev/tpm*
   dmesg | grep -i tpm
   ```

2. Check CIRISVerify status:
   ```bash
   python3 -c "
   from ciris_adapters.ciris_verify.ffi_bindings.client import CIRISVerifyClient
   client = CIRISVerifyClient()
   print(client.get_status())
   "
   ```

3. Verify key can sign:
   ```bash
   python3 -c "
   from ciris_engine.logic.audit.signing_protocol import UnifiedSigningKey
   key = UnifiedSigningKey()
   sig = key.sign(b'test')
   print('Signing works!' if sig else 'Signing failed')
   "
   ```

## Impact Assessment

- **Memory Benchmark**: Slowed due to error handling on every action
- **Normal Operations**: All actions fail with hash chain errors
- **Audit Trail**: No new entries can be signed
- **Attestation**: Works (uses separate path) but context building fails

## Recommendations

1. **Immediate**: Regenerate keys without hardware binding for development
2. **Short-term**: Add configuration option to allow software fallback
3. **Long-term**: Implement proper key migration tooling
