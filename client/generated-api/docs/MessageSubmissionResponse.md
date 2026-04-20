
# MessageSubmissionResponse

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **messageId** | **kotlin.String** | Unique message ID for tracking |  |
| **channelId** | **kotlin.String** | Channel where message was sent |  |
| **submittedAt** | **kotlin.String** | ISO timestamp of submission |  |
| **accepted** | **kotlin.Boolean** | Whether message was accepted for processing |  |
| **taskId** | **kotlin.String** |  |  [optional] |
| **rejectionReason** | [**MessageRejectionReason**](MessageRejectionReason.md) |  |  [optional] |
| **rejectionDetail** | **kotlin.String** |  |  [optional] |
