
# ToolInfo

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **name** | **kotlin.String** | Tool name |  |
| **description** | **kotlin.String** | What the tool does |  |
| **parameters** | [**ToolParameterSchema**](ToolParameterSchema.md) | Tool parameters schema |  |
| **category** | **kotlin.String** | Tool category |  [optional] |
| **cost** | **kotlin.Double** | Cost to execute the tool |  [optional] |
| **whenToUse** | **kotlin.String** |  |  [optional] |
| **contextEnrichment** | **kotlin.Boolean** | If True, tool is automatically run during context gathering to enrich ASPDMA prompt |  [optional] |
| **contextEnrichmentParams** | [**kotlin.collections.Map&lt;kotlin.String, ResponseGetSystemStatusV1TransparencyStatusGetValue&gt;**](ResponseGetSystemStatusV1TransparencyStatusGetValue.md) |  |  [optional] |
| **platformRequirements** | [**kotlin.collections.List&lt;PlatformRequirement&gt;**](PlatformRequirement.md) | Platform security requirements (e.g., ANDROID_PLAY_INTEGRITY, DPOP) |  [optional] |
| **platformRequirementsRationale** | **kotlin.String** |  |  [optional] |
