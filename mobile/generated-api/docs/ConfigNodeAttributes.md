
# ConfigNodeAttributes

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **createdBy** | **kotlin.String** | Service or user that created this node |  |
| **key** | **kotlin.String** | Configuration key (unique within scope) |  |
| **&#x60;value&#x60;** | [**kotlin.Any**](.md) | Configuration value |  |
| **description** | **kotlin.String** | What this configuration controls |  |
| **category** | **kotlin.String** | Category: system, behavioral, ethical, operational |  |
| **valueType** | **kotlin.String** | Expected type: string, integer, float, boolean, list, dict |  |
| **createdAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | When this node was created |  [optional] |
| **updatedAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | When this node was last updated |  [optional] |
| **updatedBy** | **kotlin.String** |  |  [optional] |
| **tags** | **kotlin.collections.List&lt;kotlin.String&gt;** | Tags for categorization and search |  [optional] |
| **version** | **kotlin.Int** | Schema version for migration support |  [optional] |
| **secretRefs** | **kotlin.collections.List&lt;kotlin.String&gt;** | Secret reference UUIDs for encrypted data |  [optional] |
| **validationRules** | **kotlin.collections.List&lt;kotlin.collections.Map&lt;kotlin.String, ResponseGetSystemStatusV1TransparencyStatusGetValue&gt;?&gt;** | Validation rules for this config |  [optional] |
| **isSensitive** | **kotlin.Boolean** | Whether this contains sensitive data |  [optional] |
| **requiresAuthority** | **kotlin.Boolean** | Whether changes require WiseAuthority approval |  [optional] |
| **previousValue** | [**kotlin.Any**](.md) | Previous value before last update |  [optional] |
| **changeReason** | **kotlin.String** |  |  [optional] |
| **approvedBy** | **kotlin.String** |  |  [optional] |
| **scope** | **kotlin.String** | Scope: system, channel, user |  [optional] |
| **appliesTo** | **kotlin.collections.List&lt;kotlin.String&gt;** | Specific entities this applies to |  [optional] |
| **isActive** | **kotlin.Boolean** | Whether this config is currently active |  [optional] |
| **expiresAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) |  |  [optional] |
