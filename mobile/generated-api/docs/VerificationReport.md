
# VerificationReport

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **verified** | **kotlin.Boolean** | Whether integrity check passed |  |
| **totalEntries** | **kotlin.Int** | Total audit entries checked |  |
| **validEntries** | **kotlin.Int** | Entries with valid signatures |  |
| **invalidEntries** | **kotlin.Int** | Entries with invalid signatures |  |
| **chainIntact** | **kotlin.Boolean** | Whether hash chain is intact |  |
| **verificationStarted** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | Verification start time |  |
| **verificationCompleted** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | Verification end time |  |
| **durationMs** | **kotlin.Double** | Verification duration in milliseconds |  |
| **missingEntries** | **kotlin.Int** | Entries missing from chain |  [optional] |
| **lastValidEntry** | **kotlin.String** |  |  [optional] |
| **firstInvalidEntry** | **kotlin.String** |  |  [optional] |
| **errors** | **kotlin.collections.List&lt;kotlin.String&gt;** | Errors encountered |  [optional] |
| **warnings** | **kotlin.collections.List&lt;kotlin.String&gt;** | Warnings encountered |  [optional] |
