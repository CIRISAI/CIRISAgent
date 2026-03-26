"""
Wallet Tool Service.

Provides three generic money tools:
- send_money: Send money to a recipient
- request_money: Create a payment request/invoice
- get_statement: Get account balance, history, and details

The implementation details (crypto vs fiat) are abstracted behind provider parameters.
"""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from ciris_engine.schemas.adapters.tools import (
    ToolDMAGuidance,
    ToolDocumentation,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolGotcha,
    ToolInfo,
    ToolParameterSchema,
    UsageExample,
)

from .config import WalletAdapterConfig
from .providers.base import WalletProvider

logger = logging.getLogger(__name__)


class WalletToolService:
    """
    Tool service for wallet operations.

    Provides generic money tools that work across crypto and fiat providers.
    The provider routing is handled automatically based on currency or explicit
    provider_params.
    """

    TOOL_DEFINITIONS: Dict[str, ToolInfo] = {
        "send_money": ToolInfo(
            name="send_money",
            description="Send money to a recipient via crypto (USDC) or fiat (mobile money) providers",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "recipient": {
                        "type": "string",
                        "description": "Recipient address (0x... for crypto), phone (+251... for ETB), or username",
                    },
                    "amount": {
                        "type": "number",
                        "description": "Amount to send",
                    },
                    "currency": {
                        "type": "string",
                        "description": "Currency code: USDC (crypto), ETB (Ethiopia), KES (Kenya), etc.",
                    },
                    "memo": {
                        "type": "string",
                        "description": "Optional transaction memo or description",
                    },
                    "provider_params": {
                        "type": "object",
                        "description": "Optional provider-specific parameters",
                        "properties": {
                            "provider": {
                                "type": "string",
                                "enum": ["x402", "chapa", "mpesa", "auto"],
                                "description": "Explicit provider (auto-detected from currency if omitted)",
                            },
                        },
                    },
                },
                required=["recipient", "amount", "currency"],
            ),
            documentation=ToolDocumentation(
                quick_start="Send money: send_money recipient='0x1234...' amount=10 currency='USDC'",
                detailed_instructions="""
# Send Money

Send money to any recipient using the appropriate payment provider.

## Currency → Provider Mapping
- **USDC, ETH** → x402 (crypto on Base L2)
- **ETB** → Chapa (Ethiopian Birr via Telebirr/CBE Birr)
- **KES** → M-Pesa (Kenyan Shilling) [future]
- **NGN** → Flutterwave (Nigerian Naira) [future]

## Recipient Formats

### Crypto (x402)
- EVM address: `0x742d35Cc6634C0532925a3b844Bc9e7595f...`
- ENS name: `vitalik.eth` (if supported)

### Ethiopian (Chapa)
- Phone: `+251912345678` or `0912345678`
- Bank account requires additional provider_params

### Kenyan (M-Pesa) [future]
- Phone: `+254712345678`

## Transaction Flow
1. Currency determines provider (or use explicit provider_params.provider)
2. Provider validates recipient format
3. DMA pipeline evaluates the transaction (requires_approval=True)
4. Transaction is signed and submitted
5. Result includes transaction_id and confirmation

## Spending Limits
- Per-transaction: $100 (configurable)
- Daily: $1000 (configurable)
- Session: $500 (configurable)
- Attestation level affects limits (x402 only)
""",
                examples=[
                    UsageExample(
                        title="Send USDC to contributor",
                        description="Pay a contributor in USDC",
                        code='{"recipient": "0x742d35Cc6634C0532925a3b844Bc9e7595f...", "amount": 50.00, "currency": "USDC", "memo": "March contribution"}',
                    ),
                    UsageExample(
                        title="Send ETB via Telebirr",
                        description="Pay in Ethiopian Birr",
                        code='{"recipient": "+251912345678", "amount": 1300.00, "currency": "ETB", "memo": "API usage fee"}',
                    ),
                    UsageExample(
                        title="Explicit provider",
                        description="Force a specific provider",
                        code='{"recipient": "0x1234...", "amount": 10, "currency": "USDC", "provider_params": {"provider": "x402"}}',
                    ),
                ],
                gotchas=[
                    ToolGotcha(
                        title="Recipient format must match provider",
                        description="Crypto requires 0x addresses, mobile money requires phone numbers in E.164 format",
                        severity="error",
                    ),
                    ToolGotcha(
                        title="Transactions are irreversible",
                        description="Once confirmed, crypto transactions cannot be reversed. Fiat may have dispute mechanisms.",
                        severity="warning",
                    ),
                    ToolGotcha(
                        title="Attestation level affects spending",
                        description="x402 provider requires minimum attestation level. Degraded attestation reduces limits.",
                        severity="info",
                    ),
                ],
            ),
            dma_guidance=ToolDMAGuidance(
                requires_approval=True,
                min_confidence=0.95,
                when_not_to_use="When recipient has not been explicitly confirmed by the user. When amount seems unusual or unexpected.",
                ethical_considerations="Verify recipient identity before sending. Confirm amount with user. Check for duplicate transactions.",
                prerequisite_actions=["Confirm recipient address/phone with user", "Verify amount"],
                followup_actions=["Provide transaction ID to user", "Log transaction for audit"],
            ),
        ),
        "request_money": ToolInfo(
            name="request_money",
            description="Create a payment request/invoice that others can pay",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "amount": {
                        "type": "number",
                        "description": "Amount to request",
                    },
                    "currency": {
                        "type": "string",
                        "description": "Currency code: USDC, ETB, KES, etc.",
                    },
                    "description": {
                        "type": "string",
                        "description": "What the payment is for",
                    },
                    "expires_at": {
                        "type": "string",
                        "description": "Optional ISO 8601 expiration timestamp",
                    },
                    "provider_params": {
                        "type": "object",
                        "description": "Optional provider-specific parameters",
                        "properties": {
                            "provider": {
                                "type": "string",
                                "enum": ["x402", "chapa", "mpesa", "auto"],
                                "description": "Explicit provider",
                            },
                            "callback_url": {
                                "type": "string",
                                "description": "Webhook URL for payment notification",
                            },
                        },
                    },
                },
                required=["amount", "currency", "description"],
            ),
            documentation=ToolDocumentation(
                quick_start="Request payment: request_money amount=0.10 currency='USDC' description='API task'",
                detailed_instructions="""
# Request Money

Create a payment request/invoice that can be paid by others.

## Use Cases
- API endpoint payment (402 Payment Required)
- Service fees
- Contributor invoices
- Donation requests

## Response
Returns a PaymentRequest with:
- **request_id**: Unique identifier
- **checkout_url**: URL for payer (fiat providers)
- **status**: pending/paid/expired
- **expires_at**: When request expires

## Verification
Use get_statement to check if a request has been paid,
or implement webhook callbacks for real-time notification.

## Provider Behavior

### x402 (Crypto)
- Returns payment details for X-PAYMENT header
- No checkout_url (payment is in-band)
- Instant verification via blockchain

### Chapa (Fiat)
- Returns checkout_url for Telebirr/CBE Birr/Bank
- Payer completes payment on Chapa's page
- Callback webhook on completion
""",
                examples=[
                    UsageExample(
                        title="Request for API task",
                        description="Create payment request for a single task",
                        code='{"amount": 0.10, "currency": "USDC", "description": "CIRIS API - Single task"}',
                    ),
                    UsageExample(
                        title="Request ETB with expiration",
                        description="Create Ethiopian payment request that expires",
                        code='{"amount": 13.00, "currency": "ETB", "description": "Ethical reasoning query", "expires_at": "2026-03-26T00:00:00Z"}',
                    ),
                ],
                gotchas=[
                    ToolGotcha(
                        title="Checkout URL is provider-specific",
                        description="x402 doesn't use checkout URLs (payment is in HTTP header). Fiat providers return URLs.",
                        severity="info",
                    ),
                ],
            ),
            dma_guidance=ToolDMAGuidance(
                requires_approval=False,
                min_confidence=0.8,
                when_not_to_use="When creating excessive or spam payment requests",
                ethical_considerations="Payment requests should be for legitimate services rendered",
            ),
        ),
        "get_statement": ToolInfo(
            name="get_statement",
            description="Get account balance, transaction history, and account details",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "include_balance": {
                        "type": "boolean",
                        "description": "Include current balance (default: true)",
                    },
                    "include_history": {
                        "type": "boolean",
                        "description": "Include transaction history (default: true)",
                    },
                    "include_details": {
                        "type": "boolean",
                        "description": "Include account details like address (default: false)",
                    },
                    "history_limit": {
                        "type": "integer",
                        "description": "Maximum transactions to return (default: 50)",
                    },
                    "provider_params": {
                        "type": "object",
                        "description": "Optional provider-specific parameters",
                        "properties": {
                            "provider": {
                                "type": "string",
                                "enum": ["x402", "chapa", "mpesa", "all"],
                                "description": "Specific provider or 'all' for all providers",
                            },
                        },
                    },
                },
                required=[],
            ),
            # Context enrichment: auto-run during context gathering
            # Provides balance awareness for financial decision-making
            context_enrichment=True,
            context_enrichment_params={
                "include_balance": True,
                "include_history": False,  # Don't flood context with history
                "include_details": False,
                "_cache_ttl": 60.0,  # Cache balance for 60s (balance monitor updates every 30s)
            },
            documentation=ToolDocumentation(
                quick_start="Get statement: get_statement include_balance=true include_history=true",
                detailed_instructions="""
# Get Statement

Retrieve account information including balance, transaction history, and details.

## What's Included

### Balance (include_balance=true)
- **available**: Spendable balance
- **pending**: Incoming but not confirmed
- **total**: available + pending

### History (include_history=true)
- Recent transactions (sends, receives)
- Transaction IDs for reference
- Timestamps and status

### Details (include_details=false by default)
- Wallet address (crypto)
- Phone number (mobile money)
- Network information
- Attestation level

## Provider Selection
- Omit provider_params: Query all enabled providers
- provider='x402': Only crypto accounts
- provider='chapa': Only Ethiopian accounts
- provider='all': Explicitly query all

## Privacy Note
Account details may include sensitive information.
Only request details when needed.
""",
                examples=[
                    UsageExample(
                        title="Check all balances",
                        description="Get balance from all providers",
                        code='{"include_balance": true, "include_history": false}',
                    ),
                    UsageExample(
                        title="Full statement",
                        description="Get complete statement with history",
                        code='{"include_balance": true, "include_history": true, "include_details": true, "history_limit": 20}',
                    ),
                    UsageExample(
                        title="Crypto only",
                        description="Get only x402/USDC account info",
                        code='{"include_balance": true, "provider_params": {"provider": "x402"}}',
                    ),
                ],
                gotchas=[
                    ToolGotcha(
                        title="History may be slow for large accounts",
                        description="Use history_limit to control response size",
                        severity="info",
                    ),
                ],
            ),
            dma_guidance=ToolDMAGuidance(
                requires_approval=False,
                min_confidence=0.7,
                when_not_to_use="Repeatedly polling for changes - use webhooks instead",
                ethical_considerations="Balance and history reveal financial activity. Handle with appropriate privacy.",
            ),
        ),
    }

    def __init__(
        self,
        config: WalletAdapterConfig,
        providers: Optional[Dict[str, WalletProvider]] = None,
    ) -> None:
        """
        Initialize the wallet tool service.

        Args:
            config: Wallet adapter configuration
            providers: Dict mapping provider_id to WalletProvider instance
        """
        self.config = config
        self._providers: Dict[str, WalletProvider] = providers or {}
        self._started = False
        logger.info(
            f"WalletToolService initialized with providers: {list(self._providers.keys())}"
        )

    def register_provider(self, provider: WalletProvider) -> None:
        """Register a wallet provider."""
        self._providers[provider.provider_id] = provider
        logger.info(f"Registered wallet provider: {provider.provider_id}")

    def _get_provider_for_currency(self, currency: str) -> Optional[WalletProvider]:
        """Get the appropriate provider for a currency."""
        currency = currency.upper()

        # Check currency_providers mapping
        provider_id = self.config.currency_providers.get(currency)
        if provider_id and provider_id in self._providers:
            return self._providers[provider_id]

        # Check if any provider supports this currency
        for provider in self._providers.values():
            if provider.supports_currency(currency):
                return provider

        # Fall back to default
        if self.config.default_provider in self._providers:
            return self._providers[self.config.default_provider]

        return None

    def _get_provider(
        self, currency: str, provider_params: Optional[Dict[str, Any]] = None
    ) -> Optional[WalletProvider]:
        """Get provider based on currency and optional explicit provider param."""
        # Check for explicit provider
        if provider_params and provider_params.get("provider"):
            provider_id = provider_params["provider"]
            if provider_id != "auto" and provider_id in self._providers:
                return self._providers[provider_id]

        # Route by currency
        return self._get_provider_for_currency(currency)

    async def start(self) -> None:
        """Start the tool service and initialize providers."""
        logger.info("Starting WalletToolService")
        for provider_id, provider in self._providers.items():
            try:
                success = await provider.initialize()
                if success:
                    logger.info(f"Wallet provider {provider_id} initialized")
                else:
                    logger.warning(f"Wallet provider {provider_id} initialization failed")
            except Exception as e:
                logger.error(f"Error initializing provider {provider_id}: {e}")
        self._started = True
        logger.info("WalletToolService started")

    async def stop(self) -> None:
        """Stop the tool service and cleanup providers."""
        logger.info("Stopping WalletToolService")
        for provider_id, provider in self._providers.items():
            try:
                await provider.cleanup()
                logger.info(f"Wallet provider {provider_id} cleaned up")
            except Exception as e:
                logger.error(f"Error cleaning up provider {provider_id}: {e}")
        self._started = False
        logger.info("WalletToolService stopped")

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    def get_service_metadata(self) -> Dict[str, Any]:
        """Return service metadata for DSAR and data source discovery."""
        return {
            "data_source": True,
            "data_source_type": "payment_provider",
            "contains_pii": True,
            "gdpr_applicable": True,
            "connector_id": "wallet_adapter",
            "data_retention_days": 90,
            "encryption_at_rest": True,
        }

    async def get_available_tools(self) -> List[str]:
        """Get available tool names."""
        return list(self.TOOL_DEFINITIONS.keys())

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool."""
        return self.TOOL_DEFINITIONS.get(tool_name)

    async def get_all_tool_info(self) -> List[ToolInfo]:
        """Get info for all tools."""
        return list(self.TOOL_DEFINITIONS.values())

    async def get_tool_schema(self, tool_name: str) -> Optional[ToolParameterSchema]:
        """Get parameter schema for a tool."""
        tool_info = self.TOOL_DEFINITIONS.get(tool_name)
        return tool_info.parameters if tool_info else None

    async def validate_parameters(
        self, tool_name: str, parameters: Dict[str, Any]
    ) -> bool:
        """Validate parameters for a tool without executing it."""
        if tool_name not in self.TOOL_DEFINITIONS:
            return False
        tool_info = self.TOOL_DEFINITIONS[tool_name]
        if not tool_info.parameters:
            return True
        required = tool_info.parameters.required or []
        return all(param in parameters for param in required)

    async def get_tool_result(
        self, correlation_id: str, timeout: float = 30.0
    ) -> Optional[ToolExecutionResult]:
        """Get result of previously executed tool. Not implemented for sync wallet tools."""
        return None

    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolExecutionResult:
        """Execute a wallet tool."""
        start_time = datetime.now(timezone.utc)
        correlation_id = str(uuid.uuid4())

        logger.info("=" * 60)
        logger.info(f"[WALLET TOOL] Tool: {tool_name}")
        logger.info(f"[WALLET TOOL] Parameters: {parameters}")
        logger.info(f"[WALLET TOOL] Correlation ID: {correlation_id}")

        if tool_name not in self.TOOL_DEFINITIONS:
            logger.error(f"[WALLET TOOL] Unknown tool: {tool_name}")
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.NOT_FOUND,
                success=False,
                data=None,
                error=f"Unknown tool: {tool_name}",
                correlation_id=correlation_id,
            )

        try:
            if tool_name == "send_money":
                result = await self._execute_send_money(parameters, correlation_id)
            elif tool_name == "request_money":
                result = await self._execute_request_money(parameters, correlation_id)
            elif tool_name == "get_statement":
                result = await self._execute_get_statement(parameters, correlation_id)
            else:
                result = ToolExecutionResult(
                    tool_name=tool_name,
                    status=ToolExecutionStatus.FAILED,
                    success=False,
                    data=None,
                    error=f"Tool not implemented: {tool_name}",
                    correlation_id=correlation_id,
                )

            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info(f"[WALLET TOOL] Result: success={result.success}")
            if result.error:
                logger.error(f"[WALLET TOOL] Error: {result.error}")
            logger.info(f"[WALLET TOOL] Elapsed: {elapsed:.3f}s")
            logger.info("=" * 60)
            return result

        except Exception as e:
            logger.error(f"[WALLET TOOL] Exception: {e}")
            import traceback

            logger.error(f"[WALLET TOOL] Traceback: {traceback.format_exc()}")
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=str(e),
                correlation_id=correlation_id,
            )

    async def _execute_send_money(
        self, params: Dict[str, Any], correlation_id: str
    ) -> ToolExecutionResult:
        """Execute send_money tool."""
        # Validate required parameters
        recipient = params.get("recipient", "")
        amount_raw = params.get("amount")
        currency = params.get("currency", "")
        memo = params.get("memo")
        provider_params = params.get("provider_params", {})

        missing = []
        if not recipient:
            missing.append("recipient")
        if amount_raw is None:
            missing.append("amount")
        if not currency:
            missing.append("currency")

        if missing:
            return ToolExecutionResult(
                tool_name="send_money",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={"received_params": params, "missing": missing},
                error=f"Missing required parameter(s): {', '.join(missing)}",
                correlation_id=correlation_id,
            )

        # Parse amount
        try:
            amount = Decimal(str(amount_raw))
        except (InvalidOperation, ValueError):
            return ToolExecutionResult(
                tool_name="send_money",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={"received_params": params},
                error=f"Invalid amount: {amount_raw}",
                correlation_id=correlation_id,
            )

        # Get provider
        provider = self._get_provider(currency, provider_params)
        if not provider:
            return ToolExecutionResult(
                tool_name="send_money",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={"currency": currency, "available_providers": list(self._providers.keys())},
                error=f"No provider available for currency: {currency}",
                correlation_id=correlation_id,
            )

        # Execute send
        try:
            result = await provider.send(
                recipient=recipient,
                amount=amount,
                currency=currency.upper(),
                memo=memo,
            )

            return ToolExecutionResult(
                tool_name="send_money",
                status=ToolExecutionStatus.COMPLETED if result.success else ToolExecutionStatus.FAILED,
                success=result.success,
                data={
                    "transaction_id": result.transaction_id,
                    "provider": result.provider,
                    "amount": str(result.amount),
                    "currency": result.currency,
                    "recipient": result.recipient,
                    "timestamp": result.timestamp.isoformat(),
                    "fees": {k: str(v) for k, v in (result.fees or {}).items()},
                    "confirmation": result.confirmation,
                },
                error=result.error,
                correlation_id=correlation_id,
            )
        except Exception as e:
            logger.error(f"[WALLET TOOL] send_money failed: {e}")
            return ToolExecutionResult(
                tool_name="send_money",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=str(e),
                correlation_id=correlation_id,
            )

    async def _execute_request_money(
        self, params: Dict[str, Any], correlation_id: str
    ) -> ToolExecutionResult:
        """Execute request_money tool."""
        # Validate required parameters
        amount_raw = params.get("amount")
        currency = params.get("currency", "")
        description = params.get("description", "")
        expires_at_str = params.get("expires_at")
        provider_params = params.get("provider_params", {})

        missing = []
        if amount_raw is None:
            missing.append("amount")
        if not currency:
            missing.append("currency")
        if not description:
            missing.append("description")

        if missing:
            return ToolExecutionResult(
                tool_name="request_money",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={"received_params": params, "missing": missing},
                error=f"Missing required parameter(s): {', '.join(missing)}",
                correlation_id=correlation_id,
            )

        # Parse amount
        try:
            amount = Decimal(str(amount_raw))
        except (InvalidOperation, ValueError):
            return ToolExecutionResult(
                tool_name="request_money",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={"received_params": params},
                error=f"Invalid amount: {amount_raw}",
                correlation_id=correlation_id,
            )

        # Parse expiration
        expires_at = None
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            except ValueError:
                logger.warning(f"Invalid expires_at format: {expires_at_str}")

        # Get provider
        provider = self._get_provider(currency, provider_params)
        if not provider:
            return ToolExecutionResult(
                tool_name="request_money",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data={"currency": currency},
                error=f"No provider available for currency: {currency}",
                correlation_id=correlation_id,
            )

        # Execute request
        try:
            callback_url = provider_params.get("callback_url") if provider_params else None
            result = await provider.request(
                amount=amount,
                currency=currency.upper(),
                description=description,
                expires_at=expires_at,
                callback_url=callback_url,
            )

            return ToolExecutionResult(
                tool_name="request_money",
                status=ToolExecutionStatus.COMPLETED,
                success=True,
                data={
                    "request_id": result.request_id,
                    "provider": result.provider,
                    "amount": str(result.amount),
                    "currency": result.currency,
                    "description": result.description,
                    "status": result.status.value,
                    "checkout_url": result.checkout_url,
                    "created_at": result.created_at.isoformat(),
                    "expires_at": result.expires_at.isoformat() if result.expires_at else None,
                },
                error=None,
                correlation_id=correlation_id,
            )
        except Exception as e:
            logger.error(f"[WALLET TOOL] request_money failed: {e}")
            return ToolExecutionResult(
                tool_name="request_money",
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=str(e),
                correlation_id=correlation_id,
            )

    async def _execute_get_statement(
        self, params: Dict[str, Any], correlation_id: str
    ) -> ToolExecutionResult:
        """Execute get_statement tool."""
        include_balance = params.get("include_balance", True)
        include_history = params.get("include_history", True)
        include_details = params.get("include_details", False)
        history_limit = params.get("history_limit", 50)
        provider_params = params.get("provider_params", {})

        # Determine which providers to query
        target_provider = provider_params.get("provider") if provider_params else None
        if target_provider and target_provider != "all" and target_provider in self._providers:
            providers_to_query = {target_provider: self._providers[target_provider]}
        else:
            providers_to_query = self._providers

        accounts = []
        for provider_id, provider in providers_to_query.items():
            try:
                account_data: Dict[str, Any] = {
                    "provider": provider_id,
                    "currency": provider.supported_currencies[0] if provider.supported_currencies else "UNKNOWN",
                }

                if include_balance:
                    balance = await provider.get_balance()
                    account_data["balance"] = {
                        "available": str(balance.available),
                        "pending": str(balance.pending),
                        "total": str(balance.total),
                    }

                if include_details:
                    details = await provider.get_account_details()
                    account_data["details"] = {
                        "address": details.address,
                        "phone": details.phone,
                        "account_id": details.account_id,
                        "network": details.network,
                        "attestation_level": details.attestation_level,
                    }

                if include_history:
                    history = await provider.get_history(limit=history_limit)
                    account_data["history"] = [
                        {
                            "transaction_id": tx.transaction_id,
                            "type": tx.type.value,
                            "status": tx.status.value,
                            "amount": str(tx.amount),
                            "currency": tx.currency,
                            "recipient": tx.recipient,
                            "sender": tx.sender,
                            "memo": tx.memo,
                            "timestamp": tx.timestamp.isoformat(),
                        }
                        for tx in history
                    ]

                accounts.append(account_data)

            except Exception as e:
                logger.error(f"[WALLET TOOL] Error getting statement for {provider_id}: {e}")
                accounts.append({
                    "provider": provider_id,
                    "error": str(e),
                })

        return ToolExecutionResult(
            tool_name="get_statement",
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data={"accounts": accounts},
            error=None,
            correlation_id=correlation_id,
        )
