
# ConsentDecayStatus

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **userId** | **kotlin.String** | User being forgotten |  |
| **decayStarted** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | When decay began |  |
| **identitySevered** | **kotlin.Boolean** | Identity disconnected from patterns |  |
| **patternsAnonymized** | **kotlin.Boolean** | Patterns converted to anonymous |  |
| **decayCompleteAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | When decay will complete (90 days) |  |
| **safetyPatternsRetained** | **kotlin.Int** | Patterns kept for safety |  [optional] |
