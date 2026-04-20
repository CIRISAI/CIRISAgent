
# EntryVerification

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **signatureValid** | **kotlin.Boolean** | Whether signature is valid |  |
| **hashChainValid** | **kotlin.Boolean** | Whether hash chain is intact |  |
| **verifiedAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | When verification occurred |  |
| **verifier** | **kotlin.String** | Who performed verification |  [optional] |
| **algorithm** | **kotlin.String** | Hash algorithm used |  [optional] |
| **previousHashMatch** | **kotlin.Boolean** |  |  [optional] |
