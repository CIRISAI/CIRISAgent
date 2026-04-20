
# EmergencyShutdownStatus

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **commandReceived** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | When command was received |  |
| **commandVerified** | **kotlin.Boolean** | Whether signature was verified |  |
| **verificationError** | **kotlin.String** |  |  [optional] |
| **shutdownInitiated** | [**kotlin.time.Instant**](kotlin.time.Instant.md) |  |  [optional] |
| **servicesStopped** | **kotlin.collections.List&lt;kotlin.String&gt;** | Services stopped |  [optional] |
| **dataPersisted** | **kotlin.Boolean** | Whether data was saved |  [optional] |
| **finalMessageSent** | **kotlin.Boolean** | Whether final message was sent |  [optional] |
| **shutdownCompleted** | [**kotlin.time.Instant**](kotlin.time.Instant.md) |  |  [optional] |
| **exitCode** | **kotlin.Int** |  |  [optional] |
