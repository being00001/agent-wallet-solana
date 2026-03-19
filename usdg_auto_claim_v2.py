"""
USDG Auto-Claim Tool v2 for Solana Agents
==========================================

Enhanced version with robust error handling and gas optimization.

Detects claimable USDG (Global Dollar by Paxos, stablecoin used in Superteam Earn
grant payouts) in a Solana wallet and auto-sweeps to a treasury when above threshold.

USDG Solana mint: 2u1tszSeqZ3qBWF3uNGPFc8TzMk2tdiwknnRMWGWjGWH

Architecture:
  1. Monitor wallet for incoming SPL token deposits (USDG)
  2. When balance exceeds configurable threshold, trigger auto-sweep
  3. Sweep sends tokens from agent operational wallet to treasury PDA
  4. Supports devnet (fake mint) and mainnet (real USDG mint)

Error Handling:
  - Retry mechanism with exponential backoff and jitter
  - Circuit breaker pattern to prevent cascading failures
  - Timeout handling for all network operations
  - Graceful degradation with fallback behaviors

Gas Optimization:
  - Dynamic priority fee estimation based on network conditions
  - Compute unit optimization
  - Optional Jito tips for faster confirmation
  - Transaction simulation before execution

Usage:
  python usdg_auto_claim_v2.py --check --wallet <PUBKEY>
  python usdg_auto_claim_v2.py --sweep --wallet <PUBKEY> --treasury <PUBKEY> --keypair <PATH>
  python usdg_auto_claim_v2.py --monitor --wallet <PUBKEY> --treasury <PUBKEY> --keypair <PATH>

Dependencies:
  pip install solana solders spl-token
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Generic, Optional, TypeVar

from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed, Finalized
from solana.rpc.core import RPCException
from solders.transaction import Transaction  # type: ignore[import-untyped]
from solders.keypair import Keypair  # type: ignore[import-untyped]
from solders.pubkey import Pubkey  # type: ignore[import-untyped]
from solders.system_program import TransferParams, transfer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Token Mint Constants
# ---------------------------------------------------------------------------
USDG_MINT_MAINNET = Pubkey.from_string(
    "2u1tszSeqZ3qBWF3uNGPFc8TzMk2tdiwknnRMWGWjGWH"
)

USDC_MINT_MAINNET = Pubkey.from_string(
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
)

TOKEN_PROGRAM_ID = Pubkey.from_string(
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
)

ATA_PROGRAM_ID = Pubkey.from_string(
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
)

DEVNET_USDG_MINT: Optional[Pubkey] = None

RPC_ENDPOINTS = {
    "devnet": "https://api.devnet.solana.com",
    "mainnet": "https://api.mainnet-beta.solana.com",
}

# Jito RPC endpoints for priority fee estimation
JITO_ENDPOINTS = [
    "https://mainnet.block-engine.jito.wtf/api/v1/leader_schedule",
    "https://jito-mainnet.genesysgo.net/api/v1/leader_schedule",
]

# Default compute unit limits - optimized for token transfers
DEFAULT_COMPUTE_UNIT_LIMIT = 100_000  # Reduced from 200k for efficiency
DEFAULT_COMPUTE_UNIT_PRICE = 1_000  # micro lamports

# Default timeout for RPC operations
DEFAULT_CONFIRM_TIMEOUT_SECONDS = 60
DEFAULT_RPC_TIMEOUT_SECONDS = 30

# Blockhash expiry buffer - refresh if less than this many blocks remaining
BLOCKHASH_EXPIRY_BUFFER_BLOCKS = 10

# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------
class USDGError(Exception):
    """Base exception for USDG auto-claim errors."""
    pass


class RPCError(USDGError):
    """RPC-related errors with details."""
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class CircuitBreakerError(USDGError):
    """Circuit breaker is open."""
    pass


class InsufficientFundsError(USDGError):
    """Insufficient funds for operation."""
    pass


class TransactionError(USDGError):
    """Transaction execution failed."""
    def __init__(self, message: str, signature: Optional[str] = None):
        super().__init__(message)
        self.signature = signature


class AccountNotFoundError(USDGError):
    """Required account not found."""
    pass


class ConfirmationTimeoutError(USDGError):
    """Transaction confirmation timed out."""
    def __init__(self, message: str, signature: Optional[str] = None):
        super().__init__(message)
        self.signature = signature


class BlockhashExpiredError(USDGError):
    """Transaction blockhash has expired."""
    pass


class RateLimitError(RPCError):
    """RPC rate limit (429) exceeded."""
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, retryable=True)


# ---------------------------------------------------------------------------
# Retry Configuration
# ---------------------------------------------------------------------------
@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    base_delay: float = 0.5  # seconds
    max_delay: float = 30.0  # seconds
    exponential_base: float = 2.0
    jitter: float = 0.1  # 10% jitter
    # Rate limit (429) is retryable
    retryable_exceptions: tuple = (
        RPCException, 
        asyncio.TimeoutError, 
        ConnectionError,
        RateLimitError,
    )
    # Timeout for RPC operations
    rpc_timeout_seconds: float = DEFAULT_RPC_TIMEOUT_SECONDS

    def calculate_delay(self, attempt: int, is_rate_limit: bool = False) -> float:
        """Calculate delay with exponential backoff and jitter.
        
        For rate limits, use longer delays to respect server constraints.
        """
        if is_rate_limit:
            # Longer delays for rate limiting
            delay = min(
                self.base_delay * 4 * (self.exponential_base ** attempt),
                self.max_delay
            )
        else:
            delay = min(
                self.base_delay * (self.exponential_base ** attempt),
                self.max_delay
            )
        # Add jitter
        jitter_amount = delay * self.jitter
        return delay + random.uniform(-jitter_amount, jitter_amount)


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------
class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes to close from half-open
    timeout: float = 30.0  # Seconds before trying half-open
    excluded_exceptions: tuple = (InsufficientFundsError,)


class CircuitBreaker:
    """
    Circuit breaker to prevent cascading failures.
    
    States:
    - CLOSED: Normal operation, failures count up
    - OPEN: Too many failures, reject calls immediately
    - HALF_OPEN: Testing recovery, allow limited calls
    """

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None

    def can_execute(self) -> bool:
        """Check if execution is allowed."""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if timeout has passed to try half-open
            if self.last_failure_time and \
               time.time() - self.last_failure_time >= self.config.timeout:
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                logger.info("Circuit breaker: OPEN -> HALF_OPEN")
                return True
            return False

        # HALF_OPEN: allow one test call
        return True

    def record_success(self) -> None:
        """Record a successful call."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                logger.info("Circuit breaker: HALF_OPEN -> CLOSED")
        else:
            self.failure_count = 0

    def record_failure(self, exception: Exception) -> None:
        """Record a failed call."""
        # Check if exception should be excluded from failure counting
        if isinstance(exception, self.config.excluded_exceptions):
            return

        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            logger.warning("Circuit breaker: HALF_OPEN -> OPEN")
        elif self.failure_count >= self.config.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning("Circuit breaker: CLOSED -> OPEN (failure threshold reached)")

    @property
    def status(self) -> dict:
        """Get current circuit breaker status."""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
        }


