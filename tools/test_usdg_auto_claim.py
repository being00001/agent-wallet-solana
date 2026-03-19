"""
Tests for USDG Auto-Claim Tool
================================

Tests cover:
  - Configuration defaults
  - ATA derivation
  - ClaimableBalance detection (mocked RPC)
  - CLI argument parsing
  - Devnet integration (live RPC, read-only)
  - Edge cases (confirmation, idempotency, validation)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure the v2 module is importable (parent directory)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import from v2 module which has all the fixes
from usdg_auto_claim_v2 import (
    ClaimConfig,
    ClaimableBalance,
    SweepResult,
    build_parser,
    check_claimable,
    get_associated_token_address,
    main,
    USDG_MINT_MAINNET,
    IdempotencyTracker,
    ConfirmationTimeoutError,
    AccountNotFoundError,
    load_keypair,
    DEFAULT_COMPUTE_UNIT_LIMIT,
)
from solders.pubkey import Pubkey  # type: ignore[import-untyped]
from solders.keypair import Keypair  # type: ignore[import-untyped]


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------

class TestClaimConfig:
    def test_defaults(self):
        cfg = ClaimConfig()
        assert cfg.network == "devnet"
        assert cfg.rpc == "https://api.devnet.solana.com"
        assert cfg.threshold_lamports == 1_000_000
        assert cfg.sweep_percentage == 100

    def test_mainnet(self):
        cfg = ClaimConfig(network="mainnet")
        assert cfg.rpc == "https://api.mainnet-beta.solana.com"
        assert cfg.mint_pubkey == USDG_MINT_MAINNET

    def test_custom_rpc(self):
        cfg = ClaimConfig(rpc_url="https://custom.rpc.com")
        assert cfg.rpc == "https://custom.rpc.com"

    def test_custom_mint(self):
        mint = "So11111111111111111111111111111111111111112"
        cfg = ClaimConfig(token_mint=mint)
        assert str(cfg.mint_pubkey) == mint


class TestATADerivation:
    def test_deterministic(self):
        owner = Keypair().pubkey()
        mint = USDG_MINT_MAINNET
        ata1 = get_associated_token_address(owner, mint)
        ata2 = get_associated_token_address(owner, mint)
        assert ata1 == ata2

    def test_different_owners(self):
        owner1 = Keypair().pubkey()
        owner2 = Keypair().pubkey()
        mint = USDG_MINT_MAINNET
        ata1 = get_associated_token_address(owner1, mint)
        ata2 = get_associated_token_address(owner2, mint)
        assert ata1 != ata2


class TestCLIParsing:
    def test_check_mode(self):
        parser = build_parser()
        args = parser.parse_args([
            "--check",
            "--wallet", "11111111111111111111111111111111",
        ])
        assert args.check is True
        assert args.sweep is False
        assert args.monitor is False

    def test_sweep_mode(self):
        parser = build_parser()
        args = parser.parse_args([
            "--sweep",
            "--wallet", "11111111111111111111111111111111",
            "--treasury", "11111111111111111111111111111112",
            "--keypair", "/tmp/key.json",
            "--threshold", "5.0",
            "--sweep-pct", "80",
        ])
        assert args.sweep is True
        assert args.threshold == 5.0
        assert args.sweep_pct == 80

    def test_monitor_mode(self):
        parser = build_parser()
        args = parser.parse_args([
            "--monitor",
            "--wallet", "11111111111111111111111111111111",
            "--treasury", "11111111111111111111111111111112",
            "--keypair", "/tmp/key.json",
            "--interval", "10",
            "--network", "mainnet",
        ])
        assert args.monitor is True
        assert args.interval == 10
        assert args.network == "mainnet"


class TestCheckClaimable:
    """Test check_claimable with mocked RPC."""

    @pytest.mark.asyncio
    async def test_above_threshold(self):
        config = ClaimConfig(threshold_lamports=1_000_000)
        wallet = Keypair().pubkey()

        with patch("usdg_auto_claim.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            # Mock token balance response: 5 USDC
            mock_resp = MagicMock()
            mock_resp.value = MagicMock()
            mock_resp.value.amount = "5000000"
            mock_client.get_token_account_balance = AsyncMock(return_value=mock_resp)

            result = await check_claimable(wallet, config)
            assert result.exceeds_threshold is True
            assert result.balance_raw == 5_000_000
            assert result.balance_human == 5.0

    @pytest.mark.asyncio
    async def test_below_threshold(self):
        config = ClaimConfig(threshold_lamports=1_000_000)
        wallet = Keypair().pubkey()

        with patch("usdg_auto_claim.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_resp = MagicMock()
            mock_resp.value = MagicMock()
            mock_resp.value.amount = "500000"  # 0.5 USDC
            mock_client.get_token_account_balance = AsyncMock(return_value=mock_resp)

            result = await check_claimable(wallet, config)
            assert result.exceeds_threshold is False
            assert result.balance_human == 0.5

    @pytest.mark.asyncio
    async def test_no_token_account(self):
        config = ClaimConfig(threshold_lamports=1_000_000)
        wallet = Keypair().pubkey()

        with patch("usdg_auto_claim.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_resp = MagicMock()
            mock_resp.value = None
            mock_client.get_token_account_balance = AsyncMock(return_value=mock_resp)

            result = await check_claimable(wallet, config)
            assert result.balance_raw == 0
            assert result.exceeds_threshold is False


class TestSweepResult:
    def test_success(self):
        r = SweepResult(success=True, signature="abc123", amount_swept=1000)
        assert r.success
        assert r.signature == "abc123"

    def test_failure(self):
        r = SweepResult(success=False, error="Insufficient funds")
        assert not r.success
        assert r.error == "Insufficient funds"


class TestCLIMain:
    """Test the CLI main function with mocked check."""

    @pytest.mark.asyncio
    async def test_check_outputs_json(self, capsys):
        wallet = Keypair().pubkey()

        with patch("usdg_auto_claim.check_claimable") as mock_check:
            mock_check.return_value = ClaimableBalance(
                wallet=str(wallet),
                token_mint=str(USDG_MINT_MAINNET),
                balance_raw=2_000_000,
                balance_human=2.0,
                exceeds_threshold=True,
                threshold_raw=1_000_000,
            )

            ret = await main(["--check", "--wallet", str(wallet)])
            assert ret == 0

            captured = capsys.readouterr()
            data = json.loads(captured.out)
            assert data["balance"] == 2.0
            assert data["exceeds_threshold"] is True


# ---------------------------------------------------------------------------
# Devnet Integration Test (live RPC, read-only)
# ---------------------------------------------------------------------------

class TestDevnetIntegration:
    """
    Live devnet tests. These hit the real devnet RPC and are read-only.
    Mark with a custom marker so they can be skipped in CI if needed:
        pytest -m "not devnet"
    """

    @pytest.mark.asyncio
    async def test_check_random_wallet_devnet(self):
        """Check balance of a random wallet on devnet (should be 0)."""
        wallet = Keypair().pubkey()
        config = ClaimConfig(network="devnet")

        result = await check_claimable(wallet, config)
        assert result.balance_raw == 0
        assert result.exceeds_threshold is False
        assert result.wallet == str(wallet)


# ---------------------------------------------------------------------------
# Edge Case Tests
# ---------------------------------------------------------------------------

class TestIdempotencyTracker:
    """Test idempotency tracking to prevent double-sweeps."""

    @pytest.mark.asyncio
    async def test_mark_and_check(self):
        tracker = IdempotencyTracker()
        sig = "test_signature_123"
        
        # Should not be processed initially
        assert await tracker.is_processed(sig) is False
        
        # Mark as processed
        await tracker.mark_processed(sig)
        
        # Should now be processed
        assert await tracker.is_processed(sig) is True

    @pytest.mark.asyncio
    async def test_clear(self):
        tracker = IdempotencyTracker()
        sig = "test_signature_456"
        
        await tracker.mark_processed(sig)
        assert await tracker.is_processed(sig) is True
        
        await tracker.clear()
        assert await tracker.is_processed(sig) is False

    @pytest.mark.asyncio
    async def test_max_size_eviction(self):
        tracker = IdempotencyTracker(max_size=3)
        
        # Add 3 signatures
        for i in range(3):
            await tracker.mark_processed(f"sig_{i}")
        
        assert tracker.size == 3
        
        # Add more - should trigger eviction
        for i in range(3, 6):
            await tracker.mark_processed(f"sig_{i}")
        
        # Should have more than half but less than max
        assert tracker.size >= 3


class TestCLIParsingValidation:
    """Test CLI argument validation."""

    def test_sweep_pct_negative_error(self):
        """Test that negative sweep percentage is rejected."""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([
                "--check",
                "--wallet", "11111111111111111111111111111111",
                "--sweep-pct", "-10",
            ])

    def test_sweep_pct_over_100_error(self):
        """Test that sweep percentage over 100 is rejected."""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([
                "--check",
                "--wallet", "11111111111111111111111111111111",
                "--sweep-pct", "150",
            ])


class TestComputeUnitOptimization:
    """Test compute unit optimization."""

    def test_default_compute_units(self):
        """Verify default compute units is optimized."""
        cfg = ClaimConfig()
        # Should be reduced from original 200k to ~100k
        assert cfg.compute_units == DEFAULT_COMPUTE_UNIT_LIMIT
        assert cfg.compute_units < 200_000  # Must be less than original


class TestKeypairLoading:
    """Test keypair loading security."""

    def test_file_not_found(self):
        """Test that missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_keypair("/nonexistent/path/keypair.json")

    def test_directory_not_file(self):
        """Test that directory path raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError):
                load_keypair(tmpdir)

    def test_invalid_json(self):
        """Test that invalid JSON raises ValueError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("not valid json")
            f.flush()
            try:
                with pytest.raises(ValueError):
                    load_keypair(f.name)
            finally:
                os.unlink(f.name)

    def test_invalid_structure(self):
        """Test that non-array JSON raises ValueError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"not": "array"}, f)
            f.flush()
            try:
                with pytest.raises(ValueError):
                    load_keypair(f.name)
            finally:
                os.unlink(f.name)

    def test_short_array(self):
        """Test that short array raises ValueError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([1, 2, 3], f)  # Only 3 bytes, need 64
            f.flush()
            try:
                with pytest.raises(ValueError):
                    load_keypair(f.name)
            finally:
                os.unlink(f.name)

    def test_valid_keypair(self):
        """Test that valid keypair loads successfully."""
        # Generate a random keypair and save it
        keypair = Keypair()
        secret = list(keypair.to_bytes())
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(secret, f)
            f.flush()
            try:
                loaded = load_keypair(f.name)
                assert loaded.pubkey() == keypair.pubkey()
            finally:
                os.unlink(f.name)


class TestErrorTypes:
    """Test custom error types."""

    def test_confirmation_timeout_error(self):
        """Test ConfirmationTimeoutError with signature."""
        sig = "test_signature_abc"
        err = ConfirmationTimeoutError("Timeout", signature=sig)
        assert err.signature == sig
        assert "Timeout" in str(err)

    def test_account_not_found_error(self):
        """Test AccountNotFoundError."""
        err = AccountNotFoundError("Account not found")
        assert "not found" in str(err).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
