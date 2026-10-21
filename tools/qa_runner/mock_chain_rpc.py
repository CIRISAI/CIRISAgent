"""
Local stub JSON-RPC server for the wallet adapter during QA.

The wallet adapter auto-loads at startup (bootstrap_helpers) with x402 on
base-mainnet, and its context-enrichment tool ``wallet:get_statement`` calls
the chain during context gathering. Without an override every QA run queries
the public ``https://mainnet.base.org`` endpoint, so an outage of that third
party turns the QA incidents gate red (v2.14.0, run 37649288177: 503s logged
as ``[ChainClient] Failed to get USDC/ETH balance`` ERRORs).

This stub answers the read-only calls ``ChainClient`` issues with
deterministic values. The QA runner points the wallet at it through the
adapter's existing ``WALLET_X402_RPC_URL`` env var, so QA never talks to
mainnet. It refuses ``eth_sendRawTransaction``: QA must never submit a
transaction, and a submission attempt should be loud.

Same lifecycle shape as ``MockLogshipperServer`` in ``server.py``.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List, Mapping, MutableMapping, Optional, Union

from pydantic import BaseModel, Field, JsonValue

# Env var the wallet adapter already reads for the x402 ChainClient RPC URL
# (ciris_adapters/wallet/adapter.py::_load_config_from_env).
WALLET_RPC_URL_ENV = "WALLET_X402_RPC_URL"

# Base mainnet chain id - the network the wallet initialises for in QA.
BASE_MAINNET_CHAIN_ID = 8453

# Deterministic answers. Balances are zero (a fresh QA wallet holds nothing),
# so the stub cannot make a test pass by inventing funds.
ZERO_WORD = "0x" + "0" * 64
STUB_BLOCK_NUMBER = "0x1"
STUB_GAS_PRICE = "0x3b9aca00"  # 1 gwei
STUB_GAS_ESTIMATE = "0x5208"  # 21000
STUB_BASE_FEE = "0x0"

JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_SERVER_ERROR = -32000


class JsonRpcError(BaseModel):
    """JSON-RPC 2.0 error object."""

    code: int
    message: str


class JsonRpcResponse(BaseModel):
    """JSON-RPC 2.0 response envelope."""

    jsonrpc: str = "2.0"
    id: Optional[Union[int, str]] = None
    result: JsonValue = None
    error: Optional[JsonRpcError] = None

    def to_wire(self) -> bytes:
        body = self.model_dump(exclude_none=False)
        # Per spec a response carries exactly one of result / error.
        if self.error is not None:
            body.pop("result", None)
        else:
            body.pop("error", None)
        return json.dumps(body).encode("utf-8")


class RecordedCall(BaseModel):
    """One RPC call the stub received (for assertions and the stop report)."""

    method: str
    params: List[JsonValue] = Field(default_factory=list)


def answer_rpc(method: str, chain_id: int) -> JsonRpcResponse:
    """Deterministic answer for one JSON-RPC method (id filled in by caller)."""
    static: Dict[str, JsonValue] = {
        "eth_chainId": hex(chain_id),
        "net_version": str(chain_id),
        "eth_getBalance": "0x0",
        # ERC-20 balanceOf / allowance and EntryPoint getNonce all decode a
        # single uint256 word - zero for each.
        "eth_call": ZERO_WORD,
        "eth_blockNumber": STUB_BLOCK_NUMBER,
        "eth_getTransactionCount": "0x0",
        "eth_gasPrice": STUB_GAS_PRICE,
        "eth_estimateGas": STUB_GAS_ESTIMATE,
        "eth_getTransactionReceipt": None,
        "eth_getBlockByNumber": {
            "number": STUB_BLOCK_NUMBER,
            "baseFeePerGas": STUB_BASE_FEE,
            "timestamp": "0x0",
            "transactions": [],
        },
    }
    if method in static:
        return JsonRpcResponse(result=static[method])
    if method == "eth_sendRawTransaction":
        return JsonRpcResponse(
            error=JsonRpcError(
                code=JSONRPC_SERVER_ERROR,
                message="QA stub RPC refuses transaction submission",
            )
        )
    return JsonRpcResponse(
        error=JsonRpcError(code=JSONRPC_METHOD_NOT_FOUND, message=f"QA stub RPC: method not found: {method}")
    )


class _MockChainRPCHTTPServer(HTTPServer):
    """HTTPServer holding per-instance state (see _MockLogshipperHTTPServer)."""

    chain_id: int
    forced_status: Optional[int]
    calls: List[RecordedCall]
    calls_lock: threading.Lock


class MockChainRPCHandler(BaseHTTPRequestHandler):
    """Answers JSON-RPC POSTs on any path."""

    server: _MockChainRPCHTTPServer

    def log_message(self, format: str, *args: object) -> None:
        """Suppress default logging."""

    def _send(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)

        if self.server.forced_status is not None:
            # Test hook: emulate an upstream outage (e.g. 503).
            self._send(self.server.forced_status, b'{"error": "forced by QA stub"}')
            return

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        if not isinstance(payload, dict) or not isinstance(payload.get("method"), str):
            invalid = JsonRpcResponse(error=JsonRpcError(code=JSONRPC_INVALID_REQUEST, message="Invalid Request"))
            self._send(200, invalid.to_wire())
            return

        method: str = payload["method"]
        params = payload.get("params")
        with self.server.calls_lock:
            self.server.calls.append(RecordedCall(method=method, params=params if isinstance(params, list) else []))

        response = answer_rpc(method, self.server.chain_id)
        request_id = payload.get("id")
        response.id = request_id if isinstance(request_id, (int, str)) else None
        self._send(200, response.to_wire())


class MockChainRPCServer:
    """Local stub Base RPC for QA, run in a background thread.

    port=0 (the default) binds an OS-assigned free port, so concurrent
    backends under --parallel-backends never collide.
    """

    def __init__(
        self,
        port: int = 0,
        chain_id: int = BASE_MAINNET_CHAIN_ID,
        forced_status: Optional[int] = None,
    ) -> None:
        self.port = port
        self.chain_id = chain_id
        self.forced_status = forced_status
        self.server: Optional[_MockChainRPCHTTPServer] = None
        self.thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        """Start the stub in a background thread."""
        try:
            server = _MockChainRPCHTTPServer(("127.0.0.1", self.port), MockChainRPCHandler)
        except OSError:
            return False
        server.chain_id = self.chain_id
        server.forced_status = self.forced_status
        server.calls = []
        server.calls_lock = threading.Lock()
        self.port = server.server_address[1]
        self.server = server
        self.thread = threading.Thread(target=server.serve_forever, daemon=True)
        self.thread.start()
        return True

    def stop(self) -> None:
        """Stop the stub."""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None

    def get_calls(self) -> List[RecordedCall]:
        """RPC calls received so far."""
        if self.server is None:
            return []
        with self.server.calls_lock:
            return list(self.server.calls)

    @property
    def endpoint_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


def apply_wallet_rpc_stub_env(
    env: MutableMapping[str, str], stub: Optional[MockChainRPCServer], operator_env: Mapping[str, str]
) -> bool:
    """Point the agent's wallet at the stub RPC.

    An operator-exported WALLET_X402_RPC_URL wins (same precedence as
    apply_module_server_env), so a deliberate testnet/mainnet run is still
    possible. Returns True when the stub URL was applied.
    """
    if stub is None or WALLET_RPC_URL_ENV in operator_env:
        return False
    env[WALLET_RPC_URL_ENV] = stub.endpoint_url
    return True
