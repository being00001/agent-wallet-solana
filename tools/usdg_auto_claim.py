"""
USDG Auto-Claim Tool for Solana Agents
=======================================

Detects claimable USDG (Global Dollar by Paxos, stablecoin used in Superteam Earn
grant payouts) in a Solana wallet and auto-sweeps to a treasury when above threshold.

USDG Solana mint: 2u1tszSeqZ3qBWF3uNGPFc8TzMk2tdiwknnRMWGWjGWH

Superteam Earn uses a custodial wallet model — users withdraw via standard SPL
token transfers. This tool monitors the agent's wallet for USDG deposits and
auto-sweeps to treasury.

Architecture:
  1. Monitor wallet for incoming SPL token deposits (USDG)
  2. When balance exceeds configurable threshold, trigger auto-sweep
  3. Sweep sends tokens from agent operational wallet to treasury PDA
  4. Supports devnet (fake mint) and mainnet (real USDG mint)

Usage:
  python tools/usdg_auto_claim.py --check --wallet <PUBKEY>
  python tools/usdg_auto_claim.py --sweep --wallet <PUBKEY> --treasury <PUBKEY> --keypair <PATH>
  python tools/usdg_auto_claim.py --monitor --wallet <PUBKEY> --treasury <PUBKEY> --keypair <PATH>

Dependencies:
  pip install solana solders
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import dataclass
from typing import Optional

from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from solders.keypair import Keypair  # type: ignore[import-untyped]
from solders.pubkey import Pubkey  # type: ignore[import-untyped]
from solders.system_program import TransferParams, transfer
from solders.transaction import Transaction  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Token Mint Constants
# ---------------------------------------------------------------------------
# USDG (Global Dollar by Paxos) - Solana mint address
# https://docs.paxos.com/guides/stablecoin/usdg/mainnet
USDG_MINT_MAINNET = Pubkey.from_string(
    "2u1tszSeqZ3qBWF3uNGPFc8TzMk2tdiwknnRMWGWjGWH"
)

# USDC mint (fallback for Superteam Earn bounties paid in USDC)
USDC_MINT_MAINNET = Pubkey.from_string(
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
)

# SPL Token Program
TOKEN_PROGRAM_ID = Pubkey.from_string(
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
)

# Associated Token Account Program
ATA_PROGRAM_ID = Pubkey.from_string(
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
)

# Devnet: we create a fake "USDG" mint for testing
DEVNET_USDG_MINT: Optional[Pubkey] = None  # Set at runtime during devnet setup

# RPC endpoints
RPC_ENDPOINTS = {
    "devnet": "https://api.devnet.solana.com",
    "mainnet": "https://api.mainnet-beta.solana.com",
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
@dataclass
class ClaimConfig:
    """Configuration for the auto-claim tool."""

    network: str = "devnet"
    rpc_url: Optional[str] = None
    threshold_lamports: int = 1_000_000  # 1 USDC (6 decimals) = 1_000_000
    sweep_percentage: int = 100  # Percentage of balance to sweep (0-100)
    poll_interval_seconds: int = 30
    max_retries: int = 3
    token_mint: Optional[str] = None  # Override token mint address

    @property
    def rpc(self) -> str:
        if self.rpc_url:
            return self.rpc_url
        return RPC_ENDPOINTS.get(self.network, RPC_ENDPOINTS["devnet"])

    @property
    def mint_pubkey(self) -> Pubkey:
        if self.token_mint:
            return Pubkey.from_string(self.token_mint)
        if self.network == "mainnet":
            return USDG_MINT_MAINNET
        # Devnet: use configured devnet mint or mainnet USDG address as placeholder
        return DEVNET_USDG_MINT or USDG_MINT_MAINNET


# ---------------------------------------------------------------------------
# Token Account Utilities
# ---------------------------------------------------------------------------
def get_associated_token_address(owner: Pubkey, mint: Pubkey) -> Pubkey:
    """Derive the associated token account (ATA) address for an owner+mint."""
    seeds = [bytes(owner), bytes(TOKEN_PROGRAM_ID), bytes(mint)]
    ata, _ = Pubkey.find_program_address(seeds, ATA_PROGRAM_ID)
    return ata


async def get_token_balance(
    client: AsyncClient, owner: Pubkey, mint: Pubkey
) -> int:
    """
    Get the SPL token balance (in smallest units) for a wallet.
    Returns 0 if no token account exists.
    """
    ata = get_associated_token_address(owner, mint)
    try:
        resp = await client.get_token_account_balance(ata, commitment=Confirmed)
        if resp.value is not None:
            return int(resp.value.amount)
    except Exception as e:
        logger.debug("No token account found for %s: %s", ata, e)
    return 0


async def get_sol_balance(client: AsyncClient, pubkey: Pubkey) -> int:
    """Get SOL balance in lamports."""
    resp = await client.get_balance(pubkey, commitment=Confirmed)
    return resp.value


# ---------------------------------------------------------------------------
# Claim Detection
# ---------------------------------------------------------------------------
@dataclass
class ClaimableBalance:
    """Represents a detected claimable balance."""

    wallet: str
    token_mint: str
    balance_raw: int
    balance_human: float
    exceeds_threshold: bool
    threshold_raw: int
    token_symbol: str = "USDG"


async def check_claimable(
    wallet: Pubkey, config: ClaimConfig
) -> ClaimableBalance:
    """
    Check if wallet has claimable USDG/USDC above threshold.
    """
    async with AsyncClient(config.rpc) as client:
        balance = await get_token_balance(client, wallet, config.mint_pubkey)
        balance_human = balance / 1_000_000  # 6 decimal places for USDC/USDG

        return ClaimableBalance(
            wallet=str(wallet),
            token_mint=str(config.mint_pubkey),
            balance_raw=balance,
            balance_human=balance_human,
            exceeds_threshold=balance >= config.threshold_lamports,
            threshold_raw=config.threshold_lamports,
        )


# ---------------------------------------------------------------------------
# Auto-Sweep (Claim) Execution
# ---------------------------------------------------------------------------
@dataclass
class SweepResult:
    """Result of a sweep transaction."""

    success: bool
    signature: Optional[str] = None
    amount_swept: int = 0
    error: Optional[str] = None


async def execute_sweep(
    wallet_keypair: Keypair,
    treasury: Pubkey,
    config: ClaimConfig,
) -> SweepResult:
    """
    Sweep USDG/USDC tokens from agent wallet to treasury.

    For SPL tokens, this creates a token transfer instruction.
    Falls back to SOL transfer for testing on devnet without token setup.
    """
    async with AsyncClient(config.rpc) as client:
        owner = wallet_keypair.pubkey()

        # Check token balance first
        token_balance = await get_token_balance(
            client, owner, config.mint_pubkey
        )

        if token_balance > 0 and token_balance >= config.threshold_lamports:
            # Calculate sweep amount
            sweep_amount = (token_balance * config.sweep_percentage) // 100
            logger.info(
                "Sweeping %d token units (%.6f) to treasury %s",
                sweep_amount,
                sweep_amount / 1_000_000,
                treasury,
            )

            # Build SPL token transfer instruction
            try:
                from spl.token.instructions import (
                    TransferCheckedParams,
                    transfer_checked,
                )

                source_ata = get_associated_token_address(
                    owner, config.mint_pubkey
                )
                dest_ata = get_associated_token_address(
                    treasury, config.mint_pubkey
                )

                ix = transfer_checked(
                    TransferCheckedParams(
                        program_id=TOKEN_PROGRAM_ID,
                        source=source_ata,
                        mint=config.mint_pubkey,
                        dest=dest_ata,
                        owner=owner,
                        amount=sweep_amount,
                        decimals=6,
                    )
                )

                blockhash_resp = await client.get_latest_blockhash(
                    commitment=Confirmed
                )
                blockhash = blockhash_resp.value.blockhash

                tx = Transaction.new_signed_with_payer(
                    [ix], owner, [wallet_keypair], blockhash
                )

                resp = await client.send_transaction(tx)

                sig = str(resp.value)
                logger.info("SPL sweep tx: %s", sig)
                return SweepResult(
                    success=True, signature=sig, amount_swept=sweep_amount
                )

            except ImportError:
                logger.warning(
                    "spl-token not installed; falling back to SOL transfer test"
                )
            except Exception as e:
                logger.error("SPL transfer failed: %s", e)
                return SweepResult(success=False, error=str(e))

        # Fallback: SOL transfer (useful for devnet testing without SPL setup)
        sol_balance = await get_sol_balance(client, owner)
        # Reserve 0.01 SOL for rent/fees
        reserve = 10_000_000
        transferable = sol_balance - reserve

        if transferable <= 0:
            return SweepResult(
                success=False,
                error=f"Insufficient SOL balance: {sol_balance} lamports",
            )

        sweep_sol = (transferable * config.sweep_percentage) // 100
        if sweep_sol <= 0:
            return SweepResult(
                success=False, error="Nothing to sweep after percentage calc"
            )

        logger.info(
            "SOL fallback sweep: %d lamports (%.9f SOL) to %s",
            sweep_sol,
            sweep_sol / 1e9,
            treasury,
        )

        ix = transfer(
            TransferParams(
                from_pubkey=owner,
                to_pubkey=treasury,
                lamports=sweep_sol,
            )
        )

        blockhash_resp = await client.get_latest_blockhash(commitment=Confirmed)
        blockhash = blockhash_resp.value.blockhash

        tx = Transaction.new_signed_with_payer(
            [ix], owner, [wallet_keypair], blockhash
        )

        resp = await client.send_transaction(tx)
        sig = str(resp.value)
        logger.info("SOL sweep tx: %s", sig)

        return SweepResult(success=True, signature=sig, amount_swept=sweep_sol)


# ---------------------------------------------------------------------------
# Monitoring Loop
# ---------------------------------------------------------------------------
async def monitor_and_sweep(
    wallet_keypair: Keypair,
    treasury: Pubkey,
    config: ClaimConfig,
) -> None:
    """
    Continuously monitor wallet for claimable USDG and auto-sweep.
    """
    owner = wallet_keypair.pubkey()
    logger.info(
        "Starting monitor: wallet=%s treasury=%s network=%s interval=%ds threshold=%d",
        owner,
        treasury,
        config.network,
        config.poll_interval_seconds,
        config.threshold_lamports,
    )

    while True:
        try:
            claim = await check_claimable(owner, config)
            logger.info(
                "Balance check: %.6f %s (threshold: %.6f, exceeds: %s)",
                claim.balance_human,
                claim.token_symbol,
                claim.threshold_raw / 1_000_000,
                claim.exceeds_threshold,
            )

            if claim.exceeds_threshold:
                logger.info("Threshold exceeded — initiating sweep")
                result = await execute_sweep(wallet_keypair, treasury, config)
                if result.success:
                    logger.info(
                        "Sweep successful: sig=%s amount=%d",
                        result.signature,
                        result.amount_swept,
                    )
                else:
                    logger.error("Sweep failed: %s", result.error)
            else:
                logger.debug("Below threshold, waiting...")

        except Exception as e:
            logger.error("Monitor error: %s", e)

        await asyncio.sleep(config.poll_interval_seconds)


# ---------------------------------------------------------------------------
# Keypair Loading
# ---------------------------------------------------------------------------
def load_keypair(path: str) -> Keypair:
    """Load a Solana keypair from a JSON file (standard Solana CLI format)."""
    with open(path) as f:
        secret = json.load(f)
    return Keypair.from_bytes(bytes(secret[:64]))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="USDG Auto-Claim Tool for Solana Agents"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check claimable balance and exit",
    )
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="Execute a single sweep and exit",
    )
    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Continuously monitor and auto-sweep",
    )
    parser.add_argument("--wallet", required=True, help="Wallet public key")
    parser.add_argument("--treasury", help="Treasury public key (for sweep/monitor)")
    parser.add_argument("--keypair", help="Path to keypair JSON (for sweep/monitor)")
    parser.add_argument(
        "--network",
        default="devnet",
        choices=["devnet", "mainnet"],
        help="Solana network (default: devnet)",
    )
    parser.add_argument("--rpc-url", help="Custom RPC endpoint")
    parser.add_argument(
        "--threshold",
        type=float,
        default=1.0,
        help="Minimum USDG/USDC to trigger sweep (default: 1.0)",
    )
    parser.add_argument(
        "--sweep-pct",
        type=int,
        default=100,
        help="Percentage of balance to sweep (default: 100)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Poll interval in seconds for monitor mode (default: 30)",
    )
    parser.add_argument(
        "--token-mint",
        help="Override token mint address",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable debug logging"
    )
    return parser


async def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = ClaimConfig(
        network=args.network,
        rpc_url=args.rpc_url,
        threshold_lamports=int(args.threshold * 1_000_000),
        sweep_percentage=args.sweep_pct,
        poll_interval_seconds=args.interval,
        token_mint=args.token_mint,
    )

    wallet = Pubkey.from_string(args.wallet)

    if args.check:
        claim = await check_claimable(wallet, config)
        print(json.dumps({
            "wallet": claim.wallet,
            "token_mint": claim.token_mint,
            "balance": claim.balance_human,
            "balance_raw": claim.balance_raw,
            "exceeds_threshold": claim.exceeds_threshold,
            "threshold": claim.threshold_raw / 1_000_000,
            "token_symbol": claim.token_symbol,
        }, indent=2))
        return 0

    # Sweep and monitor require keypair + treasury
    if not args.treasury:
        parser.error("--treasury is required for --sweep and --monitor")
    if not args.keypair:
        parser.error("--keypair is required for --sweep and --monitor")

    treasury = Pubkey.from_string(args.treasury)
    keypair = load_keypair(args.keypair)

    if args.sweep:
        result = await execute_sweep(keypair, treasury, config)
        print(json.dumps({
            "success": result.success,
            "signature": result.signature,
            "amount_swept": result.amount_swept,
            "error": result.error,
        }, indent=2))
        return 0 if result.success else 1

    if args.monitor:
        await monitor_and_sweep(keypair, treasury, config)
        return 0  # unreachable in practice

    parser.error("Specify one of --check, --sweep, or --monitor")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
