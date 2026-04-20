
# TelemetryQuery

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **queryType** | **kotlin.String** | Query type: metrics|traces|logs|incidents|insights |  |
| **filters** | [**TelemetryQueryFilters**](TelemetryQueryFilters.md) | Query filters |  [optional] |
| **aggregations** | **kotlin.collections.List&lt;kotlin.String&gt;** |  |  [optional] |
| **startTime** | [**kotlin.time.Instant**](kotlin.time.Instant.md) |  |  [optional] |
| **endTime** | [**kotlin.time.Instant**](kotlin.time.Instant.md) |  |  [optional] |
| **limit** | **kotlin.Int** | Result limit |  [optional] |