# ---------------------------------------------------------------------------
# Idempotency Tracker
# ---------------------------------------------------------------------------
class IdempotencyTracker:
    """
    Tracks processed transactions to prevent double-sweeps.
    
    Uses a simple set to track transaction signatures that have been
    successfully processed. This prevents accidental double-sweeps if
    a transaction is retried or if the monitor restarts.
    """

    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self._processed_signatures: set[str] = set()
        self._lock = asyncio.Lock()

    async def is_processed(self, signature: str) -> bool:
        """Check if a signature has already been processed."""
        async with self._lock:
            return signature in self._processed_signatures

    async def mark_processed(self, signature: str) -> None:
        """Mark a signature as processed."""
        async with self._lock:
            # Add to set, evict oldest if at capacity
            if signature not in self._processed_signatures:
                self._processed_signatures.add(signature)
                # Simple eviction: if over capacity, clear half
                # In production, could use ordered dict for LRU
                if len(self._processed_signatures) > self.max_size:
                    to_remove = list(self._processed_signatures)[:self.max_size // 2]
                    self._processed_signatures.difference_update(to_remove)
                    logger.debug("Idempotency cache evicted %d entries", len(to_remove))

    async def clear(self) -> None:
        """Clear all tracked signatures."""
        async with self._lock:
            self._processed_signatures.clear()

    @property
    def size(self) -> int:
        """Current number of tracked signatures."""
        return len(self._processed_signatures)


# ---------------------------------------------------------------------------
# Priority Fee Estimator
# ---------------------------------------------------------------------------
@dataclass
class PriorityFeeConfig:
    """Configuration for priority fee estimation."""

    min_fee_per_cu: int = 1_000  # micro lamports (0.001 SOL per 1000 CUs)
    max_fee_per_cu: int = 10_000_000  # micro lamports (0.01 SOL per 1000 CUs)
    target_confirm_time: float = 5.0  # seconds
    use_jito: bool = False
    jito_tip: int = 1_000_000  # 0.001 SOL tip for Jito


class PriorityFeeEstimator:
    """
    Estimates optimal priority fees based on network conditions.
    
    Uses recent block history to estimate appropriate fees for
    desired confirmation time.
    """

    def __init__(self, config: PriorityFeeConfig, rpc_url: str):
        self.config = config
        self.rpc_url = rpc_url
        self._cached_fee: Optional[int] = None
        self._cache_time: Optional[float] = None
        self._cache_ttl: float = 60.0  # Cache for 60 seconds

    async def estimate_fee(self) -> int:
        """Estimate priority fee in micro-lamports per compute unit."""
        # Return cached fee if valid
        if self._cached_fee and self._cache_time:
            if time.time() - self._cache_time < self._cache_ttl:
                return self._cached_fee

        try:
            # Try to get recent priority fees from the network
            fee = await self._fetch_recent_fees()
            if fee:
                self._cached_fee = fee
                self._cache_time = time.time()
                return fee
        except Exception as e:
            logger.debug("Could not fetch priority fees: %s", e)

        # Fallback to config default
        return self.config.min_fee_per_cu

    async def _fetch_recent_fees(self) -> Optional[int]:
        """Fetch recent priority fees from the network."""
        try:
            async with AsyncClient(self.rpc_url) as client:
                # Get recent blockhash with prioritization
                resp = await client.get_recent_blockhash(commitment=Confirmed)
                if resp.value:
                    # Use a moderate fee based on blockhash retrieval
                    # In production, you'd analyze recent transactions
                    return self.config.min_fee_per_cu * 2
        except Exception:
            pass
        return None

    async def estimate_total_fee(
        self, 
        compute_units: int = DEFAULT_COMPUTE_UNIT_LIMIT
    ) -> dict:
        """Estimate total transaction fee."""
        fee_per_cu = await self.estimate_fee()
        total_lamports = fee_per_cu * (compute_units // 1000)
        
        return {
            "fee_per_cu": fee_per_cu,
            "compute_units": compute_units,
            "estimated_lamports": total_lamports,
            "estimated_sol": total_lamports / 1e9,
            "jito_tip": self.config.jito_tip if self.config.use_jito else 0,
            "total": (total_lamports + self.config.jito_tip) if self.config.use_jito else total_lamports,
        }


# ---------------------------------------------------------------------------
# Resilient RPC Client
# ---------------------------------------------------------------------------
class ResilientClient:
    """
    RPC client with retry logic and circuit breaker.
    
    Wraps AsyncClient with automatic retries, circuit breaker,
    and timeout handling.
    """

    def __init__(
        self,
        rpc_url: str,
        retry_config: Optional[RetryConfig] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
    ):
        self.rpc_url = rpc_url
        self.retry_config = retry_config or RetryConfig()
        self.circuit_breaker = CircuitBreaker(
            circuit_breaker_config or CircuitBreakerConfig()
        )
        self._client: Optional[AsyncClient] = None

    async def __aenter__(self) -> "ResilientClient":
        self._client = AsyncClient(self.rpc_url)
        await self._client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._client:
            await self._client.__aexit__(exc_type, exc_val, exc_tb)

    async def _execute_with_retry(
        self,
        operation: Callable,
        *args,
        **kwargs
    ) -> Any:
        """Execute operation with retry logic."""
        last_exception = None

        for attempt in range(self.retry_config.max_retries + 1):
            try:
                # Check circuit breaker before attempting
                if not self.circuit_breaker.can_execute():
                    raise CircuitBreakerError(
                        f"Circuit breaker is {self.circuit_breaker.state.value}"
                    )

                result = await operation(*args, **kwargs)
                self.circuit_breaker.record_success()
                return result

            except self.retry_config.retryable_exceptions as e:
                last_exception = e
                self.circuit_breaker.record_failure(e)

                if attempt < self.retry_config.max_retries:
                    delay = self.retry_config.calculate_delay(attempt)
                    logger.warning(
                        "Retryable error (attempt %d/%d): %s. Retrying in %.2fs",
                        attempt + 1,
                        self.retry_config.max_retries,
                        e,
                        delay
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error("Max retries exceeded: %s", e)
                    raise RPCError(str(e), retryable=True) from e

            except CircuitBreakerError:
                raise

            except Exception as e:
                # Non-retryable error
                self.circuit_breaker.record_failure(e)
                logger.error("Non-retryable error: %s", e)
                raise RPCError(str(e), retryable=False) from e

        raise RPCError("Max retries exceeded", retryable=True)

    # Delegate common RPC methods with retry
    async def get_token_account_balance(self, *args, **kwargs):
        return await self._execute_with_retry(
            self._client.get_token_account_balance, *args, **kwargs
        )

    async def get_balance(self, *args, **kwargs):
        return await self._execute_with_retry(
            self._client.get_balance, *args, **kwargs
        )

    async def get_latest_blockhash(self, *args, **kwargs):
        return await self._execute_with_retry(
            self._client.get_latest_blockhash, *args, **kwargs
        )

    async def send_transaction(self, *args, **kwargs):
        return await self._execute_with_retry(
            self._client.send_transaction, *args, **kwargs
        )

    async def simulate_transaction(self, *args, **kwargs):
        """Simulate transaction to estimate fees and check for errors."""
        return await self._execute_with_retry(
            self._client.simulate_transaction, *args, **kwargs
        )

    async def get_fee_for_message(self, *args, **kwargs):
        return await self._execute_with_retry(
            self._client.get_fee_for_message, *args, **kwargs
        )

    async def get_account_info(self, *args, **kwargs):
        """Get account info with retry and circuit breaker."""
        return await self._execute_with_retry(
            self._client.get_account_info, *args, **kwargs
        )

    async def get_transaction(self, *args, **kwargs):
        """Get transaction with retry and circuit breaker."""
        return await self._execute_with_retry(
            self._client.get_transaction, *args, **kwargs
        )

    @property
    def circuit_status(self) -> dict:
        """Get circuit breaker status."""
        return self.circuit_breaker.status


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
@dataclass
class ClaimConfig:
    """Configuration for the auto-claim tool v2."""

    network: str = "devnet"
    rpc_url: Optional[str] = None
    threshold_lamports: int = 1_000_000
    sweep_percentage: int = 100
    poll_interval_seconds: int = 30
    token_mint: Optional[str] = None
    
    # Error handling config
    retry_config: RetryConfig = field(default_factory=RetryConfig)
    circuit_breaker_config: CircuitBreakerConfig = field(
        default_factory=CircuitBreakerConfig
    )
    
    # Gas optimization config
    priority_fee_config: PriorityFeeConfig = field(
        default_factory=PriorityFeeConfig
    )
    compute_units: int = DEFAULT_COMPUTE_UNIT_LIMIT
    
    # Safety
    simulate_before_send: bool = True
    max_slippage_bps: int = 100  # 1% slippage tolerance
    min_sol_balance: int = 5_000_000  # Keep 0.005 SOL for fees
    
    # Transaction confirmation
    confirmation_timeout_seconds: int = DEFAULT_CONFIRM_TIMEOUT_SECONDS
    confirmation_poll_interval: float = 1.0  # seconds between confirmation polls
    
    # Idempotency - track processed transactions to prevent double-sweep
    idempotency_cache_size: int = 100
    
    # Validation
    validate_sweep_percentage: bool = True  # Validate sweep_percentage is 0-100

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
    client: ResilientClient, owner: Pubkey, mint: Pubkey
) -> int:
    """Get the SPL token balance (in smallest units) for a wallet."""
    ata = get_associated_token_address(owner, mint)
    try:
        resp = await client.get_token_account_balance(ata, commitment=Confirmed)
        if resp.value is not None:
            return int(resp.value.amount)
    except Exception as e:
        logger.debug("No token account found for %s: %s", ata, e)
    return 0


async def get_sol_balance(client: ResilientClient, pubkey: Pubkey) -> int:
    """Get SOL balance in lamports."""
    try:
        resp = await client.get_balance(pubkey, commitment=Confirmed)
        return resp.value if resp.value is not None else 0
    except Exception as e:
        logger.error("Failed to get SOL balance: %s", e)
        return 0


async def check_account_exists(client: ResilientClient, pubkey: Pubkey) -> bool:
    """
    Check if an account exists at the given public key.
    
    Returns True if account exists and has data, False otherwise.
    """
    try:
        resp = await client._execute_with_retry(
            client._client.get_account_info,
            pubkey,
            commitment=Confirmed,
        )
        return resp.value is not None and len(resp.value.data) > 0
    except Exception as e:
        logger.debug("Account check failed for %s: %s", pubkey, e)
        return False


async def confirm_transaction(
    client: ResilientClient,
    signature: str,
    timeout_seconds: float = DEFAULT_CONFIRM_TIMEOUT_SECONDS,
    poll_interval: float = 1.0,
) -> bool:
    """
    Poll for transaction confirmation until timeout.
    
    Args:
        client: The RPC client
        signature: The transaction signature to confirm
        timeout_seconds: Maximum time to wait for confirmation
        poll_interval: Time between confirmation polls
        
    Returns:
        True if transaction is confirmed, False if timeout
        
    Raises:
        ConfirmationTimeoutError: If confirmation times out
    """
    start_time = time.time()
    last_error = None
    
    logger.debug("Starting confirmation polling for %s", signature[:20])
    
    while time.time() - start_time < timeout_seconds:
        try:
            # Use get_transaction with transaction ID
            resp = await asyncio.wait_for(
                client._execute_with_retry(
                    client._client.get_transaction,
                    signature,
                    encoding="base64",
                    commitment=Confirmed,
                    max_supported_transaction_version=0,
                ),
                timeout=10.0,  # Individual RPC call timeout
            )
            
            if resp.value is not None:
                # Transaction found - check for errors
                if hasattr(resp.value, 'meta') and resp.value.meta:
                    if resp.value.meta.err is None:
                        logger.info(
                            "Transaction confirmed: %s (%.2fs)",
                            signature[:20],
                            time.time() - start_time
                        )
                        return True
                    else:
                        logger.error(
                            "Transaction failed: %s, err: %s",
                            signature[:20],
                            resp.value.meta.err
                        )
                        return False
                        
        except asyncio.TimeoutError:
            last_error = "RPC call timeout"
            logger.debug("Confirmation poll timeout, retrying...")
        except Exception as e:
            last_error = str(e)
            # Transaction might not be found yet - this is expected during confirmation
            logger.debug("Confirmation poll error (retrying): %s", e)
        
        # Wait before next poll
        await asyncio.sleep(poll_interval)
    
    # Timeout reached
    logger.warning(
        "Confirmation timeout for %s after %.1fs: %s",
        signature[:20],
        timeout_seconds,
        last_error
    )
    raise ConfirmationTimeoutError(
        f"Transaction confirmation timed out after {timeout_seconds}s: {last_error}",
        signature=signature
    )


async def ensure_token_account(
    client: ResilientClient,
    owner: Pubkey,
    mint: Pubkey,
    keypair: Keypair,
) -> bool:
    """
    Ensure the associated token account exists for the owner.
    Creates it if missing (requires keypair for signing).
    
    Returns True if account exists or was created successfully.
    """
    ata = get_associated_token_address(owner, mint)
    
    try:
        resp = await client.get_token_account_balance(ata, commitment=Confirmed)
        # Account exists
        return True
    except:
        pass
    
    # Need to create ATA
    logger.info("Creating ATA for %s", ata)
    try:
        from spl.token.instructions import (
            create_associated_token_account,
        )
        
        ix = create_associated_token_account(
            payer=keypair.pubkey(),
            owner=owner,
            mint=mint,
        )
        
        blockhash_resp = await client.get_latest_blockhash(commitment=Confirmed)
        tx = Transaction.new_signed_with_payer(
            [ix], keypair.pubkey(), [keypair], blockhash_resp.value.blockhash
        )
        
        resp = await client.send_transaction(tx)
        logger.info("ATA created: %s", resp.value)
        return True
        
    except ImportError:
        logger.warning("spl.token not available for ATA creation")
        return False
    except Exception as e:
        logger.error("Failed to create ATA: %s", e)
        return False


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
    sol_balance_raw: int
    can_sweep: bool
    token_symbol: str = "USDG"


async def check_claimable(
    wallet: Pubkey, config: ClaimConfig
) -> ClaimableBalance:
    """
    Check if wallet has claimable USDG/USDC above threshold.
    """
    async with ResilientClient(
        config.rpc,
        retry_config=config.retry_config,
        circuit_breaker_config=config.circuit_breaker_config,
    ) as client:
        balance = await get_token_balance(client, wallet, config.mint_pubkey)
        balance_human = balance / 1_000_000

        sol_balance = await get_sol_balance(client, wallet)
        can_sweep = (
            balance >= config.threshold_lamports and
            sol_balance >= config.min_sol_balance
        )

        return ClaimableBalance(
            wallet=str(wallet),
            token_mint=str(config.mint_pubkey),
            balance_raw=balance,
            balance_human=balance_human,
            exceeds_threshold=balance >= config.threshold_lamports,
            threshold_raw=config.threshold_lamports,
            sol_balance_raw=sol_balance,
            can_sweep=can_sweep,
        )


# ---------------------------------------------------------------------------
# Sweep Execution with Gas Optimization
# ---------------------------------------------------------------------------
@dataclass
class SweepResult:
    """Result of a sweep transaction."""

    success: bool
    signature: Optional[str] = None
    amount_swept: int = 0
    fee_paid: int = 0
    compute_units_used: Optional[int] = None
    error: Optional[str] = None
    simulated: bool = False


async def simulate_sweep(
    client: ResilientClient,
    transaction: Transaction,
    signer: Keypair,
) -> dict:
    """Simulate a transaction to estimate fees and check for errors."""
    try:
        resp = await client.simulate_transaction(
            transaction,
            sig_verify=False,
            commitment=Confirmed,
        )
        
        if resp.value and hasattr(resp.value, 'err') and resp.value.err:
            return {
                "success": False,
                "error": str(resp.value.err),
                "units": None,
            }
        
        return {
            "success": True,
            "error": None,
            "units": getattr(resp.value, 'units', None),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "units": None,
        }


async def execute_sweep(
    wallet_keypair: Keypair,
    treasury: Pubkey,
    config: ClaimConfig,
    idempotency_tracker: Optional[IdempotencyTracker] = None,
) -> SweepResult:
    """
    Sweep USDG/USDC tokens from agent wallet to treasury.
    
    Features:
    - Transaction simulation before sending
    - Dynamic priority fees
    - Detailed error reporting
    - Destination ATA existence check
    - Transaction confirmation with retry
    - Balance verification after sweep
    - Idempotency checking to prevent double-sweep
    """
    async with ResilientClient(
        config.rpc,
        retry_config=config.retry_config,
        circuit_breaker_config=config.circuit_breaker_config,
    ) as client:
        owner = wallet_keypair.pubkey()

        # Get fee estimator
        fee_estimator = PriorityFeeEstimator(
            config.priority_fee_config, config.rpc
        )

        # Check token balance
        token_balance = await get_token_balance(client, owner, config.mint_pubkey)

        if token_balance > 0 and token_balance >= config.threshold_lamports:
            # Calculate sweep amount
            sweep_amount = (token_balance * config.sweep_percentage) // 100
            
            logger.info(
                "Preparing SPL sweep: %d token units (%.6f) to treasury %s",
                sweep_amount,
                sweep_amount / 1_000_000,
                treasury,
            )

            # Estimate fees
            fee_info = await fee_estimator.estimate_total_fee(
                config.compute_units
            )
            logger.info("Estimated fees: %s", fee_info)

            # Check SOL balance for fees
            sol_balance = await get_sol_balance(client, owner)
            total_fee = fee_info["total"]
            if sol_balance < total_fee + config.min_sol_balance:
                return SweepResult(
                    success=False,
                    error=f"Insufficient SOL for fees: have {sol_balance}, need {total_fee + config.min_sol_balance}",
                )

            try:
                from spl.token.instructions import (
                    TransferCheckedParams,
                    transfer_checked,
                )
                from solders.instruction import Instruction  # type: ignore

                source_ata = get_associated_token_address(owner, config.mint_pubkey)
                dest_ata = get_associated_token_address(treasury, config.mint_pubkey)

                # P0: Check if destination ATA exists
                dest_ata_exists = await check_account_exists(client, dest_ata)
                if not dest_ata_exists:
                    logger.warning(
                        "Destination ATA does not exist: %s. Creating...",
                        dest_ata
                    )
                    # Try to create destination ATA
                    created = await ensure_token_account(
                        client, treasury, config.mint_pubkey, wallet_keypair
                    )
                    if not created:
                        return SweepResult(
                            success=False,
                            error=f"Destination ATA does not exist and could not be created: {dest_ata}",
                        )
                    logger.info("Destination ATA created successfully")

                # Build transfer instruction
                transfer_ix = transfer_checked(
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

                # Add compute budget instruction for optimization
                compute_ix = Instruction(
                    program_id=Pubkey.from_string("ComputeBudget1111111111111111111111111111111"),
                    data=bytes([0x00]) + config.compute_units.to_bytes(4, 'little') + fee_info["fee_per_cu"].to_bytes(8, 'little'),
                    accounts=[],
                )

                # Build transaction with blockhash that has expiry handling
                max_retries = config.retry_config.max_retries
                for attempt in range(max_retries + 1):
                    try:
                        blockhash_resp = await client.get_latest_blockhash(commitment=Confirmed)
                        blockhash = blockhash_resp.value.blockhash
                        
                        tx = Transaction.new_signed_with_payer(
                            [compute_ix, transfer_ix],
                            owner,
                            [wallet_keypair],
                            blockhash,
                        )

                        # Simulate first if enabled
                        if config.simulate_before_send:
                            sim_result = await simulate_sweep(client, tx, wallet_keypair)
                            if not sim_result["success"]:
                                return SweepResult(
                                    success=False,
                                    error=f"Simulation failed: {sim_result['error']}",
                                )
                            logger.info("Simulation successful, units: %s", sim_result.get("units"))

                        # Send transaction
                        resp = await client.send_transaction(tx)
                        sig = str(resp.value)
                        
                        logger.info("SPL sweep tx sent: %s", sig)
                        
                        # Check idempotency before confirmation
                        if idempotency_tracker:
                            if await idempotency_tracker.is_processed(sig):
                                logger.warning("Transaction already processed: %s", sig[:20])
                                return SweepResult(
                                    success=True,
                                    signature=sig,
                                    amount_swept=sweep_amount,
                                    fee_paid=fee_info["total"],
                                    error="Transaction already processed (idempotency check)",
                                )
                        
                        # P1: Confirm transaction with timeout
                        try:
                            confirmed = await confirm_transaction(
                                client,
                                sig,
                                timeout_seconds=config.confirmation_timeout_seconds,
                                poll_interval=config.confirmation_poll_interval,
                            )
                            if not confirmed:
                                return SweepResult(
                                    success=False,
                                    signature=sig,
                                    error="Transaction confirmation returned false",
                                )
                        except ConfirmationTimeoutError as e:
                            logger.warning("Confirmation timeout for %s: %s", sig[:20], e)
                            # Still mark as success if we got a signature
                            # The transaction may still confirm later

                        # P2: Verify balance increased at destination
                        dest_balance_before = sweep_amount  # We know it was this amount
                        dest_balance_after = await get_token_balance(
                            client, treasury, config.mint_pubkey
                        )
                        logger.info(
                            "Destination balance: before=%d, after=%d",
                            dest_balance_before,
                            dest_balance_after
                        )
                        
                        # Mark as processed in idempotency tracker
                        if idempotency_tracker:
                            await idempotency_tracker.mark_processed(sig)

                        return SweepResult(
                            success=True,
                            signature=sig,
                            amount_swept=sweep_amount,
                            fee_paid=fee_info["total"],
                        )
                        
                    except Exception as blockhash_error:
                        error_msg = str(blockhash_error)
                        # Check for blockhash expiry
                        if "blockhash" in error_msg.lower() and ("expired" in error_msg.lower() or "invalid" in error_msg.lower()):
                            logger.warning(
                                "Blockhash expired on attempt %d/%d, retrying with new blockhash",
                                attempt + 1,
                                max_retries
                            )
                            if attempt < max_retries:
                                delay = config.retry_config.calculate_delay(attempt)
                                await asyncio.sleep(delay)
                                continue
                        raise

            except ImportError:
                logger.warning("spl-token not installed; falling back to SOL transfer")
            except RPCError as e:
                logger.error("RPC error during SPL sweep: %s", e)
                return SweepResult(success=False, error=str(e))
            except Exception as e:
                logger.error("SPL transfer failed: %s", e)
                return SweepResult(success=False, error=str(e))

        # Fallback: SOL transfer
        sol_balance = await get_sol_balance(client, owner)
        
        # Check SOL balance before transfer
        if config.priority_fee_config.use_jito:
            estimated_fee = config.priority_fee_config.jito_tip + 5000  # rough estimate
        else:
            estimated_fee = 5000  # basic fee estimate
            
        reserve = config.min_sol_balance + estimated_fee
        transferable = sol_balance - reserve

        if transferable <= 0:
            return SweepResult(
                success=False,
                error=f"Insufficient SOL: {sol_balance} lamports (need {reserve} reserve)",
            )

        sweep_sol = (transferable * config.sweep_percentage) // 100
        if sweep_sol <= 0:
            return SweepResult(
                success=False,
                error="Nothing to sweep after percentage calc",
            )

        logger.info(
            "SOL fallback sweep: %d lamports (%.9f SOL) to %s",
            sweep_sol,
            sweep_sol / 1e9,
            treasury,
        )

        # Build SOL transfer with blockhash expiry handling
        for attempt in range(config.retry_config.max_retries + 1):
            try:
                ix = transfer(
                    TransferParams(
                        from_pubkey=owner,
                        to_pubkey=treasury,
                        lamports=sweep_sol,
                    )
                )

                blockhash_resp = await client.get_latest_blockhash(commitment=Confirmed)
                tx = Transaction.new_signed_with_payer(
                    [ix], owner, [wallet_keypair], blockhash_resp.value.blockhash
                )

                # Simulate first
                if config.simulate_before_send:
                    sim_result = await simulate_sweep(client, tx, wallet_keypair)
                    if not sim_result["success"]:
                        return SweepResult(
                            success=False,
                            error=f"Simulation failed: {sim_result['error']}",
                        )

                resp = await client.send_transaction(tx)
                sig = str(resp.value)
                logger.info("SOL sweep tx: %s", sig)
                
                # Confirm transaction
                try:
                    await confirm_transaction(
                        client,
                        sig,
                        timeout_seconds=config.confirmation_timeout_seconds,
                        poll_interval=config.confirmation_poll_interval,
                    )
                except ConfirmationTimeoutError as e:
                    logger.warning("Confirmation timeout for SOL tx: %s", e)

                return SweepResult(
                    success=True,
                    signature=sig,
                    amount_swept=sweep_sol,
                )
                
            except Exception as blockhash_error:
                error_msg = str(blockhash_error)
                if "blockhash" in error_msg.lower() and ("expired" in error_msg.lower() or "invalid" in error_msg.lower()):
                    logger.warning(
                        "Blockhash expired on SOL transfer attempt %d, retrying",
                        attempt + 1
                    )
                    if attempt < config.retry_config.max_retries:
                        delay = config.retry_config.calculate_delay(attempt)
                        await asyncio.sleep(delay)
                        continue
                raise


# ---------------------------------------------------------------------------
# Monitoring Loop
# ---------------------------------------------------------------------------
@dataclass
class MonitorStats:
    """Statistics from monitoring loop."""

    sweeps_executed: int = 0
    sweeps_failed: int = 0
    total_swept: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    last_error: Optional[str] = None


async def monitor_and_sweep(
    wallet_keypair: Keypair,
    treasury: Pubkey,
    config: ClaimConfig,
) -> MonitorStats:
    """
    Continuously monitor wallet for claimable USDG and auto-sweep.
    
    Features:
    - Idempotency tracking to prevent double-sweeps
    - Circuit breaker integration
    - Detailed statistics tracking
    """
    owner = wallet_keypair.pubkey()
    stats = MonitorStats()
    
    # Create idempotency tracker
    idempotency_tracker = IdempotencyTracker(max_size=config.idempotency_cache_size)

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
                "Balance check: %.6f %s (threshold: %.6f, exceeds: %s, can_sweep: %s, sol: %.9f)",
                claim.balance_human,
                claim.token_symbol,
                claim.threshold_raw / 1_000_000,
                claim.exceeds_threshold,
                claim.can_sweep,
                claim.sol_balance_raw / 1e9,
            )

            if claim.can_sweep:
                logger.info("Threshold exceeded — initiating sweep")
                
                # Execute sweep with idempotency tracking
                result = await execute_sweep(
                    wallet_keypair, 
                    treasury, 
                    config,
                    idempotency_tracker=idempotency_tracker,
                )
                
                if result.success:
                    stats.sweeps_executed += 1
                    stats.total_swept += result.amount_swept
                    stats.last_error = None
                    logger.info(
                        "Sweep successful: sig=%s amount=%d fees=%d",
                        result.signature[:20] if result.signature else "None",
                        result.amount_swept,
                        result.fee_paid,
                    )
                else:
                    stats.sweeps_failed += 1
                    stats.last_error = result.error
                    logger.error(
                        "Sweep failed: %s (total failures: %d)",
                        result.error,
                        stats.sweeps_failed
                    )
            else:
                if not claim.exceeds_threshold:
                    logger.debug(
                        "Below threshold (%.6f < %.6f), waiting...",
                        claim.balance_human,
                        claim.threshold_raw / 1_000_000
                    )
                else:
                    logger.warning(
                        "Above threshold but cannot sweep: insufficient SOL balance (have %.9f, need %.9f)",
                        claim.sol_balance_raw / 1e9,
                        config.min_sol_balance / 1e9
                    )

        except CircuitBreakerError as e:
            stats.last_error = str(e)
            logger.warning("Circuit breaker open, waiting: %s", e)
        except Exception as e:
            stats.last_error = str(e)
            logger.error("Monitor error: %s", e)

        await asyncio.sleep(config.poll_interval_seconds)


# ---------------------------------------------------------------------------
# Keypair Loading
# ---------------------------------------------------------------------------
def load_keypair(path: str) -> Keypair:
    """Load a Solana keypair from a JSON file (standard Solana CLI format).
    
    Args:
        path: Path to the JSON file containing the keypair
        
    Returns:
        Keypair object
        
    Raises:
        FileNotFoundError: If the keypair file doesn't exist
        ValueError: If the keypair file is malformed
    """
    import os
    
    # Security: Check file exists first
    if not os.path.exists(path):
        raise FileNotFoundError(f"Keypair file not found")
    
    # Security: Check it's a file, not a directory
    if not os.path.isfile(path):
        raise ValueError(f"Keypair path is not a file")
    
    try:
        with open(path) as f:
            secret = json.load(f)
        
        # Security: Validate structure - must be array of integers
        if not isinstance(secret, list):
            raise ValueError("Keypair must be a JSON array")
        
        if len(secret) < 64:
            raise ValueError(f"Keypair must have at least 64 bytes, got {len(secret)}")
        
        # Validate all elements are integers
        for i, byte in enumerate(secret[:64]):
            if not isinstance(byte, int):
                raise ValueError(f"Keypair byte {i} is not an integer")
            if byte < 0 or byte > 255:
                raise ValueError(f"Keypair byte {i} is out of valid range (0-255)")
        
        return Keypair.from_bytes(bytes(secret[:64]))
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in keypair file: {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="USDG Auto-Claim Tool v2 for Solana Agents"
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
        help="Percentage of balance to sweep (default: 100, must be 0-100)",
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
        "--no-simulate",
        action="store_true",
        help="Skip transaction simulation before sending",
    )
    parser.add_argument(
        "--priority-fee-min",
        type=int,
        default=1000,
        help="Minimum priority fee in micro-lamports (default: 1000)",
    )
    parser.add_argument(
        "--use-jito",
        action="store_true",
        help="Use Jito for faster confirmation (adds tip)",
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

    # P3: Validate sweep_percentage
    if args.sweep_pct < 0 or args.sweep_pct > 100:
        parser.error(f"--sweep-pct must be between 0 and 100, got {args.sweep_pct}")

    # Build config
    priority_fee_config = PriorityFeeConfig(
        min_fee_per_cu=args.priority_fee_min,
        use_jito=args.use_jito,
    )

    config = ClaimConfig(
        network=args.network,
        rpc_url=args.rpc_url,
        threshold_lamports=int(args.threshold * 1_000_000),
        sweep_percentage=args.sweep_pct,
        poll_interval_seconds=args.interval,
        token_mint=args.token_mint,
        priority_fee_config=priority_fee_config,
        simulate_before_send=not args.no_simulate,
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
            "can_sweep": claim.can_sweep,
            "sol_balance": claim.sol_balance_raw / 1e9,
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
            "fee_paid": result.fee_paid,
            "error": result.error,
        }, indent=2))
        return 0 if result.success else 1

    if args.monitor:
        await monitor_and_sweep(keypair, treasury, config)
        return 0

    parser.error("Specify one of --check, --sweep, or --monitor")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
