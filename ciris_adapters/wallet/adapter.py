"""
Wallet Adapter for CIRIS.

Provides generic money tools (send_money, request_money, get_statement)
that work across crypto (x402/USDC) and fiat (Chapa/ETB) providers.

This adapter follows the CIRIS adapter pattern:
- Tool service registered with ToolBus
- Provider-agnostic interface
- DMA-gated financial operations

KEY ARCHITECTURE: CIRISVerify is the ONLY source for wallet primitives
- EVM address derived from CIRISVerify secp256k1 key (hardware-backed when available)
- Transaction signing via CIRISVerify (key never leaves secure boundary)
- Every CIRIS agent has a deterministic wallet address from birth
- NO fallback address derivation or local key handling
"""

import asyncio
import logging
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, RuntimeAdapterStatus
from ciris_engine.schemas.runtime.enums import ServiceType

from .config import WalletAdapterConfig
from .providers.registry import ProviderLoadError, create_provider, get_loaded_providers
from .tool_service import WalletToolService

logger = logging.getLogger(__name__)


class WalletAdapter(Service):
    """
    Wallet adapter platform for CIRIS.

    Provides generic money tools that abstract crypto and fiat payments:
    - send_money: Send to any recipient (USDC address, phone number, etc.)
    - request_money: Create payment requests/invoices
    - get_statement: Check balance and transaction history

    CRITICAL: x402 provider requires CIRISVerify 1.3.1+ for wallet operations.
    If CIRISVerify is unavailable or lacks wallet support, x402 will not load.
    """

    def __init__(
        self,
        runtime: Any,
        context: Optional[Any] = None,
        config: Optional[WalletAdapterConfig] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize Wallet adapter."""
        logger.warning("[WALLET_INIT] WalletAdapter.__init__ starting")

        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime
        self.context = context

        # Load configuration
        logger.warning("[WALLET_INIT] Loading config from environment")
        self.adapter_config = config or self._load_config_from_env()
        logger.warning(
            f"[WALLET_INIT] Config loaded with providers: {list(self.adapter_config.provider_configs.keys())}"
        )

        # Initialize providers
        self._providers: Dict[str, Any] = {}
        logger.warning("[WALLET_INIT] Calling _init_providers()")
        self._init_providers()
        logger.warning(f"[WALLET_INIT] _init_providers() complete, loaded: {list(self._providers.keys())}")

        # Create tool service
        self.tool_service = WalletToolService(
            config=self.adapter_config,
            providers=self._providers,
        )

        # Track adapter state
        self._running = False

        logger.warning(f"[WALLET_INIT] WalletAdapter.__init__ complete with providers: {list(self._providers.keys())}")

    def _load_config_from_env(self) -> WalletAdapterConfig:
        """Load configuration from environment variables."""
        import os

        from .config import (
            ChapaProviderConfig,
            MPesaProviderConfig,
            PIXProviderConfig,
            RazorpayProviderConfig,
            StripeProviderConfig,
            WiseProviderConfig,
            X402ProviderConfig,
        )

        provider_configs: Dict[str, Any] = {}

        # x402 (USDC on Base L2) - ENABLED BY DEFAULT
        if os.getenv("WALLET_X402_ENABLED", "true").lower() == "true":
            provider_configs["x402"] = X402ProviderConfig(
                enabled=True,
                network=os.getenv("WALLET_X402_NETWORK", "base-mainnet"),
                rpc_url=os.getenv("WALLET_X402_RPC_URL"),
                treasury_address=os.getenv("WALLET_X402_TREASURY_ADDRESS"),
                facilitator_url=os.getenv("WALLET_X402_FACILITATOR_URL", "https://x402.org/facilitator"),
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
        """Initialize enabled wallet providers.

        For x402: CIRISVerify 1.3.1+ is REQUIRED. No fallback.
        """
        provider_configs = self.adapter_config.provider_configs
        logger.warning(
            f"[WALLET_INIT] _init_providers: {len(provider_configs)} configs: {list(provider_configs.keys())}"
        )

        for provider_name, config in provider_configs.items():
            logger.warning(f"[WALLET_INIT] Processing provider: {provider_name}, enabled={config.enabled}")
            if not config.enabled:
                logger.warning(f"[WALLET_INIT] Skipping disabled provider: {provider_name}")
                continue

            try:
                kwargs: Dict[str, Any] = {}

                # x402 requires CIRISVerify wallet - no fallback
                if provider_name == "x402":
                    logger.warning("[WALLET_INIT] x402 provider - calling _get_ciris_verify_wallet()")
                    evm_address, signing_callback = self._get_ciris_verify_wallet()
                    logger.warning(f"[WALLET_INIT] _get_ciris_verify_wallet returned: address={evm_address}")

                    if not evm_address:
                        logger.error(
                            "[WALLET_INIT] x402 FAILED: CIRISVerify 1.3.1+ with loaded key required. "
                            "Wallet will not be available."
                        )
                        continue

                    kwargs["evm_address"] = evm_address
                    kwargs["evm_signing_callback"] = signing_callback
                    logger.warning(f"[WALLET_INIT] x402 provider using CIRISVerify wallet: {evm_address}")

                # Create the provider
                logger.warning(f"[WALLET_INIT] Creating provider: {provider_name}")
                provider = create_provider(provider_name, config=config, **kwargs)
                self._providers[provider_name] = provider
                logger.warning(f"[WALLET_INIT] Successfully loaded provider: {provider_name}")

            except ProviderLoadError as e:
                logger.error(f"[WALLET_INIT] ProviderLoadError for {provider_name}: {e}")
            except ValueError as e:
                logger.error(f"[WALLET_INIT] ValueError for {provider_name}: {e}")
            except Exception as e:
                import traceback

                logger.error(f"[WALLET_INIT] Exception for {provider_name}: {type(e).__name__}: {e}")
                logger.error(f"[WALLET_INIT] Traceback: {traceback.format_exc()}")

    def _get_ciris_verify_wallet(self) -> tuple[Optional[str], Optional[Callable[[bytes, int], bytes]]]:
        """
        Get EVM wallet address and secp256k1 signing callback from CIRISVerify.

        CIRISVerify 1.3.1+ provides unified wallet support:
        - Deterministic secp256k1 key derived from Ed25519 root identity
        - EVM address derived from secp256k1 public key (keccak256)
        - Hardware-backed signing when available (Android StrongBox/TEE)

        Returns:
            Tuple of (evm_address, signing_callback)
            - evm_address: Checksummed EVM address (0x...) or None
            - signing_callback: Function(tx_hash, chain_id) -> signature or None

        The private key NEVER leaves the secure boundary.
        """
        import os

        logger.warning("[WALLET_INIT] Starting CIRISVerify wallet initialization...")
        logger.warning(f"[WALLET_INIT] CIRIS_HOME={os.environ.get('CIRIS_HOME', 'NOT SET')}")
        logger.warning(f"[WALLET_INIT] CIRIS_DATA_DIR={os.environ.get('CIRIS_DATA_DIR', 'NOT SET')}")

        try:
            logger.warning("[WALLET_INIT] Importing verifier_singleton...")
            from ciris_engine.logic.services.infrastructure.authentication.verifier_singleton import (
                get_verifier,
                has_verifier,
            )

            logger.warning(f"[WALLET_INIT] verifier_singleton imported, has_verifier={has_verifier()}")

            logger.warning("[WALLET_INIT] Calling get_verifier()...")
            verifier = get_verifier()
            logger.warning(f"[WALLET_INIT] Got verifier instance: {type(verifier).__name__}")

            # Check if verifier has a key
            logger.warning("[WALLET_INIT] Checking has_key_sync()...")
            has_key = verifier.has_key_sync()
            logger.warning(f"[WALLET_INIT] has_key_sync={has_key}")
            if not has_key:
                logger.error("[WALLET_INIT] FAILED: CIRISVerify has no key loaded - wallet unavailable")
                return None, None

            # Check for wallet support (CIRISVerify 1.3.0+)
            has_wallet = getattr(verifier, "_has_wallet_support", False)
            logger.warning(f"[WALLET_INIT] _has_wallet_support={has_wallet}")
            if not has_wallet:
                logger.error("[WALLET_INIT] FAILED: CIRISVerify version < 1.3.0, no wallet support")
                return None, None

            # Get EVM address via secp256k1 derivation (more reliable than get_wallet_info)
            # This derives the secp256k1 pubkey from Ed25519 seed, then derives EVM address
            logger.warning("[WALLET_INIT] Calling get_evm_address_checksummed()...")
            try:
                evm_address = verifier.get_evm_address_checksummed()
                logger.warning(f"[WALLET_INIT] SUCCESS: EVM address = {evm_address}")
            except Exception as addr_err:
                # Fallback to get_wallet_info if get_evm_address_checksummed fails
                logger.warning(
                    f"[WALLET_INIT] get_evm_address_checksummed failed: {addr_err}, trying get_wallet_info..."
                )
                wallet_info = verifier.get_wallet_info()
                logger.warning(f"[WALLET_INIT] wallet_info keys: {list(wallet_info.keys()) if wallet_info else 'None'}")
                evm_address = wallet_info.get("evm_address")
                logger.warning(f"[WALLET_INIT] SUCCESS via fallback: EVM address = {evm_address}")

            # Create signing callback for EVM transactions (EIP-155)
            def signing_callback(tx_hash: bytes, chain_id: int) -> bytes:
                """Sign EVM transaction via CIRISVerify (key never leaves secure boundary)."""
                logger.debug(f"[WALLET_SIGN] Signing tx_hash={tx_hash.hex()[:16]}... chain_id={chain_id}")
                result: bytes = verifier.sign_evm_transaction(tx_hash, chain_id)
                logger.debug(f"[WALLET_SIGN] Signature: {result.hex()[:32]}...")
                return result

            return evm_address, signing_callback

        except ImportError as e:
            logger.error(f"[WALLET_INIT] FAILED: Import error - {e}")
            import traceback

            logger.error(f"[WALLET_INIT] Traceback: {traceback.format_exc()}")
            return None, None
        except RuntimeError as e:
            logger.error(f"[WALLET_INIT] FAILED: Runtime error - {e}")
            import traceback

            logger.error(f"[WALLET_INIT] Traceback: {traceback.format_exc()}")
            return None, None
        except Exception as e:
            logger.error(f"[WALLET_INIT] FAILED: Unexpected error - {type(e).__name__}: {e}")
            import traceback

            logger.error(f"[WALLET_INIT] Traceback: {traceback.format_exc()}")
            return None, None

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Get services provided by this adapter."""
        registrations = []

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

        await self.tool_service.start()
        logger.info("WalletToolService started")

        self._register_balance_audit_callback()

        self._running = True
        logger.info("Wallet adapter started")

    def _register_balance_audit_callback(self) -> None:
        """Register callbacks to emit audit events when funds are received."""
        x402_provider = self._providers.get("x402")
        if not x402_provider:
            return

        # Register sync balance callback
        if hasattr(x402_provider, "register_balance_callback"):
            x402_provider.register_balance_callback(self._on_funds_received)
            logger.info("Registered balance audit callback for x402 provider")

        # Register async audit callback with spam prevention
        if hasattr(x402_provider, "set_receive_audit_callback"):
            x402_provider.set_receive_audit_callback(self._audit_receive_with_spam_prevention)
            logger.info("Registered async receive audit callback for x402 provider")

    def _on_funds_received(self, provider_id: str, new_balance: Any, incoming_tx: Optional[Any]) -> None:
        """Handle balance change and emit audit event for received funds.

        NOTE: This is a legacy sync callback. The async audit with spam prevention
        is now handled by set_receive_audit_callback on the provider.
        """
        if incoming_tx is None:
            return

        # Log balance change event (non-audit)
        logger.info(
            f"[WALLET_BALANCE] Balance changed for {provider_id}: "
            f"new_total={new_balance.total}, "
            f"incoming={incoming_tx.amount if incoming_tx else 'N/A'}"
        )

    async def _audit_receive_with_spam_prevention(
        self, sender: str, amount: Decimal, currency: str, tx_hash: Optional[str]
    ) -> None:
        """
        Audit a received payment using the wallet audit helper.

        Uses spam prevention to filter:
        - Dust amounts (< $0.01 USDC)
        - Duplicate receives within 30 seconds
        """
        try:
            from .audit import get_wallet_audit_helper

            # Get audit service from runtime
            audit_service = None
            if self.runtime and hasattr(self.runtime, "service_initializer"):
                audit_service = getattr(self.runtime.service_initializer, "audit_service", None)

            if not audit_service:
                # Try getting from runtime directly
                audit_service = getattr(self.runtime, "audit_service", None)

            # Get audit helper with service
            audit_helper = get_wallet_audit_helper(audit_service)

            # Get network from x402 provider
            network = "base-mainnet"
            x402_provider = self._providers.get("x402")
            if x402_provider and hasattr(x402_provider, "config"):
                network = getattr(x402_provider.config, "network", "base-mainnet")

            # Audit with spam prevention (dust filter, dedup filter)
            audited = await audit_helper.audit_receive(
                sender=sender,
                amount=amount,
                currency=currency,
                tx_hash=tx_hash,
                network=network,
            )

            if audited:
                logger.info(f"[WALLET_AUDIT] Audited receive: +{amount} {currency} from {sender[:10]}...")
            else:
                logger.debug(f"[WALLET_AUDIT] Skipped receive audit (spam prevention): {amount} {currency}")

        except Exception as e:
            logger.error(f"[WALLET_AUDIT] Failed to audit receive: {e}")

    async def stop(self) -> None:
        """Stop the Wallet adapter."""
        logger.info("Stopping Wallet adapter")
        self._running = False

        await self.tool_service.stop()

        logger.info("Wallet adapter stopped")

    async def run_lifecycle(self, agent_task: Any) -> None:
        """Run the adapter lifecycle."""
        logger.info("Wallet adapter lifecycle started")
        try:
            if agent_task is None:
                logger.warning("Wallet adapter: agent_task is None (first-run mode), staying idle")
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
