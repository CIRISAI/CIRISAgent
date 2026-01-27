
# ModuleTypeInfo

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **moduleId** | **kotlin.String** | Unique module identifier (e.g., &#39;api&#39;, &#39;mcp_client&#39;) |  |
| **name** | **kotlin.String** | Human-readable module name |  |
| **version** | **kotlin.String** | Module version |  |
| **description** | **kotlin.String** | Module description |  |
| **author** | **kotlin.String** | Module author |  |
| **moduleSource** | **kotlin.String** | Source: &#39;core&#39; for built-in or &#39;modular&#39; for plugin |  |
| **serviceTypes** | **kotlin.collections.List&lt;kotlin.String&gt;** | Service types provided (e.g., TOOL, COMMUNICATION) |  [optional] |
| **capabilities** | **kotlin.collections.List&lt;kotlin.String&gt;** | Capabilities provided |  [optional] |
| **configurationSchema** | [**kotlin.collections.List&lt;ModuleConfigParameter&gt;**](ModuleConfigParameter.md) | Configuration parameters and their types |  [optional] |
| **requiresExternalDeps** | **kotlin.Boolean** | Whether module requires external packages |  [optional] |
| **externalDependencies** | **kotlin.collections.Map&lt;kotlin.String, kotlin.String&gt;** | External package dependencies with version constraints |  [optional] |
| **isMock** | **kotlin.Boolean** | Whether this is a mock/test module |  [optional] |
| **safeDomain** | **kotlin.String** |  |  [optional] |
| **prohibited** | **kotlin.collections.List&lt;kotlin.String&gt;** | Prohibited use cases |  [optional] |
| **metadata** | [**kotlin.collections.Map&lt;kotlin.String, ModuleTypeInfoMetadataValue&gt;**](ModuleTypeInfoMetadataValue.md) |  |  [optional] |
| **platformRequirements** | **kotlin.collections.List&lt;kotlin.String&gt;** | Platform requirements (e.g., &#39;android_play_integrity&#39;, &#39;google_native_auth&#39;) |  [optional] |
| **platformRequirementsRationale** | **kotlin.String** |  |  [optional] |
| **platformAvailable** | **kotlin.Boolean** | Whether this adapter is available on the current platform |  [optional] |
