"""
Comprehensive tests for agent_wallet.py
25+ pytest tests covering balance checks, error cases, networks,
transaction history, Jupiter swap, and RPC failover.
"""

import json
import time
import pytest
from unittest.mock import patch, MagicMock
from urllib.error import URLError

from agent_wallet import (
    DEFAULT_WALLET,
    KNOWN_TOKENS_MAINNET,
    KNOWN_TOKENS_DEVNET,
    RPC_ENDPOINTS,
    NETWORK_URLS,
    JUPITER_MINTS,
    MAX_RPC_RETRIES,
    TokenBalance,
    TransactionInfo,
    JupiterQuote,
    JupiterSwapResult,
    WalletStatus,
    RPCError,
    rpc_call,
    rpc_call_safe,
    read_wallet_balance,
    read_wallet_balance_rpc,
    read_spl_token_balances,
    get_signatures,
    get_transaction,
    get_transaction_history,
    jupiter_quote,
    jupiter_swap,
    agent_wallet_status,
    read_crypto_identity,
    _run_cmd,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

def _mock_rpc_response(result):
    """Create a mock urlopen response with the given result."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "result": result}
    ).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def _mock_rpc_error(error_msg="server error"):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "error": {"message": error_msg}}
    ).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


# ── 1. TokenBalance dataclass ──────────────────────────────────────────────

def test_token_balance_creation():
    tb = TokenBalance(mint="abc123", symbol="USDC", balance=100.5)
    assert tb.mint == "abc123"
    assert tb.symbol == "USDC"
    assert tb.balance == 100.5


# ── 2. WalletStatus dataclass ──────────────────────────────────────────────

def test_wallet_status_to_dict():
    ws = WalletStatus(wallet="abc", network="mainnet", sol_balance=1.5)
    d = ws.to_dict()
    assert d["wallet"] == "abc"
    assert d["sol_balance"] == 1.5
    assert d["tokens"] == []


def test_wallet_status_to_json():
    ws = WalletStatus(wallet="abc", network="devnet", sol_balance=2.0)
    j = json.loads(ws.to_json())
    assert j["network"] == "devnet"


def test_wallet_status_summary():
    ws = WalletStatus(
        wallet="abc", network="mainnet", sol_balance=3.0,
        tokens=[TokenBalance("m1", "USDC", 50.0)],
        rpc_endpoint_used="https://example.com",
    )
    s = ws.summary()
    assert "SOL: 3.0" in s
    assert "USDC: 50.0" in s
    assert "RPC: https://example.com" in s


def test_wallet_status_summary_with_error():
    ws = WalletStatus(wallet="abc", network="mainnet", sol_balance=-1,
                      error="Failed")
    assert "Error: Failed" in ws.summary()


# ── 3. TransactionInfo ─────────────────────────────────────────────────────

def test_transaction_info_creation():
    tx = TransactionInfo(
        signature="sig123", slot=100, block_time=1700000000,
        success=True, fee=5000, memo=None,
    )
    assert tx.to_dict()["signature"] == "sig123"
    assert tx.success is True


# ── 4. JupiterQuote ────────────────────────────────────────────────────────

def test_jupiter_quote_creation():
    q = JupiterQuote(
        input_mint="SOL", output_mint="USDC",
        input_amount=1.0, output_amount=150.0,
        price_impact_pct=0.05, route_plan="SOL->USDC",
        timestamp=time.time(),
    )
    d = q.to_dict()
    assert d["input_amount"] == 1.0
    assert d["output_amount"] == 150.0


# ── 5. JupiterSwapResult ───────────────────────────────────────────────────

def test_jupiter_swap_result():
    r = JupiterSwapResult(
        success=True, input_mint="SOL", output_mint="USDC",
        input_amount=1.0, output_amount=150.0,
        tx_signature="sig_abc",
    )
    assert r.success is True
    assert r.to_dict()["tx_signature"] == "sig_abc"


# ── 6. RPC call with failover ──────────────────────────────────────────────

@patch("agent_wallet.urlopen")
def test_rpc_call_success(mock_urlopen):
    mock_urlopen.return_value = _mock_rpc_response({"value": 1000000000})
    result = rpc_call("getBalance", ["abc123"], "mainnet")
    assert result["result"]["value"] == 1000000000


@patch("agent_wallet.urlopen")
def test_rpc_call_failover_on_error(mock_urlopen):
    """First endpoint returns error, second succeeds."""
    mock_urlopen.side_effect = [
        _mock_rpc_error("server busy"),
        _mock_rpc_response({"value": 500}),
    ]
    result = rpc_call("getBalance", ["abc"], "mainnet")
    assert result["result"]["value"] == 500
    assert mock_urlopen.call_count == 2


@patch("agent_wallet.urlopen")
def test_rpc_call_failover_on_network_error(mock_urlopen):
    """Network error on first try, success on second."""
    mock_urlopen.side_effect = [
        URLError("Connection refused"),
        _mock_rpc_response({"value": 999}),
    ]
    result = rpc_call("getBalance", ["abc"], "mainnet")
    assert result["result"]["value"] == 999


@patch("agent_wallet.urlopen")
def test_rpc_call_all_retries_fail(mock_urlopen):
    mock_urlopen.side_effect = URLError("down")
    with pytest.raises(RPCError, match="All RPC attempts failed"):
        rpc_call("getBalance", ["abc"], "mainnet")
    assert mock_urlopen.call_count == MAX_RPC_RETRIES


@patch("agent_wallet.urlopen")
def test_rpc_call_safe_returns_error(mock_urlopen):
    mock_urlopen.side_effect = URLError("down")
    data, err = rpc_call_safe("getBalance", ["abc"], "mainnet")
    assert data is None
    assert "All RPC attempts failed" in err


# ── 7. Balance (RPC) ───────────────────────────────────────────────────────

@patch("agent_wallet.rpc_call_safe")
def test_read_wallet_balance_rpc_success(mock_rpc):
    mock_rpc.return_value = (
        {"result": {"value": 5000000000}}, None
    )
    bal, _ = read_wallet_balance_rpc("abc", "mainnet")
    assert bal == 5.0


@patch("agent_wallet.rpc_call_safe")
def test_read_wallet_balance_rpc_failure(mock_rpc):
    mock_rpc.return_value = (None, "network error")
    bal, _ = read_wallet_balance_rpc("abc", "mainnet")
    assert bal == -1.0


@patch("agent_wallet.rpc_call_safe")
def test_read_wallet_balance_rpc_bad_response(mock_rpc):
    mock_rpc.return_value = ({"result": {}}, None)
    bal, _ = read_wallet_balance_rpc("abc", "mainnet")
    assert bal == -1.0


# ── 8. Balance (CLI legacy) ────────────────────────────────────────────────

@patch("agent_wallet._run_cmd")
def test_read_wallet_balance_cli_success(mock_cmd):
    mock_cmd.return_value = ("1.5 SOL", 0)
    assert read_wallet_balance("abc", "mainnet") == 1.5


@patch("agent_wallet._run_cmd")
def test_read_wallet_balance_cli_failure(mock_cmd):
    mock_cmd.return_value = ("error", 1)
    assert read_wallet_balance("abc", "mainnet") == -1.0


@patch("agent_wallet._run_cmd")
def test_read_wallet_balance_cli_bad_output(mock_cmd):
    mock_cmd.return_value = ("not_a_number SOL", 0)
    assert read_wallet_balance("abc", "mainnet") == -1.0


# ── 9. SPL tokens via RPC ──────────────────────────────────────────────────

@patch("agent_wallet.rpc_call_safe")
def test_read_spl_token_balances_success(mock_rpc):
    mock_rpc.return_value = (
        {"result": {"value": [
            {"account": {"data": {"parsed": {"info": {
                "mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "tokenAmount": {"uiAmountString": "100.5"},
            }}}}}
        ]}},
        None,
    )
    tokens = read_spl_token_balances("abc", "mainnet")
    assert len(tokens) == 1
    assert tokens[0].symbol == "USDC"
    assert tokens[0].balance == 100.5


@patch("agent_wallet.rpc_call_safe")
def test_read_spl_token_balances_failure(mock_rpc):
    mock_rpc.return_value = (None, "error")
    assert read_spl_token_balances("abc", "mainnet") == []


# ── 10. Transaction history ─────────────────────────────────────────────────

@patch("agent_wallet.get_transaction")
@patch("agent_wallet.get_signatures")
def test_get_transaction_history(mock_sigs, mock_tx):
    mock_sigs.return_value = [
        {"signature": "sig1", "slot": 100, "blockTime": 1700000000, "err": None, "memo": None},
        {"signature": "sig2", "slot": 101, "blockTime": 1700000001, "err": {"code": 1}, "memo": "test"},
    ]
    mock_tx.return_value = {"meta": {"fee": 5000}}
    txs = get_transaction_history("abc", "mainnet", limit=2)
    assert len(txs) == 2
    assert txs[0].success is True
    assert txs[0].fee == 5000
    assert txs[1].success is False


@patch("agent_wallet.rpc_call_safe")
def test_get_signatures_failure(mock_rpc):
    mock_rpc.return_value = (None, "error")
    assert get_signatures("abc") == []


@patch("agent_wallet.rpc_call_safe")
def test_get_transaction_failure(mock_rpc):
    mock_rpc.return_value = (None, "error")
    assert get_transaction("sig123") is None


# ── 11. Jupiter swap stub ──────────────────────────────────────────────────

def test_jupiter_quote_sol_to_usdc():
    q = jupiter_quote("SOL", "USDC", 1.0)
    assert q.input_amount == 1.0
    assert q.output_amount == 150.0
    assert q.price_impact_pct == 0.05
    assert "Raydium" in q.route_plan


def test_jupiter_quote_usdc_to_sol():
    q = jupiter_quote("USDC", "SOL", 150.0)
    assert q.output_amount == 1.0


def test_jupiter_quote_unknown_token():
    q = jupiter_quote("UNKNOWN", "USDC", 10.0)
    assert q.output_amount == 10.0  # 1:1 default


def test_jupiter_swap_success():
    r = jupiter_swap("SOL", "USDC", 2.0)
    assert r.success is True
    assert r.output_amount == 300.0
    assert r.tx_signature.startswith("simulated_")
    assert r.error is None


def test_jupiter_swap_with_wallet():
    r = jupiter_swap("SOL", "USDC", 1.0, wallet="custom_wallet")
    assert r.success is True


# ── 12. agent_wallet_status ─────────────────────────────────────────────────

@patch("agent_wallet.read_spl_token_balances")
@patch("agent_wallet.read_wallet_balance_rpc")
def test_agent_wallet_status_success(mock_bal, mock_spl):
    mock_bal.return_value = (5.0, None)
    mock_spl.return_value = [TokenBalance("m1", "USDC", 100.0)]
    status = agent_wallet_status(wallet="test_wallet", network="mainnet")
    assert status.sol_balance == 5.0
    assert status.is_active is True
    assert len(status.tokens) == 1


def test_agent_wallet_status_invalid_network():
    status = agent_wallet_status(network="invalid_net")
    assert status.is_active is False
    assert "Unknown network" in status.error


@patch("agent_wallet.read_spl_token_balances")
@patch("agent_wallet.read_wallet_balance_rpc")
def test_agent_wallet_status_balance_failure(mock_bal, mock_spl):
    mock_bal.return_value = (-1.0, None)
    mock_spl.return_value = []
    status = agent_wallet_status(network="mainnet")
    assert status.is_active is False
    assert "Failed to read SOL balance" in status.error


def test_agent_wallet_status_default_wallet():
    """Verify default wallet is used when none specified."""
    with patch("agent_wallet.read_wallet_balance_rpc") as m_bal, \
         patch("agent_wallet.read_spl_token_balances") as m_spl:
        m_bal.return_value = (1.0, None)
        m_spl.return_value = []
        status = agent_wallet_status()
        assert status.wallet == DEFAULT_WALLET


# ── 13. Network configurations ─────────────────────────────────────────────

def test_rpc_endpoints_all_networks():
    for net in ["mainnet", "devnet", "testnet"]:
        assert net in RPC_ENDPOINTS
        assert len(RPC_ENDPOINTS[net]) >= 1


def test_mainnet_has_multiple_endpoints():
    assert len(RPC_ENDPOINTS["mainnet"]) >= 2


def test_network_urls_compat():
    for net in RPC_ENDPOINTS:
        assert NETWORK_URLS[net] == RPC_ENDPOINTS[net][0]


# ── 14. read_crypto_identity ────────────────────────────────────────────────

def test_read_crypto_identity():
    identity = read_crypto_identity()
    assert identity["wallet"] == DEFAULT_WALLET
    assert "mainnet" in identity["networks"]
    assert "transaction_history" in identity["capabilities"]
    assert "jupiter_swap_stub" in identity["capabilities"]
    assert "rpc_failover" in identity["capabilities"]


# ── 15. _run_cmd edge cases ─────────────────────────────────────────────────

def test_run_cmd_timeout():
    out, rc = _run_cmd(["sleep", "60"], timeout=1)
    assert rc == 1
    assert out == "timeout"


def test_run_cmd_not_found():
    out, rc = _run_cmd(["nonexistent_command_xyz"])
    assert rc == 1
    assert out == "command_not_found"


# ── 16. Jupiter mints mapping ──────────────────────────────────────────────

def test_jupiter_mints_known():
    assert "SOL" in JUPITER_MINTS
    assert "USDC" in JUPITER_MINTS
    assert "USDT" in JUPITER_MINTS
