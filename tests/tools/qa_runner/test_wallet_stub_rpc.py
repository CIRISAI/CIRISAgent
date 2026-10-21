"""QA must never talk to the public Base RPC.

v2.14.0 release build (run 37649288177), Staged QA (all_2) sqlite: 463/463
tests passed and the job still failed, because the incidents gate found

    [ChainClient] Failed to get USDC balance: Server error '503 Service
    Unavailable' for url 'https://mainnet.base.org'

(and the ETH twin). The wallet adapter auto-loads for base-mainnet and its
context-enrichment tool queries balances during context gathering, so QA was
gated on a third party's uptime. The fix is a local stub RPC the runner
points the wallet at via WALLET_X402_RPC_URL -- NOT an incidents-pattern
allow-list entry, which would hide real wallet failures.
"""

from __future__ import annotations

import logging
import pathlib
from decimal import Decimal
from typing import Iterator

import httpx
import pytest

from ciris_adapters.wallet.providers.chain_client import CHAIN_CONFIG, ChainClient
from tools.qa_runner.mock_chain_rpc import (
    BASE_MAINNET_CHAIN_ID,
    WALLET_RPC_URL_ENV,
    ZERO_WORD,
    MockChainRPCServer,
    apply_wallet_rpc_stub_env,
)

REPO = pathlib.Path(__file__).resolve().parents[3]
TEST_ADDRESS = "0x" + "ab" * 20


@pytest.fixture
def stub() -> Iterator[MockChainRPCServer]:
    server = MockChainRPCServer()
    assert server.start()
    yield server
    server.stop()


def _rpc(url: str, method: str, params: list[object]) -> dict[str, object]:
    resp = httpx.post(url, json={"jsonrpc": "2.0", "id": 7, "method": method, "params": params})
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict)
    return body


# --------------------------------------------------------------------------
# The stub itself
# --------------------------------------------------------------------------


def test_stub_binds_a_free_local_port(stub: MockChainRPCServer) -> None:
    assert stub.port != 0
    assert stub.endpoint_url.startswith("http://127.0.0.1:")


def test_stub_answers_read_calls_deterministically(stub: MockChainRPCServer) -> None:
    url = stub.endpoint_url
    assert _rpc(url, "eth_chainId", [])["result"] == hex(BASE_MAINNET_CHAIN_ID)
    assert _rpc(url, "eth_getBalance", [TEST_ADDRESS, "latest"])["result"] == "0x0"
    call = _rpc(url, "eth_call", [{"to": CHAIN_CONFIG["base-mainnet"]["usdc_address"], "data": "0x70a08231"}, "latest"])
    assert call["result"] == ZERO_WORD
    assert call["id"] == 7
    assert "error" not in call
    assert int(str(_rpc(url, "eth_blockNumber", [])["result"]), 16) >= 0
    assert _rpc(url, "eth_getTransactionReceipt", ["0x" + "00" * 32])["result"] is None
    block = _rpc(url, "eth_getBlockByNumber", ["latest", False])["result"]
    assert isinstance(block, dict) and "baseFeePerGas" in block


def test_stub_refuses_transaction_submission(stub: MockChainRPCServer) -> None:
    body = _rpc(stub.endpoint_url, "eth_sendRawTransaction", ["0xdead"])
    assert "result" not in body
    assert isinstance(body["error"], dict)


def test_stub_rejects_unknown_methods(stub: MockChainRPCServer) -> None:
    body = _rpc(stub.endpoint_url, "debug_traceTransaction", [])
    assert isinstance(body["error"], dict) and body["error"]["code"] == -32601


def test_stub_records_calls(stub: MockChainRPCServer) -> None:
    _rpc(stub.endpoint_url, "eth_chainId", [])
    _rpc(stub.endpoint_url, "eth_getBalance", [TEST_ADDRESS, "latest"])
    assert [c.method for c in stub.get_calls()] == ["eth_chainId", "eth_getBalance"]


async def test_chain_client_against_stub_logs_no_errors(
    stub: MockChainRPCServer, caplog: pytest.LogCaptureFixture
) -> None:
    """Positive: the exact calls that failed in v2.14.0 succeed against the stub."""
    client = ChainClient(network="base-mainnet", rpc_url=stub.endpoint_url)
    with caplog.at_level(logging.DEBUG, logger="ciris_adapters.wallet.providers.chain_client"):
        assert await client.get_usdc_balance(TEST_ADDRESS) == Decimal("0")
        assert await client.get_eth_balance(TEST_ADDRESS) == Decimal("0")
        assert await client.get_block_number() == 1
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert not errors, [r.getMessage() for r in errors]
    assert {c.method for c in stub.get_calls()} == {"eth_call", "eth_getBalance", "eth_blockNumber"}


# --------------------------------------------------------------------------
# Negative checks -- the defect is reproducible without the fix
# --------------------------------------------------------------------------


def test_without_override_wallet_targets_public_mainnet(monkeypatch: pytest.MonkeyPatch) -> None:
    """NEGATIVE: no WALLET_X402_RPC_URL -> the ChainClient aims at mainnet.base.org."""
    from ciris_adapters.wallet.adapter import WalletAdapter

    monkeypatch.delenv(WALLET_RPC_URL_ENV, raising=False)
    monkeypatch.delenv("WALLET_X402_ENABLED", raising=False)
    cfg = WalletAdapter._load_config_from_env(None)  # type: ignore[arg-type]  # method never touches self
    x402 = cfg.provider_configs["x402"]
    assert x402.rpc_url is None
    assert ChainClient(network=x402.network, rpc_url=x402.rpc_url).rpc_url == "https://mainnet.base.org"


