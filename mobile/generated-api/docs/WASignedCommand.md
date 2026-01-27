
# WASignedCommand

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **commandId** | **kotlin.String** | Unique command identifier |  |
| **commandType** | [**EmergencyCommandType**](EmergencyCommandType.md) | Type of emergency command |  |
| **waId** | **kotlin.String** | ID of issuing WA |  |
| **waPublicKey** | **kotlin.String** | Public key of issuing WA |  |
| **issuedAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | When command was issued |  |
| **reason** | **kotlin.String** | Reason for emergency command |  |
| **signature** | **kotlin.String** | Ed25519 signature of command data |  |
| **expiresAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) |  |  [optional] |
| **targetAgentId** | **kotlin.String** |  |  [optional] |
| **targetTreePath** | **kotlin.collections.List&lt;kotlin.String&gt;** |  |  [optional] |
| **parentCommandId** | **kotlin.String** |  |  [optional] |
| **relayChain** | **kotlin.collections.List&lt;kotlin.String&gt;** | WA IDs in relay chain |  [optional] |
