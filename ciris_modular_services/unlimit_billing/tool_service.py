"""Tool service exposing AP2-compliant Unlimit checkout."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.protocols.services.runtime.tool import ToolServiceProtocol
from ciris_engine.schemas.adapters.tools import (
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolInfo,
    ToolParameterSchema,
)
from ciris_engine.schemas.runtime.enums import ServiceType

from .ap2 import AP2CheckoutPayload, AP2MandateType
from .commerce_service import UnlimitCommerceService
from .schemas import (
    AP2CheckoutRequest,
    AP2InvoiceRequest,
    BillingChargeRequest,
    InvoiceRequest,
    PaymentCustomer,
)
from .service import UnlimitBillingService

logger = logging.getLogger(__name__)

AP2_CHECKOUT_TOOL = "ap2_unlimit_checkout"
AP2_INVOICE_TOOL = "ap2_unlimit_invoice"


class UnlimitBillingToolService(BaseService, ToolServiceProtocol):
    """AP2 tool service that executes Unlimit-backed payments."""

    def __init__(
        self,
        *,
        base_url: str = "https://api.unlimit.com",
        api_key: Optional[str] = None,
        timeout_seconds: float = 5.0,
        cache_ttl_seconds: int = 15,
        fail_open: bool = False,
        restricted_countries: Optional[set[str]] = None,
        transport=None,
    ) -> None:
        super().__init__(service_name="UnlimitBillingToolService")
        self._billing = UnlimitBillingService(
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            cache_ttl_seconds=cache_ttl_seconds,
            fail_open=fail_open,
            transport=transport,
        )
        self._commerce = UnlimitCommerceService(
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            restricted_countries=restricted_countries,
            transport=transport,
        )
        self._results: Dict[str, ToolExecutionResult] = {}
        self._results_lock = asyncio.Lock()

    # BaseService hooks

    def get_service_type(self) -> ServiceType:
        return ServiceType.TOOL

    def _get_actions(self) -> List[str]:
        return [
            "execute_tool",
            "get_available_tools",
            "get_tool_schema",
            "get_tool_info",
            "validate_parameters",
            "get_all_tool_info",
            "get_tool_result",
        ]

    def _check_dependencies(self) -> bool:
        return True

    async def _on_start(self) -> None:
        await self._billing.start()
        await self._commerce.start()

    async def _on_stop(self) -> None:
        await self._billing.stop()
        await self._commerce.stop()

    # ToolServiceProtocol implementation

    async def execute_tool(self, tool_name: str, parameters: dict) -> ToolExecutionResult:
        if tool_name == AP2_CHECKOUT_TOOL:
            return await self._execute_checkout(parameters)
        if tool_name == AP2_INVOICE_TOOL:
            return await self._execute_invoice(parameters)
        return await self._build_failed_result(tool_name, error=f"Unknown tool '{tool_name}'")

    async def list_tools(self) -> List[str]:
        return [AP2_CHECKOUT_TOOL, AP2_INVOICE_TOOL]

    async def get_available_tools(self) -> List[str]:
        return [AP2_CHECKOUT_TOOL, AP2_INVOICE_TOOL]

    async def get_tool_schema(self, tool_name: str) -> Optional[ToolParameterSchema]:
        if tool_name == AP2_CHECKOUT_TOOL:
            return self._build_checkout_schema()
        if tool_name == AP2_INVOICE_TOOL:
            return self._build_invoice_schema()
        return None

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        if tool_name == AP2_CHECKOUT_TOOL:
            return ToolInfo(
                name=AP2_CHECKOUT_TOOL,
                description=(
                    "Execute an AP2-compliant checkout using Unlimit as the payment processor. "
                    "Requires a valid mandate chain and payment credential."
                ),
                parameters=self._build_checkout_schema(),
                category="commerce",
                cost=0.0,
                when_to_use=(
                    "Use after obtaining signed AP2 mandates and the user has authorised "
                    "the agent to complete the purchase with Unlimit."
                ),
            )
        if tool_name == AP2_INVOICE_TOOL:
            return ToolInfo(
                name=AP2_INVOICE_TOOL,
                description=(
                    "Create an AP2-compliant invoice via Unlimit so the customer can pay securely "
                    "through hosted payment flows."
                ),
                parameters=self._build_invoice_schema(),
                category="commerce",
                cost=0.0,
                when_to_use="Use when you have mandates allowing you to request payment from a user.",
            )
        return None

    async def get_all_tool_info(self) -> List[ToolInfo]:
        infos = []
        for tool in [AP2_CHECKOUT_TOOL, AP2_INVOICE_TOOL]:
            info = await self.get_tool_info(tool)
            if info:
                infos.append(info)
        return infos

    async def validate_parameters(self, tool_name: str, parameters: dict) -> bool:
        try:
            if tool_name == AP2_CHECKOUT_TOOL:
                request = AP2CheckoutRequest.model_validate(parameters)
                error = self._validate_ap2_payload(request.ap2, request.charge)
                return error is None
            if tool_name == AP2_INVOICE_TOOL:
                request = AP2InvoiceRequest.model_validate(parameters)
                error = self._validate_ap2_payload(request.ap2, request.charge)
                return error is None
        except Exception:
            return False
        return False

    async def get_tool_result(self, correlation_id: str, timeout: float = 30.0) -> Optional[ToolExecutionResult]:
        async with self._results_lock:
            return self._results.get(correlation_id)

    # Helper methods

    async def _execute_checkout(self, parameters: dict) -> ToolExecutionResult:
        try:
            request = AP2CheckoutRequest.model_validate(parameters)
        except Exception as exc:
            return await self._build_failed_result(AP2_CHECKOUT_TOOL, error=f"invalid_parameters:{exc}")

        validation_error = self._validate_ap2_payload(request.ap2, request.charge)
        if validation_error:
            return await self._build_failed_result(AP2_CHECKOUT_TOOL, error=validation_error)

        charge_result = await self._billing.spend_credits(
            identity=request.identity,
            charge=request.charge,
            context=request.context,
        )

        if not charge_result.succeeded:
            return await self._build_failed_result(
                AP2_CHECKOUT_TOOL,
                error=charge_result.reason or "charge_failed",
                data={"charge_result": charge_result.model_dump()},
            )

        result_data = {
            "transaction": charge_result.model_dump(),
            "mandates": {
                "intent": request.ap2.mandates.intent.mandate_id,
                "cart": request.ap2.mandates.cart.mandate_id,
            },
            "payment_method": request.ap2.payment_method.model_dump(),
            "metadata": request.ap2.metadata,
        }

        correlation_id = self._build_correlation_id(AP2_CHECKOUT_TOOL)
        execution_result = ToolExecutionResult(
            tool_name=AP2_CHECKOUT_TOOL,
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data=result_data,
            error=None,
            correlation_id=correlation_id,
        )
        await self._store_result(execution_result)
        return execution_result

    async def _execute_invoice(self, parameters: dict) -> ToolExecutionResult:
        try:
            request = AP2InvoiceRequest.model_validate(parameters)
        except Exception as exc:
            return await self._build_failed_result(AP2_INVOICE_TOOL, error=f"invalid_parameters:{exc}")

        validation_error = self._validate_ap2_payload(request.ap2, request.charge)
        if validation_error:
            return await self._build_failed_result(AP2_INVOICE_TOOL, error=validation_error)

        invoice_request = InvoiceRequest(
            request_id=request.invoice.request_id,
            description=request.invoice.description,
            amount=request.charge.amount_minor / 100.0,
            currency=request.charge.currency,
            customer=request.customer,
            items=request.invoice.items,
            metadata=request.invoice.metadata,
        )

        invoice_result = await self._commerce.create_invoice(invoice_request)
        if not invoice_result.succeeded:
            return await self._build_failed_result(
                AP2_INVOICE_TOOL,
                error=invoice_result.reason or "invoice_failed",
                data={"invoice_result": invoice_result.model_dump()},
            )

        result_data = {
            "invoice": invoice_result.model_dump(),
            "mandates": {
                "intent": request.ap2.mandates.intent.mandate_id,
                "cart": request.ap2.mandates.cart.mandate_id,
            },
            "metadata": request.ap2.metadata,
        }

        correlation_id = self._build_correlation_id(AP2_INVOICE_TOOL)
        execution_result = ToolExecutionResult(
            tool_name=AP2_INVOICE_TOOL,
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data=result_data,
            error=None,
            correlation_id=correlation_id,
        )
        await self._store_result(execution_result)
        return execution_result

    async def _build_failed_result(
        self,
        tool_name: str,
        *,
        error: str,
        data: Optional[Dict[str, object]] = None,
    ) -> ToolExecutionResult:
        correlation_id = self._build_correlation_id(tool_name)
        result = ToolExecutionResult(
            tool_name=tool_name,
            status=ToolExecutionStatus.FAILED,
            success=False,
            data=data,
            error=error,
            correlation_id=correlation_id,
        )
        await self._store_result(result)
        logger.warning("Tool %s failed: %s", tool_name, error)
        return result

    def _validate_ap2_payload(
        self,
        payload: AP2CheckoutPayload,
        charge: BillingChargeRequest,
    ) -> Optional[str]:
        now = datetime.now(timezone.utc)

        intent = payload.mandates.intent
        cart = payload.mandates.cart

        if intent.mandate_type != AP2MandateType.INTENT:
            return "invalid_mandate_type:intent"

        if cart.mandate_type != AP2MandateType.CART:
            return "invalid_mandate_type:cart"

        if intent.expires_at and intent.expires_at < now:
            return "intent_mandate_expired"

        if cart.expires_at and cart.expires_at < now:
            return "cart_mandate_expired"

        if cart.amount_minor is not None and cart.amount_minor != charge.amount_minor:
            return "amount_mismatch"

        if cart.currency and cart.currency != charge.currency:
            return "currency_mismatch"

        if payload.payment_method.linked_mandate_id and (
            payload.payment_method.linked_mandate_id != cart.mandate_id
        ):
            return "payment_method_not_linked_to_cart"

        return None

    def _build_checkout_schema(self) -> ToolParameterSchema:
        return ToolParameterSchema(
            type="object",
            properties={
                "identity": {
                    "type": "object",
                    "properties": {
                        "oauth_provider": {"type": "string"},
                        "external_id": {"type": "string"},
                        "wa_id": {"type": "string"},
                        "tenant_id": {"type": "string"},
                    },
                    "required": ["oauth_provider", "external_id"],
                },
                "charge": {
                    "type": "object",
                    "properties": {
                        "amount_minor": {"type": "integer", "minimum": 1},
                        "currency": {"type": "string", "minLength": 3, "maxLength": 3},
                        "description": {"type": "string"},
                        "metadata": {"type": "object", "additionalProperties": {"type": "string"}},
                    },
                    "required": ["amount_minor", "currency"],
                },
                "context": {
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string"},
                        "channel_id": {"type": "string"},
                        "request_id": {"type": "string"},
                        "metadata": {"type": "object", "additionalProperties": {"type": "string"}},
                    },
                },
                "ap2": {
                    "type": "object",
                    "properties": {
                        "mandates": {
                            "type": "object",
                            "properties": {
                                "intent": {
                                    "type": "object",
                                    "properties": {
                                        "mandate_id": {"type": "string"},
                                        "mandate_type": {"const": "intent"},
                                        "issued_at": {"type": "string", "format": "date-time"},
                                        "expires_at": {"type": "string", "format": "date-time"},
                                        "amount_minor": {"type": "integer"},
                                        "currency": {"type": "string"},
                                        "instructions": {"type": "object", "additionalProperties": {"type": "string"}},
                                        "constraints": {"type": "object", "additionalProperties": {"type": "string"}},
                                        "credential_reference": {"type": "string"},
                                        "signature": {"type": "string"},
                                    },
                                    "required": ["mandate_id", "mandate_type", "issued_at", "signature"],
                                },
                                "cart": {
                                    "type": "object",
                                    "properties": {
                                        "mandate_id": {"type": "string"},
                                        "mandate_type": {"const": "cart"},
                                        "issued_at": {"type": "string", "format": "date-time"},
                                        "expires_at": {"type": "string", "format": "date-time"},
                                        "amount_minor": {"type": "integer"},
                                        "currency": {"type": "string"},
                                        "instructions": {"type": "object", "additionalProperties": {"type": "string"}},
                                        "constraints": {"type": "object", "additionalProperties": {"type": "string"}},
                                        "credential_reference": {"type": "string"},
                                        "signature": {"type": "string"},
                                    },
                                    "required": ["mandate_id", "mandate_type", "issued_at", "signature"],
                                },
                                "credentials": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "credential_id": {"type": "string"},
                                            "issuer": {"type": "string"},
                                            "subject": {"type": "string"},
                                            "issued_at": {"type": "string", "format": "date-time"},
                                            "expires_at": {"type": "string", "format": "date-time"},
                                            "proof_type": {"type": "string"},
                                            "proof_value": {"type": "string"},
                                            "metadata": {
                                                "type": "object",
                                                "additionalProperties": {"type": "string"},
                                            },
                                        },
                                        "required": [
                                            "credential_id",
                                            "issuer",
                                            "subject",
                                            "issued_at",
                                            "proof_type",
                                            "proof_value",
                                        ],
                                    },
                                    "default": [],
                                },
                            },
                            "required": ["intent", "cart"],
                        },
                        "payment_method": {
                            "type": "object",
                            "properties": {
                                "method_type": {"type": "string"},
                                "provider": {"type": "string"},
                                "network": {"type": "string"},
                                "payment_token": {"type": "string"},
                                "display_name": {"type": "string"},
                                "linked_mandate_id": {"type": "string"},
                                "metadata": {
                                    "type": "object",
                                    "additionalProperties": {"type": "string"},
                                },
                            },
                            "required": ["method_type", "payment_token"],
                        },
                        "proof": {
                            "type": "object",
                            "properties": {
                                "proof_type": {"type": "string"},
                                "proof_value": {"type": "string"},
                                "verification_service": {"type": "string", "format": "uri"},
                                "metadata": {
                                    "type": "object",
                                    "additionalProperties": {"type": "string"},
                                },
                            },
                        },
                        "metadata": {
                            "type": "object",
                            "additionalProperties": {"type": "string"},
                        },
                    },
                    "required": ["mandates", "payment_method"],
                },
            },
            required=["identity", "charge", "ap2"],
        )

    def _build_invoice_schema(self) -> ToolParameterSchema:
        schema = self._build_checkout_schema().model_copy(deep=True)
        schema.properties["invoice"] = {
            "type": "object",
            "properties": {
                "request_id": {"type": "string"},
                "description": {"type": "string"},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "quantity": {"type": "integer", "minimum": 1},
                            "unit_price": {"type": "number", "minimum": 0},
                        },
                        "required": ["name", "quantity", "unit_price"],
                    },
                },
                "metadata": {"type": "object", "additionalProperties": {"type": "string"}},
            },
            "required": ["request_id", "description"],
        }
        schema.properties["customer"] = {
            "type": "object",
            "properties": {
                "email": {"type": "string"},
                "phone": {"type": "string"},
                "full_name": {"type": "string"},
                "country": {"type": "string", "minLength": 2, "maxLength": 2},
            },
        }
        schema.required.append("invoice")
        return schema

    def _build_correlation_id(self, tool_name: str) -> str:
        return f"{tool_name}_{uuid4()}"

    async def _store_result(self, result: ToolExecutionResult) -> None:
        async with self._results_lock:
            # Keep only last 50 results to avoid unbounded growth
            if len(self._results) >= 50:
                oldest_key = next(iter(self._results))
                self._results.pop(oldest_key, None)
            self._results[result.correlation_id] = result


__all__ = ["UnlimitBillingToolService", "AP2_CHECKOUT_TOOL"]
