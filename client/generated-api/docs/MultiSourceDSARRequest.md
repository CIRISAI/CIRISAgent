
# MultiSourceDSARRequest

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **requestType** | **kotlin.String** | Type of request: access, delete, export, or correct |  |
| **email** | **kotlin.String** | Contact email for the request |  |
| **userIdentifier** | **kotlin.String** | Primary user identifier (email, Discord ID, etc.) |  |
| **exportFormat** | **kotlin.String** |  |  [optional] |
| **corrections** | [**kotlin.collections.Map&lt;kotlin.String, kotlin.Any&gt;**](kotlin.Any.md) |  |  [optional] |
| **details** | **kotlin.String** |  |  [optional] |
| **urgent** | **kotlin.Boolean** | Whether this is an urgent request |  [optional] |
