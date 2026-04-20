
# ToolRequirements

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **binaries** | [**kotlin.collections.List&lt;BinaryRequirement&gt;**](BinaryRequirement.md) | Required CLI binaries (all must be present) |  [optional] |
| **anyBinaries** | [**kotlin.collections.List&lt;BinaryRequirement&gt;**](BinaryRequirement.md) | Alternative binaries (at least one required) |  [optional] |
| **envVars** | [**kotlin.collections.List&lt;EnvVarRequirement&gt;**](EnvVarRequirement.md) | Required environment variables |  [optional] |
| **configKeys** | [**kotlin.collections.List&lt;ConfigRequirement&gt;**](ConfigRequirement.md) | Required CIRIS config keys |  [optional] |
| **platforms** | **kotlin.collections.List&lt;kotlin.String&gt;** | Supported platforms (darwin, linux, win32). Empty &#x3D; all |  [optional] |
