# BUG: CIRISVerify Reports hardware_backed=false When Ed25519 Key IS Hardware-Backed

## Summary

CIRISVerify unified attestation reports `hardware_backed=false` even though the Ed25519 signing key IS hardware-backed (TEE). The attestation appears to report the wallet seed's status instead of the Ed25519 key's status.

**The TrustPage UI simply displays what CIRISVerify returns - no local overrides.** The fix must be in CIRISVerify.

## Evidence from Device Logs

```
# Ed25519 key correctly uses hardware-backed storage:
INFO: ciris_verify: [ciris_keyring::software] VERIFY MutableEd25519Signer::has_key - hardware wrapper check, has_key=true, hardware_backed=true

# But wallet seed explicitly uses software-only:
INFO: ciris_verify: [ciris_keyring::storage] Using software-only secure storage for wallet seeds, alias=agent_signing
INFO: ciris_verify: [ciris_keyring::software] get_wallet_seed: generated and stored new wallet seed, hardware_backed=false
```

## Impact

1. **Wrong attestation level**: `hardware_backed=false` causes lower trust level despite hardware being available
2. **UI shows wrong status**: Hardware Keystore shows "Software fallback" even though Ed25519 IS in TEE
3. **Platform misreporting**: Shows "linux" instead of "android"

## Expected Behavior

CIRISVerify unified attestation should report:
1. `hardware_backed=true` when Ed25519 key is in hardware (TEE/SE/Keystore)
2. `platform_os="android"` on Android (not "linux")
3. Wallet seeds should ALSO use hardware-backed storage when available

## Root Cause Analysis

The wallet seed storage path in CIRISVerify explicitly uses `software-only secure storage` regardless of hardware capability. This appears to be a separate code path from the Ed25519 key storage.

## Root Cause Found (v1.3.8 diagnostic)

```
signer_hw_backed=true, running_in_vm=true, hardware_backed=false, hardware_type=AndroidKeystore
```

**The VM/emulator detection is a FALSE POSITIVE!**

- `signer_hw_backed=true` - Ed25519 key IS hardware-backed ✓
- `running_in_vm=true` - Incorrectly detecting real device as VM ❌
- `hardware_backed=false` - Forced to false due to VM detection

The older Samsung SM-J700T is being incorrectly flagged as an emulator, which overrides the actual hardware-backed status.

## Affected Version

CIRISVerify v1.3.8 (with diagnostic logging)

## Device Info

- Model: Samsung SM-J700T (older device without StrongBox, but HAS TEE)
- Android Version: (older)
- Ed25519: Hardware-backed via TEE ✓
- Wallet Seed: Software-only ✗

## Proposed Fix (in ciris-verify Rust repo)

### Issue 1: hardware_backed reports wrong key
The unified attestation's `hardware_backed` field should report the Ed25519 signing key's status, NOT the wallet seed's status. The Ed25519 key is what matters for signing attestations.

### Issue 2: Wallet seeds should use hardware when available
In `ciris_keyring` module, `get_wallet_seed` should use the same hardware-backed storage as Ed25519 when available.

### Issue 3: Platform should report "android" not "linux"
CIRISVerify should detect Android specifically (check for `/system/build.prop` or similar) and report `platform_os="android"` instead of "linux".

## Files to Investigate (in ciris-verify Rust repo)

- `ciris_keyring/src/storage.rs` - wallet seed storage selection
- `ciris_keyring/src/platform/android.rs` - Android-specific storage
- Platform detection logic

## Workaround

None currently. Wallet operations are less secure than they could be on hardware-capable devices.