def test_override_env_reaches_the_chain_client(monkeypatch: pytest.MonkeyPatch, stub: MockChainRPCServer) -> None:
    """The existing env var flows adapter config -> X402 config -> ChainClient."""
    from ciris_adapters.wallet.adapter import WalletAdapter

    env: dict[str, str] = {}
    assert apply_wallet_rpc_stub_env(env, stub, operator_env={})
    monkeypatch.setenv(WALLET_RPC_URL_ENV, env[WALLET_RPC_URL_ENV])
    cfg = WalletAdapter._load_config_from_env(None)  # type: ignore[arg-type]  # method never touches self
    x402 = cfg.provider_configs["x402"]
    assert ChainClient(network=x402.network, rpc_url=x402.rpc_url).rpc_url == stub.endpoint_url


async def test_upstream_503_is_logged_as_chain_client_error(caplog: pytest.LogCaptureFixture) -> None:
    """NEGATIVE: an RPC answering 503 reproduces the exact v2.14.0 incident lines.

    This is why the incidents gate went red, and why the fix is to stop
    talking to a live RPC rather than to allow-list the message.
    """
    outage = MockChainRPCServer(forced_status=503)
    assert outage.start()
    try:
        client = ChainClient(network="base-mainnet", rpc_url=outage.endpoint_url)
        with caplog.at_level(logging.ERROR, logger="ciris_adapters.wallet.providers.chain_client"):
            assert await client.get_usdc_balance(TEST_ADDRESS) == Decimal("0")
            assert await client.get_eth_balance(TEST_ADDRESS) == Decimal("0")
    finally:
        outage.stop()
    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert any("[ChainClient] Failed to get USDC balance" in m and "503" in m for m in messages), messages
    assert any("[ChainClient] Failed to get ETH balance" in m and "503" in m for m in messages), messages


def test_chain_client_error_is_not_allow_listed() -> None:
    """The fix must not be an incidents-gate allow-list entry."""
    from tools.qa_runner.runner import EXPECTED_QA_INCIDENT_PATTERNS

    joined = " ".join(str(p) for p in EXPECTED_QA_INCIDENT_PATTERNS)
    assert "ChainClient" not in joined
    assert "mainnet.base.org" not in joined


# --------------------------------------------------------------------------
# Runner wiring
# --------------------------------------------------------------------------


def test_apply_env_sets_stub_url(stub: MockChainRPCServer) -> None:
    env: dict[str, str] = {}
    assert apply_wallet_rpc_stub_env(env, stub, operator_env={})
    assert env[WALLET_RPC_URL_ENV] == stub.endpoint_url


def test_operator_export_wins(stub: MockChainRPCServer) -> None:
    env = {WALLET_RPC_URL_ENV: "https://sepolia.base.org"}
    assert not apply_wallet_rpc_stub_env(env, stub, operator_env=dict(env))
    assert env[WALLET_RPC_URL_ENV] == "https://sepolia.base.org"


def test_no_stub_no_change() -> None:
    env: dict[str, str] = {}
    assert not apply_wallet_rpc_stub_env(env, None, operator_env={})
    assert WALLET_RPC_URL_ENV not in env


def test_server_manager_starts_stub_and_wires_wallet() -> None:
    """APIServerManager.start() must start the stub and apply it to the agent env; stop() must stop it."""
    src = (REPO / "tools" / "qa_runner" / "server.py").read_text(encoding="utf-8")
    start_body = src[src.index('    def start(self) -> bool:\n        """Start the API server') :]
    assert "self.mock_chain_rpc = MockChainRPCServer()" in start_body
    assert "apply_wallet_rpc_stub_env(env, self.mock_chain_rpc, os.environ)" in start_body
    assert "self.mock_chain_rpc.stop()" in src


async def test_x402_provider_from_env_fetches_balance_via_stub(
    monkeypatch: pytest.MonkeyPatch, stub: MockChainRPCServer, caplog: pytest.LogCaptureFixture
) -> None:
    """End to end inside the wallet: env -> adapter config -> X402Provider -> stub.

    _fetch_balance_from_chain is the path wallet:get_statement takes during
    context enrichment -- the one that hit mainnet in v2.14.0.
    """
    from ciris_adapters.wallet.adapter import WalletAdapter
    from ciris_adapters.wallet.providers.x402_provider import X402Provider

    env: dict[str, str] = {}
    apply_wallet_rpc_stub_env(env, stub, operator_env={})
    monkeypatch.setenv(WALLET_RPC_URL_ENV, env[WALLET_RPC_URL_ENV])
    cfg = WalletAdapter._load_config_from_env(None)  # type: ignore[arg-type]  # method never touches self
    provider = X402Provider(cfg.provider_configs["x402"], evm_address=TEST_ADDRESS)

    with caplog.at_level(logging.ERROR):
        balance = await provider._fetch_balance_from_chain()
    assert balance.available == Decimal("0")
    assert not [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert {c.method for c in stub.get_calls()} == {"eth_call", "eth_getBalance"}
