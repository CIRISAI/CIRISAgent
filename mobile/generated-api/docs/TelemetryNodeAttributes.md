
# TelemetryNodeAttributes

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **createdBy** | **kotlin.String** | Service or user that created this node |  |
| **metricName** | **kotlin.String** | Name of the metric |  |
| **metricType** | **kotlin.String** | Type: counter, gauge, histogram, summary |  |
| **&#x60;value&#x60;** | **kotlin.Double** | Numeric value of the metric |  |
| **startTime** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | Start of measurement period |  |
| **endTime** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | End of measurement period |  |
| **durationSeconds** | **kotlin.Double** | Duration of measurement period |  |
| **serviceName** | **kotlin.String** | Service that generated this metric |  |
| **createdAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | When this node was created |  [optional] |
| **updatedAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | When this node was last updated |  [optional] |
| **updatedBy** | **kotlin.String** |  |  [optional] |
| **tags** | **kotlin.collections.List&lt;kotlin.String&gt;** | Tags for categorization and search |  [optional] |
| **version** | **kotlin.Int** | Schema version for migration support |  [optional] |
| **secretRefs** | **kotlin.collections.List&lt;kotlin.String&gt;** | Secret reference UUIDs for encrypted data |  [optional] |
| **unit** | **kotlin.String** |  |  [optional] |
| **aggregationType** | **kotlin.String** |  |  [optional] |
| **sampleCount** | **kotlin.Int** | Number of samples in this metric |  [optional] |
| **minValue** | **kotlin.Double** |  |  [optional] |
| **maxValue** | **kotlin.Double** |  |  [optional] |
| **meanValue** | **kotlin.Double** |  |  [optional] |
| **stdDeviation** | **kotlin.Double** |  |  [optional] |
| **percentiles** | **kotlin.collections.Map&lt;kotlin.String, kotlin.Double&gt;** | Percentile values (e.g., p50, p95, p99) |  [optional] |
| **labels** | **kotlin.collections.Map&lt;kotlin.String, kotlin.String&gt;** | Metric labels for filtering and grouping |  [optional] |
| **host** | **kotlin.String** |  |  [optional] |
| **warningThreshold** | **kotlin.Double** |  |  [optional] |
| **criticalThreshold** | **kotlin.Double** |  |  [optional] |
| **thresholdDirection** | **kotlin.String** |  |  [optional] |
| **resourceType** | **kotlin.String** |  |  [optional] |
| **resourceLimit** | **kotlin.Double** |  |  [optional] |
