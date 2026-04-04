# Bug Report: CIRISVerify hardware_backed Discrepancy

**Date**: 2026-04-04
**Reporter**: Claude Code (Automated Analysis)
**Severity**: Medium - Affects wallet gasless transfer eligibility display
**Components**: CIRISVerify (Rust), TrustPage.kt (KMP UI)

---

## Summary

The Trust & Security page shows "Hardware Keystore: Software fallback" with a red X even though the Ed25519 signing key IS hardware-backed (Android Keystore TEE). This prevents the user from understanding their actual security posture.

---

## Evidence from Device Logs

```
# Ed25519 key initialization - reports hardware_backed=true
[CIRISVerify] Ed25519 signer init complete, hardware_backed=true, hardware_type=AndroidKeystore, encryption=AES-256-GCM

# Wallet seed generation - reports hardware_backed=false
[CIRISVerify] get_wallet_seed: generated and stored new wallet seed, hardware_backed=false

# Unified attestation - uses hardware_backed=false
[CIRISVerify] Unified attestation complete, key_type=local, hardware_backed=false
```

---

## Root Cause Analysis

### Issue 1: CIRISVerify Returns Wallet Seed Status, Not Ed25519 Key Status

The `key_attestation` section of the unified attestation response contains:
- `hardware_backed`: From wallet seed, NOT from Ed25519 key
- `storage_mode`: From wallet seed, NOT from Ed25519 key

The Ed25519 signing key reports `hardware_backed=true` during initialization, but the unified attestation's `key_attestation.hardware_backed` field is `false` because it reports the wallet seed's backing status.

**Expected Behavior**: The `key_attestation.hardware_backed` field should reflect the Ed25519 signing key's status, which is the PRIMARY security key for agent identity.

**Why Wallet Seed Differs**: On Android devices with Keystore TEE but without StrongBox, the Ed25519 key can be stored in the TEE, but secp256k1 wallet key derivation may fall back to software because some TEE implementations don't support all cryptographic operations.

### Issue 2: TrustPage.kt UI Check Is Too Strict

**Code Location**: `mobile/shared/src/commonMain/kotlin/ai/ciris/mobile/shared/ui/screens/TrustPage.kt:1446-1447`

```kotlin
val hasHwEncryption = status.hardwareBacked &&
    status.keyStorageMode?.contains("HW", ignoreCase = true) == true
```

This check requires:
1. `hardwareBacked = true` (from API)
2. `keyStorageMode` must contain "HW" (case-insensitive)

**Problem**: CIRISVerify returns `storage_mode` values like:
- `"TEE"` - Android TrustZone
- `"SOFTWARE"` - Software fallback
- `"STRONGBOX"` - Hardware security module

None of these contain "HW", so the check ALWAYS fails even when using TEE hardware.

---

## Device Information

- **Device**: Samsung Galaxy (without StrongBox)
- **Security Hardware**: Android Keystore with TEE (TrustZone)
- **StrongBox Available**: No
- **TPM**: No (Android device)
- **Play Integrity**: Failed (Error -16: Invalid cloud project number)

---

## Impact

1. **User Confusion**: Users see "Software fallback" red X when their device actually has hardware security (TEE)
2. **Wallet Status**: "Gasless transfers unavailable" message may be misleading since actual security is better than displayed
3. **Trust Assessment**: Attestation level stuck at 1 (receive-only) when it should potentially be higher

---

## Recommended Fixes

### Fix 1: CIRISVerify Backend (Verify Team)

Update unified attestation to include BOTH key statuses:

```json
{
  "key_attestation": {
    "ed25519_hardware_backed": true,
    "ed25519_storage_mode": "TEE",
    "wallet_seed_hardware_backed": false,
    "wallet_seed_storage_mode": "SOFTWARE",
    "hardware_backed": true,  // Use Ed25519 status for identity
    "storage_mode": "TEE"     // Use Ed25519 status for identity
  }
}
```

OR at minimum, ensure `hardware_backed` in key_attestation reflects the Ed25519 key, not the wallet seed.

### Fix 2: TrustPage.kt UI (Mobile Team)

**Option A**: Remove the `keyStorageMode` check entirely:
```kotlin
val hasHwEncryption = status.hardwareBacked  // Trust the API
```

**Option B**: Update check to recognize TEE:
```kotlin
val hasHwEncryption = status.hardwareBacked &&
    (status.keyStorageMode?.contains("HW", ignoreCase = true) == true ||
     status.keyStorageMode?.contains("TEE", ignoreCase = true) == true ||
     status.keyStorageMode?.contains("STRONGBOX", ignoreCase = true) == true)
```

**Option C**: Add separate display for Ed25519 and wallet key status:
```kotlin
// Show Ed25519 key status (identity)
DetailRow(label = "Identity Key", value = "Hardware-backed (TEE)", ok = true)

// Show wallet key status separately
DetailRow(label = "Wallet Key", value = "Software", ok = false)
```

---

## Reproduction Steps

1. Install CIRIS debug APK on Android device without StrongBox
2. Complete setup wizard with local authentication
3. Navigate to Trust & Security page
4. Observe "Hardware Keystore: Software fallback" with red X
5. Check logs for Ed25519 hardware_backed=true vs unified hardware_backed=false

---

## Related Files

- `ciris_adapters/ciris_verify/ffi_bindings/client.py` - FFI client receiving attestation
- `ciris_engine/logic/services/infrastructure/authentication/attestation/result_builder.py:302-303` - Extracts key_attestation
- `ciris_engine/logic/adapters/api/routes/setup/attestation.py:212` - API response mapping
- `mobile/shared/src/commonMain/kotlin/ai/ciris/mobile/shared/ui/screens/TrustPage.kt:1446-1463` - UI display logic

---

## Priority Assessment

**Recommend Medium Priority** because:
- Does not affect actual security (just display)
- Gasless transfers have other blockers (Play Integrity)
- Fix requires CIRISVerify binary update

**Would be High Priority** if:
- Causing users to distrust secure devices
- Blocking legitimate wallet operations
