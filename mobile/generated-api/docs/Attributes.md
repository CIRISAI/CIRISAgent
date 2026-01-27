
# Attributes

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **createdBy** | **kotlin.String** | Who created this node |  |
| **content** | **kotlin.String** |  |  |
| **memoryType** | **kotlin.String** | Type: fact, experience, learning, insight, observation |  |
| **source** | **kotlin.String** | Where this memory originated |  |
| **key** | **kotlin.String** | Configuration key (unique within scope) |  |
| **&#x60;value&#x60;** | **kotlin.Double** | Numeric value of the metric |  |
| **description** | **kotlin.String** | What this configuration controls |  |
| **category** | **kotlin.String** | Category: system, behavioral, ethical, operational |  |
| **valueType** | **kotlin.String** | Expected type: string, integer, float, boolean, list, dict |  |
| **metricName** | **kotlin.String** | Name of the metric |  |
| **metricType** | **kotlin.String** | Type: counter, gauge, histogram, summary |  |
| **startTime** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | Start of measurement period |  |
| **endTime** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | End of measurement period |  |
| **durationSeconds** | **kotlin.Double** | Duration of measurement period |  |
| **serviceName** | **kotlin.String** | Service that generated this metric |  |
| **logMessage** | **kotlin.String** | The log message content |  |
| **logLevel** | **kotlin.String** | Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL |  |
| **createdAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) |  |  [optional] |
| **updatedAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) |  |  [optional] |
| **updatedBy** | **kotlin.String** |  |  [optional] |
| **tags** | **kotlin.collections.List&lt;kotlin.String&gt;** | Tags for categorization |  [optional] |
| **version** | **kotlin.Int** | Schema version for migration support |  [optional] |
| **secretRefs** | **kotlin.collections.List&lt;kotlin.String&gt;** | Secret reference UUIDs for encrypted data |  [optional] |
| **contentType** | **kotlin.String** | Type of content: text, embedding, reference |  [optional] |
| **importance** | **kotlin.Double** | Importance score from 0.0 to 1.0 |  [optional] |
| **confidence** | **kotlin.Double** | Confidence in this memory from 0.0 to 1.0 |  [optional] |
| **sourceType** | **kotlin.String** | Source type: internal, user, system, external |  [optional] |
| **channelId** | **kotlin.String** |  |  [optional] |
| **userId** | **kotlin.String** |  |  [optional] |
| **taskId** | **kotlin.String** |  |  [optional] |
| **accessCount** | **kotlin.Int** | Number of times accessed |  [optional] |
| **lastAccessed** | [**kotlin.time.Instant**](kotlin.time.Instant.md) |  |  [optional] |
| **relatedMemories** | **kotlin.collections.List&lt;kotlin.String&gt;** | IDs of related memory nodes |  [optional] |
| **derivedFrom** | **kotlin.String** |  |  [optional] |
| **embeddingModel** | **kotlin.String** |  |  [optional] |
| **embeddingDimensions** | **kotlin.Int** |  |  [optional] |
| **validationRules** | **kotlin.collections.List&lt;kotlin.collections.Map&lt;kotlin.String, ResponseGetSystemStatusV1TransparencyStatusGetValue&gt;&gt;** | Validation rules for this config |  [optional] |
| **isSensitive** | **kotlin.Boolean** | Whether this contains sensitive data |  [optional] |
| **requiresAuthority** | **kotlin.Boolean** | Whether changes require WiseAuthority approval |  [optional] |
| **previousValue** | [**kotlin.Any**](.md) | Previous value before last update |  [optional] |
| **changeReason** | **kotlin.String** |  |  [optional] |
| **approvedBy** | **kotlin.String** |  |  [optional] |
| **scope** | **kotlin.String** | Scope: system, channel, user |  [optional] |
| **appliesTo** | **kotlin.collections.List&lt;kotlin.String&gt;** | Specific entities this applies to |  [optional] |
| **isActive** | **kotlin.Boolean** | Whether this config is currently active |  [optional] |
| **expiresAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) |  |  [optional] |
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
| **logTags** | **kotlin.collections.Map&lt;kotlin.String, kotlin.String&gt;** | Additional tags for the log entry |  [optional] |
| **retentionPolicy** | **kotlin.String** | Retention policy for this log |  [optional] |
