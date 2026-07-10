package ai.ciris.mobile.shared.models.federation

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Wire model for the result of **minting a hardware-rooted USER federation
 * identity** — the response of `POST {localNode}/v1/self/identity`.
 *
 * ARCHITECTURE: the app holds NO keys and performs NO crypto. The founder's
 * federation identity (a hybrid Ed25519 + ML-DSA-65 keypair) is minted by THIS
 * device's local ciris-server in its keyring/substrate — custodied by a YubiKey
 * (PKCS#11), TPM/Secure-Enclave (platform-sealed), or a software seed (dev). The
 * app only DRIVES the mint and surfaces the public result below.
 *
 * Mirrors `CIRISServer/src/identity.rs` `self_identity_handler` (the flat JSON
 * object it returns):
 *   { key_id, fedcode, identity_type, pubkey_ed25519_base64,
 *     pubkey_ml_dsa_65_base64, hardware_type }
 *
 * NOTE the server returns the keypair as TWO discrete base64 pubkey fields
 * (`pubkey_ed25519_base64` + `pubkey_ml_dsa_65_base64`), not a `pubkeys` map.
 * They are gathered into [pubkeys] here for an ergonomic UI surface.
 */
@Serializable
data class MintedIdentity(
    /** The federation `key_id` (FSD-002 `label-fingerprint` form when a label
     *  was supplied; else derived from the Ed25519 pubkey). */
    @SerialName("key_id")
    val keyId: String,
    /** The shareable **fedcode** — a `CIRIS-V2-…` usercode (FedKind::User). */
    val fedcode: String,
    /** Always `"user"` for this endpoint (it mints a USER identity). */
    @SerialName("identity_type")
    val identityType: String = "user",
    /** The honest custody tier the local node's signer reported, e.g.
     *  `SoftwareOnly`, `Tpm2`, `Pkcs11`/`YubiKey`. */
    @SerialName("hardware_type")
    val hardwareType: String? = null,
    /** Ed25519 signing public key, base64 standard. */
    @SerialName("pubkey_ed25519_base64")
    val pubkeyEd25519Base64: String? = null,
    /** ML-DSA-65 PQC public key, base64 standard. */
    @SerialName("pubkey_ml_dsa_65_base64")
    val pubkeyMlDsa65Base64: String? = null,
) {
    /** The two pubkeys keyed by algorithm, for an ergonomic UI surface. Only
     *  non-null halves are included. */
    val pubkeys: Map<String, String>
        get() = buildMap {
            pubkeyEd25519Base64?.let { put("ed25519", it) }
            pubkeyMlDsa65Base64?.let { put("ml_dsa_65", it) }
        }

    /** A friendly hardware-tier label for the UI: "YubiKey" / "TPM / Secure
     *  Enclave" / "software". Falls back to the raw [hardwareType]. */
    val hardwareLabel: String
        get() = when {
            hardwareType == null -> "software"
            hardwareType.contains("pkcs11", ignoreCase = true) ||
                hardwareType.contains("yubikey", ignoreCase = true) ||
                hardwareType.contains("Piv", ignoreCase = true) -> "YubiKey"
            hardwareType.contains("tpm", ignoreCase = true) ||
                hardwareType.contains("enclave", ignoreCase = true) ||
                hardwareType.contains("sealed", ignoreCase = true) -> "TPM / Secure Enclave"
            hardwareType.contains("software", ignoreCase = true) -> "software"
            else -> hardwareType
        }
}

/**
 * Request body for `POST {localNode}/v1/self/identity`. All fields optional; an
 * empty body is valid (the local node defaults the backend to `platform-sealed`
 * and the key_id alias to `<node>-user`). Mirrors `SelfIdentityRequest` in
 * `CIRISServer/src/identity.rs`.
 */
@Serializable
data class MintIdentityRequest(
    /** Custody backend hint: `pkcs11` (YubiKey) | `platform-sealed` | `software`. */
    val backend: String? = null,
    /** The human's display name → the FSD-002 `label-fingerprint` key_id. */
    val label: String? = null,
    /** Optional explicit user-identity alias (defaults to `<node>-user`). */
    @SerialName("key_id")
    val keyId: String? = null,
    /** For the `pkcs11` backend: provision an empty PIV slot via `ykman`. */
    val provision: Boolean? = null,
    /** For the `pkcs11` backend: the PIV slot (default `9c`). */
    @SerialName("piv_slot")
    val pivSlot: String? = null,
)
