
# AgentTemplate

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **id** | **kotlin.String** | Template ID |  |
| **name** | **kotlin.String** | Display name |  |
| **description** | **kotlin.String** | Template description |  |
| **identity** | **kotlin.String** | Agent identity/purpose |  |
| **stewardshipTier** | **kotlin.Int** | Book VI Stewardship Tier (1-5, higher &#x3D; more oversight) |  |
| **creatorId** | **kotlin.String** | Creator/team identifier who signed this template |  |
| **signature** | **kotlin.String** | Cryptographic signature verifying template authenticity |  |
| **exampleUseCases** | **kotlin.collections.List&lt;kotlin.String&gt;** | Example use cases |  [optional] |
| **supportedSops** | **kotlin.collections.List&lt;kotlin.String&gt;** | Supported Standard Operating Procedures (SOPs) for ticket workflows |  [optional] |
