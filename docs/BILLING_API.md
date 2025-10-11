# Agent Billing API Documentation

**For UI/Frontend Development**

## Important Architecture Note

⚠️ **The UI must NEVER call billing.ciris.ai directly.**

The UI should only interact with the **agent's billing proxy endpoints** at `/v1/api/billing/*`. The agent handles all communication with the billing backend automatically.

```
┌─────────┐         ┌────────────┐         ┌──────────────────┐
│   UI    │ ──────> │   Agent    │ ──────> │ billing.ciris.ai │
│ (React) │ <────── │    API     │ <────── │    (Backend)     │
└─────────┘         └────────────┘         └──────────────────┘
                    /v1/api/billing/*
```

**All billing API calls go through the agent's proxy endpoints.**

---

## Authentication

All billing endpoints require authentication via JWT token:

```http
Authorization: Bearer <token>
```

Get token via login:
```bash
POST /v1/auth/login
Content-Type: application/json

{
  "username": "your_username",
  "password": "your_password"
}
```

---

## Endpoints

### 1. Get Credit Status

**Endpoint**: `GET /v1/api/billing/credits`

**Description**: Get current credit balance and purchase options for the authenticated user.

**Request**:
```http
GET /v1/api/billing/credits
Authorization: Bearer <token>
```

**Response**:
```json
{
  "has_credit": true,
  "credits_remaining": 50,
  "free_uses_remaining": 5,
  "total_uses": 45,
  "plan_name": "Standard",
  "purchase_required": false,
  "purchase_options": null
}
```

**When Purchase Required**:
```json
{
  "has_credit": false,
  "credits_remaining": 0,
  "free_uses_remaining": 0,
  "total_uses": 100,
  "plan_name": "Standard",
  "purchase_required": true,
  "purchase_options": {
    "price_minor": 500,
    "uses": 100,
    "currency": "USD"
  }
}
```

**Response Fields**:
- `has_credit` (boolean): Whether user has available credit to make requests
- `credits_remaining` (integer): Remaining paid credits
- `free_uses_remaining` (integer): Remaining free trial uses
- `total_uses` (integer): Total requests made so far
- `plan_name` (string): Current billing plan name
- `purchase_required` (boolean): Whether user must purchase to continue
- `purchase_options` (object|null): Purchase details when `purchase_required=true`
  - `price_minor` (integer): Price in cents (500 = $5.00)
  - `uses` (integer): Number of uses included in purchase
  - `currency` (string): Currency code (always "USD")

**UI Logic**:
```javascript
const status = await fetch('/v1/api/billing/credits', {
  headers: { 'Authorization': `Bearer ${token}` }
}).then(r => r.json());

if (status.purchase_required) {
  // Show "Purchase Required" UI
  // Display: `$${status.purchase_options.price_minor / 100} for ${status.purchase_options.uses} uses`
} else if (status.has_credit) {
  // User can make requests
  const total = status.credits_remaining + status.free_uses_remaining;
  // Display: `${total} uses remaining`
}
```

---

### 2. Initiate Credit Purchase

**Endpoint**: `POST /v1/api/billing/purchase/initiate`

**Description**: Start the credit purchase flow. Returns Stripe payment details for frontend integration.

**Note**: Only works when billing is enabled (CIRISBillingProvider). Returns 403 error when SimpleCreditProvider is active.

**Request**:
```http
POST /v1/api/billing/purchase/initiate
Authorization: Bearer <token>
Content-Type: application/json

{
  "return_url": "https://yourapp.com/payment-complete"
}
```

**Request Fields**:
- `return_url` (string, optional): URL to redirect after payment completion

**Response**:
```json
{
  "payment_id": "pi_abc123xyz789",
  "client_secret": "pi_abc123xyz789_secret_def456",
  "amount_minor": 500,
  "currency": "USD",
  "uses_purchased": 100,
  "publishable_key": "pk_test_abc123"
}
```

**Response Fields**:
- `payment_id` (string): Stripe PaymentIntent ID (save this for status polling)
- `client_secret` (string): Stripe client secret (pass to Stripe.js)
- `amount_minor` (integer): Amount in cents (500 = $5.00)
- `currency` (string): Currency code
- `uses_purchased` (integer): Number of uses being purchased
- `publishable_key` (string): Stripe publishable key for frontend

