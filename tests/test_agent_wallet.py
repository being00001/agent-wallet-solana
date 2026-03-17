"""Tests for agent_wallet tool."""

import json
import subprocess
import sys
import os
from unittest.mock import patch, MagicMock

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.agent_wallet import (
    agent_wallet_status,
    read_wallet_balance,
    read_spl_token_balances,
    read_crypto_identity,
    WalletStatus,
    TokenBalance,
    DEFAULT_WALLET,
    NETWORK_URLS,
)


class TestWalletStatus:
    def test_wallet_status_dataclass(self):
        ws = WalletStatus(wallet="abc", network="devnet", sol_balance=1.5)
        assert ws.wallet == "abc"
        assert ws.sol_balance == 1.5
        assert ws.is_active is True
        assert ws.error is None
        assert ws.tokens == []

    def test_to_dict(self):
        ws = WalletStatus(
            wallet="abc",
            network="mainnet",
            sol_balance=0.5,
            tokens=[TokenBalance(mint="m1", symbol="USDC", balance=100.0)],
        )
        d = ws.to_dict()
        assert d["wallet"] == "abc"
        assert d["tokens"][0]["symbol"] == "USDC"

    def test_to_json(self):
        ws = WalletStatus(wallet="abc", network="mainnet", sol_balance=0.5)
        j = ws.to_json()
        parsed = json.loads(j)
        assert parsed["sol_balance"] == 0.5

    def test_summary(self):
        ws = WalletStatus(
            wallet="abc",
            network="mainnet",
            sol_balance=1.0,
            tokens=[TokenBalance(mint="m1", symbol="USDC", balance=50.0)],
        )
        s = ws.summary()
        assert "SOL: 1.0" in s
        assert "USDC: 50.0" in s

    def test_summary_with_error(self):
        ws = WalletStatus(wallet="abc", network="mainnet", sol_balance=-1, error="fail")
        assert "Error: fail" in ws.summary()


class TestReadWalletBalance:
    @patch("tools.agent_wallet._run_cmd")
    def test_success(self, mock_cmd):
        mock_cmd.return_value = ("0.1197617 SOL", 0)
        bal = read_wallet_balance("abc", "mainnet")
        assert abs(bal - 0.1197617) < 0.0001

    @patch("tools.agent_wallet._run_cmd")
    def test_failure(self, mock_cmd):
        mock_cmd.return_value = ("error", 1)
        bal = read_wallet_balance("abc", "mainnet")
        assert bal == -1.0

    @patch("tools.agent_wallet._run_cmd")
    def test_bad_output(self, mock_cmd):
        mock_cmd.return_value = ("garbage", 0)
        bal = read_wallet_balance("abc", "mainnet")
        assert bal == -1.0


class TestReadSplTokenBalances:
    @patch("tools.agent_wallet._run_cmd")
    def test_success(self, mock_cmd):
        mock_cmd.return_value = (
            "Token                                         Balance\n"
            "-----------------------------------------------------\n"
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v  100.5",
            0,
        )
        tokens = read_spl_token_balances("abc", "mainnet")
        assert len(tokens) == 1
        assert tokens[0].symbol == "USDC"
        assert tokens[0].balance == 100.5

    @patch("tools.agent_wallet._run_cmd")
    def test_empty(self, mock_cmd):
        mock_cmd.return_value = (
            "Token                                         Balance\n"
            "-----------------------------------------------------",
            0,
        )
        tokens = read_spl_token_balances("abc", "mainnet")
        assert tokens == []

    @patch("tools.agent_wallet._run_cmd")
    def test_failure(self, mock_cmd):
        mock_cmd.return_value = ("error", 1)
        tokens = read_spl_token_balances("abc", "mainnet")
        assert tokens == []


class TestAgentWalletStatus:
    @patch("tools.agent_wallet.read_spl_token_balances")
    @patch("tools.agent_wallet.read_wallet_balance")
    def test_default_wallet(self, mock_bal, mock_spl):
        mock_bal.return_value = 0.12
        mock_spl.return_value = []
        status = agent_wallet_status()
        assert status.wallet == DEFAULT_WALLET
        assert status.sol_balance == 0.12
        assert status.is_active is True

    @patch("tools.agent_wallet.read_spl_token_balances")
    @patch("tools.agent_wallet.read_wallet_balance")
    def test_custom_wallet(self, mock_bal, mock_spl):
        mock_bal.return_value = 5.0
        mock_spl.return_value = [TokenBalance("m1", "USDC", 200.0)]
        status = agent_wallet_status(wallet="custom123", network="devnet")
        assert status.wallet == "custom123"
        assert status.network == "devnet"
        assert len(status.tokens) == 1

    def test_invalid_network(self):
        status = agent_wallet_status(network="invalid")
        assert status.is_active is False
        assert "Unknown network" in status.error

    @patch("tools.agent_wallet.read_spl_token_balances")
    @patch("tools.agent_wallet.read_wallet_balance")
    def test_balance_failure(self, mock_bal, mock_spl):
        mock_bal.return_value = -1.0
        mock_spl.return_value = []
        status = agent_wallet_status()
        assert status.is_active is False
        assert status.error is not None


class TestCryptoIdentity:
    def test_identity(self):
        identity = read_crypto_identity()
        assert identity["wallet"] == DEFAULT_WALLET
        assert "mainnet" in identity["networks"]
        assert "SOL" in identity["supported_tokens"]
        assert "USDC" in identity["supported_tokens"]


class TestLiveIntegration:
    """Live integration tests - require solana CLI and network access."""

    def test_mainnet_balance(self):
        """Verify real mainnet balance for the agent wallet."""
        status = agent_wallet_status(network="mainnet")
        assert status.is_active is True
        assert status.sol_balance > 0
        print(f"Mainnet: {status.summary()}")

    def test_devnet_balance(self):
        """Verify real devnet balance for the agent wallet."""
        status = agent_wallet_status(network="devnet")
        assert status.is_active is True
        assert status.sol_balance > 0
        print(f"Devnet: {status.summary()}")
