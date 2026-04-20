
# AgentIdentity

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **agentId** | **kotlin.String** | Unique agent identifier |  |
| **name** | **kotlin.String** | Agent name |  |
| **purpose** | **kotlin.String** | Agent&#39;s purpose |  |
| **createdAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | When agent was created |  |
| **lineage** | [**AgentLineage**](AgentLineage.md) | Agent lineage information |  |
| **varianceThreshold** | **kotlin.Double** | Identity variance threshold |  |
| **tools** | **kotlin.collections.List&lt;kotlin.String&gt;** | Available tools |  |
| **handlers** | **kotlin.collections.List&lt;kotlin.String&gt;** | Active handlers |  |
| **services** | [**ServiceAvailability**](ServiceAvailability.md) | Service availability |  |
| **permissions** | **kotlin.collections.List&lt;kotlin.String&gt;** | Agent permissions |  |
