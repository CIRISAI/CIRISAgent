
# TransactionItem

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **transactionId** | **kotlin.String** | Unique transaction ID |  |
| **type** | **kotlin.String** | Transaction type: charge or credit |  |
| **amountMinor** | **kotlin.Int** | Amount in minor units (negative for charges, positive for credits) |  |
| **currency** | **kotlin.String** | Currency code (USD) |  |
| **description** | **kotlin.String** | Transaction description |  |
| **createdAt** | **kotlin.String** | Transaction timestamp (ISO format) |  |
| **balanceAfter** | **kotlin.Int** | Account balance after this transaction |  |
| **metadata** | [**kotlin.collections.Map&lt;kotlin.String, ResponseGetSystemStatusV1TransparencyStatusGetValue&gt;**](ResponseGetSystemStatusV1TransparencyStatusGetValue.md) |  |  [optional] |
| **transactionType** | **kotlin.String** |  |  [optional] |
| **externalTransactionId** | **kotlin.String** |  |  [optional] |
