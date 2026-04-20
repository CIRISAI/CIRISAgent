
# ManualSignatureVerificationRequest

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **deletionId** | **kotlin.String** | Deletion request ID |  |
| **userIdentifier** | **kotlin.String** | User identifier |  |
| **sourcesDeleted** | [**kotlin.collections.Map&lt;kotlin.String, kotlin.Any&gt;**](kotlin.Any.md) | Sources and records deleted (for hash computation) |  |
| **deletedAt** | **kotlin.String** | ISO 8601 deletion timestamp |  |
| **verificationHash** | **kotlin.String** | SHA-256 hash to verify |  |
| **signature** | **kotlin.String** | Base64-encoded RSA signature |  |
| **publicKeyId** | **kotlin.String** | Public key ID used for signing |  |
