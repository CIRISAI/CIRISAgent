
# DetailedMetric

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **name** | **kotlin.String** | Metric name |  |
| **currentValue** | **kotlin.Double** | Current value |  |
| **unit** | **kotlin.String** |  |  [optional] |
| **trend** | **kotlin.String** | Trend: up|down|stable |  [optional] |
| **hourlyAverage** | **kotlin.Double** | Average over last hour |  [optional] |
| **dailyAverage** | **kotlin.Double** | Average over last day |  [optional] |
| **byService** | [**kotlin.collections.List&lt;ServiceMetricValue&gt;**](ServiceMetricValue.md) | Values by service |  [optional] |
| **recentData** | [**kotlin.collections.List&lt;MetricData&gt;**](MetricData.md) | Recent data points |  [optional] |