**UI Integration** (Stripe Elements):
```javascript
// 1. Initiate purchase
const purchase = await fetch('/v1/api/billing/purchase/initiate', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    return_url: window.location.origin + '/payment-complete'
  })
}).then(r => r.json());

// 2. Initialize Stripe
const stripe = Stripe(purchase.publishable_key);

// 3. Confirm payment with Stripe
const { error } = await stripe.confirmCardPayment(purchase.client_secret, {
  payment_method: {
    card: cardElement,
    billing_details: { name: 'Customer Name' }
  }
});

if (error) {
  // Show error to user
  console.error(error.message);
} else {
  // 4. Poll for status using payment_id
  pollPaymentStatus(purchase.payment_id);
}
```

**Error Handling**:
- `403 Forbidden`: Billing not enabled (SimpleCreditProvider active)
- `401 Unauthorized`: Invalid/expired token
- `500 Internal Server Error`: Stripe configuration issue

---

### 3. Get Purchase Status

**Endpoint**: `GET /v1/api/billing/purchase/status/{payment_id}`

**Description**: Check payment status after initiating purchase. Poll this endpoint to confirm credits were added.

**Request**:
```http
GET /v1/api/billing/purchase/status/pi_abc123xyz789
Authorization: Bearer <token>
```

**Response** (Payment Succeeded):
```json
{
  "status": "succeeded",
  "credits_added": 100,
  "balance_after": 100
}
```

**Response** (Payment Processing):
```json
{
  "status": "processing",
  "credits_added": 0,
  "balance_after": 0
}
```

**Response** (Payment Failed):
```json
{
  "status": "failed",
  "credits_added": 0,
  "balance_after": 0
}
```

**Response Fields**:
- `status` (string): Stripe payment status (see valid statuses below)
- `credits_added` (integer): Credits added (0 if not completed)
- `balance_after` (integer): Credit balance after purchase

**Valid Status Values**:
- `succeeded` - Payment complete, credits added
- `processing` - Payment being processed
- `pending` - Awaiting payment confirmation
- `requires_payment_method` - Payment method required
- `requires_confirmation` - Requires confirmation
- `requires_action` - User action required (3D Secure)
- `failed` - Payment failed
- `canceled` - Payment canceled
- `unknown` - Status unknown

**UI Polling Logic**:
```javascript
async function pollPaymentStatus(paymentId) {
  const maxAttempts = 30;
  const pollInterval = 2000; // 2 seconds

  for (let i = 0; i < maxAttempts; i++) {
    const status = await fetch(
      `/v1/api/billing/purchase/status/${paymentId}`,
      { headers: { 'Authorization': `Bearer ${token}` } }
    ).then(r => r.json());

    if (status.status === 'succeeded') {
      // Show success message
      alert(`Success! ${status.credits_added} credits added. New balance: ${status.balance_after}`);
      return;
    }

    if (status.status === 'failed' || status.status === 'canceled') {
      // Show error message
      alert('Payment failed. Please try again.');
      return;
    }

    // Continue polling for processing/pending states
    await new Promise(resolve => setTimeout(resolve, pollInterval));
  }

  // Timeout
  alert('Payment status unknown. Please check your credit balance.');
}
```

**Error Handling**:
- `404 Not Found`: Payment ID not found (expected for test payments)
- `401 Unauthorized`: Invalid/expired token
- `403 Forbidden`: Billing not enabled

---

## Complete Purchase Flow

### Step-by-Step Integration

