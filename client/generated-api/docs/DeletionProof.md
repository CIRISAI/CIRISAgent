
# DeletionProof

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **deletionId** | **kotlin.String** | Unique deletion request ID |  |
| **userIdentifier** | **kotlin.String** | User identifier for deleted data |  |
| **sourcesDeleted** | [**kotlin.collections.Map&lt;kotlin.String, kotlin.Any&gt;**](kotlin.Any.md) | Sources and records deleted |  |
| **deletedAt** | **kotlin.String** | ISO 8601 deletion timestamp |  |
| **verificationHash** | **kotlin.String** | SHA-256 hash of deletion details |  |
| **signature** | **kotlin.String** | RSA-PSS signature (base64) |  |
| **publicKeyId** | **kotlin.String** | ID of RSA key used for signing |  |
