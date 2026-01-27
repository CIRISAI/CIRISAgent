
# PendingDeferral

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **deferralId** | **kotlin.String** | Unique deferral identifier |  |
| **createdAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | When deferral was created |  |
| **deferredBy** | **kotlin.String** | Agent that deferred |  |
| **taskId** | **kotlin.String** | Associated task ID |  |
| **thoughtId** | **kotlin.String** | Associated thought ID |  |
| **reason** | **kotlin.String** | Reason for deferral |  |
| **channelId** | **kotlin.String** |  |  [optional] |
| **userId** | **kotlin.String** |  |  [optional] |
| **priority** | **kotlin.String** | Deferral priority |  [optional] |
| **assignedWaId** | **kotlin.String** |  |  [optional] |
| **requiresRole** | **kotlin.String** |  |  [optional] |
| **status** | **kotlin.String** | Current status |  [optional] |
| **resolution** | **kotlin.String** |  |  [optional] |
| **resolvedAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) |  |  [optional] |
| **question** | **kotlin.String** |  |  [optional] |
| **context** | **kotlin.collections.Map&lt;kotlin.String, kotlin.String&gt;** | Additional context for UI |  [optional] |
| **timeoutAt** | **kotlin.String** |  |  [optional] |
