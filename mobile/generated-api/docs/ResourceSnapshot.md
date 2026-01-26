
# ResourceSnapshot

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **memoryMb** | **kotlin.Int** | Memory usage in MB |  [optional] |
| **memoryPercent** | **kotlin.Int** | Memory usage percentage |  [optional] |
| **cpuPercent** | **kotlin.Int** | CPU usage percentage |  [optional] |
| **cpuAverage1m** | **kotlin.Int** | 1-minute CPU average |  [optional] |
| **tokensUsedHour** | **kotlin.Int** | Tokens used in current hour |  [optional] |
| **tokensUsedDay** | **kotlin.Int** | Tokens used today |  [optional] |
| **diskUsedMb** | **kotlin.Int** | Disk space used in MB |  [optional] |
| **diskFreeMb** | **kotlin.Int** | Free disk space in MB |  [optional] |
| **thoughtsActive** | **kotlin.Int** | Number of active thoughts |  [optional] |
| **thoughtsQueued** | **kotlin.Int** | Number of queued thoughts |  [optional] |
| **healthy** | **kotlin.Boolean** | Overall health status |  [optional] |
| **warnings** | **kotlin.collections.List&lt;kotlin.String&gt;** | Active warnings |  [optional] |
| **critical** | **kotlin.collections.List&lt;kotlin.String&gt;** | Critical issues |  [optional] |