```javascript
// 1. Check if user needs to purchase
async function checkCredits() {
  const status = await fetch('/v1/api/billing/credits', {
    headers: { 'Authorization': `Bearer ${token}` }
  }).then(r => r.json());

  if (status.purchase_required) {
    showPurchaseUI(status.purchase_options);
  }
}

// 2. User clicks "Purchase Credits"
async function initiatePurchase() {
  const purchase = await fetch('/v1/api/billing/purchase/initiate', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      return_url: `${window.location.origin}/payment-complete`
    })
  }).then(r => r.json());

  return purchase;
}

// 3. Collect payment with Stripe
async function collectPayment(purchase) {
  const stripe = Stripe(purchase.publishable_key);

  // Show Stripe Elements card form
  const elements = stripe.elements();
  const cardElement = elements.create('card');
  cardElement.mount('#card-element');

  // On form submit
  const { error } = await stripe.confirmCardPayment(purchase.client_secret, {
    payment_method: {
      card: cardElement,
      billing_details: { name: userName }
    }
  });

  if (error) {
    throw new Error(error.message);
  }

  return purchase.payment_id;
}

// 4. Poll for completion
async function waitForCompletion(paymentId) {
  const maxAttempts = 30;
  const pollInterval = 2000;

  for (let i = 0; i < maxAttempts; i++) {
    const status = await fetch(
      `/v1/api/billing/purchase/status/${paymentId}`,
      { headers: { 'Authorization': `Bearer ${token}` } }
    ).then(r => r.json());

    if (status.status === 'succeeded') {
      return status;
    }

    if (['failed', 'canceled'].includes(status.status)) {
      throw new Error(`Payment ${status.status}`);
    }

    await new Promise(resolve => setTimeout(resolve, pollInterval));
  }

  throw new Error('Payment timeout');
}

// 5. Complete flow
async function purchaseCredits() {
  try {
    const purchase = await initiatePurchase();
    const paymentId = await collectPayment(purchase);
    const result = await waitForCompletion(paymentId);

    alert(`Success! ${result.credits_added} credits added.`);

    // Refresh credit display
    await checkCredits();
  } catch (error) {
    alert(`Purchase failed: ${error.message}`);
  }
}
```

---

## Testing

### Local Testing (SimpleCreditProvider)

When testing locally with SimpleCreditProvider (free credits only):

```bash
# Start agent with SimpleCreditProvider
python main.py --adapter api --mock-llm --port 8000
```

Expected behavior:
- `GET /v1/api/billing/credits` - Returns free credit balance
- `POST /v1/api/billing/purchase/initiate` - Returns `403 Forbidden` (billing disabled)

### QA Testing (CIRISBillingProvider)

When testing with Stripe integration:

```bash
# Set QA key
echo "cbk_test_YOUR_QA_KEY" > ~/.ciris/billing_qa_key

# Run billing tests
python -m tools.qa_runner billing
```

Expected results:
- ✅ Get Credit Status
- ✅ Check Credit Balance Display
- ✅ Check Purchase Options
- ✅ Initiate Purchase (if enabled)
- ✅ Check Purchase Status (if initiated)

---

## SDK Usage (Python)

For backend integration or testing:

```python
from ciris_sdk.client import CIRISClient

async with CIRISClient(base_url="http://localhost:8000") as client:
    # Login
    await client.login("username", "password")

    # Check credits
    status = await client.billing.get_credits()
    print(f"Credits: {status.credits_remaining}")

    if status.purchase_required:
        # Initiate purchase
        purchase = await client.billing.initiate_purchase(
            return_url="https://myapp.com/complete"
        )
        print(f"Payment ID: {purchase.payment_id}")
        print(f"Amount: ${purchase.amount_minor / 100}")

        # Check status
        result = await client.billing.get_purchase_status(purchase.payment_id)
        print(f"Status: {result.status}")
```

---

## Error Responses

All endpoints return standard error responses:

**401 Unauthorized**:
```json
{
  "detail": "Not authenticated"
}
```

**403 Forbidden** (Billing Disabled):
```json
{
  "detail": "Billing not enabled for this agent"
}
```

**404 Not Found** (Invalid Payment ID):
```json
{
  "detail": "Payment not found"
}
```

**500 Internal Server Error**:
```json
{
  "detail": "Internal server error"
}
```

---

## Security Notes

1. **Never expose billing backend URLs** - UI should only know about `/v1/api/billing/*`
2. **Always use HTTPS in production** - Never send tokens over HTTP
3. **Token expiration** - Handle 401 errors by re-authenticating
4. **Stripe client secrets** - Never log or expose client secrets
5. **PCI compliance** - Use Stripe Elements, never handle raw card data

---

## Billing Modes

The agent supports two billing modes:

### SimpleCreditProvider (Free Credits)
- Used for development and testing
- No purchase functionality
- Returns 403 on purchase endpoints
- Free credits configured in agent settings

### CIRISBillingProvider (Paid Credits)
- Production billing with Stripe
- Full purchase flow enabled
- Requires Stripe configuration
- Credits purchased via Stripe payment intents

**UI should gracefully handle both modes** - show purchase UI when `purchase_required=true`, handle 403 errors gracefully.

---

## Questions?

Contact the backend team or refer to:
- SDK implementation: `ciris_sdk/resources/billing.py`
- QA tests: `tools/qa_runner/modules/billing_tests.py`
- Test runner: `python -m tools.qa_runner billing`
