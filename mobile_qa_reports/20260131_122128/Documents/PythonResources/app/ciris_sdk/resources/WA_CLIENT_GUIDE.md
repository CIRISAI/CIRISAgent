# Wise Authority SDK Client Guide

The Wise Authority (WA) client provides a simplified interface for human-in-the-loop oversight of CIRIS agent decisions.

## Overview

The WA client focuses on three core endpoints:
- **Deferrals**: View and resolve agent decision deferrals
- **Permissions**: Manage agent permissions
- **Integrated Guidance**: Provide guidance directly when resolving deferrals

## Usage

### Initialize Client

```python
from ciris_sdk import CIRISClient

async with CIRISClient(base_url="http://localhost:8080") as client:
    # Access WA functionality through client.wa
    deferrals = await client.wa.get_deferrals()
```

### Working with Deferrals

#### Get Deferrals
```python
# Get all deferrals
all_deferrals = await client.wa.get_deferrals()

# Filter by status
pending = await client.wa.get_deferrals(status="pending")
resolved = await client.wa.get_deferrals(status="resolved", limit=10)

# Convenience method for pending deferrals
pending_list = await client.wa.get_pending_deferrals()
```

#### Resolve Deferrals
```python
# Approve with guidance
await client.wa.approve_deferral(
    deferral_id="def_123",
    guidance="Proceed with caution and validate all inputs"
)

# Reject with reasoning
await client.wa.reject_deferral(
    deferral_id="def_456",
    reasoning="This violates content policy"
)

# Modify with new guidance
await client.wa.modify_deferral(
    deferral_id="def_789",
    guidance="Take an alternative approach",
    reasoning="Original approach has risks"
)

# Full control with resolve_deferral
await client.wa.resolve_deferral(
    deferral_id="def_999",
    resolution="custom_resolution",
    guidance="Custom guidance text",
    reasoning="Explanation of decision"
)
```

### Managing Permissions

```python
# Get all active permissions
permissions = await client.wa.get_permissions()

# Filter permissions
api_perms = await client.wa.get_permissions(
    resource_type="api_endpoint",
    active_only=True
)
```

## Response Formats

### Deferral Response
```python
{
    "deferrals": [
        {
            "id": "def_123",
            "thought_id": "thought_456",
            "reason": "Uncertain about user intent",
            "context": {...},
            "status": "pending",
            "created_at": "2024-01-01T10:00:00Z",
            "resolution": null,
            "resolved_at": null
        }
    ],
    "total": 42,
    "limit": 100,
    "offset": 0
}
```

### Resolution Response
```python
{
    "id": "def_123",
    "status": "resolved",
    "resolution": "approved",
    "guidance": "Your guidance text",
    "reasoning": "Your reasoning",
    "resolved_at": "2024-01-01T10:30:00Z",
    "resolved_by": "admin_user"
}
```

### Permissions Response
```python
{
    "permissions": [
        {
            "id": "perm_123",
            "resource_type": "memory_access",
            "permission_type": "read",
            "granted_by": "wise_authority",
            "granted_at": "2024-01-01T09:00:00Z",
            "expires_at": null,
            "active": true
        }
    ]
}
```

## Best Practices

1. **Always provide guidance** when approving or modifying deferrals
2. **Always provide reasoning** when rejecting deferrals
3. **Check deferral status** before attempting to resolve
4. **Use filtering** to manage large numbers of deferrals
5. **Monitor permissions** regularly to ensure appropriate access

## Error Handling

The client will raise `CIRISAPIError` for API-related errors:

```python
from ciris_sdk.exceptions import CIRISAPIError

try:
    await client.wa.resolve_deferral(
        deferral_id="invalid_id",
        resolution="approved"
    )
except CIRISAPIError as e:
    print(f"Error: {e.status_code} - {e.message}")
```
