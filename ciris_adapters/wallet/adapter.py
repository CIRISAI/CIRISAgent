"""
Wallet Adapter for CIRIS.

Provides generic money tools (send_money, request_money, get_statement)
that work across crypto (x402/USDC) and fiat (Chapa/ETB) providers.

This adapter follows the CIRIS adapter pattern:
- Tool service registered with ToolBus
- Provider-agnostic interface
- DMA-gated financial operations

KEY FEATURE: Auto-loads from CIRISVerify
- Wallet address derived from CIRISVerify Ed25519 public key
- Private key NEVER leaves secure element
- Every CIRIS agent has a wallet address from birth
"""

import asyncio
import logging
import os
from typing import Any, Callable, Dict, List, Optional

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, RuntimeAdapterStatus
from ciris_engine.schemas.runtime.enums import ServiceType

from .config import WalletAdapterConfig
from .providers.registry import create_provider, get_loaded_providers, ProviderLoadError
from .tool_service import WalletToolService

logger = logging.getLogger(__name__)


class WalletAdapter(Service):
    """
    Wallet adapter platform for CIRIS.

    Provides generic money tools that abstract crypto and fiat payments:
    - send_money: Send to any recipient (USDC address, phone number, etc.)
    - request_money: Create payment requests/invoices
    - get_statement: Check balance and transaction history

    The implementation routes to the appropriate provider based on currency
    or explicit provider_params.
    """

    def __init__(
        self,
        runtime: Any,
        context: Optional[Any] = None,
        config: Optional[WalletAdapterConfig] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize Wallet adapter."""
        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime
        self.context = context

        # Load configuration
        self.adapter_config = config or self._load_config_from_env()

        # Initialize providers
        self._providers: Dict[str, Any] = {}
        self._init_providers()

        # Create tool service
        self.tool_service = WalletToolService(
            config=self.adapter_config,
            providers=self._providers,
        )

        # Track adapter state
        self._running = False

        logger.info(
            f"Wallet adapter initialized with providers: {list(self._providers.keys())}"
        )

    def _load_config_from_env(self) -> WalletAdapterConfig:
        """Load configuration from environment variables.

        Only creates config objects for providers that are explicitly enabled.
        Providers are lazy-loaded, so unused providers don't consume memory.

        MVP Default: x402 (USDC on Base L2) is enabled by default.
        Other providers must be explicitly enabled via environment variables.
        """
        # Import config classes lazily to match provider pattern
        from .config import (
            X402ProviderConfig,
            ChapaProviderConfig,
            MPesaProviderConfig,
            RazorpayProviderConfig,
            PIXProviderConfig,
            WiseProviderConfig,
            StripeProviderConfig,
        )

        # Build provider configs dict - only include enabled providers
        provider_configs: Dict[str, Any] = {}

        # x402 (USDC on Base L2) - ENABLED BY DEFAULT for MVP
        # Disable explicitly with WALLET_X402_ENABLED=false
        if os.getenv("WALLET_X402_ENABLED", "true").lower() == "true":
            provider_configs["x402"] = X402ProviderConfig(
                enabled=True,
                network=os.getenv("WALLET_X402_NETWORK", "base-mainnet"),
                rpc_url=os.getenv("WALLET_X402_RPC_URL"),
                treasury_address=os.getenv("WALLET_X402_TREASURY_ADDRESS"),
                facilitator_url=os.getenv(
                    "WALLET_X402_FACILITATOR_URL", "https://x402.org/facilitator"
                ),
            )

        # Chapa (ETB - Ethiopia)
        if os.getenv("WALLET_CHAPA_ENABLED", "false").lower() == "true":
            chapa_secret = os.getenv("WALLET_CHAPA_SECRET_KEY")
            provider_configs["chapa"] = ChapaProviderConfig(
                enabled=True,
                secret_key=chapa_secret if chapa_secret else None,
                callback_base_url=os.getenv("WALLET_CHAPA_CALLBACK_URL"),
                merchant_name=os.getenv("WALLET_CHAPA_MERCHANT_NAME", "CIRIS"),
            )

        # M-Pesa (KES - Kenya/Africa)
        if os.getenv("WALLET_MPESA_ENABLED", "false").lower() == "true":
            provider_configs["mpesa"] = MPesaProviderConfig(
                enabled=True,
                consumer_key=os.getenv("WALLET_MPESA_CONSUMER_KEY"),
                consumer_secret=os.getenv("WALLET_MPESA_CONSUMER_SECRET"),
                shortcode=os.getenv("WALLET_MPESA_SHORTCODE"),
                passkey=os.getenv("WALLET_MPESA_PASSKEY"),
                environment=os.getenv("WALLET_MPESA_ENVIRONMENT", "sandbox"),
                callback_base_url=os.getenv("WALLET_MPESA_CALLBACK_URL"),
            )

        # Razorpay (INR - India)
        if os.getenv("WALLET_RAZORPAY_ENABLED", "false").lower() == "true":
            provider_configs["razorpay"] = RazorpayProviderConfig(
                enabled=True,
                key_id=os.getenv("WALLET_RAZORPAY_KEY_ID"),
                key_secret=os.getenv("WALLET_RAZORPAY_KEY_SECRET"),
                webhook_secret=os.getenv("WALLET_RAZORPAY_WEBHOOK_SECRET"),
            )

        # PIX (BRL - Brazil)
        if os.getenv("WALLET_PIX_ENABLED", "false").lower() == "true":
            provider_configs["pix"] = PIXProviderConfig(
                enabled=True,
                provider=os.getenv("WALLET_PIX_PROVIDER", "mercadopago"),
                access_token=os.getenv("WALLET_PIX_ACCESS_TOKEN"),
                callback_base_url=os.getenv("WALLET_PIX_CALLBACK_URL"),
            )

        # Wise (Global transfers)
        if os.getenv("WALLET_WISE_ENABLED", "false").lower() == "true":
            provider_configs["wise"] = WiseProviderConfig(
                enabled=True,
                api_token=os.getenv("WALLET_WISE_API_TOKEN"),
                profile_id=os.getenv("WALLET_WISE_PROFILE_ID"),
                environment=os.getenv("WALLET_WISE_ENVIRONMENT", "sandbox"),
            )

        # Stripe (Global cards)
        if os.getenv("WALLET_STRIPE_ENABLED", "false").lower() == "true":
            provider_configs["stripe"] = StripeProviderConfig(
                enabled=True,
                secret_key=os.getenv("WALLET_STRIPE_SECRET_KEY"),
                publishable_key=os.getenv("WALLET_STRIPE_PUBLISHABLE_KEY"),
                webhook_secret=os.getenv("WALLET_STRIPE_WEBHOOK_SECRET"),
            )

        return WalletAdapterConfig(
            provider_configs=provider_configs,
            default_provider=os.getenv("WALLET_DEFAULT_PROVIDER", "x402"),
        )

    def _init_providers(self) -> None:
        """Lazily initialize enabled wallet providers.

        Providers are loaded on-demand using the registry, so only
        the providers actually configured get imported into memory.
        """
        provider_configs = self.adapter_config.provider_configs

        for provider_name, config in provider_configs.items():
            if not config.enabled:
                continue

            try:
                # Build provider-specific kwargs
                kwargs: Dict[str, Any] = {}

                # x402 needs special handling for CIRISVerify
                if provider_name == "x402":
                    public_key, signing_callback = self._get_ciris_verify_key()
                    kwargs["ed25519_public_key"] = public_key
                    kwargs["ed25519_seed"] = self._get_test_seed()
                    kwargs["signing_callback"] = signing_callback

                    if public_key:
                        logger.info("x402 provider configured with CIRISVerify key")
                    else:
                        logger.info("x402 provider configured (no CIRISVerify - test mode)")

                # Lazy load and create the provider
                provider = create_provider(provider_name, config=config, **kwargs)
                self._providers[provider_name] = provider
                logger.info(f"Loaded provider: {provider_name}")

            except ProviderLoadError as e:
                logger.error(f"Failed to load provider {provider_name}: {e}")
            except Exception as e:
                logger.error(f"Error initializing provider {provider_name}: {e}")

    def _get_ciris_verify_key(self) -> tuple[Optional[bytes], Optional[Callable[[bytes], bytes]]]:
        """
        Get Ed25519 public key and signing callback from CIRISVerify.

        Returns:
            Tuple of (public_key, signing_callback)
            - public_key: 32 bytes Ed25519 public key for address derivation
            - signing_callback: Function to sign data via CIRISVerify

        The private key NEVER leaves the secure element. We only get:
        1. Public key (for deriving wallet address)
        2. Signing callback (for transaction signing)
        """
        try:
            # Import the singleton getter
            from ciris_engine.logic.services.infrastructure.authentication.verifier_singleton import (
                get_verifier,
            )

            verifier = get_verifier()

            # Check if verifier has a key
            if not verifier.has_key_sync():
                logger.warning("CIRISVerify has no key loaded")
                return None, None

            # Get public key (safe - this is public information)
            public_key = verifier.get_ed25519_public_key_sync()
            logger.info(f"Got Ed25519 public key from CIRISVerify ({len(public_key)} bytes)")

            # Create signing callback that delegates to CIRISVerify
            def signing_callback(data: bytes) -> bytes:
                """Sign data using CIRISVerify (key never leaves secure element)."""
                result: bytes = verifier.sign_ed25519_sync(data)
                return result

            return public_key, signing_callback

        except ImportError as e:
            logger.warning(f"CIRISVerify not available: {e}")
            return None, None
        except Exception as e:
            logger.warning(f"Could not access CIRISVerify: {e}")
            return None, None

    def _get_test_seed(self) -> Optional[bytes]:
        """
        Get Ed25519 seed from environment (TESTING ONLY).

        In production, this should return None - use CIRISVerify instead.
        """
        seed_hex = os.getenv("WALLET_ED25519_SEED")
        if seed_hex:
            try:
                logger.warning("Using WALLET_ED25519_SEED from environment - TESTING ONLY")
                return bytes.fromhex(seed_hex)
            except ValueError:
                logger.warning("Invalid WALLET_ED25519_SEED format")
        return None

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """
        Get services provided by this adapter.

        Returns TOOL service registration for wallet operations.
        """
        registrations = []

        # Register TOOL service for wallet operations
        registrations.append(
            AdapterServiceRegistration(
                service_type=ServiceType.TOOL,
                provider=self.tool_service,
                priority=Priority.NORMAL,
                capabilities=[
                    "execute_tool",
                    "get_available_tools",
                    "send_money",
                    "request_money",
                    "get_statement",
                    "provider:wallet",
                ],
            )
        )

        return registrations

    async def start(self) -> None:
        """Start the Wallet adapter."""
        logger.info("Starting Wallet adapter")

        # Start tool service (which initializes providers)
        await self.tool_service.start()
        logger.info("WalletToolService started")

        # Register balance change callback for audit logging
        self._register_balance_audit_callback()

        self._running = True
        logger.info("Wallet adapter started")

    def _register_balance_audit_callback(self) -> None:
        """Register callback to emit audit events when funds are received."""
        x402_provider = self._providers.get("x402")
        if x402_provider and hasattr(x402_provider, "register_balance_callback"):
            x402_provider.register_balance_callback(self._on_funds_received)
            logger.info("Registered balance audit callback for x402 provider")

    def _on_funds_received(
        self,
        provider_id: str,
        new_balance: Any,
        incoming_tx: Optional[Any]
    ) -> None:
        """Handle balance change and emit audit event for received funds."""
        if incoming_tx is None:
            return  # No incoming transaction, just balance refresh

        # Emit audit event asynchronously
        asyncio.create_task(self._emit_funds_received_audit(provider_id, new_balance, incoming_tx))

    async def _emit_funds_received_audit(
        self,
        provider_id: str,
        new_balance: Any,
        incoming_tx: Any
    ) -> None:
        """Emit audit event for received funds to all 3 sinks."""
        try:
            # Get audit service from runtime
            audit_service = None
            if self.runtime and hasattr(self.runtime, "service_initializer"):
                audit_service = getattr(self.runtime.service_initializer, "audit_service", None)

            if not audit_service:
                logger.warning("[WALLET_AUDIT] Cannot log funds_received - audit_service not available")
                return

            from ciris_engine.schemas.audit import EventPayload

            # Get wallet address from x402 provider
            wallet_address = None
            x402_provider = self._providers.get("x402")
            if x402_provider:
                wallet_address = getattr(x402_provider, "_evm_address", None)

            # Create audit event payload
            event_data = EventPayload(
                action=f"received {incoming_tx.amount} {incoming_tx.currency}",
                result="success",
                service_name="wallet_balance_monitor",
                user_id=wallet_address,
            )

            # Log to all 3 audit sinks (graph, SQLite hash chain, file)
            await audit_service.log_event("wallet_funds_received", event_data)
            logger.info(
                f"[WALLET_AUDIT] Logged funds_received: +{incoming_tx.amount} {incoming_tx.currency} "
                f"to {wallet_address}, new_balance={new_balance.total}"
            )

        except Exception as e:
            logger.error(f"[WALLET_AUDIT] Failed to emit funds_received audit: {e}")

    async def stop(self) -> None:
        """Stop the Wallet adapter."""
        logger.info("Stopping Wallet adapter")
        self._running = False

        # Stop tool service (which cleans up providers)
        await self.tool_service.stop()

        logger.info("Wallet adapter stopped")

    async def run_lifecycle(self, agent_task: Any) -> None:
        """
        Run the adapter lifecycle.

        For Wallet, we just wait for the agent task to complete.
        Payment operations are request-driven, not continuous.

        Args:
            agent_task: The main agent task to wait for, or None in first-run mode.
        """
        logger.info("Wallet adapter lifecycle started")
        try:
            # Guard against None agent_task (first-run mode)
            # This shouldn't happen with the runtime fix, but defensive coding
            if agent_task is None:
                logger.warning("Wallet adapter: agent_task is None (first-run mode), staying idle")
                # In first-run mode, just wait indefinitely until cancelled
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    pass
                return

            await agent_task
        except asyncio.CancelledError:
            logger.info("Wallet adapter lifecycle cancelled")
        finally:
            await self.stop()

    def get_config(self) -> AdapterConfig:
        """Get adapter configuration."""
        # Get loaded provider names from registry
        loaded = get_loaded_providers()

        return AdapterConfig(
            adapter_type="wallet",
            enabled=self._running,
            settings={
                "providers": list(self._providers.keys()),
                "loaded_providers": loaded,
                "default_provider": self.adapter_config.default_provider,
            },
        )

    def get_status(self) -> RuntimeAdapterStatus:
        """Get adapter status."""
        return RuntimeAdapterStatus(
            adapter_id="wallet",
            adapter_type="wallet",
            is_running=self._running,
            loaded_at=None,
            error=None,
        )

    async def get_active_channels(self) -> List[Dict[str, Any]]:
        """Get active channels (not applicable for wallet adapter)."""
        return []


# Export as Adapter for load_adapter() compatibility
Adapter = WalletAdapter
