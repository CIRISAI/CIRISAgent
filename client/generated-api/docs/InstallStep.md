
# InstallStep

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **id** | **kotlin.String** | Unique step identifier |  |
| **kind** | **kotlin.String** | Install method: brew, apt, pip, npm, manual, winget, choco |  |
| **label** | **kotlin.String** | Human-readable step description |  |
| **formula** | **kotlin.String** |  |  [optional] |
| **&#x60;package&#x60;** | **kotlin.String** |  |  [optional] |
| **command** | **kotlin.String** |  |  [optional] |
| **url** | **kotlin.String** |  |  [optional] |
| **providesBinaries** | **kotlin.collections.List&lt;kotlin.String&gt;** | Binary names this step provides |  [optional] |
| **verifyCommand** | **kotlin.String** |  |  [optional] |
| **platforms** | **kotlin.collections.List&lt;kotlin.String&gt;** | Platforms this step applies to. Empty &#x3D; all |  [optional] |
